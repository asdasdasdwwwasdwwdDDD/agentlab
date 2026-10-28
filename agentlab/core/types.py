"""运行时数据模型：与任务格式解耦，可安全地序列化为 JSON。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Status = Literal["success", "failure", "error", "timeout", "budget"]

BUILTIN_ACTIONS = (
    "shell",
    "read_file",
    "write_file",
    "list_dir",
    "ask_user",
    "tool",
    "finish",
    "give_up",
)


@dataclass
class Action:
    """Agent 的一次动作。

    kind=tool 时 args = {"name": <tool>, "args": {...}}；其余 kind 直接放参数字段。
    """

    kind: str
    args: dict[str, Any] = field(default_factory=dict)
    raw: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in BUILTIN_ACTIONS:
            raise ValueError(f"unknown action kind: {self.kind!r}")

    @property
    def command(self) -> str:
        return str(self.args.get("command", ""))

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind, "args": self.args}
        if self.raw is not None:
            out["raw"] = self.raw
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Action":
        if "kind" not in data:
            raise ValueError(f"action missing kind: {data!r}")
        args = data.get("args")
        if not isinstance(args, dict):
            args = {}
        # 兼容简写：把除元信息外的顶层字段收进 args（如 kind: shell / command: "..."）
        for key, value in data.items():
            if key not in ("kind", "args", "raw") and key not in args:
                args[key] = value
        return cls(kind=data["kind"], args=args, raw=data.get("raw"))


@dataclass
class Observation:
    """环境返回给 Agent 的观测。text 是唯一进入 prompt 的部分。"""

    text: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class StepResult:
    observation: Observation
    done: bool = False
    reward_hint: float | None = None
    info: dict[str, Any] = field(default_factory=dict)


@dataclass
class Step:
    """一步交互的完整记录（用于轨迹落盘与失败分析）。"""

    idx: int
    action: Action
    observation: str
    done: bool = False
    reward_hint: float | None = None
    info: dict[str, Any] = field(default_factory=dict)
    t_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "idx": self.idx,
            "action": self.action.to_dict(),
            "observation": self.observation,
            "done": self.done,
            "reward_hint": self.reward_hint,
            "info": self.info,
            "t_ms": self.t_ms,
        }


@dataclass
class CheckResult:
    name: str
    kind: str
    passed: bool
    weight: float = 1.0
    required: bool = True
    detail: str = ""
    severity: str = "ok"  # ok | warn | error

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Verdict:
    success: bool
    score: float
    checks: list[CheckResult] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "score": self.score,
            "checks": [c.to_dict() for c in self.checks],
            "message": self.message,
        }

    def failed_names(self) -> list[str]:
        return [c.name for c in self.checks if not c.passed]


@dataclass
class FaultEvent:
    at_step: int
    axis: str
    kind: str
    note: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Episode:
    run_id: str
    task_id: str
    suite: str
    category: str
    difficulty: str
    agent: str
    model: str
    sample_idx: int = 0
    status: Status = "failure"
    verdict: Verdict | None = None
    steps: list[Step] = field(default_factory=list)
    n_steps: int = 0
    n_tool_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    wall_ms: int = 0
    cost_usd: float = 0.0
    faults: list[FaultEvent] = field(default_factory=list)
    clarifications: int = 0
    useful_clarifications: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self, include_steps: bool = True) -> dict[str, Any]:
        out: dict[str, Any] = {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "suite": self.suite,
            "category": self.category,
            "difficulty": self.difficulty,
            "agent": self.agent,
            "model": self.model,
            "sample_idx": self.sample_idx,
            "status": self.status,
            "verdict": self.verdict.to_dict() if self.verdict else None,
            "n_steps": self.n_steps,
            "n_tool_calls": self.n_tool_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "wall_ms": self.wall_ms,
            "cost_usd": round(self.cost_usd, 6),
            "faults": [f.to_dict() for f in self.faults],
            "clarifications": self.clarifications,
            "useful_clarifications": self.useful_clarifications,
            "metrics": self.metrics,
            "error": self.error,
        }
        if include_steps:
            out["steps"] = [s.to_dict() for s in self.steps]
        return out

    @property
    def success(self) -> bool:
        return self.status == "success" and bool(self.verdict and self.verdict.success)

    @property
    def fault_axes(self) -> set[str]:
        return {f.axis for f in self.faults}
