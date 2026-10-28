"""记账 CSV 解析。"""


def _to_cents(raw):
    return int(round(float(raw.strip()) * 100))


def load_entries(text):
    """解析 CSV 文本（表头 date,account,description,amount），返回 dict 列表。"""
    entries = []
    for line in text.splitlines()[1:]:
        if not line.strip():
            continue
        date, account, description, amount = line.split(',')
        entries.append({
            'date': date.strip(),
            'account': account.strip(),
            'description': description.strip(),
            'amount_cents': _to_cents(amount),
        })
    return entries
