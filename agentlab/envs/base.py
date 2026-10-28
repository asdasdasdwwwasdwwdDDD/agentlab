"""环境协议与共用配置。"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from agentlab.core.spec import LoadedTask
from agentlab.core.types import Action, Observation, StepResult


@dataclass
class EnvConfig:
    """环境执行配置。测试可以注入自定义 shell 以验证跨平台差异。"""

    shell_argv: tuple[str, ...] | None = None
    output_head: int = 6000
    output_tail: int = 6000
    read_max_bytes: int = 12000
    command_timeout_s: float | None = None
    extra_env: dict[str, str] = field(default_factory=dict)

    def resolved_shell_argv(self) -> tuple[str, ...]:
        if self.shell_argv:
            return self.shell_argv
        return default_shell_argv()


def default_shell_argv() -> tuple[str, ...]:
    """Windows 优先 pwsh；POSIX 用 /bin/sh。返回 argv 前缀，命令追加在末尾。"""
    import os

    if os.name == "nt":
        for name in ("pwsh", "powershell"):
            exe = shutil.which(name)
            if exe:
                return (exe, "-NoProfile", "-NonInteractive", "-Command")
        return (os.environ.get("COMSPEC", "cmd.exe"), "/c")
    return ("/bin/sh", "-c")


def wrap_shell_command(shell_argv: tuple[str, ...], command: str) -> str:
    """PowerShell 的进程退出码不等于最后一条 native 命令的退出码，需要显式透传。"""
    exe = Path(shell_argv[0]).name.lower()
    if "powershell" in exe or exe.startswith("pwsh"):
        return f"{command}\n; exit $LASTEXITCODE"
    return command


class Environment(Protocol):
    """最小环境协议：reset / step / snapshot。

    实现必须保证 `step` 不抛异常（异常需转成失败观测），否则评测无法收尾。
    """

    task: LoadedTask
    workspace: Path
    tool_log: list[dict]
    state: dict

    def reset(self) -> Observation: ...

    def step(self, action: Action) -> StepResult: ...

    def snapshot(self) -> dict[str, str]: ...

    def close(self) -> None: ...
