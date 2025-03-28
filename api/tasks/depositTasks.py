from celery import shared_task, chain
from accumate_backend.settings import TWILIO_PHONE_NUMBER
import robin_stocks.robinhood as r
from django.utils import timezone

from ..plaid_client import plaid_client
# from ..twilio_client import twilio_client
from ..jsonUtils import filter_jsons

from datetime import datetime, timedelta
import json

from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
from plaid.exceptions import ApiException

from ..models import PlaidItem, User, PlaidCashbackTransaction, \
    RobinhoodCashbackDeposit, Investments, SYMBOL_CHOICES
from ..serializers.rhSerializers import GetLinkedBankAccountsResponseSerializer, \
    DepositSerializer
from ..serializers.PlaidSerializers.balanceSerializers import \
    BalanceGetResponseSerializer, AccountsGetResponseSerializer
# retry all of these bc sometimes you get 
# {'detail': 'Incorrect authentication credentials.'} when you just 
# refreshed access token but are using the old one here. 
# but not this one, retry the whole chain - for idempotency... 

# plaid deposit 

@shared_task(name="rh_deposit_funds_to_robinhood_account")
def rh_deposit_funds_to_robinhood_account(uid, ach_relationship, amount):
    import pdb
    breakpoint()

    # uid = kwargs.pop('uid')

    try:
        session, userRobinhoodInfo = r.rh_create_session(uid)
    except Exception as e:
        return {"error": f"could not find userRobinhoodInfo object for that {uid}"}
    
    result = r.deposit_funds_to_robinhood_account(session, ach_relationship, amount)
    
    try:
        serializer = DepositSerializer(data=result)
        serializer.is_valid(raise_exception=True)
    except Exception as e:
        try:
            transfers = rh_get_bank_transfers(
                uid, 
                eq={
                    "amount":[amount], 
                    "ach_relationship":[ach_relationship]
                }
            )
        except Exception as e:
            transfers = {"error": f"{str(e)}"}
        return {"error": f"robinhood response {result} caused {str(e)}",
                "recent_transfers": transfers}
    return serializer.validated_data

@shared_task(name="rh_get_bank_transfers")
def rh_get_bank_transfers(uid, eq={}, gt={}, lt={}, lte={}, gte={}, 
                          metric_to_return_by=None):
    import pdb
    breakpoint()
    # uid = kwargs.pop('uid')

    try:
        session, userRobinhoodInfo = r.rh_create_session(uid)
    except Exception as e:
        return {"error": f"could not find userRobinhoodInfo object for that {uid}"}
    result = r.get_bank_transfers(session)
    
    try:
        serializer = DepositSerializer(data=result, many=True)
        serializer.is_valid(raise_exception=True)
    except Exception as e:
        return {"error": f"{str(e)}"}
    
    return filter_jsons(serializer.validated_data, eq=eq, gt=gt, lt=lt, lte=lte, 
                        gte=gte, metric_to_return_by=metric_to_return_by)

@shared_task(name="rh_get_linked_bank_accounts")
def rh_get_linked_bank_accounts(uid, eq={}, gt={}, lt={}, lte={}, gte={}, 
                                metric_to_return_by=None):
    import pdb
    breakpoint()

    # uid = kwargs.pop('uid')

    try:
        session, userRobinhoodInfo = r.rh_create_session(uid)
    except Exception as e:
        return {"error": f"could not find userRobinhoodInfo object for that {uid}"}
    result = r.get_linked_bank_accounts(session)
    
    try:
        serializer = GetLinkedBankAccountsResponseSerializer(data=result, many=True)
        serializer.is_valid(raise_exception=True)
    except Exception as e:
        return {"error": f"{str(e)}"}
    
    eq.update({"verified": [True], "state": ["approved"]})
    return filter_jsons(serializer.validated_data, eq=eq, gt=gt, lt=lt, lte=lte, 
                        gte=gte, metric_to_return_by=metric_to_return_by)


# plaid balance

@shared_task(name="plaid_accounts_get")
def plaid_accounts_get(uid, item_id=None, balance_ids_by_item_id={}):
    import pdb
    breakpoint()
    
    try:
        plaidItems = PlaidItem.objects.filter(user__id=uid)
        accounts_get_by_item = {}
        for plaidItem in plaidItems:
            if item_id and item_id != plaidItem.itemId:
                continue
            if plaidItem.itemId in balance_ids_by_item_id:
                exchange_request = AccountsGetRequest(
                    access_token=plaidItem.accessToken,
                    options={"account_ids": balance_ids_by_item_id[plaidItem.itemId]}
                )
            else:
                exchange_request = AccountsGetRequest(
                    access_token=plaidItem.accessToken
                )
        
            exchange_response = plaid_client.accounts_get(exchange_request)
            serializer = AccountsGetResponseSerializer(
                data=exchange_response.to_dict()
            )
            serializer.is_valid(raise_exception=True)

            accounts_get_by_item[plaidItem.itemId] = serializer.validated_data
        return accounts_get_by_item
    except ApiException as e:
        error = json.loads(e.body)
        return f"accounts get error: {error.get("error_code")}"
    except Exception as e:
        return f"accounts get error: {str(e)}"

@shared_task(name="plaid_balance_get")
def plaid_balance_get(uid, item_id=None, account_ids_by_item_id={}):
    import pdb
    breakpoint()
    
    try:
        plaidItems = PlaidItem.objects.filter(user__id=uid)
        balance_get_by_item = {}
        for plaidItem in plaidItems:
            if item_id and item_id != plaidItem.itemId:
                continue
            if plaidItem.itemId in account_ids_by_item_id:
                exchange_request = AccountsBalanceGetRequest(
                    access_token=plaidItem.accessToken,
                    options={"account_ids": account_ids_by_item_id[plaidItem.itemId]}
                )
            else:
                exchange_request = AccountsBalanceGetRequest(
                    access_token=plaidItem.accessToken
                )
        
            exchange_response = plaid_client.accounts_balance_get(exchange_request)
            serializer = BalanceGetResponseSerializer(
                data=exchange_response.to_dict()
            )
            serializer.is_valid(raise_exception=True)

            balance_get_by_item[plaidItem.itemId] = serializer.validated_data
        return balance_get_by_item
    except ApiException as e:
        error = json.loads(e.body)
        return f"balance get error: {error.get("error_code")}"
    except Exception as e:
        return f"balance get error: {str(e)}"
    
def process_plaid_balance(plaid_balance_responses, eq={}, gt={}, lt={}, lte={}, 
                          gte={}, metric_to_return_by=None):
    balances = []
    for item_id in plaid_balance_responses:
        balance_response = plaid_balance_responses[item_id]
        for account in balance_response['accounts']:
            balances.append(account)
    
    eq["verification_status"] = ["manually_verified", "automatically_verified"]
    eq["subtype"] = ["checking", "savings"]
    return filter_jsons(balances, eq=eq, gt=gt, lt=lt, lte=lte, gte=gte, 
                        metric_to_return_by=metric_to_return_by)

def plaid_balance_get_process(uid, item_id=None, account_ids_by_item_id={}, eq={}, 
                              gt={}, lt={}, lte={}, gte={}, metric_to_return_by=None,
                              use_balance=True):
    if use_balance:
        balance_get = plaid_balance_get(uid, item_id=None, account_ids_by_item_id={})
    else:
        balance_get = plaid_accounts_get(uid, item_id=None, account_ids_by_item_id={})
    balance_processed = process_plaid_balance(balance_get, eq={}, gt={}, lt={}, lte={}, 
                                              gte={}, metric_to_return_by=None)
    return balance_processed


# deposit the cashback

def select_cashback(uid):
    cashbacks = PlaidCashbackTransaction.objects.filter(user__id=uid, deposited=False)
    if cashbacks.size() == 0:
        raise Exception("no cashback to deposit for {uid}")
    return cashbacks.first()

def check_repeat_deposit(uid, old_deposits, cashback, repeat_day_range):
    # check for duplicate deposit
    lower_limit = timezone.now() - timedelta(days=repeat_day_range)
    old_deposits = RobinhoodCashbackDeposit.objects.filter(
        user__id=uid,
        updated_at__gt=lower_limit
    )
    potential_db_repeats = []
    for deposit in old_deposits:
        if deposit.amount == cashback.amount or \
           deposit.transaction.id == cashback.transaction_id:
            potential_db_repeats.append(deposit)

    # could add checking the transfer's account id?
    potential_rh_repeats = rh_get_bank_transfers(
        uid, 
        eq={"amount":[cashback.amount]}, 
        gt={"updated_at":[timezone.now() - timedelta(days=5)]}
    )
    return potential_db_repeats, potential_rh_repeats

def rh_deposit(uid, cashback, repeat_day_range=5):

    # get previous deposit to help decide which account to use
    old_deposits = RobinhoodCashbackDeposit.objects.filter(
        user__id=uid, 
        deposited=True
    ) .order_by("-updated_at")
    if old_deposits.exists():
        latest_deposit = old_deposits.first()
    else:
        latest_deposit = None

    # check for duplicate deposits
    potential_db_repeats, potential_rh_repeats = check_repeat_deposit(
        uid,
        cashback, 
        repeat_day_range
    )
    if potential_db_repeats or potential_rh_repeats:
        raise Exception("potential db repeats {potential_db_repeats} " +  
                        "potential rh repeats {potential_rh_repeats}")
    
    # find accounts matching in Plaid and RH
    plaid_accounts = plaid_balance_get_process(uid)
    rh_accounts = rh_get_linked_bank_accounts(uid)
    rh_account, plaid_account = select_deposit_account(
        uid, 
        cashback.amount, 
        latest_deposit and latest_deposit.accountId, 
        plaid_accounts, 
        rh_accounts
    )

    # make the deposit
    deposits = rh_deposit_funds_to_robinhood_account(
        uid, 
        rh_account["ach_relationship"], 
        cashback.amount
    )
    if len(deposits) == 0:
        raise Exception(f"no deposit with {rh_account["ach_relationship"]}")
    elif len(deposits) > 1:
        raise Exception(f"multiple deposits matching {rh_account["ach_relationship"]}")
    deposit = deposits[0]

    robinhoodCashbackDeposit = RobinhoodCashbackDeposit(
        deposit_id = deposit["id"],
        user = User.objects.get(id=uid),
        transaction = cashback,
        rh_account_id = rh_account["id"],
        rh_account_ach = deposit["ach_relationship"],
        plaid_account_id = plaid_account["account_id"],
        mask = plaid_account["mask"],
        state = deposit["state"],
        cancel = deposit["cancel"],
        amount = deposit["amount"],
        created_at = deposit["created_at"],
        updated_at = deposit["updated_at"],
        expected_landing_datetime = deposit["expected_landing_datetime"]
    )
    robinhoodCashbackDeposit.save()
    cashback.deposited = True
    cashback.save()

def rh_save_deposit_from_transfer(uid, cashback, deposit_id):
    cashback.deposited=True
    cashback.save()

    transfers = rh_get_bank_transfers(
        uid, 
        eq={"amount": [cashback.amount], "id": [deposit_id]}
    )
    if len(transfers) == 0:
        raise Exception(f"no deposit with id {deposit_id} found")
    elif len(transfers) > 1:
        raise Exception(f"multiple deposits matching: {transfers}")
    transfer_result = transfers[0]

    rh_accounts = rh_get_linked_bank_accounts(
        uid, 
        eq={"url":[transfer_result["ach_relationship"]]}
    )
    if len(rh_accounts) != 1:
        raise Exception(f"could not find rh account associated with " + 
                        f"{transfer_result["ach_relationship"]}")
    rh_account = rh_accounts[0]

    plaid_accounts = plaid_balance_get_process(
        uid, 
        eq={"mask": [transfer_result["ach_relationship"]]},
        use_balance=False
    )
    if len(plaid_accounts) != 1:
        raise Exception(f"could not find rh account associated with " + 
                        f"{transfer_result["ach_relationship"]}")
    plaid_account = plaid_accounts[0]
    if plaid_account["mask"] != rh_account["bank_routing_number"]:
        raise Exception("matching rh and plaid accounts not found")

    robinhoodCashbackDeposit = RobinhoodCashbackDeposit(
        deposit_id = transfer_result["id"],
        user = User.objects.get(id=uid),
        transaction = cashback,
        rh_account_id = rh_account["id"],
        rh_account_ach = transfer_result["ach_relationship"],
        plaid_account_id = plaid_account["account_id"], 
        mask = plaid_account["mask"],
        state = transfer_result["state"],
        cancel = transfer_result["cancel"],
        amount = transfer_result["amount"],
        created_at = transfer_result["created_at"],
        updated_at = transfer_result["updated_at"],
        expected_landing_datetime = transfer_result["expected_landing_datetime"]
    )
    robinhoodCashbackDeposit.save()
    cashback.deposited = True
    cashback.save()

def select_deposit_account(uid, cashback, latest_deposit_account_id, plaid_accounts,
                            rh_accounts):
    matching_accounts = {}
    for plaid_account in plaid_accounts:
        for rh_account in rh_accounts:
            if plaid_account["balances"]["iso_currency_code"] != "USD":
                raise Exception("not USD")
            # maybe match the subtype too! but idk rh types. 
            # but if we need subtype to form a pkey with mask, 
            # we'll notice a duplicate :)
            if plaid_account["mask"] == rh_account["bank_routing_number"] and \
                plaid_account["balances"]["available"] >= cashback.amount:
                match = {
                    "rh_account": rh_account,
                    "plaid_account": plaid_account,
                    "is_previous_choice": plaid_account["account_id"] == latest_deposit_account_id,
                    "is_cashback_source": plaid_account["account_id"] == cashback.account_id
                }
                if plaid_account["mask"] in matching_accounts:
                    match2 = matching_accounts[plaid_account["mask"]]
                    if rh_account["ach_relationship"] == match2["rh_account"]["ach_relationship"] \
                        or plaid_account["account_id"] == match2["plaid_account"]["account_id"]:
                        raise Exception("mask, and plaid account_id or rh ach_relationship duplicate")
                    raise Exception("mask duplicate, but not plaid account_id or rh ach_relationship")
                else:
                    matching_accounts[plaid_account["mask"]] = match

    if matching_accounts == {}:
        raise Exception("no matching accounts")
    matching_accounts_list = list(matching_accounts.values())
    deposit_account = matching_accounts_list.sort(key=comparator)[0]
    return deposit_account["rh_account"], deposit_account["plaid_account"]

def comparator(account1, account2):
    plaid1 = account1["plaid_account"]
    plaid2 = account2["plaid_account"]
    rh1 = account1["rh_account"]
    rh2 = account2["rh_account"]

    if plaid1["subtype"] == "checking" and plaid2["subtype"] == "savings":
        return -1
    elif plaid1["subtype"] == "savings" and plaid2["subtype"] == "checking":
        return 1
    
    if account1["is_previous_choice"] and not account2["is_previous_choice"]:
        return -1
    elif not account1["is_previous_choice"] and account2["is_previous_choice"]:
        return 1
    
    if account1["is_cashback_source"] and not account2["is_cashback_source"]:
        return -1
    elif not account1["is_cashback_source"] and account2["is_cashback_source"]:
        return 1
    
    if plaid1["balances"]["available"] > plaid2["balances"]["available"]:
        return -1
    elif plaid1["balances"]["available"] < plaid2["balances"]["available"]:
        return 1 
    
    return 0
    
def select_match(uid, matching_dict, amount, cashback):
    ranking = []
    for mask in matching_dict:
        match = matching_dict[mask]
        if match["type"] == "checking":
            ranking.append("checking")
        

    # checking then savings
    # use the one cashback was deposited into
    # then the one we used last time


def update_deposit(uid, deposit_id):
    deposits = rh_get_bank_transfers(
        uid, 
        eq={"id": [deposit_id]}
    )
    if len(deposits) == 0:
        raise Exception(f"no deposit with id {deposit_id} found")
    elif len(deposits) > 1:
        raise Exception(f"multiple deposits matching: {deposit_id}")
    deposit = deposits[0]

    try:
        robinhoodCashbackDeposit = RobinhoodCashbackDeposit.objects.get(deposit_id=deposit_id)
    except Exception as e:
        raise Exception(f"no object robinhoodCashbackDeposit found " +
                        "for user {uid}, deposit_id {deposit_id}")
    
    robinhoodCashbackDeposit.state = deposit["state"]
    robinhoodCashbackDeposit.cancel = deposit["cancel"] 
    robinhoodCashbackDeposit.updated_at = deposit["updated_at"]
    robinhoodCashbackDeposit.expected_landing_datetime = deposit["expected_landing_datetime"]
    robinhoodCashbackDeposit.save()

    # if robinhoodCashbackDeposit.state == "completed":
    #     cashback_transaction = robinhoodCashbackDeposit.transaction
    #     cashback_transaction.deposited = True
    #     cashback_transaction.save()
    #     return "updated and deposit completed"
    return deposit["state"] # completed?

