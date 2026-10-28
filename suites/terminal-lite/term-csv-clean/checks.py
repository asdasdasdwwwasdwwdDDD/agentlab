import csv
import io

EXPECTED_ROWS = [
    ['id', 'name', 'email', 'updated_at', 'status'],
    ['u10', 'Alice Chen', 'alice@example.com', '2024-03-05', 'active'],
    ['u2', 'Bob Lee', 'bob@example.com', '2024-03-06', 'active'],
    ['u3', 'Acme, Inc', 'ops@acme.io', '2024-01-10', 'active'],
    ['u4', '', 'noreply@x.dev', '2024-02-01', 'active'],
    ['u7', 'Eve', 'eve@example.com', '2024-01-02', 'inactive'],
    ['u8', 'Frank', 'frank@example.com', '2024-02-20', 'active'],
    ['u9', 'Grace', 'grace@example.com', '2024-03-01', 'inactive'],
]


def check_clean_csv(ctx):
    try:
        text = ctx.read('out/clean.csv')
    except Exception as exc:
        return False, 'out/clean.csv 不存在或不可读: ' + str(exc)
    if text.startswith('\ufeff'):
        return False, '输出不能包含 UTF-8 BOM'
    if '\r' in text:
        return False, '必须使用 LF 换行（发现 CR）'
    if not text.endswith('\n') or text.endswith('\n\n'):
        return False, '文件必须以单个换行结尾'
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) != len(EXPECTED_ROWS):
        return False, '数据行数不符：期望 %d 行（含表头），实际 %d 行' % (len(EXPECTED_ROWS), len(rows))
    for index, (got, want) in enumerate(zip(rows, EXPECTED_ROWS)):
        if got != want:
            return False, '第 %d 行不符：期望 %r，实际 %r' % (index + 1, want, got)
    return True, '清洗结果完全一致：7 行数据，去重/日期归一/字典序排序均正确'
