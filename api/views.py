# from django.contrib.auth.models import User
from .models import User, WaitlistEmail, PlaidUser, UserBrokerageInfo, PlaidItem, \
    UserInvestmentGraph, Log
from rest_framework.views import APIView
from .serializers.accumateAccountSerializers import WaitlistEmailSerializer, \
    UserBrokerageInfoSerializer, NamePasswordValidationSerializer, \
    VerificationCodeResponseSerializer, VerificationCodeRequestSerializer, SendEmailSerializer, \
    DeleteAccountVerifySerializer
from .serializers.accumateAccountSerializers import UserSerializer, \
    WaitlistEmailSerializer, GraphDataRequestSerializer
from .serializers.PlaidSerializers.itemSerializers import ItemPublicTokenExchangeRequestSerializer
from .serializers.PlaidSerializers.linkSerializers import \
    LinkTokenCreateRequestTransactionsSerializer, LinkTokenCreateRequestSerializer, \
    PlaidSessionFinishedSerializer
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication

from django.http import HttpResponseBadRequest, HttpResponse, JsonResponse
from rest_framework.exceptions import ValidationError
from django.core.cache import cache
import json
import phonenumbers
from api.yahooRapidApiClient import FPMUtils
from datetime import datetime
from celery import current_app, chain, chord
from functools import partial
from django.db import transaction
from .tasks.userTasks import plaid_item_public_tokens_exchange, \
    plaid_link_token_create, plaid_user_create, accumate_user_remove, \
    plaid_user_remove, send_verification_code, send_waitlist_email, send_forgot_email
from .tasks.graphTasks import refresh_stock_data_by_interval, get_graph_data
from robin_stocks.models import UserRobinhoodInfo

import time
from django.core.mail import send_mail
from django.urls import reverse
import secrets 

import bcrypt 


# helper methods

def createVerificationCode():
    digits = str(secrets.randbelow(1000000))
    return "0" * (6 - len(digits)) + digits

def cached_task_status(cached_string):
    cached_value = json.loads(cached_string)
    if cached_value["success"] is None and cached_value["error"] is not None:
        return 400
    else:
        return 200

def healthCheck(request):
    return JsonResponse({"success": "healthy"}, status=200)

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

# sign up flow

class CreateUserView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        # Use the serializer to validate input data
        serializer = UserSerializer(data=request.data)
        validation_error_response = validate(
            serializer, self, 
            fields_to_check=["email", "password", "phone_number", "full_name"], 
            edit_error_message=lambda x: "A " + x if x[:4] == "user" else x
        )
        if validation_error_response:
            return validation_error_response
        
        user = serializer.save()
        status = 200
        response = JsonResponse(
            {"success": "user registered", "error": None}, 
            status=status
        )
        log(self, status, True, response, user=user, args=serializer.validated_data)
        return response

class NamePasswordValidation(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = NamePasswordValidationSerializer(data=request.data)
        validation_error_respose = validate(
            serializer, self, fields_to_correct=["full_name", "password"], 
            fields_to_fail=["non_field_errors"]
        )
        if validation_error_respose:
            return validation_error_respose
        
        status = 200
        result = JsonResponse(
            {
                "success": "validated", 
                "error": None
            }, 
            status=status
        ) 
        log(self, status, True, result, args=serializer.validated_data)
        return result

class EmailPhoneSignUpValidation(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def put(self, request, *args, **kwargs):
        "Get verification code if the email matches an account"

        serializer = VerificationCodeRequestSerializer(data=request.data)
        validation_error_respose = validate(
            serializer, self, 
            fields_to_correct=[
                "verification_email", "verification_phone_number", "email", 
                "phone_number", "phone_number", "full_name", "brokerage", 
                "symbol", "password", "password2", "delete_account"
            ], 
            fields_to_fail=["field", "non_field_errors"]
        )
        if validation_error_respose:
            return validation_error_respose
        
        # this endpoint is only for email and phone_number validation
        if serializer.validated_data["field"] not in ["email", "phone_number"]:
            status = 400
            result = JsonResponse(
                {
                    "success": None,
                    "error": "The field parameter must be 'email' or 'phone_number'."
                }, 
                status = status
            )
            log(self, status, False, result, args=serializer.validated_data)
            return result
        
        # fail if a user already exists with this contact info
        user_exists = False
        field = serializer.validated_data['field']
        if field == "email":
            email = serializer.validated_data['email']
            phone_number = None
            try: 
                _ = User.objects.get(email=email)
                user_exists = True
            except Exception as e:
                user_exists = False
        elif field == "phone_number":
            email = None
            phone_number = serializer.validated_data['phone_number']
            try: 
                _ = User.objects.get(phone_number=phone_number)
                user_exists = True
            except Exception as e:
                user_exists = False
        if user_exists:
            status = 200
            error_message = f"This {field.replace("_", " ")} is already in use."
            result = JsonResponse(
                {
                    "success": None,
                    "error": {
                        "email": error_message if email else None,
                        "phone_number": error_message if phone_number else None
                    }
                    
                }, 
                status = status
            )
            log(self, status, False, result, args=serializer.validated_data)
            return result
        
        # can't yet do sms messages, accept phone without giving a verification code
        if field == "phone_number":
            status = 200
            result = JsonResponse(
                {
                    "success": "recieved",
                    "error": None
                }, 
                status = status
            )
            log(self, status, True, result, args=serializer.validated_data)
            return result

        # generate verification code
        field = serializer.validated_data['field']
        value = serializer.validated_data[field]
        code = createVerificationCode()
        while cache.get(f"validate_{field}_{code}"):
            code = createVerificationCode()
        # cache verification code
        cache.delete(f"validate_{field}_{code}")
        cache.set(
            f"validate_{field}_{code}",
            json.dumps({field: value}),
            timeout= 1800 if field == "brokerage" else 300 
        )
        # send verification message
        send_verification_code.apply_async(
            kwargs = {
                "useEmail": field == "email", 
                "sendTo": value,
                "code": code
            }
        )
        
        status = 200
        result = JsonResponse(
            {
                "success": "recieved",
                "error": None
            }, 
            status = status
        )
        log(self, status, True, result, args=serializer.validated_data)
        return result

    def post(self, request, *args, **kwargs):
        """Given the correct code, extend its lifespan if no password given, 
        and if given the password then update password"""
        serializer = VerificationCodeResponseSerializer(data=request.data)
        validation_error_respose = validate(
            serializer, self, 
            fields_to_correct=[
                "verification_email", "verification_phone_number", "email", 
                "phone_number", "phone_number", "full_name", "brokerage", 
                "symbol", "password", "delete_account", "code"
            ], 
            fields_to_fail=["field", "non_field_errors"]
        )
        if validation_error_respose:
            return validation_error_respose
        
        # this endpoint is only for email and phone_number validation
        if serializer.validated_data["field"] not in ["email", "phone_number"]:
            status = 400
            result = JsonResponse(
                {
                    "success": None,
                    "error": "The field parameter must be 'email' or 'phone_number'."
                }, 
                status = status
            )
            log(self, status, False, result, args=serializer.validated_data)
            return result
        
        # check if the code has been requested for that field, and if values match
        code = serializer.validated_data['code']
        field = serializer.validated_data['field']
        value = serializer.validated_data[field]
        cached_value = cache.get(f"validate_{field}_{code}")
        if cached_value is None:
            status = 200
            result = JsonResponse(
                {
                    "success": None,
                    "error": {
                        "code": "Code is invalid or expired"
                    }
                    
                },
                status=200
            )
            log(self, status, False, result, args=serializer.validated_data)
            return result
        loaded_value = json.loads(cached_value)
        if loaded_value[field] != value:
            status = 200
            result = JsonResponse(
                {
                    "success": None,
                    "error": {
                        "code": "Code is invalid or expired"
                    }
                },
                status=200
            )
            log(self, status, False, result, args=serializer.validated_data)
            return result
        
        cache.delete(f"validate_{field}_{code}")

        status = 200
        response = JsonResponse(
            {
                "success": "verification code valid",
                "error": None
            },
            status=200
        )
        log(self, status, True, result, args=serializer.validated_data)
        return response

class SetBrokerageInvestment(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # import pdb
        # breakpoint()
        serializer = UserBrokerageInfoSerializer(data=request.data)
        validation_error_respose = validate(
            serializer, self, fields_to_correct=["brokerage", "symbol"],
            fields_to_fail=["non_field_errors"]
        )
        if validation_error_respose:
            return validation_error_respose
        
        # save brokerage or investment preference
        uid = self.request.user.id
        try:
            userBrokerageInfo = UserBrokerageInfo.objects.get(user__id=uid)
            if "brokerage" in serializer.validated_data:
                userBrokerageInfo.brokerage = serializer.validated_data["brokerage"]
            if "symbol" in serializer.validated_data:
                userBrokerageInfo.symbol = serializer.validated_data["symbol"]
        except:
            if "brokerage" in serializer.validated_data:
                brokerage = serializer.validated_data["brokerage"]
            else:
                brokerage = None
            if "symbol" in serializer.validated_data:
                symbol = serializer.validated_data["symbol"]
            else: 
                symbol = None
            userBrokerageInfo = UserBrokerageInfo(
                user = User.objects.get(id=uid),
                brokerage = brokerage,
                symbol = symbol
            )
        userBrokerageInfo.save()

        status = 200
        response = JsonResponse(
            {
                "success": "recieved", 
                "error": None
            }, 
            status=201
        )
        log(self, status, True, response, args=serializer.validated_data)
        return response


# Plaid

class PlaidUserCreate(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # import pdb
        # breakpoint()
        
        user = self.request.user
        uid = user.id
        try:
            if PlaidUser.objects.filter(user__id=uid).count() != 0:
                raise Exception("Plaid user already exists for this account")
        except Exception as e:
            cache.delete(f"uid_{uid}_plaid_user_create")
            cache.set(
                f"uid_{uid}_plaid_user_create",
                json.dumps({"success": "created", "error": None}),
                timeout=120
            )
            status = 200
            response = JsonResponse(
                {
                    "success": "already exists",
                    "error": None
                }, 
                status=200
            )
            log(self, status, False, response, user=user)
            return response
    
        cache.delete(f"uid_{uid}_plaid_user_create")
        cache.set(
            f"uid_{uid}_plaid_user_create",
            json.dumps({"success": None, "error": None}),
            timeout=120
        )
        plaid_user_create.apply_async(kwargs={"uid": uid})
        status = 200
        response = JsonResponse(
            {
                "success": "recieved", 
                "error": None
            }, 
            status=200
        )
        log(self, status, True, response, user=user)
        return response
    
    def get(self, request, *args, **kwargs):
        user = self.request.user
        uid = user.id
        task_status = cache.get(f"uid_{uid}_plaid_user_create")
        if task_status:
            status = cached_task_status(task_status)
            response = JsonResponse(
                json.loads(task_status),
                status = status
            )
            log(self, status, status==200, response, user=user)
            return response
        else:
            status = 200
            response = JsonResponse(
                {
                    "success": None,
                    "error": "no cache value found"
                }, 
                status = status
            )
            log(self, status, False, response, user=user)
            return response

class PlaidLinkTokenCreate(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # import pdb
        # breakpoint()

        user = self.request.user

        try:
            PlaidUser.objects.get(user__id=user.id)
        except Exception:
            status = 400 
            response = JsonResponse(
                {
                    "success": None,
                    "error": "This user does not yet have a plaid user object"
                }, 
                status = status
            )
            log(self, status, False, response, user=user)
            return response

        data = {
            "user": {
                "phone_number": user.phone_number,
                "email_address": user.email
            },
            "client_name": "Accumate",
            "products": ["transactions"],
            "transactions": {
                "days_requested": 100
            },
            "webhook": "https://62ea-2601-646-8283-4f00-fd82-54cf-fd0a-2ca.ngrok-free.app" + "/api/plaid/itemwebhook/",
            "country_codes": ["US"],
            "language": "en",
            "enable_multi_item_link": True,
            "account_filters": {
                "depository": { "account_subtypes": ["checking", "savings"] },
                "credit": { "account_subtypes": ["credit card"] }
            }
        }
        serializer = LinkTokenCreateRequestSerializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            status = 400 
            response = JsonResponse(
                {
                    "success": None,
                    "error": json.dumps(e.detail)
                },
                status=400
            )
            log(self, status, False, response, user=user)
            return response
        # Access the validated data
        validated_data = serializer.validated_data
        uid = user.id
        validated_data['uid'] = uid

        cache.delete(f"uid_{uid}_plaid_link_token_create")
        cache.set(
            f"uid_{uid}_plaid_link_token_create",
            json.dumps({
                "success": None, 
                "error": None
            }),
            timeout=120
        )
        plaid_link_token_create.apply_async(kwargs=validated_data)
        status = 200
        response = JsonResponse(
            {
                "success": "recieved", 
                "error": None
            }, 
            status = status
        )
        log(self, status, True, response, user=user)
        return response
    
    def get(self, request, *args, **kwargs):
        user = self.request.user
        uid = user.id
        task_status = cache.get(f"uid_{uid}_plaid_link_token_create")
        if task_status:
            status = cached_task_status(task_status)
            response = JsonResponse(
                json.loads(task_status),
                status = status
            )
            log(self, status, True, response, user=user)
            return response
        else:
            status = 400
            response = JsonResponse(
                {
                    "success": None,
                    "error": "no cache value found"
                }, 
                status=400
            )
            log(self, status, False, response, user=user)
            return response

class PlaidItemWebhook(APIView):
    #make it so that it also takes webhooks for ITEM_REMOVED or needing update flow later
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = PlaidSessionFinishedSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            status = 400
            response = JsonResponse(
                {
                    "success": None,
                    "error": e.detail
                }, 
                status = status
            )
            log(self, status, False, response, user=user, args=dict(request.data))
            return 
        
        user = self.request.user
        uid = user.id
        link_token = serializer.validated_data["link_token"]
        cached_uid = cache.get(f"link_token_{link_token}_user")
        if cached_uid:
            uid = json.loads(cached_uid)["uid"]
            cache.delete(f"link_token_{link_token}_user")
        else:
            status = 400
            response = JsonResponse(
                {
                    "success": None,
                    "error": "corresponding link token and user are no longer cached"
                }, 
                status = 400
            )
            log(self, status, False, response, user=user, args=serializer.validated_data)
            return response

        cache.delete(f"uid_{uid}_plaid_item_public_token_exchange")
        cache.set(
            f"uid_{uid}_plaid_item_public_token_exchange",
            json.dumps({"success": None, "error": None}),
            timeout=120
        )
        plaid_item_public_tokens_exchange.apply_async(
            kwargs = {
                "uid": uid,
                "public_tokens": serializer.validated_data["public_tokens"]
            }
        )

        status = 200
        response = JsonResponse(
            {
                "success": None, 
                "error": None
            }, 
            status = status
        )
        log(self, status, True, response, user=user, args=serializer.validated_data)
        return response

    def get(self, request, *args, **kwargs):
        user = self.request.user
        uid = user.id
        cached_exchage_result = cache.get(f"uid_{uid}_plaid_item_public_token_exchange")
        if exchage_result:
            exchage_result = json.loads(cached_exchage_result)
            if not exchage_result["success"] and not exchage_result["error"]:
                cache.delete(f"uid_{uid}_plaid_item_public_token_exchange")
            
            status = cached_task_status(exchage_result)
            response = JsonResponse(
                exchage_result,
                status = status
            )
            log(self, status, status==200, response, user=user)
            return response
        else:
            status = 400
            response = JsonResponse(
                {
                    "success": None,
                    "error": "no cache value found"
                }, 
                status = status 
            )
            log(self, status, False, response, user=user)
            return response


# fetch account info

class GetUserInfo(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = self.request.user
        # brokerage, etf (symbol), full_name, email, phone_number
        try:
            userBrokerageInfo = UserBrokerageInfo.objects.get(user__id=user.id)
            brokerage, etf = userBrokerageInfo.brokerage, userBrokerageInfo.symbol
            if brokerage == "robinhood":
                brokerage_completed = UserRobinhoodInfo.objects.filter(user=user).exists()
            else:
                brokerage_completed = True
        except Exception as e:
            brokerage, etf, brokerage_completed = None, None, False
        
        status = 200
        response = JsonResponse(
            {
                "full_name": user.full_name,
                "email": user.email,
                "phone_number": user.phone_number,
                "brokerage": brokerage,
                "etf": etf,
                "brokerage_completed": brokerage_completed,
                "link_completed": PlaidItem.objects.filter(user=user).exists()
            }, 
            status = status
        )
        log(self, status, True, response, user=user)
        return response
     
class StockGraphData(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, *args, **kwargs):
        user = self.request.user
        uid = user.id
        get_graph_data.apply_async(args = [uid])
        cache.delete(f"uid_{uid}_get_investment_graph_data")
        cache.set(
            f"uid_{uid}_get_investment_graph_data",
            json.dumps({"success": None, "error": None}),
            timeout=120
        )
        status = 200
        response = JsonResponse(
            {
                "success": "recieved", 
                "error": None
            }, 
            status = status
        )
        log(self, status, True, response, user=user)
        return response
    
    def post(self, request, *args, **kwargs):
        # import pdb
        # breakpoint()
        serializer = GraphDataRequestSerializer(data=request.data)
        validation_error_response = validate(
            serializer, self, fields_to_correct=["start_date"], 
            fields_to_fail=["non_field_errors"]
        )
        if validation_error_response:
            return validation_error_response

        user = self.request.user
        uid = user.id
        start_date = serializer.validated_data["start_date"]
        task_status = cache.get(f"uid_{uid}_get_investment_graph_data")
        if task_status:
            status = cached_task_status(task_status)
            if status == 400:
                response = JsonResponse(
                    json.loads(task_status), 
                    status = status
                )
                log(self, status, False, response, user=user, args=serializer.validated_data)
                return response
            else:
                query = UserInvestmentGraph.objects.filter(
                    user__id=uid,
                    date__gte=FPMUtils.round_date_down(start_date, granularity="1min")
                ).order_by("date")
                data = []
                for item in query:
                    data.append({
                        "date": item.date.isoformat(),
                        "price": item.value
                    })
                # breakpoint()
                status = 200
                response = JsonResponse({"data": data}, status=status)
                log(self, status, True, response, user=user, args=serializer.validated_data)
                return response
        else:
            status = 200
            response = JsonResponse(
                {
                    "success": None, 
                    "error": "no cache value found"
                }, 
                status=status
            )
            log(self, status, False, response, user=user, args=serializer.validated_data)
            return response



# update info

class ResetPassword(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def put(self, request, *args, **kwargs):
        "Get verification code if the email matches an account"

        serializer = VerificationCodeRequestSerializer(data=request.data)
        validation_error_response = validate(
            serializer, self, 
            fields_to_correct = [
                "verification_email", "verification_phone_number", "email", 
                "phone_number", "phone_number", "full_name", "brokerage", 
                "symbol", "password", "password2", "delete_account"
            ], 
            fields_to_fail = ["field", "non_field_errors"]
        )
        if validation_error_response:
            return validation_error_response
        
        sanitized_data = serializer.validated_data.copy()
        sanitized_data.pop("password", None)
        
        if serializer.validated_data["field"] != "password":
            status = 400
            response = JsonResponse(
                {
                    "success": None,
                    "error": "The field parameter must be 'password'."
                }, 
                status = status
            )
            log(self, status, False, response, user=user, args=sanitized_data)
            return response
        
        # check if a user with that password exists
        user_exists = False
        user = None
        if 'verification_email' in serializer.validated_data:
            email = serializer.validated_data['verification_email']
            phone_number = None
            try: 
                user = User.objects.get(email=email)
                user_exists = True
            except Exception as e:
                user = None
                user_exists = False
        elif 'verification_phone_number' in serializer.validated_data:
            email = None
            phone_number = serializer.validated_data['verification_phone_number']
            try: 
                user = User.objects.get(phone_number=phone_number)
                user_exists = True
            except Exception as e:
                user = None
                user_exists = False
        if not user_exists:
            status = 200
            response = JsonResponse(
                {
                    "success": "recieved",
                    "error": None
                }, 
                status=status
            )
            log(self, status, False, response, user=user, args=sanitized_data)
            return response
        
        field = serializer.validated_data['field']
        salt = bcrypt.gensalt()
        value = bcrypt.hashpw(serializer.validated_data[field].encode('utf-8'), salt)
        value = value.decode()
        code = createVerificationCode()
        while cache.get(f"signed_out_uid_{user.id}_set_{field}_{code}"):
            code = createVerificationCode()

        cache.delete(f"signed_out_uid_{user.id}_set_{field}_{code}")
        cache.set(
            f"signed_out_uid_{user.id}_set_{field}_{code}",
            json.dumps({field: value}),
            timeout= 1800 if field == "brokerage" else 300 
        )

        send_verification_code.apply_async(
            kwargs = {
                "useEmail": bool(email), 
                "sendTo": email or phone_number,
                "code": code
            }
        )
        
        status = 200
        response = JsonResponse(
            {
                "success": "recieved",
                "error": None
            }, 
            status=status
        )
        log(self, status, True, response, user=user, args=sanitized_data)
        return response

    def post(self, request, *args, **kwargs):
        """Given the correct code, extend its lifespan if no password given, 
        and if given the password then update password"""
        serializer = VerificationCodeResponseSerializer(data=request.data)
        validation_error_respose = validate(
            serializer, self, 
            fields_to_correct=[
                "verification_email", "verification_phone_number", "email", 
                "phone_number", "phone_number", "full_name", "brokerage", 
                "symbol", "password", "delete_account", "code"
            ], 
            fields_to_fail=["field", "non_field_errors"]
        )
        if validation_error_respose:
            return validation_error_respose
        
        sanitized_data = serializer.validated_data.copy()
        sanitized_data.pop("password", None)
        
        if serializer.validated_data["field"]!= "password":
            status = 400
            response = JsonResponse(
                {
                    "success": None,
                    "error": "The field parameter must be 'password'."
                }, 
                status=400
            )
            log(self, status, False, response, user=user, args=sanitized_data)
            return response
        
        # check if a user with the given account info exists
        user_exists = False
        user = None
        if 'verification_email' in serializer.validated_data:
            email = serializer.validated_data['verification_email']
            phone_number = None
            try: 
                user = User.objects.get(email=email)
                user_exists = True
            except Exception as e:
                user = None
                user_exists = False
        elif 'verification_phone_number' in serializer.validated_data:
            email = None
            phone_number = serializer.validated_data['verification_phone_number']
            try: 
                user = User.objects.get(phone_number=phone_number)
                user_exists = True
            except Exception as e:
                user = None
                user_exists = False
        if not user_exists:
            status = 200
            response = JsonResponse(
                {
                    "success": None,
                    "error": {
                        "code": "This code is invalid or expired. Request a new one."
                    }
                },
                status=200
            )
            log(self, status, False, response, user=user, args=sanitized_data)
            return response
        
        # check if the code has been requested for that field, and if values match
        code = serializer.validated_data['code']
        field = serializer.validated_data['field']
        value = serializer.validated_data[field]
        cached_value = cache.get(f"signed_out_uid_{user.id}_set_{field}_{code}")
        if cached_value is None:
            status = 200
            response = JsonResponse(
                {
                    "success": None,
                    "error": {
                        "code": "This code is invalid or expired. Request a new one."
                    }
                },
                status=200
            )
            log(self, status, False, response, user=user, args=sanitized_data)
            return response
        loaded_value = json.loads(cached_value)
        curr_val = value.encode('utf-8')
        cached_val = loaded_value[field].encode('utf-8')
        if not bcrypt.checkpw(curr_val, cached_val):
            status = 200
            response = JsonResponse(
                {
                    "success": None,
                    "error": {
                        "code": "This code is invalid or expired. Request a new one."
                    }
                },
                status = status
            )
            log(self, status, False, response, user=user, args=sanitized_data)
            return response

        user.set_password(serializer.validated_data["password"])
        user.save()

        cache.delete(f"signed_out_uid_{user.id}_set_{field}_{code}")

        status = 200
        response = JsonResponse(
            {
                "success": "verification code valid",
                "error": None
            },
            status=200
        )
        log(self, status, True, response, user=user, args=sanitized_data)
        return response

class RequestVerificationCode(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, *args, **kwargs):
        "Get verification code if the email matches an account"
        user = request.user

        serializer = VerificationCodeRequestSerializer(data=request.data)
        validation_error_response = validate(
            serializer, self, 
            fields_to_correct = [
                "verification_email", "verification_phone_number", "email", 
                "phone_number", "phone_number", "full_name", "brokerage", 
                "symbol", "password", "password2", "delete_account"
            ], 
            fields_to_fail = ["field", "non_field_errors"]
        )
        if validation_error_response:
            return validation_error_response
        
        sanitized_data = serializer.validated_data.copy()
        sanitized_data.pop("password", None)
        
        # check if a user with that password exists
        user_exists = False
        if 'verification_email' in serializer.validated_data:
            verification_email = serializer.validated_data['verification_email']
            verification_phone_number = None
            try: 
                _ = User.objects.get(email=verification_email)
                user_exists = True
            except Exception as e:
                user_exists = False
        elif 'verification_phone_number' in serializer.validated_data:
            verification_email = None
            verification_phone_number = serializer.validated_data['verification_phone_number']
            try: 
                _ = User.objects.get(phone_number=verification_phone_number)
                user_exists = True
            except Exception as e:
                user_exists = False
        if not user_exists:
            status = 400
            response = JsonResponse(
                {
                    "success": None,
                    "error": "No user is associated with the information given"
                }, 
                status = status
            )
            log(self, status, False, response, user=user, args=sanitized_data)
            return response
        

        # check that this email / number aren't yet taken
        user_exists = False
        if 'email' in serializer.validated_data:
            email = serializer.validated_data['email']
            phone_number = None
            try: 
                _ = User.objects.get(email=email)
                user_exists = True
            except Exception as e:
                user_exists = False
            if user_exists:
                status = 200
                response = JsonResponse(
                    {
                        "success": None,
                        "error": {
                            "email": "This email is already in use."
                        }
                    }, 
                    status = status
                )
                log(self, status, False, response, user=user, args=sanitized_data)
                return response
        elif 'phone_number' in serializer.validated_data:
            email = None
            phone_number = serializer.validated_data['phone_number']
            try: 
                _ = User.objects.get(phone_number=phone_number)
                user_exists = True
            except Exception as e:
                user_exists = False
            if user_exists:
                status = 200
                response = JsonResponse(
                    {
                        "success": None,
                        "error": {
                            "phone_number": "This number is already in use."
                        }
                    }, 
                    status = status
                )
                log(self, status, False, response, user=user, args=sanitized_data)
                return response
        
        field = serializer.validated_data['field']
        value = serializer.validated_data[field]
        if field == "password":
            salt = bcrypt.gensalt()
            value = bcrypt.hashpw(value.encode('utf-8'), salt)
            value = value.decode()
        code = createVerificationCode()
        while cache.get(f"uid_{user.id}_set_{field}_{code}"):
            code = createVerificationCode()

        cache.delete(f"uid_{user.id}_set_{field}_{code}")
        cache.set(
            f"uid_{user.id}_set_{field}_{code}",
            json.dumps({field: value}),
            timeout= 1800 if field == "brokerage" else 300 
        )

        send_verification_code.apply_async(
            kwargs = {
                "useEmail": bool(verification_email), 
                "sendTo": verification_email or verification_phone_number,
                "code": code
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
        log(self, status, True, response, user=user, args=sanitized_data)
        return response

    def post(self, request, *args, **kwargs):
        """Given the correct code, extend its lifespan if no password given, 
        and if given the password then update password"""
        serializer = VerificationCodeResponseSerializer(data=request.data)
        validation_error_respose = validate(
            serializer, self, 
            fields_to_correct=[
                "verification_email", "verification_phone_number", "email", 
                "phone_number", "phone_number", "full_name", "brokerage", 
                "symbol", "password", "delete_account", "code"
            ], 
            fields_to_fail=["field", "non_field_errors"]
        )
        if validation_error_respose:
            return validation_error_respose
        
        sanitized_data = serializer.validated_data.copy()
        sanitized_data.pop("password", None)
        
        # check if the code has been requested for that field, and if values match
        code = serializer.validated_data['code']
        field = serializer.validated_data['field']
        value = serializer.validated_data[field]
        user = self.request.user
        cached_value = cache.get(f"uid_{user.id}_set_{field}_{code}")
        if cached_value is None:
            status = 200
            response = JsonResponse(
                {
                    "success": None,
                    "error": {
                        "code": "Code is invalid or expired"
                    }
                },
                status=200
            )
            log(self, status, False, response, user=user, args=sanitized_data)
            return response
        loaded_value = json.loads(cached_value)
        if field == "password":
            curr_val = value.encode('utf-8')
            cached_val = loaded_value[field].encode('utf-8')
            if not bcrypt.checkpw(curr_val, cached_val):
                status = 200
                response = JsonResponse(
                    {
                        "success": None,
                        "error": {
                            "code": "Code is invalid or expired"
                        }
                    },
                    status = status
                )
                log(self, status, False, response, user=user, args=sanitized_data)
                return response
        elif loaded_value[field] != value:
            status = 200
            response = JsonResponse(
                {
                    "success": None,
                    "error": {
                        "code": "Code is invalid or expired"
                    }
                },
                status = status
            )
            log(self, status, False, response, user=user, args=sanitized_data)
            return response
        
        cache.delete(f"uid_{user.id}_set_{field}_{code}")

        if field == "email":
            email = serializer.validated_data["email"]
            if User.objects.filter(email=email).exists():
                status = 200
                response = JsonResponse(
                    {
                        "success": None,
                        "error": {
                            "email": "This email is already being used by another account"
                        }
                        
                    },
                    status = status
                )
                log(self, status, False, response, user=user, args=sanitized_data)
                return response
            else:
                user.email = email
                user.save()
        elif field == "phone_number":
            phone_number = serializer.validated_data["phone_number"]
            if User.objects.filter(phone_number=phone_number).exists():
                status = 200
                response = JsonResponse(
                    {
                        "success": None,
                        "error": {
                            "phone_number": "This number is already being used by another account"
                        }
                    },
                    status = status
                )
                log(self, status, False, response, user=user, args=sanitized_data)
                return response
            else:
                user.phone_number = phone_number
                user.save()
        elif field == "full_name":
            user.full_name = serializer.validated_data["full_name"]
            user.save()
        elif field == "brokerage":
            try: 
                userBrokerageInfo = UserBrokerageInfo.objects.get(user=user)
                userBrokerageInfo.full_name = serializer.validated_data["brokerage"]
                userBrokerageInfo.save()
            except Exception as e:
                status = 200
                response = JsonResponse(
                    {
                        "success": None,
                        "error": "We could not find your brokerage and investment choice. Please contact Accumate."
                    },
                    status = status
                )
                log(self, status, False, response, user=user, args=sanitized_data)
                return response
        elif field == "symbol":
            try: 
                userBrokerageInfo = UserBrokerageInfo.objects.get(user=user)
                userBrokerageInfo.symbol = serializer.validated_data["symbol"]
                userBrokerageInfo.save()
            except Exception as e:
                status = 200
                response = JsonResponse(
                    {
                        "success": None,
                        "error": "We could not find your brokerage and investment choice. Please contact Accumate."
                    },
                    status = status
                )
                log(self, status, False, response, user=user, args=sanitized_data)
                return response
        elif field == "password":
            user.set_password(serializer.validated_data["password"])
            user.save()
        elif field == "delete_account":
            cache.delete(f"code_{code}_accumate_user_remove")
            cache.set(
                f"code_{code}_accumate_user_remove",
                json.dumps({"success": None, "error": None}),
                timeout=120
            )
            chain(
                plaid_user_remove.s(user.id, code),
                accumate_user_remove.si(user.id, code)
            ).apply_async()
        else:
            status = 200
            response = JsonResponse(
                {
                    "success": None,
                    "error": "The field parameter must be one of 'password', " + \
                            "'email', 'phone_number', 'full_name', 'brokerage', " + \
                            "or 'symbol'."
                },
                status=200
            )
            log(self, status, False, response, user=user, args=sanitized_data)
            return response

        status = 200
        response = JsonResponse(
            {
                "success": "verification code valid",
                "error": None
            },
            status = status
        )
        log(self, status, True, response, user=user, args=sanitized_data)
        return response

class SendEmail(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = SendEmailSerializer(data=request.data)
        validation_error_message = validate(serializer, self, fields_to_correct=["email"])
        if validation_error_message:
            return validation_error_message

        email = serializer.validated_data["email"]
        if not User.objects.filter(email=email).exists():
            send_forgot_email.apply_async(
                kwargs = {
                    "useEmail": True, 
                    "sendTo": serializer.validated_data["email"],
                }
            )
        status = 200
        response = JsonResponse(
            {
                "success": "email sent", 
                "error": None
            }, 
            status = status
        )
        log(self, status, True, response, args=serializer.validated_data)
        return response

class DeleteAccountVerify(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        serializer = DeleteAccountVerifySerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            code = serializer.validated_data["code"]
            cached_result = cache.get(f"code_{code}_accumate_user_remove")
            if cached_result:
                status = 200
                response = JsonResponse(
                    json.loads(cached_result),
                    status=200
                )
                log(self, status, True, response, args=serializer.validated_data)
                return response
            else:
                status = 400
                response = JsonResponse(
                    {
                        "success": None,
                        "error": "no cached value found for that code"
                    },
                    status=400
                )
                log(self, status, False, response, args=serializer.validated_data)
                return response
        except Exception as e:
            status = 400
            response = JsonResponse(
                {
                    "success": None,
                    "error": f"error: {str(e)}"
                },
                status=400
            )
            log(self, status, False, response, args=dict(request.data))
            return response


# etc

class AddToWaitlist(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    # send them a confirmation email along with this??
    def post(self, request, *args, **kwargs):
        # check if valid email
        serializer = WaitlistEmailSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            email = serializer.validated_data['email']
            if WaitlistEmail.objects.filter(email=email).exists():
                raise Exception("duplicate")
            serializer.save()

            send_waitlist_email.apply_async(kwargs={"sendTo": email})
            status = 200
            response = JsonResponse(
                {
                    "success": "email added"
                }, 
                status = status
            )
            log(self, status, True, response, args=serializer.validated_data)
            return response
        except Exception as e:
            status = 400
            response = JsonResponse(
                {
                    "error": e.args[0]
                }, 
                status = 400
            )
            log(self, status, False, response, args=dict(request.validated_data))
            return response

