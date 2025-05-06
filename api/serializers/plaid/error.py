from django.core.exceptions import ValidationError
from rest_framework import serializers

class ErrorSerializer(serializers.Serializer):
    """
    Generic serializer for handling Plaid API errors.
    """
    error_type = serializers.CharField(
        help_text="The broad categorization of the error.",
        required=True
    )
    error_code = serializers.CharField(
        help_text="The particular error code.",
        required=True
    )
    error_code_reason = serializers.CharField(
        help_text="The particular error code.",
        required=False,
        allow_null=True
    )
    error_message = serializers.CharField(
        help_text="A developer-friendly error message.",
        required=False,
        allow_null=True
    )
    display_message = serializers.CharField(
        allow_null=True, 
        help_text="A user-friendly error message.",
        required=False
    )
    request_id = serializers.CharField(
        help_text="A unique identifier for the request, used for troubleshooting.",
        allow_null=True, 
        required=False
    )
    suggested_action = serializers.CharField(
        allow_null=True, 
        help_text="Suggested steps for resolving the error.",
        required=False
    )
    # unsure of which is correct so allow either
    status_code = serializers.IntegerField(
        help_text="The HTTP status code associated with the error.",
        required=False,
        allow_null=True
    )
    status = serializers.IntegerField(
        help_text="The HTTP status code associated with the error.",
        required=False,
        allow_null=True
    )
