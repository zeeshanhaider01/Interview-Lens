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
