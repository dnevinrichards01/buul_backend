from celery import shared_task, chain

import robin_stocks.robinhood as r

from django.utils import timezone
from django.db.models import Q
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.db.models import Sum
from django.db import transaction

from api.apis.plaid import plaid_client
from ..jsonUtils import filter_jsons

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import json
import functools

from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
from plaid.model.accounts_balance_get_request_options import AccountsBalanceGetRequestOptions
from plaid.exceptions import ApiException

from ..models import PlaidItem, User, PlaidCashbackTransaction, \
    RobinhoodDeposit, Investment, Deposit, UserBrokerageInfo
from ..serializers.rh import GetLinkedBankAccountsResponseSerializer, \
    DepositSerializer, RobinhoodAccountListSerializer
from ..serializers.plaid.balance import \
    BalanceGetResponseSerializer, AccountsGetResponseSerializer

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
                    options={
                        "account_ids": account_ids_by_item_id[plaidItem.itemId],
                        "min_last_updated_datetime": timezone.now().replace(hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%dT%H:%M:%SZ')
                    }
                )
            else:
                exchange_request = AccountsBalanceGetRequest(
                    access_token=plaidItem.accessToken,
                    options=AccountsBalanceGetRequestOptions(
                        min_last_updated_datetime=timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
                    )
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
    
    # no verification status - maybe thats for the accounts and not balance endpoint?
    eq["verification_status"] = ["manually_verified", "automatically_verified"]
    # eq["subtype"] = ["checking", "savings"]
    return filter_jsons(balances, eq=eq, gt=gt, lt=lt, lte=lte, gte=gte, 
                        metric_to_return_by=metric_to_return_by)

def plaid_balance_get_process(uid, item_id=None, account_ids_by_item_id={}, eq={}, 
                              gt={}, lt={}, lte={}, gte={}, metric_to_return_by=None,
                              use_balance=True):
    if use_balance:
        balance_get = plaid_balance_get(uid, item_id=None, account_ids_by_item_id={})
    else:
        balance_get = plaid_accounts_get(uid, item_id=None, account_ids_by_item_id={})
    balance_processed = process_plaid_balance(balance_get, eq=eq, gt=gt, lt=lt, lte=lte, 
                                              gte=gte, metric_to_return_by=None)
    return balance_processed


# check which account to withdraw from

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

def comparator(account1, account2):
    plaid1 = account1["plaid_account"]
    plaid2 = account2["plaid_account"]
    rh1 = account1["rh_account"]
    rh2 = account2["rh_account"]

    account1_matches = plaid1["mask"] == rh1["bank_account_number"]
    account2_matches = plaid2["mask"] == rh2["bank_account_number"]
    if account1_matches:
        return -1
    elif account2_matches:
        return 1

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

@shared_task(name="match_brokerage_plaid_accounts")
def match_brokerage_plaid_accounts(uid):
    plaid_accounts = plaid_balance_get_process(uid, use_balance=False)
    rh_accounts = rh_get_linked_bank_accounts(uid)
    for p in plaid_accounts:
        for r in rh_accounts:
            if p["mask"] == r["bank_account_number"]:
                return True
    return False


def select_deposit_account(uid, amount, cashback_account_ids, latest_deposit_account_id, plaid_accounts,
                            rh_accounts, brokerage_plaid_match_required=True):
    # find candidate accounts
    candidate_accounts = {}
    for plaid_account in plaid_accounts:
        for rh_account in rh_accounts:
            # only support USD for now
            if plaid_account["balances"]["iso_currency_code"] != "USD":
                raise Exception("not USD")
            # if we find an account both in plaid and in rh, add to candidate list
            if plaid_account["balances"]["available"] >= amount:
                if not brokerage_plaid_match_required or plaid_account["mask"] == rh_account["bank_account_number"]:
                    match = {
                        "rh_account": rh_account,
                        "plaid_account": plaid_account,
                        "is_previous_choice": plaid_account["account_id"] == latest_deposit_account_id,
                        "is_cashback_source": plaid_account["account_id"] in cashback_account_ids
                    }
                    candidate_accounts[plaid_account["mask"]] = match
    if len(candidate_accounts) == 0:
        raise Exception("no matching accounts")
    
    # sort and select account
    matching_accounts_list = list(candidate_accounts.values())
    matching_accounts_list.sort(key=functools.cmp_to_key(comparator))
    deposit_account = matching_accounts_list[0]
    return deposit_account["rh_account"], deposit_account["plaid_account"]

#cashbacks = PlaidCashbackTransaction.objects.filter(user__id=uid, deposit=None)

# check for repeats or overdrafting

@shared_task(name="rh_get_bank_transfers")
def rh_get_bank_transfers(uid, eq={}, gt={}, lt={}, lte={}, gte={}, 
                          metric_to_return_by=None):
    import pdb
    breakpoint()
    # uid = kwargs.pop('uid')

    try:
        session, userRobinhtoodInfo = r.rh_create_session(uid)
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

def check_repeat_deposit(uid, amount, repeat_day_range):
    # check for duplicate deposit
    lower_limit = timezone.now() - timedelta(days=repeat_day_range)
    old_deposits = Deposit.objects.filter(
        Q(user__id=uid) & \
        Q(created_at=lower_limit) & \
        Q(amount=amount)
    )
    potential_db_repeats = [deposit for deposit in old_deposits]

    # could add checking the transfer's account id?
    potential_rh_repeats = rh_get_bank_transfers(
        uid, 
        lt={"amount":[amount+0.05]}, 
        gt={
            "created_at":[timezone.now() - timedelta(days=repeat_day_range)],
            "amount":[amount-0.05]
        }
    )
    return potential_db_repeats, potential_rh_repeats


# deposit

@shared_task(name="rh_deposit_funds_to_robinhood_account")
def rh_deposit_funds_to_robinhood_account(uid, ach_relationship, amount, force=False, limit=50):
    import pdb
    breakpoint()

    # uid = kwargs.pop('uid')

    try:
        session, userRobinhoodInfo = r.rh_create_session(uid)
    except Exception as e:
        raise Exception(f"could not find userRobinhoodInfo object for that {uid}")
    
    if not force:
        cumulative_amount_query = Deposit.objects.filter(
            user__id=uid,
            created_at__gt=timezone.now()-relativedelta(months=1)
        ).aggregate(cumulative_amount=Sum('amount'))
        cumulative_amount = cumulative_amount_query.get('cumulative_amount') or 0
        if cumulative_amount + amount > limit:
            raise Exception(
                "Cumulative amount deposited would be > 50. " + \
                "Set force=True to override this message."
            )

    try:
        result = r.deposit_funds_to_robinhood_account(
            session, ach_relationship, round(amount, 4)
        )
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

def rh_deposit(uid, transactions, repeat_day_range=5, force=False, 
               limit=50):
    import pdb; breakpoint()
    # get previous deposit to help decide which account to use
    old_deposits = RobinhoodDeposit.objects.filter(user__id=uid)\
        .order_by("-updated_at")
    if old_deposits.exists():
        latest_deposit = old_deposits.first()
    else:
        latest_deposit = None
    # info on cashback transactions to deposit to also help choose the account
    cashback_amount = -1 * sum([x.amount for x in transactions])
    cashback_account_ids = [x.account_id for x in transactions]

    # check for duplicate deposits
    potential_db_repeats, potential_rh_repeats = check_repeat_deposit(
        uid, cashback_amount, repeat_day_range
    )
    if not force and (potential_db_repeats or potential_rh_repeats):
        raise Exception("potential db repeats {potential_db_repeats} " +  
                        "potential rh repeats {potential_rh_repeats}")
    
    # find accounts matching in Plaid and RH
    plaid_accounts = plaid_balance_get_process(uid)
    rh_accounts = rh_get_linked_bank_accounts(uid)
    import pdb; breakpoint()
    overdraft_protection = UserBrokerageInfo.objects.get(user_id=uid).overdraft_protection
    rh_account, plaid_account = select_deposit_account(
        uid,
        cashback_amount,
        cashback_account_ids,
        latest_deposit,
        plaid_accounts,
        rh_accounts,
        brokerage_plaid_match_required = overdraft_protection
    )

    # make the deposit
    deposit = rh_deposit_funds_to_robinhood_account(
        uid, rh_account["url"], cashback_amount, 
        force=force, limit=limit
    )
    if "error" in deposit: # error message 
        return deposit

    # save deposit, update transactions
    with transaction.atomic():
        robinhoodCashbackDeposit = RobinhoodDeposit(
            deposit_id = deposit["id"],
            user = User.objects.get(id=uid),
            rh_account_id = rh_account["id"],
            rh_account_ach = deposit["ach_relationship"],
            plaid_account_id = plaid_account["account_id"],
            mask = plaid_account["mask"],
            state = deposit["state"],
            amount = deposit["amount"],
            early_access_amount = deposit["early_access_amount"],
            created_at = deposit["created_at"],
            updated_at = deposit["updated_at"],
            expected_landing_datetime = deposit["expected_landing_datetime"],
            cancel = deposit["cancel"],
        )
        robinhoodCashbackDeposit.save()
        deposit = Deposit.objects.get(rh=robinhoodCashbackDeposit)
        for _transaction in transactions:
            _transaction.deposit = deposit
        PlaidCashbackTransaction.objects.bulk_update(transactions, ['deposit'])

def rh_update_deposit(uid, deposit_id, transactions=None, get_bank_info=True):

    import pdb; breakpoint()

    transfers = rh_get_bank_transfers(
        uid, 
        eq={"id": [deposit_id]}
    )
    if "error" in transfers: # error message
        return transfers
    if len(transfers) == 0:
        raise Exception(f"no deposit with id {deposit_id} found")
    elif len(transfers) > 1:
        raise Exception(f"multiple deposits matching: {transfers}")
    transfer_result = transfers[0]

    if get_bank_info:
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
            eq={"mask": [rh_account["bank_account_number"]]},
            use_balance=False
        )
        if len(plaid_accounts) != 1:
            raise Exception(f"could not find rh account associated with " + 
                            f"{rh_account["bank_account_number"]}")
        plaid_account = plaid_accounts[0]

    try:
        robinhoodCashbackDeposit = RobinhoodDeposit.objects.get(
            deposit_id=transfer_result["id"], user__id=uid
        )
        robinhoodCashbackDeposit.state = transfer_result["state"]
        robinhoodCashbackDeposit.amount = transfer_result["amount"]
        robinhoodCashbackDeposit.early_access_amount = transfer_result["early_access_amount"]
        robinhoodCashbackDeposit.created_at = transfer_result["created_at"]
        robinhoodCashbackDeposit.updated_at = transfer_result["updated_at"]
        robinhoodCashbackDeposit.expected_landing_datetime = transfer_result["expected_landing_datetime"]
        robinhoodCashbackDeposit.cancel = transfer_result["cancel"]
    except Exception as e:
        if get_bank_info:
            robinhoodCashbackDeposit = RobinhoodDeposit(
                deposit_id = transfer_result["id"],
                user = User.objects.get(id=uid),
                rh_account_id = rh_account["id"],
                rh_account_ach = transfer_result["ach_relationship"],
                plaid_account_id = plaid_account["account_id"], 
                mask = plaid_account["mask"],
                state = transfer_result["state"], 
                amount = transfer_result["amount"],
                early_access_amount = transfer_result["early_access_amount"],
                created_at = transfer_result["created_at"],
                updated_at = transfer_result["updated_at"],
                expected_landing_datetime = transfer_result["expected_landing_datetime"],
                cancel = transfer_result["cancel"]
            )
        else:
            raise Exception("deposit not found in Buul db, " + \
                            "enable get_bank_info to create deposit record")
    robinhoodCashbackDeposit.save()
    deposit = Deposit.objects.get(rh=robinhoodCashbackDeposit)
    if transactions:
        for transaction in transactions:
            transaction.deposit = deposit
        PlaidCashbackTransaction.objects.bulk_update(transactions, ['deposit'])
    return transfer_result["state"]


# untested
def group_cashback_transactions(uid, grouped=True, group_size=50):
    to_deposit = PlaidCashbackTransaction.objects.filter(
        user__id=uid, deposit=None
    ).order_by('date')
    if grouped:
        curr_deposit_amount = 0
        curr_deposit_transactions = []
        grouped_transactions = []
        for transaction in to_deposit:
            if curr_deposit_amount < group_size:
                curr_deposit_amount += abs(transaction.amount)
                curr_deposit_transactions.append(transaction)
            else:
                curr_deposit_amount = 0
                curr_deposit_transactions.append(curr_deposit_transactions)
        if len(curr_deposit_transactions) > 0:
            grouped_transactions.append(curr_deposit_transactions)
        return grouped_transactions
    else:
        return [transaction for transaction in to_deposit]



@receiver(post_save, sender=RobinhoodDeposit)
def rhdeposit_to_deposit(sender, instance, **kwargs):
    try:
        deposit = Deposit(
            user = instance.user,
            rh = instance,
            mask = instance.mask,
            state = instance.state,
            amount = instance.amount,
            available_funds = instance.early_access_amount,
            created_at = instance.created_at
        )
        deposit.save()
    except:
        deposit = Deposit.objects.get(user = instance.user, rh = instance)
        deposit.state = instance.state
        deposit.save()
