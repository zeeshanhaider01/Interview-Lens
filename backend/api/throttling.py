from django.conf import settings
from rest_framework.settings import api_settings as drf_api_settings
from rest_framework.throttling import UserRateThrottle


class DailyUserThrottle(UserRateThrottle):
    """
    Standard per-user daily rate limit with an admin bypass.

    Any Auth0 subject (sub) listed in the THROTTLE_EXEMPT_SUBS environment
    variable is granted unlimited requests. All other authenticated users are
    subject to the DAILY_RATELIMIT quota.

    Set on EC2:
        THROTTLE_EXEMPT_SUBS=auth0|abc123,google-oauth2|xyz456
    """

    def get_rate(self):
        # Read lazily so @override_settings(REST_FRAMEWORK=...) works in tests.
        # DRF normally sets THROTTLE_RATES at class-definition time, which
        # makes the rate invisible to Django's test override mechanism.
        try:
            return drf_api_settings.DEFAULT_THROTTLE_RATES[self.scope]
        except KeyError:
            return super().get_rate()

    def allow_request(self, request, view):
        exempt_subs = {
            s.strip()
            for s in getattr(settings, "THROTTLE_EXEMPT_SUBS", "").split(",")
            if s.strip()
        }
        user_sub = str(getattr(request.user, "pk", ""))
        if user_sub and user_sub in exempt_subs:
            return True
        return super().allow_request(request, view)
