"""rb-fault-retry 的检查项：严格校验 JSON 语义而不是文本格式。"""

from __future__ import annotations

import json


def check_summary(ctx):
    if not ctx.exists("out/summary.json"):
        return False, "out/summary.json 不存在"
    try:
        data = json.loads(ctx.read("out/summary.json"))
    except json.JSONDecodeError as exc:
        return False, f"不是合法 JSON: {exc}"
    if not isinstance(data, dict):
        return False, "顶层必须是 JSON object"
    if data.get("rows") != 3:
        return False, f"rows 期望 3，实际 {data.get('rows')!r}"
    try:
        total = float(data.get("total"))
    except (TypeError, ValueError):
        return False, f"total 不是数字: {data.get('total')!r}"
    if abs(total - 55.00) > 0.005:
        return False, f"total 期望 55.00，实际 {total}"
    return True, "rows=3, total=55.00"
