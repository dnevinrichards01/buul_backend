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


def log(instance, status, success, response, user=None, args={}):
    log = Log(
        name = instance.__class__.__name__,
        user = user,
        response = response,
        success = success,
        args = args,
        status = status
    )
    log.save()

def validate(serializer, instance, fields_to_correct=[], fields_to_fail=[],
             edit_error_message=lambda x: x):
    try:
        serializer.is_valid(raise_exception=True)
    except ValidationError as e:
        # validation errors which we have no tolerance for
        for field in fields_to_fail:
            if field in e.detail and len(e.detail[field]) >= 1:
                status = 400
                result = JsonResponse(
                    {
                        "success": None,
                        "error": f"error '{field}': {e.detail[field][0]}"
                    }, 
                    status=400
                )
                return result
        # validation errors which we send error messages for
        error_messages = {}
        for field in fields_to_correct:
            if field in e.detail and len(e.detail[field]) >= 1:
                error_message = e.detail[field][0]
                error_messages[field] = edit_error_message(error_message)
            else:
                error_messages[field] = None
        status = 200
        result = JsonResponse(
            {
                "success": None, 
                "error": error_messages
            }, 
            status=status
        )
        log(instance, status, False, result, args=dict(instance.request.data))
        return result
    except Exception as e:
        # unknown error
        status = 400
        result = JsonResponse(
            {
                "success": None, 
                "error": str(e)
            }, 
            status=status
        )
        log(instance, status, False, result, args=dict(instance.request.data))
        return result


class ConnectRobinhoodView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # import pdb
        # breakpoint() 
        serializer = ConnectRobinhoodLoginSerializer(data=request.data)
        
        user = request.user
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            if "non_field_errors" in e.detail and len(e.detail["non_field_errors"]) > 0:
                status = 400
                response = JsonResponse(
                    {
                        "success": None, 
                        "error": e.detail["non_field_errors"][0]
                    }, 
                    status = status
                )
                sanitized_data = request.data.copy()
                sanitized_data.pop("username", None)
                sanitized_data.pop("password", None)
                log(self, status, False, response, user=user, args=sanitized_data)
                return response
            error_messages = {}
            for field in e.detail:
                if field in e.detail and len(e.detail[field]) > 0:
                    if field == "username":
                        error_messages["email"] = e.detail["username"][0]
                    else:
                        error_messages[field] = e.detail[field][0]
            status = 200
            response = JsonResponse(
                {
                    "success": None, 
                    "error": error_messages
                }, 
                status = status
            )
            sanitized_data = request.data.copy()
            sanitized_data.pop("username", None)
            sanitized_data.pop("password", None)
            log(self, status, False, response, user=user, args=sanitized_data)
            return response
        except Exception as e:
            status = 400
            response = JsonResponse(
                {
                    "success": None, 
                    "error": f"error: {str(e)}"
                }, 
                status = status
            )
            sanitized_data = request.data.copy()
            sanitized_data.pop("username", None)
            sanitized_data.pop("password", None)
            log(self, status, False, response, user=user, args=sanitized_data)
            return response
        
        validated_data = serializer.validated_data
        uid = self.request.user.id
        mfa_code = validated_data["app"] if "app" in validated_data else None
        challenge_code = validated_data["sms"] if "sms" in validated_data else None
        device_approval = validated_data["prompt"] if "prompt" in validated_data else None

        login_robinhood.apply_async(
            kwargs = {
                "uid": uid,
                "username": validated_data["username"],
                "password": validated_data["password"],
                "mfa_code": mfa_code,
                "device_approval": challenge_code,
                "challenge_code": device_approval
            }
        )

        status = 200
        response = JsonResponse(
            {
                "success": "recieved", 
                "error": None
            }, 
            status = status
        )
        sanitized_data = request.data.copy()
        sanitized_data.pop("username", None)
        sanitized_data.pop("password", None)
        log(self, status, True, response, user=user, args=sanitized_data)
        return response
    
    def get(self, request, *args, **kwargs):
        user = self.request.user
        uid = user.id
        # import pdb 
        # breakpoint()
        challenge = cache.get(f"uid_{uid}_rh_challenge")
        if not challenge:
            status = 200
            response = JsonResponse(
                {
                    "success": None,
                    "error": None
                }, 
                status = status
            )
            log(self, status, False, response, user=user)
            return response
        
        challenge_data = json.loads(challenge)
        if challenge_data["success"]:
            status = 200
            response = JsonResponse(
                {
                    "success": challenge_data["success"],
                    "error": None
                }, 
                status = status
            )
            log(self, status, True, response, user=user)
            return response
        elif challenge_data["challenge_type"]:
            status = 200
            response = JsonResponse(
                {
                    "success": None,
                    "error": {
                        "challenge_type": challenge_data["challenge_type"],
                        "error_message": challenge_data["error"]
                    }
                }, 
                status = status
            )
            log(self, status, False, response, user=user)
            return response
        else:
            status = 200
            response = JsonResponse(
                {
                    "success": None,
                    "error": {
                        "challenge_type": challenge_data["challenge_type"],
                        "error_message": challenge_data["error"]
                    }
                }, 
                status = status
            )
            log(self, status, False, response, user=user)
            return response