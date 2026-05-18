from django.urls import path

from .views import (
    generate_prep_session_prediction,
    get_prep_prediction,
    get_prep_session_role_profile,
    interviewee_baseline_profile,
    predict_questions,
    prep_session_detail,
    prep_sessions,
    submit_prep_profile,
)

urlpatterns = [
    path("predict-questions/", predict_questions, name="predict_questions"),
    path("prep-sessions/", prep_sessions, name="prep_sessions"),
    path(
        "prep-sessions/<uuid:prep_id>/", prep_session_detail, name="prep_session_detail"
    ),
    path(
        "prep-sessions/<uuid:prep_id>/profiles",
        submit_prep_profile,
        name="submit_prep_profile",
    ),
    path(
        "prep-sessions/<uuid:prep_id>/profiles/<str:role>",
        get_prep_session_role_profile,
        name="get_prep_session_role_profile",
    ),
    path(
        "prep-sessions/<uuid:prep_id>/generate",
        generate_prep_session_prediction,
        name="generate_prep_session_prediction",
    ),
    path(
        "prep-sessions/<uuid:prep_id>/prediction",
        get_prep_prediction,
        name="get_prep_prediction",
    ),
    path(
        "profile-baseline/interviewee",
        interviewee_baseline_profile,
        name="interviewee_baseline_profile",
    ),
]
