from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.ConnectRobinhoodView.as_view(), name='login'),
    #path('login_updates/', views.ConnectRobinhoodView.as_view({'get': 'get'}), name='check_login_updates')
]