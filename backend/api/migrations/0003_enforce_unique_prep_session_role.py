from django.db import migrations, models


def deduplicate_prep_profile_submissions(apps, schema_editor):
    PrepProfileSubmission = apps.get_model("api", "PrepProfileSubmission")

    duplicate_groups = (
        PrepProfileSubmission.objects.values("prep_session_id", "role")
        .order_by()
        .annotate(row_count=models.Count("id"))
        .filter(row_count__gt=1)
    )

    for group in duplicate_groups.iterator():
        rows = list(
            PrepProfileSubmission.objects.filter(
                prep_session_id=group["prep_session_id"],
                role=group["role"],
            )
            .order_by("-submitted_at", "-id")
            .values_list("id", flat=True)
        )
        ids_to_delete = rows[1:]
        if ids_to_delete:
            PrepProfileSubmission.objects.filter(id__in=ids_to_delete).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0002_prepsession_prepprofilesubmission"),
    ]

    operations = [
        migrations.RunPython(
            deduplicate_prep_profile_submissions,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="prepprofilesubmission",
            constraint=models.UniqueConstraint(
                fields=("prep_session", "role"),
                name="unique_prep_session_role_submission",
            ),
        ),
    ]
