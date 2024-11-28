from django.core.exceptions import ValidationErrors
from rest_framework import serializers
from errorSerializer import ErrorSerializer
from choices import PaymentChannelChoices, TransactionTypeChoices

# /transactions/sync request

class TransactionsSyncRequestOptionsSerializer(serializers.Serializer):
    """
    Serializer for the 'options' field in the TransactionsSyncRequest.
    """
    include_personal_finance_category = serializers.BooleanField(
        required=False,
        help_text="Include personal finance category data."
    )
    include_original_description = serializers.BooleanField(
        required=False,
        help_text="Include original description data."
    )

class TransactionsSyncRequestSerializer(serializers.Serializer):
    """
    Serializer for the request data sent to /transactions/sync endpoint.
    """
    access_token = serializers.CharField(
        help_text="The access token associated with the Item data is being requested for."
    )
    cursor = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Cursor value representing the last update the client has received for the given Item."
    )
    count = serializers.IntegerField(
        required=False,
        help_text="The number of transactions to fetch."
    )
    options = TransactionsSyncRequestOptionsSerializer(
        required=False,
        help_text="Additional options to filter the transactions sync request."
    )

# /transactions/sync response

class PaymentMetaSerializer(serializers.Serializer):
    """
    Serializer for the payment meta information of a transaction.
    """
    by_order_of = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="The party that ordered payment."
    )
    payee = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="The entity being paid."
    )
    payer = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="The entity paying."
    )
    payment_method = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="Method of payment."
    )
    payment_processor = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="Payment processor used."
    )
    ppd_id = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="ACH PPD ID."
    )
    reason = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="Reason for payment."
    )
    reference_number = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="Payment reference number."
    )

class LocationSerializer(serializers.Serializer):
    """
    Serializer for the location information of a transaction.
    """
    address = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="Street address where transaction occurred."
    )
    city = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="City where transaction occurred."
    )
    region = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="State or region where transaction occurred."
    )
    postal_code = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="Postal code where transaction occurred."
    )
    country = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="Country where transaction occurred."
    )
    lat = serializers.FloatField(
        allow_null=True,
        required=False,
        help_text="Latitude coordinates of transaction location."
    )
    lon = serializers.FloatField(
        allow_null=True,
        required=False,
        help_text="Longitude coordinates of transaction location."
    )
    store_number = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="Store number where transaction occurred."
    )

class PersonalFinanceCategorySerializer(serializers.Serializer):
    """
    Serializer for personal finance category information.
    """
    primary = serializers.CharField(
        help_text="The primary personal finance category."
    )
    detailed = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="The detailed personal finance category."
    )

class MerchantSerializer(serializers.Serializer):
    """
    Serializer for merchant information.
    """
    name = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="The merchant name."
    )
    id = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="The merchant ID."
    )

class TransactionCodeSerializer(serializers.Serializer):
    """
    Serializer for transaction code information.
    """
    code = serializers.CharField(
        help_text="The transaction code."
    )
    description = serializers.CharField(
        help_text="The transaction code description."
    )

class SubtransactionSerializer(serializers.Serializer):
    """
    Serializer for subtransactions within a transaction.
    """
    transaction_id = serializers.CharField(
        help_text="The unique ID of the subtransaction."
    )
    amount = serializers.FloatField(
        help_text="The amount of the subtransaction."
    )
    description = serializers.CharField(
        help_text="Description of the subtransaction."
    )
    category = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="List of categories for the subtransaction."
    )
    category_id = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="ID of the category."
    )

class TransactionSerializer(serializers.Serializer):
    """
    Serializer for transaction objects.
    """
    transaction_id = serializers.CharField(
        help_text="The unique ID of the transaction."
    )
    account_id = serializers.CharField(
        help_text="The ID of the account associated with this transaction."
    )
    amount = serializers.FloatField(
        help_text="The settled value of the transaction."
    )
    iso_currency_code = serializers.CharField(
        allow_null=True,
        required=False,
        max_length=3,
        help_text="The ISO-4217 currency code of the transaction."
    )
    unofficial_currency_code = serializers.CharField(
        allow_null=True,
        required=False,
        max_length=3,
        help_text="The unofficial currency code associated with the transaction."
    )
    date = serializers.DateField(
        help_text="The date the transaction was posted."
    )
    authorized_date = serializers.DateField(
        allow_null=True,
        required=False,
        help_text="The date the transaction was authorized."
    )
    pending = serializers.BooleanField(
        help_text="Indicates if the transaction is pending or posted."
    )
    pending_transaction_id = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="The ID of the posted transaction corresponding to a pending transaction."
    )
    account_owner = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="The account owner."
    )
    merchant_name = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="The merchant name."
    )
    name = serializers.CharField(
        help_text="The transaction name."
    )
    original_description = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="The original description of the transaction."
    )
    payment_channel = serializers.ChoiceField(
        choices=PaymentChannelChoices.CHOICES,
        help_text="The payment channel of the transaction."
    )
    payment_meta = PaymentMetaSerializer(
        allow_null=True,
        required=False,
        help_text="Additional payment meta information."
    )
    location = LocationSerializer(
        allow_null=True,
        required=False,
        help_text="Location information about the transaction."
    )
    category = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="A hierarchical array of categories."
    )
    category_id = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="The ID of the category."
    )
    transaction_type = serializers.ChoiceField(
        choices=TransactionTypeChoices.CHOICES,
        help_text="The type of transaction."
    )
    personal_finance_category = PersonalFinanceCategorySerializer(
        allow_null=True,
        required=False,
        help_text="The personal finance category of the transaction."
    )
    merchant = MerchantSerializer(
        allow_null=True,
        required=False,
        help_text="Merchant information."
    )
    transaction_code = TransactionCodeSerializer(
        allow_null=True,
        required=False,
        help_text="Transaction code information."
    )
    subtransactions = SubtransactionSerializer(
        many=True,
        required=False,
        help_text="An array of subtransactions associated with this transaction."
    )

class RemovedTransactionSerializer(serializers.Serializer):
    """
    Serializer for removed transaction objects.
    """
    transaction_id = serializers.CharField(
        help_text="The unique ID of the removed transaction."
    )
    account_id = serializers.CharField(
        help_text="The ID of the account associated with the removed transaction."
    )

class TransactionsSyncResponseSerializer(serializers.Serializer):
    """
    Serializer for the response data received from /transactions/sync endpoint.
    """
    added = TransactionSerializer(
        many=True,
        help_text="Transactions that have been added since the last sync."
    )
    modified = TransactionSerializer(
        many=True,
        help_text="Transactions that have been modified since the last sync."
    )
    removed = RemovedTransactionSerializer(
        many=True,
        help_text="Transactions that have been removed since the last sync."
    )
    next_cursor = serializers.CharField(
        help_text="The cursor value to use in the next request to receive updates."
    )
    has_more = serializers.BooleanField(
        help_text="Indicates whether more updates are available."
    )
    request_id = serializers.CharField(
        help_text="A unique identifier for the request, used for troubleshooting."
    )
