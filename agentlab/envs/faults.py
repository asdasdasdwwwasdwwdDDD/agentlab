"""扰动注入：fault（需要恢复）与 drift（需要重新观察）。

设计要点：
- 触发时机是 "第 N 步执行之前"，与 agent 的动作无关，保证不同策略可比。
- `announce=True` 的扰动通过 observation 可见（相当于环境报错）；`announce=False` 的
  drift 静默发生，只有主动重新读取的 agent 才能发现。
- `block_command` 每个 fault 只触发一次：agent 重试即可恢复，这是最干净的恢复信号。
"""

from __future__ import annotations

import re
from pathlib import Path

from agentlab.core.spec import FaultSpec
from agentlab.core.types import FaultEvent
from agentlab.envs.fsutil import safe_resolve


class FaultInjector:
    def __init__(self, faults: list[FaultSpec] | None = None):
        self.faults = list(faults or [])
        self._consumed: set[int] = set()

    @property
    def total(self) -> int:
        return len(self.faults)

    def pending(self, step_idx: int) -> list[tuple[int, FaultSpec]]:
        out = []
        for idx, fault in enumerate(self.faults):
            if idx in self._consumed:
                continue
            if fault.at_step <= step_idx:
                out.append((idx, fault))
        return out

    def apply_files(self, step_idx: int, workspace: Path) -> tuple[list[FaultEvent], list[str]]:
        """应用所有到期的文件类扰动，返回事件与需要展示给 agent 的消息。"""
        events: list[FaultEvent] = []
        messages: list[str] = []
        for idx, fault in self.pending(step_idx):
            if fault.kind == "block_command":
                continue
            self._consumed.add(idx)
            target = safe_resolve(workspace, fault.path or "")
            detail = {"path": fault.path}
            try:
                if fault.kind == "delete_file":
                    if target.exists():
                        target.unlink()
                        detail["existed"] = True
                    else:
                        detail["existed"] = False
                elif fault.kind in ("write_file", "drift_write"):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(fault.content or "", encoding="utf-8", newline="\n")
                elif fault.kind == "append_file":
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with open(target, "a", encoding="utf-8", newline="\n") as handle:
                        handle.write(fault.content or "")
                elif fault.kind == "corrupt_file":
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(fault.content or "", encoding="utf-8", newline="\n")
                elif fault.kind == "drift_delete":
                    if target.exists():
                        target.unlink()
                        detail["existed"] = True
                elif fault.kind == "remove_file_pattern":
                    pattern = re.compile(fault.match or r".*")
                    removed = []
                    for path in sorted(workspace.rglob("*")):
                        if path.is_file() and pattern.search(path.relative_to(workspace).as_posix()):
                            path.unlink()
                            removed.append(path.relative_to(workspace).as_posix())
                    detail["removed"] = removed
            except OSError as exc:  # 扰动失败不应打断评测，但要可见
                detail["error"] = str(exc)
                events.append(
                    FaultEvent(at_step=step_idx, axis=fault.axis, kind=fault.kind, note=f"注入失败: {exc}", detail=detail)
                )
                continue
            events.append(
                FaultEvent(
                    at_step=step_idx,
                    axis=fault.axis,
                    kind=fault.kind,
                    note=fault.note,
                    detail=detail,
                )
            )
            if fault.announce:
                label = "环境变化" if fault.axis == "drift" else "故障注入"
                messages.append(f"[{label}] {fault.note or fault.kind}（{fault.path or fault.match or ''}）")
        return events, messages

    def match_block(self, step_idx: int, command: str) -> FaultSpec | None:
        """命令级故障：命中即消费，返回 None 表示放行。"""
        for idx, fault in self.pending(step_idx):
            if fault.kind != "block_command" or not fault.match:
                continue
            if re.search(fault.match, command):
                self._consumed.add(idx)
                return fault
        return None
