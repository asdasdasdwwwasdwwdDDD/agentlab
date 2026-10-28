import json

EXPECTED = {
    'database': {
        'pool_size': 10,
        'timeout': 30,
        'url': 'postgresql://db:5432/app',
    },
    'features': {
        'beta_ui': False,
        'enable_search': True,
        'tags': ['alpha', 'beta', 'gamma'],
    },
    'server': {
        'debug': True,
        'host': '0.0.0.0',
        'port': 8080,
        'timeout_s': 60,
        'workers': 4,
    },
}


def check_migrated_config(ctx):
    try:
        data = json.loads(ctx.read('config/app.json'))
    except Exception as exc:
        return False, 'config/app.json 无法解析: ' + str(exc)
    if not isinstance(data, dict):
        return False, '顶层必须是 JSON 对象'
    for section in data:
        if not isinstance(data[section], dict):
            return False, '段落 %r 必须是对象' % (section,)
    if data == EXPECTED:
        return True, '迁移后的 JSON 与期望完全一致'
    diffs = []
    for section, want in EXPECTED.items():
        got = data.get(section)
        if got is None:
            diffs.append('缺少段落 ' + section)
            continue
        for key, want_value in want.items():
            if got.get(key) != want_value:
                diffs.append('%s.%s: 期望 %r，实际 %r' % (section, key, want_value, got.get(key)))
        for key in got:
            if key not in want:
                diffs.append('%s 下多余字段 %s' % (section, key))
    for section in data:
        if section not in EXPECTED:
            diffs.append('多余段落 ' + section)
    return False, '; '.join(diffs)
