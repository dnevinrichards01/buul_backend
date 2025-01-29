from django.core.exceptions import ValidationError
from rest_framework import serializers
from .errorSerializer import ErrorSerializer

# Plaid Webhook Serializer
class WebhookSerializer(serializers.Serializer):
    """
    Serializer for Plaid link webhooks.
    """
    WEBHOOK_TYPES = (
        ('ITEM', 'ITEM'),
        ('TRANSACTIONS', 'TRANSACTIONS'),
        ('INVESTMENTS_TRANSACTIONS', 'INVESTMENTS_TRANSACTIONS'),
        ('ASSETS', 'ASSETS'),
        ('AUTH', 'AUTH'),
        ('HOLDINGS', 'HOLDINGS'),
        ('IDENTITY', 'IDENTITY'),
        ('INCOME', 'INCOME'),
        ('LIABILITIES', 'LIABILITIES'),
        ('PAYMENT_INITIATION', 'PAYMENT_INITIATION'),
        ('TRANSFERS', 'TRANSFERS'),
    )

    webhook_type = serializers.ChoiceField(
        choices=WEBHOOK_TYPES,
        help_text="The type of webhook."
    )
    webhook_code = serializers.CharField(
        help_text="The code representing the webhook event."
    )
    item_id = serializers.CharField(
        help_text="The ID of the Item associated with the webhook."
    )
    error = ErrorSerializer(
        required=False,
        allow_null=True,
        help_text="Error object containing error details, if any."
    )
    account_ids = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="List of account IDs affected by the webhook."
    )
    new_transactions = serializers.IntegerField(
        required=False,
        help_text="Number of new transactions available."
    )
    removed_transactions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="List of transaction IDs that have been removed."
    )
    reset_transactions = serializers.IntegerField(
        required=False,
        help_text="Indicates a reset of transactions."
    )
    # Additional fields can be added as needed based on webhook_code

    def validate(self, data):
        """
        Custom validation to ensure required fields are present based on webhook_code.
        """
        webhook_code = data.get('webhook_code')
        # Add validation logic based on webhook_code if necessary
        return data
