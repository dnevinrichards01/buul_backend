from api.models import User
from rest_framework import serializers
from django.core.exceptions import ValidationError

class StockOrderTotalNotionalSerializer(serializers.Serializer):
    amount = serializers.FloatField()
    currency_code = serializers.CharField() # USD

# idempotency partially by checking db then search RH
class StockOrderSerializer(serializers.Serializer):
    id = serializers.CharField()
    url = serializers.CharField()
    position = serializers.CharField()
    cancel = serializers.CharField(allow_null=True)
    instrument_id = serializers.CharField() # uid for security!!!!!
    # 'cumulative_quantity': '0.00000000', 
    state = serializers.CharField() # 'queued', filled
    derived_state = serializers.CharField() # 'queued', filled
    side = serializers.CharField() # 'buy'
    # 'limit', 'gfd', 'immediate'
    price = serializers.FloatField(allow_null=True)
    quantity = serializers.FloatField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField() # a bit after created_at. check if has changed to see if updated...
    pending_cancel_open_agent = serializers.CharField(allow_null=True)
    total_notional = StockOrderTotalNotionalSerializer(allow_null=True, required=False)
    executed_notional = StockOrderTotalNotionalSerializer(allow_null=True, required=False)
    user_cancel_request_state = serializers.CharField() # 'no_cancel_requested', 'order_finalized'

    def validate_url(self, url):
        if url[:33] != "https://api.robinhood.com/orders/":
            raise ValidationError("url")
        return url
    
    def validate_position(self, url):
        if url[:36] != "https://api.robinhood.com/positions/":
            raise ValidationError("position_url")
        return url
    
    def validate_cancel(self, url):
        if url is None or url == "":
            return url
        if url[:33] != "https://api.robinhood.com/orders/" or \
            url[-8:] != "/cancel/":
            raise ValidationError("cancel_url")
        return url
    
    def validate_instrument(self, url):
        if url[:38] !=  "https://api.robinhood.com/instruments/":
            raise ValidationError("instrument_url")
        return url
    
class DepositSerializer(serializers.Serializer):
    ach_relationship = serializers.CharField() # the account
    id = serializers.CharField()
    url = serializers.CharField()
    cancel = serializers.CharField(allow_null=True) 
    amount = serializers.FloatField()
    direction = serializers.CharField() # deposit
    state = serializers.CharField() # pending
    rhs_state = serializers.CharField() # requested, completed
    created_at = serializers.DateTimeField() 
    updated_at = serializers.DateTimeField(allow_null=True) 
    expected_landing_datetime = serializers.DateTimeField() 

    def validate_ach_relationship(self, relationship_url):
        if relationship_url[:44] != "https://api.robinhood.com/ach/relationships/":
            raise ValidationError("ach_relationship url")
        return relationship_url

    def validate_cancel(self, cancel_url):
        if cancel_url is None:
            return cancel_url
        if cancel_url[:40] != "https://api.robinhood.com/ach/transfers/" or \
            cancel_url[-8:] != "/cancel/":
            raise ValidationError("ach_relationship url")
        return cancel_url
    
    def validate_url(self, cancel_url):
        if cancel_url[:40] != "https://api.robinhood.com/ach/transfers/":
            raise ValidationError("ach_relationship url")
        return cancel_url



# 'name': 'Plaid Checking', 
# 'official_name': 'Plaid Gold Standard 0% Interest Checking'
# 'subtype': 'checking'
# 'mask': '0000', 
class GetLinkedBankAccountsResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    url = serializers.CharField()
    account = serializers.CharField()
    bank_account_nickname = serializers.CharField()
    bank_account_type = serializers.CharField()
    bank_account_number = serializers.RegexField(
        regex=r'^\d{2,8}$', required=True
    )
    verified = serializers.BooleanField() # True
    state = serializers.CharField() # approved

    def validate_url(self, url):
        if url[:44] != "https://api.robinhood.com/ach/relationships/":
            raise ValidationError("url")
        return url
    

class MarginBalancesSerializer(serializers.Serializer):
    sma = serializers.CharField()
    day_trade_buying_power_held_for_orders = serializers.CharField()
    start_of_day_dtbp = serializers.CharField()
    overnight_buying_power_held_for_orders = serializers.CharField()
    leverage_enabled = serializers.BooleanField()
    unsettled_funds = serializers.CharField()
    unsettled_debit = serializers.CharField()
    cash_held_for_crypto_orders = serializers.CharField()
    cash_held_for_dividends = serializers.CharField()
    cash_held_for_restrictions = serializers.CharField()
    cash_held_for_options_collateral = serializers.CharField()
    cash_held_for_orders = serializers.CharField()
    eligible_deposit_as_instant = serializers.CharField()
    instant_used = serializers.CharField()
    outstanding_interest = serializers.CharField()
    pending_debit_card_debits = serializers.CharField()
    settled_amount_borrowed = serializers.CharField()
    uncleared_deposits = serializers.CharField()
    cash = serializers.CharField()
    cash_held_for_nummus_restrictions = serializers.CharField()
    cash_available_for_withdrawal = serializers.CharField()
    unallocated_margin_cash = serializers.CharField()
    margin_limit = serializers.CharField()
    crypto_buying_power = serializers.CharField()
    day_trade_buying_power = serializers.CharField()
    day_trades_protection = serializers.BooleanField()
    start_of_day_overnight_buying_power = serializers.CharField()
    overnight_buying_power = serializers.CharField()
    overnight_ratio = serializers.CharField()
    day_trade_ratio = serializers.CharField()
    marked_pattern_day_trader_date = serializers.DateTimeField(allow_null=True)
    pattern_day_trader_expiry_date = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    portfolio_cash = serializers.CharField()
    gold_equity_requirement = serializers.CharField()
    uncleared_nummus_deposits = serializers.CharField()
    cash_pending_from_options_events = serializers.CharField()
    pending_deposit = serializers.CharField()
    funding_hold_balance = serializers.CharField()
    net_moving_cash = serializers.CharField()
    margin_withdrawal_limit = serializers.CharField(allow_null=True)
    instant_allocated = serializers.CharField()
    is_primary_account = serializers.BooleanField()
    is_pdt_forever = serializers.BooleanField()

class RobinhoodAccountSerializer(serializers.Serializer):
    url = serializers.URLField()
    portfolio_cash = serializers.CharField() # this one
    account_number = serializers.CharField()
    deactivated = serializers.BooleanField()
    deposit_halted = serializers.BooleanField()
    withdrawal_halted = serializers.BooleanField()
    buying_power = serializers.CharField() # this one
    onbp = serializers.CharField() # this one
    cash_available_for_withdrawal = serializers.CharField() # this one
    cash_available_for_withdrawal_without_margin = serializers.CharField() # this one
    cash = serializers.CharField() # this one
    amount_eligible_for_deposit_cancellation = serializers.CharField()
    cash_held_for_orders = serializers.CharField()
    uncleared_deposits = serializers.CharField()
    sma = serializers.CharField()
    sma_held_for_orders = serializers.CharField()
    unsettled_funds = serializers.CharField()
    unsettled_debit = serializers.CharField()
    crypto_buying_power = serializers.CharField()
    max_ach_early_access_amount = serializers.CharField()
    cash_balances = serializers.CharField(allow_null=True)
    margin_balances = MarginBalancesSerializer()

class RobinhoodAccountListSerializer(serializers.Serializer):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = RobinhoodAccountSerializer(many=True)
