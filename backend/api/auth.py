# backend/api/auth.py

import requests
from django.conf import settings
from rest_framework import authentication, exceptions
from jose import jwt


class Auth0User:
    """
    Lightweight user-like object so DRF treats requests as authenticated
    without creating a Django User in the DB.
    - Must expose .is_authenticated for permissions
    - Must expose .pk (and .id) for DRF throttling keys
    """
    def __init__(self, payload: dict):
        self.payload = payload
        self.username = payload.get("sub", "auth0-user")
        # DRF throttling uses request.user.pk; make it stable & unique per subject
        self.pk = self.username
        self.id = self.username  # some libs prefer .id

    @property
    def is_authenticated(self) -> bool:
        return True


class Auth0JWTAuthentication(authentication.BaseAuthentication):
    """
    Validates Auth0-issued access tokens (RS256) using the tenant JWKS.
    Expects: Authorization: Bearer <token>
    """
    _jwks_cache = None

    def authenticate(self, request):
        auth_header = authentication.get_authorization_header(request).decode("utf-8")
        if not auth_header or not auth_header.lower().startswith("bearer "):
            return None

        token = auth_header.split(" ", 1)[1].strip()

        # Config (fail fast if missing)
        domain = (settings.AUTH0_DOMAIN or "").strip()
        audience = (settings.AUTH0_API_AUDIENCE or "").strip()
        issuer = (settings.AUTH0_ISSUER or f"https://{domain}/").strip()
        if not domain:
            raise exceptions.AuthenticationFailed("Auth0 domain not configured")
        if not audience:
            raise exceptions.AuthenticationFailed("Auth0 API audience not configured")
        if not issuer.endswith("/"):
            issuer = issuer + "/"

        # Pick JWKS key
        try:
            unverified_header = jwt.get_unverified_header(token)
        except Exception:
            raise exceptions.AuthenticationFailed("Invalid token header")

        jwks = self._get_jwks(domain)
        rsa_key = {}
        for key in jwks.get("keys", []):
            if key.get("kid") == unverified_header.get("kid"):
                rsa_key = {
                    "kty": key["kty"], "kid": key["kid"], "use": key["use"],
                    "n": key["n"], "e": key["e"],
                }
                break
        if not rsa_key:
            raise exceptions.AuthenticationFailed("Appropriate key not found")

        # Verify token
        try:
            payload = jwt.decode(
                token,
                rsa_key,
                # specifying the algorithm is essential otherwise decode will use algorithm whatever mentioned in the token header which may allow hackers to use other algorithms.
                algorithms=["RS256"],
                audience=audience,
                # we are explicitly specifying the issuer
                issuer=issuer,
            )
        except Exception:
            raise exceptions.AuthenticationFailed("Token validation failed")

        # Return authenticated user-like object
        user = Auth0User(payload)
        return (user, payload)

    def _get_jwks(self, domain: str):
        if self._jwks_cache:
            return self._jwks_cache
        url = f"https://{domain}/.well-known/jwks.json"
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        self._jwks_cache = r.json()
        return self._jwks_cache
