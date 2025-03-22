from celery import shared_task, chord
from django.core.cache import cache 
from django.utils import timezone
import json
from ..models import User, StockData, Investments, UserInvestmentGraph

from django.db.models import OuterRef, Subquery, JSONField, F
from django.contrib.postgres.aggregates import JSONBAgg
from api.yahooRapidApiClient import fpm_client, FPMClient, FPMUtils
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from zoneinfo import ZoneInfo

from django.apps import apps




@shared_task(name="refresh_stock_data_by_interval")
def refresh_stock_data_by_interval(symbols=["VOO", "VOOG", "QQQ", "IBIT"], 
                       interval="1d"):
    import pdb
    breakpoint()


    # decide whether to refresh, and when to refresh from
    most_recent_refresh_date_query = StockData.objects.all()
    if most_recent_refresh_date_query.exists():
        most_recent_refresh_date = most_recent_refresh_date_query\
            .sort_by("-date")[:1].date
        most_recent_refresh_date_rounded = FPMUtils.round_date_down(
            most_recent_refresh_date.replace(tzinfo=ZoneInfo("UTC")), 
            granularity=interval
        )
        curr_date_rounded = FPMUtils.round_date_down(
            timezone.now(), 
            granularity=interval
        )
        # if current date is more recent than last refresh, then must refresh
        if curr_date_rounded > most_recent_refresh_date_rounded:
            oldest_queryable_data = curr_date_rounded - FPMUtils.get_maximum_range(interval)
            # refresh from most recent refresh date. 
            # if that is too far in the past, refresh from oldest possible date
            start_date_rounded = max(
                oldest_queryable_data, 
                most_recent_refresh_date_rounded
            )
        else:
            return
    else:
        # if this is our first time then refresh from right now. 
        curr_date_rounded = FPMUtils.round_date_down(
            timezone.now(), 
            granularity=interval
        )
        start_date_rounded = curr_date_rounded

    
    # for each security...
    for symbol in symbols:
        # fetch data...
        response = fpm_client.get_historical(symbol, start_date_rounded, 
                                            timezone.now(), interval)
        # and save it to db
        for item in response:
            item_date = FPMUtils.no_timezone_to_with_timezone(item["date"], interval)
            item_price = item["close"]
            stockData, created = StockData.objects.get_or_create(
                date = item_date
            )
            if stockData[symbol]:
                continue
            else:
                stockData[symbol] = item_price 
                stockData.save()
    return 

# on a timer?
@shared_task(name="delete_non_closing_times")
def delete_non_closing_times():
    for interval in ["1m", "1h", "1d", "1w", "1M"]:
        current_date_rounded = FPMUtils.round_date_down(
            timezone.now(), 
            granularity=interval
        )
        FPMUtils.delete_non_closing_times(current_date_rounded, interval)

@shared_task(name="get_graph_data")
def get_graph_data(uid, start_date, symbols=["VOO", "VOOG", "QQQ", "IBIT"]):
    import pdb 
    breakpoint()
    
    user = User.objects.get(id=uid)

    cumulative_quantity_subquery = (
        Investments.objects.filter(
            user=user,
            date__lte=OuterRef("date")
        )
        .order_by("-date")
        .values("cumulative_quantities")[:1]
    )

    # Annotate Investments with the JSON-aggregated cumulative quantities
    queryset = StockData.objects \
        .filter(date__gte=start_date) \
        .annotate(
            cumulative_quantities=Subquery(cumulative_quantity_subquery)
        )

    data = []
    quantities = {}
    for stockData in queryset:
        quantities = stockData.cumulative_quantities or {}
        price = 0
        for symbol in quantities:
            price += stockData[symbol] * quantities[symbol]
        data.append({
            "date": stockData.date.strftime("%Y-%m-%d %H:%M:%S"),
            "price": price
        })
    
    breakpoint()

    if data:
        userInvestmentGraph, created = UserInvestmentGraph.objects.get_or_create(
            user = user
        )
        if created:
            userInvestmentGraph.data = data
        else:
            new_data_index = 0 
            for i, investment in enumerate(userInvestmentGraph.data):
                investment_date = FPMUtils.no_timezone_to_with_timezone(investment["date"], "1m")
                if investment_date > start_date:
                    userInvestmentGraph.data[i] = data[new_data_index]
                    new_data_index += 1
        userInvestmentGraph.save()  
    
    cache.delete(f"uid_{uid}_get_investment_graph_data")
    cache.set(
        f"uid_{uid}_get_investment_graph_data",
        json.dumps({"success": True, "error": None}),
        timeout=120
    )
            