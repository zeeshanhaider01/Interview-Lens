
from django.urls import path
from .views import predict_questions

urlpatterns = [
    path("predict-questions/", predict_questions, name="predict_questions"),
]
