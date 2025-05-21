from celery import shared_task
from django.utils import timezone
from django.apps import apps

from api.apis.plaid import plaid_client
from ..jsonUtils import filter_jsons

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from zoneinfo import ZoneInfo
import json
import re

from django.db.utils import OperationalError
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.exceptions import ApiException

from..serializers.plaid.transaction import TransactionsSyncResponseSerializer, \
    TransactionsGetResponseSerializer
from ..models import PlaidItem, User, PlaidCashbackTransaction, \
    PlaidPersonalFinanceCategories

from buul_backend.retry_db import retry_on_db_error

# plaid transactions 





# find cashback 

@shared_task(name="transactions_sync")
@retry_on_db_error
def transactions_sync(uid=None, item_ids={}, update_cursor=False, page_size=100):
    # import pdb
    # breakpoint()

    if item_ids:
        plaidItems = PlaidItem.objects.filter(itemId__in=item_ids)
    elif uid:
        plaidItems = PlaidItem.objects.filter(user__id=uid)
    else:
        raise Exception("Must enter at least one of uid and item_ids")
        
    try:
        # eventually both prevent duplicate items, and filter out duplicate accounts here
        transactions_sync_by_item = {}
        for plaidItem in plaidItems:
            hasMore = True
            page = 0
            nextCursor = plaidItem.transactionsCursor
            added, modified, removed = [], [], []
            while hasMore:
                if nextCursor is not None: 
                    # test if we can get rid of second case
                    exchange_request = TransactionsSyncRequest(
                        plaidItem.accessToken,
                        cursor = nextCursor,
                        count=page_size
                    )
                else:
                    exchange_request = TransactionsSyncRequest(
                        plaidItem.accessToken,
                        count=page_size
                    )
                exchange_response = plaid_client.transactions_sync(exchange_request)
                serializer = TransactionsSyncResponseSerializer(
                    data=exchange_response.to_dict()
                )
                serializer.is_valid(raise_exception=True)

                added.extend(serializer.validated_data['added'])
                modified.extend(serializer.validated_data['modified'])
                removed.extend(serializer.validated_data['removed'])
                nextCursor = serializer.validated_data["next_cursor"]
                hasMore = serializer.validated_data["has_more"]
                page += 1
                if update_cursor:
                    plaidItem.transactionsCursor = nextCursor
                    plaidItem.save()
        return added, modified, removed
    except ApiException as e:
        error = json.loads(e.body)
        return f"transactions sync get error: {error.get("error_code")}"
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        return f"transactions sync get error: {str(e)}"

@retry_on_db_error
def is_cashback(name):
    keywords_include = [
        "CASHBACK",
        "CASH BACK",
        "CASH AWARD",
        "CASH REWARD",
        "CASHREWARD", 
        "CASH REDEMPTION",
        "CASH AUTO REDEMPTION", # real name
        "CASHBACK BONUS",
        "CASHBACK REDEMPTION",
        "CASHBACK REWARDS",
        "REWARDS DEPOSIT",
        "REWARDS CREDIT",
        "REWARDS DEPOSIT",
        "REWARDS REDEMPTION",
        "STATEMENT CREDIT",
        "CREDIT- REWARD", # real name
        "CREDIT REWARD",
        "WELLS FARGO REWARDS",
        "CREDIT CRD DES:RWRD"
    ]
    keywords_reject = [
        "ZELLE",
        "BILL",
        "CITY",
        "DIRECT DEP"
    ]
    # add in terms to return false for. 
    # use 'word boundaries' around CASH etc so it won't match "CASHIER" etc
    match_pattern = '|'.join(map(re.escape, keywords_include))
    is_match = re.search(match_pattern, name) is not None
    reject_pattern = '|'.join(map(re.escape, keywords_reject))
    is_reject = re.search(reject_pattern, name) is not None 
    return is_match and not is_reject


@shared_task(name="find_cashback_added")
@retry_on_db_error
def find_cashback_added(uid, transactions, eq={}, gt={}, lt={}, lte={}, gte={}, 
                        metric_to_return_by=None):
    user = User.objects.get(id=uid)

    lt = {"amount": [0]}
    is_cashback_name = {
        "func": lambda name, bool: is_cashback(name) == bool,
        "filter_set": {"name" : [True]}
    }
    cashback_candidates = filter_jsons(transactions, eq=eq, gt=gt, lt=lt, lte=lte, 
                        gte=gte, metric_to_return_by=metric_to_return_by, 
                        is_cashback=is_cashback_name)
    if isinstance(cashback_candidates, str):
        raise Exception(cashback_candidates)
    all_cashback = []
    for cashback in cashback_candidates:
        plaidCashbackTransaction = PlaidCashbackTransaction(
            user = user,
            transaction_id = cashback["transaction_id"],
            account_id = cashback["account_id"],
            amount = cashback["amount"],
            pending = cashback["pending"],
            authorized_date = cashback["authorized_date"],
            authorized_datetime = cashback["authorized_datetime"], 
            date = cashback["date"],
            name = cashback["name"],
            iso_currency_code = cashback["iso_currency_code"],
            flag = user.date_joined > timezone.make_aware(
                datetime.combine(cashback["date"], datetime.min.time()),
                timezone.get_current_timezone()
            )
        )
        all_cashback.append(plaidCashbackTransaction)
    try:
        PlaidCashbackTransaction.objects.bulk_create(all_cashback, batch_size=100)
    except:
        # if bulk create fails
        for cashback in cashback_candidates:
            # could use all_cashback instead
            try:
                # try to create them individually 
                plaidCashbackTransaction = PlaidCashbackTransaction(
                    user = User.objects.get(id=uid),
                    transaction_id = cashback["transaction_id"],
                    account_id = cashback["account_id"],
                    amount = cashback["amount"],
                    pending = cashback["pending"],
                    authorized_date = cashback["authorized_date"],
                    authorized_datetime = cashback["authorized_datetime"], 
                    date = cashback["date"],
                    name = cashback["name"],
                    iso_currency_code = cashback["iso_currency_code"],
                    flag = user.date_joined > timezone.make_aware(
                        datetime.combine(cashback["date"], datetime.min.time()),
                        timezone.get_current_timezone()
                    )
                )
                plaidCashbackTransaction.save()
            except:
                # if fails then assume it's because it already exists 
                plaidCashbackTransaction = PlaidCashbackTransaction.objects.get(
                    user = User.objects.get(id=uid),
                    transaction_id = cashback["transaction_id"],
                    account_id = cashback["account_id"]
                )
                if plaidCashbackTransaction.deposit is not None and \
                cashback["amount"] != plaidCashbackTransaction.amount or \
                cashback["iso_currency_code"] != plaidCashbackTransaction.iso_currency_code:
                    plaidCashbackTransaction.deposit.flag = True
                if not plaidCashbackTransaction.deposit:
                    plaidCashbackTransaction.amount = cashback["amount"]
                    plaidCashbackTransaction.iso_currency_code = cashback["iso_currency_code"]
                plaidCashbackTransaction.pending = cashback["pending"]
                plaidCashbackTransaction.authorized_date = cashback["authorized_date"]
                plaidCashbackTransaction.authorized_datetime = cashback["authorized_datetime"]
                plaidCashbackTransaction.date = cashback["date"]
                plaidCashbackTransaction.name = cashback["name"]
                plaidCashbackTransaction.iso_currency_code = cashback["iso_currency_code"]
                plaidCashbackTransaction.save()

                # xact x deposit, deposit connected to investment
                # something to mark any deposits or investments 

@shared_task(name="find_cashback_modified")
@retry_on_db_error
def find_cashback_modified(uid, transactions, eq={}, gt={}, lt={}, lte={}, gte={}, 
                        metric_to_return_by=None):
    lt = {"amount": [0]}
    is_cashback_name = {
        "func": lambda name, bool: is_cashback(name) == bool,
        "filter_set": {"name" : [True]}
    }
    cashback_candidates = filter_jsons(transactions, eq=eq, gt=gt, lt=lt, lte=lte, 
                        gte=gte, metric_to_return_by=metric_to_return_by, 
                        is_cashback=is_cashback_name)
    to_create = []
    to_update = []
    for cashback in cashback_candidates:
        try:
            plaidCashbackTransaction = PlaidCashbackTransaction.objects.get(
                user = User.objects.get(id=uid),
                transaction_id = cashback["transaction_id"],
                account_id = cashback["account_id"]
            )
            if plaidCashbackTransaction.deposit is not None and \
                cashback["amount"] != plaidCashbackTransaction.amount or \
                cashback["iso_currency_code"] != plaidCashbackTransaction.iso_currency_code:
                plaidCashbackTransaction.deposit.flag = True
            if not plaidCashbackTransaction.deposit:
                plaidCashbackTransaction.amount = cashback["amount"]
                plaidCashbackTransaction.iso_currency_code = cashback["iso_currency_code"]
            plaidCashbackTransaction.pending = cashback["pending"]
            plaidCashbackTransaction.authorized_date = cashback["authorized_date"]
            plaidCashbackTransaction.authorized_datetime = cashback["authorized_datetime"]
            plaidCashbackTransaction.date = cashback["date"]
            to_create.append(plaidCashbackTransaction)

            # xact x deposit, deposit connected to investment
            # something to mark any deposits or investments 
        except:
            plaidCashbackTransaction = PlaidCashbackTransaction(
                user = User.objects.get(id=uid),
                transaction_id = cashback["transaction_id"],
                account_id = cashback["account_id"],
                amount = cashback["amount"],
                pending = cashback["pending"],
                date = cashback["date"],
                authorized_date = cashback["authorized_date"],
                authorized_datetime = cashback["datetime"], 
                name = cashback["name"],
                iso_currency_code = cashback["iso_currency_code"]
            )
            to_update.append(plaidCashbackTransaction)
    PlaidCashbackTransaction.objects.bulk_create(to_create, batch_size=100)
    PlaidCashbackTransaction.objects.bulk_update(
        to_update, 
        ["amount", "iso_currency_code", "pending", "authorized_date", 
         "authorized_datetime", "date"],
         batch_size=100
    )

# in future turn these into generators?
# or in future make transactions ordered by dictionary (key=cashback?)
@shared_task(name="find_cashback_removed")
@retry_on_db_error
def find_cashback_removed(uid, transactions, eq={}, gt={}, lt={}, lte={}, gte={}, 
                        metric_to_return_by=None):
    lt = {"amount": [0]}
    is_cashback_name = {
        "func": lambda name, bool: is_cashback(name) == bool,
        "filter_set": {"name" : [True]}
    }
    cashback_candidates = filter_jsons(transactions, eq=eq, gt=gt, lt=lt, lte=lte, 
                        gte=gte, metric_to_return_by=metric_to_return_by, 
                        is_cashback=is_cashback_name)
    for cashback in cashback_candidates:
        try:
            plaidCashbackTransaction = PlaidCashbackTransaction.objects.get(
                user = User.objects.get(id=uid),
                transaction_id = cashback["transaction_id"],
                account_id = cashback["account_id"]
            )
            if plaidCashbackTransaction.deposit is None:
                plaidCashbackTransaction.delete()
            else: 
                plaidCashbackTransaction.deposit.flag = True
                plaidCashbackTransaction.deposit.save()
        except:
            continue

@shared_task(name="update_transactions")
@retry_on_db_error
def update_transactions(item_id):
    item = PlaidItem.objects.get(itemId = item_id)
    uid = item.user.id
    cursor = item.transactionsCursor
    try:
        added, modified, removed = transactions_sync(
            item_ids={item_id}, update_cursor=True
        )
        find_cashback_added(uid, added)
        find_cashback_modified(uid, modified)
        find_cashback_removed(uid, removed)
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        item.transactionsCursor = cursor
        return e
        # some sort of CTE / view made from celery logs


# spending by category

@shared_task(name="transactions_get")
@retry_on_db_error
def transactions_get(uid, start_date_str, end_date_str, item_ids={}, page_size=100):
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
                    plaidItem.accessToken,
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
            transactions_get_by_item[plaidItem.itemId] = pages

        return transactions_get_by_item
    except ApiException as e:
        error = json.loads(e.body)
        return f"transactions get error: {error.get("error_code")}"
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        return f"transactions get error: {str(e)}"

@shared_task(name="transactions_categories_sum")
@retry_on_db_error
def transactions_categories_sum(transactions_response, transactions_sync=True,
                                personal_finance_categories=True):
    plaid_category_detail_to_buul_categories = {
        "FOOD_DRINK_AND_COFFEE": "dining",
        "FOOD_DRINK_AND_FAST_FOOD": "dining",
        "FOOD_AND_DRINK_RESTAURANT": "dining",
        "FOOD_AND_DRINK_GROCERIES": "groceries",
        "RENT_AND_UTILITIES_WATER": "utilities",
        "RENT_AND_UTILITIES_TELEPHONE": "utilities",
        "RENT_AND_UTILITIES_SEWAGE_AND_WASTE_TREATMENT": "utilities",
        "RENT_AND_UTILITIES_INTERNET_AND_CABLE": "utilities",
        "RENT_AND_UTILITIES_GAS_AND_ELECTRICITY": "utilities",
        "TRAVEL_FLIGHTS": "travel",
        "TRAVEL_LODGING": "travel"
    }

    counter_dict = {}
    min_date = None
    max_date = None
    for item_id in transactions_response:
        item = transactions_response[item_id]
        for page_num in item:
            page = item[page_num]
            for transaction in page['added' if transactions_sync else 'transactions']:
                amount = transaction['amount']
                # check if valid
                if transaction['pending'] == True or amount < 0:
                    continue

                if min_date is None or max_date is None:
                    min_date = transaction["date"]
                    max_date = transaction["date"]
                elif transaction["date"] < min_date:
                    min_date = transaction["date"]
                elif transaction["date"] > max_date:
                    max_date = transaction["date"]

                detailed = transaction['personal_finance_category']['detailed']
                categ = plaid_category_detail_to_buul_categories.get(detailed, None)
                if categ and categ in counter_dict:
                    counter_dict[categ] += amount
                elif categ and categ not in counter_dict:
                    counter_dict[categ] = amount
                else: 
                    continue
    return counter_dict, min_date, max_date

@shared_task(name="user_spending_by_category")
@retry_on_db_error
def user_spending_by_category(uid):
    start_date_str = (timezone.now() - relativedelta(months=1)).strftime("%Y-%m-%d")
    end_date_str = timezone.now().strftime("%Y-%m-%d")
    transactions = transactions_get(uid, start_date_str, end_date_str)
    spending_by_category, min_date, max_date = transactions_categories_sum(
        transactions, transactions_sync=False
    )

    category_model_query = PlaidPersonalFinanceCategories.objects.filter(user__id=uid)
    if category_model_query.exists():
        category_model = category_model_query.first()
    else:
        category_model = PlaidPersonalFinanceCategories(
            user = User.objects.get(id=uid)
        )
    for category in spending_by_category:
        category_model[category] = spending_by_category[category]
    category_model.start_date = start_date_str
    category_model.end_date = end_date_str
    category_model.save()
    

@shared_task(name="all_users_spending_by_category")
@retry_on_db_error
def all_users_spending_by_category():
    for user in User.objects.all():
        user_spending_by_category(user.id)

