"""尝试记录汇总。"""


def summarize_attempts(records):
    """按 attempt 升序返回新列表，每项追加 index（从 1 开始）；不修改输入。"""
    ordered = sorted(records, key=lambda record: record.get('duration_ms', 0))
    return [dict(record, index=index + 1) for index, record in enumerate(ordered)]
