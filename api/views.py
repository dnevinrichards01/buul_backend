# from django.contrib.auth.models import User
from .models import User, WaitlistEmail, PlaidUser, UserBrokerageInfo
from rest_framework.views import APIView
from .serializers.accumateAccountSerializers import ResetPasswordRequestSerializer, \
    ResetPasswordSerializer, VerificationCodeSerializer, WaitlistEmailSerializer, \
    EmailPhoneValidationSerializer, UserBrokerageInfoSerializer
from .serializers.accumateAccountSerializers import UserSerializer, WaitlistEmailSerializer
from .serializers.PlaidSerializers.itemSerializers import ItemPublicTokenExchangeRequestSerializer
from .serializers.PlaidSerializers.linkSerializers import \
    LinkTokenCreateRequestTransactionsSerializer, LinkTokenCreateRequestSerializer
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication

from django.http import HttpResponseBadRequest, HttpResponse, JsonResponse
from django.core.exceptions import ValidationError
from django.core.cache import cache
import json
import phonenumbers

from accumate_backend.settings import DOMAIN
from celery import current_app, chain
from functools import partial
from django.db import transaction
from .tasks.userTasks import plaid_item_public_token_exchange, \
    plaid_link_token_create, plaid_user_create, accumate_user_remove, \
    plaid_user_remove, send_verification_code, send_waitlist_email
from .tasks.transactionsTasks import get_investment_graph_data

import time
from django.core.mail import send_mail
from django.urls import reverse
import secrets 

def createVerificationCode():
    return secrets.randbelow(999999) + 100000

def healthCheck(request):
    return JsonResponse({"success": "healthy"}, status=200)

class CreateUserView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        # Use the serializer to validate input data
        serializer = UserSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            serializer.save() # error here indicates duplicate
            return JsonResponse({"success": "user registered"}, status=200)
        except Exception as e:
            return JsonResponse({"error": e.args[0]}, status=400)

# send them a confirmation email along with this??
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

            send_waitlist_email.apply_async(kwargs={"sendTo": email})
            return JsonResponse({"success": "email added"}, status=200)
        except Exception as e:
            return JsonResponse({"error": e.args[0]}, status=400)

class EmailPhoneValidation(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        serializer = VerificationCodeSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
        
        code = serializer.validated_data["code"]
        cached_code = cache.get(f"verify_code_{code}")
        if cached_code is None:
            return JsonResponse({"error": "Code is invalid or expired"})
        else:
            cache.delete(f"verify_code_{code}")
            return JsonResponse({"success": "verification code valid"})


    def post(self, request, *args, **kwargs):
        serializer = EmailPhoneValidationSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
        
        if 'email' in serializer.validated_data:
            email = serializer.validated_data['email']
            sms = None
        elif 'sms' in serializer.validated_data:
            email = None
            sms = serializer.validated_data['sms']
        else:
            return JsonResponse({"error": "must return 'email' or 'sms'"}, status=400)
        
        code = createVerificationCode()

        cache.delete(f"verify_code_{code}")
        cache.set(
            f"verify_code_{code}",
            json.dumps({"email": email, "sms": sms}),
            timeout=300
        )

        send_verification_code.apply_async(
            kwargs = {
                "useEmail": bool(email), 
                "sendTo": email or sms,
                "code": code
            }
        )

        return JsonResponse({'success': 'verification code sent'}, status=200)
    
class RequestPasswordReset(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = ResetPasswordRequestSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
        
        if 'email' in serializer.validated_data:
            email = serializer.validated_data['email']
            sms = None
            try:
                user = User.objects.get(email=email)
            except Exception as e:
                JsonResponse({"error": "user not found"}, status=400)
        elif 'sms' in serializer.validated_data:
            email = None
            sms = serializer.validated_data['sms']
            try:
                user = User.objects.get(sms=sms)
            except Exception as e:
                JsonResponse({"error": "user not found"}, status=400)
        else:
            return JsonResponse({"error": "must return 'email' or 'sms'"}, status=400)
        
        code = createVerificationCode()

        cache.delete(f"verify_code_{code}")
        cache.set(
            f"verify_code_{code}",
            json.dumps({"email": email, "sms": sms}),
            timeout=300
        )

        send_verification_code.apply_async(
            kwargs = {
                "useEmail": bool(email), 
                "sendTo": email or sms,
                "code": code
            }
        )

        return JsonResponse({'success': 'verification code sent'}, status=200)

class ResetPassword(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        serializer = VerificationCodeSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
        
        code = serializer.validated_data["code"]
        cached_code = cache.get(f"verify_code_{code}")
        if cached_code is None:
            raise JsonResponse({"error": "Code is invalid or expired"})
        # refreshing code to last longer
        cached_code = json.loads(cached_code)
        cache.set(
            f"verify_code_{code}",
            json.dumps({"email": cached_code["email"], "sms": cached_code["sms"]}),
            timeout=300
        )
        return JsonResponse({"success": "verification code valid"})

    def post(self, request, *args, **kwargs):
        serializer = ResetPasswordSerializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
        
        new_password = serializer.validated_data['new_password']
        confirm_password = serializer.validated_data['confirm_password']
        if new_password != confirm_password:
            return JsonResponse({"error": "Passwords do not match"}, status=400)
        
        code = serializer.validated_data["code"]
        cached_code = cache.get(f"verify_code_{code}")
        if cached_code is None:
            raise JsonResponse({"error": "Code is invalid or expired"})
        cached_code = json.loads(cached_code)
        
        try:
            if cached_code["email"]:
                user = User.objects.get(email=cached_code["email"])
            else: 
                user = User.objects.get(sms=cached_code["sms"])
        except Exception as e:
            return JsonResponse({"error": "user not found"}, status=400)
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        cache.delete(f"verify_code_{code}")
        
        return JsonResponse({'success':'Password updated'}, status=200)

class PlaidItemPublicTokenExchange(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # import pdb
        # breakpoint()
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
        plaid_item_public_token_exchange.apply_async(kwargs=validated_data)
        return JsonResponse({"success": "recieved"}, status=201)
    
    def get(self, request, *args, **kwargs):
        uid = self.request.user.id
        task_status = cache.get(f"uid_{uid}_plaid_item_public_token_exchange")
        if task_status:
            return JsonResponse(json.loads(task_status), status=201)
        else:
            return JsonResponse({"error": "no cache value found"}, status=400)

class PlaidLinkTokenCreate(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # import pdb
        # breakpoint()
        # Use the serializer to validate input data
        data = request.data.copy()

        try:
            phone_number = request.data.get("user", {}).get("phone_number")
            parsed_phone_number = phonenumbers.parse(phone_number, None)
            if not phonenumbers.is_valid_number(parsed_phone_number):
                raise Exception("Invalid phone number.")
            data["user"]["phone_number"] = phonenumbers.format_number(
                parsed_phone_number, 
                phonenumbers.PhoneNumberFormat.E164
            )
        except Exception as e:
            return JsonResponse({"error": "invalid phone number"}, status=400)
        
        serializer = LinkTokenCreateRequestSerializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
        # Access the validated data
        validated_data = serializer.validated_data
        uid = self.request.user.id
        validated_data['uid'] = uid

        cache.delete(f"uid_{uid}_plaid_link_token_create")
        cache.set(
            f"uid_{uid}_plaid_link_token_create",
            json.dumps({"message": "pending", "error": None}),
            timeout=120
        )
        plaid_link_token_create.apply_async(kwargs=validated_data)
        return JsonResponse({"success": "recieved"}, status=201)
    
    def get(self, request, *args, **kwargs):
        uid = self.request.user.id
        task_status = cache.get(f"uid_{uid}_plaid_link_token_create")
        if task_status:
            return JsonResponse(json.loads(task_status), status=201)
        else:
            return JsonResponse({"error": "no cache value found"}, status=400)

class PlaidUserCreate(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # import pdb
        # breakpoint()
        
        uid = self.request.user.id

        try:
            if PlaidUser.objects.filter(user__id=uid).count() != 0:
                raise Exception("plaid user already exists for this account")
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    
        cache.delete(f"uid_{uid}_plaid_user_create")
        cache.set(
            f"uid_{uid}_plaid_user_create",
            json.dumps({"message": "pending", "error": None}),
            timeout=120
        )
        plaid_user_create.apply_async(kwargs={"uid": uid})
        return JsonResponse({"success": "recieved"}, status=201)
    
    def get(self, request, *args, **kwargs):
        uid = self.request.user.id
        task_status = cache.get(f"uid_{uid}_plaid_user_create")
        if task_status:
            return JsonResponse(json.loads(task_status), status=201)
        else:
            return JsonResponse({"error": "no cache value found"}, status=400)

class DeleteAccount(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, *args, **kwargs):
        # import pdb
        # breakpoint()
        
        uid = self.request.user.id

        cache.delete(f"uid_{uid}_accumate_user_remove")
        cache.set(
            f"uid_{uid}_accumate_user_remove",
            json.dumps({"message": "pending", "error": None}),
            timeout=120
        )
        chain(
            plaid_user_remove.s(uid),
            accumate_user_remove.si(uid)
        ).apply_async()
        # accumate_user_remove.apply_async(kwargs={"uid": uid})
        return JsonResponse({"success": "recieved"}, status=201)
    
    def get(self, request, *args, **kwargs):
        # should never be successfully called (can't authenticate non-existent user)
        # {
        #     "detail": "User not found",
        #     "code": "user_not_found"
        # }
        return JsonResponse({"error": "user not deleted"}, status=400)

class BrokerageInvestment(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # import pdb
        # breakpoint()
        
        uid = self.request.user.id

        serializer = UserBrokerageInfoSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
        
        userBrokerageInfo = UserBrokerageInfo(
            user = User.objects.get(id=uid),
            brokerage = serializer.validated_data["brokerage"],
            symbol = serializer.validated_data["symbol"]
        )
        userBrokerageInfo.save()

        return JsonResponse({"success": "recieved"}, status=201)
    
class StockGraphData(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        uid = self.request.user.id

        cache.delete(f"uid_{uid}_get_investment_graph_data")
        cache.set(
            f"uid_{uid}_get_investment_graph_data",
            json.dumps({"message": "pending", "error": None}),
            timeout=120
        )
        get_investment_graph_data.apply_async(uid)
        return JsonResponse({"success": "recieved"}, status=201)
    
    def get(self, request, *args, **kwargs):
        uid = self.request.user.id
        task_status = cache.get(f"uid_{uid}_get_investment_graph_data")
        if task_status:
            return JsonResponse(json.loads(task_status), status=201)
        else:
            return JsonResponse({"error": "no cache value found"}, status=400)





