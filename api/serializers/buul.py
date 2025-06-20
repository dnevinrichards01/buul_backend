# from django.contrib.auth.models import User
from rest_framework import serializers
from ..models import WaitlistEmail, User
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from .plaid.link import e164_phone_number_validator
from api.models import User
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.hashers import check_password

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

PASSWORD_REGEX = r'^(?=.*[A-Z])(?=.*\d)(?=.*[\-@$!\.%*?&])[A-Za-z\d\-@$!\.%*?&]{8,}$'

class MyTokenObtainPairSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.RegexField(
        regex=PASSWORD_REGEX,
        required=False,
        write_only=True,
        error_messages={"invalid": invalid_password_error_message}
    )
    app_version = serializers.CharField(required=False)

    def validate(self, attrs):
        email = attrs.pop('email').lower()
        password = attrs.pop('password')
        try:
            user = User.objects.get(email=email)
            if not check_password(password, user.password):
                raise ValidationError()
            attrs['user'] = user
            return attrs
        except:
            raise ValidationError("no such user")
        

class MyTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        try:
            refresh = RefreshToken(attrs["refresh"])
        except:
            raise ValidationError("Invalid or expired refresh token.")

        user_id = refresh.payload.get(api_settings.USER_ID_CLAIM, None)
        if user_id:
            user = User.objects.get(id=user_id)
        else:
            raise ValidationError("User not found")
        
        app_version = attrs.get('app_version', None)
        if app_version != user.app_version or \
            (app_version is not None or user.app_version != "pre_build_8"):
            user.app_version = app_version
            user.save()
        
        data = super().validate(attrs)

        data["user"] = user
        return data

class GraphDataRequestSerializer(serializers.Serializer):
    start_date = serializers.DateTimeField()

class UserSerializer(serializers.ModelSerializer):
    password = serializers.RegexField(
        regex=PASSWORD_REGEX,
        required=False,
        write_only=True,
        error_messages={"invalid": invalid_password_error_message}
    )
        
    pre_account_id = serializers.IntegerField(min_value=0, max_value=99999999, required=True)
    class Meta:
        model = User
        fields = ['phone_number', 'full_name', 'password', 'email', 'pre_account_id']
        extra_kwargs = {'password': {'write_only': True}}
    
    def validate(self, attrs):
        # also run query to make all emails lower case (practice on local first)
        attrs['email'] = attrs['email'].lower()
        return attrs

    def create(self, validated_data):
        validated_data.pop('pre_account_id', None)
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

class NamePasswordValidationSerializer(serializers.Serializer):
    pre_account_id = serializers.IntegerField(min_value=0, max_value=99999999, required=True)
    full_name = serializers.CharField(required=False)
    password = serializers.RegexField(
        regex=PASSWORD_REGEX,
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
    brokerage = serializers.CharField(required=False)
    symbol = serializers.CharField(required=False)
    password = serializers.RegexField(
        regex=PASSWORD_REGEX,
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
        if 'email' in attrs:
            attrs['email'] = attrs['email'].lower()
        if 'verification_email' in attrs:
            attrs['verification_email'] = attrs['verification_email'].lower()
        
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
    brokerage = serializers.CharField(required=False)
    symbol = serializers.CharField(required=False)
    password = serializers.RegexField(
        regex=PASSWORD_REGEX,
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
        if 'email' in attrs:
            attrs['email'] = attrs['email'].lower()
        if 'verification_email' in attrs:
            attrs['verification_email'] = attrs['verification_email'].lower()

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

    def validate(self, attrs):
        attrs['email'] = attrs['email'].lower()
        return attrs


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
        email = email.lower()
        try: 
            validate_email(email)
            return email
        except: 
            raise ValidationError()
        
    def validate(self, attrs):
        attrs['email'] = attrs['email'].lower()
        return attrs
        
class UserBrokerageInfoSerializer(serializers.Serializer):
    brokerage = serializers.CharField(required=False)
    symbol = serializers.CharField(required=False)
    overdraft_protection = serializers.BooleanField(required=False)

class RequestLinkTokenSerializer(serializers.Serializer):
    update = serializers.BooleanField(required=False)
    institution_name = serializers.CharField(required=False)

    def validate(self, attrs):
        if len(attrs) != 0 and len(attrs) < 2:
            raise ValidationError("Our update flow requires institution name")
        return attrs