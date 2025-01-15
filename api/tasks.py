from celery import shared_task
import time
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from .plaid_client import plaid_client
from django.core.cache import cache
import json
from .serializers.PlaidSerializers.itemSerializers import ItemPublicTokenExchangeResponseSerializer
from .models import UserPlaidInfo
from django.contrib.auth.models import User

@shared_task(name="test_celery_task")
def test_celery_task():
    time.sleep(5)
    return True

@shared_task(name="plaid_item_public_token_exchange")
def plaid_item_public_token_exchange(**kwargs):
    # import pdb
    # breakpoint()
    uid = kwargs.pop('uid')
    public_token = kwargs.pop('public_token')
    exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
    exchange_response = plaid_client.item_public_token_exchange(exchange_request)

    try:
        serializer = ItemPublicTokenExchangeResponseSerializer(data={
            "access_token": exchange_response.access_token, 
            "item_id": exchange_response.item_id, 
            "request_id": exchange_response.request_id
        })
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        # userPlaidInfo = UserPlaidInfo.objects.get(user__id=uid)
        userPlaidInfo = UserPlaidInfo(user=User.objects.get(id=uid))
        userPlaidInfo.accessToken = validated_data['access_token']
        userPlaidInfo.itemId = validated_data['item_id']
        userPlaidInfo.save()

        cache.delete(f"uid_{uid}_plaid_item_public_token_exchange")
        cache.set(
            f"uid_{uid}_plaid_item_public_token_exchange",
            json.dumps({"message": "success", "error": None}), 
            timeout=120
        )
        return "cached plaid public token exchange success"
    except Exception as e:
        cache.delete(f"uid_{uid}_plaid_item_public_token_exchange")
        cache.set(
            f"uid_{uid}_plaid_item_public_token_exchange",
            json.dumps({"message": "error", "error": str(e)}), 
            timeout=120
        )
        return f"cached plaid public token exchange error: {str(e)}"
