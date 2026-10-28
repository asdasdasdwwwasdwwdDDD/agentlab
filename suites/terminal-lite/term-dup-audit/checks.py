import json

EXPECTED = {'scanned_count': 9, 'empty_file_count': 2, 'groups': [{'sha256': 'b95a07037a0d40aa7deb537a6863e29d67856bb15b2008967e9cb866f2f3f4a9', 'size': 36, 'paths': ['a/report copy.txt', 'a/report.txt', 'b/archive/report-2023.txt']}, {'sha256': '70b1e12cfeaa62fcf965cc791cb0d983cd3ce5c5cf27446ff28893312c9cfe57', 'size': 16, 'paths': ['c/data.csv', 'd/backup/data.csv']}], 'redundant_count': 3, 'wasted_bytes': 88}


def check_duplicates(ctx):
    try:
        data = json.loads(ctx.read('audit/duplicates.json'))
    except Exception as exc:
        return False, 'audit/duplicates.json 无法解析: ' + str(exc)
    if not isinstance(data, dict):
        return False, '顶层必须是 JSON 对象'
    if data == EXPECTED:
        return True, '重复审计结果与期望完全一致'
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
