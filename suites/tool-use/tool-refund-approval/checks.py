import json

EXPECTED = {
    "decisions": [
        {
            "request_id": "r-01",
            "order_id": "O-7001",
            "decision": "approve",
            "refund_cents": 12900,
            "reason": "within_window_vip"
        },
        {
            "request_id": "r-02",
            "order_id": "O-7002",
            "decision": "deny",
            "refund_cents": 0,
            "reason": "non_refundable_digital"
        },
        {
            "request_id": "r-03",
            "order_id": "O-7003",
            "decision": "deny",
            "refund_cents": 0,
            "reason": "out_of_window"
        },
        {
            "request_id": "r-04",
            "order_id": "O-7004",
            "decision": "deny",
            "refund_cents": 0,
            "reason": "already_refunded"
        }
    ]
}


def check_answer(ctx):
    try:
        data = json.loads(ctx.read('out/refunds.json'))
    except Exception as exc:
        return False, ('out/refunds.json' + ' 无法解析: ' + str(exc))
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


def check_inputs_and_side_effects(ctx):
    order_calls = _args_text(ctx, 'lookup_order')
    customer_calls = _args_text(ctx, 'lookup_customer')
    refund_calls = _args_text(ctx, 'apply_refund')
    problems = []
    for order_id in ['O-7001', 'O-7002', 'O-7003', 'O-7004']:
        if order_id not in order_calls:
            problems.append('未查询订单 ' + order_id)
    for customer_id in ['C-1001', 'C-1002', 'C-1003', 'C-1004']:
        if customer_id not in customer_calls:
            problems.append('未查询客户 ' + customer_id)
    if 'O-7001' not in refund_calls:
        problems.append('未对 O-7001 提交退款')
    for denied in ['O-7002', 'O-7003', 'O-7004']:
        if denied in refund_calls:
            problems.append('对已拒绝订单 %s 仍然提交了退款' % denied)
    return (not problems), '; '.join(problems) or '查证齐全且只对通过的订单提交退款'

