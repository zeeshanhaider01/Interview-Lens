from django.test import TestCase, override_settings
from django.core.cache import cache
from django.urls import reverse
from api.models import InterviewPrediction
from django.conf import settings
from unittest import mock
import json

# Tests cover:
#  - model creation
#  - cache behavior toggled by ENABLE_CACHING flag
#  - predict_questions endpoint basic behavior (mocking OpenAI client)

class CachingModelTests(TestCase):
    def setUp(self):
        InterviewPrediction.objects.all().delete()
        cache.clear()

    def test_model_creation_and_str(self):
        obj = InterviewPrediction.objects.create(
            fingerprint="abc123",
            status=InterviewPrediction.STATUS_RUNNING
        )
        self.assertEqual(str(obj), "abc123 (RUNNING)")
        self.assertEqual(obj.status, InterviewPrediction.STATUS_RUNNING)

class PredictEndpointTests(TestCase):
    def setUp(self):
        InterviewPrediction.objects.all().delete()
        cache.clear()

    @mock.patch("api.openai_client.generate_questions")
    def test_endpoint_with_caching_disabled_calls_openai_directly(self, mock_generate):
        # Force feature flag OFF to ensure no caching/lock used
        mock_resp = {"html": "<article>QA</article>"}
        mock_generate.return_value = mock_resp

        with override_settings(ENABLE_CACHING=False):
            payload = {
                "interviewee": {"name": "Alice", "email": "a@x.com", "education": "CS", "experience": "2y"},
                "interviewer": {"name": "Bob", "education": "SE", "experience": "5y"}
            }
            # Using client to call the endpoint
            url = reverse("predict_questions")
            response = self.client.post(url, data=json.dumps(payload), content_type="application/json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), mock_resp)
            mock_generate.assert_called_once()

    @mock.patch("api.openai_client.generate_questions")
    def test_endpoint_with_caching_enabled_uses_db_and_cache(self, mock_generate):
        mock_resp = {"html": "<article>Cached</article>"}
        mock_generate.return_value = mock_resp
        payload = {
            "interviewee": {"name": "Alice", "email": "a@x.com", "education": "CS", "experience": "2y"},
            "interviewer": {"name": "Bob", "education": "SE", "experience": "5y"}
        }
        url = reverse("predict_questions")

        # First call: should trigger OpenAI call and store in DB/cache
        response1 = self.client.post(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response1.json(), mock_resp)
        self.assertEqual(mock_generate.call_count, 1)

        # Second call: should return from cache/DB without calling OpenAI again
        response2 = self.client.post(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response2.status_code, 200)
        # OpenAI should not be called again
        self.assertEqual(mock_generate.call_count, 1)