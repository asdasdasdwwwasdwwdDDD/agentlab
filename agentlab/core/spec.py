"""task.yaml 的模式定义与加载逻辑。

设计原则：
- 任务数据是纯声明式的；不允许在 YAML 里写 Python。
- 复杂断言只能通过 `checks.py` 的 `python` 检查项完成，路径固定、作用域受限。
- 任何字段拼写错误都应该在加载期报错（extra=forbid），而不是静默忽略。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

CATEGORIES = ("terminal", "repo", "tools", "rebound")
DIFFICULTIES = ("easy", "medium", "hard")
VISIBILITIES = ("public", "hidden")

FAULT_KINDS = (
    "delete_file",
    "write_file",
    "append_file",
    "remove_file_pattern",
    "block_command",
    "corrupt_file",
    "drift_write",
    "drift_delete",
)
_FAULT_FILE_KINDS = {"delete_file", "write_file", "append_file", "corrupt_file", "drift_write", "drift_delete"}

# kind -> 必须提供的额外参数（除 name/kind/weight/required 外）
CHECK_REQUIRED_PARAMS: dict[str, set[str]] = {
    "file_exists": {"path"},
    "file_absent": {"path"},
    "dir_exists": {"path"},
    "file_contains": {"path", "pattern"},
    "file_not_contains": {"path", "pattern"},
    "file_equals": {"path"},
    "file_line_count": {"path"},
    "shell": {"command"},
    "state_changed": {"paths"},
    "state_unchanged": {"paths"},
    "tool_called": {"tool"},
    "python": {"func"},
}

BUILTIN_TOOLS = {"shell", "read_file", "write_file", "list_dir", "ask_user", "finish", "give_up"}


class SpecError(ValueError):
    """任务包非法（面向任务作者，需要可操作的错误信息）。"""


class WorkspaceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    copy_files: bool = False
    files: dict[str, str] = Field(default_factory=dict)


class BudgetSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_tool_calls: int = 20
    max_tokens: int = 60_000
    max_wall_s: float = 300.0
    oracle_tool_calls: int = 1


class MockResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    match: str | None = None
    response: str | None = None
    default: str | None = None

    @model_validator(mode="after")
    def _check_shape(self) -> "MockResponse":
        has_match = self.match is not None and self.response is not None
        has_default = self.default is not None and self.response is None and self.match is None
        if not (has_match or has_default):
            raise ValueError("mock 条目必须是 {match, response} 或 {default}")
        if self.match is not None:
            try:
                re.compile(self.match)
            except re.error as exc:  # pragma: no cover - 依赖作者输入
                raise ValueError(f"非法正则 {self.match!r}: {exc}") from exc
        return self


class ToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    kind: str = "builtin"  # builtin | mock_tool
    description: str = ""
    mock: list[MockResponse] = Field(default_factory=list)
    effect: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> "ToolSpec":
        if self.kind not in ("builtin", "mock_tool"):
            raise ValueError(f"tool kind 必须是 builtin 或 mock_tool: {self.name}")
        if self.kind == "mock_tool" and not self.mock:
            raise ValueError(f"mock_tool {self.name} 至少要有一条 mock 响应")
        return self

    def respond(self, args_text: str) -> str:
        """按声明顺序做正则匹配，未命中走 default。"""
        fallback = ""
        for item in self.mock:
            if item.default is not None:
                fallback = item.default
                continue
            assert item.match is not None and item.response is not None
            if re.search(item.match, args_text, re.IGNORECASE):
                return item.response
        if fallback:
            return fallback
        return f"[mock:{self.name}] 无匹配响应（args={args_text[:200]}）"


class AnswerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    match: str | None = None
    reply: str | None = None
    default: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "AnswerSpec":
        if (self.match is None) == (self.default is None):
            raise ValueError("answers 每项必须是 {match, reply} 或 {default}")
        if self.match is not None:
            if self.reply is None:
                raise ValueError("answers 带 match 时必须给 reply")
            try:
                re.compile(self.match)
            except re.error as exc:
                raise ValueError(f"非法正则 {self.match!r}: {exc}") from exc
        return self


class AmbiguitySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clarification_budget: int = 3
    required_clarifications: int = 1
    answers: list[AnswerSpec] = Field(default_factory=list)

    @field_validator("clarification_budget", "required_clarifications")
    @classmethod
    def _non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("ambiguity 计数不能为负")
        return value

    def respond(self, question: str) -> tuple[str, bool]:
        """返回 (回复, 是否命中可判定信息)。"""
        fallback = ""
        for item in self.answers:
            if item.default is not None:
                fallback = item.default
                continue
            if item.match is not None and re.search(item.match, question, re.IGNORECASE):
                return item.reply or "", True
        return fallback or "（用户没有回答）", False


class FaultSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    at_step: int = 1
    axis: str = "fault"  # fault | drift
    kind: str
    path: str | None = None
    content: str | None = None
    match: str | None = None
    announce: bool = True
    note: str = ""

    @model_validator(mode="after")
    def _check(self) -> "FaultSpec":
        if self.kind not in FAULT_KINDS:
            raise ValueError(f"未知 fault kind: {self.kind!r} (可选 {FAULT_KINDS})")
        if self.axis not in ("fault", "drift"):
            raise ValueError(f"fault axis 必须是 fault 或 drift: {self.axis!r}")
        if self.kind in _FAULT_FILE_KINDS and not self.path:
            raise ValueError(f"{self.kind} 需要 path")
        if self.kind in ("write_file", "drift_write", "corrupt_file") and self.content is None:
            raise ValueError(f"{self.kind} 需要 content")
        if self.kind == "block_command":
            if not self.match:
                raise ValueError("block_command 需要 match 正则")
            try:
                re.compile(self.match)
            except re.error as exc:
                raise ValueError(f"非法正则 {self.match!r}: {exc}") from exc
        if self.at_step < 0:
            raise ValueError("at_step 不能为负")
        return self


class CheckSpec(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    kind: str
    weight: float = 1.0
    required: bool = True

    @property
    def params(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


class VerifierSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pass_threshold: float = 1.0
    checks: list[CheckSpec]

    @field_validator("checks")
    @classmethod
    def _non_empty(cls, checks: list[CheckSpec]) -> list[CheckSpec]:
        if not checks:
            raise ValueError("verifier.checks 不能为空")
        names = [c.name for c in checks]
        dup = {n for n in names if names.count(n) > 1}
        if dup:
            raise ValueError(f"检查项 name 重复: {sorted(dup)}")
        return checks


class SolutionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actions: list[dict[str, Any]] = Field(default_factory=list)


class TaskSpec(BaseModel):
    """单个任务的声明式定义。字段语义见 docs/DESIGN.md §4。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    category: str
    difficulty: str = "medium"
    tags: list[str] = Field(default_factory=list)
    visibility: str = "public"
    prompt: str
    max_steps: int = 12
    timeout_s: float = 60.0
    workspace: WorkspaceSpec = Field(default_factory=WorkspaceSpec)
    tools: list[ToolSpec] = Field(default_factory=lambda: [ToolSpec(name="shell")])
    budget: BudgetSpec = Field(default_factory=BudgetSpec)
    faults: list[FaultSpec] = Field(default_factory=list)
    ambiguity: AmbiguitySpec | None = None
    verifier: VerifierSpec
    solution: SolutionSpec = Field(default_factory=SolutionSpec)
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tools", mode="before")
    @classmethod
    def _coerce_tools(cls, value: Any) -> Any:
        """允许简写 `tools: [shell, read_file]`。"""
        if value is None:
            return [{"name": "shell"}]
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return value
        return [{"name": item} if isinstance(item, str) else item for item in value]

    @field_validator("id")
    @classmethod
    def _id_shape(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", value):
            raise ValueError(f"id 必须匹配 [a-z0-9][a-z0-9._-]*，收到 {value!r}")
        return value

    @field_validator("category")
    @classmethod
    def _category(cls, value: str) -> str:
        if value not in CATEGORIES:
            raise ValueError(f"category 必须是 {CATEGORIES} 之一，收到 {value!r}")
        return value

    @field_validator("difficulty")
    @classmethod
    def _difficulty(cls, value: str) -> str:
        if value not in DIFFICULTIES:
            raise ValueError(f"difficulty 必须是 {DIFFICULTIES} 之一，收到 {value!r}")
        return value

    @field_validator("visibility")
    @classmethod
    def _visibility(cls, value: str) -> str:
        if value not in VISIBILITIES:
            raise ValueError(f"visibility 必须是 {VISIBILITIES} 之一，收到 {value!r}")
        return value

    @field_validator("max_steps")
    @classmethod
    def _max_steps(cls, value: int) -> int:
        if not 1 <= value <= 200:
            raise ValueError("max_steps 应在 1..200")
        return value

    @model_validator(mode="after")
    def _check_tools_and_checks(self) -> "TaskSpec":
        names: list[str] = []
        for tool in self.tools:
            if tool.kind == "builtin" and tool.name not in BUILTIN_TOOLS:
                raise ValueError(f"未知内置工具: {tool.name}")
            names.append(tool.name)
        if len(names) != len(set(names)):
            raise ValueError("tools 中存在重复名称")
        if any(t.kind == "builtin" and t.name == "ask_user" for t in self.tools):
            if self.ambiguity is None:
                raise ValueError("声明了 ask_user 但缺少 ambiguity 配置")
        for check in self.verifier.checks:
            required = CHECK_REQUIRED_PARAMS.get(check.kind)
            if required is None:
                raise ValueError(f"未知检查项 kind: {check.kind!r} (检查项 {check.name})")
            missing = required - set(check.params)
            if missing:
                raise ValueError(f"检查项 {check.name} ({check.kind}) 缺少参数 {sorted(missing)}")
            if check.kind == "file_equals" and not ({"content", "content_file"} & set(check.params)):
                raise ValueError(f"检查项 {check.name} (file_equals) 需要 content 或 content_file")
            if check.weight <= 0:
                raise ValueError(f"检查项 {check.name} 的 weight 必须 > 0")
        if not (0.0 < self.verifier.pass_threshold <= 1.0):
            raise ValueError("pass_threshold 应在 (0, 1]")
        if self.faults and self.category != "rebound":
            raise ValueError("只有 category=rebound 的任务可以声明 faults")
        return self

    # ---- 便捷访问 ----
    @property
    def tool_names(self) -> list[str]:
        return [t.name for t in self.tools]

    def get_tool(self, name: str) -> ToolSpec | None:
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    @property
    def is_ambiguous(self) -> bool:
        return self.ambiguity is not None

    def solution_actions(self) -> list[Any]:
        from agentlab.core.types import Action

        return [Action.from_dict(dict(a)) for a in self.solution.actions]

    def fingerprint(self) -> str:
        """任务内容哈希（用于结果可复现性校验）。"""
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class LoadedTask:
    """任务定义 + 所在目录（checks.py / files/ 的锚点）。"""

    spec: TaskSpec
    root: Path

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def suite(self) -> str:
        return self.root.parent.name

    @property
    def checks_module_path(self) -> Path:
        return self.root / "checks.py"

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"LoadedTask(id={self.spec.id!r}, suite={self.suite!r})"


def load_task(path: str | Path) -> LoadedTask:
    """加载单个任务包（目录或 task.yaml）。"""
    path = Path(path)
    root = path if path.is_dir() else path.parent
    yaml_path = root / "task.yaml" if path.is_dir() else path
    if not yaml_path.exists():
        raise SpecError(f"找不到 task.yaml: {yaml_path}")
    try:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SpecError(f"YAML 解析失败 {yaml_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SpecError(f"task.yaml 顶层必须是 mapping: {yaml_path}")
    try:
        spec = TaskSpec.model_validate(raw)
    except ValidationError as exc:
        raise SpecError(f"任务模式校验失败 {yaml_path}:\n{_format_validation(exc)}") from exc
    if spec.id != root.name:
        raise SpecError(f"任务 id ({spec.id}) 必须与目录名 ({root.name}) 一致: {yaml_path}")
    if spec.workspace.copy_files and not (root / "files").is_dir():
        raise SpecError(f"copy_files=true 但缺少 files/ 目录: {root}")
    return LoadedTask(spec=spec, root=root)


def _format_validation(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        lines.append(f"  - {loc}: {err['msg']}")
    return "\n".join(lines)


def ensure_template(name: str) -> str:
    """给 doctor / 脚手架用：返回一个最小可运行任务模板。"""
    return f"""id: {name}
name: 示例任务
category: terminal
difficulty: easy
prompt: 在 workspace 中创建 hello.txt，内容为 hello
max_steps: 4
tools: [shell, read_file, write_file]
verifier:
  checks:
    - name: hello_exists
      kind: file_exists
      path: hello.txt
    - name: hello_content
      kind: file_contains
      path: hello.txt
      pattern: "^hello$"
solution:
  actions:
    - kind: write_file
      args: {{path: hello.txt, content: "hello"}}
"""
