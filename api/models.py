from django.db import models
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

class PasswordReset(models.Model):
    email = models.EmailField(primary_key=True)
    token = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

class WaitlistEmail(models.Model):
    email = models.EmailField(primary_key=True)
    date_enrolled = models.DateField(auto_now=True)

class UserBrokerageInfo(models.Model):
    BROKERAGE_CHOICES = [
        ('RH', 'Robinhood')
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    brokerage = models.CharField(choices=BROKERAGE_CHOICES, max_length=255)

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
    cardAccountId = models.CharField(max_length=255)
    transactionId = models.CharField(max_length=255)
    amount = models.FloatField()
    withdrawAccountId = models.CharField(max_length=255) # check which is connected to brokerage
    hasBalance = models.BooleanField(default=False)

class RobinhoodCashbackDeposit(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    transactionId = models.CharField(max_length=255) # bank transfers
    depositId = models.CharField(max_length=255)
    depositState = models.CharField(choices=[], max_length=255)
    deposited = models.BooleanField(default=False)

class RobinhoodInvest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    orderId = models.CharField(max_length=255)
    orderState = models.CharField(choices=[], max_length=255)
    price = models.FloatField()
    quantity = models.FloatField()
    invested = models.BooleanField(default=False)




