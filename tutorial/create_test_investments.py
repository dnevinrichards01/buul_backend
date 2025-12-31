import random
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

start_date = make_aware(datetime.now()) - relativedelta(years=2)
num_months = 24
running_total = 0.0

for i in range(num_months):
    quantity = round(random.uniform(0.1, 1.0), 4)
    running_total += quantity
    investment_date = start_date + relativedelta(months=i)
    Investment.objects.create(
        user=user,
        rh=None,
        deposit=None,
        symbol=symbol,
        quantity=quantity,
        cumulative_quantities={
            symbol: round(running_total, 4)
        },
        date=investment_date,
        buy=buy,
    )
Investment.objects.all().delete()
UserInvestmentGraph.objects.all().delete()