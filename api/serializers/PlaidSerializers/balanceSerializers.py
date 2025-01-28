from django.core.exceptions import ValidationError
from rest_framework import serializers
from .errorSerializer import ErrorSerializer
from .itemSerializers import ItemSerializer

# /accounts/balance/get request 

class BalanceGetRequestOptionsSerializer(serializers.Serializer):
    """
    Serializer for the 'options' field in the BalanceGetRequest.
    """
    account_ids = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="List of account IDs to retrieve balances for."
    )
    min_last_updated_datetime = serializers.DateTimeField(
        required=False,
        help_text="Filter to accounts updated after this datetime."
    )

class BalanceGetRequestSerializer(serializers.Serializer):
    """
    Serializer for the request data sent to /accounts/balance/get endpoint.
    """
    access_token = serializers.CharField(
        help_text="The access token associated with the Item data is being requested for."
    )
    options = BalanceGetRequestOptionsSerializer(
        required=False,
        help_text="Additional options to filter the balance request."
    )

# /accounts/balance/get response 

class AccountBalancesSerializer(serializers.Serializer):
    """
    Serializer for the 'balances' field within an account.
    """
    available = serializers.FloatField(
        allow_null=True,
        help_text="The available balance for the account.",
        required=False
    )
    current = serializers.FloatField(
        help_text="The current balance for the account.",
        required=False,
        allow_null=True
    )
    limit = serializers.FloatField(
        allow_null=True,
        help_text="For credit-type accounts, the credit limit.",
        required=False
    )
    iso_currency_code = serializers.CharField(
        allow_null=True,
        max_length=3,
        help_text="The ISO-4217 currency code of the balance.",
        required=False
    )
    unofficial_currency_code = serializers.CharField(
        allow_null=True,
        max_length=3,
        help_text="The unofficial currency code associated with the balance.",
        required=False
    )

class AccountSerializer(serializers.Serializer):
    """
    Serializer for an individual account object.
    """
    ACCOUNT_TYPES = (
        ('brokerage', 'brokerage'),
        ('credit', 'credit'),
        ('depository', 'depository'),
        ('loan', 'loan'),
        ('investment', 'investment'),
        ('other', 'other'),
    )
    VERIFICATION_STATUSES = (
        ('pending_automatic_verification', 'pending_automatic_verification'),
        ('pending_manual_verification', 'pending_manual_verification'),
        ('manually_verified', 'manually_verified'),
        ('verification_expired', 'verification_expired'),
    )

    account_id = serializers.CharField(
        help_text="A unique ID identifying the account."
    )
    balances = AccountBalancesSerializer(
        help_text="The balances for the account."
    )
    mask = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="The last 2-4 digits of the account number."
    )
    name = serializers.CharField(
        help_text="The name of the account."
    )
    official_name = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="The official name of the account."
    )
    subtype = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="The account subtype."
    )
    type = serializers.ChoiceField(
        choices=ACCOUNT_TYPES,
        help_text="The account type."
    )
    verification_status = serializers.ChoiceField(
        choices=VERIFICATION_STATUSES,
        required=False,
        allow_null=True,
        help_text="The verification status of the account."
    )

# class ItemSerializer(serializers.Serializer):
#     """
#     Serializer for the 'item' field in the response.
#     """
#     UPDATE_TYPES = (
#         ('background', 'background'),
#         ('user_present_required', 'user_present_required'),
#     )

#     available_products = serializers.ListField(
#         child=serializers.CharField(),
#         help_text="Products available for the Item."
#     )
#     billed_products = serializers.ListField(
#         child=serializers.CharField(),
#         help_text="Products billed for the Item."
#     )
#     consent_expiration_time = serializers.DateTimeField(
#         allow_null=True,
#         help_text="Time when the Item's consent will expire."
#     )
#     error = ErrorSerializer(
#         allow_null=True,
#         help_text="Error object containing error details, if any."
#     )
#     institution_id = serializers.CharField(
#         allow_null=True,
#         help_text="The Plaid institution ID associated with the Item."
#     )
#     item_id = serializers.CharField(
#         help_text="A unique ID identifying the Item."
#     )
#     update_type = serializers.ChoiceField(
#         choices=UPDATE_TYPES,
#         help_text="The type of update for the Item."
#     )
#     webhook = serializers.CharField(
#         allow_null=True,
#         help_text="The webhook URL associated with the Item."
#     )

class BalanceGetResponseSerializer(serializers.Serializer):
    """
    Serializer for the response data received from /accounts/balance/get endpoint.
    """
    accounts = AccountSerializer(
        many=True,
        help_text="List of accounts associated with the Item."
    )
    item = ItemSerializer(
        help_text="Information about the Item."
    )
    request_id = serializers.CharField(
        help_text="A unique identifier for the request, used for troubleshooting."
    )

# /accounts/get serializers

class AccountsGetResponseSerializer(serializers.Serializer):
    accounts = AccountSerializer(many=True)
    item = ItemSerializer()
    request_id = serializers.CharField()