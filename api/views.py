from django.contrib.auth.models import User
from .models import WaitlistEmail
from rest_framework import generics
from rest_framework.views import APIView
from .serializers.accumateAccountSerializers import UserSerializer, WaitlistEmailSerializer
from .serializers.PlaidSerializers.itemSerializers import ItemPublicTokenExchangeRequestSerializer
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.http import HttpResponseBadRequest, HttpResponse, JsonResponse
from django.core.exceptions import ValidationError
from django.core.cache import cache
import json

from celery import current_app
from functools import partial
from django.db import transaction
from .tasks import test_celery_task, plaid_item_public_token_exchange

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


class PlaidItemPublicTokenExchange(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        
        # Use the serializer to validate input data
        serializer = ItemPublicTokenExchangeRequestSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
        # Access the validated data
        validated_data = serializer.validated_data
        uid = self.request.user.id
        validated_data['uid'] = uid

        cache.delete(f"uid_{uid}_plaid_item_public_token_exchange")
        cache.set(
            f"uid_{uid}_plaid_item_public_token_exchange",
            json.dumps({"message": "pending", "error": None}),
            timeout=120
        )
        result = transaction.on_commit(
            partial(
                plaid_item_public_token_exchange.apply_async,
                kwargs=validated_data
            )
        )
        return JsonResponse({"success": "recieved"}, status=201)
    
    def get(self, request, *args, **kwargs):
        uid = self.request.user.id
        task_status = cache.get(f"uid_{uid}_plaid_item_public_token_exchange")
        if task_status:
            return JsonResponse(json.loads(task_status), status=201)
        else:
            return JsonResponse({"error": "no cache value found"}, status=400)


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