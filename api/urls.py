from django.urls import path
from . import views
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


urlpatterns = [
    path('user/register/', views.CreateUserView.as_view(), name='register'),
    path('token/', TokenObtainPairView.as_view(), name='get_token'),
    path('token/refresh/', TokenRefreshView.as_view(), name='refresh'),
    path('waitlist/', views.AddToWaitlist.as_view(), name='waitlist'),
    path('plaid/publictokenexchange/', views.PlaidItemPublicTokenExchange.as_view(), name='public_token_exchange'),
    path('plaid/linktokencreate/', views.PlaidLinkTokenCreate.as_view(), name='link_token_create'),
    path('plaid/usercreate/', views.PlaidUserCreate.as_view(), name='user_create'),
    path('user/delete/', views.DeleteAccount.as_view(), name='user_delete'),
    path('user/requestpasswordreset/', views.RequestPasswordReset.as_view(), name='request_password_reset'),
    path('user/resetpassword/', views.ResetPassword.as_view(), name='reset_password'),
    path('user/emailphonevalidation/', views.EmailPhoneValidation.as_view(), name='email_phone_validation'),
    path('user/brokerageinfo/', views.BrokerageInvestment.as_view(), name='brokerage_info'),
    path('user/getinvestmentdata/', views.StockGraphData.as_view(), name='get_investment_data')
]