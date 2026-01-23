from django.db import models


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
