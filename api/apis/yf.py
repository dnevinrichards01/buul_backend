from buul_backend.settings import FMP_KEY

from django.utils import timezone
from django.db.models import OuterRef, Subquery

from api.models import StockData, UserInvestmentGraph

from django.db.models import Max
from django.db.models.functions import ExtractYear, ExtractWeek, \
    ExtractHour, ExtractDay, ExtractMonth

import requests
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from zoneinfo import ZoneInfo
import json

import yfinance as yf
import pandas as pd
from typing import Any, Dict, List, Optional

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
        # yf uses utc by default:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            return dt.astimezone(ZoneInfo("UTC"))
        return dt

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
            delta = relativedelta(days=1)
            # kwargs = {
            #     "date__hour": OuterRef("date__hour"),
            #     "date__date": OuterRef("date__date")
            # }
            latest_stock_data_dates = (
                StockData.objects
                .filter(date__lte = current_date_rounded - delta)
                .annotate(hour=ExtractHour('date'),day=ExtractDay('date'), month=ExtractMonth('date'), year=ExtractYear('date'))
                .values('hour', 'day', 'month', 'year')
                .annotate(latest=Max('date'))
                .values_list('latest', flat=True)
            )
            latest_user_graph_dates = (
                UserInvestmentGraph.objects
                .filter(date__lte = current_date_rounded - delta)
                .annotate(hour=ExtractHour('date'),day=ExtractDay('date'), month=ExtractMonth('date'), year=ExtractYear('date'))
                .values('hour', 'day', 'month', 'year')
                .annotate(latest=Max('date'))
                .values_list('latest', flat=True)
            )
        elif interval[1] == "d":
            delta = relativedelta(months=3)
            # kwargs = {
            #     "date__date": OuterRef("date__date")
            # }
            latest_stock_data_dates = (
                StockData.objects
                .filter(date__lte = current_date_rounded - delta)
                .annotate(day=ExtractDay('date'), month=ExtractMonth('date'), year=ExtractYear('date'))
                .values('day', 'month', 'year')
                .annotate(latest=Max('date'))
                .values_list('latest', flat=True)
            )
            latest_user_graph_dates = (
                UserInvestmentGraph.objects
                .filter(date__lte = current_date_rounded - delta)
                .annotate(day=ExtractDay('date'), month=ExtractMonth('date'), year=ExtractYear('date'))
                .values('day', 'month', 'year')
                .annotate(latest=Max('date'))
                .values_list('latest', flat=True)
            )
        elif interval[1] == "w":
            delta = relativedelta(years=1)
            # kwargs = {
            #     "date__week": OuterRef("date__week"),
            #     "date__year": OuterRef("date__year")
            # }
            latest_stock_data_dates = (
                StockData.objects
                .filter(date__lte = current_date_rounded - delta)
                .annotate(week=ExtractWeek('date'), year=ExtractYear('date'))
                .values('week', 'year')
                .annotate(latest=Max('date'))
                .values_list('latest', flat=True)
            )
            latest_user_graph_dates = (
                UserInvestmentGraph.objects
                .filter(date__lte = current_date_rounded - delta)
                .annotate(week=ExtractWeek('date'), year=ExtractYear('date'))
                .values('week', 'year')
                .annotate(latest=Max('date'))
                .values_list('latest', flat=True)
            )
        elif interval[1] == "M":
            delta = relativedelta(years=5)
            # kwargs = {
            #     "date__month": OuterRef("date__month"),
            #     "date__year": OuterRef("date__year")
            # }
            latest_stock_data_dates = (
                StockData.objects
                .filter(date__lte = current_date_rounded - delta)
                .annotate(month=ExtractMonth('date'), year=ExtractYear('date'))
                .values('month', 'year')
                .annotate(latest=Max('date'))
                .values_list('latest', flat=True)
            )
            latest_user_graph_dates = (
                UserInvestmentGraph.objects
                .filter(date__lte = current_date_rounded - delta)
                .annotate(month=ExtractMonth('date'), year=ExtractYear('date'))
                .values('month', 'year')
                .annotate(latest=Max('date'))
                .values_list('latest', flat=True)
            )
        
        StockData.objects.filter(
            date__lte = current_date_rounded - delta
        ).exclude(
            date__in = latest_stock_data_dates
        ).delete()

        UserInvestmentGraph.objects.filter(
            date__lte = current_date_rounded - delta
        ).exclude(
            date__in = latest_user_graph_dates
        ).delete()
        # latest_date_subquery = StockData.objects.filter(**kwargs) \
        #     .order_by("-date").values("date")[:1]
        # StockData.objects \
        #     .filter(date__lte = current_date_rounded - delta) \
        #     .exclude(date=Subquery(latest_date_subquery)) \
        #     .delete()
        
        # latest_date_subquery = UserInvestmentGraph.objects.filter(**kwargs) \
        #     .order_by("-date").values("date")[:1]
        # UserInvestmentGraph.objects \
        #     .filter(date__lte = current_date_rounded - delta) \
        #     .exclude(date=Subquery(latest_date_subquery)) \
        #     .delete()
        return
       

class YFClient:
    possible_intervals = ["1min", "5min", "15min", "30min", "1hour", "4hour"]
    _allowed = {"1m", "5m", "15m", "30m", "1h", "1d", "1M"}

    def get_historical(self, symbol, start, end, interval):
        if interval not in self._allowed:
            raise ValueError(f"interval must be one of {sorted(self._allowed)}")
        yf_interval = self._to_yf_interval(interval)
        df = yf.download(
            tickers=symbol if symbol != "BTCUSD" else "BTC-USD",
            start=start,
            end=end,
            interval=yf_interval,
            auto_adjust=True,
            progress=False,
            group_by="column",
            threads=True,
        )
        close_series = df["Close"]
        close_series = close_series.dropna()
        return [
            {
                "date": ts.isoformat(),
                "close": float(close_series.loc[ts].iloc[0])
            }
            for ts in close_series.index
        ]

    def _to_yf_interval(self, interval: str):
        if interval == "1M":
            return "1mo"
        return interval


yf_client = YFClient()
