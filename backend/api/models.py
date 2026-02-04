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