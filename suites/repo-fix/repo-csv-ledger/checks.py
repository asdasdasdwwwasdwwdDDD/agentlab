import importlib
import json
import sys


def _import(ctx, name):
    root = str(ctx.workspace)
    for module_name in list(sys.modules):
        if module_name == name or module_name.startswith(name + '.'):
            del sys.modules[module_name]
    if root not in sys.path:
        sys.path.insert(0, root)
    module = importlib.import_module(name)
    return module


def _load_api(ctx, package):
    _import(ctx, package)
    return importlib.import_module(package)


def check_parse_quoted_comma(ctx):
    try:
        api = _load_api(ctx, 'ledger')
    except Exception as exc:
        return False, '无法导入 ledger: %r' % (exc,)
    text = 'date,account,description,amount\n2024-01-03,office,"Paper, A4",12.50\n2024-01-04,travel,Taxi,-30.00\n'
    try:
        entries = api.load_entries(text)
    except Exception as exc:
        return False, '引号内逗号解析失败: %r' % (exc,)
    problems = []
    if len(entries) != 2:
        problems.append('解析出 %d 条，期望 2 条' % len(entries))
    else:
        if entries[0].get('description') != 'Paper, A4':
            problems.append('description = %r，期望 %r' % (entries[0].get('description'), 'Paper, A4'))
        if entries[0].get('amount_cents') != 1250:
            problems.append('amount_cents = %r，期望 1250' % (entries[0].get('amount_cents'),))
    return (not problems), '; '.join(problems) or '引号内逗号解析正确'


def check_sign_and_rounding(ctx):
    try:
        api = _load_api(ctx, 'ledger')
    except Exception as exc:
        return False, '无法导入 ledger: %r' % (exc,)
    text = ('date,account,description,amount\n'
            '2024-01-05,office,Staples,(12.34)\n'
            '2024-01-06,office,Clip,0.005\n'
            '2024-01-07,office,Paper,12.345\n'
            '2024-01-08,office,Refund,(0.05)\n')
    try:
        entries = api.load_entries(text)
    except Exception as exc:
        return False, '括号负数/取整解析失败: %r' % (exc,)
    expected = [-1234, 1, 1235, -5]
    problems = []
    if len(entries) != 4:
        problems.append('解析出 %d 条，期望 4 条' % len(entries))
    else:
        for index, want in enumerate(expected):
            got = entries[index].get('amount_cents')
            if got != want:
                problems.append('第 %d 条 amount_cents = %r，期望 %r' % (index + 1, got, want))
            elif type(got) is not int:
                problems.append('第 %d 条 amount_cents 是 %s，应为 int' % (index + 1, type(got).__name__))
    return (not problems), '; '.join(problems) or '括号负数与 half-up 取整正确'


def check_export_order_and_ints(ctx):
    try:
        api = _load_api(ctx, 'ledger')
    except Exception as exc:
        return False, '无法导入 ledger: %r' % (exc,)
    text = ('date,account,description,amount\n'
            '2024-01-03,travel,Taxi,-30.00\n'
            '2024-01-03,office,"Paper, A4",12.50\n'
            '2024-01-05,office,Pen set,8.25\n'
            '2024-01-06,cloud,Storage,5.005\n')
    try:
        entries = api.load_entries(text)
        summary = api.to_dict(entries)
    except Exception as exc:
        return False, 'to_dict 失败: %r' % (exc,)
    problems = []
    if summary.get('entry_count') != 4:
        problems.append('entry_count = %r，期望 4' % (summary.get('entry_count'),))
    accounts = summary.get('accounts')
    if not isinstance(accounts, list):
        return False, 'accounts 必须是数组，实际 %r' % (accounts,)
    names = [item.get('account') for item in accounts]
    if names != ['cloud', 'office', 'travel']:
        problems.append('accounts 顺序 = %r，期望按字典序升序' % (names,))
    expected_totals = {'cloud': 501, 'office': 2075, 'travel': -3000}
    for item in accounts:
        name = item.get('account')
        value = item.get('total_cents')
        if name in expected_totals and value != expected_totals[name]:
            problems.append('%s 的 total_cents = %r，期望 %r' % (name, value, expected_totals[name]))
        if type(value) is not int:
            problems.append('%s 的 total_cents 是 %s，应为 int' % (name, type(value).__name__))
    return (not problems), '; '.join(problems) or '导出顺序与整数分合计正确'
