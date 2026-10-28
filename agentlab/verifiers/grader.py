"""判分：把检查项组合成 Verdict（确定性，可复现）。"""

from __future__ import annotations

from typing import Any

from agentlab.core.spec import LoadedTask
from agentlab.core.types import Action, CheckResult, Verdict
from agentlab.verifiers.checks import CheckContext, run_check


def grade(
    task: LoadedTask,
    workspace,
    state_before: dict[str, str],
    state_after: dict[str, str],
    tool_log: list[dict],
    actions: list[Action],
    meta: dict[str, Any] | None = None,
    skip_kinds: frozenset[str] = frozenset(),
) -> Verdict:
    ctx = CheckContext(
        task=task,
        workspace=workspace,
        state_before=state_before,
        state_after=state_after,
        tool_log=tool_log,
        actions=actions,
        meta=meta or {},
    )
    checks = [c for c in task.spec.verifier.checks if c.kind not in skip_kinds]
    if not checks:
        return Verdict(success=False, score=0.0, checks=[], message="没有可执行的检查项（可能全部被 skip）")
    results: list[CheckResult] = [run_check(check, ctx) for check in checks]
    total_weight = sum(r.weight for r in results) or 1.0
    score = sum(r.weight for r in results if r.passed) / total_weight
    required_ok = all(r.passed for r in results if r.required)
    success = required_ok and score >= task.spec.verifier.pass_threshold
    failed = [r.name for r in results if not r.passed]
    message = "全部检查通过" if success else f"未通过检查: {', '.join(failed) or '无（分数不足）'}"
    return Verdict(success=success, score=round(score, 4), checks=results, message=message)
