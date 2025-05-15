from celery import shared_task
import robin_stocks.robinhood as r
from django.utils import timezone
from django.dispatch import receiver
from django.db.models.signals import post_save
from rest_framework.exceptions import ValidationError

from django.db.utils import OperationalError
from datetime import datetime, timedelta
import json

from ..jsonUtils import filter_jsons

from ..models import RobinhoodStockOrder, UserBrokerageInfo, User, Investment, Deposit
from ..serializers.rh import StockOrderSerializer, RobinhoodAccountListSerializer, \
    RobinhoodAccountSerializer
from .deposit import rh_update_deposit

from accumate_backend.retry_db import retry_on_db_error

# transactions



# deposit



# select account to use to withdraw 
# get linked accounts. 
# checking, then savings, then others?
# check what the most recent deposit was made with? (could check in rh, but potentially plaid too...)
# check balance

# once withdraw then check transactions - mb with get to make sure it went through?
# optional maybe?



# (1)
# rewrite some of the methods so that they are in the pattern of the latter ones 
# make a transaction and cancel
# then make sure you can sell a stock (never use this tho)

# (3)
# transaction search function which creates a transaction object

# (4)
# create a deposit and an invest function which saves data to db. 
#   and a transaction object from which we start the deposit,
#   and user info on which investment they want

# (2)
# function to match rh and plaid accounts and pick one (by checking balance)

# match accounts in rh and plaid w mask
# get rh accounts - mask type name longer-name
# get matching plaid accounts
# decide on one (cashback depositted one, then checking, then savings) 
# check their validity 
# store check if rh mask etc matches

# so we will need to store the cashback transaction
# then upon successful triggering of rh deposit, 
#   store from which account we did it from by matching it to a mask / plaid account id
#   log in cache and in celery error message if the deposit was made but function failed
#       then need to search for it ig 
# then keep checking if deposit done, and if it succeeds add that to deposit table
# if fails then same, but retry from the top

# --

# then make the investment in rh and store in a table
#   as before with deposit, log in cache / error message if you made the investment but error happened AFTER
#   including if you sent a message but got no response. search for that investment b4 retrying

# then keep checking, and as before store if is failure or success. 
# if failure then try this investment step only again 

# -------

# get transactions summarizing code to work

# get the graph data thing working

# get redis and backend working on AWS
# in the process figure out how to do all your debuging etc on AWS from VSCode
# get Plaid approval

# work on plaid link flow + app. 
# then test on ourselves till we're ready

# --------

# while waiting for app approval, change deployment to be manual. 
# and create a testing environment where we can test deployments
# mb even write some tests and work on logging if time
# and eventually want to increasingly automate backend
#   but if deposit or invest fails then we look at it MANUALLY. ALWAYS. set up logging





# json filtering utility functions


# later on need to look into the pagination in get request in robin stocks
# optimize getting only data we want rather than pulling it all here, serializing it all..
# mb scroll to end to get most recent? or mb we only need the start...



# investing
# order, track it

# if it errors, then upon repeat we search for an identical investment 
# to what we want to make being made in the past 3 days
# if found, do nothing.

# rh endpoints

# plaid get accounts / items???
@shared_task(name="rh_order_buy_fractional_by_price")
@retry_on_db_error
def rh_order_buy_fractional_by_price(uid, symbol, amount):
    import pdb
    breakpoint()

    # uid = kwargs.pop('uid')

    try:
        session, userRobinhoodInfo = r.rh_create_session(uid)
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        return {"error": f"could not find userRobinhoodInfo object for that {uid}"}

    # result = r.order_buy_fractional_by_price(session, symbol, amount)
    result = r.order(session, symbol, 0, "buy", amount=amount)

    try:
        serializer = StockOrderSerializer(data=result)
        serializer.is_valid(raise_exception=True)
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        try:
            orders = rh_find_stock_orders_custom(uid, amount=amount, created_day_range=2)
        except Exception as e:
            if isinstance(e, OperationalError):
                raise e
            orders = {"error": f"{str(e)}"}
        return {"error": f"robinhood response {result} caused {str(e)}",
                "recent_orders": orders}
    return serializer.validated_data

# note that you must trade DURING hours
@shared_task(name="rh_order_sell_fractional_by_price")
@retry_on_db_error
def rh_order_sell_fractional_by_price(uid, symbol, amount):
    import pdb
    breakpoint()

    # uid = kwargs.pop('uid')

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
def rh_get_stock_order_info(uid, order_id):
    import pdb
    breakpoint()

    # uid = kwargs.pop('uid')

    try:
        session, userRobinhoodInfo = r.rh_create_session(uid)
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        return {"error": f"could not find userRobinhoodInfo object for that {uid}"}
    
    result = r.get_stock_order_info(session, order_id)
    
    try:
        serializer = StockOrderSerializer(data=result)
        serializer.is_valid(raise_exception=True)
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        return {"error": f"{str(e)}"}
    return serializer.validated_data

# make something with improved search ability
@shared_task(name="rh_cancel_stock_order")
@retry_on_db_error
def rh_cancel_stock_order(uid, order_id):
    import pdb
    breakpoint()

    # uid = kwargs.pop('uid')

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

    
    # try:
    #     serializer = StockOrderSerializer(data=result)
    #     serializer.is_valid(raise_exception=True)
    # except Exception as e:
        # if isinstance(e, OperationalError):
        #     raise e
    #     return {"error": str(e)}
    # return serializer.validated_data

# and another helper one which filters them by any given attribute
@shared_task(name="rh_find_stock_orders_custom")
@retry_on_db_error
def rh_find_stock_orders_custom(uid, eq={}, lt={}, gt={}, lte={}, gte={}):
    
    try:
        session, userRobinhoodInfo = r.rh_create_session(uid)
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        return {"error": f"could not find userRobinhoodInfo object for that {uid}"}

    result = r.find_stock_orders(session)

    try:
        serializer = StockOrderSerializer(data=result, many=True)
        serializer.is_valid(raise_exception=True)
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        return {"error": f"robinhood response {result} caused {str(e)}"}
    
    return filter_jsons(serializer.validated_data, eq=eq, lt=lt, gt=gt, 
                        gte=gte, lte=lte, metric_to_return_by="id")



# invest based on a deposit / cashback

@retry_on_db_error
def rh_save_order_from_order_info(uid, deposit, order_id, symbol):
    import pdb; breakpoint()
    order = rh_get_stock_order_info(uid, order_id)

    if order["executed_notional"]:
        executed_amount = order["executed_notional"]["amount"]
    else:
        executed_amount = None

    user = User.objects.get(id=uid)
    try:
        robinhoodStockOrder = RobinhoodStockOrder.objects.get(
            user = user,
            order_id = order["id"],
            side = order["side"]
        )
        robinhoodStockOrder.cancel = order["cancel"]
        robinhoodStockOrder.state = order["state"]
        robinhoodStockOrder.updated_at = order["updated_at"]
        robinhoodStockOrder.pending_cancel_open_agent = order["pending_cancel_open_agent"]
        robinhoodStockOrder.requested_amount = order["total_notional"]["amount"]
        robinhoodStockOrder.executed_amount = executed_amount
        robinhoodStockOrder.user_cancel_request_state = order["user_cancel_request_state"]
    except:
        robinhoodStockOrder = RobinhoodStockOrder(
            user = user,
            order_id = order["id"],
            cancel = order["cancel"],
            symbol = symbol,
            state = order["state"],
            side = order["side"],
            quantity = order["quantity"],
            created_at = order["created_at"].isoformat(),
            updated_at = order["updated_at"].isoformat(),
            pending_cancel_open_agent = order["pending_cancel_open_agent"],
            requested_amount = order["total_notional"]["amount"], 
            executed_amount = executed_amount, 
            user_cancel_request_state = order["user_cancel_request_state"]
        )
    robinhoodStockOrder.save()

    investment = Investment.objects.get(rh = robinhoodStockOrder)
    investment.deposit = deposit
    investment.save()

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
def rh_invest(uid, deposit, repeat_day_range=5, 
              ignore_early_access_amount=False):
    
    import pdb; breakpoint()

    # check for duplicate deposits
    
    if deposit.flag:
        raise Exception(f"deposit flagged")
    if deposit.early_access_amount < deposit.amount:
        if not ignore_early_access_amount:
            raise Exception(f"early_access_amount {deposit.early_access_amount} < {deposit.amount}")
        
    
    import pdb; breakpoint()
    
    potential_db_repeats, potential_rh_repeats = check_repeat_order(
        uid,
        deposit, 
        repeat_day_range
    )
    if potential_db_repeats or potential_rh_repeats:
        raise Exception("potential db repeats {potential_db_repeats} " + 
                        "potential rh repeats {potential_rh_repeats}")
    
    import pdb; breakpoint()

    # check if enough cash 
    account_info_response = rh_load_account_profile(uid)
    if "error" in account_info_response:
        return account_info_response
    elif isinstance(account_info_response, list):
        if len(account_info_response) != 1:
            raise Exception(f"we found {len(account_info_response)} accounts for this user")
        account_info = account_info_response[0]
    if account_info[0]["buying_power"] < deposit.amount \
        and account_info[0]["portfolio_cash"] < deposit.amount:
        raise Exception(f"Buying power is {account_info[0]["buying_power"]} " +\
                        f"and portfolio cash is {account_info[0]["portfolio_cash"]} " +\
                        f"but investment requires {deposit.amount}")
    
    try:
        userBrokerageInfo = UserBrokerageInfo.objects.get(user__id=uid)
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        raise Exception(f"no userBrokerageInfo for user {uid}")
    
    import pdb; breakpoint()
    order = rh_order_buy_fractional_by_price(
        uid, 
        userBrokerageInfo.symbol, 
        deposit.amount
    )
    if order["executed_notional"]:
        executed_amount = order["executed_notional"]["amount"]
    else:
        executed_amount = None

    import pdb; breakpoint()
    
    user = User.objects.get(id=uid)
    robinhoodStockOrder = RobinhoodStockOrder(
        user = user,
        order_id = order["id"],
        cancel = order["cancel"],
        symbol = userBrokerageInfo.symbol,
        state = order["state"],
        side = order["side"],
        quantity = order["quantity"],
        created_at = order["created_at"],
        updated_at = order["updated_at"],
        pending_cancel_open_agent = order["pending_cancel_open_agent"],
        requested_amount = order["total_notional"]["amount"], 
        executed_amount = executed_amount, 
        user_cancel_request_state = order["user_cancel_request_state"]
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
        if userBrokerageInfo.symbol in cum_quant:
            cum_quant[userBrokerageInfo.symbol] += order["quantity"]
        else:
            cum_quant[userBrokerageInfo.symbol] = order["quantity"]
    else:
        cum_quant = {userBrokerageInfo.symbol: order["quantity"]}
    investment.cumulative_quantities = cum_quant
    investment.save()
    

@retry_on_db_error
def check_repeat_order(uid, deposit, repeat_day_range):
    # check for duplicate deposit
    lower_limit = timezone.now() - timedelta(days=repeat_day_range)
    old_orders = RobinhoodStockOrder.objects.filter(
        user__id=uid,
        updated_at__gt=lower_limit
    )
    potential_db_repeats = []
    for order in old_orders:
        if order.requested_amount == deposit.amount \
           or order.deposit.deposit_id == deposit.deposit_id:
            potential_db_repeats.append(order)
    
    potential_rh_repeats = rh_find_stock_orders_custom(
        uid, 
        lt={"amount":[deposit.amount+0.05]}, 
        gt={
            "created_at":[timezone.now() - timedelta(days=repeat_day_range)],
            "amount":[deposit.amount-0.05]
        }
    )
    return potential_db_repeats, potential_rh_repeats

@retry_on_db_error
def rh_load_account_profile(uid):

    import pdb
    breakpoint()

    try:
        session, userRobinhoodInfo = r.rh_create_session(uid)
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        return {"error": f"could not find userRobinhoodInfo object for that {uid}"}
    result = r.load_account_profile(session)

    try:
        serializer = RobinhoodAccountListSerializer(data=result)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data
    except ValidationError as e:
        try:
            serializer = RobinhoodAccountSerializer(data=result)
            serializer.is_valid(raise_exception=True)
            return serializer.validated_data
        except Exception as e:
            if isinstance(e, OperationalError):
                raise e
            return {"error": f"{str(e)}"}
    except Exception as e:
        if isinstance(e, OperationalError):
            raise e
        return {"error": f"{str(e)}"}

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


