import json
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from api.auth import Auth0User
from api.models import (
    IntervieweeBaselineProfile,
    PrepProfileSubmission,
    PrepSession,
    User,
)
from api.views import (
    build_generate_user_message,
    build_submit_profile_next_action,
    build_submit_profile_user_message,
    profile_state_response_fields,
    resolve_session_profile_state,
)

TEST_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def _profile_state(**overrides):
    base = {
        "pipeline_status": "WAITING_FOR_COUNTERPART_PROFILE",
        "has_interviewee_profile": False,
        "has_interviewer_profile": False,
        "has_session_interviewee_profile": False,
        "has_session_interviewer_profile": False,
        "can_generate_prep": False,
        "has_default_interviewee_profile": False,
        "interviewee_source": "MISSING",
    }
    base.update(overrides)
    return base


class PrepSessionSaveGenerateHelperTests(SimpleTestCase):
    def test_build_submit_profile_user_message_when_both_session_profiles_ready(self):
        state = _profile_state(
            can_generate_prep=True, pipeline_status="READY_FOR_TOPIC_GENERATION"
        )
        message = build_submit_profile_user_message(
            PrepProfileSubmission.ROLE_INTERVIEWEE, state
        )
        self.assertIn("Interviewee profile saved", message)
        self.assertIn("Generate interview prep", message)

    def test_build_submit_profile_user_message_lists_missing_counterpart(self):
        state = _profile_state(
            has_session_interviewee_profile=True,
            has_interviewee_profile=True,
            interviewee_source="SESSION",
        )
        message = build_submit_profile_user_message(
            PrepProfileSubmission.ROLE_INTERVIEWEE, state
        )
        self.assertIn("interviewer", message.lower())

    def test_build_submit_profile_next_action_when_ready_to_generate(self):
        state = _profile_state(can_generate_prep=True)
        self.assertEqual(build_submit_profile_next_action(state), "GENERATE_PREP")

    def test_build_submit_profile_next_action_when_waiting_for_counterpart(self):
        state = _profile_state(can_generate_prep=False)
        self.assertEqual(
            build_submit_profile_next_action(state), "SUBMIT_COUNTERPART_PROFILE"
        )

    def test_build_generate_user_message_for_running_prediction(self):
        message = build_generate_user_message({"status": "RUNNING"})
        self.assertIn("started generating", message.lower())

    def test_build_generate_user_message_for_completed_prediction(self):
        message = build_generate_user_message({"status": "COMPLETED"})
        self.assertIn("ready", message.lower())

    def test_build_generate_user_message_for_cached_completed_prediction(self):
        message = build_generate_user_message(
            {"status": "COMPLETED"}, generation_source="cache"
        )
        self.assertIn("loaded your saved interview prep", message.lower())

    def test_build_generate_user_message_for_in_progress_generation(self):
        message = build_generate_user_message(
            {"status": "RUNNING"}, generation_source="in_progress"
        )
        self.assertIn("already running", message.lower())

    def test_build_generate_user_message_for_failed_prediction(self):
        message = build_generate_user_message({"status": "FAILED"})
        self.assertIn("could not generate", message.lower())

    def test_profile_state_response_fields_exposes_session_flags(self):
        state = _profile_state(
            can_generate_prep=True,
            has_session_interviewee_profile=True,
            has_session_interviewer_profile=True,
            pipeline_status="READY_FOR_TOPIC_GENERATION",
        )
        fields = profile_state_response_fields(state)
        self.assertTrue(fields["can_generate_prep"])
        self.assertTrue(fields["has_session_interviewee_profile"])
        self.assertTrue(fields["has_session_interviewer_profile"])


class ResolveSessionProfileStateTests(TestCase):
    def test_can_generate_requires_both_session_submissions(self):
        db_user = User.objects.create(
            auth0_sub="test|state-both", email="both@example.com"
        )
        prep_session = PrepSession.objects.create(user=db_user, title="Both profiles")
        PrepProfileSubmission.objects.create(
            prep_session=prep_session,
            user=db_user,
            role=PrepProfileSubmission.ROLE_INTERVIEWEE,
            extracted_sections={"experience": ["Python"]},
        )
        PrepProfileSubmission.objects.create(
            prep_session=prep_session,
            user=db_user,
            role=PrepProfileSubmission.ROLE_INTERVIEWER,
            extracted_sections={"experience": ["Manager"]},
        )

        state = resolve_session_profile_state(prep_session, db_user)
        self.assertTrue(state["can_generate_prep"])
        self.assertEqual(state["pipeline_status"], "READY_FOR_TOPIC_GENERATION")

    def test_default_interviewee_does_not_enable_can_generate(self):
        db_user = User.objects.create(
            auth0_sub="test|state-default", email="default@example.com"
        )
        prep_session = PrepSession.objects.create(user=db_user, title="Default only")
        IntervieweeBaselineProfile.objects.create(
            user=db_user,
            extracted_sections={"experience": ["Default interviewee"]},
            normalized_text="EXPERIENCE:\nDefault interviewee",
        )
        PrepProfileSubmission.objects.create(
            prep_session=prep_session,
            user=db_user,
            role=PrepProfileSubmission.ROLE_INTERVIEWER,
            extracted_sections={"experience": ["Interviewer only"]},
        )

        state = resolve_session_profile_state(prep_session, db_user)
        self.assertEqual(state["interviewee_source"], "DEFAULT")
        self.assertFalse(state["has_session_interviewee_profile"])
        self.assertFalse(state["can_generate_prep"])
        self.assertEqual(state["pipeline_status"], "WAITING_FOR_COUNTERPART_PROFILE")


@override_settings(CACHES=TEST_CACHE)
class PrepSessionSaveGenerateAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        self.client.force_authenticate(
            user=Auth0User({"sub": "test|save-generate", "email": "sg@example.com"})
        )
        self.db_user = User.objects.create(
            auth0_sub="test|save-generate", email="sg@example.com"
        )

    def _create_session_with_both_profiles(self):
        prep_session = PrepSession.objects.create(
            user=self.db_user, title="Save generate session"
        )
        PrepProfileSubmission.objects.create(
            prep_session=prep_session,
            user=self.db_user,
            role=PrepProfileSubmission.ROLE_INTERVIEWEE,
            extracted_sections={"experience": ["2 years Python"]},
        )
        PrepProfileSubmission.objects.create(
            prep_session=prep_session,
            user=self.db_user,
            role=PrepProfileSubmission.ROLE_INTERVIEWER,
            extracted_sections={"experience": ["Staff engineer"]},
        )
        return prep_session

    def test_submit_profile_save_only_response_shape(self):
        prep_session = PrepSession.objects.create(user=self.db_user, title="Shape test")
        url = reverse(
            "submit_prep_profile", kwargs={"prep_id": str(prep_session.prep_id)}
        )
        payload = {
            "role": "INTERVIEWEE",
            "extracted_sections": {
                "experience": ["Backend engineer"],
                "education": ["BS CS"],
            },
        }

        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIsNone(body["prediction"])
        self.assertEqual(body["next_action"], "SUBMIT_COUNTERPART_PROFILE")
        self.assertFalse(body["can_generate_prep"])
        self.assertFalse(body["has_session_interviewer_profile"])
        self.assertTrue(body["has_session_interviewee_profile"])
        self.assertIn("interviewer", body["user_message"].lower())

    @mock.patch("api.views.run_prediction_task.delay")
    def test_submit_profile_does_not_enqueue_when_both_profiles_present(
        self, mock_delay
    ):
        prep_session = self._create_session_with_both_profiles()
        url = reverse(
            "submit_prep_profile", kwargs={"prep_id": str(prep_session.prep_id)}
        )
        payload = {
            "role": "INTERVIEWEE",
            "extracted_sections": {
                "experience": ["Updated interviewee"],
                "education": ["BS CS"],
            },
        }

        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["can_generate_prep"])
        self.assertEqual(body["next_action"], "GENERATE_PREP")
        self.assertIsNone(body["prediction"])
        mock_delay.assert_not_called()

    def test_prep_session_detail_exposes_can_generate_prep(self):
        prep_session = self._create_session_with_both_profiles()
        url = reverse(
            "prep_session_detail", kwargs={"prep_id": str(prep_session.prep_id)}
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["can_generate_prep"])
        self.assertTrue(body["has_session_interviewee_profile"])
        self.assertTrue(body["has_session_interviewer_profile"])

    def test_get_prep_session_role_profile_rejects_invalid_role(self):
        prep_session = PrepSession.objects.create(
            user=self.db_user, title="Invalid role"
        )
        url = reverse(
            "get_prep_session_role_profile",
            kwargs={"prep_id": str(prep_session.prep_id), "role": "MODERATOR"},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid role", response.json()["detail"])

    def test_get_prep_session_role_profile_accepts_lowercase_role(self):
        prep_session = PrepSession.objects.create(user=self.db_user, title="Lower role")
        PrepProfileSubmission.objects.create(
            prep_session=prep_session,
            user=self.db_user,
            role=PrepProfileSubmission.ROLE_INTERVIEWER,
            extracted_sections={"experience": ["Lead"]},
            metadata={"profile_name": "Pat Interviewer"},
        )
        url = reverse(
            "get_prep_session_role_profile",
            kwargs={"prep_id": str(prep_session.prep_id), "role": "interviewer"},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["exists"])
        self.assertEqual(response.json()["profile"]["profile_name"], "Pat Interviewer")

    def test_get_prep_session_role_profile_does_not_return_baseline_interviewee(self):
        prep_session = PrepSession.objects.create(
            user=self.db_user, title="Baseline excluded"
        )
        IntervieweeBaselineProfile.objects.create(
            user=self.db_user,
            extracted_sections={"experience": ["Default only"]},
            normalized_text="EXPERIENCE:\nDefault only",
            metadata={"profile_name": "Default Person"},
        )
        url = reverse(
            "get_prep_session_role_profile",
            kwargs={"prep_id": str(prep_session.prep_id), "role": "INTERVIEWEE"},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["exists"])
        self.assertIsNone(response.json()["profile"])

    def test_generate_prep_returns_404_for_other_users_session(self):
        other_user = User.objects.create(
            auth0_sub="test|other-user", email="other@example.com"
        )
        prep_session = PrepSession.objects.create(
            user=other_user, title="Owned by other"
        )
        PrepProfileSubmission.objects.create(
            prep_session=prep_session,
            user=other_user,
            role=PrepProfileSubmission.ROLE_INTERVIEWEE,
            extracted_sections={"experience": ["Other"]},
        )
        PrepProfileSubmission.objects.create(
            prep_session=prep_session,
            user=other_user,
            role=PrepProfileSubmission.ROLE_INTERVIEWER,
            extracted_sections={"experience": ["Other interviewer"]},
        )
        url = reverse(
            "generate_prep_session_prediction",
            kwargs={"prep_id": str(prep_session.prep_id)},
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 404)

    @mock.patch("api.views.run_prediction_task.delay")
    def test_generate_prep_user_message_when_job_starts(self, mock_delay):
        prep_session = self._create_session_with_both_profiles()
        url = reverse(
            "generate_prep_session_prediction",
            kwargs={"prep_id": str(prep_session.prep_id)},
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_delay.call_count, 1)
        self.assertIn("started generating", response.json()["user_message"].lower())
        self.assertEqual(response.json()["next_action"], "OPEN_DASHBOARD")
