# backend/api/views.py

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status, permissions
from .serializers import PredictRequestSerializer
from .openai_client import generate_questions, OpenAIError

@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def predict_questions(request):
    s = PredictRequestSerializer(data=request.data)
    if not s.is_valid():
        return Response({"detail": s.errors}, status=status.HTTP_400_BAD_REQUEST)

    interviewee = s.validated_data["interviewee"]
    interviewer = s.validated_data["interviewer"]

    try:
        result = generate_questions(interviewee, interviewer)
        return Response(result, status=200)
    except OpenAIError as e:
        return Response({"detail": str(e)}, status=502)  # Bad Gateway -> upstream error
    except Exception as e:
        return Response({"detail": f"Server error: {e}"}, status=500)




# from rest_framework.decorators import api_view, permission_classes
# from rest_framework.response import Response
# from rest_framework import status, permissions
# from .serializers import PredictRequestSerializer
# from .openai_client import generate_questions

# @api_view(["POST"])
# @permission_classes([permissions.IsAuthenticated])
# def predict_questions(request):
#     s = PredictRequestSerializer(data=request.data)
#     if not s.is_valid():
#         return Response({"detail": s.errors}, status=status.HTTP_400_BAD_REQUEST)
#     interviewee = s.validated_data["interviewee"]
#     interviewer = s.validated_data["interviewer"]
#     try:
#         result = generate_questions(interviewee, interviewer)
#     except Exception as e:
#         return Response({"detail": str(e)}, status=500)
#     return Response(result, status=200)
