from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from .serializers.PlaidSerializers.linkSerializers import e164_phone_number_validator
import uuid
import json
from django.utils import timezone
from django_celery_results.models import TaskResult
from accumate_backend.encryption import encrypt, decrypt
from accumate_backend.settings import RH_ACCESS_KMS_ALIAS, \
    RH_REFRESH_KMS_ALIAS, PLAID_ITEM_KMS_ALIAS, PLAID_USER_KMS_ALIAS, \
    USER_PII_KMS_ALIAS, ANONYMIZE_USER_HMAC_KEY
import hmac
import hashlib

# Create your models here.

# SYMBOL_CHOICES = [
#     ('VOO', 'VOO'),
#     ('VOOG', 'VOOG'),
#     ('QQQ', 'QQQ'),
#     ('IBIT', 'IBIT')
# ]

# BROKERAGE_CHOICES = [
#     ('robinhood', 'robinhood'),
#     ('webull', 'webull'),
#     ('charles_schwab', 'charles_schwab'),
#     ('fidelity', 'fidelity')
# ]

class User(AbstractUser):
    # if we must encrypt we can encrypt but have prefix. 
    # so range search on prefix, scan the rest
    id = models.UUIDField(
        primary_key=True,  # Redefine id as primary key
        default=uuid.uuid4,  # Assign UUID by default
        editable=True,  # Allow manual assignment
        unique=True
    )
    phone_number = models.CharField(
        max_length=15,
        validators=[e164_phone_number_validator],
        unique=True
    )
    full_name = models.TextField(max_length=255)
    email = models.EmailField(blank=True, max_length=254, unique=True)
    username = models.CharField(unique=True, max_length=50)

    def save(self, *args, **kwargs):
        self.username = str(self.id)
        super().save(*args, **kwargs)

class LogAnon(models.Model):
    name = models.CharField()
    method = models.CharField()
    user = models.CharField(default=None, null=True)
    date = models.DateTimeField(auto_now=True)
    errors = models.JSONField(default=None, null=True)
    state = models.CharField()
    status = models.IntegerField()
    pre_account_id = models.CharField(default=None, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['date', 'status', 'state']),
            models.Index(fields=['user', 'date', 'status', 'state'])
        ]
class Log(models.Model):
    name = models.CharField()
    method = models.CharField()
    user = models.ForeignKey(User, default=None, null=True, 
                             on_delete=models.SET_NULL, related_name='api_logs')
    date = models.DateTimeField(auto_now=True)
    errors = models.JSONField(default=None, null=True)
    state = models.CharField()
    status = models.IntegerField()
    pre_account_id = models.PositiveIntegerField(default=None, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['date', 'status', 'state']),
            models.Index(fields=['user', 'date', 'status', 'state'])
        ]
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # import pdb
        # breakpoint()

        user_hmac = self.user and hmac.new(
            key=ANONYMIZE_USER_HMAC_KEY.encode(),
            msg=str(self.user.id).encode(),
            digestmod=hashlib.sha256
        ).hexdigest()

        pre_account_id_hmac = self.pre_account_id and hmac.new(
            key=ANONYMIZE_USER_HMAC_KEY.encode(),
            msg=str(self.pre_account_id).encode(),
            digestmod=hashlib.sha256
        ).hexdigest()

        log_anonymized = LogAnon(
            name = self.name,
            method = self.method,
            user = user_hmac,
            date = self.date,
            errors = self.errors,
            state = self.state,
            status = self.status,
            pre_account_id = pre_account_id_hmac
        )
        log_anonymized.save()




class WaitlistEmail(models.Model):
    email = models.EmailField(primary_key=True)
    date_enrolled = models.DateTimeField(auto_now=True)

class UserBrokerageInfo(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, unique=True)
    brokerage = models.CharField(max_length=255, null=True, default=None)
    symbol = models.CharField(max_length=255, null=True, default=None)

# need to create this sometime
class UserInvestmentGraph(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateTimeField()
    value = models.FloatField()

    # in the future we can partition on date as well in psql
    class Meta:
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['user', 'date']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'date'], 
                name='user_portfolio_value_by_date'
            )
        ]

# need to create this sometime
class StockData(models.Model):
    VOO = models.FloatField(null=True, default=None)
    VOOG = models.FloatField(null=True, default=None)
    QQQ = models.FloatField(null=True, default=None)
    IBIT = models.FloatField(null=True, default=None)
    date = models.DateTimeField(primary_key=True)

    class Meta:
        ordering = ['date']
    
    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)
        self.save()

class PlaidUser(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, unique=True)
    countryCodes = models.CharField(choices=[], max_length=2, null=True, default=None) # create a class with these choices in serializers?
    language = models.CharField(choices=[], max_length=2, null=True, default=None)
    _userToken = models.BinaryField()
    userTokenDek = models.BinaryField()
    userId = models.CharField(max_length=255)
    clientUserId = models.CharField(max_length=255)
    link_token = models.CharField(max_length=255, null=True, default=None)

    def __init__(self, *args, **kwargs):
        userToken = kwargs.pop('userToken', None)
        super().__init__(*args, **kwargs)
        if userToken is not None:
            self.userToken = userToken

    @property 
    def userToken(self):
        return decrypt(self, "userToken", "userTokenDek", 
                       alias=PLAID_USER_KMS_ALIAS)
    
    @userToken.setter
    def userToken(self, value):
        encrypt(self, value.encode("utf-8"), "userToken", 
                "userTokenDek", alias=PLAID_USER_KMS_ALIAS)

class LogAnonPlaid(models.Model):
    user = models.CharField()
    items = models.IntegerField()

class PlaidItem(models.Model):
    # user and itemID primary key
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4, 
        editable=True,
        unique=True
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    itemId = models.CharField(max_length=255, unique=True)
    _accessToken = models.BinaryField()
    accessTokenDek = models.BinaryField()
    previousRefresh = models.DateTimeField(auto_now=True)
    previousRefreshSuccess = models.BooleanField(default=True)
    transactionsCursor = models.CharField(max_length=255, null=True, default=None)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'itemId'], 
                name='unique_plaid_item'
            )
        ]
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # import pdb
        # breakpoint()

        user_hmac = self.user and hmac.new(
            key=ANONYMIZE_USER_HMAC_KEY.encode(),
            msg=str(self.user.id).encode(),
            digestmod=hashlib.sha256
        ).hexdigest()

        try:
            log_plaid_anonymized = LogAnonPlaid.objects.get(user = user_hmac)
            log_plaid_anonymized.items += 1
            log_plaid_anonymized.save()
        except:
            log_plaid_anonymized = LogAnonPlaid(
                user = user_hmac,
                items = 1
            )
            log_plaid_anonymized.save()

        

    
    def __init__(self, *args, **kwargs):
        accessToken = kwargs.pop('accessToken', None)
        super().__init__(*args, **kwargs)
        if accessToken is not None:
            self.accessToken = accessToken

    @property
    def accessToken(self):
        return decrypt(self, "accessToken", "accessTokenDek",
                       context_fields=[], alias=PLAID_ITEM_KMS_ALIAS)
    
    @accessToken.setter
    def accessToken(self, value):
        encrypt(self, value.encode("utf-8"), "accessToken", 
                "accessTokenDek", context_fields=[], 
                alias=PLAID_ITEM_KMS_ALIAS)

class PlaidPersonalFinanceCategories(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    income = models.FloatField(default=0)
    transfer_in = models.FloatField(default=0)
    transfer_out = models.FloatField(default=0)
    loan_payments = models.FloatField(default=0)
    bank_fees = models.FloatField(default=0)
    entertainment = models.FloatField(default=0)
    food_and_drink = models.FloatField(default=0)
    general_merchandise = models.FloatField(default=0)
    home_improvement = models.FloatField(default=0)
    medical = models.FloatField(default=0)
    personal_care = models.FloatField(default=0)
    general_services = models.FloatField(default=0)
    government_and_non_profit = models.FloatField(default=0)
    transportation = models.FloatField(default=0)
    travel = models.FloatField(default=0)
    rent_and_utilities = models.FloatField(default=0)
    income = models.FloatField(default=0)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()

    def __setattr__(self, name, value):
        return super().__setattr__(name, value)



class Deposits(models.Model):
    deposit_id = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    mask = models.CharField(max_length=4)
    state = models.CharField(max_length=255)
    amount = models.FloatField()
    created_at = models.DateTimeField()
    invested = models.BooleanField(default=False)
    # user canceled request state?

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'deposit_id'], name='unique_deposit')
        ]

class PlaidCashbackTransaction(models.Model):
    user = models.ForeignKey(PlaidItem, on_delete=models.CASCADE)
    account_id = models.CharField(max_length=255)
    transaction_id = models.CharField(max_length=255)
    amount = models.FloatField()
    pending = models.BooleanField()
    iso_currency_code = models.CharField(max_length=10)
    authorized_date =  models.DateField()
    authorized_datetime =  models.DateTimeField()
    deposit = models.ForeignKey(Deposits, on_delete=models.SET_NULL, 
                                default=None, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'transaction_id'], name='unique_plaid_transaction')
        ]

class RobinhoodCashbackDeposit(models.Model):
    deposit_id = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rh_account_id = models.CharField(max_length=255)
    rh_account_ach = models.CharField(max_length=255)
    mask = models.CharField(max_length=4)
    state = models.CharField(max_length=255)
    amount = models.FloatField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    expected_landing_datetime = models.DateTimeField()
    cancel = models.CharField(max_length=255, null=True)
    invested = models.BooleanField(default=False)
    # user canceled request state?

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'deposit_id'], name='unique_rh_deposit')
        ]



class RobinhoodStockOrder(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    deposit = models.ForeignKey(Deposits, on_delete=models.SET_NULL, 
                                default=None, null=True)
    order_id = models.CharField(max_length=255)
    cancel = models.CharField(max_length=255, null=True)
    instrument_id = models.CharField(max_length=255) # uid for security!!!!!
    symbol = models.CharField(max_length=255, null=True)
    state = models.CharField(max_length=255) # 'queued', filled
    side = models.CharField(max_length=255) # 'buy'
    quantity = models.FloatField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField() # a bit after created_at. check if has changed to see if updated...
    pending_cancel_open_agent = models.CharField(max_length=255, null=True)
    requested_amount = models.FloatField()
    executed_amount = models.FloatField(null=True)
    user_cancel_request_state = models.CharField(max_length=255) # 'no_cancel_requested', 'order_finalized'

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'order_id'], name='unique_rh_order')
        ]
        ordering = ['user', 'updated_at']
        indexes = [
            models.Index(fields=['order_id']),
            models.Index(fields=['user', 'updated_at'])
        ]


class LogAnonInvestments(models.Model):
    user = models.CharField()
    symbol = models.CharField(max_length=255, null=True, default=None)
    brokerage = models.CharField(max_length=255, null=True, default=None)
    date = models.DateField()
    quantity = models.FloatField()
    buy = models.BooleanField()


class Investments(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    # one to one?
    deposit = models.ForeignKey(Deposits, on_delete=models.SET_NULL, null=True)
    rh = models.ForeignKey(RobinhoodStockOrder, on_delete=models.CASCADE, null=True, default=None)
    symbol = models.CharField(max_length=255, null=True, default=None)
    quantity = models.FloatField()
    cumulative_quantities = models.JSONField(default=dict)
    date = models.DateTimeField()
    buy = models.BooleanField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['deposit', 'buy'], 
                name='unique_investment'
            )
        ]
        ordering = ['user', 'date']
        indexes = [
            models.Index(fields=['user', 'date'])
        ]
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # import pdb
        # breakpoint()

        user_hmac = hmac.new(
            key=ANONYMIZE_USER_HMAC_KEY.encode(),
            msg=str(self.user.id).encode(),
            digestmod=hashlib.sha256
        ).hexdigest()

        logAnonInvestments = LogAnonInvestments(
            user = user_hmac,
            symbol = self.symbol,
            brokerage = self.brokerage,
            quantity = self.quantity,
            buy = self.buy,
            date = self.date.date()
        )
        logAnonInvestments.save()






