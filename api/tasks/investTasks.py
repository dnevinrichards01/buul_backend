from celery import shared_task, chain
from accumate_backend.settings import TWILIO_PHONE_NUMBER
import robin_stocks.robinhood as r
from django.core.cache import cache 
from django.core.mail import send_mail
from django.utils import timezone

from django.dispatch import receiver
from django.db.models.signals import post_save

from ..plaid_client import plaid_client
# from ..twilio_client import twilio_client
from ..jsonUtils import filter_jsons

from datetime import datetime, timedelta
import json

from ..models import RobinhoodStockOrder, UserBrokerageInfo, User, Investment, Deposit
from ..serializers.rhSerializers import StockOrderSerializer



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
def rh_order_buy_fractional_by_price(uid, symbol, amount):
    import pdb
    breakpoint()

    # uid = kwargs.pop('uid')

    try:
        session, userRobinhoodInfo = r.rh_create_session(uid)
    except Exception as e:
        return {"error": f"could not find userRobinhoodInfo object for that {uid}"}

    result = r.order_buy_fractional_by_price(session, symbol, amount)

    try:
        serializer = StockOrderSerializer(data=result)
        serializer.is_valid(raise_exception=True)
    except Exception as e:
        try:
            orders = rh_find_stock_orders_custom(uid, amount=amount, created_day_range=2)
        except Exception as e:
            orders = {"error": f"{str(e)}"}
        return {"error": f"robinhood response {result} caused {str(e)}",
                "recent_orders": orders}
    return serializer.validated_data

# note that you must trade DURING hours
@shared_task(name="rh_order_sell_fractional_by_price")
def rh_order_sell_fractional_by_price(uid, symbol, amount):
    import pdb
    breakpoint()

    # uid = kwargs.pop('uid')

    try:
        session, userRobinhoodInfo = r.rh_create_session(uid)
    except Exception as e:
        return {"error": f"could not find userRobinhoodInfo object for that {uid}"}

    result = r.order_sell_fractional_by_price(session, symbol, amount)
    
    try:
        serializer = StockOrderSerializer(data=result, many=True)
        serializer.is_valid(raise_exception=True)
    except Exception as e:
        return {"error": f"robinhood response {result} caused {str(e)}"}
    return serializer.validated_data

@shared_task(name="rh_get_stock_order_info")
def rh_get_stock_order_info(uid, order_id):
    import pdb
    breakpoint()

    # uid = kwargs.pop('uid')

    try:
        session, userRobinhoodInfo = r.rh_create_session(uid)
    except Exception as e:
        return {"error": f"could not find userRobinhoodInfo object for that {uid}"}
    
    result = r.get_stock_order_info(session, order_id)
    
    try:
        serializer = StockOrderSerializer(data=result)
        serializer.is_valid(raise_exception=True)
    except Exception as e:
        return {"error": f"{str(e)}"}
    return serializer.validated_data

#make something with improved search ability
@shared_task(name="rh_cancel_stock_order")
def rh_cancel_stock_order(uid, order_id):
    import pdb
    breakpoint()

    # uid = kwargs.pop('uid')

    try:
        session, userRobinhoodInfo = r.rh_create_session(uid)
    except Exception as e:
        return {"error": f"could not find userRobinhoodInfo object for that {uid}"}

    result = r.cancel_stock_order(session, order_id)
    if result:
        return {"error": f"{result}"}
    
    check_if_canceled = r.get_stock_order_info(session, order_id)
    
    try:
        serializer = StockOrderSerializer(data=check_if_canceled)
        serializer.is_valid(raise_exception=True)
    except Exception as e:
        return {"error": f"{str(e)}"}
    return serializer.validated_data

    
    # try:
    #     serializer = StockOrderSerializer(data=result)
    #     serializer.is_valid(raise_exception=True)
    # except Exception as e:
    #     return {"error": str(e)}
    # return serializer.validated_data

# and another helper one which filters them by any given attribute
@shared_task(name="rh_find_stock_orders_custom")
def rh_find_stock_orders_custom(uid, amount=None, currency_code=None, 
                                instrument_id=None, created_day_range=None, 
                                updated_day_range=None):
    
    try:
        session, userRobinhoodInfo = r.rh_create_session(uid)
    except Exception as e:
        return {"error": f"could not find userRobinhoodInfo object for that {uid}"}

    result = r.find_stock_orders(session)

    try:
        serializer = StockOrderSerializer(data=result, many=True)
        serializer.is_valid(raise_exception=True)
    except Exception as e:
        return {"error": f"robinhood response {result} caused {str(e)}"}
    
    
    eq={}
    if amount:
        eq["amount"] = [amount]
    if instrument_id:
        eq["instrument_id"] = [instrument_id]
    if currency_code:
        eq["currency_code"] = [currency_code]

    gte = {}
    now_utc = timezone.now()
    if created_day_range:
        created_lower_limit = now_utc - timedelta(days=created_day_range)
        gte["created_at"] = [created_lower_limit]
    if updated_day_range:
        updated_lower_limit = now_utc - timedelta(days=updated_day_range)
        gte["updated_at"] = [updated_lower_limit]
    return filter_jsons(serializer.validated_data, eq=eq, gte=gte, 
                        metric_to_return_by="id")



# invest based on a deposit / cashback

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
        robinhoodStockOrder.updated_at = order["updated_at"],
        robinhoodStockOrder.pending_cancel_open_agent = order["pending_cancel_open_agent"],
        robinhoodStockOrder.requested_amount = order["total_notional"]["amount"], 
        robinhoodStockOrder.executed_amount = executed_amount, 
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

    recent_deposit_query = Deposit.objects\
        .filter(user=user, created_at__lt=deposit.created_at)\
        .order_by('-date')
    if recent_deposit_query.exists():
        cum_quant = recent_deposit_query.first().cumulative_quantities.copy()
        cum_quant[symbol] += order["quantity"]
    else:
        cum_quant = {symbol: order["quantity"]}
    investment.cumulative_quantities = cum_quant
    investment.save()

def rh_invest(uid, deposit, repeat_day_range=5):
    # check for duplicate deposits
    if deposit.investment:
        raise Exception(f"deposit already invested")

    if deposit.state != "completed":
        raise Exception(f"deposit not yet completed. state: {deposit.state}")
    potential_db_repeats, potential_rh_repeats = check_repeat_order(
        uid,
        deposit, 
        repeat_day_range
    )
    if potential_db_repeats or potential_rh_repeats:
        raise Exception("potential db repeats {potential_db_repeats} " + 
                        "potential rh repeats {potential_rh_repeats}")
    
    try:
        userBrokerageInfo = UserBrokerageInfo.objects.get(user__id=id)
    except Exception as e:
        raise Exception(f"no userBrokerageInfo for user {uid}")
    
    order = rh_order_buy_fractional_by_price(
        uid, 
        userBrokerageInfo.symbol, 
        deposit.amount
    )
    if order["executed_notional"]:
        executed_amount = order["executed_notional"]["amount"]
    else:
        executed_amount = None

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

    recent_deposit_query = Deposit.objects\
        .filter(user=user, created_at__lt=deposit.created_at)\
        .order_by('-date')
    if recent_deposit_query.exists():
        cum_quant = recent_deposit_query.first().cumulative_quantities.copy()
        cum_quant[userBrokerageInfo.symbol] += order["quantity"]
    else:
        cum_quant = {userBrokerageInfo.symbol: order["quantity"]}
    investment.cumulative_quantities = cum_quant
    investment.save()

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



@receiver(post_save, sender=RobinhoodStockOrder)
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