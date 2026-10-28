"""ShellEnv：临时工作区 + 子进程终端 + mock 工具。

安全边界：`local` backend 直接在宿主机子进程里执行命令，只适合运行自己编写的任务与
mock agent。接入真实模型时请换容器化 backend（见 docs/DESIGN.md §11）。
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from agentlab.core.spec import LoadedTask
from agentlab.core.types import Action, FaultEvent, Observation, StepResult
from agentlab.envs.base import EnvConfig, wrap_shell_command
from agentlab.envs.faults import FaultInjector
from agentlab.envs.fsutil import (
    PathEscapeError,
    copy_tree,
    list_tree,
    read_text,
    snapshot,
    write_text,
)

SHELL_LIKE_ACTIONS = {"shell", "tool"}


class ShellEnv:
    """一个 episode 一个 workspace，状态由文件系统承载（可快照、可判分）。"""

    def __init__(self, task: LoadedTask, workspace: Path, config: EnvConfig | None = None):
        self.task = task
        self.workspace = Path(workspace)
        self.config = config or EnvConfig()
        self.faults = FaultInjector(task.spec.faults)
        self.tool_log: list[dict[str, Any]] = []
        self.state: dict[str, Any] = {}
        self.step_index = 0
        self.n_tool_calls = 0
        self.clarifications = 0
        self.useful_clarifications = 0
        self.fault_events: list[FaultEvent] = []
        self.snapshot_before: dict[str, str] = {}
        self._closed = False
        self._shell_argv = self.config.resolved_shell_argv()

    # ------------------------------------------------------------------ reset
    def reset(self) -> Observation:
        self.workspace.mkdir(parents=True, exist_ok=True)
        spec = self.task.spec
        if spec.workspace.copy_files:
            copy_tree(self.task.root / "files", self.workspace)
        for rel, content in spec.workspace.files.items():
            write_text(self.workspace, rel, content)
        self.snapshot_before = snapshot(self.workspace)
        files = list_tree(self.workspace, ".", limit=100)
        listing = "\n".join(f"- {f}" for f in files) if files else "（空目录）"
        text = (
            f"workspace 已就绪（{self.task.id}）。\n"
            f"初始文件:\n{listing}\n\n"
            f"可用动作: {', '.join(spec.tool_names)}\n"
            f"所有相对路径都相对于 workspace 根目录。"
        )
        return Observation(text=text, data={"files": files, "state_before": dict(self.snapshot_before)})

    # ------------------------------------------------------------------- step
    def step(self, action: Action) -> StepResult:
        started = time.perf_counter()
        idx = self.step_index
        self.step_index += 1

        events, messages = self.faults.apply_files(idx, self.workspace)
        self.fault_events.extend(events)

        allowed = (
            action.kind in ("finish", "give_up")
            or action.kind in self.task.spec.tool_names
            or (action.kind == "tool" and any(t.kind == "mock_tool" for t in self.task.spec.tools))
        )
        if not allowed:
            result = StepResult(
                observation=Observation(text=f"[错误] 动作 {action.kind!r} 不在本任务可用工具中: {self.task.spec.tool_names}"),
                info={"error": "tool_not_available"},
            )
        else:
            handler = getattr(self, f"_act_{action.kind}", None)
            if handler is None:
                result = StepResult(observation=Observation(text=f"[错误] 不支持的动作: {action.kind}"), info={"error": "bad_action"})
            else:
                try:
                    result = handler(action)
                except Exception as exc:  # 环境内部错误也不能中断整批判分
                    result = StepResult(
                        observation=Observation(text=f"[环境错误] {type(exc).__name__}: {exc}"),
                        info={"error": "env_exception", "exception": type(exc).__name__},
                    )

        if messages:
            prefix = "\n".join(messages)
            result.observation = Observation(
                text=f"{prefix}\n\n{result.observation.text}",
                data={**result.observation.data, "fault_messages": messages},
            )
            result.info.setdefault("faults", []).extend([e.to_dict() for e in events])
        if action.kind in SHELL_LIKE_ACTIONS:
            self.n_tool_calls += 1
        result.info.setdefault("elapsed_ms", int((time.perf_counter() - started) * 1000))
        return result

    # ---------------------------------------------------------------- helpers
    def snapshot(self) -> dict[str, str]:
        return snapshot(self.workspace)

    def close(self) -> None:
        self._closed = True

    def _read(self, rel: str) -> str:
        return read_text(self.workspace, rel, max_bytes=self.config.read_max_bytes)

    def _elide(self, text: str) -> str:
        head, tail = self.config.output_head, self.config.output_tail
        if len(text) <= head + tail:
            return text
        omitted = len(text) - head - tail
        return f"{text[:head]}\n...[省略 {omitted} 字符]...\n{text[-tail:]}"

    def _run(self, command: str, timeout_s: float | None = None) -> dict[str, Any]:
        timeout = timeout_s or self.config.command_timeout_s or self.task.spec.timeout_s
        argv = [*self._shell_argv, wrap_shell_command(tuple(self._shell_argv), command)]
        env = dict(os.environ)
        env.update(
            {
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "AGENTLAB_WORKSPACE": str(self.workspace),
            }
        )
        env.update(self.config.extra_env)
        started = time.perf_counter()
        try:
            proc = subprocess.run(
                argv,
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=env,
            )
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout or "",
                "stderr": proc.stderr or "",
                "timeout": False,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "exit_code": -1,
                "stdout": _as_text(exc.stdout),
                "stderr": f"[timeout] 命令超过 {timeout:g}s",
                "timeout": True,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            }

    # --------------------------------------------------------------- handlers
    def _act_shell(self, action: Action) -> StepResult:
        command = str(action.args.get("command", "")).strip()
        if not command:
            return StepResult(observation=Observation(text="[错误] shell 缺少 command"), info={"error": "empty_command"})
        blocked = self.faults.match_block(self.step_index - 1, command)
        if blocked is not None:
            event = FaultEvent(
                at_step=self.step_index - 1,
                axis=blocked.axis,
                kind="block_command",
                note=blocked.note,
                detail={"command": command, "match": blocked.match},
            )
            self.fault_events.append(event)
            message = blocked.note or "命令执行失败（瞬时故障）"
            text = (
                f"$ {command}\n"
                f"exit_code: 1\n"
                f"--- stdout ---\n\n"
                f"--- stderr ---\n[injected] {message}\n"
                + ("\n（提示：这是可以重试的瞬时故障）" if blocked.announce else "")
            )
            return StepResult(observation=Observation(text=text), info={"exit_code": 1, "injected": True})
        result = self._run(command)
        stdout, stderr = self._elide(result["stdout"]), self._elide(result["stderr"])
        text = (
            f"$ {command}\n"
            f"exit_code: {result['exit_code']}\n"
            f"--- stdout ---\n{stdout.rstrip()}\n"
            f"--- stderr ---\n{stderr.rstrip()}"
        )
        return StepResult(
            observation=Observation(text=text, data={"exit_code": result["exit_code"]}),
            info={
                "exit_code": result["exit_code"],
                "timeout": result["timeout"],
                "duration_ms": result["duration_ms"],
                "command": command,
            },
        )

    def _act_read_file(self, action: Action) -> StepResult:
        rel = str(action.args.get("path", ""))
        try:
            content = self._read(rel)
        except (PathEscapeError, FileNotFoundError, IsADirectoryError) as exc:
            return StepResult(observation=Observation(text=f"[读取失败] {rel}: {exc}"), info={"error": "read_failed"})
        return StepResult(
            observation=Observation(text=f"read_file {rel}:\n{content}"),
            info={"path": rel, "bytes": len(content)},
        )

    def _act_write_file(self, action: Action) -> StepResult:
        rel = str(action.args.get("path", ""))
        content = action.args.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False, indent=2)
        try:
            path = write_text(self.workspace, rel, content)
        except (PathEscapeError, OSError) as exc:
            return StepResult(observation=Observation(text=f"[写入失败] {rel}: {exc}"), info={"error": "write_failed"})
        rel_path = path.relative_to(self.workspace).as_posix()
        return StepResult(
            observation=Observation(text=f"write_file {rel_path}: 已写入 {len(content)} 字符"),
            info={"path": rel_path, "bytes": len(content)},
        )

    def _act_list_dir(self, action: Action) -> StepResult:
        rel = str(action.args.get("path", ".") or ".")
        try:
            entries = list_tree(self.workspace, rel)
        except (PathEscapeError, FileNotFoundError) as exc:
            return StepResult(observation=Observation(text=f"[列目录失败] {rel}: {exc}"), info={"error": "list_failed"})
        body = "\n".join(entries) if entries else "（空）"
        return StepResult(observation=Observation(text=f"list_dir {rel}:\n{body}"), info={"path": rel, "count": len(entries)})

    def _act_ask_user(self, action: Action) -> StepResult:
        ambiguity = self.task.spec.ambiguity
        if ambiguity is None:
            return StepResult(observation=Observation(text="[错误] 本任务不支持向用户提问"), info={"error": "no_ambiguity"})
        question = str(action.args.get("question", "")).strip()
        if not question:
            return StepResult(observation=Observation(text="[错误] ask_user 缺少 question"), info={"error": "empty_question"})
        self.clarifications += 1
        self.tool_log.append({"tool": "ask_user", "args": {"question": question}, "step": self.step_index - 1})
        if self.clarifications > ambiguity.clarification_budget:
            reply, useful = "（澄清次数已用尽，无法继续提供信息）", False
        else:
            reply, useful = ambiguity.respond(question)
        if useful:
            self.useful_clarifications += 1
        return StepResult(
            observation=Observation(text=f"user: {reply}"),
            info={"useful": useful, "clarifications": self.clarifications},
        )

    def _act_tool(self, action: Action) -> StepResult:
        name = str(action.args.get("name", "")).strip()
        tool = self.task.spec.get_tool(name)
        if tool is None:
            return StepResult(observation=Observation(text=f"[错误] 未知工具: {name}"), info={"error": "unknown_tool"})
        if tool.kind != "mock_tool":
            return StepResult(
                observation=Observation(text=f"[错误] 工具 {name} 不是 mock_tool，请直接使用对应动作"),
                info={"error": "not_mock_tool"},
            )
        args = action.args.get("args") or {}
        if not isinstance(args, dict):
            args = {"value": args}
        args_text = json.dumps(args, ensure_ascii=False)
        response = tool.respond(args_text)
        entry: dict[str, Any] = {"tool": name, "args": args, "response": response, "step": self.step_index - 1}
        if tool.effect:
            entry["effect"] = dict(tool.effect)
            self.state.update(tool.effect)
        self.tool_log.append(entry)
        return StepResult(observation=Observation(text=f"tool {name} -> {response}"), info={"tool": name})

    def _act_finish(self, action: Action) -> StepResult:
        message = str(action.args.get("message", "") or "")
        return StepResult(observation=Observation(text="任务结束。"), done=True, info={"finish": message})

    def _act_give_up(self, action: Action) -> StepResult:
        reason = str(action.args.get("reason", "") or "")
        return StepResult(observation=Observation(text="已放弃任务。"), done=True, info={"gave_up": True, "reason": reason})


# 语义别名：挂载 mock 工具的环境。
ToolEnv = ShellEnv


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
