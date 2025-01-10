from django.contrib.auth.models import User
from .models import WaitlistEmail
from rest_framework import generics
from rest_framework.views import APIView
from .serializers.accumateAccountSerializers import UserSerializer, WaitlistEmailSerializer
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.http import HttpResponseBadRequest, HttpResponse, JsonResponse
from django.core.exceptions import ValidationError

from celery import current_app
from functools import partial
from django.db import transaction
from api.tasks import test_celery_task

import time

def healthCheck(request):
    return JsonResponse({"success": "healthy"}, status=200)

class CreateUserView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        # Use the serializer to validate input data
        serializer = UserSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            serializer.save() # error here indicates duplicate
            return JsonResponse({"success": "user registered"}, status=200)
        except Exception as e:
            return JsonResponse(e.args[0], status=400)


class AddToWaitlist(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        # check if valid email
        serializer = WaitlistEmailSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            email = serializer.validated_data['email']
            if WaitlistEmail.objects.filter(email=email).exists():
                raise Exception("duplicate")
            serializer.save()
            return JsonResponse({"success": "email added"}, status=200)
        except Exception as e:
            return JsonResponse({"error": e.args[0]}, status=400)


def test_celery_task_view(request):
    result = transaction.on_commit(
        partial(
            test_celery_task.apply_async,
            kwargs={}
        )
    )
    return JsonResponse({"success": "celery applied if this came though immediately"}, status=201)

def test_placebo_task_view(request):
    time.sleep(5)
    return JsonResponse({"success": "celery not applied"}, status=201)