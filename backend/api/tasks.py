from celery import shared_task

from .models import User
from .prediction_service import execute_prediction_job


@shared_task
def run_prediction_task(
    *,
    user_identifier,
    db_user_id,
    interviewee,
    interviewer,
    prompt_version="",
    regenerate_nonce="",
):
    db_user = User.objects.get(id=db_user_id)
    payload, response_status = execute_prediction_job(
        user_identifier=user_identifier,
        db_user=db_user,
        interviewee=interviewee,
        interviewer=interviewer,
        prompt_version=prompt_version,
        regenerate_nonce=regenerate_nonce,
    )
    return {
        "response_status": response_status,
        "payload": payload,
    }
