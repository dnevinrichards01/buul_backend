# from django.contrib.auth.models import User
from .models import User, WaitlistEmail, PlaidUser, UserBrokerageInfo
from rest_framework.views import APIView
from .serializers.accumateAccountSerializers import WaitlistEmailSerializer, \
    EmailPhoneSignUpValidationSerializer, UserBrokerageInfoSerializer, NamePasswordValidationSerializer, \
    VerificationCodeResponseSerializer, VerificationCodeRequestSerializer, SendEmailSerializer, \
    PasswordResetSerializer, DeleteAccountVerifySerializer
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

import time
from django.core.mail import send_mail
from django.urls import reverse
import secrets 

# helper methods

def createVerificationCode():
    return secrets.randbelow(999999) + 100000

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
            for field in e.detail.keys():
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

class EmailPhoneSignUpValidation(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
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
                            "error": f"{field}: {e.detail[field][0]}"
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
        
        # check if a user with this email or phone number already exists
        user_exists = False
        if 'email' in serializer.validated_data:
            email = serializer.validated_data['email']
            phone_number = None
            try: 
                User.objects.get(email=email)
                user_exists = True
            except Exception as e:
                user_exists = False
        elif 'phone_number' in serializer.validated_data:
            email = None
            phone_number = serializer.validated_data['phone_number']
            try: 
                User.objects.get(phone_number=phone_number)
                user_exists = True
            except Exception as e:
                user_exists = False
        if user_exists:
            return JsonResponse(
                {
                    "success": None,
                    "error": f"This {'email' if bool(email) else 'number'} is in use by another user"
                }, 
                status=200
            )
        
        # cache code and the value to be verified, and send verification code
        code = createVerificationCode()
        field = serializer.validated_data['field']
        cached_value = {field: serializer.validated_data[field]}
        cache.delete(f"set_{field}_{code}")
        cache.set(
            f"set_{field}_{code}",
            json.dumps(cached_value),
            timeout=300
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
        serializer = EmailPhoneSignUpValidationSerializer(data=request.data)
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

        # check if a user with this email or phone number already exists
        user_exists = False
        field = serializer.validated_data['field']
        if field == 'email':
            email = serializer.validated_data['email']
            phone_number = None
            try: 
                _ = User.objects.get(email=email)
                user_exists = True
            except Exception as e:
                user_exists = False
        elif field == 'phone_number':
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
                    "error": f"This {'email' if bool(email) else 'number'} is in use by another user"
                }, 
                status=200
            )
        
        # check if the code and field correspond to a cached value
        code = serializer.validated_data['code']
        cached_value = cache.get(f"set_{field}_{code}")
        if cached_value is None:
            return JsonResponse(
                {
                    "success": None,
                    "error": "Code is invalid or expired"
                },
                status=200
            )
        
        # check if the cached value matches the value submitted for verification
        value = json.loads(cached_value)
        if field in value and value[field] == serializer.validated_data[field]:
            # verified
            cache.delete(f"set_{field}_{code}")
            return JsonResponse(
                {
                    "success": "validated",
                    "error": None
                },
                status=200
            )
        else:
            # not verified
            return JsonResponse(
            {
                "success": None,
                "error": "Code is invalid or expired"
            },
            status=200
        )

        # if all previous check succeed, return validated
        
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
            error_messages = {}
            for field in e.detail:
                if len(e.detail[field]) >= 1:
                    error_messages[field] = e.detail[field][0]
            return JsonResponse(
                {
                    "success": None,
                    "error": serializer.errors#error_messages
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
            
        try :
            userBrokerageInfo = UserBrokerageInfo.objects.get(user__id=uid)
            userBrokerageInfo.brokerage = serializer.validated_data["brokerage"]
            userBrokerageInfo.symbol = serializer.validated_data["symbol"]
        except:
            userBrokerageInfo = UserBrokerageInfo(
                user = User.objects.get(id=uid),
                brokerage = serializer.validated_data["brokerage"],
                symbol = serializer.validated_data["symbol"]
            )
        userBrokerageInfo.save()

        return JsonResponse({"success": "recieved", "error": None}, status=201)



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
            "country_codes": ["US"],
            "language": "en",
            "enable_multi_item_link": True,
            "webhook": "https://your-ngrok-id.ngrok.io/api/plaid/sessionfinished/",
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
            return
        
        status = serializer.validated_data["status"]
        if status != "SUCCESS":
            return
        
        link_token = serializer.validated_data["link_token"]
        cached_uid = cache.get(f"link_token_{link_token}_user")
        if cached_uid:
            uid = json.loads(cached_uid)["uid"]
            cache.delete(f"link_token_{link_token}_user")
        else:
            return

        cache.delete(f"uid_{uid}_plaid_item_public_token_exchange")
        cache.set(
            f"uid_{uid}_plaid_item_public_token_exchange",
            json.dumps({"success": None, "error": None}),
            timeout=120
        )
        plaid_item_public_token_exchange.apply_async(
            kwargs = {
                "uid": uid,
                "public_tokens": serializer.validated_data["public_tokens"]
            }
        )
        return JsonResponse({"success": None, "error": None}, status=201)



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
                "etf": etf
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

    def get(self, request, *args, **kwargs):
        "Get verification code if the email matches an account"

        serializer = VerificationCodeRequestSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            if serializer.validated_data["field"] != "password":
                return JsonResponse(
                    {
                        "success": None,
                        "error": "The field parameter must be 'password'"
                    }, 
                    status=400
                )
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
        user = None
        if 'email' in serializer.validated_data:
            email = serializer.validated_data['email']
            phone_number = None
            try: 
                user = User.objects.get(email=email)
                user_exists = True
            except Exception as e:
                user = None
                user_exists = False
        elif 'phone_number' in serializer.validated_data:
            email = None
            phone_number = serializer.validated_data['phone_number']
            try: 
                user = User.objects.get(phone_number=phone_number)
                user_exists = True
            except Exception as e:
                user = None
                user_exists = False
        
        # if they exist send verification code
        if user_exists:
            code = createVerificationCode()
            uid = user.id
            field = "password"

            cache.delete(f"uid_{user.id}_set_{field}_{code}")
            cache.set(
                f"uid_{user.id}_set_{field}_{code}",
                json.dumps({field: None}),
                timeout=300
            )

            send_verification_code.apply_async(
                kwargs = {
                    "useEmail": bool(email), 
                    "sendTo": email or phone_number,
                    "code": code
                }
            )
        
        # send success response either way to not reveal if a user with that password exists
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
            if serializer.validated_data["field"] != "password":
                return JsonResponse(
                    {
                        "success": None,
                        "error": "The field parameter must be 'password'"
                    }, 
                    status=400
                )
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
        
        # check if a user with the given account info exists
        user_exists = False
        user = None
        if 'old_email' in serializer.validated_data:
            email = serializer.validated_data['old_email']
            phone_number = None
            try: 
                user = User.objects.get(email=email)
                user_exists = True
            except Exception as e:
                user = None
                user_exists = False
        elif 'old_phone_number' in serializer.validated_data:
            email = None
            phone_number = serializer.validated_data['old_phone_number']
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
                        "error": "Code is invalid or expired"
                    },
                    status=200
                )
        
        # return JsonResponse({"uh oh": "checked if user exists"}, status=300)
        # check if the code matches
        code = serializer.validated_data['code']
        uid = user.id
        field = "password"
        cached_value = cache.get(f"uid_{uid}_set_{field}_{code}")
        if cached_value is None:
            return JsonResponse(
                {
                    "success": None,
                    "error": "Code is invalid or expired"
                },
                status=200
            )
        
        # return JsonResponse({"uh oh": "found cached value"}, status=300)
        # check if the code given was to reset the password
        value = json.loads(cached_value)
        if "password" not in value:
            return JsonResponse(
                {
                    "success": None,
                    "error": "Code is invalid or expired"
                },
                status=200
            )
        
        if "password" in serializer.validated_data:
            cache.delete(f"uid_{user.id}_set_{field}_{code}")
            user.set_password(serializer.validated_data["password"])
            user.save()
            cache.delete(f"uid_{user.id}_set_{field}_{code}")
            return JsonResponse(
                {
                    "success": "password reset",
                    "error": None
                },
                status=200
            )
        else:
            # extend period of time during which the code is valid
            cache.delete(f"uid_{user.id}_set_{field}_{code}")
            cache.set(
                f"uid_{user.id}_set_{field}_{code}",
                json.dumps({field: None}),
                timeout=300
            )
            return JsonResponse(
                {
                    "success": "code valid",
                    "error": None
                },
                status=200
            )

class RequestVerificationCode(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        "Get verification code if the email matches an account"

        serializer = VerificationCodeRequestSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            if serializer.validated_data["field"] not in ["password", "email", \
                "phone_number", "full_name", "brokerage", "symbol"]:
                return JsonResponse(
                    {
                        "success": None,
                        "error": "The field parameter must be one of 'password', " + \
                            "'email', 'phone_number', 'full_name', 'brokerage', " + \
                            "or 'symbol'."
                    }, 
                    status=400
                )
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
        user = None
        if 'email' in serializer.validated_data:
            email = serializer.validated_data['email']
            phone_number = None
            try: 
                user = User.objects.get(email=email)
                user_exists = True
            except Exception as e:
                user = None
                user_exists = False
        elif 'phone_number' in serializer.validated_data:
            email = None
            phone_number = serializer.validated_data['phone_number']
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
                    "error": "No user is associated with the information given"
                }, 
                status=400
            )
        
        code = createVerificationCode()
        uid = user.id
        field = serializer.validated_data['field']

        cache.delete(f"uid_{user.id}_set_{field}_{code}")
        cache.set(
            f"uid_{user.id}_set_{field}_{code}",
            json.dumps({field: None}),
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
            if serializer.validated_data["field"] not in ["password", "email", \
                "phone_number", "full_name", "brokerage", "symbol"]:
                return JsonResponse(
                    {
                        "success": None,
                        "error": "The field parameter must be one of 'password', " + \
                            "'email', 'phone_number', 'full_name', 'brokerage', " + \
                            "or 'symbol'."
                    }, 
                    status=400
                )
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
        
        # check if a user with the given account info exists
        user_exists = False
        user = None
        if 'old_email' in serializer.validated_data:
            email = serializer.validated_data['old_email']
            phone_number = None
            try: 
                user = User.objects.get(email=email)
                user_exists = True
            except Exception as e:
                user = None
                user_exists = False
        elif 'old_phone_number' in serializer.validated_data:
            email = None
            phone_number = serializer.validated_data['old_phone_number']
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
                        "error": "Code is invalid or expired"
                    },
                    status=200
                )
        
        # return JsonResponse({"uh oh": "checked if user exists"}, status=300)
        # check if the code matches
        code = serializer.validated_data['code']
        field = serializer.validated_data['field']
        cached_value = cache.get(f"uid_{user.id}_set_{field}_{code}")
        if cached_value is None:
            return JsonResponse(
                {
                    "success": None,
                    "error": "Code is invalid or expired"
                },
                status=200
            )
        
        # return JsonResponse({"uh oh": "found cached value"}, status=300)
        # check if the code given was to reset the password
        value = json.loads(cached_value)
        if field not in value:
            return JsonResponse(
                {
                    "success": None,
                    "error": "Code is invalid or expired"
                },
                status=200
            )
        
        if not field in serializer.validated_data:
            return JsonResponse(
                {
                    "success": None,
                    "error": f"No {field} was submitted."
                },
                status=400
            ) 
        
        cache.delete(f"uid_{user.id}_set_{field}_{code}")

        if field == "email":
            email = serializer.validated_data["email"]
            if not User.objects.filter(email=email).empty():
                return JsonResponse(
                    {
                        "success": None,
                        "error": "This email is already being used by another account"
                    },
                    status=200
                )
            else:
                user.email = email
                user.save()
        elif field == "phone_number":
            phone_number = serializer.validated_data["phone_number"]
            if not User.objects.filter(phone_number=phone_number).empty():
                return JsonResponse(
                    {
                        "success": None,
                        "error": "This number is already being used by another account"
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
                        "error": "This user does has not yet chosen their brokerage and investment"
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
                        "error": "This user does has not yet chosen their brokerage and investment"
                    },
                    status=200
                )
        elif field == "password":
            user.set_password(serializer.validated_data["password"])
            user.save()
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

class DeleteAccount(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        "Get verification code if the email matches an account"
        
        serializer = VerificationCodeRequestSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            if serializer.validated_data["field"] != "delete_account":
                return JsonResponse(
                    {
                        "success": None,
                        "error": "The field parameter must be 'delete_account'"
                    }, 
                    status=400
                )
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
        user = None
        if 'email' in serializer.validated_data:
            email = serializer.validated_data['email']
            phone_number = None
            try: 
                user = User.objects.get(email=email)
                user_exists = True
            except Exception as e:
                user = None
                user_exists = False
        elif 'phone_number' in serializer.validated_data:
            email = None
            phone_number = serializer.validated_data['phone_number']
            try: 
                user = User.objects.get(phone_number=phone_number)
                user_exists = True
            except Exception as e:
                user = None
                user_exists = False
        
        # if they exist send verification code
        if user_exists:
            code = createVerificationCode()
            uid = user.id
            field = "delete_account"

            cache.delete(f"uid_{user.id}_set_{field}_{code}")
            cache.set(
                f"uid_{user.id}_set_{field}_{code}",
                json.dumps({field: True}),
                timeout=300
            )

            send_verification_code.apply_async(
                kwargs = {
                    "useEmail": bool(email), 
                    "sendTo": email or phone_number,
                    "code": code
                }
            )
        
        # send success response either way to not reveal if a user with that password exists
        return JsonResponse(
            {
                "success": "recieved",
                "error": None
            }, 
            status=200
        )
    
    def post(self, request, *args, **kwargs):
        "given correct code, the account deletion is triggered"
        # import pdb
        # breakpoint()


        serializer = VerificationCodeResponseSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            if serializer.validated_data["field"] != "delete_account":
                return JsonResponse(
                    {
                        "success": None,
                        "error": "The field parameter must be 'delete_account'"
                    }, 
                    status=400
                )
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
        
        # check if a user with the given account info exists
        user_exists = False
        user = None
        if 'old_email' in serializer.validated_data:
            email = serializer.validated_data['old_email']
            phone_number = None
            try: 
                user = User.objects.get(email=email)
                user_exists = True
            except Exception as e:
                user = None
                user_exists = False
        elif 'old_phone_number' in serializer.validated_data:
            email = None
            phone_number = serializer.validated_data['old_phone_number']
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
                        "error": "Code is invalid or expired"
                    },
                    status=200
                )
        
        # return JsonResponse({"uh oh": "checked if user exists"}, status=300)
        # check if the code matches
        code = serializer.validated_data['code']
        uid = user.id
        field = "delete_account"
        cached_value = cache.get(f"uid_{uid}_set_{field}_{code}")
        if cached_value is None:
            return JsonResponse(
                {
                    "success": None,
                    "error": "Code is invalid or expired"
                },
                status=200
            )
        
        # return JsonResponse({"uh oh": "found cached value"}, status=300)
        # check if the code given was to reset the password
        value = json.loads(cached_value)
        if "delete_account" not in value:
            return JsonResponse(
                {
                    "success": None,
                    "error": "Code is invalid or expired"
                },
                status=200
            )
        
        #verified so delete verification code and begin deletion
        cache.delete(f"uid_{user.id}_set_{field}_{code}")
        cache.delete(f"code_{code}_accumate_user_remove")
        cache.set(
            f"code_{code}_accumate_user_remove",
            json.dumps({"success": None, "error": None}),
            timeout=120
        )
        chain(
            plaid_user_remove.s(uid, code),
            accumate_user_remove.si(uid, code)
        ).apply_async()
        # accumate_user_remove.apply_async(kwargs={"uid": uid})
        return JsonResponse({"success": code, "error": None}, status=201)

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

