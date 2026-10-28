"""失败分类：互斥的单一归因，供报告与错误分析使用。"""

from __future__ import annotations

import json
from collections import Counter

from agentlab.core.types import Episode

# 优先级从高到低（DESIGN §8）
TAXONOMY_ORDER = (
    "error",
    "gave_up",
    "budget",
    "timeout",
    "loop",
    "no_attempt",
    "fault_unrecovered",
    "wrong_output",
    "incomplete",
    "none",
)


def classify(episode: Episode) -> str:
    if episode.status == "error":
        return "error"
    if episode.success:
        return "none"
    if _gave_up(episode):
        return "gave_up"
    if episode.status == "budget":
        return "budget"
    if episode.status == "timeout":
        return "timeout"
    if _looped(episode):
        return "loop"
    if not any(step.action.kind in ("shell", "tool") for step in episode.steps):
        return "no_attempt"
    if episode.faults:
        return "fault_unrecovered"
    failed = [c for c in (episode.verdict.checks if episode.verdict else []) if not c.passed]
    if any(c.kind in ("file_equals", "file_contains", "python", "shell") for c in failed):
        return "wrong_output"
    return "incomplete"


def _gave_up(episode: Episode) -> bool:
    for step in reversed(episode.steps):
        if step.action.kind == "give_up":
            return True
        if step.done:
            return False
    return False


def _looped(episode: Episode) -> bool:
    keys = [f"{s.action.kind}:{json.dumps(s.action.args, sort_keys=True, ensure_ascii=False)}" for s in episode.steps]
    run = 1
    for prev, cur in zip(keys, keys[1:]):
        run = run + 1 if cur == prev else 1
        if run >= 3:
            return True
    return False


def distribution(episodes: list[Episode]) -> dict[str, int]:
    counts = Counter(classify(e) for e in episodes)
    return {name: counts.get(name, 0) for name in TAXONOMY_ORDER if counts.get(name, 0) or name == "none"}
