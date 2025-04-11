from django.db import models
# from django.contrib.auth.models import User
from api.models import User
from django.utils.timezone import now
from accumate_backend.settings import RH_ACCESS_KMS_ALIAS, \
    RH_REFRESH_KMS_ALIAS, PLAID_ITEM_KMS_ALIAS, PLAID_USER_KMS_ALIAS, \
    USER_PII_KMS_ALIAS, ANONYMIZE_USER_HMAC_KEY
from accumate_backend.encryption import encrypt, decrypt
import hmac
import hashlib

class UserRobinhoodInfo(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token_type = models.CharField(max_length=255) 
    access_token = models.BinaryField()
    access_token_dek = models.BinaryField()
    refresh_token = models.BinaryField()
    refresh_token_dek = models.BinaryField()
    device_token = models.BinaryField()
    device_token_dek = models.BinaryField()
    issued_time = models.DateTimeField(default=now)
    # adding this in a later migration, so need to make it nullable for hypothetical existing rows...
    expiration_time = models.DateTimeField(null=True) 

    def refresh(self):
        from robin_stocks.robinhood import refresh, create_session
        refresh(create_session(), self.user.id)
    
    def __init__(self, *args, **kwargs):
        access_token = kwargs.pop('access_token', None)
        refresh_token = kwargs.pop('refresh_token', None)
        device_token = kwargs.pop('device_token', None)
        super().__init__(*args, **kwargs)
        if access_token is not None:
            self.access_token = access_token
        if refresh_token is not None:
            self.refresh_token = refresh_token
        if device_token is not None:
            self.device_token = device_token

    @property
    def access_token(self):
        return decrypt(self, "access_token", "access_token_dek",
                       context_fields=[], alias=RH_ACCESS_KMS_ALIAS)
    
    @access_token.setter
    def access_token(self, value):
        encrypt(self, value.encode("utf-8"), "access_token", 
                "access_token_dek", context_fields=[], 
                alias=RH_ACCESS_KMS_ALIAS)
        
    @property
    def refresh_token(self):
        return decrypt(self, "refresh_token", "refresh_token_dek",
                       context_fields=[], alias=RH_REFRESH_KMS_ALIAS)
    
    @refresh_token.setter
    def refresh_token(self, value):
        encrypt(self, value.encode("utf-8"), "refresh_token", 
                "refresh_token_dek", context_fields=[], 
                alias=RH_REFRESH_KMS_ALIAS)
    
    @property
    def device_token(self):
        return decrypt(self, "device_token", "device_token_dek",
                       context_fields=[], alias=RH_REFRESH_KMS_ALIAS)
    
    @device_token.setter
    def device_token(self, value):
        encrypt(self, value.encode("utf-8"), "device_token", 
                "device_token_dek", context_fields=[], 
                alias=RH_REFRESH_KMS_ALIAS)
    
    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value) 

class LogAnon(models.Model):
    name = models.CharField()
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
    user = models.ForeignKey(User, default=None, null=True, 
                             on_delete=models.DO_NOTHING, related_name='rh_logs')
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
            user = user_hmac,
            date = self.date,
            errors = self.errors,
            state = self.state,
            status = self.status,
            pre_account_id = pre_account_id_hmac
        )
        log_anonymized.save()


