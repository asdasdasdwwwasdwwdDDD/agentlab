"""Agent 工厂。"""

from __future__ import annotations

from agentlab.agents.base import Agent
from agentlab.agents.react import ReActAgent
from agentlab.agents.scripted import POLICIES, ScriptedAgent
from agentlab.core.spec import LoadedTask
from agentlab.models import create_model

__all__ = ["Agent", "ReActAgent", "ScriptedAgent", "POLICIES", "build_agent"]


def build_agent(
    spec: str,
    task: LoadedTask,
    model: str = "mock",
    policy: str = "oracle",
    noise: float = 0.0,
    seed: int = 0,
    temperature: float = 0.0,
) -> Agent:
    """spec: oracle | scripted[:policy] | react。"""
    spec = (spec or "oracle").strip().lower()
    if spec == "oracle":
        return ScriptedAgent(task, policy="oracle", noise=noise, seed=seed)
    if spec.startswith("scripted"):
        if ":" in spec:
            policy = spec.split(":", 1)[1]
        return ScriptedAgent(task, policy=policy, noise=noise, seed=seed)
    if spec == "react":
        client = create_model(model, plan=task.spec.solution_actions(), noise=noise, seed=seed)
        return ReActAgent(client, task, temperature=temperature)
    raise ValueError(f"未知 agent {spec!r}（可选 oracle / scripted[:policy] / react）")
