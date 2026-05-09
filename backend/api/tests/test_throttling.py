from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from api.auth import Auth0User

TEST_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

NORMAL_SUB = "test|normal-user"
ADMIN_SUB = "test|admin-user"

# Override the full REST_FRAMEWORK dict so DRF picks up the test rate (3/day).
# Using DAILY_RATELIMIT alone is not enough because DRF computes
# DEFAULT_THROTTLE_RATES once at settings load time from the env var.
TEST_REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["api.auth.Auth0JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": ["api.throttling.DailyUserThrottle"],
    "DEFAULT_THROTTLE_RATES": {"user": "3/day"},
}


@override_settings(CACHES=TEST_CACHE, THROTTLE_EXEMPT_SUBS=ADMIN_SUB, REST_FRAMEWORK=TEST_REST_FRAMEWORK)
class DailyUserThrottleTests(APITestCase):
    """
    Tests for DailyUserThrottle.

    DAILY_RATELIMIT is set to 3 so tests hit the limit quickly without
    making hundreds of real requests.
    """

    def setUp(self):
        cache.clear()

    def _url(self):
        return reverse("prep_sessions")

    def _auth(self, sub):
        self.client.force_authenticate(user=Auth0User({"sub": sub, "email": f"{sub}@test.com"}))

    # ── Normal user — rate limit applies ─────────────────────────────────────

    def test_normal_user_allowed_within_limit(self):
        self._auth(NORMAL_SUB)
        for _ in range(3):
            response = self.client.get(self._url())
            self.assertNotEqual(response.status_code, 429)

    def test_normal_user_blocked_after_limit_exceeded(self):
        self._auth(NORMAL_SUB)
        for _ in range(3):
            self.client.get(self._url())

        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 429)

    def test_normal_user_429_response_contains_detail(self):
        self._auth(NORMAL_SUB)
        for _ in range(3):
            self.client.get(self._url())

        response = self.client.get(self._url())
        self.assertIn("detail", response.json())

    # ── Admin/exempt user — no rate limit ────────────────────────────────────

    def test_exempt_user_never_throttled(self):
        self._auth(ADMIN_SUB)
        # Make far more requests than the limit allows for normal users
        for _ in range(10):
            response = self.client.get(self._url())
            self.assertNotEqual(response.status_code, 429)

    def test_exempt_user_not_affected_by_normal_user_usage(self):
        # Normal user exhausts their quota
        self._auth(NORMAL_SUB)
        for _ in range(3):
            self.client.get(self._url())

        # Admin user should still be allowed through
        self._auth(ADMIN_SUB)
        response = self.client.get(self._url())
        self.assertNotEqual(response.status_code, 429)

    # ── Multiple exempt subs ──────────────────────────────────────────────────

    @override_settings(THROTTLE_EXEMPT_SUBS=f"{ADMIN_SUB},test|second-admin", REST_FRAMEWORK=TEST_REST_FRAMEWORK)
    def test_multiple_exempt_subs_both_bypass_throttle(self):
        for sub in [ADMIN_SUB, "test|second-admin"]:
            cache.clear()
            self._auth(sub)
            for _ in range(10):
                response = self.client.get(self._url())
                self.assertNotEqual(response.status_code, 429, msg=f"sub={sub} was throttled")

    # ── Edge cases ────────────────────────────────────────────────────────────

    @override_settings(THROTTLE_EXEMPT_SUBS="", REST_FRAMEWORK=TEST_REST_FRAMEWORK)
    def test_empty_exempt_list_applies_limit_to_all(self):
        self._auth(ADMIN_SUB)
        for _ in range(3):
            self.client.get(self._url())

        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 429)

    @override_settings(THROTTLE_EXEMPT_SUBS="  ,  , ", REST_FRAMEWORK=TEST_REST_FRAMEWORK)
    def test_whitespace_only_exempt_list_applies_limit_to_all(self):
        self._auth(ADMIN_SUB)
        for _ in range(3):
            self.client.get(self._url())

        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 429)

    def test_partial_sub_match_does_not_bypass_throttle(self):
        # Only the number part without the prefix should NOT match
        self._auth("normal-user")  # same suffix but different sub entirely
        for _ in range(3):
            self.client.get(self._url())

        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 429)
