"""RL 环境封装：把「可交互 workspace + 确定性 verifier」变成可采样的 reward 环境。

设计动机（对应岗位职责 3）：
- 评测与训练共用同一个环境/判分器，避免 reward 与 eval 口径漂移；
- 支持三种 reward：稀疏终局（terminal）、进度塑形（shaped）、0/1（binary）；
- 环境步骤成本可配置，用于研究"效率-成功率"权衡与 reward hacking。

注意：
- 这里的 reward 完全由 verifier 的检查项聚合而来，不引入 LLM judge，保证可复现。
- shaped reward 默认跳过 `shell` 类检查（避免每步执行任意命令），只聚合文件/状态/工具检查。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentlab.core.spec import LoadedTask
from agentlab.core.types import Action, Step
from agentlab.envs.base import EnvConfig
from agentlab.envs.shell import ShellEnv
from agentlab.verifiers.grader import grade

REWARD_MODES = ("terminal", "shaped", "binary")


@dataclass
class Transition:
    step: int
    action: dict[str, Any]
    observation: str
    reward: float
    terminated: bool
    truncated: bool
    info: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "action": self.action,
            "observation": self.observation,
            "reward": round(self.reward, 6),
            "terminated": self.terminated,
            "truncated": self.truncated,
            "info": self.info,
        }


class AgentEnv:
    """Gym 风格接口：reset() / step(action) -> (obs, reward, terminated, truncated, info)。"""

    def __init__(
        self,
        task: LoadedTask,
        workspace: str | Path,
        reward_mode: str = "terminal",
        step_cost: float = 0.0,
        success_bonus: float = 0.0,
        max_steps: int | None = None,
        config: EnvConfig | None = None,
    ):
        if reward_mode not in REWARD_MODES:
            raise ValueError(f"reward_mode 必须是 {REWARD_MODES} 之一")
        self.task = task
        self.reward_mode = reward_mode
        self.step_cost = max(0.0, step_cost)
        self.success_bonus = max(0.0, success_bonus)
        self.max_steps = max_steps or task.spec.max_steps
        self._env = ShellEnv(task, Path(workspace), config)
        self._steps: list[Step] = []
        self._prev_partial = 0.0
        self._verdict = None
        self._done = False
        self._started = False

    # ---------------------------------------------------------------- gym API
    def reset(self) -> str:
        observation = self._env.reset()
        self._steps = []
        self._prev_partial = 0.0
        self._verdict = None
        self._done = False
        self._started = True
        return observation.text

    def step(self, action: Action) -> tuple[str, float, bool, bool, dict[str, Any]]:
        if not self._started:
            raise RuntimeError("调用 reset() 之后才能 step()")
        if self._done:
            raise RuntimeError("episode 已结束，请 reset()")
        result = self._env.step(action)
        step = Step(
            idx=len(self._steps),
            action=action,
            observation=result.observation.text,
            done=result.done,
            reward_hint=result.reward_hint,
            info=dict(result.info),
            t_ms=int(result.info.get("elapsed_ms", 0)),
        )
        self._steps.append(step)
        self._done = result.done or len(self._steps) >= self.max_steps

        reward = -self.step_cost
        info: dict[str, Any] = {
            "step": step.idx,
            "tool_calls": self._env.n_tool_calls,
            "done": result.done,
        }
        if self._done:
            self._verdict = self._grade(full=True)
            success = bool(self._verdict.success)
            if self.reward_mode == "binary":
                reward = (1.0 if success else 0.0) - self.step_cost
            elif self.reward_mode == "shaped":
                # shaped 模式只补发"剩余进度"，避免与中间过程奖励重复计算
                target = self._verdict.score + (self.success_bonus if success else 0.0)
                reward = (target - self._prev_partial) - self.step_cost
                self._prev_partial = max(self._prev_partial, target)
            else:
                reward = self._verdict.score + (self.success_bonus if success else 0.0) - self.step_cost
            info["verdict"] = self._verdict.to_dict()
            info["success"] = success
        elif self.reward_mode == "shaped":
            partial = self._grade(full=False).score
            reward += max(0.0, partial - self._prev_partial)
            self._prev_partial = max(self._prev_partial, partial)
            info["partial_score"] = partial
        return result.observation.text, float(reward), result.done, bool(self._done and not result.done), info

    # ---------------------------------------------------------------- rollout
    def rollout(self, agent, record_observations: bool = True) -> dict[str, Any]:
        """用给定 Agent（需有 act(observation)）跑完一个 episode，返回可落盘的数据。"""
        started = time.perf_counter()
        observation = self.reset()
        transitions: list[Transition] = []
        total_reward = 0.0
        terminated = truncated = False
        while not (terminated or truncated):
            action = agent.act(observation)
            observation, reward, terminated, truncated, info = self.step(action)
            total_reward += reward
            transitions.append(
                Transition(
                    step=len(transitions),
                    action=action.to_dict() if hasattr(action, "to_dict") else dict(action),
                    observation=observation if record_observations else "",
                    reward=reward,
                    terminated=terminated,
                    truncated=truncated,
                    info=info,
                )
            )
            if len(transitions) > self.max_steps + 1:  # 防御性上界
                break
        success = bool(self._verdict and self._verdict.success)
        return {
            "task_id": self.task.id,
            "suite": self.task.suite,
            "reward_mode": self.reward_mode,
            "agent": getattr(agent, "name", type(agent).__name__),
            "transitions": [t.to_dict() for t in transitions],
            "total_reward": round(total_reward, 6),
            "success": success,
            "score": self._verdict.score if self._verdict else 0.0,
            "verdict": self._verdict.to_dict() if self._verdict else None,
            "n_steps": len(transitions),
            "n_tool_calls": self._env.n_tool_calls,
            "faults": [f.to_dict() for f in self._env.fault_events],
            "clarifications": self._env.clarifications,
            "wall_ms": int((time.perf_counter() - started) * 1000),
        }

    # ---------------------------------------------------------------- helpers
    def _grade(self, full: bool):
        verdict = grade(
            task=self.task,
            workspace=self._env.workspace,
            state_before=self._env.snapshot_before,
            state_after=self._env.snapshot(),
            tool_log=self._env.tool_log,
            actions=[s.action for s in self._steps],
            meta={
                "state": dict(self._env.state),
                "clarifications": self._env.clarifications,
                "useful_clarifications": self._env.useful_clarifications,
            },
            skip_kinds=frozenset() if full else frozenset({"shell"}),
        )
        return verdict

    @property
    def verdict(self):
        return self._verdict

    def close(self) -> None:
        self._env.close()

    def render(self) -> str:
        return f"step={len(self._steps)} tool_calls={self._env.n_tool_calls} workspace={self._env.workspace}"
