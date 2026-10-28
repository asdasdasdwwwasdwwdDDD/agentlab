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


def check_rounding_half_up(ctx):
    try:
        _import(ctx, 'invoicelib')
        money = importlib.import_module('invoicelib.money')
    except Exception as exc:
        return False, '无法导入 invoicelib.money: %r' % (exc,)
    problems = []
    for raw, expected in [('0.125', 13), ('2.345', 235), ('1.005', 101), ('19.99', 1999), ('0.001', 0)]:
        try:
            got = money.to_cents(raw)
        except Exception as exc:
            problems.append('to_cents(%r) 抛异常 %r' % (raw, exc))
            continue
        if got != expected:
            problems.append('to_cents(%r) = %r，期望 %r' % (raw, got, expected))
        elif type(got) is not int:
            problems.append('to_cents(%r) 返回 %s，应为 int' % (raw, type(got).__name__))
    if money.format_cents(13) != '0.13':
        problems.append('format_cents(13) = %r' % (money.format_cents(13),))
    if money.format_cents(-205) != '-2.05':
        problems.append('format_cents(-205) = %r' % (money.format_cents(-205),))
    return (not problems), '; '.join(problems) or 'half-up 取整与格式化正确'


def check_all_items_and_tax(ctx):
    try:
        api = _load_api(ctx, 'invoicelib')
    except Exception as exc:
        return False, '无法导入 invoicelib: %r' % (exc,)
    items = [
        {'sku': 'A', 'unit_price': '10.00', 'quantity': 1, 'tax_rate': 0.1},
        {'sku': 'B', 'unit_price': '5.00', 'quantity': 2, 'tax_rate': 0.1},
        {'sku': 'C', 'unit_price': '0.125', 'quantity': 1, 'tax_rate': 0.05},
    ]
    try:
        data = api.build_invoice('INV-2002', items).as_dict()
    except Exception as exc:
        return False, 'build_invoice/as_dict 抛异常: %r' % (exc,)
    problems = []
    for key, expected in [('subtotal_cents', 2013), ('tax_cents', 201), ('total_cents', 2214)]:
        if data.get(key) != expected:
            problems.append('%s = %r，期望 %r' % (key, data.get(key), expected))
    return (not problems), '; '.join(problems) or '全部条目都参与合计，逐条计税正确'


def check_serialized_cents_are_ints(ctx):
    try:
        api = _load_api(ctx, 'invoicelib')
        data = api.build_invoice('INV-3003', [
            {'sku': 'A', 'unit_price': '10.00', 'quantity': 1, 'tax_rate': 0.1},
        ]).as_dict()
    except Exception as exc:
        return False, '无法导出 as_dict(): %r' % (exc,)
    problems = []
    for key in ('subtotal_cents', 'tax_cents', 'total_cents'):
        if type(data.get(key)) is not int:
            problems.append('%s 是 %s，应为 int' % (key, type(data.get(key)).__name__))
    if (data.get('subtotal_cents'), data.get('tax_cents'), data.get('total_cents')) != (1000, 100, 1100):
        problems.append('金额数值不正确: %r' % (data,))
    if data.get('invoice_id') != 'INV-3003':
        problems.append('invoice_id 被改动')
    try:
        json.dumps(data)
    except Exception as exc:
        problems.append('as_dict() 不能 JSON 序列化: %r' % (exc,))
    return (not problems), '; '.join(problems) or '导出金额均为整数分且可 JSON 序列化'
