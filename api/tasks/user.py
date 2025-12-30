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
from buul_backend.settings import NOTIFICATIONS_EMAIL

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

from buul_backend.retry_db import retry_on_db_error

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
            existing_connections_to_institution = PlaidItem.objects.filter(
                user__id=uid, 
                institution_id=plaidItem.institution_id
            )
            if existing_connections_to_institution.count() > 1:
                continue

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

        plaidUser.link_token = None
        plaidUser.save()
        cache.delete(f"uid_{uid}_plaid_item_public_token_exchange")
        cache.set(
            f"uid_{uid}_plaid_item_public_token_exchange",
            json.dumps({"success": "recieved", "error": None}), 
            timeout=120
        )

        if item_get_error_messages:
            return f"cached plaid public token exchange success but " + \
                "item_get failures: {item_get_error_messages}"
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
        # cache.delete(f"code_{code}_plaid_user_remove")
        # cache.set(
        #     f"code_{code}_plaid_user_remove",
        #     json.dumps({"success": "Plaid user did not exist", "error": None}), 
        #     timeout=120
        # )
        # return f"cached plaid user remove success"
        True
    
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
        # cache.delete(f"code_{code}_plaid_user_remove")
        # cache.set(
        #     f"code_{code}_plaid_user_remove", 
        #     json.dumps({
        #         "success": "plaid user deleted", 
        #         "error": None
        #     }), 
        #     timeout=120
        # )
        # return "cached plaid user remove success"
        return True
    except ApiException as e:
        if e.body["error_type"] == "INVALID_INPUT" and e.body["error_code"] == "INVALID_USER_TOKEN":
            # cache.delete(f"code_{code}_plaid_user_remove")
            # cache.set(
            #     f"code_{code}_plaid_user_remove",
            #     json.dumps({"success": "Plaid user did not exist", "error": None}), 
            #     timeout=120
            # )
            plaidUser.delete()
            # return f"cached plaid user remove success"
            return True
            # cache.delete(f"code_{code}_plaid_user_remove")
            # cache.set(
            #     f"code_{code}_plaid_user_remove",
            #     json.dumps({"success": None, "error": f"error: {str(e.body)}"}), 
            #     timeout=120
            # )
            # return f"cached plaid user remove error: {str(e.body)}"
            # return False
    except ValidationError as e:
        # cache.delete(f"code_{code}_plaid_user_remove")
        # cache.set(
        #     f"code_{code}_plaid_user_remove",
        #     json.dumps({"success": None, "error": f"error: {str(e.detail)}"}), 
        #     timeout=120
        # )
        return f"cached plaid user remove error: {str(e.detail)}"
        # return False

@shared_task(name="buul_user_remove")
def buul_user_remove(results_from_dependencies, uid, code, ignore_dependencies=False):
    # import pdb
    # breakpoint()

    if not ignore_dependencies and not all(results_from_dependencies):
        failed_dependencies_str = " and ".join([
            ["plaid"][i] for i in len(range(results_from_dependencies)) \
            if results_from_dependencies[i] == True
        ])
        cache.delete(f"code_{code}_buul_user_remove")
        cache.set(
            f"code_{code}_buul_user_remove",
            json.dumps({"success": None, "error": f"{failed_dependencies_str} user not yet deleted"}), 
            timeout=120
        )
        return f"buul user not deleted because {failed_dependencies_str} user not yet deleted"

        # for dependency in ["plaid", "snaptrade"]:
        #     cached = cache.get(f"code_{code}_{dependency}_user_remove")
        #     if not cached:
        #         cache.delete(f"code_{code}_buul_user_remove")
        #         cache.set(
        #             f"code_{code}_buul_user_remove",
        #             json.dumps({"success": None, "error": f"{dependency} user not yet deleted"}), 
        #             timeout=120
        #         )
        #         return f"buul user not deleted because {dependency} user not yet deleted"
        
        #     cached_dict = json.loads(cached)
        #     if not cached_dict["success"]:
                # cache.delete(f"code_{code}_buul_user_remove")
                # cache.set(
                #     f"code_{code}_buul_user_remove",
                #     json.dumps({"success": None, "error": f"{dependency} user not yet deleted"}), 
                #     timeout=120
                # )
                # return f"buul user not deleted because {dependency} user not yet deleted"

    try:
        User.objects.get(id=uid).delete()

        cache.delete(f"code_{code}_buul_user_remove")
        cache.set(
            f"code_{code}_buul_user_remove",
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
        cache.delete(f"code_{code}_buul_user_remove")
        cache.set(
            f"code_{code}_buul_user_remove",
            json.dumps({"success": None, "error": str(e)}), 
            timeout=120
        )
        return f"cached buul user remove error: {str(e)}"



# send notifications

from django.core.mail import EmailMultiAlternatives
from django.conf import settings

def send_email(subject: str, to_email: str, text_body: str, html_body: str | None = None):
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    if html_body:
        msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)

@shared_task(name="send_verification_code")
@retry_on_db_error
def send_verification_code(**kwargs):
    if not kwargs.get("useEmail"):
        return

    code = kwargs["code"]
    to_email = kwargs["sendTo"]

    subject = "Buul verification code"

    text_body = (
        f"Enter this code in the Buul app to verify your identity: {code}.\n\n"
        "If you didn't request this code, please ignore this email."
    )

    html_body = (
        f"<p>Enter this code in the Buul app to verify your identity:</p>"
        f"<h2>{code}</h2>"
        "<p>If you didn't request this code, please ignore this email.</p>"
    )

    try:
        send_email(subject, to_email, text_body, html_body)
        return 200
    except Exception as e:
        if isinstance(e, OperationalError):
            raise
        return f"error: {str(e)}"


@shared_task(name="send_forgot_email")
@retry_on_db_error
def send_forgot_email(**kwargs):
    if not kwargs.get("useEmail"):
        return

    to_email = kwargs["sendTo"]

    subject = "Buul account reminder"

    text_body = (
        "We were asked to send an email to this address to remind you that "
        "you have a Buul account registered with this email.\n\n"
        "If you didn't request this email, please ignore it."
    )

    html_body = (
        "<p>We were asked to send an email to this address to remind you that "
        "<strong>you have a Buul account</strong> registered with this email.</p>"
        "<p>If you didn't request this email, please ignore it.</p>"
    )

    try:
        send_email(subject, to_email, text_body, html_body)
        return 200
    except Exception as e:
        if isinstance(e, OperationalError):
            raise
        return f"error: {str(e)}"


@shared_task(name="send_waitlist_email")
@retry_on_db_error
def send_waitlist_email(**kwargs):
    if not kwargs.get("useEmail"):
        return

    to_email = kwargs["sendTo"]

    subject = "You're on the Buul waitlist!"

    text_body = (
        "We look forward to working with you to maximize your cashback "
        "and grow your wealth! Stay tuned for updates.\n\n"
        "If you would like to unsubscribe, reply to this email requesting "
        "to be taken off the waitlist.\n\n"
        "Thank you,\n"
        "The Buul Team"
    )

    html_body = (
        "<p>We look forward to working with you to maximize your cashback "
        "and grow your wealth! Stay tuned for updates.</p>"
        "<p>If you would like to unsubscribe, reply to this email requesting "
        "to be taken off the waitlist.</p>"
        "<p>Thank you,<br><strong>The Buul Team</strong></p>"
    )

    try:
        send_email(subject, to_email, text_body, html_body)
        return 200
    except Exception as e:
        if isinstance(e, OperationalError):
            raise
        return f"error: {str(e)}"




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
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        instance.task_kwargs = instance.task_kwargs

    try:
        uuid, formatted_task_args_str = format_task_result_kwargs(instance.task_args)
        task_args = json.loads(formatted_task_args_str)
        for key in sensitive_keys:
            if key in task_args:
                task_args[key] = "****"
        instance.task_args = f'{{"uid": UUID({uuid}), ' + json.dumps(task_args)[1:]
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        instance.task_args = instance.task_args








