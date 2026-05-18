# backend/api/views.py
from urllib.parse import urlencode

from django.conf import settings
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import (
    IntervieweeBaselineProfile,
    InterviewPrediction,
    PrepProfileSubmission,
    PrepSession,
    User,
)
from .prediction_service import (
    enrich_completed_result,
    get_prediction_state,
    mark_prediction_enqueue_failed,
    reserve_prediction_job,
    run_prediction_pipeline,
)
from .profile_trim import trim_predict_person
from .serializers import (
    IntervieweeBaselineProfileSerializer,
    PredictRequestSerializer,
    PrepProfileSubmissionSerializer,
    PrepSessionCreateSerializer,
    PrepSessionUpdateSerializer,
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


def build_interview_context(prep_session=None):
    if prep_session is None:
        return {"target_role": "", "target_company": ""}
    return {
        "target_role": str(prep_session.title or "").strip(),
        "target_company": str(prep_session.company_name or "").strip(),
    }


def build_predict_payload_from_prep_session(prep_session, user_email=None):
    profile_state = resolve_session_profile_state(prep_session, prep_session.user)
    if profile_state["pipeline_status"] != "READY_FOR_TOPIC_GENERATION":
        raise ValueError("Both required profiles are not available for prediction.")
    return build_predict_payload_from_profile_state(
        profile_state,
        user_email=user_email,
        prep_session=prep_session,
    )


def build_prediction_response(
    payload, response_status, *, db_user=None, fingerprint=None
):
    if response_status == status.HTTP_200_OK:
        result = payload
        if db_user and fingerprint:
            result = _enrich_result_with_topics(db_user, fingerprint, payload)
        return {
            "status": "COMPLETED",
            "result": result,
        }

    response_body = {"status": payload.get("status", "UNKNOWN")}
    for key in ("fingerprint", "error", "last_good_fallback"):
        if key in payload:
            response_body[key] = payload[key]
    return response_body


def _enrich_result_with_topics(db_user, fingerprint, payload):
    try:
        pred_obj = InterviewPrediction.objects.get(
            fingerprint=fingerprint, user=db_user
        )
    except InterviewPrediction.DoesNotExist:
        return payload
    return enrich_completed_result(pred_obj, payload)


def start_prediction_job(
    db_user,
    user_identifier,
    interviewee,
    interviewer,
    prompt_version="",
    regenerate_nonce="",
    prep_session=None,
    interview_context=None,
):
    if interview_context is None:
        interview_context = build_interview_context(prep_session)
    payload, response_status, fingerprint, should_enqueue = reserve_prediction_job(
        user_identifier=user_identifier,
        db_user=db_user,
        interviewee=interviewee,
        interviewer=interviewer,
        interview_context=interview_context,
        prompt_version=prompt_version,
        regenerate_nonce=regenerate_nonce,
        prep_session=prep_session,
    )
    if payload is not None and not should_enqueue:
        generation_source = (
            "cache" if response_status == status.HTTP_200_OK else "in_progress"
        )
        return payload, response_status, fingerprint, generation_source

    if should_enqueue:
        try:
            run_prediction_task.delay(
                user_identifier=user_identifier,
                db_user_id=db_user.id,
                interviewee=interviewee,
                interviewer=interviewer,
                interview_context=interview_context,
                prompt_version=prompt_version,
                regenerate_nonce=regenerate_nonce,
                prep_session_id=str(prep_session.prep_id) if prep_session else None,
            )
        except Exception as exc:
            mark_prediction_enqueue_failed(
                db_user,
                fingerprint,
                f"Queue error: {exc}",
            )
            return (
                {"status": "FAILED", "error": f"Queue error: {exc}"},
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                fingerprint,
                "failed",
            )
        return payload, response_status, fingerprint, "queued"

    return payload, response_status, fingerprint, "in_progress"


def build_dashboard_url(prep_session):
    base_url = (getattr(settings, "FRONTEND_DASHBOARD_URL", "") or "").rstrip("/")
    if not base_url:
        return ""
    query = urlencode({"prep_id": str(prep_session.prep_id)})
    return f"{base_url}/?{query}"


def _role_display_label(role):
    if role == PrepProfileSubmission.ROLE_INTERVIEWER:
        return "Interviewer"
    return "Interviewee"


def build_submit_profile_user_message(role, profile_state):
    role_label = _role_display_label(role)
    if profile_state["can_generate_prep"]:
        return (
            f"{role_label} profile saved for this session. "
            "Both profiles are on file — use Generate interview prep when you are ready."
        )

    missing_roles = []
    if not profile_state["has_session_interviewee_profile"]:
        missing_roles.append("interviewee")
    if not profile_state["has_session_interviewer_profile"]:
        missing_roles.append("interviewer")
    if missing_roles:
        return (
            f"{role_label} profile saved for this session. "
            f"Submit the {' and '.join(missing_roles)} profile for this session before generating."
        )
    return f"{role_label} profile saved for this session."


def build_submit_profile_next_action(profile_state):
    if profile_state["can_generate_prep"]:
        return "GENERATE_PREP"
    return "SUBMIT_COUNTERPART_PROFILE"


def build_generate_user_message(prediction, generation_source=None):
    prediction_status = (prediction or {}).get("status")
    if prediction_status == "COMPLETED":
        if generation_source == "cache":
            return (
                "Loaded your saved interview prep for the current profiles. "
                "Update a profile in the extension and generate again to refresh."
            )
        return "Your interview prep is ready. Open the Interview Lens Dashboard to review it."

    if prediction_status == "FAILED":
        return "We could not generate prep right now. Open the Interview Lens Dashboard for details and retry options."

    if generation_source == "in_progress":
        return (
            "Interview prep generation is already running for these profiles. "
            "Use Refresh results to check progress."
        )

    return (
        "Great! We received both profiles and started generating your interview prep. "
        "Open the Interview Lens Dashboard to see progress and results."
    )


def profile_state_response_fields(profile_state):
    return {
        "pipeline_status": profile_state["pipeline_status"],
        "has_interviewee_profile": profile_state["has_interviewee_profile"],
        "has_interviewer_profile": profile_state["has_interviewer_profile"],
        "has_session_interviewee_profile": profile_state[
            "has_session_interviewee_profile"
        ],
        "has_session_interviewer_profile": profile_state[
            "has_session_interviewer_profile"
        ],
        "can_generate_prep": profile_state["can_generate_prep"],
        "has_default_interviewee_profile": profile_state[
            "has_default_interviewee_profile"
        ],
        "interviewee_source": profile_state["interviewee_source"],
    }


def serialize_prep_profile_submission(submission):
    return {
        "role": submission.role,
        "source": submission.source,
        "source_url": submission.source_url or "",
        "extracted_sections": submission.extracted_sections,
        "confidence_flags": submission.confidence_flags,
        "metadata": submission.metadata,
        "profile_name": (submission.metadata or {}).get("profile_name", ""),
        "submitted_at": submission.submitted_at.isoformat(),
    }


def resolve_session_profile_state(prep_session, db_user):
    session_submissions = {
        submission.role: submission
        for submission in prep_session.profile_submissions.all()
    }
    session_interviewee_submission = session_submissions.get(
        PrepProfileSubmission.ROLE_INTERVIEWEE
    )
    interviewer_submission = session_submissions.get(
        PrepProfileSubmission.ROLE_INTERVIEWER
    )
    baseline_interviewee_profile = IntervieweeBaselineProfile.objects.filter(
        user=db_user
    ).first()

    interviewee_source = "MISSING"
    if session_interviewee_submission:
        interviewee_source = "SESSION"
    elif baseline_interviewee_profile:
        interviewee_source = "DEFAULT"

    has_session_interviewee = session_interviewee_submission is not None
    has_session_interviewer = interviewer_submission is not None
    has_interviewee = interviewee_source != "MISSING"
    has_interviewer = interviewer_submission is not None
    can_generate_prep = has_session_interviewee and has_session_interviewer
    pipeline_status = (
        "READY_FOR_TOPIC_GENERATION"
        if can_generate_prep
        else "WAITING_FOR_COUNTERPART_PROFILE"
    )

    return {
        "session_interviewee_submission": session_interviewee_submission,
        "baseline_interviewee_profile": baseline_interviewee_profile,
        "interviewer_submission": interviewer_submission,
        "has_interviewee_profile": has_interviewee,
        "has_interviewer_profile": has_interviewer,
        "has_session_interviewee_profile": has_session_interviewee,
        "has_session_interviewer_profile": has_session_interviewer,
        "can_generate_prep": can_generate_prep,
        "has_default_interviewee_profile": baseline_interviewee_profile is not None,
        "interviewee_source": interviewee_source,
        "pipeline_status": pipeline_status,
    }


def _profile_display_name(profile_record, fallback):
    if not profile_record:
        return fallback
    metadata = getattr(profile_record, "metadata", None) or {}
    name = str(metadata.get("profile_name") or "").strip()
    return name or fallback


def build_predict_payload_from_profile_state(
    profile_state, user_email=None, prep_session=None
):
    interviewee_sections = {}
    interviewee_record = None
    if profile_state["interviewee_source"] == "SESSION":
        interviewee_record = profile_state["session_interviewee_submission"]
        interviewee_sections = interviewee_record.extracted_sections
    elif profile_state["interviewee_source"] == "DEFAULT":
        interviewee_record = profile_state["baseline_interviewee_profile"]
        interviewee_sections = interviewee_record.extracted_sections

    interviewer_record = profile_state["interviewer_submission"]
    interviewer_sections = interviewer_record.extracted_sections
    interviewee = trim_predict_person(
        {
            "name": _profile_display_name(interviewee_record, "Interviewee"),
            "email": user_email or "unknown@example.com",
            "education": stringify_section(interviewee_sections.get("education"))
            or "Not provided",
            "experience": normalize_sections_to_text(interviewee_sections)
            or "Not provided",
        }
    )
    interviewer = trim_predict_person(
        {
            "name": _profile_display_name(interviewer_record, "Interviewer"),
            "education": stringify_section(interviewer_sections.get("education"))
            or "Not provided",
            "experience": normalize_sections_to_text(interviewer_sections)
            or "Not provided",
        }
    )
    interview_context = build_interview_context(prep_session)
    return interviewee, interviewer, interview_context


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
    interview_context = build_interview_context()
    db_user = get_or_create_db_user(request.user)
    if getattr(settings, "ENABLE_CACHING", True):
        payload, response_status, _fingerprint, _generation_source = (
            start_prediction_job(
                db_user,
                request.user.id,
                interviewee,
                interviewer,
                prompt_version,
                regenerate_nonce,
                interview_context=interview_context,
            )
        )
    else:
        payload, response_status = run_prediction_pipeline(
            user_identifier=request.user.id,
            db_user=db_user,
            interviewee=interviewee,
            interviewer=interviewer,
            interview_context=interview_context,
            prompt_version=prompt_version,
            regenerate_nonce=regenerate_nonce,
        )
    return Response(payload, status=response_status)


def compute_prep_session_row(
    prep_session, db_user, user_identifier, *, is_latest=False
):
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

    interviewee, interviewer, interview_context = (
        build_predict_payload_from_profile_state(
            profile_state,
            user_email=db_user.email,
            prep_session=prep_session,
        )
    )
    payload, response_status, fingerprint = get_prediction_state(
        user_identifier=user_identifier,
        db_user=db_user,
        interviewee=interviewee,
        interviewer=interviewer,
        interview_context=interview_context,
    )
    prediction = (
        build_prediction_response(
            payload,
            response_status,
            db_user=db_user,
            fingerprint=fingerprint,
        )
        if payload is not None
        else {"status": "NOT_STARTED", "fingerprint": fingerprint}
    )
    row["prediction_status"] = prediction.get("status")
    pred_status = prediction.get("status")
    if pred_status == "COMPLETED":
        row["row_status"] = "ready"
    elif pred_status == "FAILED":
        row["row_status"] = "failed"
    elif pred_status == "RUNNING":
        row["row_status"] = "generating"
    else:
        row["row_status"] = "ready_to_generate"

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
    fingerprint = None

    if pipeline_status == "READY_FOR_TOPIC_GENERATION":
        interviewee, interviewer, interview_context = (
            build_predict_payload_from_profile_state(
                profile_state,
                user_email=db_user.email,
                prep_session=prep_session,
            )
        )
        payload, response_status, fingerprint = get_prediction_state(
            user_identifier=user_identifier,
            db_user=db_user,
            interviewee=interviewee,
            interviewer=interviewer,
            interview_context=interview_context,
        )
        prediction = (
            build_prediction_response(
                payload,
                response_status,
                db_user=db_user,
                fingerprint=fingerprint,
            )
            if payload is not None
            else {"status": "NOT_STARTED", "fingerprint": fingerprint}
        )
        if prediction.get("status") == "COMPLETED" and fingerprint:
            pred_obj = (
                InterviewPrediction.objects.filter(
                    fingerprint=fingerprint, user=db_user
                )
                .values("last_success_at")
                .first()
            )
            if pred_obj and pred_obj["last_success_at"]:
                prediction = {
                    **prediction,
                    "last_success_at": pred_obj["last_success_at"].isoformat(),
                }
    else:
        prediction = {"status": "NOT_READY"}

    profile_submissions = [
        {
            "role": sub.role,
            "source_url": sub.source_url or "",
            "profile_name": (sub.metadata or {}).get("profile_name", ""),
            "submitted_at": sub.submitted_at.isoformat(),
        }
        for sub in prep_session.profile_submissions.order_by("submitted_at").all()
    ]

    response_body = {
        "prep_id": str(prep_session.prep_id),
        "status": prep_session.status,
        "title": prep_session.title,
        "company_name": prep_session.company_name,
        "created_at": prep_session.created_at.isoformat(),
        "updated_at": prep_session.updated_at.isoformat(),
        "prediction": prediction,
        "profile_submissions": profile_submissions,
        **profile_state_response_fields(profile_state),
    }
    return response_body


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def prep_sessions(request):
    if request.method == "GET":
        return list_prep_sessions(request)

    serializer = PrepSessionCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )

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
        return Response(
            {"detail": "Prep session not found."}, status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "GET":
        return Response(
            build_prep_session_detail(prep_session, db_user, request.user.id)
        )

    if request.method == "PATCH":
        serializer = PrepSessionUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(
                {"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
            )
        if not serializer.validated_data:
            return Response(
                {
                    "detail": "At least one of title, company_name, or status must be provided."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated_fields = []
        if "title" in serializer.validated_data:
            prep_session.title = serializer.validated_data["title"] or None
            updated_fields.append("title")
        if "company_name" in serializer.validated_data:
            prep_session.company_name = (
                serializer.validated_data["company_name"] or None
            )
            updated_fields.append("company_name")
        if "status" in serializer.validated_data:
            prep_session.status = serializer.validated_data["status"]
            updated_fields.append("status")

        if updated_fields:
            prep_session.save(update_fields=[*updated_fields, "updated_at"])

        return Response(
            build_prep_session_detail(prep_session, db_user, request.user.id)
        )

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
        return Response(
            {"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )

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
        return Response(
            {"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )

    db_user = get_or_create_db_user(request.user)
    try:
        prep_session = PrepSession.objects.get(
            prep_id=prep_id, user=db_user, status=PrepSession.STATUS_ACTIVE
        )
    except PrepSession.DoesNotExist:
        return Response(
            {"detail": "Prep session not found or not active."},
            status=status.HTTP_404_NOT_FOUND,
        )

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

    return Response(
        {
            "submission_id": submission.id,
            "prep_id": str(prep_session.prep_id),
            "role": submission.role,
            "prediction": None,
            "user_message": build_submit_profile_user_message(
                submission.role, profile_state
            ),
            "next_action": build_submit_profile_next_action(profile_state),
            "dashboard_url": build_dashboard_url(prep_session),
            "submitted_at": submission.submitted_at.isoformat(),
            **profile_state_response_fields(profile_state),
        },
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_prep_session_role_profile(request, prep_id, role):
    role_value = str(role or "").strip().upper()
    valid_roles = {
        PrepProfileSubmission.ROLE_INTERVIEWEE,
        PrepProfileSubmission.ROLE_INTERVIEWER,
    }
    if role_value not in valid_roles:
        return Response(
            {"detail": "Invalid role. Use INTERVIEWEE or INTERVIEWER."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    db_user = get_or_create_db_user(request.user)
    prep_session = get_owned_prep_session(db_user, prep_id)
    if prep_session is None:
        return Response(
            {"detail": "Prep session not found."}, status=status.HTTP_404_NOT_FOUND
        )

    profile_state = resolve_session_profile_state(prep_session, db_user)
    if role_value == PrepProfileSubmission.ROLE_INTERVIEWEE:
        submission = profile_state["session_interviewee_submission"]
    else:
        submission = profile_state["interviewer_submission"]

    if submission is None:
        return Response(
            {
                "prep_id": str(prep_session.prep_id),
                "role": role_value,
                "exists": False,
                "profile": None,
                **profile_state_response_fields(profile_state),
            }
        )

    return Response(
        {
            "prep_id": str(prep_session.prep_id),
            "role": role_value,
            "exists": True,
            "profile": serialize_prep_profile_submission(submission),
            **profile_state_response_fields(profile_state),
        }
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def generate_prep_session_prediction(request, prep_id):
    db_user = get_or_create_db_user(request.user)
    try:
        prep_session = PrepSession.objects.get(
            prep_id=prep_id, user=db_user, status=PrepSession.STATUS_ACTIVE
        )
    except PrepSession.DoesNotExist:
        return Response(
            {"detail": "Prep session not found or not active."},
            status=status.HTTP_404_NOT_FOUND,
        )

    profile_state = resolve_session_profile_state(prep_session, db_user)
    if not profile_state["can_generate_prep"]:
        return Response(
            {
                "detail": "Both interviewee and interviewer profiles must be saved on this session before generating.",
                **profile_state_response_fields(profile_state),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    interviewee, interviewer, interview_context = (
        build_predict_payload_from_profile_state(
            profile_state,
            user_email=db_user.email,
            prep_session=prep_session,
        )
    )
    payload_fp = None
    generation_source = "sync"
    if getattr(settings, "ENABLE_CACHING", True):
        prediction_payload, prediction_status, payload_fp, generation_source = (
            start_prediction_job(
                db_user,
                request.user.id,
                interviewee,
                interviewer,
                prep_session=prep_session,
                interview_context=interview_context,
            )
        )
    else:
        prediction_payload, prediction_status = run_prediction_pipeline(
            user_identifier=request.user.id,
            db_user=db_user,
            interviewee=interviewee,
            interviewer=interviewer,
            interview_context=interview_context,
        )
        _, _, payload_fp = get_prediction_state(
            user_identifier=request.user.id,
            db_user=db_user,
            interviewee=interviewee,
            interviewer=interviewer,
            interview_context=interview_context,
        )
        generation_source = (
            "cache" if prediction_status == status.HTTP_200_OK else "queued"
        )
    prediction = build_prediction_response(
        prediction_payload,
        prediction_status,
        db_user=db_user,
        fingerprint=payload_fp,
    )

    return Response(
        {
            "prep_id": str(prep_session.prep_id),
            "prediction": prediction,
            "generation_source": generation_source,
            "fingerprint": payload_fp,
            "user_message": build_generate_user_message(
                prediction, generation_source=generation_source
            ),
            "next_action": "OPEN_DASHBOARD",
            "dashboard_url": build_dashboard_url(prep_session),
            **profile_state_response_fields(profile_state),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_prep_prediction(request, prep_id):
    db_user = get_or_create_db_user(request.user)
    try:
        prep_session = PrepSession.objects.get(prep_id=prep_id, user=db_user)
    except PrepSession.DoesNotExist:
        return Response(
            {"detail": "Prep session not found."}, status=status.HTTP_404_NOT_FOUND
        )

    profile_state = resolve_session_profile_state(prep_session, db_user)
    pipeline_status = profile_state["pipeline_status"]

    if pipeline_status != "READY_FOR_TOPIC_GENERATION":
        return Response(
            {
                "prep_id": str(prep_session.prep_id),
                "prediction": {"status": "NOT_READY"},
                **profile_state_response_fields(profile_state),
            },
            status=status.HTTP_200_OK,
        )

    interviewee, interviewer, interview_context = (
        build_predict_payload_from_profile_state(
            profile_state,
            user_email=db_user.email,
            prep_session=prep_session,
        )
    )
    payload, response_status, fingerprint = get_prediction_state(
        user_identifier=request.user.id,
        db_user=db_user,
        interviewee=interviewee,
        interviewer=interviewer,
        interview_context=interview_context,
    )
    prediction = (
        build_prediction_response(
            payload,
            response_status,
            db_user=db_user,
            fingerprint=fingerprint,
        )
        if payload is not None
        else {"status": "NOT_STARTED", "fingerprint": fingerprint}
    )
    if prediction.get("status") == "COMPLETED":
        pred_obj = (
            InterviewPrediction.objects.filter(fingerprint=fingerprint, user=db_user)
            .values("last_success_at")
            .first()
        )
        if pred_obj and pred_obj["last_success_at"]:
            prediction = {
                **prediction,
                "last_success_at": pred_obj["last_success_at"].isoformat(),
            }

    return Response(
        {
            "prep_id": str(prep_session.prep_id),
            "prediction": prediction,
            **profile_state_response_fields(profile_state),
        },
        status=response_status or status.HTTP_200_OK,
    )
