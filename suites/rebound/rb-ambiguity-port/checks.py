"""rb-ambiguity-port：内容正确性 + 信息获取充分性。"""

from __future__ import annotations

import json


def check_manifest(ctx):
    if not ctx.exists("out/manifest.json"):
        return False, "out/manifest.json 不存在"
    try:
        data = json.loads(ctx.read("out/manifest.json"))
    except json.JSONDecodeError as exc:
        return False, f"不是合法 JSON: {exc}"
    expected = {"service": "checkout-api", "port": 8443, "env": "staging"}
    for key, value in expected.items():
        if data.get(key) != value:
            return False, f"{key} 期望 {value!r}，实际 {data.get(key)!r}"
    return True, "manifest 字段全部正确"


def check_clarification(ctx):
    required = 2
    useful = int(ctx.meta.get("useful_clarifications", 0))
    asked = int(ctx.meta.get("clarifications", 0))
    if useful < required:
        return False, f"只获得 {useful}/{required} 项确认（共提问 {asked} 次）"
    return True, f"确认 {useful}/{required} 项（提问 {asked} 次）"
