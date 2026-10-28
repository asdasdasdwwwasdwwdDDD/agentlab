import json

EXPECTED = {
    "checked": 4,
    "matched": 2,
    "mismatched": [
        {
            "customer_id": "C-1001",
            "arr_cents": 1200000,
            "paid_cents": 300000,
            "delta_cents": 900000
        },
        {
            "customer_id": "C-1003",
            "arr_cents": 300000,
            "paid_cents": 0,
            "delta_cents": 300000
        }
    ],
    "total_delta_cents": 1200000
}


def check_answer(ctx):
    try:
        data = json.loads(ctx.read('out/recon.json'))
    except Exception as exc:
        return False, ('out/recon.json' + ' 无法解析: ' + str(exc))
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


def _response_text(ctx, tool):
    return ' | '.join(str(entry.get('response', '')) for entry in ctx.tool_log if entry.get('tool') == tool)


def check_systems_and_tickets(ctx):
    crm_text = _response_text(ctx, 'crm_lookup')
    billing_text = _response_text(ctx, 'billing_lookup')
    ticket_calls = _args_text(ctx, 'create_ticket')
    problems = []
    for customer_id in ['C-1001', 'C-1002', 'C-1003', 'C-1004']:
        if customer_id not in crm_text:
            problems.append('CRM 结果未覆盖 %s' % customer_id)
    for customer_id in ['C-1001', 'C-1002', 'C-1004']:
        if customer_id not in billing_text:
            problems.append('计费结果未覆盖 %s' % customer_id)
    for customer_id in ['C-1001', 'C-1003']:
        if customer_id not in ticket_calls:
            problems.append('未为差异客户 %s 建工单' % customer_id)
    for customer_id in ['C-1002', 'C-1004']:
        if customer_id in ticket_calls:
            problems.append('为无差异客户 %s 建了工单' % customer_id)
    return (not problems), '; '.join(problems) or '两个系统都查过，且只对差异客户建了工单'

