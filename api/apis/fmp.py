from buul_backend.settings import FMP_KEY

from django.utils import timezone
from django.db.models import OuterRef, Subquery

from api.models import StockData, UserInvestmentGraph

import requests
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from zoneinfo import ZoneInfo
import json


class FPMUtils:
    interval_char_to_str = {
        "m": "Minute",
        "h": "Hour",
        "d": "Day",
        "w": "Day",
        "M": "Month"
    }
    # i think we'll have a main order table which links to other ones with an id/etc?
    brokerage_to_order_model = {
        "robinhood": "RobinhoodStockOrder"
    }

    @classmethod
    def round_date_down(cls, date, granularity="1d"):
        n = int(granularity[0])
        unit = granularity[1]
        
        if unit == "m":
            delta = relativedelta(minutes=n-1)
            return date.replace(second=0, microsecond=0) - delta
        elif unit == "h":
            delta = relativedelta(hours=n-1)
            return date.replace(minute=0, second=0, microsecond=0) - delta
        elif unit == "d":
            delta = relativedelta(days=n-1)
            return date.replace(hour=0, minute=0, second=0, microsecond=0) - delta
        elif unit == "w":
            days_since_start_of_week = relativedelta(days=date.weekday())
            delta = relativedelta(weeks=n-1)
            return date.replace(
                hour=0, 
                minute=0, 
                second=0, 
                microsecond=0
            ) - days_since_start_of_week - delta
        elif unit == "M":
            delta = relativedelta(months=n-1)
            return date.replace(
                day=1,
                hour=0, 
                minute=0, 
                second=0, 
                microsecond=0
            ) - delta

    @classmethod
    def get_time_delta(cls, delta_str):
        n = delta_str[0]
        unit = delta_str[1]
        
        if unit == "m":
            return relativedelta(minutes=n)
        elif unit == "h":
            return relativedelta(hours=n)
        elif unit == "d":
            return relativedelta(days=n)
        elif unit == "w":
            return relativedelta(weeks=n)
        elif unit == "M":
            return relativedelta(month=n)
    
    @classmethod
    def get_maximum_range(cls, delta_str):
        n = delta_str[0]
        unit = delta_str[1]
        
        if unit == "m":
            return relativedelta(days=1)
        elif unit == "h":
            return relativedelta(months=3)
        elif unit == "d":
            return relativedelta(years=5)
        else:
            raise ValueError("unit must be from ['m', 'h', 'd']")
    
    @classmethod
    def no_timezone_to_with_timezone(cls, date_str, interval):
        if interval[1] in ["m", "h"]:
            naive_dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S") 
        else:
            naive_dt = datetime.strptime(date_str, "%Y-%m-%d")
        eastern_dt = naive_dt.replace(tzinfo=ZoneInfo("America/New_York"))
        utc_dt = eastern_dt.astimezone(ZoneInfo("UTC"))
        return utc_dt
    
    @classmethod
    def delete_non_closing_times(cls, current_date_rounded, interval):
        if interval[1] == "m":
            return
        if interval[1] == "h":
            delta = relativedelta(months=3)
            kwargs = {
                "date__hour": OuterRef("date__hour"),
                "date__date": OuterRef("date__date")
            }
        elif interval[1] == "d":
            delta = relativedelta(years=1)
            kwargs = {
                "date__date": OuterRef("date__date")
            }
        elif interval[1] == "w":
            delta = relativedelta(years=1)
            kwargs = {
                "date__week": OuterRef("date__week"),
                "date__year": OuterRef("date__year")
            }
        elif interval[1] == "M":
            delta = relativedelta(years=5)
            kwargs = {
                "date__month": OuterRef("date__month"),
                "date__year": OuterRef("date__year")
            }
        
        latest_date_subquery = StockData.objects.filter(**kwargs) \
            .order_by("-date").values("date")[:1]
        StockData.objects \
            .filter(date__lte = current_date_rounded - delta) \
            .exclude(date=Subquery(latest_date_subquery)) \
            .delete()
        
        latest_date_subquery = UserInvestmentGraph.objects.filter(**kwargs) \
            .order_by("-date").values("date")[:1]
        UserInvestmentGraph.objects \
            .filter(date__lte = current_date_rounded - delta) \
            .exclude(date=Subquery(latest_date_subquery)) \
            .delete()
        return
       

class FPMClient:
    root_url = "https://financialmodelingprep.com/stable/"
    possible_intervals = ["1min", "5min", "15min", "30min", "1hour", "4hour"]
    

    def __init__(self, key):
        self.key = key

    def get_historical(self, symbol, start, end, interval):
        
        if interval[1] in ["m", "h"]:
            return self.get_intra_day(symbol, start, end, interval)
        elif interval[1] in ["d", "M"]:
            return self.get_eod(symbol, start, end)
        else: 
           interval_formatted = interval
        if not interval_formatted in self.possible_intervals:
            raise ValueError(f"interval must be in {self.possible_intervals}")
    
    def get_intra_day(self, symbol, start, end, interval):
        if interval[1] == "m":
            interval_formatted = f"{interval[0]}min"
        elif interval[1] == "h":
            interval_formatted = f"{interval[0]}hour"
        else: 
            interval_formatted = interval
        if not interval_formatted in self.possible_intervals:
            raise ValueError(f"interval must be in {["m", "h"]}")
        
        response = requests.get(
            self.root_url + f"historical-chart/{interval_formatted}",
            params={
                "from": start.strftime("%Y-%m-%d"),
                "to": end.strftime("%Y-%m-%d"),
                "apikey": self.key,
                "nonadjusted": False,
                "symbol": symbol
            }
        )
        if response.status_code < 200 or response.status_code > 299:
            raise ConnectionError(f"fpm response has status code {response.status_code}: {response.content}")
        return json.loads(response.content.decode("utf-8"))

    def get_eod(self, symbol, start, end):
        response = requests.get(
            self.root_url + f"historical-price-eod/full",
            params={
                "from": start.strftime("%Y-%m-%d"),
                "to": end.strftime("%Y-%m-%d"),
                "apikey": self.key,
                "symbol": symbol
            }
        )
        if response.status_code < 200 or response.status_code > 299:
            raise ConnectionError(f"fpm response has status code {response.status_code}: {response.content}")
        return json.loads(response.content.decode("utf-8"))

   





fpm_client = FPMClient(FMP_KEY)
