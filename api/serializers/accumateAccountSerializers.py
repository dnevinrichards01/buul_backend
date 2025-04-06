# from django.contrib.auth.models import User
from rest_framework import serializers
from ..models import WaitlistEmail, User, BROKERAGE_CHOICES, SYMBOL_CHOICES
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from .PlaidSerializers.linkSerializers import e164_phone_number_validator
from api.models import User

invalid_password_error_message = "The password must contain at least one capital " + \
    "letter, one digit, 8 characters, and one symbol of the following symbols: " + \
    "@, $, !, ., %%, *, ?, &."

FIELD_CHOICES = [
    ('email', 'email'),
    ('phone_number', 'phone_number'),
    ('full_name', 'full_name'),
    ('brokerage', 'brokerage'),
    ('symbol', 'symbol'),
    ('password', 'password'),
    ('delete_account', 'delete_account')
]

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):


    def validate(self, attrs):
        # get user
        email = attrs.pop('email')
        try:
            user = User.objects.get(email=email)
            attrs['username'] = user.id
        except:
            raise ValidationError("no such user")
        
        # if found user, validate as before
        data = super().validate(attrs)
        return data

class GraphDataRequestSerializer(serializers.Serializer):
    start_date = serializers.DateTimeField()

class UserSerializer(serializers.ModelSerializer):
    password = serializers.RegexField(
        regex=r'^(?=.*[A-Z])(?=.*\d)(?=.*[@$!\.%*?&])[A-Za-z\d@$!\.%*?&]{8,}$',
        required=False,
        write_only=True,
        error_messages={"invalid": invalid_password_error_message}
    )
    pre_account_id = serializers.IntegerField(min_value=0, max_value=99999999, required=True)
    class Meta:
        model = User
        fields = ['phone_number', 'full_name', 'password', 'email', 'pre_account_id']
        extra_kwargs = {'password': {'write_only': True}}
    

    def create(self, validated_data):
        validated_data.pop('pre_account_id', None)
        user = User(**validated_data)
        user.save()
        return user

class NamePasswordValidationSerializer(serializers.Serializer):
    pre_account_id = serializers.IntegerField(min_value=0, max_value=99999999, required=True)
    full_name = serializers.CharField(required=False)
    password = serializers.RegexField(
        regex=r'^(?=.*[A-Z])(?=.*\d)(?=.*[@$!\.%*?&])[A-Za-z\d@$!\.%*?&]{8,}$',
        required=False,
        write_only=True,
        error_messages={"invalid": invalid_password_error_message}
    )

    def validate(self, attrs):
        if ("full_name" in attrs) == ("password" in attrs):
            raise ValidationError("You can only submit one value at a time")
        return attrs

class VerificationCodeResponseSerializer(serializers.Serializer):
    pre_account_id = serializers.IntegerField(min_value=0, max_value=99999999, required=False)
    verification_email = serializers.EmailField(required=False)
    verification_phone_number = serializers.CharField(required=False, validators=[e164_phone_number_validator])
    email = serializers.EmailField(required=False)
    phone_number = serializers.CharField(required=False, validators=[e164_phone_number_validator])
    full_name = serializers.CharField(required=False)
    brokerage = serializers.ChoiceField(required=False, choices=BROKERAGE_CHOICES)
    symbol = serializers.ChoiceField(required=False, choices=SYMBOL_CHOICES)
    password = serializers.RegexField(
        regex=r'^(?=.*[A-Z])(?=.*\d)(?=.*[@$!\.%*?&])[A-Za-z\d@$!\.%*?&]{8,}$',
        required=False,
        write_only=True,
        error_messages={"invalid": invalid_password_error_message}
    )
    delete_account = serializers.BooleanField(required=False)
    code = serializers.RegexField(
        regex=r'^[\d]{6}$',
        required=True,
        write_only=True,
        error_messages={"invalid": "The code must consist of 6 digits"}
    )
    field = serializers.ChoiceField(
        required=True,
        choices=FIELD_CHOICES
    )

    def validate(self, attrs):
        if ("verification_email" in attrs) == ("verification_phone_number" in attrs):
            raise serializers.ValidationError("You must submit either the email or phone number associated with your account.")
        if ('pre_account_id' in attrs and len(attrs) != 5) \
                or ('pre_account_id' not in attrs and len(attrs) != 4):
            raise serializers.ValidationError("You may only change or verify one thing at a time.")
        if attrs["field"] not in attrs:
            raise ValidationError(f"No {attrs['field']} was submitted")
        return attrs
    
class VerificationCodeRequestSerializer(serializers.Serializer):
    pre_account_id = serializers.IntegerField(min_value=0, max_value=99999999, required=False)
    verification_email = serializers.EmailField(required=False)
    verification_phone_number = serializers.CharField(required=False, validators=[e164_phone_number_validator])
    email = serializers.EmailField(required=False)
    phone_number = serializers.CharField(required=False, validators=[e164_phone_number_validator])
    full_name = serializers.CharField(required=False)
    brokerage = serializers.ChoiceField(required=False, choices=BROKERAGE_CHOICES)
    symbol = serializers.ChoiceField(required=False, choices=SYMBOL_CHOICES)
    password = serializers.RegexField(
        regex=r'^(?=.*[A-Z])(?=.*\d)(?=.*[@$!\.%*?&])[A-Za-z\d@$!\.%*?&]{8,}$',
        required=False,
        write_only=True,
        error_messages={"invalid": invalid_password_error_message}
    )
    password2 = serializers.CharField(
        required=False
    )
    delete_account = serializers.BooleanField(required=False)
    field = serializers.ChoiceField(
        required=True,
        choices=FIELD_CHOICES
    )

    def validate(self, attrs):
        if ("verification_email" in attrs) == ("verification_phone_number" in attrs):
            raise ValidationError("You must submit either the email or phone number associated with your account.")
        if attrs["field"] == "password":
            if "password2" not in attrs:
                raise ValidationError(f"No password2 was submitted")
            if len(attrs) != 4:
                raise ValidationError("You may only change or verify one thing at a time.")
            if attrs["password"] != attrs["password2"]:
                raise ValidationError("Passwords do not match")
        else:
            if ('pre_account_id' in attrs and len(attrs) != 4) \
                or ('pre_account_id' not in attrs and len(attrs) != 3):
                raise ValidationError("You may only change or verify one thing at a time.")
        if attrs["field"] not in attrs:
            raise ValidationError(f"No {attrs['field']} was submitted")
        return attrs

        
class SendEmailSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

class DeleteAccountVerifySerializer(serializers.Serializer):
    code = serializers.RegexField(
        regex=r'^[\d]{6}$',
        required=True,
        write_only=True,
        error_messages={"invalid": "The code must consist of 6 digits"}
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
    brokerage = serializers.ChoiceField(choices=BROKERAGE_CHOICES, required=False)
    symbol = serializers.ChoiceField(choices=SYMBOL_CHOICES, required=False)