from celery import shared_task
from django.core.cache import cache 
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django_celery_results.models import TaskResult

from api.apis.plaid import plaid_client
from api.apis.sendgrid import sendgrid_client
from sendgrid.helpers.mail import Mail
from accumate_backend.settings import NOTIFICATIONS_EMAIL

import re
import json
import uuid

from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.item_get_request import ItemGetRequest
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.user_create_request import UserCreateRequest
from plaid.model.user_remove_request import UserRemoveRequest
from plaid.exceptions import ApiException
from rest_framework.exceptions import ValidationError

from plaid.model.item_access_token_invalidate_request import ItemAccessTokenInvalidateRequest

from ..serializers.plaid.item import ItemPublicTokenExchangeResponseSerializer, \
    ItemRemoveResponseSerializer, ItemAccessTokenInvalidateResponseSerializer, \
    ItemGetResponseSerializer
from ..serializers.plaid.link import LinkTokenCreateResponseSerializer
from ..serializers.plaid.user import UserRemoveResponseSerializer, \
    UserCreateResponseSerializer
from ..models import PlaidItem, PlaidUser, User

from accumate_backend.retry_db import retry_on_db_error

from django.db.utils import OperationalError


# user and plaid management

@shared_task(name="plaid_item_public_tokens_exchange")
@retry_on_db_error
def plaid_item_public_tokens_exchange(**kwargs):
    # import pdb
    # breakpoint()
    uid = kwargs.pop('uid')
    public_tokens = kwargs.pop('public_tokens')
    context = kwargs.pop('context')
    
    try:
        plaidUser = PlaidUser.objects.get(user__id=uid) # make sure we have a user
        item_get_error_messages = {}
        item_remove_error_messages = {}
        for public_token in public_tokens:
            exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)

            exchange_response = plaid_client.item_public_token_exchange(exchange_request)
            serializer = ItemPublicTokenExchangeResponseSerializer(data={
                "access_token": exchange_response.access_token, 
                "item_id": exchange_response.item_id, 
                "request_id": exchange_response.request_id
            })
            serializer.is_valid(raise_exception=True)
            validated_data = serializer.validated_data

            plaidUser = PlaidUser.objects.get(user__id=uid) # make sure we have a user

            plaidItem = PlaidItem(user=plaidUser.user)
            plaidItem.accessToken = serializer.validated_data["access_token"]
            plaidItem.itemId = validated_data['item_id']
            plaidItem.save()

            # get new item's institution
            item_get_result = plaid_item_get(
                uid=uid,
                item_ids=[validated_data['item_id']]
            )
            if item_get_result['error']:
                item_get_error_messages[validated_data['item_id']] = item_get_result['error']
            else:
                plaidItem.institution_name = item_get_result["success"]["institution_name"]
                plaidItem.institution_id = item_get_result["success"]["institution_id"]
                plaidItem.save()

                # if got institution, delete duplicates of institution
                duplicate_institutions = PlaidItem.objects.filter(
                    user__id=uid, 
                    institution_id=plaidItem.institution_id
                ).exclude(itemId=plaidItem.itemId)
                for item in duplicate_institutions:
                    item_remove_result = plaid_item_remove(uid, item.itemId)
                    if item_remove_result['error']:
                        item_remove_error_messages[validated_data['item_id']] = item_remove_result['error']
                    else:
                        item.delete()

        plaidUser.link_token = None
        plaidUser.save()
        cache.delete(f"uid_{uid}_plaid_item_public_token_exchange")
        cache.set(
            f"uid_{uid}_plaid_item_public_token_exchange",
            json.dumps({"success": "recieved", "error": None}), 
            timeout=120
        )

        if item_get_error_messages or item_remove_error_messages:
            return f"cached plaid public token exchange success but " + \
                "item_get failures: {item_get_error_messages} + " \
                "item_remove failures: {item_remove_error_messages}"
        else:
            return "cached plaid public token exchange success"
    except ApiException as e:
        error = json.loads(e.body)
        cache.delete(f"uid_{uid}_plaid_item_public_token_exchange")
        cache.set(
            f"uid_{uid}_plaid_item_public_token_exchange",
            json.dumps({"success": None, "error": f"{e.status}: {str(e)}"}), 
            timeout=120
        )
        return f"cached plaid public token exchange ApiException: {error.get("error_code")}"
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        cache.delete(f"uid_{uid}_plaid_item_public_token_exchange")
        cache.set(
            f"uid_{uid}_plaid_item_public_token_exchange",
            json.dumps({"success": None, "error": "error: " + str(e)}), 
            timeout=120
        )
        return f"cached plaid public token exchange error: {str(e)}"

# @shared_task(name="plaid_item_get")
@retry_on_db_error
def plaid_item_get(**kwargs):
    # import pdb
    # breakpoint()
    uid = kwargs.pop('uid')
    item_ids = kwargs.pop('item_ids')

    try:
        for item_id in item_ids:
            plaid_item = PlaidItem.objects.get(user__id=uid, itemId=item_id)
            exchange_request = ItemGetRequest(access_token = plaid_item.accessToken)
            exchange_response = plaid_client.item_get(exchange_request)
            serializer = ItemGetResponseSerializer(
                data=exchange_response.to_dict()
            )
            serializer.is_valid(raise_exception=True)
            return {
                "error": None,
                "success": {
                    "institution_id": serializer.validated_data["item"]["institution_id"],
                    "institution_name": serializer.validated_data["item"]["institution_name"]
                }
            }
            # return f"{serializer.validated_data["item"]["institution_name"]}, {serializer.validated_data["item"]["institution_id"]}"
    except ApiException as e:
        error = json.loads(e.body)
        return {
            "error": f"item get error: {error.get("error_code")}",
            "success": None
        }
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        return {
            "error": f"item get error: {str(e)}",
            "success": None
        }


@shared_task(name="plaid_link_token_create")
@retry_on_db_error
def plaid_link_token_create(**kwargs):
    # import pdb
    # breakpoint()

    uid = kwargs.pop('uid')
    try:
        plaidUser = PlaidUser.objects.get(user__id=uid)
        exchange_request = {
            "client_name": kwargs["client_name"],
            "language": kwargs['language'],
            "country_codes": [code for code in kwargs["country_codes"]], 
            "user": {
                "client_user_id": plaidUser.clientUserId,  
                "phone_number": kwargs['user']['phone_number'],
                "email_address": kwargs['user']['email_address']
            },
            "user_token": plaidUser.userToken,
            "products": [val for val in kwargs['products']], 
            "transactions": {"days_requested": 100},
            "enable_multi_item_link": True,
            "redirect_uri": kwargs['redirect_uri'], 
            "webhook": kwargs["webhook"],
            "account_filters": {
                "depository": { "account_subtypes": ["checking", "savings"] },
                "credit": { "account_subtypes": ["credit card"] }
            }
        }

        if kwargs.get("update", False):
            items = PlaidItem.objects.filter(
                user__id=uid, 
                institution_name=kwargs["institution_name"]
            )
            if items.exists():
                item = items.first()
                items.exclude(itemId=item.itemId).delete()
                exchange_request['update'] = {
                    # 'user': True,
                    'account_selection_enabled': True,
                    # 'item_ids': [item.itemId]
                }
                # exchange_request.pop('user_token')
                exchange_request['enable_multi_item_link'] = False
                exchange_request['access_token'] = item.accessToken
            else:
                cache.delete(f"uid_{uid}_plaid_link_token_create")
                cache.set(
                    f"uid_{uid}_plaid_link_token_create",
                    json.dumps({
                        "success": None, 
                        "error": "We could not find a connection between " + \
                            "you and this institution to update. Please create " + \
                            "a new connection or contact Buul."
                    }), 
                    timeout=120
                )
                return "could not find matching plaid item to update"

        
        exchange_response = plaid_client.link_token_create(exchange_request)
        serializer = LinkTokenCreateResponseSerializer(data={
            "link_token": exchange_response.link_token, 
            "expiration": exchange_response.expiration, 
            "request_id": exchange_response.request_id
        })
        serializer.is_valid(raise_exception=True)

        link_token = serializer.validated_data["link_token"]
        cache.delete(f"link_token_{link_token}_user")
        cache.set(
            f"link_token_{link_token}_user",
            json.dumps({"uid":str(uid)}),
            timeout=3600
        )

        cache.delete(f"uid_{uid}_plaid_link_token_create")
        cache.set(
            f"uid_{uid}_plaid_link_token_create",
            json.dumps({
                "success": serializer.validated_data["link_token"], 
                "error": None
            }), 
            timeout=120
        )
        return "cached plaid link token create success"
    except ApiException as e:
        error = json.loads(e.body)
        cache.delete(f"uid_{uid}_plaid_link_token_create")
        cache.set(
            f"uid_{uid}_plaid_link_token_create",
            json.dumps({
                "success": None, 
                "error": f"{e.status}: {str(e)}"
            }), 
            timeout=120
        )
        return f"cached plaid link token create ApiException error: {error.get("error_code")}"
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        cache.delete(f"uid_{uid}_plaid_link_token_create")
        cache.set(
            f"uid_{uid}_plaid_link_token_create",
            json.dumps({
                "success": None, 
                "error": "error: " + str(e)
            }), 
            timeout=120
        )
        return f"cached plaid link token create error: {str(e)}"

@shared_task(name="plaid_item_remove")
@retry_on_db_error
def plaid_item_remove(uid, item_id):
    # import pdb
    # breakpoint()
    try:
        plaidItem = PlaidItem.objects.get(user__id=uid, itemId=item_id)
        exchange_request = ItemRemoveRequest(access_token = plaidItem.accessToken)
        exchange_response = plaid_client.item_remove(exchange_request)
        serializer = ItemRemoveResponseSerializer(
            data=exchange_response.to_dict()
        )
        serializer.is_valid(raise_exception=True)
        plaidItem.delete()
        return {
            "error": None,
            "success": serializer.validated_data
        }
    except ApiException as e:
        error = json.loads(e.body)
        return {
            "error": f"item remove error: {error.get("error_code")}",
            "success": None
        }
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        return {
            "error": f"item remove error: {str(e)}",
            "success": None
        }

@shared_task(name="plaid_user_create")
@retry_on_db_error
def plaid_user_create(**kwargs):
    # import pdb
    # breakpoint()

    uid = kwargs.pop('uid')
    
    try:
        duplicate_client_id_count = float('inf')
        while duplicate_client_id_count > 0:
            client_user_id = str(uuid.uuid4())
            duplicates = PlaidUser.objects.filter(clientUserId=client_user_id)
            duplicate_client_id_count = duplicates.count()

        exchange_request = UserCreateRequest(
            client_user_id = client_user_id
        )

        exchange_response = plaid_client.user_create(exchange_request)
        serializer = UserCreateResponseSerializer(
            data=exchange_response.to_dict()
        )
        serializer.is_valid(raise_exception=True)

        plaidUser = PlaidUser(user=User.objects.get(id=uid))
        plaidUser.clientUserId = client_user_id
        plaidUser.userId = serializer.validated_data['user_id']
        plaidUser.userToken = serializer.validated_data['user_token']
        plaidUser.save()

        cache.delete(f"uid_{uid}_plaid_user_create")
        cache.set(
            f"uid_{uid}_plaid_user_create",
            json.dumps({
                "success": "success", 
                "error": None
            }), 
            timeout=120
        )
        return "cached plaid user create success"
    except ApiException as e:
        error = json.loads(e.body)
        cache.delete(f"uid_{uid}_plaid_user_create")
        cache.set(
            f"uid_{uid}_plaid_user_create",
            json.dumps({"success": None, "error": str(type(e))}), 
            timeout=120
        )
        return f"cached plaid user create error: {error.get("error_code")}"
    # except Exception as e:
        # if isinstance(e, OperationalError):
        #     raise e
    #     cache.delete(f"uid_{uid}_plaid_user_create")
    #     cache.set(
    #         f"uid_{uid}_plaid_user_create",
    #         json.dumps({"success": None, "error": str(type(e))}), 
    #         timeout=120
    #     )
    #     return f"cached plaid user create error: {str(e)}"

@shared_task(name="plaid_user_remove")
@retry_on_db_error
def plaid_user_remove(uid, code):
    # import pdb
    # breakpoint()
    
    try:
        plaidUser = PlaidUser.objects.get(user__id=uid)
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        cache.delete(f"code_{code}_plaid_user_remove")
        cache.set(
            f"code_{code}_plaid_user_remove",
            json.dumps({"success": "Plaid user did not exist", "error": None}), 
            timeout=120
        )
        return f"cached plaid user remove success"
    
    exchange_request = UserRemoveRequest(
        user_token = plaidUser.userToken
    )

    try:
        exchange_response = plaid_client.user_remove(exchange_request)
        serializer = UserRemoveResponseSerializer(
            data=exchange_response.to_dict()
        )
        serializer.is_valid(raise_exception=True)

        plaidUser.delete()
        cache.delete(f"code_{code}_plaid_user_remove")
        cache.set(
            f"code_{code}_plaid_user_remove", 
            json.dumps({
                "success": "plaid user deleted", 
                "error": None
            }), 
            timeout=120
        )
        return "cached plaid user remove success"
    except ApiException as e:
        if e.body["error_type"] == "INVALID_INPUT" and e.body["error_code"] == "INVALID_USER_TOKEN":
            cache.delete(f"code_{code}_plaid_user_remove")
            cache.set(
                f"code_{code}_plaid_user_remove",
                json.dumps({"success": "Plaid user did not exist", "error": None}), 
                timeout=120
            )
            plaidUser.delete()
            return f"cached plaid user remove success"
        else:
            cache.delete(f"code_{code}_plaid_user_remove")
            cache.set(
                f"code_{code}_plaid_user_remove",
                json.dumps({"success": None, "error": f"error: {str(e.body)}"}), 
                timeout=120
            )
            return f"cached plaid user remove error: {str(e.body)}"
    except ValidationError as e:
        cache.delete(f"code_{code}_plaid_user_remove")
        cache.set(
            f"code_{code}_plaid_user_remove",
            json.dumps({"success": None, "error": f"error: {str(e.detail)}"}), 
            timeout=120
        )
        return f"cached plaid user remove error: {str(e.detail)}"

@shared_task(name="accumate_user_remove")
@retry_on_db_error
def accumate_user_remove(uid, code, ignore_plaid_delete=False):
    # import pdb
    # breakpoint()

    if not ignore_plaid_delete:
        cached_plaid_user_delete = cache.get(f"code_{code}_plaid_user_remove")
        if not cached_plaid_user_delete:
            cache.delete(f"code_{code}_accumate_user_remove")
            cache.set(
                f"code_{code}_accumate_user_remove",
                json.dumps({"success": None, "error": "plaid user not yet deleted"}), 
                timeout=120
            )
            return f"accumate user not deleted because plaid user not yet deleted"
        
        plaid_user_delete_dict = json.loads(cached_plaid_user_delete)
        if not plaid_user_delete_dict["success"]:
            cache.delete(f"code_{code}_accumate_user_remove")
            cache.set(
                f"code_{code}_accumate_user_remove",
                json.dumps({"success": None, "error": "plaid user not yet deleted"}), 
                timeout=120
            )
            return f"accumate user not deleted because plaid user not yet deleted"

    try:
        User.objects.get(id=uid).delete()

        cache.delete(f"code_{code}_accumate_user_remove")
        cache.set(
            f"code_{code}_accumate_user_remove",
            json.dumps({
                "success": "user deleted",
                "error": None
            }),
            timeout=120
        )
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        # import pdb 
        # breakpoint()
        cache.delete(f"code_{code}_accumate_user_remove")
        cache.set(
            f"code_{code}_accumate_user_remove",
            json.dumps({"success": None, "error": str(e)}), 
            timeout=120
        )
        return f"cached accumate user remove error: {str(e)}"



# send notifications

@shared_task(name="send_verification_code")
@retry_on_db_error
def send_verification_code(**kwargs):
    if kwargs["useEmail"]:
        message = Mail(
            from_email=NOTIFICATIONS_EMAIL,
            to_emails=kwargs["sendTo"],
            subject="Buul verification code",
            html_content=f"Enter this code in the Buul app to verify your identity: {kwargs["code"]}.\nIf you didn't request this code, please ignore this email.",
        )
        try:
            response = sendgrid_client.send(message)
            return response.status_code
        except Exception as e:
            if isinstance(e, OperationalError):
                raise e
            return f"error: {str(e)}"
        # send_mail(
        #     "Accumate verification code",
        #     f"Enter this code in the Accumate app to verify your identity: {kwargs["code"]}.\nIf you didn't request this code, please ignore this email.",
        #     "accumate-verify@accumatewealth.com",
        #     [kwargs["sendTo"]],
        #     fail_silently=False,
        # )
    else:
        return
        # twilio_client.messages.create(
        #     to = kwargs["sendTo"],
        #     from_ = TWILIO_PHONE_NUMBER,
        #     body = f"Enter this code in the Accumate app to verify your identity: {kwargs["code"]}"
        # )

@shared_task(name="send_forgot_email")
@retry_on_db_error
def send_forgot_email(**kwargs):
    if kwargs["useEmail"]:
        message = Mail(
            from_email=NOTIFICATIONS_EMAIL,
            to_emails=kwargs["sendTo"],
            subject="Buul Email Verification",
            html_content=f"We were asked to send an email to this address to remind you that " + \
                "you have an Buul account registered with this email. \nIf you " + \
                "didn't request this email, please ignore this.",
        )
        try:
            response = sendgrid_client.send(message)
            return response.status_code
        except Exception as e:
            if isinstance(e, OperationalError):
                raise e
            return f"error: {str(e)}"
    else:
        return
        # twilio_client.messages.create(
        #     to = kwargs["sendTo"],
        #     from_ = TWILIO_PHONE_NUMBER,
        #     body = f"Enter this code in the Accumate app to verify your identity: {kwargs["code"]}"
        # )

@shared_task(name="send_waitlist_email")
@retry_on_db_error
def send_waitlist_email(**kwargs):
    if kwargs["useEmail"]:
        message = Mail(
            from_email=NOTIFICATIONS_EMAIL,
            to_emails=kwargs["sendTo"],
            subject="You're on the Buul waitlist!",
            html_content=f"We look forward to working with you to maximize your cashback " \
                "and grow your wealth! Stay tuned for updates. \nIf you would like " \
                "to unsubscribe, respond to this email address requesting to be taken " \
                "off. \n\nThank you, \nthe Accumate team",
        )
        try:
            response = sendgrid_client.send(message)
            return response.status_code
        except Exception as e:
            if isinstance(e, OperationalError):
                raise e
            return f"error: {str(e)}"
    else:
        return
        # twilio_client.messages.create(
        #     to = kwargs["sendTo"],
        #     from_ = TWILIO_PHONE_NUMBER,
        #     body = f"Enter this code in the Accumate app to verify your identity: {kwargs["code"]}"
        # )



# refresh plaid tokens

@shared_task(name="plaid_access_token_refresh")
@retry_on_db_error
def plaid_access_token_refresh(plaid_item_id):
    # import pdb
    # breakpoint()
    #ApiException, ValidationError
    plaidItem = PlaidItem.objects.get(id=plaid_item_id)
    request = ItemAccessTokenInvalidateRequest(plaidItem.accessToken)
    exchange_response = plaid_client.item_access_token_invalidate(request)
    serializer = ItemAccessTokenInvalidateResponseSerializer(
        data=exchange_response.to_dict()
    )
    serializer.is_valid(raise_exception=True)
    plaidItem.accessToken = serializer.validated_data["new_access_token"]
    plaidItem.previousRefresh = timezone.now()
    plaidItem.previousRefreshSuccess = True
    plaidItem.save()

@shared_task(name="plaid_access_token_refresh_all")
@retry_on_db_error
def plaid_access_token_refresh_all():
    plaidItems = PlaidItem.objects.filter(
        previousRefresh__lt=timezone.now() - relativedelta(days=3)
    )
    try:
        i = 0
        for plaidItem in plaidItems:
            plaid_access_token_refresh(plaidItem.id)
            i += 1
        return f"all remaining {i} tokens rotated"
    except ApiException as e:
        if e.error_code == "ITEM_ACCESS_TOKEN_INVALIDATE_LIMIT" and e.status == 429:
            return f"rate limit exceeded, {i} tokens rotated"
        else:
            raise e


# censor celery task result logs

@retry_on_db_error
def format_task_result_kwargs(text):
    # Regular expression to match `'uid': UUID('<uuid>')`

    formatted_text = text.strip().strip('\'').strip('"')\
        .replace('\'', '"')\
        .replace('True', '"true"').replace('False', '"false"')\
        .replace('None', '"null"')
    
    uuid_pattern = re.compile(r'"uid": UUID\("([a-f0-9\-]+)"\)(, )?')
    match = uuid_pattern.search(formatted_text)
    if match:
        extracted_uuid = match.group(1)
        cleaned_text = uuid_pattern.sub("", formatted_text)
    else:
        extracted_uuid = None
        cleaned_text = text

    return extracted_uuid, cleaned_text

@receiver(pre_save, sender=TaskResult)
@retry_on_db_error
def modify_task_result(sender, instance, **kwargs):
    """ Nullify task_args and task_kwargs before saving """

    if instance.task_name != "login_robinhood":
        return

    sensitive_keys = ["password", "username"]

    try:
        uuid, formatted_task_kwargs_str = format_task_result_kwargs(instance.task_kwargs)
        task_kwargs = json.loads(formatted_task_kwargs_str)
        for key in sensitive_keys:
            if key in task_kwargs:
                task_kwargs[key] = "****"
        instance.task_kwargs = f'{{"uid": UUID(\'{uuid}\'), ' + json.dumps(task_kwargs)[1:]
    except:
        instance.task_kwargs = instance.task_kwargs

    try:
        uuid, formatted_task_args_str = format_task_result_kwargs(instance.task_args)
        task_args = json.loads(formatted_task_args_str)
        for key in sensitive_keys:
            if key in task_args:
                task_args[key] = "****"
        instance.task_args = f'{{"uid": UUID({uuid}), ' + json.dumps(task_args)[1:]
    except:
        instance.task_args = instance.task_args








