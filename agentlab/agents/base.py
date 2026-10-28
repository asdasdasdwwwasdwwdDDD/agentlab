"""Agent 协议。"""

from __future__ import annotations

from typing import Protocol

from agentlab.core.types import Action, Step


class Agent(Protocol):
    name: str
    model_name: str

    def act(self, observation: str) -> Action: ...

    def observe(self, step: Step) -> None: ...

    def usage(self) -> dict[str, float]: ...
