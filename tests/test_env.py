"""环境、动作与扰动注入测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentlab.core.spec import load_task
from agentlab.core.types import Action
from agentlab.envs.base import EnvConfig
from agentlab.envs.shell import ShellEnv
from agentlab.envs.fsutil import PathEscapeError, safe_resolve


@pytest.fixture()
def task(tmp_path: Path):
    root = tmp_path / "suites" / "unit" / "env-demo"
    root.mkdir(parents=True)
    (root / "task.yaml").write_text(
        """
id: env-demo
name: env demo
category: terminal
prompt: demo
max_steps: 6
tools: [shell, read_file, write_file, list_dir]
workspace:
  files:
    data/note.txt: |
      hello
verifier:
  checks:
    - name: exists
      kind: file_exists
      path: out.txt
""",
        encoding="utf-8",
    )
    return load_task(root)


def make_env(task, tmp_path: Path, **kwargs) -> ShellEnv:
    workspace = tmp_path / "ws"
    env = ShellEnv(task, workspace, EnvConfig(**kwargs))
    env.reset()
    return env


def test_reset_writes_workspace_files(task, tmp_path: Path):
    env = make_env(task, tmp_path)
    assert (env.workspace / "data" / "note.txt").read_text(encoding="utf-8").strip() == "hello"
    assert "data/note.txt" in env.snapshot_before


def test_shell_action_and_exit_code(task, tmp_path: Path):
    env = make_env(task, tmp_path)
    result = env.step(Action(kind="shell", args={"command": "python -c \"print(40+2)\""}))
    assert result.info["exit_code"] == 0
    assert "42" in result.observation.text
    assert not result.done


def test_shell_failure_observation(task, tmp_path: Path):
    env = make_env(task, tmp_path)
    result = env.step(Action(kind="shell", args={"command": "python -c \"raise SystemExit(3)\""}))
    assert result.info["exit_code"] == 3
    assert "exit_code: 3" in result.observation.text


def test_read_write_list_and_escape(task, tmp_path: Path):
    env = make_env(task, tmp_path)
    env.step(Action(kind="write_file", args={"path": "out/x.txt", "content": "abc"}))
    read = env.step(Action(kind="read_file", args={"path": "out/x.txt"}))
    assert "abc" in read.observation.text
    listed = env.step(Action(kind="list_dir", args={"path": "out"}))
    assert "out/x.txt" in listed.observation.text
    with pytest.raises(PathEscapeError):
        safe_resolve(env.workspace, "../escape.txt")
    escaped = env.step(Action(kind="read_file", args={"path": "../../etc/passwd"}))
    assert escaped.info["error"] == "read_failed"


def test_tool_not_declared_is_rejected(task, tmp_path: Path):
    env = make_env(task, tmp_path)
    result = env.step(Action(kind="ask_user", args={"question": "hi"}))
    assert result.info["error"] == "tool_not_available"


def test_finish_and_give_up_end_episode(task, tmp_path: Path):
    env = make_env(task, tmp_path)
    assert env.step(Action(kind="finish", args={"message": "done"})).done
    assert env.step(Action(kind="give_up", args={"reason": "stuck"})).done


def test_mock_tool_response_and_effect(tmp_path: Path):
    root = tmp_path / "suites" / "unit" / "tool-demo"
    root.mkdir(parents=True)
    (root / "task.yaml").write_text(
        """
id: tool-demo
name: tool demo
category: tools
prompt: demo
tools:
  - name: shell
  - name: search_docs
    kind: mock_tool
    mock:
      - match: "refund|退款"
        response: "7 天内可退"
      - default: "未找到"
  - name: create_ticket
    kind: mock_tool
    mock:
      - default: "ticket-42"
    effect: {ticket_id: "ticket-42"}
verifier:
  checks:
    - name: a
      kind: file_exists
      path: x
""",
        encoding="utf-8",
    )
    task = load_task(root)
    env = make_env(task, tmp_path)
    env.step(Action(kind="tool", args={"name": "search_docs", "args": {"query": "退款政策"}}))
    env.step(Action(kind="tool", args={"name": "create_ticket", "args": {"title": "x"}}))
    assert env.tool_log[0]["response"] == "7 天内可退"
    assert env.state["ticket_id"] == "ticket-42"
    assert env.n_tool_calls == 2


def test_ask_user_budget_and_useful(tmp_path: Path):
    root = tmp_path / "suites" / "unit" / "ask-demo"
    root.mkdir(parents=True)
    (root / "task.yaml").write_text(
        """
id: ask-demo
name: ask demo
category: rebound
prompt: demo
tools: [shell, ask_user]
ambiguity:
  clarification_budget: 1
  required_clarifications: 1
  answers:
    - match: "端口|port"
      reply: "8443"
    - default: "不知道"
verifier:
  checks:
    - name: a
      kind: file_exists
      path: x
""",
        encoding="utf-8",
    )
    task = load_task(root)
    env = make_env(task, tmp_path)
    first = env.step(Action(kind="ask_user", args={"question": "端口是多少"}))
    assert first.info["useful"] is True
    assert "8443" in first.observation.text
    second = env.step(Action(kind="ask_user", args={"question": "端口再说一次"}))
    assert second.info["useful"] is False
    assert "用尽" in second.observation.text
    assert env.useful_clarifications == 1


def test_block_command_fault_fires_once(tmp_path: Path):
    root = tmp_path / "suites" / "unit" / "fault-demo"
    root.mkdir(parents=True)
    (root / "task.yaml").write_text(
        """
id: fault-demo
name: fault demo
category: rebound
prompt: demo
max_steps: 5
tools: [shell]
faults:
  - at_step: 0
    axis: fault
    kind: block_command
    match: "python"
    note: "瞬时故障，可重试"
verifier:
  checks:
    - name: a
      kind: file_exists
      path: x
""",
        encoding="utf-8",
    )
    task = load_task(root)
    env = make_env(task, tmp_path)
    first = env.step(Action(kind="shell", args={"command": "python -c \"print(1)\""}))
    assert first.info["exit_code"] == 1 and first.info["injected"] is True
    second = env.step(Action(kind="shell", args={"command": "python -c \"print(1)\""}))
    assert second.info["exit_code"] == 0
    assert len(env.fault_events) == 1


def test_drift_delete_is_silent(tmp_path: Path):
    root = tmp_path / "suites" / "unit" / "drift-demo"
    root.mkdir(parents=True)
    (root / "task.yaml").write_text(
        """
id: drift-demo
name: drift demo
category: rebound
prompt: demo
workspace:
  files:
    cfg.ini: "port=1"
tools: [shell, read_file]
faults:
  - at_step: 1
    axis: drift
    kind: drift_delete
    path: cfg.ini
    announce: false
    note: "外部删除"
verifier:
  checks:
    - name: a
      kind: file_exists
      path: x
""",
        encoding="utf-8",
    )
    task = load_task(root)
    env = make_env(task, tmp_path)
    env.step(Action(kind="read_file", args={"path": "cfg.ini"}))
    result = env.step(Action(kind="read_file", args={"path": "cfg.ini"}))
    assert "读取失败" in result.observation.text
    assert "外部删除" not in result.observation.text  # silent
    assert env.fault_events[0].kind == "drift_delete"
