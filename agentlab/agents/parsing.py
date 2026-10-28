"""把模型文本解析成 Action。对真实模型常见的格式漂移做有限归一化。"""

from __future__ import annotations

import json
import re
from typing import Any

from agentlab.core.types import BUILTIN_ACTIONS, Action

_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.S)
_ACTION_TAG = re.compile(r"<action>\s*(.*?)\s*</action>", re.S)
_ACTION_PREFIX = re.compile(r"^\s*(?:ACTION|Action|动作)\s*[:：]\s*", re.M)


def parse_action(text: str) -> Action | None:
    if not text or not text.strip():
        return None
    candidates: list[str] = []
    candidates.extend(match.group(1).strip() for match in _FENCE.finditer(text))
    candidates.extend(match.group(1).strip() for match in _ACTION_TAG.finditer(text))
    candidates.append(text.strip())
    for start in [m.start() for m in re.finditer(r"\{", text)][:5]:
        try:
            obj, _ = json.JSONDecoder().raw_decode(text[start:])
            candidates.append(json.dumps(obj))
        except json.JSONDecodeError:
            continue
    for candidate in candidates:
        candidate = _ACTION_PREFIX.sub("", candidate).strip()
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        action = _to_action(data)
        if action is not None:
            return action
    return None


def _to_action(data: Any) -> Action | None:
    if not isinstance(data, dict):
        return None
    kind = data.get("kind") or data.get("type") or data.get("action")
    args = data.get("args")
    if args is None:
        args = data.get("arguments")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    raw_args = dict(args) if isinstance(args, dict) else {}
    args = dict(raw_args)

    # 常见漂移：{"tool": "x", "args": {...}} / {"name": "x", "order_id": ...}
    if kind is None and ("tool" in data or ("name" in data and "command" not in data)):
        kind = "tool"
        args = {"name": data.get("tool") or data.get("name"), **raw_args}
    if kind is None and "command" in data:
        kind = "shell"
    if kind == "bash":
        kind = "shell"
    if kind not in BUILTIN_ACTIONS:
        return None

    # 把散落在顶层的参数收进 args
    known = {"kind", "type", "action", "args", "arguments", "tool", "name"}
    for key, value in data.items():
        if key not in known and key not in args:
            args[key] = value

    if kind == "tool":
        name = args.get("name")
        if not name:
            return None
        inner = args.get("args")
        if not isinstance(inner, dict):
            inner = {}
        # 顶层散参数统一移动到工具入参里
        for key in list(args):
            if key not in ("name", "args"):
                inner.setdefault(key, args.pop(key))
        args = {"name": name, "args": inner}
    return Action(kind=kind, args=args, raw=json.dumps(data, ensure_ascii=False)[:500])
