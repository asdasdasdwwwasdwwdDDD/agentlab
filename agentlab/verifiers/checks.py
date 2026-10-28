"""检查项实现：全部确定性、无副作用（shell 检查除外）。

每个检查项只依赖 CheckContext，方便单测与复用。
"""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from agentlab.core.spec import CheckSpec
from agentlab.core.types import Action, CheckResult
from agentlab.envs.base import default_shell_argv, wrap_shell_command
from agentlab.envs.fsutil import PathEscapeError, read_text, safe_resolve

_CHECK_CACHE: dict[str, tuple[float, Any]] = {}


class CheckContext:
    """检查项可访问的只读上下文（禁止读取 solution）。"""

    def __init__(
        self,
        task,
        workspace: Path,
        state_before: dict[str, str],
        state_after: dict[str, str],
        tool_log: list[dict],
        actions: list[Action],
        meta: dict[str, Any] | None = None,
    ):
        self.task = task
        self.workspace = Path(workspace)
        self.state_before = state_before
        self.state_after = state_after
        self.tool_log = tool_log
        self.actions = actions
        self.meta = meta or {}

    def path(self, rel: str) -> Path:
        return safe_resolve(self.workspace, rel)

    def read(self, rel: str) -> str:
        return read_text(self.workspace, rel, max_bytes=10 * 1024 * 1024)

    def exists(self, rel: str) -> bool:
        try:
            return self.path(rel).exists()
        except PathEscapeError:
            return False

    def is_file(self, rel: str) -> bool:
        try:
            return self.path(rel).is_file()
        except PathEscapeError:
            return False


def _result(check: CheckSpec, passed: bool, detail: str = "", severity: str = "ok") -> CheckResult:
    return CheckResult(
        name=check.name,
        kind=check.kind,
        passed=passed,
        weight=check.weight,
        required=check.required,
        detail=detail,
        severity=severity,
    )


def _error(check: CheckSpec, exc: Exception) -> CheckResult:
    return _result(check, False, f"检查执行异常: {type(exc).__name__}: {exc}", severity="error")


# ----------------------------------------------------------------- 基础断言
def check_file_exists(check: CheckSpec, ctx: CheckContext) -> CheckResult:
    rel = str(check.params["path"])
    ok = ctx.is_file(rel)
    return _result(check, ok, f"{rel} {'存在' if ok else '不存在'}")


def check_file_absent(check: CheckSpec, ctx: CheckContext) -> CheckResult:
    rel = str(check.params["path"])
    ok = not ctx.exists(rel)
    return _result(check, ok, f"{rel} {'不存在' if ok else '仍存在（应被清理）'}")


def check_dir_exists(check: CheckSpec, ctx: CheckContext) -> CheckResult:
    rel = str(check.params["path"])
    ok = ctx.exists(rel) and ctx.path(rel).is_dir()
    return _result(check, ok, f"{rel} {'是目录' if ok else '不是目录/不存在'}")


def check_file_contains(check: CheckSpec, ctx: CheckContext) -> CheckResult:
    rel = str(check.params["path"])
    pattern = str(check.params["pattern"])
    flags = _flags(check.params.get("flags", ""))
    if not ctx.is_file(rel):
        return _result(check, False, f"{rel} 不存在")
    matched = re.search(pattern, ctx.read(rel), flags)
    return _result(check, matched is not None, f"pattern={pattern!r} {'命中' if matched else '未命中'}")


def check_file_not_contains(check: CheckSpec, ctx: CheckContext) -> CheckResult:
    inner = check_file_contains(check, ctx)
    return _result(check, not inner.passed, inner.detail.replace("命中", "命中（应被移除）"))


def check_file_equals(check: CheckSpec, ctx: CheckContext) -> CheckResult:
    rel = str(check.params["path"])
    expected = check.params.get("content")
    if expected is None:
        content_file = str(check.params["content_file"])
        expected = (ctx.task.root / content_file).read_text(encoding="utf-8")
    expected = _normalize(str(expected))
    if not ctx.is_file(rel):
        return _result(check, False, f"{rel} 不存在")
    actual = _normalize(ctx.read(rel))
    if actual == expected:
        return _result(check, True, f"{rel} 内容一致")
    detail = f"{rel} 内容不一致: 期望 {len(expected)} 字符, 实际 {len(actual)} 字符"
    return _result(check, False, detail)


def check_file_line_count(check: CheckSpec, ctx: CheckContext) -> CheckResult:
    rel = str(check.params["path"])
    if not ctx.is_file(rel):
        return _result(check, False, f"{rel} 不存在")
    lines = [ln for ln in ctx.read(rel).splitlines() if ln.strip()]
    minimum = check.params.get("min")
    maximum = check.params.get("max")
    ok = (minimum is None or len(lines) >= int(minimum)) and (maximum is None or len(lines) <= int(maximum))
    return _result(check, ok, f"{rel} 非空行数={len(lines)} (min={minimum}, max={maximum})")


def check_state_changed(check: CheckSpec, ctx: CheckContext) -> CheckResult:
    paths = _as_list(check.params["paths"])
    changed, unchanged = _state_delta(ctx, paths)
    return _result(check, bool(changed), f"变化: {sorted(changed)}; 未变化: {sorted(unchanged)}")


def check_state_unchanged(check: CheckSpec, ctx: CheckContext) -> CheckResult:
    paths = _as_list(check.params["paths"])
    changed, unchanged = _state_delta(ctx, paths)
    return _result(check, not changed, f"被误改: {sorted(changed)}" if changed else f"{len(unchanged)} 个路径保持原样")


# ------------------------------------------------------------------- 执行类
def check_shell(check: CheckSpec, ctx: CheckContext) -> CheckResult:
    command = str(check.params["command"])
    expect_exit = int(check.params.get("expect_exit", 0))
    timeout = float(check.params.get("timeout_s", 60))
    shell_argv = default_shell_argv()
    argv = [*shell_argv, wrap_shell_command(shell_argv, command)]
    proc = subprocess.run(
        argv,
        cwd=str(ctx.workspace),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    detail = f"exit={proc.returncode} (期望 {expect_exit})"
    ok = proc.returncode == expect_exit
    if "stdout_contains" in check.params:
        pattern = str(check.params["stdout_contains"])
        hit = re.search(pattern, proc.stdout or "") is not None
        ok = ok and hit
        detail += f"; stdout /{pattern}/ {'命中' if hit else '未命中'}"
    if "stderr_contains" in check.params:
        pattern = str(check.params["stderr_contains"])
        hit = re.search(pattern, proc.stderr or "") is not None
        ok = ok and hit
        detail += f"; stderr /{pattern}/ {'命中' if hit else '未命中'}"
    if not ok:
        tail = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()[-3:]
        detail += f"; 输出尾部: {' | '.join(tail)[:300]}"
    return _result(check, ok, detail)


def check_tool_called(check: CheckSpec, ctx: CheckContext) -> CheckResult:
    name = str(check.params["tool"])
    min_times = int(check.params.get("min_times", 1))
    pattern = check.params.get("args_contains")
    entries = [e for e in ctx.tool_log if e.get("tool") == name]
    if pattern is not None:
        regex = re.compile(str(pattern), re.IGNORECASE)
        entries = [e for e in entries if regex.search(json.dumps(e.get("args", {}), ensure_ascii=False))]
    ok = len(entries) >= min_times
    return _result(check, ok, f"{name} 调用 {len(entries)} 次 (>= {min_times})")


# --------------------------------------------------------------------- python
def check_python(check: CheckSpec, ctx: CheckContext) -> CheckResult:
    func_name = str(check.params["func"])
    module = _load_checks_module(ctx.task)
    func: Callable[..., Any] | None = getattr(module, func_name, None)
    if func is None:
        raise AttributeError(f"{ctx.task.checks_module_path} 中找不到 {func_name}()")
    kwargs = check.params.get("args") or {}
    value = func(ctx, **kwargs) if kwargs else func(ctx)
    if isinstance(value, dict):
        passed = bool(value.get("passed"))
        detail = str(value.get("detail", ""))
    elif isinstance(value, tuple) and len(value) == 2:
        passed, detail = bool(value[0]), str(value[1])
    else:
        passed, detail = bool(value), ""
    return _result(check, passed, detail)


HANDLERS: dict[str, Callable[[CheckSpec, CheckContext], CheckResult]] = {
    "file_exists": check_file_exists,
    "file_absent": check_file_absent,
    "dir_exists": check_dir_exists,
    "file_contains": check_file_contains,
    "file_not_contains": check_file_not_contains,
    "file_equals": check_file_equals,
    "file_line_count": check_file_line_count,
    "state_changed": check_state_changed,
    "state_unchanged": check_state_unchanged,
    "shell": check_shell,
    "tool_called": check_tool_called,
    "python": check_python,
}


# ------------------------------------------------------------------- helpers
def _load_checks_module(task):
    path = Path(task.checks_module_path)
    if not path.is_file():
        raise FileNotFoundError(f"任务缺少 checks.py: {path}")
    mtime = path.stat().st_mtime
    cached = _CHECK_CACHE.get(str(path))
    if cached and cached[0] == mtime:
        return cached[1]
    import importlib.util

    module_name = f"agentlab_task_checks_{task.id.replace('-', '_').replace('.', '_')}_{abs(hash(str(path))) % 10**8}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - 极少数环境
        raise ImportError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    # 不把 __pycache__ 写进任务目录：任务包应该是只读数据
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    finally:
        sys.dont_write_bytecode = previous
    _CHECK_CACHE[str(path)] = (mtime, module)
    return module


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").rstrip("\n")


def _flags(raw: object) -> int:
    flags = 0
    for char in str(raw).lower():
        flags |= {"i": re.IGNORECASE, "m": re.MULTILINE, "s": re.DOTALL}.get(char, 0)
    return flags


def _as_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]  # type: ignore[union-attr]


def _matches(rel: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(rel, pattern):
            return True
        prefix = pattern.rstrip("/")
        if prefix and (rel == prefix or rel.startswith(prefix + "/")):
            return True
    return False


def _state_delta(ctx: CheckContext, patterns: list[str]) -> tuple[set[str], set[str]]:
    keys = set(ctx.state_before) | set(ctx.state_after)
    changed: set[str] = set()
    unchanged: set[str] = set()
    for rel in keys:
        if not _matches(rel, patterns):
            continue
        if ctx.state_before.get(rel) != ctx.state_after.get(rel):
            changed.add(rel)
        else:
            unchanged.add(rel)
    return changed, unchanged


def run_check(check: CheckSpec, ctx: CheckContext) -> CheckResult:
    handler = HANDLERS.get(check.kind)
    if handler is None:  # pragma: no cover - 加载期已拦截
        return _result(check, False, f"未知检查项: {check.kind}", severity="error")
    started = time.perf_counter()
    try:
        result = handler(check, ctx)
    except Exception as exc:  # 检查项失败必须可见，不能静默吞掉
        result = _error(check, exc)
    result.detail = f"{result.detail} [{int((time.perf_counter() - started) * 1000)}ms]".strip()
    return result
