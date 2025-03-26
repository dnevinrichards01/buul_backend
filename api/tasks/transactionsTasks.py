from celery import shared_task, chain
import robin_stocks.robinhood as r
from django.core.cache import cache 
from django.core.mail import send_mail
from django.utils import timezone
from django.db.models import Sum

from ..plaid_client import plaid_client
from ..jsonUtils import filter_jsons

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import numpy as np
import json
import re
import yfinance as yf
import math

from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.exceptions import ApiException

from..serializers.PlaidSerializers.transactionSerializers import TransactionsSyncResponseSerializer, \
    TransactionsGetResponseSerializer
from ..models import PlaidItem, User, RobinhoodStockOrder, PlaidCashbackTransaction

from django.utils import timezone
from zoneinfo import ZoneInfo

from django.apps import apps

# plaid transactions 

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
            transactions_get_by_item[plaidItem.itemId] = pages

        return transactions_get_by_item
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
        transactions_sync_by_item = {}
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
            transactions_sync_by_item[plaidItem.itemId] = pages
        return transactions_sync_by_item
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


# find cashback 

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

def transactions_identify_cashback(transactions_response, transactions_sync=True, 
                                eq={}, gt={}, lt={}, lte={}, gte={}, 
                                metric_to_return_by=None):
    cashback_transactions = []
    for item_id in transactions_response:
        item = transactions_response[item_id]
        for page_num in item:
            page = item[page_num]
            for transaction in page['added' if transactions_sync else 'transactions']:
                cashback_transactions.append(transaction)
    
    transaction['pending'] == False #?
    eq = {"pending": [False]}
    gt = {"amount": [0]}
    is_cashback = {"func": is_cashback, "filterset":["name"]}
    return filter_jsons(cashback_transactions, eq=eq, gt=gt, lt=lt, lte=lte, 
                        gte=gte, metric_to_return_by=metric_to_return_by, 
                        is_cashback=is_cashback)

def find_cashback(uid):
    all_cashback = {}
    transactions_sync_res = transactions_sync(uid)
    cashback_by_transaction_id = transactions_identify_cashback(transactions_sync_res)
    for cashback in cashback_by_transaction_id:
        plaidCashbackTransaction, created = PlaidCashbackTransaction.objects.get_or_create(
            user = User.objects.get(id=uid),
            transaction_id = cashback["transaction_id"],
            account_id = cashback["account_id"],
            amount = cashback["amount"],
            authorized_datetime = cashback["authorized_datetime"], 
        )
        if created:
            plaidCashbackTransaction.save()
            if "created" not in all_cashback:
                all_cashback["created"] = []
            all_cashback["created"].append(plaidCashbackTransaction)
        else:
            if "pre-existing" not in all_cashback:
                all_cashback["pre-existing"] = []
            all_cashback["pre-existing"].append(plaidCashbackTransaction)
        all_cashback.append(cashback)
    return all_cashback
        












# stock graph data
@shared_task(name="get_investment_graph_data")
def get_investment_graph_data(uid, symbol):
    # import pdb 
    # breakpoint()

    # get orders
    try:
        orders = RobinhoodStockOrder.objects \
            .filter(user__id=uid, state="filled") \
            .order_by('updated_at')
        if not orders.exists():
            raise Exception()
    except Exception as e:
        return {
            "success": None,
            "error": f"could not find robinhoodInvest object for user {uid}"
        }
    
    # calculate values for indexing and determining arrray lengths
    orders_start_date = orders.first().updated_at.replace(hour=0, minute=0, second=0, microsecond=0)
    date_today = timezone.now().date().replace(hour=0, minute=0, second=0, microsecond=0)
    date_five_years_ago = date_today - relativedelta(years=5)
    if orders_start_date > date_five_years_ago:
        start_date = date_five_years_ago
    else:
        start_date = orders_start_date
    total_days = (date_today - start_date).days

    stock_quantities = {}
    stock_prices = {}
    prev_indices = {}
    for investment in orders:
        # initialize stock prices and investment value array if stock not yet seen
        if investment not in stock_prices:
            stockData = StockData.objects.get(symbol=symbol)
            stock_start_date = stockData.startDate.replace(hour=0, minute=0, second=0, microsecond=0)
            if stock_start_date > start_date:
                padding = (stock_start_date - start_date).days
                stock_prices[investment.symbol] = np.pad(
                    np.array(stockData.dailyPrice), 
                    pad_width = (padding, 0),
                    mode='constant', 
                    constant_values=0
                )
                stock_quantities[investment.symbol] = np.zeros(len(stock_prices[investment.symbol]))
                prev_indices[investment.symbol] = None
            else:
                trim = (start_date - stock_start_date).days
                stock_prices[investment.symbol] = np.array(stockData.dailyPrice)[trim:]
                stock_quantities[investment.symbol] = np.zeros(len(stock_prices[investment.symbol]))
                prev_indices[investment.symbol] = None
            
            # make sure that all investment / price arrays are same length
            if len(stock_prices[investment.symbol]) != total_days:
                cache.set(
                    f"uid_{uid}_get_investment_graph_data",
                    json.dumps(
                        {
                            "success": None, 
                            "error": "mismatch in vector lengths between securities"
                        }
                    ),
                    timeout=120
                )
                return
            
        # get relevant info for current investment and the prev investment for this stock
        curr_date = investment.updated_at.replace(hour=0, minute=0, second=0, microsecond=0)
        curr_index = (curr_date - start_date).days
        prev_index = prev_indices[investment.symbol]
        prev_quantity = stock_quantities[investment.symbol][prev_index]
        
        # update stock quantities
        stock_quantities[investment.symbol][prev_index:curr_index+1] = prev_quantity
        prev_indices[investment.symbol] = curr_index
        stock_quantities[investment.symbol] = investment.quantity

    # calculate investment values
    investment_values = np.zeros(total_days)
    for stock in stock_prices:
        investment_values += stock_quantities[stock] * stock_prices[stock]

    # create graph data object and cache it
    graph_data = []
    for i in range(len(investment_values)):
        graph_data.append(
            {
                "price": investment_values[i],
                "date": (start_date + relativedelta(days=i)).isoformat()
            }
        )
    cache.set(
        f"uid_{uid}_get_investment_graph_data",
        json.dumps({"success": graph_data, "error": None}),
        timeout=120
    )


