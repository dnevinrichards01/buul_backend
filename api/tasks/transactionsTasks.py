from celery import shared_task, chain
import robin_stocks.robinhood as r
from django.core.cache import cache 
from django.core.mail import send_mail
from django.utils import timezone

from ..plaid_client import plaid_client
from ..jsonUtils import filter_jsons

from datetime import datetime, timedelta
import numpy as np
import json
import re
import yfinance as yf

from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.exceptions import ApiException

from..serializers.PlaidSerializers.transactionSerializers import TransactionsSyncResponseSerializer, \
    TransactionsGetResponseSerializer
from ..models import PlaidItem, User, RobinhoodStockOrder, StockData, \
    PlaidCashbackTransaction




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
    
    transaction['pending'] == False
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
    try:
        robinhoodInvestments = RobinhoodInvest.objects \
            .filter(user__id=uid, invested=True) \
            .order_by('updated_at')
    except Exception as e:
        return {"error": f"could not find robinhoodInvest object for that {uid}"} 
    
    if robinhoodInvestments.size() == 0:
        return {"error": f"{uid} has no investments"}
    
    start_date = robinhoodInvestments.first().updated_at - timedelta(days=1)
    total_quantity = {}
    previous_index = {}
    all_stock_prices = {}
    vector_length = 0
    for i in range(len(robinhoodInvestments) + 1):
        investment = robinhoodInvestments[i]

        if investment.symbol not in total_quantity:
            total_quantity[investment.symbol] = 0
        if investment.symbol not in previous_index:
            previous_index[investment.symbol] = None
        if investment.symbol not in all_stock_prices:
            stockData = StockData.objects.get(symbol=symbol)
            prices = stockData.dailyPrice
            if stockData.startDate > start_date:
                padding = (stockData.startDate - start_date).days
                all_stock_prices[investment.symbol] = np.pad(
                    np.array(prices), 
                    pad_width = (padding, 0),
                    mode='constant', 
                    constant_values=0
                )
            else:
                trim = (start_date - stockData.startDate).days
                all_stock_prices[investment.symbol] = np.array(prices)[trim:]
        
        current_index = investment.updated_at.strftime("&Y-%m-%d")
        previous_index = previous_index[investment.symbol]
        total_quantity = total_quantity[investment.symbol]
        prices = all_stock_prices[investment.symbol]
        
        if i == 0:
            vector_length = len(prices)
        if i == len(robinhoodInvestments):
            current_index = None
        
        prices[previous_index:current_index] *= total_quantity

        total_quantity[investment.symbol] += investment.quantity
        previous_index[investment.symbol] = current_index
        all_stock_prices[investment.symbol] = prices

    investment_values = np.zeros(vector_length)
    for stock_prices in all_stock_prices:
        investment_values += stock_prices 
    
    cache.delete(f"uid_{uid}_get_investment_graph_data")
    cache.set(
        f"uid_{uid}_get_investment_graph_data",
        json.dumps({
            "message": "success", 
            "error": None,
            "investment_values": investment_values.tolist(),
            }
        ),
        timeout=120
    )
    return investment_values

@shared_task(name="refresh_stock_data")
def refresh_stock_data(symbols=["VOO"], start_date=None, end_date=None):
    for symbol in symbols:
        stockData, created = StockData.objects.get_or_create(symbol=symbol)
         
        data = yf.download(
            symbol, 
            start = start_date or stockData.cursor.strftime("%Y-%m-%d"),
            end = end_date or timezone.now().strftime("%Y-%m-%d"),
            interval="1d"
        )
        
        stockData.dailyPrice += list(data[("Close", symbol)])

        stockData.cursor = timezone.now()
        stockData.save()
