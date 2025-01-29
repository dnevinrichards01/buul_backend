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
    price = serializers.FloatField()
    quantity = serializers.FloatField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField() # a bit after created_at. check if has changed to see if updated...
    pending_cancel_open_agent = serializers.CharField(allow_null=True)
    total_notional = StockOrderTotalNotionalSerializer()
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
    
class DepositFundsToRobinhoodResponseSerializer(serializers.Serializer):
    ach_relationship = serializers.CharField() # the account
    id = serializers.CharField()
    url = serializers.CharField()
    cancel = serializers.CharField() 
    amount = serializers.FloatField()
    status_description = serializers.CharField() # ''
    state = serializers.CharField() # pending
    rhs_state = serializers.CharField() # requested
    created_at = serializers.DateTimeField() 
    expected_landing_datetime = serializers.DateTimeField() 

    def validate_ach_relationship(self, relationship_url):
        if relationship_url[:44] != "https://api.robinhood.com/ach/relationships/":
            raise ValidationError("ach_relationship url")
        return relationship_url

    def validate_cancel(self, cancel_url):
        if cancel_url[:40] != "https://api.robinhood.com/ach/transfers/" or \
            cancel_url[-8:] != "/cancel/":
            raise ValidationError("ach_relationship url")
        return cancel_url
    
    def validate_url(self, cancel_url):
        if cancel_url[:40] != "https://api.robinhood.com/ach/transfers/":
            raise ValidationError("ach_relationship url")
        return cancel_url

class GetBankTransfersResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    # cancel: None
    ach_relationship = serializers.CharField() 
    amount = serializers.FloatField() #: 1.00
    direction = serializers.ChoiceField(choices=["deposit"])
    state = serializers.CharField() # completed
    rhs_state = serializers.CharField() # completed
    status_description = serializers.CharField(allow_blank=True) # ''
    # scheduled: False
    created_at = serializers.DateTimeField()
    expected_landing_datetime = serializers.DateTimeField()

    def validate_ach_relationship(self, relationship_url):
        if relationship_url[:44] != "https://api.robinhood.com/ach/relationships/":
            raise ValidationError("ach_relationship url")
        return relationship_url

# class MyModelSerializer(serializers.ModelSerializer):
#     # Define the input field (not in the model)
#     status = serializers.CharField(write_only=True)

#     class Meta:
#         model = MyModel
#         fields = ['status', 'is_special']

#     def create(self, validated_data):
#         # Transform 'status' into 'is_special'
#         status = validated_data.pop('status', None)
#         validated_data['is_special'] = status == 'special'
#         return super().create(validated_data)

#     def update(self, instance, validated_data):
#         # Transform 'status' into 'is_special' during updates
#         status = validated_data.pop('status', None)
#         if status is not None:
#             validated_data['is_special'] = status == 'special'
#         return super().update(instance, validated_data)


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
    bank_routing_number = serializers.CharField()
    verified = serializers.BooleanField() # True
    state = serializers.CharField() # approved

    def validate_url(self, url):
        if url[:44] != "https://api.robinhood.com/ach/relationships/":
            raise ValidationError("url")
        return url

    def validate_bank_routing_number(self, num):
        if len(num) < 4:
            raise ValidationError()
        return num[-4:]
    

