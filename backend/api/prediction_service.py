import hashlib
import json

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .ai_client import (
    OUTPUT_MODE,
    PROMPT_VERSION,
    AIClientError,
    _normalize_interview_context,
    generate_questions,
)
from .models import InterviewPrediction
from .profile_trim import trim_predict_person
from .topic_service import replace_prediction_topics, topics_for_prediction


def _effective_prompt_version(prompt_version=""):
    explicit = str(prompt_version or "").strip()
    return explicit or PROMPT_VERSION


def compute_fingerprint(
    user_identifier,
    interviewee,
    interviewer,
    prompt_version="",
    regenerate_nonce="",
    interview_context=None,
):
    """
    Deterministic fingerprint of the request + prompt versioning inputs.
    """
    digest = hashlib.sha256()
    digest.update(str(user_identifier).encode("utf-8"))
    digest.update(b"||")
    digest.update(json.dumps(interviewee, sort_keys=True).encode("utf-8"))
    digest.update(b"||")
    digest.update(json.dumps(interviewer, sort_keys=True).encode("utf-8"))
    digest.update(b"||ctx:")
    digest.update(
        json.dumps(_normalize_interview_context(interview_context), sort_keys=True).encode("utf-8")
    )
    version = _effective_prompt_version(prompt_version)
    if version:
        digest.update(b"||v:")
        digest.update(version.encode("utf-8"))
    if regenerate_nonce:
        digest.update(b"||r:")
        digest.update(str(regenerate_nonce).encode("utf-8"))
    digest.update(b"||mode:")
    digest.update(OUTPUT_MODE.encode("utf-8"))
    return digest.hexdigest()


def _build_failed_payload(error_text, db_user):
    fallback = None
    last_good = (
        InterviewPrediction.objects.filter(
            user=db_user,
            status=InterviewPrediction.STATUS_COMPLETED,
        )
        .order_by("-last_success_at")
        .first()
    )
    if last_good and last_good.result_json:
        try:
            fallback = json.loads(last_good.result_json)
        except Exception:
            fallback = None

    return {
        "status": InterviewPrediction.STATUS_FAILED,
        "error": error_text or "Upstream error",
        "last_good_fallback": fallback,
    }


def _build_lock_key(fingerprint):
    return f"predict:lock:{fingerprint}"


def _build_result_key(fingerprint):
    return f"predict:result:{fingerprint}"


def get_prediction_state_by_fingerprint(db_user, fingerprint):
    result_key = _build_result_key(fingerprint)

    try:
        db_obj = InterviewPrediction.objects.get(fingerprint=fingerprint, user=db_user)
        if db_obj.status == InterviewPrediction.STATUS_COMPLETED and db_obj.result_json:
            try:
                return json.loads(db_obj.result_json), 200
            except Exception:
                pass

        if db_obj.status == InterviewPrediction.STATUS_FAILED:
            return _build_failed_payload(db_obj.error_text, db_user), 502

        if db_obj.status == InterviewPrediction.STATUS_RUNNING:
            return {"status": InterviewPrediction.STATUS_RUNNING, "fingerprint": fingerprint}, 202
    except InterviewPrediction.DoesNotExist:
        pass

    cached = cache.get(result_key)
    if cached:
        try:
            return json.loads(cached), 200
        except Exception:
            cache.delete(result_key)

    return None, None


def get_prediction_state(
    *,
    user_identifier,
    db_user,
    interviewee,
    interviewer,
    prompt_version="",
    regenerate_nonce="",
    interview_context=None,
):
    fingerprint = compute_fingerprint(
        user_identifier,
        interviewee,
        interviewer,
        prompt_version,
        regenerate_nonce,
        interview_context,
    )
    payload, response_status = get_prediction_state_by_fingerprint(db_user, fingerprint)
    return payload, response_status, fingerprint


def reserve_prediction_job(
    *,
    user_identifier,
    db_user,
    interviewee,
    interviewer,
    prompt_version="",
    regenerate_nonce="",
    prep_session=None,
    interview_context=None,
):
    fingerprint = compute_fingerprint(
        user_identifier,
        interviewee,
        interviewer,
        prompt_version,
        regenerate_nonce,
        interview_context,
    )
    payload, response_status = get_prediction_state_by_fingerprint(db_user, fingerprint)
    if payload is not None:
        return payload, response_status, fingerprint, False

    lock_ttl = getattr(settings, "CACHE_TTL_RUNNING", 300)
    lock_key = _build_lock_key(fingerprint)

    got_lock = cache.add(lock_key, "1", timeout=lock_ttl)
    if not got_lock:
        return {"status": InterviewPrediction.STATUS_RUNNING, "fingerprint": fingerprint}, 202, fingerprint, False

    try:
        InterviewPrediction.objects.get_or_create(
            fingerprint=fingerprint,
            defaults={
                "user": db_user,
                "prep_session": prep_session,
                "prompt_version": _effective_prompt_version(prompt_version) or None,
                "regenerate_nonce": regenerate_nonce or None,
                "status": InterviewPrediction.STATUS_RUNNING,
            },
        )
    except Exception:
        cache.delete(lock_key)
        return {"status": InterviewPrediction.STATUS_RUNNING, "fingerprint": fingerprint}, 202, fingerprint, False

    return {"status": InterviewPrediction.STATUS_RUNNING, "fingerprint": fingerprint}, 202, fingerprint, True


def mark_prediction_enqueue_failed(db_user, fingerprint, error_text):
    lock_key = _build_lock_key(fingerprint)
    try:
        db_obj = InterviewPrediction.objects.get(fingerprint=fingerprint, user=db_user)
        db_obj.status = InterviewPrediction.STATUS_FAILED
        db_obj.error_text = error_text
        db_obj.save(update_fields=["status", "error_text", "updated_at"])
    except InterviewPrediction.DoesNotExist:
        pass
    cache.delete(lock_key)


def run_prediction_pipeline(
    *,
    user_identifier,
    db_user,
    interviewee,
    interviewer,
    prompt_version="",
    regenerate_nonce="",
    interview_context=None,
):
    if not getattr(settings, "ENABLE_CACHING", True):
        try:
            return generate_questions(
                trim_predict_person(interviewee),
                trim_predict_person(interviewer),
                interview_context,
            ), 200
        except AIClientError as exc:
            return {"status": "FAILED", "error": str(exc)}, 502
        except Exception as exc:
            return {"status": "FAILED", "error": f"Server error: {exc}"}, 500

    return execute_prediction_job(
        user_identifier=user_identifier,
        db_user=db_user,
        interviewee=interviewee,
        interviewer=interviewer,
        prompt_version=prompt_version,
        regenerate_nonce=regenerate_nonce,
        interview_context=interview_context,
    )


def execute_prediction_job(
    *,
    user_identifier,
    db_user,
    interviewee,
    interviewer,
    prompt_version="",
    regenerate_nonce="",
    prep_session=None,
    interview_context=None,
):
    fingerprint = compute_fingerprint(
        user_identifier,
        interviewee,
        interviewer,
        prompt_version,
        regenerate_nonce,
        interview_context,
    )
    lock_key = _build_lock_key(fingerprint)
    result_key = _build_result_key(fingerprint)
    result_ttl = getattr(settings, "CACHE_TTL_RESULT", 86400)

    try:
        db_obj = InterviewPrediction.objects.get(fingerprint=fingerprint, user=db_user)
        if db_obj.status == InterviewPrediction.STATUS_COMPLETED and db_obj.result_json:
            try:
                return json.loads(db_obj.result_json), 200
            except Exception:
                pass
    except InterviewPrediction.DoesNotExist:
        db_obj = InterviewPrediction.objects.create(
            fingerprint=fingerprint,
            user=db_user,
            prep_session=prep_session,
            prompt_version=_effective_prompt_version(prompt_version) or None,
            regenerate_nonce=regenerate_nonce or None,
            status=InterviewPrediction.STATUS_RUNNING,
        )

    try:
        trimmed_interviewee = trim_predict_person(interviewee)
        trimmed_interviewer = trim_predict_person(interviewer)
        result = generate_questions(
            trimmed_interviewee,
            trimmed_interviewer,
            interview_context,
        )
        db_obj.result_json = json.dumps(result)
        db_obj.status = InterviewPrediction.STATUS_COMPLETED
        db_obj.error_text = ""
        db_obj.last_success_at = timezone.now()
        db_obj.save(
            update_fields=["result_json", "status", "error_text", "last_success_at", "updated_at"]
        )
        replace_prediction_topics(db_obj, result.get("topics") or [])

        try:
            cache.set(result_key, json.dumps(result), timeout=result_ttl)
        except Exception:
            pass

        cache.delete(lock_key)
        return result, 200
    except AIClientError as exc:
        db_obj.status = InterviewPrediction.STATUS_FAILED
        db_obj.error_text = str(exc)
        db_obj.save(update_fields=["status", "error_text", "updated_at"])
        cache.delete(lock_key)
        return _build_failed_payload(str(exc), db_user), 502
    except Exception as exc:
        db_obj.status = InterviewPrediction.STATUS_FAILED
        db_obj.error_text = f"Server error: {exc}"
        db_obj.save(update_fields=["status", "error_text", "updated_at"])
        cache.delete(lock_key)
        return {"status": "FAILED", "error": f"Server error: {exc}"}, 500


def enrich_completed_result(db_obj, payload):
    """Attach structured topics from DB to a completed prediction payload."""
    if not isinstance(payload, dict):
        return payload
    if db_obj is None:
        return payload
    enriched = dict(payload)
    if not enriched.get("topics"):
        enriched["topics"] = topics_for_prediction(db_obj)
    return enriched
