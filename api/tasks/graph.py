from celery import shared_task, chord
from django.apps import apps
from django.core.cache import cache 
from django.utils import timezone

from ..models import User, StockData, Investment, UserInvestmentGraph

from django.db.models import OuterRef, Subquery

from api.apis.fmp import fpm_client, FPMUtils

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from zoneinfo import ZoneInfo
import json

from buul_backend.retry_db import retry_on_db_error

@shared_task(name="refresh_stock_data_by_interval")
@retry_on_db_error
def refresh_stock_data_by_interval(symbols=["VOO", "VOOG", "QQQ", "IBIT", "BTC", "BTCUSD"], 
                       interval="1d", refresh_all=False):
    # import pdb
    # breakpoint()

    curr_minute_rounded = FPMUtils.round_date_down(
            timezone.now(), 
            granularity="1m"
        )

    # decide whether to refresh, and when to refresh from
    most_recent_refresh_date_query = StockData.objects.all()
    if not refresh_all and most_recent_refresh_date_query.exists():
        most_recent_refresh_date = most_recent_refresh_date_query\
            .order_by("-date").first().date
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
        # if this is our first time
        start_date_rounded = FPMUtils.round_date_down(
            timezone.now() - relativedelta(years=5), 
            granularity=interval
        )

    # for each security...
    for symbol in symbols:
        # fetch data...
        response = fpm_client.get_historical(symbol, start_date_rounded, 
                                            timezone.now(), interval)
        # and save it to db
        for item in response:
            item_date = FPMUtils.no_timezone_to_with_timezone(item["date"], interval)
            if item_date < start_date_rounded:
                continue
            item_price = item["close"]
            stockData, created = StockData.objects.get_or_create(
                date = item_date
            )
            if stockData[symbol]:
                continue
            else:
                stockData[symbol] = item_price 
                stockData.save()

    # for symbol in symbols:

        null_prices = StockData.objects.filter(**{
            f"{symbol}__isnull": True,
            "date__gte": start_date_rounded
        })
        if null_prices.exists():
            most_recent_prices = null_prices.annotate(
                prev_price = Subquery((
                    StockData.objects.filter(**{
                        f"{symbol}__isnull": False,
                        "date__lte": OuterRef("date")
                    })
                    .order_by("-date")
                    .values(symbol)[:1]
                ))
            )
            for item in most_recent_prices:
                item[symbol] = item.prev_price
            StockData.objects.bulk_update(most_recent_prices, [symbol])


        null_prices = StockData.objects.filter(**{
            f"{symbol}__isnull": True,
            "date__gte": start_date_rounded
        })
        if null_prices.exists():
            prices_immediately_after = null_prices.annotate(
                price_immediately_after = Subquery((
                    StockData.objects.filter(**{
                        f"{symbol}__isnull": False,
                        "date__gte": OuterRef("date")
                    })
                    .order_by("date")
                    .values(symbol)[:1]
                ))
            )
            for item in prices_immediately_after:
                item[symbol] = item.price_immediately_after
            StockData.objects.bulk_update(prices_immediately_after, [symbol])

        # if interval == "1m":
        #     time_gap_query = StockData.objects.filter(
        #         date__gte=curr_minute_rounded-relativedelta(hours=24))\
        #         .annotate(**{
        #             "next_date": Window(
        #                 expression=Lead('date'),
        #                 order_by=F('date').asc()
        #             ),
        #             "time_gap": ExpressionWrapper(
        #                 F('next_date') - F('date'),
        #                 output_field=DurationField()
        #             )
        #         }) \
        #         .filter(time_gap__gt=relativedelta(minutes=1))
        #     for item in time_gap_query:
        #         created = True
        #         item_date = item.date + relativedelta(minutes=1)
        #         while created and item_date < item.next_date:
        #             stockData, created = StockData.objects.get_or_create(
        #                 date = item_date,
        #                 defaults={symbol: item[symbol]}
        #             )
        #             item_date += relativedelta(minutes=1)

    return "done"

@retry_on_db_error
def refresh_stock_data_all():
    for interval in ["1m", "1h", "1d"]:
        refresh_stock_data_by_interval(interval=interval, refresh_all=True)
    delete_non_closing_times()

# on a timer?
@shared_task(name="delete_non_closing_times")
@retry_on_db_error
def delete_non_closing_times():
    for interval in ["1m", "1h", "1d", "1w", "1M"]:
        current_date_rounded = FPMUtils.round_date_down(
            timezone.now(), 
            granularity="1m"
        )
        FPMUtils.delete_non_closing_times(current_date_rounded, interval)

@shared_task(name="get_graph_data")
@retry_on_db_error
def get_graph_data(uid):
    try:
        # import pdb 
        # breakpoint()

        user = User.objects.get(id=uid)

        # the last time they requested graph data
        last_saved_date_query = UserInvestmentGraph.objects.filter(user=user)\
            .order_by('-date')
        if last_saved_date_query.exists():
            last_saved_date = last_saved_date_query.first()
            start_date = FPMUtils.round_date_down(
                last_saved_date.date, 
                granularity="1min"
            )
        # if they've never requested graph data, start from beginning
        else:
            # their first investment
            first_investment_date_query = Investment.objects.filter(user=user)\
                .order_by("date")
            if first_investment_date_query.exists():
                first_investment_date = first_investment_date_query.first().date
            else:
                first_investment_date = None

            # date five years ago
            five_years_ago = FPMUtils.round_date_down(
                timezone.now() - relativedelta(years=5), 
                granularity="1min"
            )

            # start_date = whichever is oldest
            if first_investment_date is None:
                start_date = five_years_ago
            else:
                start_date = min(first_investment_date, five_years_ago)
        
        cumulative_quantity_subquery = (
            Investment.objects.filter(
                user=user,
                date__lte=OuterRef("date")
            )
            .order_by("-date")
            .values("cumulative_quantities")[:1]
        )
        # Annotate Investment with the JSON-aggregated cumulative quantities
        queryset = StockData.objects \
            .filter(date__gte=start_date) \
            .annotate(
                cumulative_quantities=Subquery(cumulative_quantity_subquery)
            )
        
        # breakpoint()
        
        for stockData in queryset:
            quantities = stockData.cumulative_quantities or {}
            price = 0
            for symbol in quantities:
                price += stockData[symbol] * (quantities[symbol] or 0)
            userInvestmentGraph, created = UserInvestmentGraph.objects.get_or_create(
                user = user,
                date = stockData.date,
                defaults = {'value': price}
            )
            if created:
                userInvestmentGraph.save()
        
        # breakpoint()
        
        cache.delete(f"uid_{uid}_get_investment_graph_data")
        cache.set(
            f"uid_{uid}_get_investment_graph_data",
            json.dumps({"success": "calculated and saved", "error": None}),
            timeout=120
        )
    except ImportError as e:
        cache.delete(f"uid_{uid}_get_investment_graph_data")
        cache.set(
            f"uid_{uid}_get_investment_graph_data",
            json.dumps({"success": None, "error": f"error {str(e)}"}),
            timeout=120
        )
            