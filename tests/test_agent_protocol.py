"""Agent 文本协议测试：真实模型常见的格式漂移必须被正确归一化。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentlab.agents.parsing import parse_action
from agentlab.agents.react import ReActAgent
from agentlab.core.spec import load_task
from agentlab.models.base import ModelResponse


@pytest.mark.parametrize(
    "text,kind",
    [
        ('```json\n{"kind":"shell","args":{"command":"ls"}}\n```', "shell"),
        ('{"kind":"read_file","args":{"path":"a.txt"}}', "read_file"),
        ('<action>{"kind":"list_dir","args":{}}</action>', "list_dir"),
        ('ACTION: {"kind":"finish","args":{"message":"done"}}', "finish"),
        ('{"command":"echo hi"}', "shell"),
        ('{"tool":"search_docs","query":"refund"}', "tool"),
        ('思考一下...\n```json\n{"type":"finish","arguments":{"message":"ok"}}\n```\n结束', "finish"),
    ],
)
def test_parse_action_variants(text, kind):
    action = parse_action(text)
    assert action is not None, text
    assert action.kind == kind


def test_parse_action_rejects_garbage():
    assert parse_action("no action here") is None
    assert parse_action('{"kind":"curl","args":{}}') is None
    assert parse_action("") is None


def test_tool_action_normalizes_nested_args():
    action = parse_action('{"tool":"lookup_order","args":{"order_id":"O-1"}}')
    assert action.kind == "tool"
    assert action.args["name"] == "lookup_order"
    assert action.args["args"] == {"order_id": "O-1"}


class _ScriptedModel:
    name = "fake"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def chat(self, messages, temperature=0.0, max_tokens=None):
        self.calls += 1
        text = self.replies.pop(0) if self.replies else "```json\n{\"kind\":\"finish\",\"args\":{}}\n```"
        return ModelResponse(text=text, prompt_tokens=10, completion_tokens=5, model="fake")


def _task(tmp_path: Path):
    root = tmp_path / "suites" / "unit" / "react-demo"
    root.mkdir(parents=True)
    (root / "task.yaml").write_text(
        """
id: react-demo
name: react demo
category: terminal
prompt: 列目录
max_steps: 4
tools: [shell, list_dir]
verifier:
  checks:
    - name: a
      kind: file_exists
      path: x
""",
        encoding="utf-8",
    )
    return load_task(root)


def test_react_agent_retries_once_on_bad_format(tmp_path):
    model = _ScriptedModel(["这不是 JSON", "```json\n{\"kind\":\"list_dir\",\"args\":{\"path\":\".\"}}\n```"])
    agent = ReActAgent(model, _task(tmp_path))
    action = agent.act("初始观测")
    assert action.kind == "list_dir"
    assert model.calls == 2
    assert agent.usage()["prompt_tokens"] == 20


def test_react_agent_gives_up_after_repeated_format_errors(tmp_path):
    model = _ScriptedModel(["bad", "still bad"])
    agent = ReActAgent(model, _task(tmp_path))
    action = agent.act("观测")
    assert action.kind == "finish"
    assert action.raw == "format_error"
    assert model.calls == 2


def test_react_system_prompt_lists_mock_tools(tmp_path):
    root = tmp_path / "suites" / "unit" / "react-tool"
    root.mkdir(parents=True)
    (root / "task.yaml").write_text(
        """
id: react-tool
name: react tool
category: tools
prompt: 查文档
tools:
  - name: shell
  - name: search_docs
    kind: mock_tool
    description: "搜索内部文档"
    mock:
      - default: "not found"
verifier:
  checks:
    - name: a
      kind: file_exists
      path: x
""",
        encoding="utf-8",
    )
    agent = ReActAgent(_ScriptedModel([]), load_task(root))
    prompt = agent._system_prompt()
    assert "search_docs" in prompt
    assert "搜索内部文档" in prompt
    assert "__TOOL_LINES__" not in prompt
