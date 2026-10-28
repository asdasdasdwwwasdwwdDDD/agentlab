"""按账户汇总。"""


def totals_by_account(entries):
    totals = {}
    for entry in entries:
        account = entry['account']
        totals[account] = totals.get(account, 0) + entry['amount_cents']
    return totals
