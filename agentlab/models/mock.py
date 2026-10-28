"""MockModel：无 API key 也能跑通整条 pipeline 的确定性模型。

它把任务 `solution.actions` 当作"剧本"逐步吐出来，可选注入噪声来模拟不同能力档位。
**结论仅用于验证 harness 能区分行为，不能代表任何真实模型的能力。**
"""

from __future__ import annotations

import json
import random

from agentlab.core.types import Action
from agentlab.models.base import ModelResponse, ModelClient


class MockModel:
    def __init__(self, plan: list[Action], noise: float = 0.0, seed: int = 0, name: str = "mock"):
        self.plan = list(plan)
        self.noise = max(0.0, min(1.0, float(noise)))
        self.rng = random.Random(seed)
        self.name = name
        self._idx = 0

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        action = self._next_action()
        text = "```json\n" + json.dumps({"kind": action.kind, "args": action.args}, ensure_ascii=False) + "\n```"
        prompt_chars = sum(len(m.get("content", "")) for m in messages)
        return ModelResponse(
            text=text,
            prompt_tokens=max(1, prompt_chars // 4),
            completion_tokens=max(1, len(text) // 4),
            cost_usd=0.0,
            model="mock",
        )

    def _next_action(self) -> Action:
        if self._idx >= len(self.plan):
            return Action(kind="finish", args={"message": "（mock）剧本已执行完毕"})
        action = self.plan[self._idx]
        self._idx += 1
        if self.noise > 0 and self.rng.random() < self.noise:
            if self.rng.random() < 0.5:
                # 行为噪声 1：漏做一步
                return self._next_action()
            # 行为噪声 2：把动作替换成无效命令
            return Action(kind="shell", args={"command": "echo mock-noise"}, raw="noise")
        return action


def create_mock_model(plan: list[Action], noise: float = 0.0, seed: int = 0) -> ModelClient:
    return MockModel(plan=plan, noise=noise, seed=seed)
