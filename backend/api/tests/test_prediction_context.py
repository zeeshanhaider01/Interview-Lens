from django.test import TestCase

from api.models import PrepSession, User
from api.prediction_service import compute_fingerprint
from api.views import build_interview_context, build_predict_payload_from_profile_state


class BuildInterviewContextTests(TestCase):
    def test_maps_prep_session_title_and_company(self):
        user = User.objects.create(auth0_sub="test|ctx", email="ctx@example.com")
        prep_session = PrepSession.objects.create(
            user=user,
            title="  Junior Backend Engineer  ",
            company_name=" Acme Corp ",
        )
        self.assertEqual(
            build_interview_context(prep_session),
            {
                "target_role": "Junior Backend Engineer",
                "target_company": "Acme Corp",
            },
        )

    def test_empty_prep_session_fields(self):
        user = User.objects.create(auth0_sub="test|ctx-empty", email="empty@example.com")
        prep_session = PrepSession.objects.create(user=user, title=None, company_name=None)
        self.assertEqual(
            build_interview_context(prep_session),
            {"target_role": "", "target_company": ""},
        )

    def test_missing_prep_session(self):
        self.assertEqual(
            build_interview_context(),
            {"target_role": "", "target_company": ""},
        )


class ComputeFingerprintContextTests(TestCase):
    def setUp(self):
        self.interviewee = {
            "name": "A",
            "email": "a@example.com",
            "education": "BS",
            "experience": "EXPERIENCE:\nPython",
        }
        self.interviewer = {
            "name": "B",
            "education": "MS",
            "experience": "EXPERIENCE:\nStaff Engineer",
        }

    def test_different_target_role_changes_fingerprint(self):
        base_kwargs = dict(
            user_identifier="user-1",
            interviewee=self.interviewee,
            interviewer=self.interviewer,
            prompt_version="5",
        )
        fp_junior = compute_fingerprint(
            **base_kwargs,
            interview_context={"target_role": "Junior Engineer", "target_company": "Acme"},
        )
        fp_staff = compute_fingerprint(
            **base_kwargs,
            interview_context={"target_role": "Staff Engineer", "target_company": "Acme"},
        )
        self.assertNotEqual(fp_junior, fp_staff)

    def test_different_target_company_changes_fingerprint(self):
        base_kwargs = dict(
            user_identifier="user-1",
            interviewee=self.interviewee,
            interviewer=self.interviewer,
            prompt_version="5",
        )
        fp_a = compute_fingerprint(
            **base_kwargs,
            interview_context={"target_role": "Backend Engineer", "target_company": "Acme"},
        )
        fp_b = compute_fingerprint(
            **base_kwargs,
            interview_context={"target_role": "Backend Engineer", "target_company": "OtherCo"},
        )
        self.assertNotEqual(fp_a, fp_b)


class BuildPredictPayloadContextTests(TestCase):
    def test_includes_interview_context_from_prep_session(self):
        from api.models import PrepProfileSubmission

        user = User.objects.create(auth0_sub="test|payload-ctx", email="payload@example.com")
        prep_session = PrepSession.objects.create(
            user=user,
            title="Data Engineer",
            company_name="FinPay",
        )
        PrepProfileSubmission.objects.create(
            prep_session=prep_session,
            user=user,
            role=PrepProfileSubmission.ROLE_INTERVIEWEE,
            extracted_sections={"experience": ["3 years ETL"], "education": ["BS CS"]},
            normalized_text="EXPERIENCE:\n3 years ETL",
        )
        PrepProfileSubmission.objects.create(
            prep_session=prep_session,
            user=user,
            role=PrepProfileSubmission.ROLE_INTERVIEWER,
            extracted_sections={"experience": ["Staff Engineer"], "education": ["MS"]},
            normalized_text="EXPERIENCE:\nStaff Engineer",
        )
        profile_state = {
            "session_interviewee_submission": prep_session.profile_submissions.get(
                role=PrepProfileSubmission.ROLE_INTERVIEWEE
            ),
            "baseline_interviewee_profile": None,
            "interviewer_submission": prep_session.profile_submissions.get(
                role=PrepProfileSubmission.ROLE_INTERVIEWER
            ),
            "interviewee_source": "SESSION",
            "pipeline_status": "READY_FOR_TOPIC_GENERATION",
        }
        _, _, interview_context = build_predict_payload_from_profile_state(
            profile_state,
            user_email=user.email,
            prep_session=prep_session,
        )
        self.assertEqual(
            interview_context,
            {"target_role": "Data Engineer", "target_company": "FinPay"},
        )
