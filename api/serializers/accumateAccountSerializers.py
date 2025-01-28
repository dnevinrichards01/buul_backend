# from django.contrib.auth.models import User
from rest_framework import serializers
from ..models import WaitlistEmail, User
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from .PlaidSerializers.linkSerializers import e164_phone_number_validator

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'password', 'email']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user


class EmailPhoneValidationSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    sms = serializers.CharField(required=False,validators=[e164_phone_number_validator])
    
class ResetPasswordRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    sms = serializers.CharField(validators=[e164_phone_number_validator])

class VerificationCodeSerializer(serializers.Serializer):
    code = serializers.RegexField(
        regex=r'^[\d]{6}$',
        required=True,
        write_only=True
    )

class ResetPasswordSerializer(serializers.Serializer):
    new_password = serializers.RegexField(
        regex=r'^(?=.*[A-Z])(?=.*\d)(?=.*[@$!\.%*?&])[A-Za-z\d@$!\.%*?&]{8,}$',
        required=True,
        write_only=True
    )
    confirm_password = serializers.RegexField(
        regex=r'^(?=.*[A-Z])(?=.*\d)(?=.*[@$!\.%*?&])[A-Za-z\d@$!\.%*?&]{8,}$',
        required=True,
        write_only=True
    )
    code = serializers.RegexField(
        regex=r'^[\d]{6}$',
        required=True,
        write_only=True
    )

class WaitlistEmailSerializer(serializers.ModelSerializer):

    email = serializers.EmailField()

    class Meta:
        model = WaitlistEmail
        fields = ['email']
        extra_kwargs = {'email': {'write_only': True}}

    def validate_email(self, email):
        try: 
            validate_email(email)
            return email
        except: 
            raise ValidationError()
        
class UserBrokerageInfoSerializer(serializers.Serializer):
    BROKERAGE_CHOICES = [
        ('Robinhood', 'Robinhood')
    ]
    SYMBOL_CHOICES = [
        ('VOO', 'VOO')
    ]
    brokerage = serializers.ChoiceField(choices=BROKERAGE_CHOICES)
    symbol = serializers.ChoiceField(choices=SYMBOL_CHOICES)