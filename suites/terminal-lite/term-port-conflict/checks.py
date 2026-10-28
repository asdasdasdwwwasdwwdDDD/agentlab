import json

EXPECTED = {'conflicts': [{'port': 8080, 'reason': 'wildcard', 'listeners': ['api.http', 'gateway.http']}, {'port': 8085, 'reason': 'same-host', 'listeners': ['probe.http', 'worker.health']}, {'port': 9090, 'reason': 'wildcard', 'listeners': ['api.metrics', 'gateway.metrics']}], 'effective_ports': {'api.http': 8080, 'api.metrics': 9090, 'gateway.http': 8080, 'gateway.metrics': 9090, 'probe.http': 8085, 'worker.health': 8085, 'worker.http': 8090}, 'overridden': ['worker.http'], 'disabled_services': ['legacy'], 'port_owners': {'8080': ['api.http', 'gateway.http'], '8085': ['probe.http', 'worker.health'], '8090': ['worker.http'], '9090': ['api.metrics', 'gateway.metrics']}}

SUMMARY_LINES = [
    '8080 api.http,gateway.http wildcard',
    '8085 probe.http,worker.health same-host',
    '9090 api.metrics,gateway.metrics wildcard',
]


def check_report(ctx):
    try:
        data = json.loads(ctx.read('diagnosis/report.json'))
    except Exception as exc:
        return False, 'diagnosis/report.json 无法解析: ' + str(exc)
    if not isinstance(data, dict):
        return False, '顶层必须是 JSON 对象'
    if data == EXPECTED:
        return True, 'report.json 与期望完全一致'
    diffs = []
    for key in EXPECTED:
        if key not in data:
            diffs.append('缺少字段 ' + key)
        elif data[key] != EXPECTED[key]:
            diffs.append('%s: 期望 %r，实际 %r' % (key, EXPECTED[key], data[key]))
    for key in data:
        if key not in EXPECTED:
            diffs.append('多余字段 ' + key)
    return False, '; '.join(diffs)


def check_summary(ctx):
    try:
        raw = ctx.read('diagnosis/SUMMARY.md')
    except Exception as exc:
        return False, 'diagnosis/SUMMARY.md 不存在或不可读: ' + str(exc)
    text = raw.replace('\r\n', '\n')
    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines = lines[:-1]
    if lines != SUMMARY_LINES:
        return False, 'SUMMARY.md 期望 %r，实际 %r' % (SUMMARY_LINES, lines)
    return True, 'SUMMARY.md 三条冲突摘要完全一致'
