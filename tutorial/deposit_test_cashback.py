from api.models import *
from robin_stocks.models import *
from api.tasks import *
from django.db.models import Q

user = User.objects.first()

# cashback = PlaidCashbackTransaction.objects.filter(user=user, deposit=None, flag=False)
# cashback.count()
# cashback.values('amount', 'name', 'date')
cashback = PlaidCashbackTransaction.objects.filter(user=user, deposit=None, flag=False)

limit = 1 # maximum amount that can be deposited in the past month
# # uncomment to invest more than limit
# cumulative_amount_query = Deposit.objects.filter(
#     user__id=user.id,
#     created_at__gt=timezone.now()-relativedelta(months=1)
# )
# cumulative_amount_query.values('created_at','amount')
# cumulative_amount = cumulative_amount_query.aggregate(cumulative_amount=Sum('amount')).get('cumulative_amount') or 0
# limit = cumulative_amount + -1 * sum([x.amount for x in cashback])

try:
    rh_deposit(
        user.id,
        transactions=cashback, 
        limit=limit, 
        ignore_overdraft_protection=True, # protection requires connection with plaid,
        force=False # True if you want to deposit same amount within a month
    ) 
except Exception as e:
    if str(e)[:19] == "potential db repeat":
        raise Exception(
            "You have recently deposited the same amount, " +\
            "which has been identified as a possible repeat.\n" +\
            "To override this, set force=True"
        )
deposit = Deposit.objects.filter(user= user).order_by('-created_at').first()
rh_update_deposit(
    user.id, 
    deposit.rh.deposit_id, 
    get_bank_info=False # getting bank info requires connection with plaid
)
