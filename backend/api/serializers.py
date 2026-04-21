from rest_framework import serializers

class PersonProfileSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    education = serializers.CharField()
    experience = serializers.CharField()

class IntervieweeSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    email = serializers.EmailField()
    education = serializers.CharField()
    experience = serializers.CharField()

class PredictRequestSerializer(serializers.Serializer):
    """
    Adds optional prompt_version and regenerate_nonce fields:
      - prompt_version: bump this when you change the prompt wording (forces new result)
      - regenerate_nonce: client-provided nonce to force a fresh run (e.g., when user clicks "Regenerate")
    """
    interviewee = IntervieweeSerializer()
    interviewer = PersonProfileSerializer()
    prompt_version = serializers.CharField(max_length=40, required=False, allow_blank=True)
    regenerate_nonce = serializers.CharField(max_length=64, required=False, allow_blank=True)


class PrepSessionCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    company_name = serializers.CharField(max_length=200, required=False, allow_blank=True)


class PrepSessionUpdateSerializer(serializers.Serializer):
    STATUS_CHOICES = ("ACTIVE", "CLOSED")

    title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    company_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=STATUS_CHOICES, required=False)


class PrepProfileSubmissionSerializer(serializers.Serializer):
    ROLE_CHOICES = ("INTERVIEWEE", "INTERVIEWER")

    role = serializers.ChoiceField(choices=ROLE_CHOICES)
    source = serializers.ChoiceField(choices=("LINKEDIN",), default="LINKEDIN", required=False)
    source_url = serializers.URLField(required=False, allow_blank=True, max_length=500)
    extracted_sections = serializers.DictField(required=True)
    confidence_flags = serializers.DictField(required=False, default=dict)
    metadata = serializers.DictField(required=False, default=dict)

    def validate_extracted_sections(self, value):
        if not value:
            raise serializers.ValidationError("At least one extracted section is required.")

        allowed_sections = {
            "experience",
            "education",
            "certifications",
            "projects",
            "skills",
            "honors_awards",
        }

        for section_name in value.keys():
            if section_name not in allowed_sections:
                raise serializers.ValidationError(f"Unsupported section '{section_name}'.")

        return value


class IntervieweeBaselineProfileSerializer(serializers.Serializer):
    source = serializers.ChoiceField(choices=("LINKEDIN",), default="LINKEDIN", required=False)
    source_url = serializers.URLField(required=False, allow_blank=True, max_length=500)
    extracted_sections = serializers.DictField(required=True)
    confidence_flags = serializers.DictField(required=False, default=dict)
    metadata = serializers.DictField(required=False, default=dict)

    def validate_extracted_sections(self, value):
        if not value:
            raise serializers.ValidationError("At least one extracted section is required.")

        allowed_sections = {
            "experience",
            "education",
            "certifications",
            "projects",
            "skills",
            "honors_awards",
        }

        for section_name in value.keys():
            if section_name not in allowed_sections:
                raise serializers.ValidationError(f"Unsupported section '{section_name}'.")

        return value
