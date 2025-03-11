# from django.contrib.auth.models import User
from .models import User, WaitlistEmail, PlaidUser, UserBrokerageInfo, PlaidItem
from rest_framework.views import APIView
from .serializers.accumateAccountSerializers import WaitlistEmailSerializer, \
    UserBrokerageInfoSerializer, NamePasswordValidationSerializer, \
    VerificationCodeResponseSerializer, VerificationCodeRequestSerializer, SendEmailSerializer, \
    DeleteAccountVerifySerializer
from .serializers.accumateAccountSerializers import UserSerializer, WaitlistEmailSerializer
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

from celery import current_app, chain
from functools import partial
from django.db import transaction
from .tasks.userTasks import plaid_item_public_tokens_exchange, \
    plaid_link_token_create, plaid_user_create, accumate_user_remove, \
    plaid_user_remove, send_verification_code, send_waitlist_email, send_forgot_email
from .tasks.transactionsTasks import get_investment_graph_data
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
        return 201

def healthCheck(request):
    return JsonResponse({"success": "healthy"}, status=200)


# sign up flow

class CreateUserView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        # Use the serializer to validate input data

        serializer = UserSerializer(data=request.data)
        try:
            
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return JsonResponse(
                {"success": "user registered", "error": None}, 
                status=200
            )
        except ValidationError as e:
            error_messages = {}
            unfiltered_error_messages = e.detail
            for field in unfiltered_error_messages.keys():
                if field in ["email", "password", "phone_number", "full_name"]:
                    if len(unfiltered_error_messages[field]) >= 1:
                        error_message = unfiltered_error_messages[field][0]
                        if error_message[:4] == "user": #fix grammar for duplicates message
                            error_message = "A " + error_message
                        error_messages[field] = error_message
                    else:
                        error_messages[field] = None
            return JsonResponse(
                {
                    "success": None, 
                    "error": error_messages
                }, 
                status=200
            )
        except Exception as e:
            return JsonResponse(
                {
                    "success": None, 
                    "error": str(e)
                }, 
                status=400
            )

class NamePasswordValidation(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = NamePasswordValidationSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            return JsonResponse(
                {
                    "success": "validated", 
                    "error": None
                }, 
                status=200
            ) 
        except ValidationError as e:
            if "non_field_errors" in e.detail and len(e.detail["non_field_errors"]) >= 1:
                return JsonResponse(
                    {
                        "success": None, 
                        "error": e.detail["non_field_errors"][0]
                    }, 
                    status=400
                )
            error_messages = {}
            for field in e.detail.keys():
                if len(e.detail[field]) >= 1:
                    error_messages[field] = e.detail[field][0]
            return JsonResponse(
                {
                    "success": None, 
                    "error": error_messages
                }, 
                status=200
            )
        except Exception as e:
            return JsonResponse(
                {
                    "success": None, 
                    "error": f"error: {str(e)}"
                }, 
                status=400
            )

class EmailPhoneSignUpValidation(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def put(self, request, *args, **kwargs):
        "Get verification code if the email matches an account"

        serializer = VerificationCodeRequestSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            for field in ["field", "non_field_errors"]:
                if field in e.detail and len(e.detail[field]) >= 1:
                    return JsonResponse(
                        {
                            "success": None,
                            "error": f"error '{field}': {e.detail[field][0]}"
                        }, 
                        status=400
                    )
            for field in e.detail:
                error_messages = {}
                if len(e.detail[field]) >= 1:
                    error_messages[field] = e.detail[field][0]
            return JsonResponse(
                {
                    "success": None,
                    "error": error_messages
                }, 
                status=200
            )
        except Exception as e:
            return JsonResponse(
                {
                    "success": None,
                    "error": f"error: {str(e)}"
                }, 
                status=400
            )
        
        if serializer.validated_data["field"] not in ["email", "phone_number"]:
            return JsonResponse(
                {
                    "success": None,
                    "error": "The field parameter must be 'email' or 'phone_number'."
                }, 
                status=400
            )
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
            error_message = f"This {field.replace("_", " ")} is already in use."
            return JsonResponse(
                {
                    "success": None,
                    "error": {
                        "email": error_message if email else None,
                        "phone_number": error_message if phone_number else None
                    }
                    
                }, 
                status=200
            )
        
        if field == "phone_number":
            return JsonResponse(
                {
                    "success": "recieved",
                    "error": None
                }, 
                status=200
            )

        field = serializer.validated_data['field']
        value = serializer.validated_data[field]
        code = createVerificationCode()
        while cache.get(f"validate_{field}_{code}"):
            code = createVerificationCode()
        
        cache.delete(f"validate_{field}_{code}")
        cache.set(
            f"validate_{field}_{code}",
            json.dumps({field: value}),
            timeout= 1800 if field == "brokerage" else 300 
        )

        send_verification_code.apply_async(
            kwargs = {
                "useEmail": field == "email", 
                "sendTo": value,
                "code": code
            }
        )
        
        return JsonResponse(
            {
                "success": "recieved",
                "error": None
            }, 
            status=200
        )


    def post(self, request, *args, **kwargs):
        """Given the correct code, extend its lifespan if no password given, 
        and if given the password then update password"""
        serializer = VerificationCodeResponseSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            for field in ["field", "non_field_errors"]:
                if field in e.detail and len(e.detail[field]) >= 1:
                    return JsonResponse(
                        {
                            "success": None,
                            "error": e.detail[field][0]
                        }, 
                        status=400
                    )
            error_messages = {}
            for field in e.detail:
                if len(e.detail[field]) >= 1:
                    error_messages[field] = e.detail[field][0]
            return JsonResponse(
                {
                    "success": None,
                    "error": error_messages
                }, 
                status=200
            )
        except Exception as e:
            return JsonResponse(
                {
                    "success": None,
                    "error": f"error: {str(e)}"
                }, 
                status=400
            )
        
        if serializer.validated_data["field"] not in ["email", "phone_number"]:
            return JsonResponse(
                {
                    "success": None,
                    "error": "The field parameter must be 'email' or 'phone_number'."
                }, 
                status=400
            )
        
        # check if the code has been requested for that field, and if values match
        code = serializer.validated_data['code']
        field = serializer.validated_data['field']
        value = serializer.validated_data[field]
        cached_value = cache.get(f"validate_{field}_{code}")
        if cached_value is None:
            return JsonResponse(
                {
                    "success": None,
                    "error": {
                        "code": "Code is invalid or expired"
                    }
                    
                },
                status=200
            )
        loaded_value = json.loads(cached_value)
        if loaded_value[field] != value:
            return JsonResponse(
                {
                    "success": None,
                    "error": {
                        "code": "Code is invalid or expired"
                    }
                },
                status=200
            )
        
        cache.delete(f"validate_{field}_{code}")

        return JsonResponse(
            {
                "success": "verification code valid",
                "error": None
            },
            status=200
        )

class SetBrokerageInvestment(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # import pdb
        # breakpoint()
        
        uid = self.request.user.id

        serializer = UserBrokerageInfoSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            if "non_field_errors" in e.detail and len(e.detail["non_field_errors"]) >= 1:
                return JsonResponse(
                    {
                        "success": None, 
                        "error": e.detail["non_field_errors"][0]
                    }, 
                    status=400
                )
            error_messages = {}
            for field in e.detail.keys():
                if len(e.detail[field]) >= 1:
                    error_messages[field] = e.detail[field][0]
            return JsonResponse(
                {
                    "success": None, 
                    "error": error_messages
                }, 
                status=200
            )
        except Exception as e:
            return JsonResponse(
                {
                    "success": None, 
                    "error": f"error: {str(e)}"
                }, 
                status=400
            )
        
        try :
            userBrokerageInfo = UserBrokerageInfo.objects.get(user__id=uid)
            if "brokerage" in serializer.validated_data:
                userBrokerageInfo.brokerage = serializer.validated_data["brokerage"]
            if "symbol" in serializer.validated_data:
                userBrokerageInfo.symbol = serializer.validated_data["symbol"]
        except:
            if "brokerage" in serializer.validated_data:
                brokerage = serializer.validated_data["brokerage"]
                symbol = None
            if "symbol" in serializer.validated_data:
                brokerage = None
                symbol = serializer.validated_data["symbol"]
            userBrokerageInfo = UserBrokerageInfo(
                user = User.objects.get(id=uid),
                brokerage = brokerage,
                symbol = symbol
            )
        userBrokerageInfo.save()

        return JsonResponse(
            {
                "success": "recieved", 
                "error": None
            }, 
            status=201
        )



# Plaid

class PlaidUserCreate(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # import pdb
        # breakpoint()
        
        uid = self.request.user.id

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
            return JsonResponse(
                {
                    "success": "already exists",
                    "error": None
                }, 
                status=200
            )
    
        cache.delete(f"uid_{uid}_plaid_user_create")
        cache.set(
            f"uid_{uid}_plaid_user_create",
            json.dumps({"success": None, "error": None}),
            timeout=120
        )
        plaid_user_create.apply_async(kwargs={"uid": uid})
        return JsonResponse({"success": "recieved", "error": None}, status=201)
    
    def get(self, request, *args, **kwargs):
        uid = self.request.user.id
        task_status = cache.get(f"uid_{uid}_plaid_user_create")
        if task_status:
            return JsonResponse(
                json.loads(task_status),
                status=cached_task_status(task_status)
            )
        else:
            return JsonResponse(
                {
                    "success": None,
                    "error": "no cache value found"
                }, 
                status=200
            )

class PlaidLinkTokenCreate(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # import pdb
        # breakpoint()
        # Use the serializer to validate input data
        # data = request.data.copy()

        user = self.request.user

        try:
            PlaidUser.objects.get(user__id=user.id)
        except Exception:
            return JsonResponse(
                {
                    "success": None,
                    "error": "This user does not yet have a plaid user object"
                }, 
                status = 400
            )

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
            return JsonResponse(
                {
                    "success": None,
                    "error": json.dumps(e.detail)
                },
                status=400
            )
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
        return JsonResponse(
            {
                "success": "recieved", 
                "error": None
            }, 
            status=201
        )
    
    def get(self, request, *args, **kwargs):
        uid = self.request.user.id
        task_status = cache.get(f"uid_{uid}_plaid_link_token_create")
        if task_status:
            return JsonResponse(
                json.loads(task_status),
                status=cached_task_status(task_status)
            )
        else:
            error_message = "no cache value found"
            return JsonResponse(
                {
                    "success": None,
                    "error": error_message
                }, 
                status=400
            )

class PlaidItemWebhook(APIView):
    #make it so that it also takes webhooks for ITEM_REMOVED or needing update flow later
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = PlaidSessionFinishedSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            cache.set("temp_val_err", dict(request.data))
            return JsonResponse(
                {
                    "success": None,
                    "error": e.detail
                }, 
                status = 400
            )
        
        link_token = serializer.validated_data["link_token"]
        cached_uid = cache.get(f"link_token_{link_token}_user")
        if cached_uid:
            uid = json.loads(cached_uid)["uid"]
            cache.delete(f"link_token_{link_token}_user")
        else:
            cache.set("no_cache", "no_cache")
            return JsonResponse(
                {
                    "success": None,
                    "error": "corresponding link token and user are no longer cached"
                }, 
                status = 400
            )

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
        return JsonResponse({"success": None, "error": None}, status=201)

    def get(self, request, *args, **kwargs):
        uid = self.request.user.id
        exchage_result = cache.get(f"uid_{uid}_plaid_item_public_token_exchange")
        if exchage_result:
            loaded_exchage_result = json.loads(exchage_result)
            if not loaded_exchage_result["success"] and not loaded_exchage_result["error"]:
                cache.delete(f"uid_{uid}_plaid_item_public_token_exchange")
            return JsonResponse(
                loaded_exchage_result,
                status=cached_task_status(exchage_result)
            )
        else:
            return JsonResponse(
                {
                    "success": None,
                    "error": "no cache value found"
                }, 
                status=400
            )


# fetch account info

class GetUserInfo(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = self.request.user
        # brokerage, etf (symbol), full_name, email, phone_number
        try:
            userBrokerageInfo = UserBrokerageInfo.objects.get(user__id=user.id)
            brokerage, etf = userBrokerageInfo.brokerage, userBrokerageInfo.symbol
        except Exception as e:
            brokerage, etf = None, None

        return JsonResponse(
            {
                "full_name": user.full_name,
                "email": user.email,
                "phone_number": user.phone_number,
                "brokerage": brokerage,
                "etf": etf,
                "brokerage_completed": UserRobinhoodInfo.objects.filter(user=user).exists(),
                "link_completed": PlaidItem.objects.filter(user=user).exists()
            }, 
            status=200
        )
     
class StockGraphData(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        uid = self.request.user.id

        cache.delete(f"uid_{uid}_get_investment_graph_data")
        cache.set(
            f"uid_{uid}_get_investment_graph_data",
            json.dumps({"success": None, "error": None}),
            timeout=120
        )
        # get_investment_graph_data.apply_async(uid)
        return JsonResponse({"success": "recieved"}, status=201)
    
    def get(self, request, *args, **kwargs):
        uid = self.request.user.id
        task_status = cache.get(f"uid_{uid}_get_investment_graph_data")
        # if task_status:
        #     return JsonResponse(json.loads(task_status), status=cached_task_status(task_status))
        # else:
            # return JsonResponse({"success": None, "error": "no cache value found"}, status=400)
        JsonResponse({"success": None, "error": "no cache value found"}, status=400)



# update info

class ResetPassword(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def put(self, request, *args, **kwargs):
        "Get verification code if the email matches an account"

        serializer = VerificationCodeRequestSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            for field in ["field", "non_field_errors"]:
                if field in e.detail and len(e.detail[field]) >= 1:
                    return JsonResponse(
                        {
                            "success": None,
                            "error": f"error '{field}': {e.detail[field][0]}"
                        }, 
                        status=400
                    )
            error_messages = {}
            for field in e.detail:
                if len(e.detail[field]) >= 1:
                    error_messages[field] = e.detail[field][0]
            return JsonResponse(
                {
                    "success": None,
                    "error": error_messages or None
                }, 
                status=200
            )
        except Exception as e:
            return JsonResponse(
                {
                    "success": None,
                    "error": f"error: {str(e)}"
                }, 
                status=400
            )
        
        if serializer.validated_data["field"] != "password":
            return JsonResponse(
                {
                    "success": None,
                    "error": "The field parameter must be 'password'."
                }, 
                status=400
            )
        
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
            return JsonResponse(
                {
                    "success": "recieved",
                    "error": None
                }, 
                status=200
            )
        
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
        
        return JsonResponse(
            {
                "success": "recieved",
                "error": None
            }, 
            status=200
        )

    def post(self, request, *args, **kwargs):
        """Given the correct code, extend its lifespan if no password given, 
        and if given the password then update password"""
        serializer = VerificationCodeResponseSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            for field in ["field", "non_field_errors"]:
                if field in e.detail and len(e.detail[field]) >= 1:
                    return JsonResponse(
                        {
                            "success": None,
                            "error": e.detail[field][0]
                        }, 
                        status=400
                    )
            error_messages = {}
            for field in e.detail:
                if len(e.detail[field]) >= 1:
                    error_messages[field] = e.detail[field][0]
            return JsonResponse(
                {
                    "success": None,
                    "error": error_messages or None
                }, 
                status=200
            )
        except Exception as e:
            return JsonResponse(
                {
                    "success": None,
                    "error": f"error: {str(e)}"
                }, 
                status=400
            )
        
        if serializer.validated_data["field"]!= "password":
            return JsonResponse(
                {
                    "success": None,
                    "error": "The field parameter must be 'password'."
                }, 
                status=400
            )
        
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
            return JsonResponse(
                    {
                        "success": None,
                        "error": {
                            "code": "This code is invalid or expired. Request a new one."
                        }
                    },
                    status=200
                )
        
        # check if the code has been requested for that field, and if values match
        code = serializer.validated_data['code']
        field = serializer.validated_data['field']
        value = serializer.validated_data[field]
        cached_value = cache.get(f"signed_out_uid_{user.id}_set_{field}_{code}")
        if cached_value is None:
            return JsonResponse(
                {
                    "success": None,
                    "error": {
                        "code": "This code is invalid or expired. Request a new one."
                    }
                },
                status=200
            )
        loaded_value = json.loads(cached_value)
        curr_val = value.encode('utf-8')
        cached_val = loaded_value[field].encode('utf-8')
        if not bcrypt.checkpw(curr_val, cached_val):
            return JsonResponse(
                {
                    "success": None,
                    "error": {
                        "code": "This code is invalid or expired. Request a new one."
                    }
                },
                status=200
            )

        user.set_password(serializer.validated_data["password"])
        user.save()

        cache.delete(f"signed_out_uid_{user.id}_set_{field}_{code}")

        return JsonResponse(
            {
                "success": "verification code valid",
                "error": None
            },
            status=200
        )

class RequestVerificationCode(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, *args, **kwargs):
        "Get verification code if the email matches an account"
        user = request.user

        serializer = VerificationCodeRequestSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            for field in ["field", "non_field_errors"]:
                if field in e.detail and len(e.detail[field]) >= 1:
                    return JsonResponse(
                        {
                            "success": None,
                            "error": f"error '{field}': {e.detail[field][0]}"
                        }, 
                        status=400
                    )
            for field in e.detail:
                if len(e.detail[field]) >= 1:
                    return JsonResponse(
                        {
                            "success": None,
                            "error": e.detail[field][0]
                        }, 
                        status=200
                    )
            return JsonResponse(
                {
                    "success": None,
                    "error": f"error: {str(e)}"
                }, 
                status=400
            )
        except Exception as e:
            return JsonResponse(
                {
                    "success": None,
                    "error": f"error: {str(e)}"
                }, 
                status=400
            )
        
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
            return JsonResponse(
                {
                    "success": None,
                    "error": "No user is associated with the information given"
                }, 
                status=400
            )
        

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
                return JsonResponse(
                    {
                        "success": None,
                        "error": {
                            "email": "This email is already in use."
                        }
                    }, 
                    status=200
                )
        elif 'phone_number' in serializer.validated_data:
            email = None
            phone_number = serializer.validated_data['phone_number']
            try: 
                _ = User.objects.get(phone_number=phone_number)
                user_exists = True
            except Exception as e:
                user_exists = False
            if user_exists:
                return JsonResponse(
                    {
                        "success": None,
                        "error": {
                            "phone_number": "This number is already in use."
                        }
                    }, 
                    status=200
                )
        
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
        
        return JsonResponse(
            {
                "success": "recieved",
                "error": None
            }, 
            status=200
        )

    def post(self, request, *args, **kwargs):
        """Given the correct code, extend its lifespan if no password given, 
        and if given the password then update password"""
        serializer = VerificationCodeResponseSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            for field in ["field", "non_field_errors"]:
                if field in e.detail and len(e.detail[field]) >= 1:
                    return JsonResponse(
                        {
                            "success": None,
                            "error": e.detail[field][0]
                        }, 
                        status=400
                    )
            error_messages = {}
            for field in e.detail:
                if len(e.detail[field]) >= 1:
                    error_messages[field] = e.detail[field][0]
            return JsonResponse(
                {
                    "success": None,
                    "error": error_messages
                }, 
                status=200
            )
        except Exception as e:
            return JsonResponse(
                {
                    "success": None,
                    "error": f"error: {str(e)}"
                }, 
                status=400
            )
        
        # check if the code has been requested for that field, and if values match
        code = serializer.validated_data['code']
        field = serializer.validated_data['field']
        value = serializer.validated_data[field]
        user = self.request.user
        cached_value = cache.get(f"uid_{user.id}_set_{field}_{code}")
        if cached_value is None:
            return JsonResponse(
                {
                    "success": None,
                    "error": {
                        "code": "Code is invalid or expired"
                    }
                },
                status=200
            )
        loaded_value = json.loads(cached_value)
        if field == "password":
            curr_val = value.encode('utf-8')
            cached_val = loaded_value[field].encode('utf-8')
            if not bcrypt.checkpw(curr_val, cached_val):
                return JsonResponse(
                    {
                        "success": None,
                        "error": {
                            "code": "Code is invalid or expired"
                        }
                    },
                    status=200
                )
        elif loaded_value[field] != value:
            return JsonResponse(
                {
                    "success": None,
                    "error": {
                        "code": "Code is invalid or expired"
                    }
                },
                status=200
            )
        
        cache.delete(f"uid_{user.id}_set_{field}_{code}")

        if field == "email":
            email = serializer.validated_data["email"]
            if User.objects.filter(email=email).exists():
                return JsonResponse(
                    {
                        "success": None,
                        "error": {
                            "email": "This email is already being used by another account"
                        }
                        
                    },
                    status=200
                )
            else:
                user.email = email
                user.save()
        elif field == "phone_number":
            phone_number = serializer.validated_data["phone_number"]
            if User.objects.filter(phone_number=phone_number).exists():
                return JsonResponse(
                    {
                        "success": None,
                        "error": {
                            "phone_number": "This number is already being used by another account"
                        }
                    },
                    status=200
                )
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
                return JsonResponse(
                    {
                        "success": None,
                        "error": "We could not find your brokerage and investment choice. Please contact Accumate."
                    },
                    status=200
                )
        elif field == "symbol":
            try: 
                userBrokerageInfo = UserBrokerageInfo.objects.get(user=user)
                userBrokerageInfo.symbol = serializer.validated_data["symbol"]
                userBrokerageInfo.save()
            except Exception as e:
                return JsonResponse(
                    {
                        "success": None,
                        "error": "We could not find your brokerage and investment choice. Please contact Accumate."
                    },
                    status=200
                )
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
            return JsonResponse(
                {
                    "success": None,
                    "error": "The field parameter must be one of 'password', " + \
                            "'email', 'phone_number', 'full_name', 'brokerage', " + \
                            "or 'symbol'."
                },
                status=200
            )

        return JsonResponse(
            {
                "success": "verification code valid",
                "error": None
            },
            status=200
        )

class SendEmail(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = SendEmailSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            email = serializer.validated_data["email"]
            if not User.objects.filter(email=email).exists():
                send_forgot_email.apply_async(
                    kwargs = {
                        "useEmail": True, 
                        "sendTo": serializer.validated_data["email"],
                    }
                )
            return JsonResponse(
                {
                    "success": "email sent", 
                    "error": None
                }, 
                status=200
            )
        except ValidationError as e:
            if "email" in e.detail and len(e.detail["email"]) > 0:
                return JsonResponse(
                    {
                        "success": None, 
                        "error": e.detail["email"][0]
                    }, 
                    status=200
                )
            else: 
                return JsonResponse(
                    {
                        "success": None, 
                        "error": f"error: {str(e)}"
                    }, 
                    status=400
                )
        except Exception as e:
            return JsonResponse(
                {
                    "success": None, 
                    "error": f"error: {str(e)}"
                }, 
                status=400
            )

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
                return JsonResponse(
                    json.loads(cached_result),
                    status=200
                )
            else:
                return JsonResponse(
                    {
                        "success": None,
                        "error": "no cached value found for that code"
                    },
                    status=400
                )
        except Exception as e:
            return JsonResponse(
                {
                    "success": None,
                    "error": f"error: {str(e)}"
                },
                status=400
            )


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
            return JsonResponse({"success": "email added"}, status=200)
        except Exception as e:
            return JsonResponse({"error": e.args[0]}, status=400)

