from django.core.exceptions import ValidationError
from rest_framework import serializers
from .errorSerializer import ErrorSerializer
from .choices import LanguageChoices, CountryCodes, LinkTokenProductChoices
from phonenumbers import parse, is_valid_number, format_number, PhoneNumberFormat


def e164_phone_number_validator(value):
    try:
        parsed = parse(value, None)

        if not is_valid_number(parsed):
            raise serializers.ValidationError("Invalid phone number")
        
        formatted = format_number(parsed, PhoneNumberFormat.E164)
        if value != formatted:
            raise serializers.ValidationError("Phone number not in E.164 format")
        
        return value
    except Exception as e:
        raise serializers.ValidationError("Invalid phone number")

# /link/create/token request

class LinkTokenCreateRequestUserSerializer(serializers.Serializer):
    """
    Serializer for the 'user' field in the LinkTokenCreateRequest.
    """
    client_user_id = serializers.CharField(
        required=False,
        help_text="A unique ID representing the end user. Used for logging and analytics."
    )
    legal_name = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="The user's full legal name."
    )
    email_address = serializers.EmailField(
        required=False,
        allow_null=True,
        help_text="The user's email address."
    )
    phone_number = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="The user's phone number.",
        validators=[e164_phone_number_validator]
    )
    ssn = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="The user's Social Security Number."
    )
    date_of_birth = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="The user's date of birth."
    )
    # Additional optional fields can be added here as needed.

class LinkTokenCreateRequestAccountFiltersSerializer(serializers.Serializer):
    """
    Serializer for the 'account_filters' field in the LinkTokenCreateRequest.
    """
    depository = serializers.DictField(
        child=serializers.ListField(
            child=serializers.CharField()
        ),
        required=False,
        help_text="Filters for depository accounts."
    )
    credit = serializers.DictField(
        child=serializers.ListField(
            child=serializers.CharField()
        ),
        required=False,
        help_text="Filters for credit accounts."
    )
    # Add other account types if needed.

class LinkTokenCreateRequestTransactionsSerializer(serializers.Serializer):
    """
    Serializer for the 'transactions' field in the LinkTokenCreateRequest.
    """
    days_requested = serializers.IntegerField(
        min_value=30, 
        max_value=730,
        help_text="The maximum number of days of transaction history to \
                   request for the Transactions product"
    )

class LinkTokenCreateRequestSerializer(serializers.Serializer):
    """
    Serializer for the request data sent to /link/token/create endpoint.
    """
    client_name = serializers.CharField(
        required=False,
        help_text="The name of your application."
    )
    language = serializers.ChoiceField(
        help_text="The language that Link should be displayed in.",
        choices=LanguageChoices.choices()
    )
    country_codes = serializers.ListField(
        child=serializers.ChoiceField(choices=CountryCodes.choices()),
        help_text="List of country codes supported by your application.",
    )
    user = LinkTokenCreateRequestUserSerializer(
        help_text="An object containing information about the end user."
    )
    products = serializers.ListField(
        child=serializers.ChoiceField(choices=LinkTokenProductChoices.choices()),
        help_text="List of Plaid products to use."
    )
    webhook = serializers.URLField(
        required=False,
        allow_null=True,
        help_text="The webhook URL to receive notifications."
    )
    link_customization_name = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="The name of the customization to apply to Link."
    )
    account_filters = LinkTokenCreateRequestAccountFiltersSerializer(
        required=False,
        allow_null=True,
        help_text="Filters to apply to the accounts shown in Link."
    )
    access_token = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="An access token associated with an Item to modify."
    )
    redirect_uri = serializers.URLField(
        required=False,
        allow_null=True,
        help_text="The redirect URI to be used upon completion of the Link flow."
    )
    android_package_name = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="The Android package name to redirect to upon completion."
    )
    transactions = LinkTokenCreateRequestTransactionsSerializer(
        required=True,
        allow_null=False,
        help_text="Configuration parameters for the Transactions product"
    )


    # Additional optional fields can be added here as needed.

# /link/create/token response

class LinkTokenCreateResponseSerializer(serializers.Serializer):
    """
    Serializer for the response data received from /link/token/create endpoint.
    """
    link_token = serializers.CharField(
        help_text="A link_token that can be used to initialize Link."
    )
    expiration = serializers.DateTimeField(
        help_text="The expiration time of the link_token."
    )
    request_id = serializers.CharField(
        help_text="A unique identifier for the request, used for troubleshooting."
    )