from django.core.exceptions import ValidationError
from rest_framework import serializers

class ConnectRobinhoodLoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=255, allow_null=True)
    password = serializers.CharField(max_length=255, allow_null=True)
    challenge_code = serializers.CharField(max_length=255, allow_null=True, default=None)
    mfa_code = serializers.CharField(max_length=255, allow_null=True, default=None)
    by_sms = serializers.BooleanField(allow_null=True, default=True)
    device_token = serializers.CharField(max_length=255, allow_null=True, default=None)

