from django.test import TestCase
from .models import User, WaitlistEmail, PlaidUser, UserBrokerageInfo
from rest_framework.views import APIView
from .serializers.buul import WaitlistEmailSerializer, \
    EmailPhoneSignUpValidationSerializer, UserBrokerageInfoSerializer, NamePasswordValidationSerializer, \
    VerificationCodeResponseSerializer, VerificationCodeRequestSerializer, SendEmailSerializer, \
    PasswordResetSerializer
from .serializers.buul import UserSerializer, WaitlistEmailSerializer
from .serializers.plaid.item import ItemPublicTokenExchangeRequestSerializer
from .serializers.plaid.link import \
    LinkTokenCreateRequestTransactionsSerializer, LinkTokenCreateRequestSerializer, \
    PlaidSessionFinishedSerializer
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication

from django.http import HttpResponseBadRequest, HttpResponse, JsonResponse
from rest_framework.exceptions import ValidationError
from django.core.cache import cache
import json
import phonenumbers

from celery import current_app, chain
from functools import partial
from django.db import transaction
from .tasks.user import plaid_item_public_tokens_exchange, \
    plaid_link_token_create, plaid_user_create, buul_user_remove, \
    plaid_user_remove, send_verification_code, send_waitlist_email, send_forgot_email
from .tasks.identify import get_investment_graph_data

import time
from django.core.mail import send_mail
from django.urls import reverse
import secrets 

# import pdb

import pyotp

import robin_stocks.robinhood as r

import time 

# Standard unittest.TestCase Methods:
#   - assertEqual(a, b, msg=None)
#   - assertNotEqual(a, b, msg=None)
#   - assertTrue(x, msg=None)
#   - assertFalse(x, msg=None)
#   - assertIs(a, b, msg=None)
#   - assertIsNot(a, b, msg=None)
#   - assertIsNone(x, msg=None)
#   - assertIsNotNone(x, msg=None)
#   - assertIn(member, container, msg=None)
#   - assertNotIn(member, container, msg=None)
#   - assertIsInstance(obj, cls, msg=None)
#   - assertNotIsInstance(obj, cls, msg=None)
#   - assertRaises(exception, callable, *args, **kwargs)
#       (also supports context manager form)
#   - assertRaisesRegex(exception, regex, callable, *args, **kwargs)
#   - assertAlmostEqual(a, b, places=None, msg=None, delta=None)
#   - assertNotAlmostEqual(a, b, places=None, msg=None, delta=None)

# Setup and Teardown Methods:
#   - setUp()
#   - tearDown()
#   - setUpClass()
#   - tearDownClass()

# Django-Specific Extensions:
#   - setUpTestData()

# HTTP Client & Response Assertions:
#   - assertContains(response, text, count=None, status_code=200, msg_prefix='', html=False)
#   - assertNotContains(response, text, status_code=200, msg_prefix='', html=False)
#   - assertRedirects(response, expected_url, status_code=302, target_status_code=200, msg_prefix='', fetch_redirect_response=True)
#   - assertTemplateUsed(response, template_name, msg_prefix='', count=None)
#   - assertTemplateNotUsed(response, template_name, msg_prefix='')
#   - assertFormError(response, form, field, errors, msg_prefix='')

# Query and HTML Assertions:
#   - assertQuerysetEqual(qs, values, transform=repr, ordered=True, msg_prefix='')
#   - assertHTMLEqual(html1, html2, msg=None)
#   - assertHTMLNotEqual(html1, html2, msg=None)
#   - assertInHTML(needle, haystack, count=None, msg_prefix='')
#   - assertNumQueries(num, func=None, *args, **kwargs)
#       (also available as a context manager: "with self.assertNumQueries(n): ...")

from django.test import TestCase

class MyModelTestCase(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        username = "dnevinrichards@gmail.com"
        password = "Pumpkinpie42."
        user = User(
            username=username,
            email=username,
            phone_number="+14086127386",
            full_name="Nevin Richards"
        )
        user.set_password(password)
        user.save()

        cls.shared_data = {
            "user": user,
            "username": username,
            "password": password
        }
	
    @classmethod
    def tearDownClass(cls):
        cls.shared_data["user"].delete()
        super().tearDownClass()
    
    def setUp(self):
        tokens = self.client.post(
            "/api/token/",
            {
                "username": self.shared_data["username"],
                "password": self.shared_data["password"]
            }
        )
        tokens_loaded = json.loads(tokens.content)

        self.shared_data["access"] = tokens_loaded["access"]
        self.shared_data["refresh"] = tokens_loaded["refresh"]
	
    def tearDown(self):
        return

    def test_login_endpoint(self):
        import pdb; breakpoint()
        response = self.client.post(
            "/rh/login/",
            {
                "username": self.shared_data["username"],
                "password": self.shared_data["password"],
                # "mfa_code": "111111",
                # "challenge_code": "111111",
            },
            HTTP_AUTHORIZATION=f"Bearer {self.shared_data["access"]}"
        )
    
    # def test_login_method(self):
    #     import pdb; breakpoint()
        # response = self.client.post(
        #     "/rh/login/",
        #     {
        #         "username": self.shared_data["username"],
        #         "password": self.shared_data["password"],
        #         # "mfa_code": "111111",
        #         # "challenge_code": "111111",
        #     },
        #     HTTP_AUTHORIZATION=f"Bearer {self.shared_data["access"]}"
        # )
        # login_res = r.login(
        #     session=r.create_session(), 
        #     # mfa_code=None,#pyotp.TOTP("6YRNMXMB4WDWX4ML").now(), 
        #     #challenge_code="111111",
        #     uid=self.shared_data["user"].id, 
        #     username=self.shared_data["username"], 
        #     password=self.shared_data["password"],
        #     device_approval=True
        # )
        # self.assertEqual(str(obj), 'Test Object')
        return



# def test_login(uid):
# 	import pdb; breakpoint()
	# login_res = r.login(
    #     session=r.create_session(), 
    #     mfa_code=None,#pyotp.TOTP("6YRNMXMB4WDWX4ML").now(), 
    #     uid=uid, 
    #     username="dnevinrichards@gmail.com", 
    #     password="Pumpkinpie42."
    # )
# 	return login_res

# def test_refresh(uid):
# 	import pdb
# 	breakpoint()
# 	refresh_res = r.refresh(session=r.create_session(), uid=uid)
# 	return refresh_res

# test_login(nevin.id)


# ____

# from api.models import User
# nevin = User(
#     username="dnevinrichards@gmail.com",
#     email="dnevinrichards@gmail.com",
#     phone_number="+14086127386",
#     full_name="Nevin Richards"
# )
# nevin.set_password("Pumpkinpie42.")
# nevin.save()
# import robin_stocks.robinhood as r
# import pyotp
# 
# def test_login(device=False):
#     import pdb
#     breakpoint()
#     if device:
#         login_res = r.login(
#             session=r.create_session(), 
#             # mfa_code=None,#pyotp.TOTP("6YRNMXMB4WDWX4ML").now(), 
#             #challenge_code="111111",
#             uid=nevin.id, 
#             username="dnevinrichards@gmail.com",
#             password="Pumpkinpie42.",
#             device_approval=True
#         )
#     else:
#         login_res = r.login(
#             session=r.create_session(), 
#             # mfa_code=None,#pyotp.TOTP("6YRNMXMB4WDWX4ML").now(), 
#             #challenge_code="111111",
#             uid=nevin.id, 
#             username="dnevinrichards@gmail.com",
#             password="Pumpkinpie42.",
#             # device_approval=True
#         )
#     return login_res

# def test_refresh(uid):
# 	import pdb
# 	breakpoint()
# 	refresh_res = r.refresh(session=r.create_session(), uid=uid)
# 	return refresh_res

# test_login(nevin.id)

# ____


# from api.models import User
# nevin = User.objects.all().first()
# import robin_stocks.robinhood as r
# from django.core.cache import cache
# import pyotp
# def test_login(uid):
# 	import pdb
# 	breakpoint()
# 	login_res = r.login(session=r.create_session(), mfa_code=None, challenge_code=422446, uid=uid, username="dnevinrichards@gmail.com", password="Pumpkinpie42.", device_token=None)
# 	return login_res



# def check_approval(uid):
# 	import pdb
# 	breakpoint()
# 	result = r.check_device_approvals(uid)
# 	return result

# cache.get(f"uid_{nevin.id}_challenge")


# def test_refresh(uid):
# 	import pdb
# 	breakpoint()
# 	refresh_res = r.refresh(session=r.create_session(), uid=uid)
# 	return refresh_res

# test_login(nevin.id)

# _____


# from django.contrib.auth.models import User
# nevin = User.objects.all().first()
# import robin_stocks.robinhood as r
# import pyotp
# def test_login(uid):
# 	import pdb
# 	breakpoint()
# 	login_res = r.login(session=r.create_session(), challenge_code=477679, mfa_code=None, uid=uid, username="dnevinrichards@gmail.com", password="Pumpkinpie42.")
# 	return login_res

# def test_refresh(uid):
# 	import pdb
# 	breakpoint()
# 	refresh_res = r.refresh(session=r.create_session(), uid=uid)
# 	return refresh_res

# test_login(nevin.id)

# __

# def test_login(uid):
# 	import pdb
# 	breakpoint()
# 	login_res = r.login(session=r.create_session(), mfa_code=None, uid=uid, username="dnevinrichards@gmail.com", password="Pumpkinpie42.", challenge_type= "sms", challenge_id= "f6433112-39c4-428c-8bf9-e001c6142753", device_token="7c1ea404-6dc3-5e9e-f1fa-751dd73e481d", challenge_code="443024")
# 	return login_res
# ____

# {"challenge_type": "sms","inquiries_url": "https://api.robinhood.com/pathfinder/inquiries/1bad30de-13f9-4aa1-8bec-d7d16e5c3ca7/user_view/","challenge_id": "588aea61-c483-40f5-9067-6b169d708c3c","device_token": "a8e55453-0589-81f8-3818-66f1812e5209","message": "That sms code was not correct. Please type in the new code"}



# If status in challenge_response
# But also check for {‘detail': 'Challenge has expired.'} when doing sms
# What about mfa?

# _____

# from django.contrib.auth.models import User
# nevin = User.objects.all().first()
# import robin_stocks.robinhood as r
# import pyotp
# def test_login(uid):
# 	import pdb
# 	breakpoint()
# 	login_res = r.login(session=r.create_session(), challenge_code=None, mfa_code=None, uid=uid, username="dnevinrichards@gmail.com", password="Pumpkinpie42.", by_sms=False)
# 	return login_res

# from django.contrib.auth.models import User
# nevin = User.objects.all().first()
# import robin_stocks.robinhood as r
# import pyotp
# def test_login(uid):
# 	import pdb
# 	breakpoint()
# 	login_res = r.login(session=r.create_session(), challenge_code="286385", mfa_code=None, uid=uid, username="dnevinrichards@gmail.com", password="Pumpkinpie42.")
# 	return login_res

# _____

# from rest_framework.test import APIClient
# from api.models import User
# import json

# client = APIClient()
# nevin = User.objects.all().first()
# client.force_authenticate(user=nevin)

# response = client.post("/api/plaid/publictokenexchange/", json.dumps({"public_token": "public-sandbox-03a487ba-3bfa-4b2a-9e44-8b7b7026dd0d"}), content_type="application/json")
# response = client.get("/api/plaid/publictokenexchange/")

# (Later do response.content)

# from api.tasks import plaid_item_public_token_exchange
# plaid_item_public_token_exchange(uid=1, public_token="public-sandbox-03a487ba-3bfa-4b2a-9e44-8b7b7026dd0d")


# ____

# from rest_framework.test import APIClient
# from api.models import User
# import json

# client = APIClient()
# nevin = User.objects.all().first()
# client.force_authenticate(user=nevin)

# response = client.post("/api/plaid/linktokencreate/", json.dumps({
#     "user": {
#         "phone_number": "+14155550123",
#         "email_address": "dnevinrichards@gmail.com"
#     },
#     "client_name": "Personal Finance App",
#     "products": [
#         "balance_plus",
#         "transactions"
#     ],
#     "transactions": {
#         "days_requested": 100
#     },
#     "country_codes": [
#         "US"
#     ],
#     "language": "en"
# }), content_type="application/json")

# response = client.get("/api/plaid/linktokencreate/")

# from api.models import User
# from api.tasks.userTasks import plaid_link_token_create
# plaid_link_token_create(**{'client_name': '', 'language': 'en', 'country_codes': ['US'], 'user': {'phone_number': '+14155550123', 'email_address': 'dnevinrichards@gmail.com'}, 'products': ['transactions'], 'transactions': {'days_requested': 100}, 'uid': 1})

# ____

# from api.models import User
# from api.tasks import plaid_accounts_get
# plaid_accounts_get(User.objects.all().first().id)

# from api.models import User
# from api.tasks import plaid_balance_get
# from api.tasks import process_plaid_balance
# res_balance = plaid_balance_get(User.objects.all().first().id)
# processed_balances = process_plaid_balance(res_balance)

# from api.models import User
# from api.tasks import plaid_item_remove
# plaid_item_remove(User.objects.all().first().id)

# from api.models import User
# from api.tasks.userTasks import plaid_user_create
# plaid_user_create(**{"uid": User.objects.all().first().id})

# from api.models import User
# from api.tasks import transactions_sync
# transactions_sync(User.objects.all().first().id)

# from api.models import User
# from api.tasks import transactions_get
# transactions_get(User.objects.all().first().id, "2023-01-01", "2024-01-01")

# from api.models import User
# from api.tasks import transactions_categories_sum
# transactions_categories_sum(res)

# from api.models import User
# from api.tasks import transactions_get
# from api.tasks import transactions_sync
# from api.tasks import transactions_categories_sum
# from api.tasks import transactions_identify_cashback
# res_sync = transactions_sync(User.objects.all().first().id)
# res_get = transactions_get(User.objects.all().first().id, "2023-01-01", "2024-01-01")
# cashback_sync = transactions_identify_cashback(res_sync)
# cashback_get = transactions_identify_cashback(res_get, transactions_sync=False)
# analyzed_sync = transactions_categories_sum(res_sync)
# analyzed_get = transactions_categories_sum(res_get, transactions_sync=False)
# analyzed_sync_personal = transactions_categories_sum(res_sync, personal_finance_categories=True)
# analyzed_get_personal = transactions_categories_sum(res_get, transactions_sync=False, personal_finance_categories=True)

# transactions_identify_cashback


# from api.tasks import all_categories
# categs = all_categories()
# _______





# from rest_framework.test import APIClient
# from api.models import User
# import json

# client = APIClient()
# nevin = User.objects.all().first()

# response = client.post("/api/user/requestpasswordreset/", json.dumps({"email": "dnevinrichards@gmail.com"}), content_type="application/json")


# client.force_authenticate(user=nevin)
# response = client.post("/api/user/delete/")

# from api.tasks import plaid_user_remove
# from api.tasks import buul_user_remove


# ____

# from api.models import User
# nevin = User.objects.all().first()
# import robin_stocks.robinhood as r

# from api.tasks.investTasks import rh_deposit_funds_to_robinhood_account
# rh_deposit_funds_to_robinhood_account(nevin.id, "https://api.robinhood.com/ach/relationships/8604c876-1658-424a-be60-22be984ac2f5/", 3)


# from api.models import User
# nevin = User.objects.all().first()
# import robin_stocks.robinhood as r
# from api.tasks.investTasks import rh_get_linked_bank_accounts
# rh_get_linked_bank_accounts(nevin.id)
# rh_get_linked_bank_accounts(nevin.id, eq={"url": ["https://api.robinhood.com/ach/relationships/8604c876-1658-424a-be60-22be984ac2f5/"]}, metric_to_return_by="url")

# from api.models import User
# nevin = User.objects.all().first()
# import robin_stocks.robinhood as r
# from api.tasks.investTasks import rh_get_bank_transfers
# rh_get_bank_transfers(nevin.id)

# import datetime
# import zoneinfo
# transfers = rh_get_bank_transfers(nevin.id, lt={"expected_landing_datetime": [datetime.datetime(2024, 11, 4, 15, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC'))]}, metric_to_return_by="state")




# from api.models import User
# nevin = User.objects.all().first()
# import robin_stocks.robinhood as r
# from api.tasks.investTasks import rh_get_bank_transfers, filter_jsons
# transfers = rh_get_bank_transfers(nevin.id)

# filtered_jsons = filter_jsons(transfers, eq={"state": ["completed"]})

# import datetime
# import zoneinfo
# filtered_jsons = filter_jsons(transfers, lt={"expected_landing_datetime": [datetime.datetime(2024, 11, 4, 15, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC'))]}, metric_to_return_by="state")


# from api.models import User
# nevin = User.objects.all().first()
# import robin_stocks.robinhood as r
# from api.tasks.investTasks import rh_get_stock_order_info, filter_jsons
# info = rh_get_stock_order_info(nevin.id, "678ea898-2de8-4f0e-82db-78ccba93f86a")
# filtered_jsons = filter_jsons([info], eq={"amount": [1.0]}, metric_to_return_by="amount")
# Or
# filtered_jsons = filter_jsons([info], custom_func={"func": (lambda x, y: x==y), "filter_set": {"amount": [1.0]}}, metric_to_return_by="amount")



# from api.models import User
# nevin = User.objects.all().first()
# import robin_stocks.robinhood as r

# from api.tasks.investTasks import rh_order_sell_fractional_by_price
# rh_order_sell_fractional_by_price(nevin.id, "VOO", 1)



# from api.models import User
# nevin = User.objects.all().first()
# import robin_stocks.robinhood as r

# from api.tasks.investTasks import rh_order_buy_fractional_by_price
# rh_order_buy_fractional_by_price(nevin.id, "VOO", 1)


# https://api.robinhood.com/ach/relationships/8604c876-1658-424a-be60-22be984ac2f5/ 

# {'account_id': 'jAJEZz1xVKHe9ag3JEegt3P33p3opbiQXpjPo', 'balances': {'available': 100.0, 'current': 110.0, 'limit': None, 'iso_currency_code': 'USD', 'unofficial_currency_code': None}, 'mask': '0000', 'name': 'Plaid Checking', 'official_name': 'Plaid Gold Standard 0% Interest Checking', 'subtype': 'checking', 'type': 'depository'}


# from api.models import User
# nevin = User.objects.all().first()
# import robin_stocks.robinhood as r
# from api.tasks.investTasks import rh_get_stock_order_info
# rh_get_stock_order_info(nevin.id, "678ea898-2de8-4f0e-82db-78ccba93f86a")


# from api.models import User
# nevin = User.objects.all().first()
# import robin_stocks.robinhood as r
# from api.tasks.investTasks import rh_find_stock_orders_custom
# rh_find_stock_orders_custom(nevin.id, amount=1.0, currency_code="USD", instrument_id="306245dd-b82d-4d8d-bcc5-7c58e87cdd15", created_day_range=1)

# from api.models import User
# nevin = User.objects.all().first()
# import robin_stocks.robinhood as r
# from api.tasks.investTasks import rh_cancel_stock_order
# rh_cancel_stock_order(nevin.id)
