"""rb-budget-oneshot：合并结果与清单的严格校验。"""

from __future__ import annotations

import json


def check_merged(ctx):
    if not ctx.exists("out/merged.json"):
        return False, "out/merged.json 不存在"
    try:
        data = json.loads(ctx.read("out/merged.json"))
    except json.JSONDecodeError as exc:
        return False, f"不是合法 JSON: {exc}"
    expected = {"a": 1, "b": 22, "c": 3}
    if data != expected:
        return False, f"期望 {expected}，实际 {data!r}"
    return True, "merged 正确"


def check_manifest(ctx):
    if not ctx.exists("out/manifest.txt"):
        return False, "out/manifest.txt 不存在"
    lines = [ln for ln in ctx.read("out/manifest.txt").splitlines() if ln.strip()]
    if len(lines) != 1:
        return False, f"manifest 应恰有 1 行，实际 {len(lines)} 行"
    expected = "keys=3 sum=26"
    if lines[0].strip() != expected:
        return False, f"期望 {expected!r}，实际 {lines[0]!r}"
    return True, "manifest 正确"
