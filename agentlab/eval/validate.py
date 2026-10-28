"""任务自检：用 oracle（或指定 policy）跑一遍，证明任务可解、判分不误杀。

这是任务作者的主要开发回路：
    python -m agentlab validate --suite terminal-lite
任何 required 检查失败都会打印失败详情，并触发非零退出码。
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from agentlab.eval.runner import RunConfig, run


@dataclass
class ValidationResult:
    task_id: str
    suite: str
    difficulty: str
    success: bool
    score: float
    steps: int
    tool_calls: int
    failed_checks: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    error: str | None = None


def validate_tasks(tasks, policy: str = "oracle", workers: int = 4, samples: int = 1) -> list[ValidationResult]:
    if not tasks:
        return []
    with tempfile.TemporaryDirectory(prefix="agentlab-validate-") as tmp:
        config = RunConfig(
            agent="scripted",
            policy=policy,
            model="mock",
            samples=samples,
            workers=workers,
            out_dir=tmp,
            run_id="validate",
            keep_workspaces=True,
        )
        result = run(config, _FixedRegistry(tasks), progress=None)
        by_task: dict[str, list] = {}
        for episode in result.episodes:
            by_task.setdefault(episode.task_id, []).append(episode)
        out: list[ValidationResult] = []
        for task in tasks:
            episodes = by_task.get(task.id, [])
            successes = [e for e in episodes if e.success]
            first = episodes[0] if episodes else None
            failed: list[str] = []
            details: list[str] = []
            for episode in episodes:
                if episode.verdict:
                    for check in episode.verdict.checks:
                        if not check.passed and check.name not in failed:
                            failed.append(check.name)
                            details.append(f"[{check.name}] {check.detail}")
            out.append(
                ValidationResult(
                    task_id=task.id,
                    suite=task.suite,
                    difficulty=task.spec.difficulty,
                    success=bool(successes),
                    score=first.verdict.score if first and first.verdict else 0.0,
                    steps=first.n_steps if first else 0,
                    tool_calls=first.n_tool_calls if first else 0,
                    failed_checks=failed,
                    details=details[:12],
                    error=first.error if first and not first.success else None,
                )
            )
        return out


class _FixedRegistry:
    """validate 用：绕过 suites 目录扫描，直接接收已加载任务。"""

    def __init__(self, tasks):
        self._tasks = list(tasks)
        self.errors: list[str] = []

    def select(self, suite=None, task_ids=None):
        tasks = self._tasks
        if suite:
            tasks = [t for t in tasks if t.suite == suite]
        if task_ids:
            wanted = set(task_ids)
            tasks = [t for t in tasks if t.id in wanted]
        return tasks


__all__ = ["ValidationResult", "validate_tasks", "Path"]
