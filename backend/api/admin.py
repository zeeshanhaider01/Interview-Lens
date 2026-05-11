from django.contrib import admin

from .models import (
    IntervieweeBaselineProfile,
    InterviewPrediction,
    PrepProfileSubmission,
    PrepSession,
    User,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    """Base class that makes every model fully read-only in the admin panel."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyInline(admin.TabularInline):
    """Base inline class that is fully read-only."""

    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class PrepProfileSubmissionInline(ReadOnlyInline):
    model = PrepProfileSubmission
    fields = ("role", "source", "source_url", "submitted_at")
    readonly_fields = ("role", "source", "source_url", "submitted_at")


@admin.register(User)
class UserAdmin(ReadOnlyAdmin):
    list_display = ("id", "email", "auth0_sub", "plan", "created_at")
    list_filter = ("plan",)
    search_fields = ("email", "auth0_sub")
    ordering = ("-created_at",)
    readonly_fields = ("id", "email", "auth0_sub", "plan", "created_at", "updated_at")


@admin.register(PrepSession)
class PrepSessionAdmin(ReadOnlyAdmin):
    list_display = ("prep_id", "user", "title", "company_name", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("prep_id", "title", "company_name", "user__email")
    ordering = ("-created_at",)
    readonly_fields = ("prep_id", "user", "title", "company_name", "status", "created_at", "updated_at")
    inlines = [PrepProfileSubmissionInline]


@admin.register(PrepProfileSubmission)
class PrepProfileSubmissionAdmin(ReadOnlyAdmin):
    list_display = ("id", "prep_session", "user", "role", "source", "submitted_at")
    list_filter = ("role", "source")
    search_fields = ("prep_session__prep_id", "user__email", "source_url")
    ordering = ("-submitted_at",)
    readonly_fields = (
        "prep_session", "user", "role", "source", "source_url",
        "extracted_sections", "normalized_text", "confidence_flags",
        "metadata", "submitted_at",
    )


@admin.register(InterviewPrediction)
class InterviewPredictionAdmin(ReadOnlyAdmin):
    list_display = ("fingerprint", "prep_session", "user", "status", "prompt_version", "last_success_at", "created_at")
    list_filter = ("status",)
    search_fields = ("fingerprint", "user__email", "prep_session__prep_id")
    ordering = ("-created_at",)
    readonly_fields = (
        "fingerprint", "prep_session", "user", "prompt_version", "regenerate_nonce",
        "status", "result_json", "error_text", "last_success_at",
        "created_at", "updated_at",
    )


@admin.register(IntervieweeBaselineProfile)
class IntervieweeBaselineProfileAdmin(ReadOnlyAdmin):
    list_display = ("id", "user", "source", "source_url", "created_at")
    list_filter = ("source",)
    search_fields = ("user__email", "source_url")
    ordering = ("-created_at",)
    readonly_fields = (
        "user", "source", "source_url", "extracted_sections",
        "normalized_text", "confidence_flags", "metadata",
        "created_at", "updated_at",
    )
