# backend/api/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status, permissions
from .serializers import PredictRequestSerializer
from .openai_client import generate_questions, OpenAIError
from .models import InterviewPrediction, User
from django.core.cache import cache
from django.utils import timezone
from django.conf import settings

import hashlib
import json

def compute_fingerprint(user_identifier, interviewee, interviewer, prompt_version="", regenerate_nonce=""):
    """
    Deterministic fingerprint of the request + prompt_version or regenerate_nonce.
    Changing prompt_version or regenerate_nonce will change the fingerprint and force a fresh run.
    """
    h = hashlib.sha256()
    # sort_keys=True ensures stable JSON ordering
    h.update(str(user_identifier).encode("utf-8"))
    h.update(b"||")
    h.update(json.dumps(interviewee, sort_keys=True).encode("utf-8"))
    h.update(b"||")
    h.update(json.dumps(interviewer, sort_keys=True).encode("utf-8"))
    if prompt_version:
        h.update(b"||v:")
        h.update(str(prompt_version).encode("utf-8"))
    if regenerate_nonce:
        h.update(b"||r:")
        h.update(str(regenerate_nonce).encode("utf-8"))
    return h.hexdigest()

@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def predict_questions(request):
    """
    Main endpoint to compute or fetch cached interview question results.

    Feature flag:
      - settings.ENABLE_CACHING (bool)
        If False: caching & locking logic is skipped; the view simply calls OpenAI and returns the result.
        This is useful in production for quick rollback: set ENABLE_CACHING=False to disable the caching system.

    Locking:
      - A Redis-backed lock is used via Django cache.add(lock_key, "1", timeout=LOCK_TTL)
      - cache.add is atomic in Redis; this prevents duplicate OpenAI calls.

    State:
      - Results are stored in DB (InterviewPrediction) for durable storage.
      - Results are also cached in Redis for fast reads.
    """
    s = PredictRequestSerializer(data=request.data)
    if not s.is_valid():
        return Response({"detail": s.errors}, status=status.HTTP_400_BAD_REQUEST)

    interviewee = s.validated_data["interviewee"]
    interviewer = s.validated_data["interviewer"]
    prompt_version = s.validated_data.get("prompt_version", "") or ""
    regenerate_nonce = s.validated_data.get("regenerate_nonce", "") or ""

    # Compute stable fingerprint (user id isolates cache/DB rows per account)
    fingerprint = compute_fingerprint(request.user.id, interviewee, interviewer, prompt_version, regenerate_nonce)
    lock_key = f"predict:lock:{fingerprint}"
    result_key = f"predict:result:{fingerprint}"

    # TTLs (configured in settings; fallback to sensible defaults)
    LOCK_TTL = getattr(settings, "CACHE_TTL_RUNNING", 300)  # seconds
    RESULT_TTL = getattr(settings, "CACHE_TTL_RESULT", 86400)  # seconds

    # If feature flag disabled, skip caching/locks entirely (simple fallback)
    if not getattr(settings, "ENABLE_CACHING", True):
        try:
            result = generate_questions(interviewee, interviewer)
            return Response(result, status=200)
        except OpenAIError as e:
            return Response({"status": "FAILED", "error": str(e)}, status=502)
        except Exception as e:
            return Response({"status": "FAILED", "error": f"Server error: {e}"}, status=500)

    # JWT auth exposes Auth0User; InterviewPrediction.user is api.User — resolve by auth0_sub.
    payload = getattr(request.user, "payload", None) or {}
    db_user, _ = User.objects.get_or_create(
        auth0_sub=str(request.user.id),
        defaults={"email": payload.get("email") or None},
    )

    # ---------- CACHING & LOCKING PATH ----------
    # 1) Check persistent DB first (authoritative), scoped to current user
    try:
        db_obj = InterviewPrediction.objects.get(fingerprint=fingerprint, user=db_user)
        if db_obj.status == InterviewPrediction.STATUS_COMPLETED and db_obj.result_json:
            try:
                return Response(json.loads(db_obj.result_json), status=200)
            except Exception:
                # corrupted stored JSON -> fall through to attempt regeneration
                pass

        if db_obj.status == InterviewPrediction.STATUS_FAILED:
            # Try to supply a last-good fallback if available
            fallback = None
            last_good = InterviewPrediction.objects.filter(user=db_user, status=InterviewPrediction.STATUS_COMPLETED).order_by("-last_success_at").first()
            if last_good and last_good.result_json:
                try:
                    fallback = json.loads(last_good.result_json)
                except Exception:
                    fallback = None
            return Response({
                "status": "FAILED",
                "error": db_obj.error_text or "Upstream error",
                "last_good_fallback": fallback
            }, status=502)

        if db_obj.status == InterviewPrediction.STATUS_RUNNING:
            # Another worker is already generating this fingerprint
            return Response({"status": "RUNNING", "fingerprint": fingerprint}, status=202)
    except InterviewPrediction.DoesNotExist:
        db_obj = None

    # 2) Fast path: read from Redis cache
    cached = cache.get(result_key)
    if cached:
        try:
            return Response(json.loads(cached), status=200)
        except Exception:
            # If cached value corrupted, delete and continue
            cache.delete(result_key)

    # 3) Attempt to acquire RUNNING lock (atomic)
    got_lock = cache.add(lock_key, "1", timeout=LOCK_TTL)
    if not got_lock:
        # Another process holds the lock; tell client to poll
        return Response({"status": "RUNNING", "fingerprint": fingerprint}, status=202)

    # 4) Create DB record with RUNNING status
    try:
        db_obj = InterviewPrediction.objects.create(
            fingerprint=fingerprint,
            user=db_user,
            prompt_version=prompt_version or None,
            regenerate_nonce=regenerate_nonce or None,
            status=InterviewPrediction.STATUS_RUNNING
        )
    except Exception:
        # DB write failed (e.g. race-created by another process); release lock and
        # tell client to poll — it will succeed on the next attempt.
        cache.delete(lock_key)
        return Response({"status": "RUNNING", "fingerprint": fingerprint}, status=202)

    # 5) Call OpenAI
    try:
        result = generate_questions(interviewee, interviewer)
        # Persist result to DB
        db_obj.result_json = json.dumps(result)
        db_obj.status = InterviewPrediction.STATUS_COMPLETED
        db_obj.error_text = ""
        db_obj.last_success_at = timezone.now()
        db_obj.save(update_fields=["result_json", "status", "error_text", "last_success_at", "updated_at"])

        # Cache for fast future access (best-effort)
        try:
            cache.set(result_key, json.dumps(result), timeout=RESULT_TTL)
        except Exception:
            # if caching fails, still return the result (do not crash)
            pass

        cache.delete(lock_key)  # release lock
        return Response(result, status=200)

    except OpenAIError as e:
        db_obj.status = InterviewPrediction.STATUS_FAILED
        db_obj.error_text = str(e)
        db_obj.save(update_fields=["status", "error_text", "updated_at"])
        cache.delete(lock_key)

        # optional: return the last successful fallback if exists (same user)
        last_good = InterviewPrediction.objects.filter(user=db_user, status=InterviewPrediction.STATUS_COMPLETED).order_by("-last_success_at").first()
        fallback = None
        if last_good and last_good.result_json:
            try:
                fallback = json.loads(last_good.result_json)
            except Exception:
                fallback = None

        return Response({
            "status": "FAILED",
            "error": str(e),
            "last_good_fallback": fallback
        }, status=502)

    except Exception as e:
        db_obj.status = InterviewPrediction.STATUS_FAILED
        db_obj.error_text = f"Server error: {e}"
        db_obj.save(update_fields=["status", "error_text", "updated_at"])
        cache.delete(lock_key)
        return Response({"status": "FAILED", "error": f"Server error: {e}"}, status=500)
