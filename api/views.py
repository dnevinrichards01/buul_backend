from django.shortcuts import render
from django.contrib.auth.models import User
from .models import WaitlistEmail
from rest_framework import generics
from .serializers.accumateAccountSerializers import UserSerializer, WaitlistEmailSerializer
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.http import HttpResponseBadRequest, HttpResponse
from django.core.exceptions import ValidationError



# Create your views here.
class CreateUserView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]

"""
class NoteListCreate(generics.ListCreateAPIView):
    serializer_class = NoteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Note.objects.filter(author=self.request.user)
    
    def perform_create(self, serializer):
        if serializer.is_valid():
            serializer.save(author=self.request.user)
        else:
            print(serializer.errors) #why not raise serializers.SerializerError?

class NoteDelete(generics.DestroyAPIView):
    serializer_class = NoteSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Note.objects.filter(author=self.request.user)
"""

class AddToWaitlist(generics.CreateAPIView):
    queryset = WaitlistEmail.objects.all()
    serializer_class = WaitlistEmailSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def create(self, request, *args, **kwargs):
        # check if valid email
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            print(serializer.errors)
            return HttpResponseBadRequest(serializer.errors)
        # check if duplicate
        email = serializer.validated_data['email']
        if WaitlistEmail.objects.filter(email=email).exists():
            return HttpResponseBadRequest("duplicate")
        # save
        serializer.save()
        return HttpResponse(status=201)

