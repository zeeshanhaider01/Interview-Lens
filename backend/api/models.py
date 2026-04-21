from django.db import models
import uuid


class User(models.Model):
    auth0_sub = models.CharField(max_length=255, unique=True, db_index=True)
    email = models.EmailField(unique=True, null=True, blank=True)

    PLAN_FREE = "FREE"
    PLAN_PREMIUM = "PREMIUM"

    PLAN_CHOICES = [
        (PLAN_FREE, "Free"),
        (PLAN_PREMIUM, "Premium"),
    ]
    plan = models.CharField(
        max_length=20,
        choices=PLAN_CHOICES,
        default=PLAN_FREE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.auth0_sub}({self.plan})"


class InterviewPrediction(models.Model):
    """
    Persistent model to store generated interview question results and state.
    This lets us:
      - Return cached results to users who revisit (durable storage)
      - Mark RUNNING / FAILED so UI can poll status
      - Provide a last_good_fallback if OpenAI fails
    """
    STATUS_RUNNING = "RUNNING"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_FAILED = "FAILED"

    STATUS_CHOICES = [
        (STATUS_RUNNING, "RUNNING"),
        (STATUS_COMPLETED, "COMPLETED"),
        (STATUS_FAILED, "FAILED"),
    ]

    fingerprint = models.CharField(max_length=128, unique=True, db_index=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    prompt_version = models.CharField(max_length=40, blank=True, null=True)
    regenerate_nonce = models.CharField(max_length=64, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    result_json = models.TextField(blank=True, null=True)  # JSON string of the response
    error_text = models.TextField(blank=True, null=True)
    last_success_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.fingerprint} ({self.status})"


class PrepSession(models.Model):
    """
    Represents one interview-preparation session for a user.
    The `prep_id` is shared with clients (frontend/extension).
    """

    STATUS_ACTIVE = "ACTIVE"
    STATUS_CLOSED = "CLOSED"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_CLOSED, "Closed"),
    ]

    prep_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="prep_sessions")
    title = models.CharField(max_length=200, blank=True, null=True)
    company_name = models.CharField(max_length=200, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.prep_id} ({self.status})"


class PrepProfileSubmission(models.Model):
    """
    Stores one profile snapshot submitted by the extension for a prep session.
    """

    ROLE_INTERVIEWEE = "INTERVIEWEE"
    ROLE_INTERVIEWER = "INTERVIEWER"
    ROLE_CHOICES = [
        (ROLE_INTERVIEWEE, "Interviewee"),
        (ROLE_INTERVIEWER, "Interviewer"),
    ]

    SOURCE_LINKEDIN = "LINKEDIN"
    SOURCE_CHOICES = [
        (SOURCE_LINKEDIN, "LinkedIn"),
    ]

    prep_session = models.ForeignKey(PrepSession, on_delete=models.CASCADE, related_name="profile_submissions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="profile_submissions")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_LINKEDIN)
    source_url = models.URLField(max_length=500, blank=True, null=True)
    extracted_sections = models.JSONField(default=dict)
    normalized_text = models.TextField(blank=True, default="")
    confidence_flags = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["prep_session", "role"],
                name="unique_prep_session_role_submission",
            )
        ]

    def __str__(self):
        return f"{self.prep_session.prep_id}::{self.role}"


class IntervieweeBaselineProfile(models.Model):
    """
    Stores the user's default interviewee profile for reuse across prep sessions.
    """

    SOURCE_LINKEDIN = "LINKEDIN"
    SOURCE_CHOICES = [
        (SOURCE_LINKEDIN, "LinkedIn"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="interviewee_baseline_profile")
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_LINKEDIN)
    source_url = models.URLField(max_length=500, blank=True, null=True)
    extracted_sections = models.JSONField(default=dict)
    normalized_text = models.TextField(blank=True, default="")
    confidence_flags = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.auth0_sub}::interviewee-baseline"
