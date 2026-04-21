import json
from unittest import mock

from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from api.auth import Auth0User
from api.models import IntervieweeBaselineProfile, PrepProfileSubmission, PrepSession, User
from api.tasks import run_prediction_task


TEST_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@override_settings(CACHES=TEST_CACHE)
class PrepSessionEndpointTests(APITestCase):
    def setUp(self):
        cache.clear()
        payload = {"sub": "test|prep-session", "email": "prep@example.com"}
        self.client.force_authenticate(user=Auth0User(payload))

    def test_create_prep_session_returns_prep_id(self):
        url = reverse("prep_sessions")
        response = self.client.post(
            url,
            data=json.dumps({"title": "Backend Engineer at Acme"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn("prep_id", response.json())
        self.assertEqual(response.json()["status"], PrepSession.STATUS_ACTIVE)

    def test_list_prep_sessions_returns_newest_first_with_is_latest(self):
        url = reverse("prep_sessions")
        self.client.post(
            url,
            data=json.dumps({"title": "First session"}),
            content_type="application/json",
        )
        self.client.post(
            url,
            data=json.dumps({"title": "Second session"}),
            content_type="application/json",
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("results", body)
        self.assertEqual(len(body["results"]), 2)
        self.assertEqual(body["results"][0]["title"], "Second session")
        self.assertTrue(body["results"][0]["is_latest"])
        self.assertFalse(body["results"][1]["is_latest"])
        self.assertEqual(body["results"][1]["title"], "First session")

    def test_get_prep_session_detail_returns_owned_session(self):
        db_user = User.objects.create(auth0_sub="test|detail", email="detail@example.com")
        prep_session = PrepSession.objects.create(
            user=db_user,
            title="Detail session",
            company_name="Acme",
        )
        self.client.force_authenticate(
            user=Auth0User({"sub": "test|detail", "email": "detail@example.com"})
        )

        url = reverse("prep_session_detail", kwargs={"prep_id": str(prep_session.prep_id)})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["prep_id"], str(prep_session.prep_id))
        self.assertEqual(body["title"], "Detail session")
        self.assertEqual(body["company_name"], "Acme")
        self.assertEqual(body["pipeline_status"], "WAITING_FOR_COUNTERPART_PROFILE")
        self.assertEqual(body["interviewee_source"], "MISSING")
        self.assertFalse(body["has_default_interviewee_profile"])
        self.assertEqual(body["prediction"]["status"], "NOT_READY")

    def test_interviewee_baseline_profile_get_returns_exists_false_when_missing(self):
        url = reverse("interviewee_baseline_profile")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["exists"])
        self.assertIsNone(body["profile"])

    def test_interviewee_baseline_profile_put_saves_profile(self):
        url = reverse("interviewee_baseline_profile")
        payload = {
            "source": "LINKEDIN",
            "source_url": "https://www.linkedin.com/in/default-interviewee/",
            "extracted_sections": {
                "experience": ["5 years backend engineering"],
                "education": ["BS Computer Science"],
            },
            "confidence_flags": {"edited_by_user": True},
            "metadata": {"submitted_from": "extension"},
        }
        response = self.client.put(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(IntervieweeBaselineProfile.objects.count(), 1)
        saved = IntervieweeBaselineProfile.objects.first()
        self.assertIn("EXPERIENCE:", saved.normalized_text)
        self.assertEqual(saved.source_url, payload["source_url"])

    def test_patch_prep_session_detail_updates_fields(self):
        db_user = User.objects.create(auth0_sub="test|patch", email="patch@example.com")
        prep_session = PrepSession.objects.create(user=db_user, title="Old title", company_name="OldCo")
        self.client.force_authenticate(
            user=Auth0User({"sub": "test|patch", "email": "patch@example.com"})
        )

        url = reverse("prep_session_detail", kwargs={"prep_id": str(prep_session.prep_id)})
        response = self.client.patch(
            url,
            data=json.dumps({"title": "New title", "company_name": "", "status": "CLOSED"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        prep_session.refresh_from_db()
        self.assertEqual(prep_session.title, "New title")
        self.assertIsNone(prep_session.company_name)
        self.assertEqual(prep_session.status, PrepSession.STATUS_CLOSED)

    def test_patch_prep_session_detail_rejects_empty_payload(self):
        db_user = User.objects.create(auth0_sub="test|patch-empty", email="patch-empty@example.com")
        prep_session = PrepSession.objects.create(user=db_user, title="Session")
        self.client.force_authenticate(
            user=Auth0User({"sub": "test|patch-empty", "email": "patch-empty@example.com"})
        )

        url = reverse("prep_session_detail", kwargs={"prep_id": str(prep_session.prep_id)})
        response = self.client.patch(url, data=json.dumps({}), content_type="application/json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())

    def test_delete_prep_session_archives_session(self):
        db_user = User.objects.create(auth0_sub="test|delete", email="delete@example.com")
        prep_session = PrepSession.objects.create(user=db_user, title="Session to close")
        self.client.force_authenticate(
            user=Auth0User({"sub": "test|delete", "email": "delete@example.com"})
        )

        detail_url = reverse("prep_session_detail", kwargs={"prep_id": str(prep_session.prep_id)})
        delete_response = self.client.delete(detail_url)
        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(delete_response.json()["archived"])

        prep_session.refresh_from_db()
        self.assertEqual(prep_session.status, PrepSession.STATUS_CLOSED)

        submit_url = reverse("submit_prep_profile", kwargs={"prep_id": str(prep_session.prep_id)})
        submit_response = self.client.post(
            submit_url,
            data=json.dumps(
                {
                    "role": "INTERVIEWEE",
                    "extracted_sections": {
                        "experience": ["2 years Python"],
                        "education": ["BS Computer Science"],
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(submit_response.status_code, 404)

    def test_submit_profile_requires_owned_active_prep_session(self):
        url = reverse("submit_prep_profile", kwargs={"prep_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"})
        payload = {
            "role": "INTERVIEWEE",
            "source": "LINKEDIN",
            "extracted_sections": {
                "experience": ["2 years Python"],
                "education": ["BS Computer Science"],
            },
        }
        response = self.client.post(url, data=json.dumps(payload), content_type="application/json")

        self.assertEqual(response.status_code, 404)

    def test_submit_profile_saves_normalized_text(self):
        db_user = User.objects.create(auth0_sub="test|existing", email="existing@example.com")
        prep_session = PrepSession.objects.create(user=db_user, title="ML interview")

        # authenticate as same user subject to match ownership
        self.client.force_authenticate(
            user=Auth0User({"sub": "test|existing", "email": "existing@example.com"})
        )
        url = reverse("submit_prep_profile", kwargs={"prep_id": str(prep_session.prep_id)})
        payload = {
            "role": "INTERVIEWER",
            "source_url": "https://www.linkedin.com/in/some-profile/",
            "extracted_sections": {
                "experience": ["Principal Engineer at ExampleCo"],
                "education": ["MS Software Engineering"],
                "skills": ["System Design", "Distributed Systems"],
            },
        }
        response = self.client.post(url, data=json.dumps(payload), content_type="application/json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(PrepProfileSubmission.objects.count(), 1)
        submission = PrepProfileSubmission.objects.first()
        self.assertIn("EXPERIENCE:", submission.normalized_text)
        self.assertEqual(submission.role, PrepProfileSubmission.ROLE_INTERVIEWER)

    def test_submit_profile_same_role_updates_existing_row(self):
        db_user = User.objects.create(auth0_sub="test|upsert", email="upsert@example.com")
        prep_session = PrepSession.objects.create(user=db_user, title="Data interview")

        self.client.force_authenticate(
            user=Auth0User({"sub": "test|upsert", "email": "upsert@example.com"})
        )
        url = reverse("submit_prep_profile", kwargs={"prep_id": str(prep_session.prep_id)})

        first_payload = {
            "role": "INTERVIEWEE",
            "extracted_sections": {
                "experience": ["2 years Python"],
                "education": ["BS Computer Science"],
            },
        }
        first_response = self.client.post(url, data=json.dumps(first_payload), content_type="application/json")
        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(PrepProfileSubmission.objects.count(), 1)

        second_payload = {
            "role": "INTERVIEWEE",
            "extracted_sections": {
                "experience": ["4 years Python", "Led backend platform team"],
                "education": ["BS Computer Science"],
                "skills": ["Django", "System Design"],
            },
        }
        second_response = self.client.post(url, data=json.dumps(second_payload), content_type="application/json")
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(PrepProfileSubmission.objects.count(), 1)

        submission = PrepProfileSubmission.objects.get(
            prep_session=prep_session,
            role=PrepProfileSubmission.ROLE_INTERVIEWEE,
        )
        self.assertIn("4 years Python", submission.normalized_text)
        self.assertIn("SKILLS:", submission.normalized_text)

    def test_submit_profile_allows_two_rows_max_per_session_by_role(self):
        db_user = User.objects.create(auth0_sub="test|two-roles", email="two-roles@example.com")
        prep_session = PrepSession.objects.create(user=db_user, title="Full prep")

        self.client.force_authenticate(
            user=Auth0User({"sub": "test|two-roles", "email": "two-roles@example.com"})
        )
        url = reverse("submit_prep_profile", kwargs={"prep_id": str(prep_session.prep_id)})

        interviewee_payload = {
            "role": "INTERVIEWEE",
            "extracted_sections": {
                "experience": ["3 years backend development"],
                "education": ["BS Computer Science"],
            },
        }
        interviewer_payload = {
            "role": "INTERVIEWER",
            "extracted_sections": {
                "experience": ["Staff Engineer at ExampleOrg"],
                "education": ["MS Computer Science"],
            },
        }

        first_response = self.client.post(
            url, data=json.dumps(interviewee_payload), content_type="application/json"
        )
        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(first_response.json()["pipeline_status"], "WAITING_FOR_COUNTERPART_PROFILE")

        second_response = self.client.post(
            url, data=json.dumps(interviewer_payload), content_type="application/json"
        )
        self.assertEqual(second_response.status_code, 201)
        self.assertEqual(second_response.json()["pipeline_status"], "READY_FOR_TOPIC_GENERATION")
        self.assertEqual(PrepProfileSubmission.objects.filter(prep_session=prep_session).count(), 2)

        third_response = self.client.post(
            url, data=json.dumps(interviewer_payload), content_type="application/json"
        )
        self.assertEqual(third_response.status_code, 200)
        self.assertEqual(PrepProfileSubmission.objects.filter(prep_session=prep_session).count(), 2)

    @mock.patch("api.views.run_prediction_task.delay")
    def test_submit_interviewer_uses_default_interviewee_profile(self, mock_delay):
        db_user = User.objects.create(auth0_sub="test|baseline-ready", email="baseline-ready@example.com")
        prep_session = PrepSession.objects.create(user=db_user, title="Baseline ready")
        IntervieweeBaselineProfile.objects.create(
            user=db_user,
            extracted_sections={
                "experience": ["6 years Python backend development"],
                "education": ["BS Software Engineering"],
            },
            normalized_text="EXPERIENCE:\n6 years Python backend development\n\nEDUCATION:\nBS Software Engineering",
        )
        self.client.force_authenticate(
            user=Auth0User({"sub": "test|baseline-ready", "email": "baseline-ready@example.com"})
        )
        url = reverse("submit_prep_profile", kwargs={"prep_id": str(prep_session.prep_id)})
        interviewer_payload = {
            "role": "INTERVIEWER",
            "extracted_sections": {
                "experience": ["Staff Engineer at ExampleOrg"],
                "education": ["MS Computer Science"],
            },
        }
        response = self.client.post(url, data=json.dumps(interviewer_payload), content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["pipeline_status"], "READY_FOR_TOPIC_GENERATION")
        self.assertEqual(response.json()["interviewee_source"], "DEFAULT")
        self.assertEqual(response.json()["prediction"]["status"], "RUNNING")
        self.assertEqual(mock_delay.call_count, 1)

    def test_session_interviewee_profile_overrides_default_source(self):
        db_user = User.objects.create(auth0_sub="test|override-source", email="override@example.com")
        prep_session = PrepSession.objects.create(user=db_user, title="Override source")
        IntervieweeBaselineProfile.objects.create(
            user=db_user,
            extracted_sections={
                "experience": ["10 years legacy profile"],
                "education": ["Old Degree"],
            },
            normalized_text="EXPERIENCE:\n10 years legacy profile\n\nEDUCATION:\nOld Degree",
        )
        PrepProfileSubmission.objects.create(
            prep_session=prep_session,
            user=db_user,
            role=PrepProfileSubmission.ROLE_INTERVIEWEE,
            extracted_sections={
                "experience": ["2 years modern profile"],
                "education": ["BS Computer Science"],
            },
            normalized_text="EXPERIENCE:\n2 years modern profile\n\nEDUCATION:\nBS Computer Science",
        )
        self.client.force_authenticate(
            user=Auth0User({"sub": "test|override-source", "email": "override@example.com"})
        )

        detail_url = reverse("prep_session_detail", kwargs={"prep_id": str(prep_session.prep_id)})
        detail_response = self.client.get(detail_url)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["interviewee_source"], "SESSION")
        self.assertTrue(detail_response.json()["has_default_interviewee_profile"])

    @mock.patch("api.views.run_prediction_task.delay")
    def test_submit_profile_queues_prediction_once_ready(self, mock_delay):
        db_user = User.objects.create(auth0_sub="test|predict-from-prep", email="prep-flow@example.com")
        prep_session = PrepSession.objects.create(user=db_user, title="Full prep")
        self.client.force_authenticate(
            user=Auth0User({"sub": "test|predict-from-prep", "email": "prep-flow@example.com"})
        )
        url = reverse("submit_prep_profile", kwargs={"prep_id": str(prep_session.prep_id)})

        interviewee_payload = {
            "role": "INTERVIEWEE",
            "extracted_sections": {
                "experience": ["3 years backend development"],
                "education": ["BS Computer Science"],
                "skills": ["Python", "Django"],
            },
        }
        interviewer_payload = {
            "role": "INTERVIEWER",
            "extracted_sections": {
                "experience": ["Staff Engineer at ExampleOrg"],
                "education": ["MS Computer Science"],
            },
        }

        first_response = self.client.post(
            url,
            data=json.dumps(interviewee_payload),
            content_type="application/json",
        )
        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(first_response.json()["pipeline_status"], "WAITING_FOR_COUNTERPART_PROFILE")
        self.assertIsNone(first_response.json()["prediction"])
        mock_delay.assert_not_called()

        second_response = self.client.post(
            url,
            data=json.dumps(interviewer_payload),
            content_type="application/json",
        )
        self.assertEqual(second_response.status_code, 201)
        self.assertEqual(second_response.json()["pipeline_status"], "READY_FOR_TOPIC_GENERATION")
        self.assertEqual(second_response.json()["prediction"]["status"], "RUNNING")
        self.assertEqual(mock_delay.call_count, 1)

    @mock.patch("api.prediction_service.generate_questions")
    def test_submit_profile_reuses_completed_prediction_without_requeue(self, mock_generate):
        mock_generate.return_value = {"html": "<article>Cached prep questions</article>"}
        db_user = User.objects.create(auth0_sub="test|repeat-prep", email="repeat@example.com")
        prep_session = PrepSession.objects.create(user=db_user, title="Repeat prep")
        self.client.force_authenticate(
            user=Auth0User({"sub": "test|repeat-prep", "email": "repeat@example.com"})
        )
        url = reverse("submit_prep_profile", kwargs={"prep_id": str(prep_session.prep_id)})

        interviewee_payload = {
            "role": "INTERVIEWEE",
            "extracted_sections": {
                "experience": ["2 years Python"],
                "education": ["BS Computer Science"],
            },
        }
        interviewer_payload = {
            "role": "INTERVIEWER",
            "extracted_sections": {
                "experience": ["Engineering Manager"],
                "education": ["MS Software Engineering"],
            },
        }

        self.client.post(url, data=json.dumps(interviewee_payload), content_type="application/json")
        with mock.patch("api.views.run_prediction_task.delay") as mock_delay:
            ready_response = self.client.post(url, data=json.dumps(interviewer_payload), content_type="application/json")
        self.assertEqual(ready_response.status_code, 201)
        self.assertEqual(ready_response.json()["prediction"]["status"], "RUNNING")
        self.assertEqual(mock_delay.call_count, 1)

        run_prediction_task.run(
            user_identifier="test|repeat-prep",
            db_user_id=db_user.id,
            interviewee={
                "name": "Interviewee",
                "email": "repeat@example.com",
                "education": "BS Computer Science",
                "experience": "EXPERIENCE:\n2 years Python\n\nEDUCATION:\nBS Computer Science",
            },
            interviewer={
                "name": "Interviewer",
                "education": "MS Software Engineering",
                "experience": "EXPERIENCE:\nEngineering Manager\n\nEDUCATION:\nMS Software Engineering",
            },
        )

        with mock.patch("api.views.run_prediction_task.delay") as repeat_delay:
            repeat_response = self.client.post(url, data=json.dumps(interviewer_payload), content_type="application/json")
        self.assertEqual(ready_response.status_code, 201)
        self.assertEqual(repeat_response.status_code, 200)
        self.assertEqual(repeat_response.json()["prediction"]["status"], "COMPLETED")
        self.assertEqual(
            repeat_response.json()["prediction"]["result"],
            {"html": "<article>Cached prep questions</article>"},
        )
        repeat_delay.assert_not_called()
        self.assertEqual(mock_generate.call_count, 1)

    @mock.patch("api.prediction_service.generate_questions")
    def test_get_prep_prediction_returns_completed_result_after_task_finishes(self, mock_generate):
        mock_generate.return_value = {"html": "<article>Async prep questions</article>"}
        db_user = User.objects.create(auth0_sub="test|prep-status", email="status@example.com")
        prep_session = PrepSession.objects.create(user=db_user, title="Status prep")
        self.client.force_authenticate(
            user=Auth0User({"sub": "test|prep-status", "email": "status@example.com"})
        )
        submit_url = reverse("submit_prep_profile", kwargs={"prep_id": str(prep_session.prep_id)})
        status_url = reverse("get_prep_prediction", kwargs={"prep_id": str(prep_session.prep_id)})

        self.client.post(
            submit_url,
            data=json.dumps(
                {
                    "role": "INTERVIEWEE",
                    "extracted_sections": {
                        "experience": ["2 years Python"],
                        "education": ["BS Computer Science"],
                    },
                }
            ),
            content_type="application/json",
        )
        with mock.patch("api.views.run_prediction_task.delay"):
            self.client.post(
                submit_url,
                data=json.dumps(
                    {
                        "role": "INTERVIEWER",
                        "extracted_sections": {
                            "experience": ["Senior Engineering Manager"],
                            "education": ["MS Software Engineering"],
                        },
                    }
                ),
                content_type="application/json",
            )

        run_prediction_task.run(
            user_identifier="test|prep-status",
            db_user_id=db_user.id,
            interviewee={
                "name": "Interviewee",
                "email": "status@example.com",
                "education": "BS Computer Science",
                "experience": "EXPERIENCE:\n2 years Python\n\nEDUCATION:\nBS Computer Science",
            },
            interviewer={
                "name": "Interviewer",
                "education": "MS Software Engineering",
                "experience": "EXPERIENCE:\nSenior Engineering Manager\n\nEDUCATION:\nMS Software Engineering",
            },
        )

        response = self.client.get(status_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["pipeline_status"], "READY_FOR_TOPIC_GENERATION")
        self.assertEqual(response.json()["prediction"]["status"], "COMPLETED")
        self.assertEqual(
            response.json()["prediction"]["result"],
            {"html": "<article>Async prep questions</article>"},
        )
