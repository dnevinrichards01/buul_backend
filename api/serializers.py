from django.contrib.auth.models import User
from rest_framework import serializers
from .models import WaitlistEmail
from django.core.validators import validate_email
from django.core.exceptions import ValidationError


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'password']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        #print(validated_data)
        user = User.objects.create_user(**validated_data)
        return user
"""    
class NoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Note
        fields = ['id', 'title', 'content', 'created_at', 'author']
        extra_kwargs = {'author': {'read_only': True}}
"""

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

        