# backend/api/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status, permissions
from django.conf import settings
from django.utils import timezone
from urllib.parse import urlencode
from .serializers import (
    IntervieweeBaselineProfileSerializer,
    PredictRequestSerializer,
    PrepProfileSubmissionSerializer,
    PrepSessionCreateSerializer,
    PrepSessionUpdateSerializer,
)
from .models import IntervieweeBaselineProfile, PrepProfileSubmission, PrepSession, User
from .prediction_service import (
    get_prediction_state,
    mark_prediction_enqueue_failed,
    reserve_prediction_job,
    run_prediction_pipeline,
)
from .tasks import run_prediction_task


def get_or_create_db_user(auth_user):
    payload = getattr(auth_user, "payload", None) or {}
    db_user, _ = User.objects.get_or_create(
        auth0_sub=str(auth_user.id),
        defaults={"email": payload.get("email") or None},
    )
    return db_user


def normalize_sections_to_text(extracted_sections):
    normalized_chunks = []
    for section_name, value in extracted_sections.items():
        if isinstance(value, list):
            values = [str(item).strip() for item in value if str(item).strip()]
            section_text = "\n".join(values)
        elif isinstance(value, str):
            section_text = value.strip()
        else:
            section_text = str(value).strip()

        if section_text:
            normalized_chunks.append(f"{section_name.upper()}:\n{section_text}")

    return "\n\n".join(normalized_chunks)


def stringify_section(value):
    if isinstance(value, list):
        return "\n".join(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return str(value).strip()


def build_predict_payload_from_prep_session(prep_session, user_email=None):
    profile_state = resolve_session_profile_state(prep_session, prep_session.user)
    if profile_state["pipeline_status"] != "READY_FOR_TOPIC_GENERATION":
        raise ValueError("Both required profiles are not available for prediction.")
    return build_predict_payload_from_profile_state(profile_state, user_email=user_email)


def build_prediction_response(payload, response_status):
    if response_status == status.HTTP_200_OK:
        return {
            "status": "COMPLETED",
            "result": payload,
        }

    response_body = {"status": payload.get("status", "UNKNOWN")}
    for key in ("fingerprint", "error", "last_good_fallback"):
        if key in payload:
            response_body[key] = payload[key]
    return response_body


def start_prediction_job(db_user, user_identifier, interviewee, interviewer, prompt_version="", regenerate_nonce=""):
    payload, response_status, fingerprint, should_enqueue = reserve_prediction_job(
        user_identifier=user_identifier,
        db_user=db_user,
        interviewee=interviewee,
        interviewer=interviewer,
        prompt_version=prompt_version,
        regenerate_nonce=regenerate_nonce,
    )
    if should_enqueue:
        try:
            run_prediction_task.delay(
                user_identifier=user_identifier,
                db_user_id=db_user.id,
                interviewee=interviewee,
                interviewer=interviewer,
                prompt_version=prompt_version,
                regenerate_nonce=regenerate_nonce,
            )
        except Exception as exc:
            mark_prediction_enqueue_failed(
                db_user,
                fingerprint,
                f"Queue error: {exc}",
            )
            return {"status": "FAILED", "error": f"Queue error: {exc}"}, status.HTTP_500_INTERNAL_SERVER_ERROR
    return payload, response_status


def build_dashboard_url(prep_session):
    base_url = (getattr(settings, "FRONTEND_DASHBOARD_URL", "") or "").rstrip("/")
    if not base_url:
        return ""
    query = urlencode({"prep_id": str(prep_session.prep_id)})
    return f"{base_url}/?{query}"


def build_submit_profile_user_message(pipeline_status, prediction):
    if pipeline_status == "WAITING_FOR_COUNTERPART_PROFILE":
        return (
            "Profile saved successfully. Add the counterpart profile to start generating your interview prep."
        )

    prediction_status = (prediction or {}).get("status")
    if prediction_status == "COMPLETED":
        return "Your interview prep is ready. Open the Interview Lens Dashboard to review it."

    if prediction_status == "FAILED":
        return (
            "We could not generate prep right now. Open the Interview Lens Dashboard for details and retry options."
        )

    return (
        "Great! We received both profiles and started generating your interview prep. "
        "Open the Interview Lens Dashboard to see progress and results."
    )


def build_submit_profile_next_action(pipeline_status):
    if pipeline_status == "WAITING_FOR_COUNTERPART_PROFILE":
        return "SUBMIT_COUNTERPART_PROFILE"
    return "OPEN_DASHBOARD"


def resolve_session_profile_state(prep_session, db_user):
    session_submissions = {
        submission.role: submission for submission in prep_session.profile_submissions.all()
    }
    session_interviewee_submission = session_submissions.get(PrepProfileSubmission.ROLE_INTERVIEWEE)
    interviewer_submission = session_submissions.get(PrepProfileSubmission.ROLE_INTERVIEWER)
    baseline_interviewee_profile = IntervieweeBaselineProfile.objects.filter(user=db_user).first()

    interviewee_source = "MISSING"
    if session_interviewee_submission:
        interviewee_source = "SESSION"
    elif baseline_interviewee_profile:
        interviewee_source = "DEFAULT"

    has_interviewee = interviewee_source != "MISSING"
    has_interviewer = interviewer_submission is not None
    pipeline_status = (
        "READY_FOR_TOPIC_GENERATION"
        if has_interviewee and has_interviewer
        else "WAITING_FOR_COUNTERPART_PROFILE"
    )

    return {
        "session_interviewee_submission": session_interviewee_submission,
        "baseline_interviewee_profile": baseline_interviewee_profile,
        "interviewer_submission": interviewer_submission,
        "has_interviewee_profile": has_interviewee,
        "has_interviewer_profile": has_interviewer,
        "has_default_interviewee_profile": baseline_interviewee_profile is not None,
        "interviewee_source": interviewee_source,
        "pipeline_status": pipeline_status,
    }


def build_predict_payload_from_profile_state(profile_state, user_email=None):
    interviewee_sections = {}
    if profile_state["interviewee_source"] == "SESSION":
        interviewee_sections = profile_state["session_interviewee_submission"].extracted_sections
    elif profile_state["interviewee_source"] == "DEFAULT":
        interviewee_sections = profile_state["baseline_interviewee_profile"].extracted_sections

    interviewer_sections = profile_state["interviewer_submission"].extracted_sections
    interviewee = {
        "name": "Interviewee",
        "email": user_email or "unknown@example.com",
        "education": stringify_section(interviewee_sections.get("education")) or "Not provided",
        "experience": normalize_sections_to_text(interviewee_sections) or "Not provided",
    }
    interviewer = {
        "name": "Interviewer",
        "education": stringify_section(interviewer_sections.get("education")) or "Not provided",
        "experience": normalize_sections_to_text(interviewer_sections) or "Not provided",
    }
    return interviewee, interviewer

@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def predict_questions(request):
    s = PredictRequestSerializer(data=request.data)
    if not s.is_valid():
        return Response({"detail": s.errors}, status=status.HTTP_400_BAD_REQUEST)

    interviewee = s.validated_data["interviewee"]
    interviewer = s.validated_data["interviewer"]
    prompt_version = s.validated_data.get("prompt_version", "") or ""
    regenerate_nonce = s.validated_data.get("regenerate_nonce", "") or ""
    db_user = get_or_create_db_user(request.user)
    if getattr(settings, "ENABLE_CACHING", True):
        payload, response_status = start_prediction_job(
            db_user,
            request.user.id,
            interviewee,
            interviewer,
            prompt_version,
            regenerate_nonce,
        )
    else:
        payload, response_status = run_prediction_pipeline(
            user_identifier=request.user.id,
            db_user=db_user,
            interviewee=interviewee,
            interviewer=interviewer,
            prompt_version=prompt_version,
            regenerate_nonce=regenerate_nonce,
        )
    return Response(payload, status=response_status)


def compute_prep_session_row(prep_session, db_user, user_identifier, *, is_latest=False):
    """
    One row for GET /prep-sessions/ — includes human-oriented row_status for the dashboard list.
    """
    profile_state = resolve_session_profile_state(prep_session, db_user)
    pipeline_status = profile_state["pipeline_status"]

    row = {
        "prep_id": str(prep_session.prep_id),
        "title": prep_session.title,
        "company_name": prep_session.company_name,
        "created_at": prep_session.created_at.isoformat(),
        "pipeline_status": pipeline_status,
        "interviewee_source": profile_state["interviewee_source"],
        "has_interviewee_profile": profile_state["has_interviewee_profile"],
        "has_interviewer_profile": profile_state["has_interviewer_profile"],
        "is_latest": is_latest,
    }

    if pipeline_status != "READY_FOR_TOPIC_GENERATION":
        row["row_status"] = "waiting_for_profiles"
        return row

    interviewee, interviewer = build_predict_payload_from_profile_state(
        profile_state,
        user_email=db_user.email,
    )
    payload, response_status, fingerprint = get_prediction_state(
        user_identifier=user_identifier,
        db_user=db_user,
        interviewee=interviewee,
        interviewer=interviewer,
    )
    prediction = (
        build_prediction_response(payload, response_status)
        if payload is not None
        else {"status": "NOT_STARTED", "fingerprint": fingerprint}
    )
    row["prediction_status"] = prediction.get("status")
    pred_status = prediction.get("status")
    if pred_status == "COMPLETED":
        row["row_status"] = "ready"
    elif pred_status == "FAILED":
        row["row_status"] = "failed"
    else:
        row["row_status"] = "generating"

    return row


def list_prep_sessions(request):
    db_user = get_or_create_db_user(request.user)
    sessions = PrepSession.objects.filter(user=db_user).order_by("-created_at")
    results = []
    for idx, prep_session in enumerate(sessions):
        results.append(
            compute_prep_session_row(
                prep_session,
                db_user,
                request.user.id,
                is_latest=(idx == 0),
            )
        )
    return Response({"results": results})


def get_owned_prep_session(db_user, prep_id):
    try:
        return PrepSession.objects.get(prep_id=prep_id, user=db_user)
    except PrepSession.DoesNotExist:
        return None


def build_prep_session_detail(prep_session, db_user, user_identifier):
    profile_state = resolve_session_profile_state(prep_session, db_user)
    pipeline_status = profile_state["pipeline_status"]

    if pipeline_status == "READY_FOR_TOPIC_GENERATION":
        interviewee, interviewer = build_predict_payload_from_profile_state(
            profile_state,
            user_email=db_user.email,
        )
        payload, response_status, fingerprint = get_prediction_state(
            user_identifier=user_identifier,
            db_user=db_user,
            interviewee=interviewee,
            interviewer=interviewer,
        )
        prediction = (
            build_prediction_response(payload, response_status)
            if payload is not None
            else {"status": "NOT_STARTED", "fingerprint": fingerprint}
        )
    else:
        prediction = {"status": "NOT_READY"}

    return {
        "prep_id": str(prep_session.prep_id),
        "status": prep_session.status,
        "title": prep_session.title,
        "company_name": prep_session.company_name,
        "created_at": prep_session.created_at.isoformat(),
        "updated_at": prep_session.updated_at.isoformat(),
        "pipeline_status": pipeline_status,
        "has_interviewee_profile": profile_state["has_interviewee_profile"],
        "has_interviewer_profile": profile_state["has_interviewer_profile"],
        "has_default_interviewee_profile": profile_state["has_default_interviewee_profile"],
        "interviewee_source": profile_state["interviewee_source"],
        "prediction": prediction,
    }


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def prep_sessions(request):
    if request.method == "GET":
        return list_prep_sessions(request)

    serializer = PrepSessionCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    db_user = get_or_create_db_user(request.user)
    prep_session = PrepSession.objects.create(
        user=db_user,
        title=serializer.validated_data.get("title") or None,
        company_name=serializer.validated_data.get("company_name") or None,
    )
    return Response(
        {
            "prep_id": str(prep_session.prep_id),
            "status": prep_session.status,
            "title": prep_session.title,
            "company_name": prep_session.company_name,
            "created_at": prep_session.created_at.isoformat(),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def prep_session_detail(request, prep_id):
    db_user = get_or_create_db_user(request.user)
    prep_session = get_owned_prep_session(db_user, prep_id)
    if prep_session is None:
        return Response({"detail": "Prep session not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(build_prep_session_detail(prep_session, db_user, request.user.id))

    if request.method == "PATCH":
        serializer = PrepSessionUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        if not serializer.validated_data:
            return Response(
                {"detail": "At least one of title, company_name, or status must be provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated_fields = []
        if "title" in serializer.validated_data:
            prep_session.title = serializer.validated_data["title"] or None
            updated_fields.append("title")
        if "company_name" in serializer.validated_data:
            prep_session.company_name = serializer.validated_data["company_name"] or None
            updated_fields.append("company_name")
        if "status" in serializer.validated_data:
            prep_session.status = serializer.validated_data["status"]
            updated_fields.append("status")

        if updated_fields:
            prep_session.save(update_fields=[*updated_fields, "updated_at"])

        return Response(build_prep_session_detail(prep_session, db_user, request.user.id))

    if prep_session.status != PrepSession.STATUS_CLOSED:
        prep_session.status = PrepSession.STATUS_CLOSED
        prep_session.save(update_fields=["status", "updated_at"])

    return Response(
        {
            "prep_id": str(prep_session.prep_id),
            "status": prep_session.status,
            "archived": True,
        }
    )


@api_view(["GET", "PUT"])
@permission_classes([permissions.IsAuthenticated])
def interviewee_baseline_profile(request):
    db_user = get_or_create_db_user(request.user)
    existing_profile = IntervieweeBaselineProfile.objects.filter(user=db_user).first()

    if request.method == "GET":
        if existing_profile is None:
            return Response({"exists": False, "profile": None})
        return Response(
            {
                "exists": True,
                "profile": {
                    "source": existing_profile.source,
                    "source_url": existing_profile.source_url,
                    "extracted_sections": existing_profile.extracted_sections,
                    "confidence_flags": existing_profile.confidence_flags,
                    "metadata": existing_profile.metadata,
                    "created_at": existing_profile.created_at.isoformat(),
                    "updated_at": existing_profile.updated_at.isoformat(),
                },
            }
        )

    serializer = IntervieweeBaselineProfileSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    extracted_sections = serializer.validated_data["extracted_sections"]
    normalized_text = normalize_sections_to_text(extracted_sections)
    profile, _ = IntervieweeBaselineProfile.objects.update_or_create(
        user=db_user,
        defaults={
            "source": serializer.validated_data.get("source", "LINKEDIN"),
            "source_url": serializer.validated_data.get("source_url") or None,
            "extracted_sections": extracted_sections,
            "normalized_text": normalized_text,
            "confidence_flags": serializer.validated_data.get("confidence_flags", {}),
            "metadata": serializer.validated_data.get("metadata", {}),
        },
    )
    return Response(
        {
            "exists": True,
            "profile": {
                "source": profile.source,
                "source_url": profile.source_url,
                "extracted_sections": profile.extracted_sections,
                "confidence_flags": profile.confidence_flags,
                "metadata": profile.metadata,
                "created_at": profile.created_at.isoformat(),
                "updated_at": profile.updated_at.isoformat(),
            },
        }
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def submit_prep_profile(request, prep_id):
    serializer = PrepProfileSubmissionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    db_user = get_or_create_db_user(request.user)
    try:
        prep_session = PrepSession.objects.get(prep_id=prep_id, user=db_user, status=PrepSession.STATUS_ACTIVE)
    except PrepSession.DoesNotExist:
        return Response({"detail": "Prep session not found or not active."}, status=status.HTTP_404_NOT_FOUND)

    extracted_sections = serializer.validated_data["extracted_sections"]
    normalized_text = normalize_sections_to_text(extracted_sections)

    submission, created = PrepProfileSubmission.objects.update_or_create(
        prep_session=prep_session,
        role=serializer.validated_data["role"],
        defaults={
            "user": db_user,
            "source": serializer.validated_data.get("source", "LINKEDIN"),
            "source_url": serializer.validated_data.get("source_url") or None,
            "extracted_sections": extracted_sections,
            "normalized_text": normalized_text,
            "confidence_flags": serializer.validated_data.get("confidence_flags", {}),
            "metadata": serializer.validated_data.get("metadata", {}),
            "submitted_at": timezone.now(),
        },
    )

    profile_state = resolve_session_profile_state(prep_session, db_user)
    pipeline_status = profile_state["pipeline_status"]

    prediction = None
    if pipeline_status == "READY_FOR_TOPIC_GENERATION":
        interviewee, interviewer = build_predict_payload_from_profile_state(
            profile_state,
            user_email=db_user.email,
        )
        if getattr(settings, "ENABLE_CACHING", True):
            prediction_payload, prediction_status = start_prediction_job(
                db_user,
                request.user.id,
                interviewee,
                interviewer,
            )
        else:
            prediction_payload, prediction_status = run_prediction_pipeline(
                user_identifier=request.user.id,
                db_user=db_user,
                interviewee=interviewee,
                interviewer=interviewer,
            )
        prediction = build_prediction_response(prediction_payload, prediction_status)

    return Response(
        {
            "submission_id": submission.id,
            "prep_id": str(prep_session.prep_id),
            "role": submission.role,
            "pipeline_status": pipeline_status,
            "interviewee_source": profile_state["interviewee_source"],
            "prediction": prediction,
            "user_message": build_submit_profile_user_message(pipeline_status, prediction),
            "next_action": build_submit_profile_next_action(pipeline_status),
            "dashboard_url": build_dashboard_url(prep_session),
            "submitted_at": submission.submitted_at.isoformat(),
        },
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_prep_prediction(request, prep_id):
    db_user = get_or_create_db_user(request.user)
    try:
        prep_session = PrepSession.objects.get(prep_id=prep_id, user=db_user)
    except PrepSession.DoesNotExist:
        return Response({"detail": "Prep session not found."}, status=status.HTTP_404_NOT_FOUND)

    profile_state = resolve_session_profile_state(prep_session, db_user)
    pipeline_status = profile_state["pipeline_status"]

    if pipeline_status != "READY_FOR_TOPIC_GENERATION":
        return Response(
            {
                "prep_id": str(prep_session.prep_id),
                "pipeline_status": pipeline_status,
                "has_interviewee_profile": profile_state["has_interviewee_profile"],
                "has_interviewer_profile": profile_state["has_interviewer_profile"],
                "interviewee_source": profile_state["interviewee_source"],
                "prediction": {"status": "NOT_READY"},
            },
            status=status.HTTP_200_OK,
        )

    interviewee, interviewer = build_predict_payload_from_profile_state(
        profile_state,
        user_email=db_user.email,
    )
    payload, response_status, fingerprint = get_prediction_state(
        user_identifier=request.user.id,
        db_user=db_user,
        interviewee=interviewee,
        interviewer=interviewer,
    )
    prediction = (
        build_prediction_response(payload, response_status)
        if payload is not None
        else {"status": "NOT_STARTED", "fingerprint": fingerprint}
    )
    return Response(
        {
            "prep_id": str(prep_session.prep_id),
            "pipeline_status": pipeline_status,
            "has_interviewee_profile": profile_state["has_interviewee_profile"],
            "has_interviewer_profile": profile_state["has_interviewer_profile"],
            "interviewee_source": profile_state["interviewee_source"],
            "prediction": prediction,
        },
        status=response_status or status.HTTP_200_OK,
    )
