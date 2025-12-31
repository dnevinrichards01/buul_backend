from api.models import *
from robin_stocks.models import *
from api.tasks import *
from django.db.models import Q

user = User.objects.first()
deposit = Deposit.objects.filter(user= user).order_by('-created_at').first()
cashback = PlaidCashbackTransaction.objects.filter(user=user, deposit=deposit)

crypto = False
if UserBrokerageInfo.objects.get(user=user).symbol == "BTC":
    crypto = True

try:
    rh_invest(
        user.id, 
        deposit, 
        crypto=crypto,
        ignore_repeats=False, # True if want to invest same amount within <repeat_day_range> days
        repeat_day_range=5
    )
except Exception as e:
    if str(e)[:19] == "potential db repeat":
        raise Exception(
            "You have recently invested the same amount, " +\
            "which has been identified as a possible repeat.\n" +\
            "To override this, set ignore_repeats=True"
        )

investment = Investment.objects.filter(user=user).order_by('-date').first()
rh_save_order_from_order_info(
    user.id, 
    investment.rh.order_id, 
    deposit=deposit, 
    symbol=UserBrokerageInfo.objects.get(user=user).symbol,
    crypto=crypto
) 


