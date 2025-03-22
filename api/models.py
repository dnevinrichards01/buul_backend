from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from .serializers.PlaidSerializers.linkSerializers import e164_phone_number_validator
import uuid
import json
from django_celery_results.models import TaskResult
# Create your models here.

SYMBOL_CHOICES = [
    ('VOO', 'VOO'),
    ('VOOG', 'VOOG'),
    ('QQQ', 'QQQ'),
    ('IBIT', 'IBIT')
]

BROKERAGE_CHOICES = [
    ('robinhood', 'robinhood'),
    ('webull', 'webull'),
    ('charles_schwab', 'charles_schwab'),
    ('fidelity', 'fidelity')
]

class User(AbstractUser):
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
    username = models.EmailField(blank=True, max_length=254, unique=True)

class WaitlistEmail(models.Model):
    email = models.EmailField(primary_key=True)
    date_enrolled = models.DateField(auto_now=True)

class UserBrokerageInfo(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, unique=True)
    brokerage = models.CharField(choices=BROKERAGE_CHOICES, max_length=255, null=True, default=None)
    symbol = models.CharField(choices=SYMBOL_CHOICES, max_length=255, null=True, default=None)

# need to create this sometime
class UserInvestmentGraph(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, unique=True)
    data = models.JSONField(default=list)

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
    userToken = models.CharField(max_length=255)
    userId = models.CharField(max_length=255)
    clientUserId = models.CharField(max_length=255)
    link_token = models.CharField(max_length=255, null=True, default=None)

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
    accessToken = models.CharField(max_length=255)
    transactionsCursor = models.CharField(max_length=255, null=True, default=None)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'itemId'], 
                name='unique_plaid_item'
            )
        ]

class PlaidCashbackTransaction(models.Model):
    user = models.ForeignKey(PlaidItem, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    account_id = models.CharField(max_length=255)
    transaction_id = models.CharField(max_length=255)
    amount = models.FloatField()
    # currency = models.CharField(max_length=10)
    authorized_date =  models.DateTimeField(max_length=255)
    deposited = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'transaction_id'], name='unique_plaid_transaction')
        ]

class RobinhoodCashbackDeposit(models.Model):
    deposit_id = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    transaction = models.ForeignKey(PlaidCashbackTransaction, on_delete=models.SET_NULL, null=True) # bank transfers
    rh_account_id = models.CharField(max_length=255)
    rh_account_ach = models.CharField(max_length=255)
    plaid_account_id = models.CharField(max_length=255)
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

class Investments(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    # one to one?
    investment_id = models.CharField(max_length=255)
    symbol = models.CharField(choices=SYMBOL_CHOICES, max_length=255, null=True, default=None)
    brokerage = models.CharField(choices=BROKERAGE_CHOICES, max_length=255, null=True, default=None)
    quantity = models.FloatField()
    cumulative_quantities = models.JSONField(default=dict)
    date = models.DateTimeField()

class RobinhoodStockOrder(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    deposit = models.ForeignKey(RobinhoodCashbackDeposit, on_delete=models.SET_NULL, null=True)
    order_id = models.CharField(max_length=255)
    cancel = models.CharField(max_length=255, null=True)
    instrument_id = models.CharField(max_length=255) # uid for security!!!!!
    symbol = models.CharField(choices=SYMBOL_CHOICES, max_length=255, null=True)
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
        ordering = ['updated_at', 'symbol']




