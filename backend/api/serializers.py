
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
    interviewee = IntervieweeSerializer()
    interviewer = PersonProfileSerializer()
