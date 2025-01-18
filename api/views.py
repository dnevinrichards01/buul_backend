# from django.contrib.auth.models import User
from .models import User, WaitlistEmail, PlaidUser, PasswordReset
from rest_framework.views import APIView
from .serializers.accumateAccountSerializers import ResetPasswordRequestSerializer, \
    ResetPasswordSerializer
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
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from .tasks import test_celery_task, plaid_item_public_token_exchange, \
    plaid_link_token_create, plaid_user_create, accumate_user_remove, \
    plaid_user_remove, send_recovery_email

import time
from django.core.mail import send_mail
from django.urls import reverse




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


class RequestPasswordReset(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = ResetPasswordRequestSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
        
        try:
            email = serializer.validated_data['email']
            user = User.objects.get(email=email)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

        token_generator = PasswordResetTokenGenerator()
        token = token_generator.make_token(user) 

        reset_url = f"https://{DOMAIN}/resetpassword/{token}"

        passwordReset, created = PasswordReset.objects.update_or_create(
            email=email, 
            token=token
        )

        send_recovery_email.apply_async(kwargs={"email": email, "url": reset_url})

        return JsonResponse({'success': 'We have sent you a link to reset your password'}, status=200)


class ResetPassword(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

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
        
        try:
            token = kwargs['token']
            reset_obj = PasswordReset.objects.get(token=token)
        except:
            return JsonResponse({'error':'Invalid token'}, status=400)
        
        try:
            user = User.objects.get(email=reset_obj.email)
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            reset_obj.delete()
        except:
            return JsonResponse({"error": str(e)}, status=400)
        
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