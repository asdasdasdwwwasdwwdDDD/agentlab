import json

EXPECTED = {
    "tickets": [
        {
            "message_id": "m-01",
            "customer_id": "C-1001",
            "priority": "P1",
            "queue": "incident",
            "sla_hours": 1
        },
        {
            "message_id": "m-02",
            "customer_id": "C-1002",
            "priority": "P1",
            "queue": "incident",
            "sla_hours": 1
        },
        {
            "message_id": "m-03",
            "customer_id": "C-1003",
            "priority": "P2",
            "queue": "support",
            "sla_hours": 4
        }
    ]
}


def check_answer(ctx):
    try:
        data = json.loads(ctx.read('out/triage.json'))
    except Exception as exc:
        return False, ('out/triage.json' + ' 无法解析: ' + str(exc))
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


def check_tool_usage_complete(ctx):
    customer_calls = _args_text(ctx, 'lookup_customer')
    ticket_calls = _args_text(ctx, 'create_ticket')
    problems = []
    for customer_id in ['C-1001', 'C-1002', 'C-1003']:
        if customer_id not in customer_calls:
            problems.append('未查询客户 %s' % customer_id)
    for message_id in ['m-01', 'm-02', 'm-03']:
        if message_id not in ticket_calls:
            problems.append('未为 %s 创建工单' % message_id)
    return (not problems), '; '.join(problems) or '3 个客户都查过、3 条消息都建了工单'

