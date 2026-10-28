"""RL 环境接口测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentlab.agents.scripted import ScriptedAgent
from agentlab.core.registry import Registry, default_suites_dir
from agentlab.core.types import Action
from agentlab.rl.env import AgentEnv


def get_task(task_id: str):
    registry = Registry(default_suites_dir()).scan()
    return registry.get(task_id)


def test_terminal_reward_and_rollout(tmp_path: Path):
    task = get_task("rb-budget-oneshot")
    env = AgentEnv(task, tmp_path / "ws", reward_mode="terminal")
    record = env.rollout(ScriptedAgent(task, policy="oracle"))
    assert record["success"] is True
    assert record["score"] == 1.0
    assert record["total_reward"] == pytest.approx(1.0, abs=1e-6)
    assert record["n_tool_calls"] == 1
    assert len(record["transitions"]) == 2
    env.close()


def test_shaped_reward_penalizes_steps(tmp_path: Path):
    task = get_task("rb-budget-oneshot")
    env = AgentEnv(task, tmp_path / "ws", reward_mode="shaped", step_cost=0.05)
    record = env.rollout(ScriptedAgent(task, policy="oracle"))
    assert record["success"] is True
    assert record["total_reward"] == pytest.approx(1.0 - 0.05 * record["n_steps"], abs=1e-6)


def test_binary_reward(tmp_path: Path):
    task = get_task("rb-ambiguity-port")
    env = AgentEnv(task, tmp_path / "ws", reward_mode="binary")
    record = env.rollout(ScriptedAgent(task, policy="oracle"))
    assert record["success"] and record["total_reward"] == 1.0


def test_truncation_at_max_steps(tmp_path: Path):
    task = get_task("rb-fault-retry")
    env = AgentEnv(task, tmp_path / "ws", reward_mode="terminal", max_steps=2)
    env.reset()
    env.step(Action(kind="shell", args={"command": "echo one"}))
    _, _, terminated, truncated, _ = env.step(Action(kind="shell", args={"command": "echo two"}))
    assert terminated is False and truncated is True
    assert env.verdict is not None
    with pytest.raises(RuntimeError):
        env.step(Action(kind="shell", args={"command": "echo three"}))


def test_invalid_reward_mode(tmp_path: Path):
    task = get_task("rb-budget-oneshot")
    with pytest.raises(ValueError):
        AgentEnv(task, tmp_path / "ws", reward_mode="dense")


def test_silent_policy_fails_ambiguity_but_not_content(tmp_path: Path):
    task = get_task("rb-ambiguity-port")
    env = AgentEnv(task, tmp_path / "ws", reward_mode="terminal")
    record = env.rollout(ScriptedAgent(task, policy="silent"))
    assert record["success"] is False
    failed = [c["name"] for c in record["verdict"]["checks"] if not c["passed"]]
    assert "clarification_done" in failed
    assert "manifest_content" not in failed
