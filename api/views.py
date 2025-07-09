# from django.contrib.auth.models import User
from .models import User, WaitlistEmail, PlaidUser, UserBrokerageInfo, PlaidItem, \
    UserInvestmentGraph, Log, PlaidPersonalFinanceCategories, PlaidLinkWebhook, \
    Investment, UserInvestmentGoal
from rest_framework.views import APIView
from .serializers.buul import WaitlistEmailSerializer, \
    UserBrokerageInfoSerializer, NamePasswordValidationSerializer, \
    VerificationCodeResponseSerializer, VerificationCodeRequestSerializer, SendEmailSerializer, \
    DeleteAccountVerifySerializer, MyTokenRefreshSerializer, RequestLinkTokenSerializer, \
    GetUserInvestmentsSerializer
from .serializers.buul import UserSerializer, \
    WaitlistEmailSerializer, GraphDataRequestSerializer
from .serializers.plaid.item import ItemPublicTokenExchangeRequestSerializer
from .serializers.plaid.link import \
    LinkTokenCreateRequestTransactionsSerializer, LinkTokenCreateRequestSerializer
from .serializers.plaid.webhook import \
    PlaidSessionFinishedSerializer, WebhookSerializer, PlaidTransactionSyncUpdatesAvailable, \
    PlaidItemWebhookSerializer, LinkEventWebhookSerializer
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken
from django.db.models import Case, When, Value, CharField, F, Func
from django.http import JsonResponse
from rest_framework.exceptions import ValidationError
from django.core.cache import cache
import json
from api.apis.fmp import FPMUtils
from celery import current_app, chain, chord
from .tasks.user import plaid_item_public_tokens_exchange, \
    plaid_link_token_create, plaid_user_create, buul_user_remove, \
    plaid_user_remove, send_verification_code, send_waitlist_email, send_forgot_email
from .tasks.graph import refresh_stock_data_by_interval, get_graph_data
from .tasks.identify import update_transactions
from .tasks.deposit import match_brokerage_plaid_accounts
from robin_stocks.models import UserRobinhoodInfo
import math
import secrets 

from django.db.utils import OperationalError

from buul_backend.settings import LOAD_BALANCER_ENDPOINT

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .serializers.buul import MyTokenObtainPairSerializer
import bcrypt 

from buul_backend.viewHelper import LogState, log, validate, \
    cached_task_logging_info


# helper methods

def healthCheck(request):
    return JsonResponse({"success": "healthy"}, status=200)

def createVerificationCode():
    digits = str(secrets.randbelow(1000000))
    return "0" * (6 - len(digits)) + digits


# tokens

class MyTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = MyTokenObtainPairSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)

            user = serializer.validated_data['user']
            app_version = serializer.validated_data.get('app_version', None)
            if app_version != user.app_version and app_version is not None:
                user.app_version = app_version
                user.save()
            refresh = RefreshToken.for_user(user)

            status = 200
            log(Log, self, status, LogState.SUCCESS, user = serializer.validated_data['user'])
            return JsonResponse(
                {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token)
                }, 
                status = status
            )
        except ValidationError as e:
            error_messages = {}
            for field in e.detail:
                if len(e.detail[field]) >= 1:
                    error_messages[field] = e.detail[field][0]
            status = 401
            log(Log, self, status, LogState.VAL_ERR_NO_MESSAGE, errors = error_messages)
            return JsonResponse({}, status = status)
        except Exception as e:
            if isinstance(e, OperationalError):
                raise e
            status = 401
            log(Log, self, status, LogState.VAL_ERR_UNKOWN, errors = {"error": str(type(e))})
            return JsonResponse({}, status = status)

class MyTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = MyTokenRefreshSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            status = 200
            log(Log, self, status, LogState.SUCCESS,
                user = serializer.validated_data['user'])
            return JsonResponse(
                {
                    'refresh': serializer.validated_data['refresh'],
                    'access': serializer.validated_data['access']
                }, 
                status = status
            )
        except ValidationError as e:
        # validation errors which we have no tolerance for
            error_messages = {}
            for field in e.detail:
                if len(e.detail[field]) >= 1:
                    error_messages[field] = e.detail[field][0]
            status = 401
            log(Log, self, status, LogState.VAL_ERR_NO_MESSAGE, errors = error_messages)
            return JsonResponse({}, status = status)
        except Exception as e:
            if isinstance(e, OperationalError):
                raise e
            status = 401
            log(Log, self, status, LogState.VAL_ERR_INTERNAL, errors = {"error": str(type(e))})
            return JsonResponse({}, status = status)


# sign up flow

class CreateUserView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        # Use the serializer to validate input data
        serializer = UserSerializer(data=request.data)
        validation_error_response = validate(
            Log, serializer, self, 
            fields_to_correct=["email", "password", "phone_number", "full_name"], 
            fields_to_fail=['pre_account_id', 'username'],
            edit_error_message=lambda x: "A " + x if x[:4] == "user" else x
        )
        if validation_error_response:
            return validation_error_response
        
        pre_account_id = serializer.validated_data['pre_account_id']
        user = serializer.save()
        status = 200
        log(Log, self, status, LogState.SUCCESS, user = user, pre_account_id=pre_account_id)
        return JsonResponse(
            {"success": "user registered", "error": None}, 
            status=status
        )

class NamePasswordValidation(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = NamePasswordValidationSerializer(data=request.data)
        validation_error_respose = validate(
            Log, serializer, self, fields_to_correct=["full_name", "password"], 
            fields_to_fail=["non_field_errors", "pre_account_id"]
        )
        if validation_error_respose:
            return validation_error_respose
        
        status = 200
        log(Log, self, status, LogState.SUCCESS,
            pre_account_id = serializer.validated_data['pre_account_id'])
        return JsonResponse(
            {
                "success": "validated", 
                "error": None
            }, 
            status = status
        ) 

class EmailPhoneSignUpValidation(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def put(self, request, *args, **kwargs):
        "Get verification code if the email matches an account"

        serializer = VerificationCodeRequestSerializer(data=request.data)
        validation_error_respose = validate(
            Log, serializer, self, 
            fields_to_correct=[
                "verification_email", "verification_phone_number", "email", 
                "phone_number", "phone_number", "full_name", "brokerage", 
                "symbol", "password", "password2", "delete_account"
            ], 
            fields_to_fail=["field", "non_field_errors", "pre_account_id"]
        )
        if validation_error_respose:
            return validation_error_respose
        
        pre_account_id = serializer.validated_data['pre_account_id']

        # this endpoint is only for email and phone_number validation
        if serializer.validated_data["field"] not in ["email", "phone_number"]:
            status = 400
            error_messages = {
                "field": "The field parameter must be 'email' or 'phone_number'."
            }
            log(Log, self, status, LogState.VAL_ERR_NO_MESSAGE, 
                errors = error_messages, pre_account_id = pre_account_id)
            return JsonResponse(
                {
                    "success": None,
                    "error": error_messages
                }, 
                status = status
            )
        
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
                if isinstance(e, OperationalError):
                    raise e
                user_exists = False
        elif field == "phone_number":
            email = None
            phone_number = serializer.validated_data['phone_number']
            try: 
                _ = User.objects.get(phone_number=phone_number)
                user_exists = True
            except Exception as e:
                if isinstance(e, OperationalError):
                    raise e
                user_exists = False
        if user_exists:
            status = 200
            error_message = f"This {field.replace("_", " ")} is already in use."
            error_messages = {
                "email": error_message if email else None,
                "phone_number": error_message if phone_number else None
            }
            log(Log, self, status, LogState.VAL_ERR_MESSAGE, errors = error_messages,
                pre_account_id=pre_account_id)
            return JsonResponse(
                {
                    "success": None,
                    "error": error_messages
                }, 
                status = status
            )
        
        # can't yet do sms messages, accept phone without giving a verification code
        if field == "phone_number":
            status = 200
            log(Log, self, status, LogState.SUCCESS, 
                pre_account_id=pre_account_id)
            return JsonResponse(
                {
                    "success": "recieved",
                    "error": None
                }, 
                status = status
            )

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
        log(Log, self, status, LogState.SUCCESS, 
            pre_account_id=pre_account_id)
        return JsonResponse(
            {
                "success": "recieved",
                "error": None
            }, 
            status = status
        )

    def post(self, request, *args, **kwargs):
        """Given the correct code, extend its lifespan if no password given, 
        and if given the password then update password"""
        serializer = VerificationCodeResponseSerializer(data=request.data)
        validation_error_respose = validate(
            Log, serializer, self, 
            fields_to_correct=[
                "verification_email", "verification_phone_number", "email", 
                "phone_number", "phone_number", "full_name", "brokerage", 
                "symbol", "password", "delete_account", "code"
            ], 
            fields_to_fail=["field", "non_field_errors", "pre_account_id"]
        )
        if validation_error_respose:
            return validation_error_respose
        
        pre_account_id = serializer.validated_data['pre_account_id']
        
        # this endpoint is only for email and phone_number validation
        if serializer.validated_data["field"] not in ["email", "phone_number"]:
            status = 400
            error_messages = {
                "field": "The field parameter must be 'email' or 'phone_number'."
            }
            log(Log, self, status, LogState.VAL_ERR_NO_MESSAGE, 
                errors = error_messages, pre_account_id=pre_account_id)
            return JsonResponse(
                {
                    "success": None,
                    "error": error_messages
                }, 
                status = status
            )
        
        # check if the code has been requested for that field, and if values match
        code = serializer.validated_data['code']
        field = serializer.validated_data['field']
        value = serializer.validated_data[field]
        cached_value = cache.get(f"validate_{field}_{code}")
        if cached_value is None:
            status = 200
            error_messages = {"code": "Code is invalid or expired"}
            log(Log, self, status, LogState.VAL_ERR_MESSAGE, 
                errors = error_messages, pre_account_id=pre_account_id)
            return JsonResponse(
                {
                    "success": None,
                    "error": error_messages
                },
                status = status
            )
        loaded_value = json.loads(cached_value)
        if loaded_value[field] != value:
            status = 200
            error_messages = {"code": "Code is invalid or expired"}
            log(Log, self, status, LogState.VAL_ERR_MESSAGE, 
                errors = error_messages, pre_account_id=pre_account_id)
            return JsonResponse(
                {
                    "success": None,
                    "error": error_messages
                },
                status = status
            )
        
        cache.delete(f"validate_{field}_{code}")

        status = 200
        log(Log, self, status, LogState.SUCCESS, 
            pre_account_id=pre_account_id)
        return JsonResponse(
            {
                "success": "verification code valid",
                "error": None
            },
            status = status
        )

class SetBrokerageInvestment(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # import pdb
        # breakpoint()
        serializer = UserBrokerageInfoSerializer(data=request.data)
        validation_error_respose = validate(
            Log, serializer, self, 
            fields_to_correct=["brokerage", "symbol", "overdraft_protection"],
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
            if "overdraft_protection" in serializer.validated_data:
                userBrokerageInfo.overdraft_protection = serializer.validated_data["overdraft_protection"]
        except:
            if "brokerage" in serializer.validated_data:
                brokerage = serializer.validated_data["brokerage"]
            else:
                brokerage = None
            if "symbol" in serializer.validated_data:
                symbol = serializer.validated_data["symbol"]
            else: 
                symbol = None
            if "overdraft_protection" in serializer.validated_data:
                overdraft_protection = serializer.validated_data["overdraft_protection"]
            else: 
                overdraft_protection = True
            userBrokerageInfo = UserBrokerageInfo(
                user = User.objects.get(id=uid),
                brokerage = brokerage,
                symbol = symbol,
                overdraft_protection = overdraft_protection
            )
        userBrokerageInfo.save()

        status = 200
        log(Log, self, status, LogState.SUCCESS)
        return JsonResponse(
            {
                "success": "recieved", 
                "error": None
            }, 
            status = status
        )


# Plaid

class PlaidUserCreate(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # import pdb
        # breakpoint()
        
        user = self.request.user
        uid = user.id
        if PlaidUser.objects.filter(user__id=uid).count() != 0:
            cache.delete(f"uid_{uid}_plaid_user_create")
            cache.set(
                f"uid_{uid}_plaid_user_create",
                json.dumps({"success": "created", "error": None}),
                timeout=120
            )
            status = 200
            log(Log, self, status, LogState.SUCCESS)
            return JsonResponse(
                {
                    "success": "already exists",
                    "error": None
                }, 
                status = status
            )
    
        cache.delete(f"uid_{uid}_plaid_user_create")
        cache.set(
            f"uid_{uid}_plaid_user_create",
            json.dumps({"success": None, "error": None}),
            timeout=120
        )
        plaid_user_create.apply_async(kwargs={"uid": uid})
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
        task_status = cache.get(f"uid_{uid}_plaid_user_create")
        if task_status:
            status, log_state, errors = cached_task_logging_info(task_status)
            response = json.loads(task_status)
            log(Log, self, status, log_state, errors = errors)
            return JsonResponse(
                response,
                status = status
            )
        else:
            status = 200
            error_message = "no cache value found"
            log(Log, self, status, LogState.BACKGROUND_TASK_NO_CACHE, 
                errors = {"error": error_message})
            return JsonResponse(
                {
                    "success": None,
                    "error": error_message
                }, 
                status = status
            )

class PlaidLinkTokenCreate(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # import pdb
        # breakpoint()

        user_request_serializer = RequestLinkTokenSerializer(data=request.data)
        validation_error_respose = validate(
            Log, user_request_serializer, self, 
            fields_to_fail=["update", "institution_name", "non_field_errors"]
        )
        if validation_error_respose:
            return validation_error_respose
        
        user = self.request.user
        try:
            PlaidUser.objects.get(user__id=user.id)
        except Exception as e:
            if isinstance(e, OperationalError):
                raise e
            status = 400 
            error_message = "This user does not yet have a plaid user object"
            response = JsonResponse(
                {
                    "success": None,
                    "error": error_message
                }, 
                status = status
            )
            log(Log, self, status, LogState.ERR_NO_MESSAGE, 
                errors = {"error": error_message})
            return response
        
        data = {
            "user": {
                "phone_number": user.phone_number,
                "email_address": user.email
            },
            "client_name": "Buul",
            "products": ["transactions"],
            "transactions": {
                "days_requested": 100
            },
            "redirect_uri": f"https://{LOAD_BALANCER_ENDPOINT}/" + "plaid/link/redirect/oauth/",
            "webhook": f"https://{LOAD_BALANCER_ENDPOINT}/" + "api/plaid/itemwebhook/",
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
            error_messages = {}
            for field in e.detail:
                if len(e.detail[field]) >= 1:
                    error_messages[field] = e.detail[field]
            status = 400 
            log(Log, self, status, LogState.ERR_NO_MESSAGE, errors = error_messages)
            return JsonResponse(
                {
                    "success": None,
                    "error": error_messages
                },
                status = status
            )
        # Access the validated data
        validated_data = serializer.validated_data
        uid = user.id
        validated_data['uid'] = uid
        validated_data['update'] = user_request_serializer.validated_data.get('update', False)
        validated_data['institution_name'] = user_request_serializer.validated_data.get('institution_name', None)

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
        task_status = cache.get(f"uid_{uid}_plaid_link_token_create")
        if task_status:
            status, log_state, errors = cached_task_logging_info(task_status)
            log(Log, self, status, log_state, errors = errors)
            return JsonResponse(
                json.loads(task_status),
                status = status
            )
        else:
            status = 400
            error_message = "no cache value found"
            log(Log, self, status, LogState.BACKGROUND_TASK_NO_CACHE, 
                errors = {"error": error_message})
            return JsonResponse(
                {
                    "success": None,
                    "error": error_message
                }, 
                status = status
            )

class PlaidItemWebhook(APIView):
    #make it so that it also takes webhooks for ITEM_REMOVED or needing update flow later
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        user = self.request.user
        uid = user.id
        
        serializer = WebhookSerializer(data=request.data)
        validation_error_respose = validate(
            Log, serializer, self,
            fields_to_fail=["webhook_type", "webhook_code", "environment",
                            "error", "non_field_errors"]
        )
        if validation_error_respose:
            return JsonResponse(
                {
                    "success": None, 
                    "error": "This webhook is not supported"
                }, 
                status = 400
            )
        
        webhook_type = serializer.validated_data["webhook_type"]
        webhook_code = serializer.validated_data["webhook_code"]
        
        if webhook_type == "LINK" and webhook_code == "SESSION_FINISHED":
            serializer = PlaidSessionFinishedSerializer(data=request.data)
            validation_error_respose = validate(
                Log, serializer, self,
                fields_to_fail=["webhook_type", "webhook_code", "item_id",
                                "environment", "status", "link_token", "link_session_id", 
                                "public_tokens", "non_field_errors"]
            )
            if validation_error_respose:
                status = 400
                display_error_message = f"Invalid webhook of type {webhook_type} and code {webhook_code}."
                internal_error_message = f"{display_error_message} causes: " + \
                    f"{json.loads(validation_error_respose.content)["error"]}"
                log(Log, self, status, LogState.ERR_NO_MESSAGE, 
                    errors = internal_error_message
                )
                    # errors = {"error": error_message})
                return JsonResponse(
                    {
                        "success": None, 
                        "error": display_error_message
                    }, 
                    status = status
                )

            link_token = serializer.validated_data["link_token"]
            cached_uid = cache.get(f"link_token_{link_token}_user")
            if cached_uid:
                # maybe change this to be in the db itself... so it cant expire
                # just add link_token to PlaidUser, delete potential duplicates before doing so
                uid = json.loads(cached_uid)["uid"]
            else:
                status = 400
                error_message = f"{webhook_type}, {webhook_code}: corresponding link token and user are no longer cached"
                log(Log, self, status, LogState.ERR_NO_MESSAGE, 
                    errors = {"error": error_message})
                return JsonResponse(
                    {
                        "success": None,
                        "error": error_message
                    }, 
                    status = status
                )

            cache.delete(f"uid_{uid}_plaid_item_public_token_exchange")
            cache.set(
                f"uid_{uid}_plaid_item_public_token_exchange",
                json.dumps({"success": None, "error": None}),
                timeout=120
            )

            if serializer.validated_data['status'] in ["SUCCESS", "success"]:
                plaid_item_public_tokens_exchange.apply_async(
                    kwargs = {
                        "uid": uid,
                        "public_tokens": serializer.validated_data["public_tokens"],
                        "context": {}
                    }
                )

            plaidLinkWebhook = PlaidLinkWebhook(
                event_name = None,
                link_session_id = serializer.validated_data["link_session_id"],
                link_token = link_token,
                request_id = None,
                institution_name = None,
                view_name = None,
                webhook_code = webhook_code,
                exit_status = serializer.validated_data['status'],
                error_code = None,
                error_message = None,
                error_type = None,
                user = User.objects.get(id=uid)
            )
            plaidLinkWebhook.save()

            status = 200
            errors = None
            if serializer.validated_data['status'] not in ["SUCCESS", "success"]:
                errors = {"status": serializer.validated_data['status']} 
            log(Log, self, status, webhook_code, errors=errors)
            return JsonResponse(
                {
                    "success": "recieved", 
                    "error": None
                }, 
                status = status
            )

        elif webhook_type == "TRANSACTIONS" and webhook_code == "SYNC_UPDATES_AVAILABLE":
            serializer = PlaidTransactionSyncUpdatesAvailable(data=request.data)
            validation_error_respose = validate(
                Log, serializer, self,
                fields_to_fail=["webhook_type", "webhook_code", "environment",
                                "item_id", "initial_update_complete",
                                "historical_update_complete", "non_field_errors"]
            )
            if validation_error_respose:
                status = 400
                display_error_message = f"Invalid webhook of type {webhook_type} and code {webhook_code}."
                internal_error_message = f"{display_error_message} caused: " + \
                    f"{json.loads(validation_error_respose.content)["error"]}"
                log(Log, self, status, LogState.ERR_NO_MESSAGE,
                    errors = {"error": internal_error_message})
                return JsonResponse(
                    {
                        "success": None, 
                        "error": display_error_message
                    }, 
                    status = status
                )
            
            item_id = serializer.validated_data["item_id"]

            update_transactions.apply_async(args = [item_id])

            status = 200
            log(Log, self, status, webhook_code)#LogState.SUCCESS)
            return JsonResponse(
                {
                    "success": "recieved", 
                    "error": None
                }, 
                status = status
            )
        
        elif webhook_type == "ITEM" and webhook_code in [
                'WEBHOOK_UPDATE_ACKNOWLEDGED', 'USER_ACCOUNT_REVOKED', 
                'USER_PERMISSION_REVOKED', 'PENDING_EXPIRATION', 'ERROR'
            ]:
            serializer = PlaidItemWebhookSerializer(data=request.data)
            validation_error_respose = validate(
                Log, serializer, self,
                fields_to_fail=["webhook_type", "webhook_code", "item_id",
                                "environment", "non_field_errors"]
            )
            if validation_error_respose:
                status = 400
                display_error_message = f"Invalid webhook of type {webhook_type} and code {webhook_code}."
                internal_error_message = f"{display_error_message} caused: " + \
                    f"{json.loads(validation_error_respose.content)["error"]}"
                log(Log, self, status, LogState.ERR_NO_MESSAGE,
                    errors = {"error": internal_error_message})
                return JsonResponse(
                    {
                        "success": None, 
                        "error": display_error_message
                    }, 
                    status = status
                )
            
            error = serializer.validated_data.get("error", None)
            item_update_code = webhook_code

            if error:
                error_code = error["error_code"]
                if not error_code == "ITEM_LOGIN_REQUIRED":
                    status = 400
                    error_message = f"Invalid webhook of type {webhook_type}, code \
                                {webhook_code}, and error_code {error_code}."
                    log(Log, self, status, LogState.ERR_NO_MESSAGE,
                        errors = {"error": error_message})
                    return JsonResponse(
                        {
                            "success": None, 
                            "error": error_message
                        }, 
                        status = status
                    )
                item_update_code = error_code
            
            if webhook_code == 'LOGIN_REPAIRED':
                item_update_code = None
            
            item_id = serializer.validated_data["item_id"]
            plaid_item = PlaidItem.objects.get(item_id=item_id)
            plaid_item.update_code = item_update_code
            plaid_item.save()

            status = 200
            log(Log, self, status, webhook_code)#LogState.SUCCESS)
            return JsonResponse(
                {
                    "success": "recieved", 
                    "error": None
                }, 
                status = status
            )

        elif webhook_type == "LINK" and webhook_code == "EVENTS":
            serializer = LinkEventWebhookSerializer(data=request.data)
            validation_error_respose = validate(Log, serializer, self, correct_all=True)
            if validation_error_respose:
                status = 400
                display_error_message = f"Invalid webhook of type {webhook_type} and code {webhook_code}."
                internal_error_message = f"{display_error_message} caused: " + \
                    f"{json.loads(validation_error_respose.content)["error"]}"
                log(Log, self, status, LogState.ERR_NO_MESSAGE,
                    errors = {"error": internal_error_message})
                return JsonResponse(
                    {
                        "success": None, 
                        "error": display_error_message
                    }, 
                    status = status
                )
            
            link_token = serializer.validated_data["link_token"]
            cached_uid = cache.get(f"link_token_{link_token}_user")
            if cached_uid:
                # maybe change this to be in the db itself... so it cant expire
                # just add link_token to PlaidUser, delete potential duplicates before doing so
                uid = json.loads(cached_uid)["uid"]
            else:
                status = 400
                error_message = f"{webhook_type}, {webhook_code}: corresponding link token and user are no longer cached"
                log(Log, self, status, LogState.ERR_NO_MESSAGE, 
                    errors = {"error": error_message})
                return JsonResponse(
                    {
                        "success": None,
                        "error": error_message
                    }, 
                    status = status
                )

            
            events = serializer.validated_data["events"]
            for event in events:
                event_id = event.pop("event_id", None)
                metadata = event["event_metadata"]
                user = User.objects.get(id=uid)
                if PlaidLinkWebhook.objects.filter(
                    user=user, event_id=event.get("event_id", None), request_id=metadata["request_id"]
                ).count() == 0:
                    plaidLinkWebhook = PlaidLinkWebhook(
                        user = user,
                        webhook_code = webhook_code,
                        link_session_id = serializer.validated_data["link_session_id"],
                        link_token = serializer.validated_data["link_token"],
                        event_name = event.get("event_name", None),
                        event_id = event_id,
                        request_id = metadata["request_id"],
                        institution_name = metadata.get("institution_name", None),
                        view_name = metadata.get("view_name", None),
                        exit_status = metadata.get("exit_status", None),
                        error_code = metadata.get("error_code", None),
                        error_message = metadata.get("error_message", None),
                        error_type = metadata.get("error_type", None),
                        time_created = event.get("timestamp", None)
                    )
                    plaidLinkWebhook.save()

            status = 200
            log(Log, self, status, webhook_code)
            return JsonResponse(
                {
                    "success": "recieved", 
                    "error": None
                }, 
                status = status
            )
        
        else:
            status = 400
            error_message = f"Invalid webhook of type {webhook_type} and code \
                            {webhook_code}."
            log(Log, self, status, LogState.ERR_NO_MESSAGE,
                errors = error_message)
            return JsonResponse(
                {
                    "success": None, 
                    "error": error_message
                }, 
                status = status
            )
# fetch account info

class PlaidItemsSubmit(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        uid = request.user.id
        match_brokerage_plaid_accounts.apply_async(args = [uid])
        cache.delete(f"uid_{uid}_check_plaid_brokerage_match")
        cache.set(
            f"uid_{uid}_check_plaid_brokerage_match".
            json.dumps({"success": None, "error": None}),
            timeout=120
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
        uid = request.user.id
        task_status = cache.get(f"uid_{uid}_check_plaid_brokerage_match")
        if task_status:
            status, log_state, errors = cached_task_logging_info(task_status)
            log(Log, self, status, log_state, errors = errors)
            return JsonResponse(
                json.loads(task_status), 
                status = status
            )
        else:
            status = 200
            error_message = "no cache value found"
            response = JsonResponse(
                {
                    "success": None, 
                    "error": error_message
                }, 
                status=status
            )
            log(Log, self, status, LogState.BACKGROUND_TASK_NO_CACHE, errors = {"error": error_message})
            return response



class GetUserInfo(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = self.request.user
        try:
            userBrokerageInfo = UserBrokerageInfo.objects.get(user__id=user.id)
            brokerage = userBrokerageInfo.brokerage
            etf = userBrokerageInfo.symbol
            overdraft_protection = userBrokerageInfo.overdraft_protection
            if brokerage == "robinhood":
                brokerage_completed = UserRobinhoodInfo.objects.filter(user=user).exists()
            else:
                brokerage_completed = True
        except Exception as e:
            if isinstance(e, OperationalError):
                raise e
            brokerage, etf, brokerage_completed = None, None, False
        
        status = 200
        log(Log, self, status, LogState.SUCCESS)
        return JsonResponse(
            {
                "full_name": user.full_name,
                "email": user.email,
                "phone_number": user.phone_number,
                "brokerage": brokerage,
                "etf": etf,
                "overdraft_protection": overdraft_protection,
                "brokerage_completed": brokerage_completed,
                "link_completed": PlaidItem.objects.filter(user=user).exists()
            }, 
            status = status
        )

class GetUserInvestmentsInfo(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = self.request.user        
        serializer = GetUserInvestmentsSerializer(data=request.data)
        validation_error_response = validate(
            Log, serializer, self,
            fields_to_fail = ["page", "goals", "non_field_errors"]
        )
        if validation_error_response:
            return validation_error_response
        
        page = serializer.validated_data.get("page", None)
        goals = serializer.validated_data.get("goals", False)

        investments = None
        start_index = None
        count = None
        if page is not None:
            investments_all = Investment.objects.filter(
                user=user, 
                rh__executed_amount__gt=0
            )
            count = investments_all.count()
            start_index = min((count//10)*10, page*10)
            investments_query = investments_all\
                .order_by("-date")\
                .annotate(
                    _symbol=Case(
                        When(symbol="BTC", then=Value("BTC ETF")),
                        When(symbol="btcusd", then=Value("BTC")),
                        default=F("symbol"),
                        output_field=CharField()
                    ),
                    _date=Func(
                        F("date"),
                        function="to_char",
                        template="to_char(%(expressions)s AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"+00:00\"')",
                        output_field=CharField()
                    ),
                    amount=F("rh__executed_amount")
                )\
                [start_index:start_index+10]\
                .values("_symbol", "quantity", "amount", "_date", "_id")
            investments = list(investments_query)
        
        goals = None
        if goals:
            goals = list(UserInvestmentGoal.objects.filter(user=user).values())
        
        status = 200
        log(Log, self, status, LogState.SUCCESS)
        return JsonResponse(
            {
                "success": { 
                    "investments": investments,
                    "page": None if count is None else start_index//10,
                    "max_pages": None if count is None else max(1, math.ceil(count/10)),
                    "goals": goals
                },
                "error": None
            }, 
            status = status
        )

class GetPlaidItems(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = self.request.user
        plaid_items = PlaidItem.objects.filter(user=user)
        institution_names = [i.institution_name for i in plaid_items if i.institution_name]
        
        status = 200
        log(Log, self, status, LogState.SUCCESS)
        return JsonResponse(
            {
                "institution_names": institution_names,
                "error": None
            }, 
            status = status
        )
  

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
        log(Log, self, status, LogState.SUCCESS)
        return JsonResponse(
            {
                "success": "recieved", 
                "error": None
            }, 
            status = status
        )
    
    def post(self, request, *args, **kwargs):
        # import pdb
        # breakpoint()
        serializer = GraphDataRequestSerializer(data=request.data)
        validation_error_response = validate(
            Log, serializer, self, fields_to_correct=["start_date"], 
            fields_to_fail=["non_field_errors"]
        )
        if validation_error_response:
            return validation_error_response

        user = self.request.user
        uid = user.id
        start_date = serializer.validated_data["start_date"]
        task_status = cache.get(f"uid_{uid}_get_investment_graph_data")
        if task_status:
            status, log_state, errors = cached_task_logging_info(task_status)
            if status == 400:
                log(Log, self, status, log_state, errors = errors)
                return JsonResponse(
                    json.loads(task_status), 
                    status = status
                )
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
                status = 200
                log(Log, self, status, LogState.SUCCESS, errors)
                return JsonResponse({"data": data}, status=status)
        else:
            status = 200
            error_message = "no cache value found"
            response = JsonResponse(
                {
                    "success": None, 
                    "error": error_message
                }, 
                status=status
            )
            log(Log, self, status, LogState.BACKGROUND_TASK_NO_CACHE, errors = {"error": error_message})
            return response


# update info

class ResetPassword(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def put(self, request, *args, **kwargs):
        "Get verification code if the email matches an account"

        serializer = VerificationCodeRequestSerializer(data=request.data)
        validation_error_response = validate(
            Log, serializer, self, 
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
            error_message = "The field parameter must be 'password'."
            log(Log, self, status, LogState.VAL_ERR_NO_MESSAGE, 
                errors = {"error": error_message})
            return JsonResponse(
                {
                    "success": None,
                    "error": error_message
                }, 
                status = status
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
                if isinstance(e, OperationalError):
                    raise e
                user = None
                user_exists = False
        elif 'verification_phone_number' in serializer.validated_data:
            email = None
            phone_number = serializer.validated_data['verification_phone_number']
            try: 
                user = User.objects.get(phone_number=phone_number)
                user_exists = True
            except Exception as e:
                if isinstance(e, OperationalError):
                    raise e
                user = None
                user_exists = False
        if not user_exists:
            status = 200
            log(Log, self, status, LogState.SUCCESS)
            return JsonResponse(
                {
                    "success": "recieved",
                    "error": None
                }, 
                status=status
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
        
        status = 200
        log(Log, self, status, LogState.SUCCESS)
        return JsonResponse(
            {
                "success": "recieved",
                "error": None
            }, 
            status=status
        )

    def post(self, request, *args, **kwargs):
        """Given the correct code, extend its lifespan if no password given, 
        and if given the password then update password"""
        serializer = VerificationCodeResponseSerializer(data=request.data)
        validation_error_respose = validate(
            Log, serializer, self, 
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
        
        if serializer.validated_data["field"] != "password":
            status = 400
            error_message = "The field parameter must be 'password'."
            log(Log, self, status, LogState.VAL_ERR_NO_MESSAGE, 
                errors = {"error": error_message})
            return JsonResponse(
                {
                    "success": None,
                    "error": error_message
                }, 
                status = status
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
                if isinstance(e, OperationalError):
                    raise e
                user = None
                user_exists = False
        elif 'verification_phone_number' in serializer.validated_data:
            email = None
            phone_number = serializer.validated_data['verification_phone_number']
            try: 
                user = User.objects.get(phone_number=phone_number)
                user_exists = True
            except Exception as e:
                if isinstance(e, OperationalError):
                    raise e
                user = None
                user_exists = False
        if not user_exists:
            status = 200
            error_messages = {
                "code": "This code is invalid or expired. Request a new one."
            }
            log(Log, self, status, LogState.VAL_ERR_MESSAGE, errors = error_messages)
            return JsonResponse(
                {
                    "success": None,
                    "error": error_messages
                },
                status = status
            )
        
        # check if the code has been requested for that field, and if values match
        code = serializer.validated_data['code']
        field = serializer.validated_data['field']
        value = serializer.validated_data[field]
        cached_value = cache.get(f"signed_out_uid_{user.id}_set_{field}_{code}")
        if cached_value is None:
            status = 200
            error_messages = {
                "code": "This code is invalid or expired. Request a new one."
            }
            log(Log, self, status, LogState.VAL_ERR_MESSAGE, 
                errors = error_messages)
            return JsonResponse(
                {
                    "success": None,
                    "error": error_messages
                },
                status = status
            )
        loaded_value = json.loads(cached_value)
        curr_val = value.encode('utf-8')
        cached_val = loaded_value[field].encode('utf-8')
        if not bcrypt.checkpw(curr_val, cached_val):
            status = 200
            error_messages = {
                "code": "This code is invalid or expired. Request a new one."
            }
            log(Log, self, status, LogState.VAL_ERR_MESSAGE, 
                errors = error_messages)
            return JsonResponse(
                {
                    "success": None,
                    "error": error_messages
                },
                status = status
            )

        user.set_password(serializer.validated_data["password"])
        user.save()

        cache.delete(f"signed_out_uid_{user.id}_set_{field}_{code}")

        status = 200
        log(Log, self, status, LogState.SUCCESS)
        return JsonResponse(
            {
                "success": "verification code valid",
                "error": None
            },
            status = status
        )

class RequestVerificationCode(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, *args, **kwargs):
        "Get verification code if the email matches an account"
        user = request.user

        serializer = VerificationCodeRequestSerializer(data=request.data)
        validation_error_response = validate(
            Log, serializer, self, 
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
                if isinstance(e, OperationalError):
                    raise e
                user_exists = False
        elif 'verification_phone_number' in serializer.validated_data:
            verification_email = None
            verification_phone_number = serializer.validated_data['verification_phone_number']
            try: 
                _ = User.objects.get(phone_number=verification_phone_number)
                user_exists = True
            except Exception as e:
                if isinstance(e, OperationalError):
                    raise e
                user_exists = False
        if not user_exists:
            status = 400
            error_message = "No user is associated with the information given"
            log(Log, self, status, LogState.VAL_ERR_NO_MESSAGE, 
                errors = {"error": error_message})
            return JsonResponse(
                {
                    "success": None,
                    "error": error_message
                }, 
                status = status
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
                if isinstance(e, OperationalError):
                    raise e
                user_exists = False
            if user_exists:
                status = 200
                error_messages = {
                    "email": "This email is already in use."
                }
                log(Log, self, status, LogState.VAL_ERR_MESSAGE, errors = error_messages)
                return JsonResponse(
                    {
                        "success": None,
                        "error": error_messages
                    }, 
                    status = status
                )
        elif 'phone_number' in serializer.validated_data:
            email = None
            phone_number = serializer.validated_data['phone_number']
            try: 
                _ = User.objects.get(phone_number=phone_number)
                user_exists = True
            except Exception as e:
                if isinstance(e, OperationalError):
                    raise e
                user_exists = False
            if user_exists:
                status = 200
                error_messages = {
                    "phone_number": "This number is already in use."
                }
                log(Log, self, status, LogState.VAL_ERR_MESSAGE, errors = error_messages)
                return JsonResponse(
                    {
                        "success": None,
                        "error": error_messages
                    }, 
                    status = status
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
        
        status = 200
        log(Log, self, status, LogState.SUCCESS)
        return JsonResponse(
            {
                "success": "recieved",
                "error": None
            }, 
            status = status
        )

    def post(self, request, *args, **kwargs):
        """Given the correct code, extend its lifespan if no password given, 
        and if given the password then update password"""
        serializer = VerificationCodeResponseSerializer(data=request.data)
        validation_error_respose = validate(
            Log, serializer, self, 
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
            error_messages = {
                "code": "Code is invalid or expired"
            }
            log(Log, self, status, LogState.VAL_ERR_MESSAGE, errors = error_messages)
            return JsonResponse(
                {
                    "success": None,
                    "error": error_messages
                },
                status = status
            )
        loaded_value = json.loads(cached_value)
        if field == "password":
            curr_val = value.encode('utf-8')
            cached_val = loaded_value[field].encode('utf-8')
            if not bcrypt.checkpw(curr_val, cached_val):
                status = 200
                error_messages = {
                    "code": "Code is invalid or expired"
                }
                log(Log, self, status, LogState.VAL_ERR_MESSAGE, errors = error_messages)
                return JsonResponse(
                    {
                        "success": None,
                        "error": error_messages
                    },
                    status = status
                )
        elif loaded_value[field] != value:
            status = 200
            error_messages = {
                "code": "Code is invalid or expired"
            }
            log(Log, self, status, LogState.VAL_ERR_MESSAGE, errors = error_messages)
            return JsonResponse(
                {
                    "success": None,
                    "error": error_messages
                },
                status = status
            )
        
        cache.delete(f"uid_{user.id}_set_{field}_{code}")

        if field == "email":
            email = serializer.validated_data["email"]
            if User.objects.filter(email=email).exists():
                status = 200
                error_messages = {
                    "email": "This email is already being used by another account"
                }
                log(Log, self, status, LogState.VAL_ERR_MESSAGE, errors = error_messages)
                return JsonResponse(
                    {
                        "success": None,
                        "error": error_messages
                    },
                    status = status
                )
            else:
                user.email = email
                user.save()
        elif field == "phone_number":
            phone_number = serializer.validated_data["phone_number"]
            if User.objects.filter(phone_number=phone_number).exists():
                status = 200
                error_messages = {
                    "phone_number": "This number is already being used by another account"
                }
                log(Log, self, status, LogState.VAL_ERR_MESSAGE, errors = error_messages)
                return JsonResponse(
                    {
                        "success": None,
                        "error": error_messages
                    },
                    status = status
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
                userBrokerageInfo.brokerage = serializer.validated_data["brokerage"]
                userBrokerageInfo.save()
            except Exception as e:
                if isinstance(e, OperationalError):
                    raise e
                status = 200
                error_message = "We could not find your brokerage and investment choice. Please contact Buul."
                log(Log, self, status, LogState.VAL_ERR_MESSAGE, errors = {"error": error_message})
                return JsonResponse(
                    {
                        "success": None,
                        "error": error_message
                    },
                    status = status
                )
        elif field == "symbol":
            try: 
                userBrokerageInfo = UserBrokerageInfo.objects.get(user=user)
                userBrokerageInfo.symbol = serializer.validated_data["symbol"]
                userBrokerageInfo.save()
            except Exception as e:
                if isinstance(e, OperationalError):
                    raise e
                status = 200
                error_message = "We could not find your brokerage and investment choice. Please contact Buul."
                log(Log, self, status, LogState.VAL_ERR_MESSAGE, errors = {"error": error_message})
                return JsonResponse(
                    {
                        "success": None,
                        "error": error_message
                    },
                    status = status
                )
        elif field == "password":
            user.set_password(serializer.validated_data["password"])
            user.save()
        elif field == "delete_account":
            cache.delete(f"code_{code}_buul_user_remove")
            cache.set(
                f"code_{code}_buul_user_remove",
                json.dumps({"success": None, "error": None}),
                timeout=120
            )
            chord(
                [
                    plaid_user_remove.s(user.id, code)
                ],
                buul_user_remove.s(user.id, code)
            ).apply_async()
        else:
            status = 200
            error_message = "The field parameter must be one of 'password', " + \
                            "'email', 'phone_number', 'full_name', 'brokerage', " + \
                            "or 'symbol'."
            log(Log, self, status, LogState.VAL_ERR_MESSAGE, errors = {"error": error_message})
            return JsonResponse(
                {
                    "success": None,
                    "error": error_message
                },
                status = status
            )

        status = 200
        log(Log, self, status, LogState.SUCCESS)
        return JsonResponse(
            {
                "success": "verification code valid",
                "error": None
            },
            status = status
        )

class SendEmail(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = SendEmailSerializer(data=request.data)
        validation_error_message = validate(Log, serializer, self, 
                                            fields_to_correct=["email"])
        if validation_error_message:
            return validation_error_message

        email = serializer.validated_data["email"]
        try:
            user = User.objects.get(email=email)
            send_forgot_email.apply_async(
                kwargs = {
                    "useEmail": True, 
                    "sendTo": serializer.validated_data["email"],
                }
            )
        except:
            user = None
            
        status = 200
        log(Log, self, status, LogState.SUCCESS, user = user)
        return JsonResponse(
            {
                "success": "email sent", 
                "error": None
            }, 
            status = status
        )

class DeleteAccountVerify(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        serializer = DeleteAccountVerifySerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            code = serializer.validated_data["code"]
            cached_result = cache.get(f"code_{code}_buul_user_remove")
            if cached_result:
                status = 200
                log(Log, self, status, LogState.SUCCESS)
                return JsonResponse(
                    json.loads(cached_result),
                    status = status
                )
            else:
                status = 400
                error_message = "no cached value found for that code"
                log(Log, self, status, LogState.BACKGROUND_TASK_NO_CACHE,
                    errors = {"error": error_message})
                return JsonResponse(
                    {
                        "success": None,
                        "error": error_message
                    },
                    status = status
                )
        except Exception as e:
            if isinstance(e, OperationalError):
                raise e
            status = 400
            log(Log, self, status, LogState.VAL_ERR_MESSAGE)
            return JsonResponse(
                {
                    "success": None,
                    "error": f"error: {str(e)}"
                },
                status = status
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
            status = 200
            log(Log, self, status, LogState.SUCCESS)
            return JsonResponse(
                {
                    "success": "email added"
                }, 
                status = status
            )
        except Exception as e:
            if isinstance(e, OperationalError):
                raise e
            status = 400
            error_messages = {"error": e.args[0]}
            log(Log, self, status, LogState.VAL_ERR_NO_MESSAGE, errors = error_messages)
            return JsonResponse( 
                error_messages,
                status = status
            )

class GetSpendingRecommendations(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        "Get verification code if the email matches an account"
        user = request.user
        try:
            result = {}
            spending_by_category = PlaidPersonalFinanceCategories.get(user=user)
            total_amount = 0
            for field in PlaidPersonalFinanceCategories._meta.get_fields():
                if field.name in [    
                    'entertainment', 'food_and_drink', 
                    'home_improvement', 'personal_care', 'transportation', 
                    'travel', 'rent_and_utilities'
                ]:
                    result[field.name] = spending_by_category[field.name]
                if field.name in ['start_date', 'end_date']:
                    result[field.name] = spending_by_category[field.name].isoformat()
                else:
                    total_amount += spending_by_category[field.name].isoformat()
            result["total_amount"] = total_amount
                    

            status = 200
            log(Log, self, status, LogState.SUCCESS)
            return JsonResponse( 
                {
                    "success": result,
                    "error": None
                },
                status = status
            )
        except:
            status = 400
            log(Log, self, status, LogState.ERR_NO_MESSAGE)
            return JsonResponse( 
                {
                    "success": None,
                    "error": "not yet calculated"
                },
                status = status
            )