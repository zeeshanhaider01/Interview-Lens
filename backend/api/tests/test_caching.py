from django.test import TestCase, override_settings
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APITestCase
from api.models import InterviewPrediction, User
from api.auth import Auth0User
from unittest import mock
import json

# Use an in-process cache so tests never require a live Redis connection.
TEST_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Tests cover:
#  - model creation
#  - cache behavior toggled by ENABLE_CACHING flag
#  - predict_questions endpoint basic behavior (mocking OpenAI client)


# --- unittest.mock.patch (quick reference) ------------------------------------
# mock.patch(...) is a *function* in the standard library module unittest.mock.
# Used as @mock.patch("dotted.path.to.name"), it temporarily replaces the object
# at that import path (e.g. api.views.generate_questions) with a fake
# for the duration of the test, so we never call the real OpenAI / LLM / network.
#
# Main argument: the string target — where to patch (patch "where it is used").
# Optional keyword args exist (e.g. new=...) but we use the defaults here.
#
# As a *decorator*, patch does not assign a variable by itself: when the test
# runs, the test runner passes in one extra argument — by default a MagicMock
# instance. You choose the parameter name (e.g. mock_generate); that name is
# just a reference to that MagicMock. Set .return_value to control what the
# fake "function" returns; use .call_count / assert_called_* to assert calls.
# ------------------------------------------------------------------------------

@override_settings(CACHES=TEST_CACHE)
class ModelTests(TestCase):
    def setUp(self):
        # this method will be called before each test
        # we are clearing the cache before each test to ensure a clean state.
        cache.clear()
        # no need to call InterviewPrediction.objects.all().delete() here explicitly.
        # django will clear the database automatically before each test.

    def test_model_creation_and_str(self):
        user = User.objects.create(auth0_sub="test|sub-abc", email="test@example.com")
        obj = InterviewPrediction.objects.create(
            fingerprint="abc123",
            user=user,
            status=InterviewPrediction.STATUS_RUNNING,
        )
        self.assertEqual(str(obj), "abc123 (RUNNING)")
        self.assertEqual(obj.status, InterviewPrediction.STATUS_RUNNING)

@override_settings(CACHES=TEST_CACHE)
class PredictEndpointTests(APITestCase):
    def setUp(self):
        # this method will be called before each test
        # we are clearing the cache before each test to ensure a clean state.
        cache.clear()
        payload = {"sub": "test|predict-endpoint", "email": "a@x.com"}
        self.client.force_authenticate(user=Auth0User(payload))

    @mock.patch("api.views.generate_questions")
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

    @mock.patch("api.views.generate_questions")
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
