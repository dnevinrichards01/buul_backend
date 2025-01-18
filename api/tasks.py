from celery import shared_task, chain
import time
from .plaid_client import plaid_client
from django.core.cache import cache 
from django.core.mail import send_mail

from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.user_create_request import UserCreateRequest
from plaid.model.user_remove_request import UserRemoveRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.country_code import CountryCode
from plaid.model.products import Products
from plaid.exceptions import ApiException

from .serializers.PlaidSerializers.itemSerializers import ItemPublicTokenExchangeResponseSerializer, \
    ItemRemoveResponseSerializer
from .serializers.PlaidSerializers.linkSerializers import LinkTokenCreateResponseSerializer
from .serializers.PlaidSerializers.errorSerializer import ErrorSerializer
from .serializers.PlaidSerializers.balanceSerializers import BalanceGetResponseSerializer, \
    AccountsGetResponseSerializer
from .serializers.PlaidSerializers.userSerializers import UserRemoveResponseSerializer, \
    UserCreateResponseSerializer
from.serializers.PlaidSerializers.transactionSerializers import TransactionsSyncResponseSerializer, \
    TransactionsGetResponseSerializer
from .models import PlaidItem, PlaidUser, User

import json
import uuid
from datetime import datetime
import re



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
            json.dumps({"message": "success", "error": None}), 
            timeout=120
        )
        return "cached plaid public token exchange success"
    except ApiException as e:
        error = json.loads(e.body)
        cache.delete(f"uid_{uid}_plaid_item_public_token_exchange")
        cache.set(
            f"uid_{uid}_plaid_item_public_token_exchange",
            json.dumps({"message": "error", "error": error.get("error_code")}), 
            timeout=120
        )
        return f"cached plaid public token exchange error: {error.get("error_code")}"
    except Exception as e:
        cache.delete(f"uid_{uid}_plaid_item_public_token_exchange")
        cache.set(
            f"uid_{uid}_plaid_item_public_token_exchange",
            json.dumps({"message": "error", "error": str(e)}), 
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
            client_name="Accumate",
            language=kwargs['language'],
            country_codes=[CountryCode(val) for val in kwargs['country_codes']], # Specify the countries
            user=LinkTokenCreateRequestUser(
                client_user_id=PlaidUser.objects.get(user__id=uid).client_user_id,  # Replace with a unique identifier for the user
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
                "message": serializer.validated_data["link_token"], 
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
            json.dumps({"message": "error", "error": error.get("error_code")}), 
            timeout=120
        )
        return f"cached plaid link token create error: {error.get("error_code")}"
    except Exception as e:
        cache.delete(f"uid_{uid}_plaid_link_token_create")
        cache.set(
            f"uid_{uid}_plaid_link_token_create",
            json.dumps({"message": "error", "error": str(e)}), 
            timeout=120
        )
        return f"cached plaid link token create error: {str(e)}"


@shared_task(name="plaid_accounts_get")
def plaid_accounts_get(uid, item_id=None):
    # import pdb
    # breakpoint()
        
    try:
        plaidItems = PlaidItem.objects.filter(user__id=uid)
        accounts_get_by_item = {}
        for plaidItem in plaidItems:
            if item_id and item_id != plaidItem.item_id:
                continue
            exchange_request = AccountsGetRequest(
                access_token=plaidItem.accessToken
            )
            
            exchange_response = plaid_client.accounts_get(exchange_request)
            serializer = AccountsGetResponseSerializer(
                data=exchange_response.to_dict()
            )
            serializer.is_valid(raise_exception=True)
            accounts_get_by_item[plaidItem.itemId] = serializer.validated_data
        return accounts_get_by_item
    except ApiException as e:
        error = json.loads(e.body)
        return f"accounts get error: {error.get("error_code")}"
    except Exception as e:
        return f"accounts get error: {str(e)}"


@shared_task(name="plaid_balance_get")
def plaid_balance_get(uid, item_id=None, account_ids_by_item_id={}):
    import pdb
    breakpoint()
    
    try:
        plaidItems = PlaidItem.objects.filter(user__id=uid)
        balance_get_by_item = {}
        for plaidItem in plaidItems:
            if item_id and item_id != plaidItem.itemId:
                continue
            if plaidItem.itemId in account_ids_by_item_id:
                exchange_request = AccountsBalanceGetRequest(
                    access_token=plaidItem.accessToken,
                    options={"account_ids": account_ids_by_item_id[plaidItem.itemId]}
                )
            else:
                exchange_request = AccountsBalanceGetRequest(
                    access_token=plaidItem.accessToken
                )
        
            exchange_response = plaid_client.accounts_balance_get(exchange_request)
            serializer = BalanceGetResponseSerializer(
                data=exchange_response.to_dict()
            )
            serializer.is_valid(raise_exception=True)

            balance_get_by_item[plaidItem.itemId] = serializer.validated_data
        return balance_get_by_item
    except ApiException as e:
        error = json.loads(e.body)
        return f"balance get error: {error.get("error_code")}"
    except Exception as e:
        return f"balance get error: {str(e)}"
    
def process_plaid_balance(plaid_balance_response):
    balances = {}
    for item_id in plaid_balance_response:
        item = plaid_balance_response[item_id]
        for account in item['accounts']:
            account_balance_data = account.copy()
            account_balance_data['iso_currency_code'] = account['balances']['iso_currency_code']
            account_balance_data['balance'] = account['balances']['available']
            account_balance_data.pop('balances')
            balances[account['account_id']] = account_balance_data
    return balances

@shared_task(name="plaid_transactions_sync")
def plaid_transactions_sync(uid, item_id=None, account_ids_by_item_id={}):
    import pdb
    breakpoint()
    
    try:
        plaidItems = PlaidItem.objects.filter(user__id=uid)
        balance_get_by_item = {}
        for plaidItem in plaidItems:
            if item_id and item_id != plaidItem.item_id:
                continue
            if plaidItem.item_id in account_ids_by_item_id:
                exchange_request = AccountsBalanceGetRequest(
                    access_token=plaidItem.accessToken,
                    options={"account_ids": account_ids_by_item_id[plaidItem.item_id]}
                )
            else:
                exchange_request = AccountsBalanceGetRequest(
                    access_token=plaidItem.accessToken
                )
        
            exchange_response = plaid_client.accounts_balance_get(exchange_request)
            serializer = BalanceGetResponseSerializer(
                data=exchange_response.to_dict()
            )
            serializer.is_valid(raise_exception=True)

            balance_get_by_item[plaidItem.item_id] = serializer.validated_data
        return balance_get_by_item
    except ApiException as e:
        error = json.loads(e.body)
        return f"transactions sync get error: {error.get("error_code")}"
    except Exception as e:
        return f"transactions sync get error: {str(e)}"
   

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
        plaidUser = PlaidUser(user=User.objects.get(id=uid))

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

        plaidUser.clientUserId = client_user_id
        plaidUser.userId = serializer.validated_data['user_id']
        plaidUser.userToken = serializer.validated_data['user_token']
        plaidUser.save()

        cache.delete(f"uid_{uid}_plaid_user_create")
        cache.set(
            f"uid_{uid}_plaid_user_create",
            json.dumps({
                "message": "success", 
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
            json.dumps({"message": "error", "error": error.get("error_code")}), 
            timeout=120
        )
        return f"cached plaid user create error: {error.get("error_code")}"
    except Exception as e:
        cache.delete(f"uid_{uid}_plaid_user_create")
        cache.set(
            f"uid_{uid}_plaid_user_create",
            json.dumps({"message": "error", "error": str(e)}), 
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
    

@shared_task(name="transactions_get")
def transactions_get(uid, start_date_str, end_date_str, item_ids={}, 
                     transactions_by_item_id={}, page_size=100):
    # import pdb
    # breakpoint()
    
    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()

        plaidItems = PlaidItem.objects.filter(user__id=uid)

        transactions_get_by_item = {}
        
        for plaidItem in plaidItems:
            if item_ids and plaidItem.itemId not in item_ids:
                continue
            offset = 0
            page = 0
            pages = {}
            total_transactions = float('inf')
            while total_transactions > offset:
                exchange_request = TransactionsGetRequest(
                    access_token = plaidItem.accessToken,
                    start_date = start_date,
                    end_date = end_date,
                    options = TransactionsGetRequestOptions(
                        count = page_size,
                        offset = offset
                    )
                )
                
                exchange_response = plaid_client.transactions_get(exchange_request)
                serializer = TransactionsGetResponseSerializer(
                    data=exchange_response.to_dict()
                )
                serializer.is_valid(raise_exception=True)

                pages[page] = serializer.validated_data

                offset += page_size
                page += 1
                total_transactions = serializer.validated_data["total_transactions"]
            transactions_by_item_id[plaidItem.itemId] = pages

        return transactions_by_item_id
    except ApiException as e:
        error = json.loads(e.body)
        return f"transactions get error: {error.get("error_code")}"
    except Exception as e:
        return f"transactions get error: {str(e)}"

@shared_task(name="transactions_sync")
def transactions_sync(uid, item_ids={}, transactions_by_item_id={}, 
                      update_cursor=False, page_size=100):
    # import pdb
    # breakpoint()
    
    try:
        plaidItems = PlaidItem.objects.filter(user__id=uid)
        transactions_get_by_item = {}
        for plaidItem in plaidItems:
            if item_ids and plaidItem.itemId not in item_ids:
                continue
            
            hasMore = True
            page = 0
            nextCursor = plaidItem.transactionsCursor
            pages = {}
            while hasMore:
                if nextCursor is not None:
                    exchange_request = TransactionsSyncRequest(
                        access_token=plaidItem.accessToken,
                        cursor = nextCursor,
                        count=page_size
                    )
                else:
                    exchange_request = TransactionsSyncRequest(
                        access_token=plaidItem.accessToken,
                        count=page_size
                    )
                exchange_response = plaid_client.transactions_sync(exchange_request)
                serializer = TransactionsSyncResponseSerializer(
                    data=exchange_response.to_dict()
                )
                serializer.is_valid(raise_exception=True)
                pages[page] = serializer.validated_data
                if update_cursor:
                    plaidItem.transactionsCursor = serializer.validated_data["next_cursor"]

                nextCursor = serializer.validated_data["next_cursor"]
                hasMore = serializer.validated_data["has_more"]
                page += 1
            transactions_by_item_id[plaidItem.itemId] = pages
        return transactions_by_item_id
    except ApiException as e:
        error = json.loads(e.body)
        return f"transactions sync get error: {error.get("error_code")}"
    except Exception as e:
        return f"transactions sync get error: {str(e)}"

@shared_task(name="transactions_categories_sum")
def transactions_categories_sum(transactions_response, transactions_sync=True,
                                personal_finance_categories=False):
    counter_dict = {}
    for item_id in transactions_response:
        item = transactions_response[item_id]
        for page_num in item:
            page = item[page_num]
            for transaction in page['added' if transactions_sync else 'transactions']:
                amount = transaction['amount']
                if transaction['pending'] == True or amount < 0:
                    continue

                if personal_finance_categories:
                    personal_finance_category = transaction['personal_finance_category']['detailed']
                    if personal_finance_category in counter_dict:
                        counter_dict[personal_finance_category] += amount
                    else:
                        counter_dict[personal_finance_category] = amount
                else:
                    for category in transaction['category']:
                        if category in counter_dict:
                            counter_dict[category] += amount
                        else:
                            counter_dict[category] = amount
    return counter_dict

def all_categories():
    categs = plaid_client.categories_get({}).to_dict()['categories']
    all_categs_set = set()
    for category_combo in categs:
        for category in category_combo['hierarchy']:
            all_categs_set.add(category)
    return all_categs_set



def is_cashback(name):
    cashback_names = [
        "CASH REWARD REDEMPTION",
        "REWARDS DEPOSIT",
        "CASHBACK BONUS",
        "REWARDS DEPOSIT",
        "CASHBACK REDEMPTION",
        "REWARDS CREDIT",
        "DISCOVER CASHBACK BONUS",
        "CASHBACK REWARDS DEPOSIT",
        "REWARDS REDEMPTION",
        "CASHBACK REWARDS",
        "STATEMENT CREDIT",
        "REWARDS CREDIT",
        "CASH REDEMPTION",
    ]
    cashback_keywords = [
        "CASHBACK",
        "REWARDS"
    ]

    pattern = '|'.join(map(re.escape, cashback_names + cashback_keywords))  # Escape substrings to handle special characters
    return re.search(pattern, name) is not None

def transactions_identify_cashback(transactions_response, transactions_sync=True):
    
    cashback_transactions = {}
    for item_id in transactions_response:
        item = transactions_response[item_id]
        for page_num in item:
            page = item[page_num]
            for transaction in page['added' if transactions_sync else 'transactions']:
                amount = transaction['amount']
                if transaction['pending'] == True or amount < 0:
                    continue
                if is_cashback(transaction['name']):
                    id = transaction['transaction_id']
                    transaction_data = {
                        "name": transaction['name'],
                        "account_id": transaction['account_id'],
                        "transaction_id": transaction['transaction_id'],
                        "date": transaction['date'],
                        "amount": transaction['amount']
                    }
                    cashback_transactions[id] = transaction_data
    return cashback_transactions

@shared_task(name="send_email")
def send_recovery_email(**kwargs):
    send_mail(
        "Accumate password recovery",
        f"To recover your account, please click on the link: {kwargs["url"]}",
        "accumate-verify@accumatewealth.com",
        [kwargs["email"]],
        fail_silently=False,
    )
















