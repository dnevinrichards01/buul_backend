from celery import shared_task, chain
import time
from ..plaid_client import plaid_client
# from ..twilio_client import twilio_client
from django.core.cache import cache 
from django.core.mail import send_mail

from accumate_backend.settings import TWILIO_PHONE_NUMBER

from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.user_create_request import UserCreateRequest
from plaid.model.user_remove_request import UserRemoveRequest
from plaid.model.country_code import CountryCode
from plaid.model.products import Products
from plaid.exceptions import ApiException

from ..serializers.PlaidSerializers.itemSerializers import ItemPublicTokenExchangeResponseSerializer, \
    ItemRemoveResponseSerializer
from ..serializers.PlaidSerializers.linkSerializers import LinkTokenCreateResponseSerializer
from ..serializers.PlaidSerializers.userSerializers import UserRemoveResponseSerializer, \
    UserCreateResponseSerializer
from ..models import PlaidItem, PlaidUser, User

import json
import uuid


# user creation and deletion

@shared_task(name="plaid_item_public_token_exchange")
def plaid_item_public_token_exchange(**kwargs):
    # import pdb
    # breakpoint()
    uid = kwargs.pop('uid')
    public_token = kwargs.pop('public_token')
    
    try:
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
        plaidItem.accessToken = validated_data['access_token']
        plaidItem.itemId = validated_data['item_id']
        plaidItem.save()

        cache.delete(f"uid_{uid}_plaid_item_public_token_exchange")
        cache.set(
            f"uid_{uid}_plaid_item_public_token_exchange",
            json.dumps({"success": "recieved", "error": None}), 
            timeout=120
        )
        return "cached plaid public token exchange success"
    except ApiException as e:
        error = json.loads(e.body)
        cache.delete(f"uid_{uid}_plaid_item_public_token_exchange")
        cache.set(
            f"uid_{uid}_plaid_item_public_token_exchange",
            json.dumps({"success": None, "error": f"{e.status}: {str(e)}"}), 
            timeout=120
        )
        return f"cached plaid public token exchange error: {error.get("error_code")}"
    except Exception as e:
        cache.delete(f"uid_{uid}_plaid_item_public_token_exchange")
        cache.set(
            f"uid_{uid}_plaid_item_public_token_exchange",
            json.dumps({"success": None, "error": "error: " + str(e)}), 
            timeout=120
        )
        return f"cached plaid public token exchange error: {str(e)}"

@shared_task(name="plaid_link_token_create")
def plaid_link_token_create(**kwargs):
    # import pdb
    # breakpoint()

    uid = kwargs.pop('uid')
    
    try:
        exchange_request = LinkTokenCreateRequest(
            client_name=kwargs["client_name"],
            language=kwargs['language'],
            country_codes=[CountryCode(code) for code in kwargs["country_codes"]], # Specify the countries
            user=LinkTokenCreateRequestUser(
                client_user_id=PlaidUser.objects.get(user__id=uid).clientUserId,  # Replace with a unique identifier for the user
                phone_number=kwargs['user']['phone_number'],
                email_address=kwargs['user']['email_address']
            ),
            products=[Products(val) for val in kwargs['products']],  # Specify the Plaid products you want to use
        )
        
        exchange_response = plaid_client.link_token_create(exchange_request)
        serializer = LinkTokenCreateResponseSerializer(data={
            "link_token": exchange_response.link_token, 
            "expiration": exchange_response.expiration, 
            "request_id": exchange_response.request_id
        })
        serializer.is_valid(raise_exception=True)

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
        return f"cached plaid link token create error: {error.get("error_code")}"
    except Exception as e:
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
def plaid_item_remove(uid, item_id):
    import pdb
    breakpoint()
    try:
        plaidItem = PlaidItem.objects.get(user__id=uid, item_id=item_id)
        exchange_request = ItemRemoveRequest(
            access_token=plaidItem.accessToken
        )
        plaidItem.delete()
        
        exchange_response = plaid_client.item_remove(exchange_request)
        serializer = ItemRemoveResponseSerializer(
            data=exchange_response.to_dict()
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data
    except ApiException as e:
        error = json.loads(e.body)
        return f"item remove error: {error.get("error_code")}"
    except Exception as e:
        return f"item remove error: {str(e)}"

@shared_task(name="plaid_user_create")
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
            json.dumps({"success": None, "error": f"{e.status}: {str(e)}"}), 
            timeout=120
        )
        return f"cached plaid user create error: {error.get("error_code")}"
    except Exception as e:
        cache.delete(f"uid_{uid}_plaid_user_create")
        cache.set(
            f"uid_{uid}_plaid_user_create",
            json.dumps({"success": None, "error": "error: " + str(e)}), 
            timeout=120
        )
        return f"cached plaid user create error: {str(e)}"

@shared_task(name="plaid_user_remove")
def plaid_user_remove(uid):
    # import pdb
    # breakpoint()
    
    try:
        plaidUser = PlaidUser.objects.get(user__id=uid)
        exchange_request = UserRemoveRequest(
            user_token = plaidUser.userToken
        )
        exchange_response = plaid_client.user_remove(exchange_request)
        serializer = UserRemoveResponseSerializer(
            data=exchange_response.to_dict()
        )
        serializer.is_valid(raise_exception=True)

        plaidUser.delete()

        cache.delete(f"uid_{uid}_plaid_user_remove")
        cache.set(
            f"uid_{uid}_plaid_user_remove", 
            json.dumps({
                "message": "success", 
                "error": None
            }), 
            timeout=120
        )
        return "cached plaid user remove success"
    except ApiException as e:
        error = json.loads(e.body)
        cache.delete(f"uid_{uid}_plaid_user_remove")
        cache.set(
            f"uid_{uid}_plaid_user_remove",
            json.dumps({"message": "error", "error": error.get("error_code")}), 
            timeout=120
        )
        return f"cached plaid user remove error: {error.get("error_code")}"
    except Exception as e:
        cache.delete(f"uid_{uid}_plaid_user_remove")
        cache.set(
            f"uid_{uid}_plaid_user_remove",
            json.dumps({"message": "error", "error": str(e)}), 
            timeout=120
        )
        return f"cached plaid user remove error: {str(e)}"

@shared_task(name="accumate_user_remove")
def accumate_user_remove(uid):
    # import pdb
    # breakpoint()

    try:
        User.objects.get(id=uid).delete()

        cache.delete(f"uid_{uid}_accumate_user_remove")
        cache.set(
            f"uid_{uid}_accumate_user_remove",
            json.dumps({
                "message": "success",
                "error": None
            }),
            timeout=120
        )
    except Exception as e:
        # import pdb 
        # breakpoint()
        cache.delete(f"uid_{uid}_accumate_user_remove")
        cache.set(
            f"uid_{uid}_accumate_user_remove",
            json.dumps({"message": "error", "error": str(e)}), 
            timeout=120
        )
        return f"cached accumate user remove error: {str(e)}"

@shared_task(name="send_verification_code")
def send_verification_code(**kwargs):
    if kwargs["useEmail"]:
        send_mail(
            "Accumate verification code",
            f"Enter this code in the Accumate app to verify your identity: {kwargs["code"]}",
            "accumate-verify@accumatewealth.com",
            [kwargs["sendTo"]],
            fail_silently=False,
        )
    else:
        return
        # twilio_client.messages.create(
        #     to = kwargs["sendTo"],
        #     from_ = TWILIO_PHONE_NUMBER,
        #     body = f"Enter this code in the Accumate app to verify your identity: {kwargs["code"]}"
        # )

@shared_task(name="send_waitlist_email")
def send_waitlist_email(**kwargs):
    send_mail(
        "You're on the Accumate waitlist!",
        "We look forward to working with you to maximize your cashback " \
        "and grow your wealth! Stay tuned for updates. \nIf you would like " \
        "to unsubscribe, respond to this email address requesting to be taken " \
        "off. \n\nThank you, \nthe Accumate team",
        "accumate-verify@accumatewealth.com",
        [kwargs["sendTo"]],
        fail_silently=False,
    )

