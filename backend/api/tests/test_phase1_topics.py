import json
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from api.ai_client import (
    OUTPUT_MODE,
    PROMPT_VERSION,
    AIClientError,
    _parse_prediction_payload,
)
from api.auth import Auth0User
from api.models import InterviewPrediction, PredictionTopic, PrepSession, User
from api.prediction_service import compute_fingerprint, execute_prediction_job
from api.profile_trim import trim_predict_person, trim_profile_field
from api.topic_service import replace_prediction_topics

# In-process cache — CI has no Redis (see deploy.yml test job).
TEST_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

SAMPLE_TOPICS = [
    {
        "topic_key": "system-design",
        "title": "System design",
        "emoji": "🧠",
        "likelihood": "HIGH",
        "why": "B is a staff engineer.",
        "study_anchors": ["scalability", "trade-offs"],
    },
    {
        "topic_key": "python-depth",
        "title": "Python depth",
        "emoji": "⚙️",
        "likelihood": "HIGH",
        "why": "Overlap on A's backend work.",
        "study_anchors": ["asyncio"],
    },
    {
        "topic_key": "behavioral",
        "title": "Behavioral",
        "emoji": "🎙️",
        "likelihood": "MEDIUM",
        "why": "B's management background.",
        "study_anchors": ["STAR stories"],
    },
    {
        "topic_key": "culture",
        "title": "Culture fit",
        "emoji": "📋",
        "likelihood": "LOWER",
        "why": "Standard closing topics.",
        "study_anchors": ["team collaboration"],
    },
]


def sample_prediction_result():
    return {
        "output_mode": OUTPUT_MODE,
        "markdown": "# 🎯 Interview Prep: A ← topics from B",
        "topics": SAMPLE_TOPICS,
    }


class ParsePredictionPayloadTests(TestCase):
    def test_parses_topics_json(self):
        payload = sample_prediction_result()
        raw = json.dumps(payload)
        parsed = _parse_prediction_payload(raw)
        self.assertEqual(parsed["output_mode"], OUTPUT_MODE)
        self.assertEqual(len(parsed["topics"]), 4)
        self.assertIn("Interview Prep", parsed["markdown"])

    def test_rejects_truncated_json(self):
        raw = '{"output_mode": "topics_v1", "markdown": "# Hi", "topics": ['
        with self.assertRaises(AIClientError):
            _parse_prediction_payload(raw)

    def test_rejects_too_few_topics(self):
        payload = {
            "output_mode": OUTPUT_MODE,
            "markdown": "# Prep",
            "topics": SAMPLE_TOPICS[:2],
        }
        with self.assertRaises(AIClientError):
            _parse_prediction_payload(json.dumps(payload))


class ProfileTrimTests(TestCase):
    def test_trims_long_experience(self):
        long_text = "x" * 20_000
        trimmed = trim_profile_field(long_text, "experience")
        self.assertLess(len(trimmed), 20_000)
        self.assertIn("[Profile trimmed for length]", trimmed)

    def test_trim_predict_person(self):
        person = {"name": "A", "experience": "y" * 20_000, "education": "BS"}
        out = trim_predict_person(person)
        self.assertLess(len(out["experience"]), 20_000)


class FingerprintOutputModeTests(TestCase):
    def test_output_mode_in_fingerprint(self):
        interviewee = {
            "name": "A",
            "email": "a@x.com",
            "education": "BS",
            "experience": "Py",
        }
        interviewer = {"name": "B", "education": "MS", "experience": "Eng"}
        fp = compute_fingerprint(
            "user-1",
            interviewee,
            interviewer,
            prompt_version=PROMPT_VERSION,
            interview_context={"target_role": "Dev", "target_company": ""},
        )
        fp_old = compute_fingerprint(
            "user-1",
            interviewee,
            interviewer,
            prompt_version="4",
            interview_context={"target_role": "Dev", "target_company": ""},
        )
        self.assertNotEqual(fp, fp_old)


class TopicPersistenceTests(TestCase):
    def test_replace_prediction_topics(self):
        user = User.objects.create(auth0_sub="test|topics", email="topics@example.com")
        prediction = InterviewPrediction.objects.create(
            fingerprint="fp-topics-test",
            user=user,
            status=InterviewPrediction.STATUS_COMPLETED,
        )
        rows = replace_prediction_topics(prediction, SAMPLE_TOPICS)
        self.assertEqual(len(rows), 4)
        self.assertEqual(
            PredictionTopic.objects.filter(prediction=prediction).count(), 4
        )
        self.assertEqual(rows[0]["topic_key"], "system-design")


@override_settings(CACHES=TEST_CACHE)
class ExecutePredictionJobIntegrationTests(TestCase):
    def setUp(self):
        cache.clear()

    @mock.patch("api.prediction_service.generate_questions")
    def test_persists_topics_on_completion(self, mock_generate):
        mock_generate.return_value = sample_prediction_result()
        user = User.objects.create(auth0_sub="test|job", email="job@example.com")
        interviewee = {
            "name": "A",
            "email": "a@x.com",
            "education": "BS",
            "experience": "Python",
        }
        interviewer = {"name": "B", "education": "MS", "experience": "Staff"}

        result, status_code = execute_prediction_job(
            user_identifier="test|job",
            db_user=user,
            interviewee=interviewee,
            interviewer=interviewer,
            interview_context={"target_role": "Backend", "target_company": "Acme"},
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(len(result["topics"]), 4)
        pred = InterviewPrediction.objects.get(user=user)
        self.assertEqual(pred.topics.count(), 4)


@override_settings(CACHES=TEST_CACHE)
class GetPrepPredictionTopicsTests(APITestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    @mock.patch("api.prediction_service.generate_questions")
    def test_get_prep_prediction_includes_topics(self, mock_generate):
        mock_generate.return_value = sample_prediction_result()
        db_user = User.objects.create(
            auth0_sub="test|prep-topics", email="prep-topics@example.com"
        )
        prep_session = PrepSession.objects.create(
            user=db_user,
            title="Backend Engineer",
            company_name="Acme",
        )
        from api.models import PrepProfileSubmission
        from api.tasks import run_prediction_task

        PrepProfileSubmission.objects.create(
            prep_session=prep_session,
            user=db_user,
            role=PrepProfileSubmission.ROLE_INTERVIEWEE,
            extracted_sections={"experience": ["Python dev"], "education": ["BS"]},
        )
        PrepProfileSubmission.objects.create(
            prep_session=prep_session,
            user=db_user,
            role=PrepProfileSubmission.ROLE_INTERVIEWER,
            extracted_sections={"experience": ["Staff Eng"], "education": ["MS"]},
        )

        self.client.force_authenticate(
            user=Auth0User(
                {"sub": "test|prep-topics", "email": "prep-topics@example.com"}
            )
        )
        generate_url = reverse(
            "generate_prep_session_prediction",
            kwargs={"prep_id": str(prep_session.prep_id)},
        )
        status_url = reverse(
            "get_prep_prediction", kwargs={"prep_id": str(prep_session.prep_id)}
        )

        with mock.patch("api.views.run_prediction_task.delay"):
            self.client.post(generate_url)

        from api.views import (
            build_predict_payload_from_profile_state,
            resolve_session_profile_state,
        )

        profile_state = resolve_session_profile_state(prep_session, db_user)
        interviewee, interviewer, interview_context = (
            build_predict_payload_from_profile_state(
                profile_state,
                user_email=db_user.email,
                prep_session=prep_session,
            )
        )
        run_prediction_task.run(
            user_identifier="test|prep-topics",
            db_user_id=db_user.id,
            interviewee=interviewee,
            interviewer=interviewer,
            interview_context=interview_context,
            prep_session_id=str(prep_session.prep_id),
        )

        response = self.client.get(status_url)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["prediction"]["status"], "COMPLETED")
        topics = body["prediction"]["result"]["topics"]
        self.assertEqual(len(topics), 4)
        self.assertEqual(topics[0]["title"], "System design")
