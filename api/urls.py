from django.urls import path
from . import views
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


urlpatterns = [
    #path('notes/delete/<int:pk>/', views.NoteDelete.as_view(), name='delete-note'),
    #path('notes/', views.NoteListCreate.as_view(), name='note-list'),
    path('celery/test/', views.test_celery_task_view, name='celery_test'),
    path('celery/placebo/', views.test_placebo_task_view, name='celery_placebo'),
    path('user/register/', views.CreateUserView.as_view(), name='register'),
    path('token/', TokenObtainPairView.as_view(), name='get_token'),
    path('token/refresh/', TokenRefreshView.as_view(), name='refresh'),
    path('waitlist/', views.AddToWaitlist.as_view(), name='waitlist')
]





    
    
    