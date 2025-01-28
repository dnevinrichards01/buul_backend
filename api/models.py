from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
import uuid
# Create your models here.

class User(AbstractUser):
    id = models.UUIDField(
        primary_key=True,  # Redefine id as primary key
        default=uuid.uuid4,  # Assign UUID by default
        editable=True,  # Allow manual assignment
        unique=True
    )
    phone_number = models.CharField(
        max_length=15,
        validators=[RegexValidator(regex=r'^\+?[1-9]\d{1,14}$', message='Enter a valid phone number.')],
    )

class WaitlistEmail(models.Model):
    email = models.EmailField(primary_key=True)
    date_enrolled = models.DateField(auto_now=True)

class UserBrokerageInfo(models.Model):
    BROKERAGE_CHOICES = [
        ('robinhood', 'robinhood')
    ]
    SYMBOL_CHOICES = [
        ('VOO', 'VOO')
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    brokerage = models.CharField(choices=BROKERAGE_CHOICES, max_length=255)
    symbol = models.CharField(choices=SYMBOL_CHOICES, max_length=255)

class StockData(models.Model):
    SYMBOL_CHOICES = [
        ('VOO', 'VOO')
    ]
    symbol = models.CharField(choices=SYMBOL_CHOICES, max_length=255)
    dailyPrice = ArrayField(models.FloatField(), default=list)
    cursor = models.DateTimeField(auto_now=True)
    startDate = models.DateTimeField(auto_now=True)

class PlaidUser(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    countryCodes = models.CharField(choices=[], max_length=2, null=True, default=None) # create a class with these choices in serializers?
    language = models.CharField(choices=[], max_length=2, null=True, default=None)
    userToken = models.CharField(max_length=255)
    userId = models.CharField(max_length=255)
    clientUserId = models.CharField(max_length=255)

class PlaidItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    itemId = models.CharField(max_length=255, unique=True)
    accessToken = models.CharField(max_length=255)
    transactionsCursor = models.CharField(max_length=255, null=True, default=None)

class PlaidCashbackTransaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    account_id = models.CharField(max_length=255)
    transaction_id = models.CharField(max_length=255)
    amount = models.FloatField()
    # currency = models.CharField(max_length=10)
    authorized_date =  models.DateTimeField(max_length=255)
    deposited = models.BooleanField(default=False) 

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

class RobinhoodStockOrder(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    deposit = models.ForeignKey(RobinhoodCashbackDeposit, on_delete=models.SET_NULL, null=True)
    order_id = models.CharField(max_length=255)
    cancel = models.CharField(max_length=255, null=True)
    instrument_id = models.CharField(max_length=255) # uid for security!!!!!
    state = models.CharField(max_length=255) # 'queued', filled
    side = models.CharField(max_length=255) # 'buy'
    quantity = models.FloatField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField() # a bit after created_at. check if has changed to see if updated...
    pending_cancel_open_agent = models.CharField(max_length=255, null=True)
    requested_amount = models.FloatField()
    executed_amount = models.FloatField(null=True)
    user_cancel_request_state = models.CharField(max_length=255) # 'no_cancel_requested', 'order_finalized'




