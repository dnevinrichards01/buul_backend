import secrets
import string
from datetime import datetime
from dateutil.relativedelta import relativedelta
from django.utils.timezone import make_aware
from django.contrib.auth import get_user_model
from api.models import *
from api.tasks import *

User = get_user_model()
user = User.objects.order_by("id").first()
symbol = "VOO"
buy = True

account_type = "checking" # savings
linked_accounts = rh_get_linked_bank_accounts(
    user.id, 
    eq={"bank_account_type": [account_type]}
)
if len(linked_accounts) == 0:
    raise Exception(
        f"No {account_type} accounts are linked to your Robinhood account.\n" +\
        "Try changing the account_type variable above if a different account type is linked."
    ) 
PlaidCashbackTransaction.objects.create(
    user=user,
    account_id = 'test_data_placeholder',
    transaction_id = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(20)),
    amount = -1.0,
    pending = False,
    iso_currency_code = 'USD',
    date = make_aware(datetime.now()) - relativedelta(months=1),
    authorized_date = make_aware(datetime.now()) - relativedelta(months=1),
    authorized_datetime = make_aware(datetime.now()) - relativedelta(months=1),
    name = 'test cashback'
)

