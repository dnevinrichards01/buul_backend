from django.db import models
from django.contrib.auth.models import User
# Create your models here.

class WaitlistEmail(models.Model):
    email = models.EmailField(primary_key=True)
    date_enrolled = models.DateField(auto_now=True)

class UserBrokerageInfo(models.Model):
    BROKERAGE_CHOICES = [
        ('RH', 'Robinhood')
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    brokerage = models.CharField(choices=BROKERAGE_CHOICES, max_length=255)
    username = models.CharField(max_length=255) # find the consraints RH places
    password = models.CharField(max_length=255) # find the consraints RH places

class UserPlaidInfo(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    countryCodes = models.CharField(choices=[], max_length=2)
    language = models.CharField(choices=[], max_length=2)
    userToken = models.CharField(max_length=255)
    accessToken = models.CharField(max_length=255)
    clientUserId = models.CharField(max_length=255)
    itemId = models.CharField(max_length=255)

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