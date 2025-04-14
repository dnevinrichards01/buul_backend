from rest_framework.permissions import IsAuthenticated, AllowAny
from django.http import HttpResponseBadRequest, HttpResponse, JsonResponse
from rest_framework.views import APIView
from rest_framework.decorators import api_view
from .serializers import ConnectRobinhoodLoginSerializer
from django.db import transaction
from functools import partial
from .tasks import login_robinhood
from django.core.cache import cache
import json
from rest_framework.exceptions import ValidationError
from robin_stocks.models import Log

from accumate_backend.viewHelper import LogState, log, validate, \
    cached_task_logging_info


class ConnectRobinhoodView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # import pdb
        # breakpoint() 
        serializer = ConnectRobinhoodLoginSerializer(data=request.data)
        validation_error_response = validate(
            Log, serializer, self, 
            fields_to_correct=["username", "password", "sms", "prompt", "app", "by_sms"], 
            fields_to_fail=["non_field_errors"],
            rename_field=lambda x: "email" if x == "username" else x
        )
        if validation_error_response:
            return validation_error_response

        login_robinhood.apply_async(
            kwargs = {
                "uid": self.request.user.id,
                "username": serializer.validated_data["username"],
                "password": serializer.validated_data["password"],
                "mfa_code": serializer.validated_data.get("app", None),
                "device_approval": serializer.validated_data.get("prompt", None),
                "challenge_code": serializer.validated_data.get("sms", None)
            }
        )

        status = 200
        log(Log, self, status, LogState.SUCCESS)
        return JsonResponse(
            {
                "success": "recieved", 
                "error": None
            }, 
            status = status
        )
    
    def get(self, request, *args, **kwargs):
        user = self.request.user
        uid = user.id
        # import pdb 
        # breakpoint()
        challenge = cache.get(f"uid_{uid}_rh_challenge")
        if not challenge:
            status = 200
            log(Log, self, status, LogState.BACKGROUND_TASK_WAITING)
            return JsonResponse(
                {
                    "success": None,
                    "error": None
                }, 
                status = status
            )
        
        challenge_data = json.loads(challenge)
        if challenge_data["success"]:
            status = 200
            log(Log, self, status, LogState.SUCCESS)
            return JsonResponse(
                {
                    "success": challenge_data["success"],
                    "error": None
                }, 
                status = status
            )
        elif challenge_data["challenge_type"]:
            status = 200
            error_message = challenge_data["error"]
            log(Log, self, status, LogState.RH_MFA,
                errors = {"error": error_message})
            return JsonResponse(
                {
                    "success": None,
                    "error": {
                        "challenge_type": challenge_data["challenge_type"],
                        "error_message": error_message
                    }
                }, 
                status = status
            )
        elif challenge_data["error"]:
            status = 200
            error_message = challenge_data["error"]
            log(Log, self, status, LogState.BACKGROUND_TASK_ERR, 
                errors = {"error": error_message})
            return JsonResponse(
                {
                    "success": None,
                    "error": {
                        "challenge_type": challenge_data["challenge_type"],
                        "error_message": error_message
                    }
                }, 
                status = status
            )
        else:
            status = 400
            log(Log, self, status, LogState.BACKGROUND_TASK_MISFORMATTED)
            return JsonResponse(
                {
                    "success": None,
                    "error": {}
                }, 
                status = status
            )





