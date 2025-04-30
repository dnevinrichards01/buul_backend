from django.core.exceptions import ValidationError
from rest_framework import serializers
from .error import ErrorSerializer

# Plaid User Serializers

class UserNameSerializer(serializers.Serializer):
    """
    Serializer for a user's name information.
    """
    full_name = serializers.CharField(allow_null=True, help_text="Full name of the user.")
    first_name = serializers.CharField(allow_null=True, help_text="First name of the user.")
    last_name = serializers.CharField(allow_null=True, help_text="Last name of the user.")
    middle_name = serializers.CharField(allow_null=True, help_text="Middle name of the user.")
    suffix = serializers.CharField(allow_null=True, help_text="Suffix of the user's name (e.g., Jr., Sr.).")
    prefix = serializers.CharField(allow_null=True, help_text="Prefix of the user's name (e.g., Mr., Ms.).")

class UserEmailSerializer(serializers.Serializer):
    """
    Serializer for a user's email information.
    """
    data = serializers.EmailField(allow_null=True, help_text="Email address of the user.")
    primary = serializers.BooleanField(help_text="Indicates if this is the primary email address.")
    type = serializers.CharField(allow_null=True, help_text="Type of email (e.g., 'work', 'personal').")

class UserPhoneNumberSerializer(serializers.Serializer):
    """
    Serializer for a user's phone number information.
    """
    data = serializers.CharField(allow_null=True, help_text="Phone number of the user.")
    primary = serializers.BooleanField(help_text="Indicates if this is the primary phone number.")
    type = serializers.CharField(allow_null=True, help_text="Type of phone number (e.g., 'mobile', 'home').")

class UserAddressDataSerializer(serializers.Serializer):
    """
    Serializer for the address data within a user's address.
    """
    street = serializers.CharField(allow_null=True, help_text="Street address.")
    city = serializers.CharField(allow_null=True, help_text="City.")
    region = serializers.CharField(allow_null=True, help_text="State or region.")
    postal_code = serializers.CharField(allow_null=True, help_text="Postal code.")
    country = serializers.CharField(allow_null=True, help_text="Country.")

class UserAddressSerializer(serializers.Serializer):
    """
    Serializer for a user's address information.
    """
    data = UserAddressDataSerializer(allow_null=True, help_text="Detailed address information.")
    primary = serializers.BooleanField(help_text="Indicates if this is the primary address.")
    type = serializers.CharField(allow_null=True, help_text="Type of address (e.g., 'home', 'work').")

class UserIdentitySerializer(serializers.Serializer):
    """
    Serializer for the user's identity information.
    """
    names = serializers.ListField(
        child=UserNameSerializer(),
        help_text="List of names associated with the user."
    )
    emails = serializers.ListField(
        child=UserEmailSerializer(),
        help_text="List of email addresses associated with the user."
    )
    phone_numbers = serializers.ListField(
        child=UserPhoneNumberSerializer(),
        help_text="List of phone numbers associated with the user."
    )
    addresses = serializers.ListField(
        child=UserAddressSerializer(),
        help_text="List of addresses associated with the user."
    )




class UserGetRequestSerializer(serializers.Serializer):
    """
    Serializer for the request data sent to /users/get endpoint.
    """
    access_token = serializers.CharField(
        help_text="The access token associated with the Item data is being requested for."
    )

class UserGetResponseSerializer(serializers.Serializer):
    """
    Serializer for the response data received from /users/get endpoint.
    """
    user = UserIdentitySerializer(help_text="User identity information.")
    request_id = serializers.CharField(help_text="A unique identifier for the request, used for troubleshooting.")
    error = ErrorSerializer(allow_null=True, help_text="Error object containing error details, if any.")



class UserCreateRequestSerializer(serializers.Serializer):
    """
    Serializer for the request data sent to /user/create endpoint.
    """
    client_user_id = serializers.CharField(
        help_text="A unique ID representing the end user",
        max_length=128
    )

class UserCreateResponseSerializer(serializers.Serializer):
    """
    Serializer for the response data recieved from /user/create endpoint.
    """
    request_id = serializers.CharField(
        help_text="A unique identifier for the request"
    )
    user_token = serializers.CharField(
        help_text="The user token associated with the User data is being requested for."
    )
    user_id = serializers.CharField(
        help_text="The Plaid user_id of the User associated with this webhook, warning, or error"
    )



class UserRemoveRequestSerializer(serializers.Serializer):
    """
    Serializer for the request data sent to /user/remove endpoint.
    """
    client_user_id = serializers.CharField(
        help_text="A unique ID representing the end user",
        max_length=128
    )

class UserRemoveResponseSerializer(serializers.Serializer):
    """
    Serializer for the response data recieved from /user/remove endpoint.
    """
    request_id = serializers.CharField(
        help_text="A unique identifier for the request"
    )