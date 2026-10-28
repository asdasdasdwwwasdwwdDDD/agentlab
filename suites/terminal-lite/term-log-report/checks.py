import json

EXPECTED = {
    'total': 18,
    'by_level': {'INFO': 12, 'WARN': 4, 'ERROR': 2},
    'error_rate': 0.1111,
    'slowest_path': '/api/reports',
    'slow_count': 3,
}


def check_report_values(ctx):
    try:
        data = json.loads(ctx.read('report/log_summary.json'))
    except Exception as exc:
        return False, 'report/log_summary.json 无法解析: ' + str(exc)
    if not isinstance(data, dict):
        return False, '顶层必须是 JSON 对象'
    if type(data.get('total')) is not int or type(data.get('slow_count')) is not int:
        return False, 'total 与 slow_count 必须是整数'
    if not isinstance(data.get('by_level'), dict):
        return False, 'by_level 必须是对象'
    rate = data.get('error_rate')
    if isinstance(rate, bool) or not isinstance(rate, (int, float)):
        return False, 'error_rate 必须是数字'
    normalized = dict(data)
    normalized['error_rate'] = round(float(rate), 4)
    if normalized == EXPECTED:
        return True, '统计结果与期望完全一致'
    diffs = []
    for key, want in EXPECTED.items():
        if normalized.get(key) != want:
            diffs.append('%s: 期望 %r，实际 %r' % (key, want, normalized.get(key)))
    for key in normalized:
        if key not in EXPECTED:
            diffs.append('多余字段: ' + key)
    return False, '; '.join(diffs)
