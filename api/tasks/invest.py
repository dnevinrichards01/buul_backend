from celery import shared_task
import robin_stocks.robinhood as r
from django.utils import timezone
from django.dispatch import receiver
from django.db.models.signals import post_save
from rest_framework.exceptions import ValidationError

from django.db.utils import OperationalError
from datetime import datetime, timedelta
import json
from .shared_utilities import rh_load_account_profile
from ..jsonUtils import filter_jsons

from ..models import RobinhoodStockOrder, UserBrokerageInfo, User, Investment
from ..serializers.rh import StockOrderSerializer, CryptoOrderSerializer
from .deposit import rh_update_deposit

from buul_backend.retry_db import retry_on_db_error


@shared_task(name="rh_order_buy_fractional_by_price")
@retry_on_db_error
def rh_order_buy_fractional_by_price(uid, symbol, amount, crypto=False):
    try:
        session, userRobinhoodInfo = r.rh_create_session(uid)
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        return {"error": f"could not find userRobinhoodInfo object for that {uid}"}

    if not crypto:
        result = r.order(session, symbol, 0, "buy", amount=amount)
    else:
        result = r.order_crypto(session, symbol, "buy", None, amount=amount)
    try:
        if not crypto:
            serializer = StockOrderSerializer(data=result)
        else:
            serializer = CryptoOrderSerializer(data=result)
        serializer.is_valid(raise_exception=True)
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        try:
            orders = rh_find_stock_orders_custom(
                uid, amount=amount, created_day_range=2, crypto=crypto
            )
        except Exception as e:
            if isinstance(e, OperationalError):
                raise e
            orders = {"error": f"{str(e)}"}
        return {"error": f"robinhood response {result} caused {str(e)}",
                "recent_crypto_orders" if crypto else "recent_orders": orders}
    return serializer.validated_data


@shared_task(name="rh_order_sell_fractional_by_price")
@retry_on_db_error
def rh_order_sell_fractional_by_price(uid, symbol, amount):
    try:
        session, userRobinhoodInfo = r.rh_create_session(uid)
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        return {"error": f"could not find userRobinhoodInfo object for that {uid}"}

    result = r.order_sell_fractional_by_price(session, symbol, amount)
    
    try:
        serializer = StockOrderSerializer(data=result, many=True)
        serializer.is_valid(raise_exception=True)
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        return {"error": f"robinhood response {result} caused {str(e)}"}
    return serializer.validated_data

@shared_task(name="rh_get_stock_order_info")
@retry_on_db_error
def rh_get_stock_order_info(uid, order_id, crypto=False):
    try:
        session, userRobinhoodInfo = r.rh_create_session(uid)
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        return {"error": f"could not find userRobinhoodInfo object for that {uid}"}
    
    if not crypto:
        result = r.get_stock_order_info(session, order_id)
        try:
            serializer = StockOrderSerializer(data=result)
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            if isinstance(e, OperationalError):
                raise e
            return {"error": f"{str(e)}"}
    else:
        result = r.get_crypto_order_info(session, order_id)
        try:
            serializer = CryptoOrderSerializer(data=result)
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            if isinstance(e, OperationalError):
                raise e
            return {"error": f"{str(e)}"}
    return serializer.validated_data


@shared_task(name="rh_cancel_stock_order")
@retry_on_db_error
def rh_cancel_stock_order(uid, order_id):
    try:
        session, userRobinhoodInfo = r.rh_create_session(uid)
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        return {"error": f"could not find userRobinhoodInfo object for that {uid}"}

    result = r.cancel_stock_order(session, order_id)
    if result:
        return {"error": f"{result}"}
    
    check_if_canceled = r.get_stock_order_info(session, order_id)
    
    try:
        serializer = StockOrderSerializer(data=check_if_canceled)
        serializer.is_valid(raise_exception=True)
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        return {"error": f"{str(e)}"}
    return serializer.validated_data


@shared_task(name="rh_find_stock_orders_custom")
@retry_on_db_error
def rh_find_stock_orders_custom(uid, eq={}, lt={}, gt={}, lte={}, gte={},
                                crypto=False):
    
    try:
        session, userRobinhoodInfo = r.rh_create_session(uid)
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        return {"error": f"could not find userRobinhoodInfo object for that {uid}"}

    if not crypto:
        result = r.find_stock_orders(session)
        try:
            serializer = StockOrderSerializer(data=result, many=True)
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            if isinstance(e, OperationalError):
                raise e
            return {"error": f"robinhood response {result} caused {str(e)}"}
    else:
        result = r.get_all_crypto_orders(session)
        try:
            serializer = CryptoOrderSerializer(data=result, many=True)
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            if isinstance(e, OperationalError):
                raise e
            return {"error": f"robinhood response {result} caused {str(e)}"}
    
    return filter_jsons(serializer.validated_data, eq=eq, lt=lt, gt=gt, 
                        gte=gte, lte=lte, metric_to_return_by="id")


@retry_on_db_error
def rh_save_order_from_order_info(uid, order_id, deposit=None, symbol=None, crypto=False):
    order = rh_get_stock_order_info(uid, order_id, crypto=crypto)

    if symbol == "BTC" and crypto:
        symbol = "BTCUSD"

    if not crypto:
        pending_cancel_open_agent = order["pending_cancel_open_agent"]
        notional_amount = order["total_notional"]["amount"]
        executed_amount = None
        if order["executed_notional"]:
            executed_amount = order["executed_notional"]["amount"]
        user_cancel_request_state = order["user_cancel_request_state"]
        cancel_url = order["cancel"]
    else:
        pending_cancel_open_agent = None
        notional_amount = order["rounded_estimated_notional_with_estimated_fee"]
        executed_amount = None
        if order["rounded_executed_notional_with_fee"] != 0:
            executed_amount = order["rounded_executed_notional_with_fee"]
        user_cancel_request_state = None
        cancel_url = order["cancel_url"]

    user = User.objects.get(id=uid)
    try:
        robinhoodStockOrder = RobinhoodStockOrder.objects.get(
            user = user,
            order_id = order["id"],
            side = order["side"]
        )
        robinhoodStockOrder.cancel = cancel_url
        robinhoodStockOrder.state = order["state"]
        robinhoodStockOrder.updated_at = order["updated_at"]
        robinhoodStockOrder.pending_cancel_open_agent = pending_cancel_open_agent
        robinhoodStockOrder.requested_amount = notional_amount
        robinhoodStockOrder.executed_amount = executed_amount
        robinhoodStockOrder.user_cancel_request_state = user_cancel_request_state
    except:
        if not symbol:
            raise Exception("Cannot created RobinhoodStockOrder without symbol")
        robinhoodStockOrder = RobinhoodStockOrder(
            user = user,
            order_id = order["id"],
            cancel = cancel_url,
            symbol = symbol,
            state = order["state"],
            side = order["side"],
            quantity = order["quantity"],
            created_at = order["created_at"].isoformat(),
            updated_at = order["updated_at"].isoformat(),
            pending_cancel_open_agent = pending_cancel_open_agent,
            requested_amount = notional_amount,
            executed_amount = executed_amount, 
            user_cancel_request_state = user_cancel_request_state
        )
    robinhoodStockOrder.save()

    investment = Investment.objects.get(rh = robinhoodStockOrder)
    if deposit:
        investment.deposit = deposit
        investment.save()
    if not symbol:
        symbol = robinhoodStockOrder.symbol
    
    recent_investment_query = Investment.objects\
        .filter(user=user, date__lte=investment.date)\
        .exclude(id=investment.id)\
        .order_by('-date')
    if recent_investment_query.exists():
        cum_quant = recent_investment_query.first().cumulative_quantities.copy()
        if symbol in cum_quant:
            cum_quant[symbol] += order["quantity"]
        else:
            cum_quant[symbol] = order["quantity"]
    else:
        cum_quant = {symbol: order["quantity"]}
    investment.cumulative_quantities = cum_quant
    investment.save()
    return executed_amount

@retry_on_db_error
def rh_invest(uid, deposit, repeat_day_range=5, ignore_early_access_amount=False,
              crypto=False, ignore_repeats=False, amount_factor=1):
    # check for duplicate deposits
    if deposit.flag:
        raise Exception(f"deposit flagged")
    if deposit.early_access_amount < deposit.amount:
        if not ignore_early_access_amount:
            raise Exception(f"early_access_amount {deposit.early_access_amount} < {deposit.amount}")
    
    if not ignore_repeats:
        potential_db_repeats, potential_rh_repeats = check_repeat_order(
            uid,
            deposit, 
            repeat_day_range,
            crypto=crypto,
            amount_factor=amount_factor
        )
        if potential_db_repeats or potential_rh_repeats:
            raise Exception("potential db repeats {potential_db_repeats} " + 
                            "potential rh repeats {potential_rh_repeats}")

    # check if enough cash 
    account_info = rh_load_account_profile(uid)
    if "error" in account_info:
        return account_info
    elif isinstance(account_info, list):
        if len(account_info) != 1:
            raise Exception(f"we found {len(account_info)} accounts for this user")
        account_info = account_info[0]
    if account_info["portfolio_cash"] < deposit.amount:
        raise Exception(f"Portfolio cash is {account_info["portfolio_cash"]} " +\
                        f"but investment requires {deposit.amount}")
    
    # make order
    try:
        userBrokerageInfo = UserBrokerageInfo.objects.get(user__id=uid)
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        raise Exception(f"no userBrokerageInfo for user {uid}")
    order = rh_order_buy_fractional_by_price(
        uid, 
        userBrokerageInfo.symbol, 
        deposit.amount*amount_factor,
        crypto=crypto
    )

    if userBrokerageInfo.symbol == "BTC" and crypto:
        symbol = "BTCUSD"
    else: 
        symbol = userBrokerageInfo.symbol

    # save order
    if not crypto:
        pending_cancel_open_agent = order["pending_cancel_open_agent"]
        notional_amount = order["total_notional"]["amount"]
        executed_amount = None
        if order["executed_notional"]:
            executed_amount = order["executed_notional"]["amount"]
        user_cancel_request_state = order["user_cancel_request_state"]
        cancel_url = order["cancel"]
    else:
        pending_cancel_open_agent = None
        notional_amount = order["rounded_estimated_notional_with_estimated_fee"]
        executed_amount = None
        if order["rounded_executed_notional_with_fee"] != 0:
            executed_amount = order["rounded_executed_notional_with_fee"]
        user_cancel_request_state = None
        cancel_url = order["cancel_url"]
    
    user = User.objects.get(id=uid)
    robinhoodStockOrder = RobinhoodStockOrder(
        user = user,
        order_id = order["id"],
        cancel = cancel_url,
        symbol = symbol,
        state = order["state"],
        side = order["side"],
        quantity = order["quantity"],
        created_at = order["created_at"],
        updated_at = order["updated_at"],
        pending_cancel_open_agent =pending_cancel_open_agent,
        requested_amount = notional_amount, 
        executed_amount = executed_amount, 
        user_cancel_request_state = user_cancel_request_state
    )
    robinhoodStockOrder.save()

    investment = Investment.objects.get(rh = robinhoodStockOrder)
    deposit.investment = investment
    deposit.save()

    recent_investment_query = Investment.objects\
        .filter(user=user, date__lte=investment.date)\
        .exclude(id=investment.id)\
        .order_by('-date')
    if recent_investment_query.exists():
        cum_quant = recent_investment_query.first().cumulative_quantities.copy()
        if symbol in cum_quant:
            cum_quant[symbol] += order["quantity"]
        else:
            cum_quant[symbol] = order["quantity"]
    else:
        cum_quant = {symbol: order["quantity"]}
    investment.cumulative_quantities = cum_quant
    investment.save()
    

@retry_on_db_error
def check_repeat_order(uid, deposit, repeat_day_range, crypto=False, amount_factor=1):
    # check for duplicate deposit
    lower_limit = timezone.now() - timedelta(days=repeat_day_range)
    old_orders = RobinhoodStockOrder.objects.filter(
        user__id=uid,
        updated_at__gt=lower_limit
    )

    amount_field = "rounded_executed_notional_with_fee" if crypto else "amount"
    potential_db_repeats = []
    for order in old_orders:
        if order.requested_amount == deposit.amount \
           or order.deposit.deposit_id == deposit.deposit_id:
            potential_db_repeats.append(order)
    
    potential_rh_repeats = rh_find_stock_orders_custom(
        uid, 
        lt={amount_field:[(deposit.amount*amount_factor)+0.05]}, 
        gt={
            "created_at":[timezone.now() - timedelta(days=repeat_day_range)],
            amount_field:[(deposit.amount*amount_factor)-0.05]
        },
        crypto=crypto
    )
    return potential_db_repeats, potential_rh_repeats


@receiver(post_save, sender=RobinhoodStockOrder)
@retry_on_db_error
def rhdorder_to_investment(sender, instance, **kwargs):
    try:
        investment = Investment(
            user = instance.user,
            rh = instance, 
            symbol = instance.symbol,
            quantity = instance.quantity,
            buy = instance.side == "buy",
            date = instance.created_at
        )
        investment.save()
    except:
        investment = Investment.objects.get(user = instance.user, rh = instance)
        investment.save()


