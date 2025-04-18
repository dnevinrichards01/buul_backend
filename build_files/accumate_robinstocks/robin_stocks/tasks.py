from celery import shared_task
from datetime import datetime, timedelta
from django.utils.timezone import now
from django.apps import apps

from django.http import JsonResponse
import json

import robin_stocks.robinhood as r
from django.core.cache import cache



@shared_task(name="refresh_robinhood")
def refresh_robinhood():
    UserRobinhoodInfo = apps.get_model("robin_stocks", "UserRobinhoodInfo")
    query_set = UserRobinhoodInfo.objects.all()
    for brokerageInfo in query_set:
        if brokerageInfo.issued_time + timedelta(minutes=5) < now():
            brokerageInfo.refresh()
    return "refreshed robinhood access tokens"

@shared_task(name="login_robinhood")
def login_robinhood(**kwargs):
    import robin_stocks.robinhood as r
    kwargs['session'] = r.create_session()
    res = r.login(**kwargs)
    if 'access_token' in res:
        return "access token recieved, result cached"
    else: 
        return res


