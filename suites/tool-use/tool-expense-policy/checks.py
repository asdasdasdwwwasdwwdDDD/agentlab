import json

EXPECTED = {
    "reviews": [
        {
            "receipt_id": "x-01",
            "employee_id": "E-01",
            "cny_cents": 86400,
            "limit_cents": 80000,
            "decision": "reject",
            "reason": "over_limit"
        },
        {
            "receipt_id": "x-02",
            "employee_id": "E-01",
            "cny_cents": 13800,
            "limit_cents": 15000,
            "decision": "approve",
            "reason": "within_limit"
        },
        {
            "receipt_id": "x-03",
            "employee_id": "E-02",
            "cny_cents": 54600,
            "limit_cents": 50000,
            "decision": "reject",
            "reason": "over_limit"
        },
        {
            "receipt_id": "x-04",
            "employee_id": "E-03",
            "cny_cents": 24000,
            "limit_cents": 30000,
            "decision": "approve",
            "reason": "within_limit"
        },
        {
            "receipt_id": "x-05",
            "employee_id": "E-03",
            "cny_cents": 18000,
            "limit_cents": 15000,
            "decision": "reject",
            "reason": "over_limit"
        },
        {
            "receipt_id": "x-06",
            "employee_id": "E-02",
            "cny_cents": 2000,
            "limit_cents": 0,
            "decision": "reject",
            "reason": "unknown_category"
        }
    ],
    "approved": 2,
    "rejected": 4,
    "total_approved_cents": 37800
}


def check_answer(ctx):
    try:
        data = json.loads(ctx.read('out/expense_review.json'))
    except Exception as exc:
        return False, ('out/expense_review.json' + ' 无法解析: ' + str(exc))
    if data == EXPECTED:
        return True, '答案与期望完全一致'
    diffs = []
    if not isinstance(data, dict):
        return False, '顶层必须是 JSON 对象，实际 %r' % (type(data).__name__,)
    for key in EXPECTED:
        if key not in data:
            diffs.append('缺少字段 ' + key)
        elif data[key] != EXPECTED[key]:
            diffs.append('%s: 期望 %r，实际 %r' % (key, EXPECTED[key], data[key]))
    for key in data:
        if key not in EXPECTED:
            diffs.append('多余字段 ' + key)
    return False, '; '.join(diffs)


def _args_text(ctx, tool):
    return ' | '.join(json.dumps(entry.get('args', {}), ensure_ascii=False)
                      for entry in ctx.tool_log if entry.get('tool') == tool)


def check_lookups_and_tickets(ctx):
    employee_calls = _args_text(ctx, 'lookup_employee')
    fx_calls = _args_text(ctx, 'lookup_fx_rate')
    ticket_calls = _args_text(ctx, 'create_ticket')
    problems = []
    for employee_id in ['E-01', 'E-02', 'E-03']:
        if employee_id not in employee_calls:
            problems.append('未查询员工 ' + employee_id)
    for currency in ['USD', 'EUR', 'JPY']:
        if currency not in fx_calls:
            problems.append('未查询币种汇率 ' + currency)
    for receipt_id in ['x-01', 'x-03', 'x-05', 'x-06']:
        if receipt_id not in ticket_calls:
            problems.append('未为被拒收据 %s 建工单' % receipt_id)
    for receipt_id in ['x-02', 'x-04']:
        if receipt_id in ticket_calls:
            problems.append('为通过的收据 %s 建了工单' % receipt_id)
    return (not problems), '; '.join(problems) or '员工/汇率都查过，且只为被拒收据建单'

