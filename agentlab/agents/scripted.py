"""脚本化 Agent：用任务的 solution 当剧本，模拟不同能力档位。

用途：
1. `validate` 用 oracle 证明任务可解、判分无假阴性。
2. `early_stop` / `fragile` / `retry` 用于消融，测量同一个任务上"没做完 / 不重试 / 会重试"
   三种行为的得分差 —— 这是 REBOUND-Bench 恢复率指标的自检基线。

**synthetic**：分数只反映 harness 的区分度，不代表任何模型能力。
"""

from __future__ import annotations

import json
import random

from agentlab.core.types import Action, Step
from agentlab.core.spec import LoadedTask

POLICIES = ("oracle", "early_stop", "fragile", "retry", "silent")

_FAIL_MARKERS = ("exit_code: 1", "[injected]", "[环境错误]", "Traceback (most recent call last)")


class ScriptedAgent:
    def __init__(self, task: LoadedTask, policy: str = "oracle", noise: float = 0.0, seed: int = 0):
        if policy not in POLICIES:
            raise ValueError(f"未知 scripted policy {policy!r}，可选 {POLICIES}")
        self.task = task
        self.policy = policy
        self.plan = task.spec.solution_actions()
        self.noise = max(0.0, min(1.0, float(noise)))
        self.rng = random.Random(seed)
        self._idx = 0
        self._retries = 0
        self._last_action: Action | None = None
        self._last_failed = False
        self._cutoff = next(
            (idx for idx in range(len(self.plan) - 1, -1, -1) if self.plan[idx].kind not in ("finish", "give_up")),
            -1,
        )
        self.name = f"scripted/{policy}"
        self.model_name = "mock"

    def act(self, observation: str) -> Action:
        self._last_failed = self._saw_failure(observation)

        if self.policy == "fragile" and self._last_failed:
            return Action(kind="give_up", args={"reason": "环境报错，放弃"})

        if self.policy == "retry" and self._last_failed and self._last_action is not None and self._retries < 3:
            self._retries += 1
            return Action.from_dict(self._last_action.to_dict())

        if self.policy == "early_stop" and self._idx >= self._cutoff:
            return Action(kind="finish", args={"message": "先这样，交卷"})

        if self.noise > 0 and self.rng.random() < self.noise:
            if self.rng.random() < 0.5 and self._idx + 1 < len(self.plan):
                self._idx += 1  # 漏做一步
            else:
                return Action(kind="shell", args={"command": "echo noise"})

        action = self._take_next()
        if action is not None:
            return action
        return Action(kind="finish", args={"message": "任务完成"})

    def _take_next(self) -> Action | None:
        """silent 策略跳过 ask_user（模拟"不敢问、直接猜"的 agent）。"""
        while self._idx < len(self.plan):
            action = self.plan[self._idx]
            self._idx += 1
            if self.policy == "silent" and action.kind == "ask_user":
                continue
            self._last_action = action
            return action
        return None

    def observe(self, step: Step) -> None:
        return None

    def usage(self) -> dict[str, float]:
        return {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}

    @staticmethod
    def _saw_failure(observation: str) -> bool:
        return any(marker in observation for marker in _FAIL_MARKERS)


def plan_action_keys(task: LoadedTask) -> list[str]:
    return [json.dumps(a.to_dict(), sort_keys=True) for a in task.spec.solution_actions()]
