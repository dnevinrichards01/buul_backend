from django.core.exceptions import ValidationError
from rest_framework import serializers
from .error import ErrorSerializer

# Plaid Webhook Serializer


class PlaidSessionFinishedSerializer(serializers.Serializer):
    webhook_type = serializers.ChoiceField(required=True, choices=["LINK"])
    webhook_code = serializers.ChoiceField(required=True, choices=["SESSION_FINISHED"])
    status = serializers.ChoiceField(required=True, choices=["success", "exited"])
    link_session_id = serializers.CharField(required=True)
    link_token = serializers.CharField(required=True)
    public_tokens = serializers.ListField(
        required=True,
        child=serializers.CharField(required=True),
    )
    environment = serializers.ChoiceField(required=True, choices=["sandbox", "production"])

    def validate(self, attrs):
        if attrs['status'] not in ["SUCCESS", "success"]:
            raise serializers.ValidationError("status must be 'SUCCESS' or 'success'")
        return attrs

class PlaidItemAddSerializer(serializers.Serializer):
    webhook_type = serializers.ChoiceField(required=True, choices=["LINK"])
    webhook_code = serializers.ChoiceField(required=True, choices=["ITEM_ADD_RESULT"])
    link_session_id = serializers.CharField(required=True)
    link_token = serializers.CharField(required=True)
    public_token = serializers.CharField(required=True)
    environment = serializers.ChoiceField(required=True, choices=["sandbox", "production"])

# when we create the item, pull their transactions immediately. 
# bc we only get this webhook after the initial sync call
class PlaidTransactionSyncUpdatesAvailable(serializers.Serializer):
    webhook_type = serializers.ChoiceField(required=True, choices=["TRANSACTION"])
    webhook_code = serializers.ChoiceField(required=True, choices=["SYNC_UPDATES_AVAILABLE"])
    item_id = serializers.CharField(required=True)
    initial_update_complete = serializers.BooleanField(required=True)
    historical_update_complete = serializers.BooleanField(required=True)
    environment = serializers.ChoiceField(required=True, choices=["sandbox", "production"])

    def validate(self, attrs):
        return attrs
    

class WebhookSerializer(serializers.Serializer):
    """
    Serializer for Plaid link webhooks.
    """
    WEBHOOK_TYPES = (
        ('ITEM', 'ITEM'),
        ('TRANSACTIONS', 'TRANSACTIONS'),
        ('LINK', 'LINK')
    )
    WEBHOOK_CODES = (
        ('SESSION_FINISHED', 'SESSION_FINISHED'),
        ('ITEM_ADD_RESULT', 'ITEM_ADD_RESULT'),
        ('SYNC_UPDATES_AVAILABLE', 'SYNC_UPDATES_AVAILABLE')
    )

    webhook_type = serializers.ChoiceField(
        choices=WEBHOOK_TYPES,
        required=True,
        help_text="The type of webhook."
    )
    webhook_code = serializers.ChoiceField(
        choices=WEBHOOK_CODES,
        required=True,
        help_text="The code representing the webhook event."
    )
    environment = serializers.ChoiceField(required=True, choices=["sandbox", "production"])
    error = ErrorSerializer(
        required=False,
        allow_null=True,
        help_text="Error object containing error details, if any."
    )

    def validate(self, data):
        """
        Custom validation to ensure required fields are present based on webhook_code.
        """
        webhook_type = data.get('webhook_type')
        webhook_code = data.get('webhook_code')
        if not (webhook_type == "LINK" and webhook_code == "SESSION_FINISHED") and \
            not (webhook_type == "TRANSACTION" and webhook_code == "SYNC_UPDATES_AVAILABLE"):
            raise ValidationError(f"unsupported webhook of type {webhook_type} and code {webhook_code}")
        return data
