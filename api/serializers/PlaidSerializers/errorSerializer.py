from django.core.exceptions import ValidationError
from rest_framework import serializers

class ErrorSerializer(serializers.Serializer):
    """
    Generic serializer for handling Plaid API errors.
    """
    error_type = serializers.CharField(help_text="The broad categorization of the error.")
    error_code = serializers.CharField(help_text="The particular error code.")
    error_message = serializers.CharField(help_text="A developer-friendly error message.")
    display_message = serializers.CharField(allow_null=True, help_text="A user-friendly error message.")
    request_id = serializers.CharField(help_text="A unique identifier for the request, used for troubleshooting.")
    suggested_action = serializers.CharField(allow_null=True, help_text="Suggested steps for resolving the error.")
    status_code = serializers.IntegerField(help_text="The HTTP status code associated with the error.")
