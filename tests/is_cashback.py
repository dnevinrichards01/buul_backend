import gc; gc.collect()
from api.models import *; from api.tasks import *;
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from django.forms.models import model_to_dict
import json


def user_xacts(uid, start, end):
    transactions = transactions_get(uid, start, end)
    if isinstance(transactions, str):
        raise Exception(transactions)
    xacts = []
    for item_id in transactions.keys():
        item = transactions[item_id]
        for page in item.keys():
            xacts.extend(item[page]['transactions'])
    xacts_final = []
    for x in xacts:
        if not PlaidCashbackTransaction.objects.filter(
            transaction_id = x['transaction_id'],
            name = x['name'],
            amount = x['amount'],
            date = x['date'],
            user__id = uid
        ).exists():
            xacts_final.append(x)
    return xacts_final, xacts


def get_all_transactions():
	xacts = []
	id_counter = {}
	for user in User.objects.all():
		try:
			xacts_filtered, _ = user_xacts(user.id, (timezone.now() - relativedelta(years=1)).strftime("%Y-%m-%d"), (timezone.now() + relativedelta(years=1)).strftime("%Y-%m-%d"))
		except Exception:
			continue
		for x in xacts_filtered:
			x['user'] = user.id
			if (x['transaction_id'], x['user'], x['name'], x['amount'], x['date']) in id_counter:
				id_counter[(x['transaction_id'], x['user'], x['name'], x['amount'], x['date'])] += 1
				continue
			else:
				id_counter[(x['transaction_id'], x['user'], x['name'], x['amount'], x['date'])] = 1
				xacts.append(x)
	known_cashback = [model_to_dict(x) for x in PlaidCashbackTransaction.objects.all()]
	xacts.extend(known_cashback)
	return xacts, id_counter



def test_is_cashback(xacts):
    tp_list, fp_list, tn_list, fn_list = [], [], [], []
    fp, tp, fn, tn = 0, 0, 0, 0
    total = len(xacts)
    pos = PlaidCashbackTransaction.objects.all().count()
    neg = total - pos
    id_counter = {}
    for x in xacts:
        lt = {"amount": [0]}
        is_cashback_name = {
            "func": lambda name, bool: is_cashback(name) == bool,
            "filter_set": {"name" : [True]}
        }
        cashback_db = PlaidCashbackTransaction.objects.filter(
            transaction_id=x['transaction_id'],
            user=x['user']
        ).exists()
        if (x['transaction_id'], x['user'], x['name'], x['amount'], x['date']) in id_counter:
            id_counter[(x['transaction_id'], x['user'],  x['name'], x['amount'], x['date'])] += 1
            continue
        else:
            id_counter[(x['transaction_id'], x['user'], x['name'], x['amount'], x['date'])] = 1
        cashback_guess = is_cashback(x['name'])
        if cashback_guess and cashback_db:
            tp += 1
            tp_list.append(x)
        elif not cashback_guess and not cashback_db:
            tn += 1
            tn_list.append(x)
        elif cashback_guess and not cashback_db:
            fp += 1
            fp_list.append(x)
        elif not cashback_guess and cashback_db:
            fn += 1
            fn_list.append(x)
    print(f"|{'TP':^10}|{'FP':^10}|{'TN':^10}|{'FN':^10}|{'acc':^10}|{'pos':^10}|{'neg':^10}|")
    print(f"|{'_'*10}|{'_'*10}|{'_'*10}|{'_'*10}|{'_'*10}|{'_'*10}|{'_'*10}|")
    print(f"|{tp:<10}|{fp:<10}|{tn:<10}|{fn:<10}|{(tp+tn)/total:<10.8f}|{pos:<10}|{neg:<10}|")
    print(f"|{'_'*10}|{'_'*10}|{'_'*10}|{'_'*10}|{'_'*10}|{'_'*10}|{'_'*10}|")
    return tp_list, tn_list, fp_list, fn_list, id_counter


xacts, fetch_counter = get_all_transactions()
tp_list, tn_list, fp_list, fn_list, test_counter = test_is_cashback(xacts)
[fetch_counter[key] for key in fetch_counter.keys() if fetch_counter[key] > 1]
[test_counter[key] for key in test_counter.keys() if test_counter[key] > 1]

[print(x['name']) for x in tp_list]

