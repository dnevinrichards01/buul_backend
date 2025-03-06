from django.urls import path
from . import views
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


urlpatterns = [
    # sign up flow
    path('user/createuser/', views.CreateUserView.as_view(), name='create_user'),
    path('user/namepasswordvalidation/', views.NamePasswordValidation.as_view(), name='name_password_validation'),
    path('user/emailphonesignupvalidation/', views.EmailPhoneSignUpValidation.as_view(), name='email_phone_signup_validation'),
    path('user/setbrokerageinvestment/', views.SetBrokerageInvestment.as_view(), name='get_brokerage_investment'),
    
    # plaid
    path('plaid/usercreate/', views.PlaidUserCreate.as_view(), name='plaid_user_create'),
    path('plaid/linktokencreate/', views.PlaidLinkTokenCreate.as_view(), name='plaid_link_token_create'),
    path('plaid/itemwebhook/', views.PlaidItemWebhook.as_view(), name='plaid_item_webhook'),
    
    # fetch account info 
    path('user/getuserinfo/', views.GetUserInfo.as_view(), name='get_user_info'),
    path('user/getstockgraphdata/', views.StockGraphData.as_view(), name='get_stock_graph_data'),

    # update info
    path('user/resetpassword/', views.ResetPassword.as_view(), name='reset_password'),
    path('user/requestverificationcode/', views.RequestVerificationCode.as_view(), name='request_verification_code'),
    path('user/sendemail/', views.SendEmail.as_view(), name='send_email'),
    path('user/deleteaccountverify/', views.DeleteAccountVerify.as_view(), name='delete_account_verify'),
    
    # etc
    path('waitlist/', views.AddToWaitlist.as_view(), name='waitlist'),
    path('token/', TokenObtainPairView.as_view(), name='get_token'),
    path('token/refresh/', TokenRefreshView.as_view(), name='refresh')
]