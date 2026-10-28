"""指标：置信区间、pass@k、效率分、聚合。

公式与口径见 docs/DESIGN.md §8。所有函数都只依赖 Episode，便于离线复算。
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from typing import Any, Iterable

from agentlab.core.types import Episode

# REBOUND 综合分权重（改这里必须同步 docs/gaps-and-proposal.md）
REBOUND_WEIGHTS = {"sr": 0.40, "rrs": 0.25, "es": 0.20, "cq": 0.15}


def wilson_ci(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return (0.0, 0.0)
    phat = successes / total
    denom = 1 + z * z / total
    center = (phat + z * z / (2 * total)) / denom
    margin = z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def pass_at_k(n: int, c: int, k: int) -> float:
    """无偏 estimate：1 - C(n-c, k) / C(n, k)。"""
    if n <= 0 or k <= 0:
        return 0.0
    if c <= 0:
        return 0.0
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def efficiency_score(success: bool, used_calls: int, oracle_calls: int, cap: int) -> float:
    """成功且接近 oracle 调用数得 1；超出预算上限得 0。见 DESIGN §8。"""
    if not success:
        return 0.0
    oracle_calls = max(1, int(oracle_calls))
    cap = max(oracle_calls + 1, int(cap))
    over = max(0, used_calls - oracle_calls)
    span = cap - oracle_calls
    return round(max(0.0, min(1.0, 1.0 - over / span)), 4)


def clarification_quality(episode: Episode, required: int) -> float:
    if required <= 0:
        return 1.0
    return round(min(1.0, episode.useful_clarifications / required), 4)


def aggregate(episodes: list[Episode]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "overall": _stats(episodes),
        "by_suite": {k: _stats(v) for k, v in _group(episodes, lambda e: e.suite).items()},
        "by_difficulty": {k: _stats(v) for k, v in _group(episodes, lambda e: e.difficulty).items()},
        "by_agent": {k: _stats(v) for k, v in _group(episodes, lambda e: f"{e.agent}/{e.model}").items()},
        "by_task": {k: _stats(v) for k, v in sorted(_group(episodes, lambda e: e.task_id).items())},
        "taxonomy": dict(sorted(Counter(e.metrics.get("failure_mode", "none") for e in episodes).items())),
        "recovery": _recovery(episodes),
        "rebound": _rebound(episodes),
        "pass_at_k": _pass_at_k(episodes),
        "per_task_rows": _per_task_rows(episodes),
    }
    return summary


def _group(episodes: Iterable[Episode], key) -> dict[str, list[Episode]]:
    groups: dict[str, list[Episode]] = defaultdict(list)
    for episode in episodes:
        groups[key(episode)].append(episode)
    return dict(groups)


def _stats(episodes: list[Episode]) -> dict[str, Any]:
    n = len(episodes)
    successes = sum(1 for e in episodes if e.success)
    ci = wilson_ci(successes, n)
    calls = [e.n_tool_calls for e in episodes]
    steps = [e.n_steps for e in episodes]
    walls = [e.wall_ms for e in episodes]
    eff = [float(e.metrics.get("efficiency", 0.0)) for e in episodes]
    return {
        "n": n,
        "successes": successes,
        "success_rate": round(successes / n, 4) if n else 0.0,
        "wilson_ci": [round(ci[0], 4), round(ci[1], 4)],
        "avg_tool_calls": round(statistics.fmean(calls), 2) if calls else 0.0,
        "avg_steps": round(statistics.fmean(steps), 2) if steps else 0.0,
        "p50_wall_ms": int(statistics.median(walls)) if walls else 0,
        "avg_efficiency": round(statistics.fmean(eff), 4) if eff else 0.0,
        "avg_cost_usd": round(statistics.fmean([e.cost_usd for e in episodes]), 6) if episodes else 0.0,
        "avg_tokens": round(
            statistics.fmean([e.prompt_tokens + e.completion_tokens for e in episodes]), 1
        )
        if episodes
        else 0.0,
    }


def _recovery(episodes: list[Episode]) -> dict[str, Any]:
    clean = [e for e in episodes if not e.faults]
    fault = [e for e in episodes if "fault" in e.fault_axes]
    drift = [e for e in episodes if "drift" in e.fault_axes]

    def rate(items: list[Episode]) -> float | None:
        return round(sum(1 for e in items if e.success) / len(items), 4) if items else None

    clean_sr, rrs, drs = rate(clean), rate(fault), rate(drift)
    lift = round(rrs - clean_sr, 4) if (rrs is not None and clean_sr is not None) else None
    return {
        "clean": {"n": len(clean), "success_rate": clean_sr},
        "fault": {"n": len(fault), "success_rate": rrs},
        "drift": {"n": len(drift), "success_rate": drs},
        "recovery_lift": lift,
    }


def _rebound(episodes: list[Episode]) -> dict[str, Any]:
    rebound = [e for e in episodes if e.suite == "rebound"]
    if not rebound:
        return {"n": 0, "score": None, "sr": None, "rrs": None, "es": None, "cq": None}
    sr = sum(1 for e in rebound if e.success) / len(rebound)
    fault = [e for e in rebound if "fault" in e.fault_axes]
    rrs = (sum(1 for e in fault if e.success) / len(fault)) if fault else None
    es = statistics.fmean([float(e.metrics.get("efficiency", 0.0)) for e in rebound])
    cq_values = [float(e.metrics.get("clarification_quality", 0.0)) for e in rebound if e.metrics.get("has_ambiguity")]
    cq = statistics.fmean(cq_values) if cq_values else None
    parts = {
        "sr": sr,
        "rrs": rrs if rrs is not None else sr,
        "es": es,
        "cq": cq if cq is not None else 1.0,
    }
    score = sum(REBOUND_WEIGHTS[k] * v for k, v in parts.items())
    return {
        "n": len(rebound),
        "score": round(score, 4),
        "sr": round(parts["sr"], 4),
        "rrs": round(parts["rrs"], 4),
        "es": round(parts["es"], 4),
        "cq": round(parts["cq"], 4),
        "weights": REBOUND_WEIGHTS,
    }


def _pass_at_k(episodes: list[Episode]) -> dict[str, Any]:
    by_task: dict[str, list[Episode]] = defaultdict(list)
    for episode in episodes:
        by_task[episode.task_id].append(episode)
    ks = sorted({len(v) for v in by_task.values()})
    out: dict[str, Any] = {}
    for k in ks:
        if k <= 0:
            continue
        values = [pass_at_k(len(v), sum(1 for e in v if e.success), k) for v in by_task.values()]
        out[f"pass@{k}"] = round(statistics.fmean(values), 4)
    return out


def _per_task_rows(episodes: list[Episode]) -> list[dict[str, Any]]:
    by_task: dict[str, list[Episode]] = defaultdict(list)
    for episode in episodes:
        by_task[episode.task_id].append(episode)
    rows = []
    for task_id, items in sorted(by_task.items()):
        stats = _stats(items)
        rows.append(
            {
                "task_id": task_id,
                "suite": items[0].suite,
                "difficulty": items[0].difficulty,
                "n": stats["n"],
                "success_rate": stats["success_rate"],
                "avg_tool_calls": stats["avg_tool_calls"],
                "avg_efficiency": stats["avg_efficiency"],
                "failed_checks": sorted(
                    {c.name for e in items if e.verdict for c in e.verdict.checks if not c.passed}
                ),
                "failure_modes": sorted({e.metrics.get("failure_mode") for e in items if not e.success}),
            }
        )
    return rows
