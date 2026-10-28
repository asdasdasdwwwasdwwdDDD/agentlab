"""任务模式与加载测试。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agentlab.core.registry import Registry, default_suites_dir
from agentlab.core.spec import SpecError, load_task


def _write_task(tmp_path: Path, payload: dict, name: str = "demo-task") -> Path:
    root = tmp_path / name
    root.mkdir()
    (root / "task.yaml").write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return root


BASE = {
    "id": "demo-task",
    "name": "demo",
    "category": "terminal",
    "prompt": "do it",
    "tools": ["shell", "read_file"],
    "verifier": {"checks": [{"name": "a", "kind": "file_exists", "path": "out.txt"}]},
}


def test_tool_shorthand_is_coerced(tmp_path: Path):
    task = load_task(_write_task(tmp_path, BASE))
    assert task.spec.tool_names == ["shell", "read_file"]
    assert task.spec.get_tool("shell").kind == "builtin"


def test_tools_full_form_mock(tmp_path: Path):
    payload = {
        **BASE,
        "tools": [
            {"name": "shell"},
            {
                "name": "search_docs",
                "kind": "mock_tool",
                "description": "doc search",
                "mock": [{"match": "refund", "response": "7 days"}, {"default": "not found"}],
            },
        ],
    }
    task = load_task(_write_task(tmp_path, payload))
    tool = task.spec.get_tool("search_docs")
    assert tool is not None and tool.kind == "mock_tool"
    assert tool.respond("refund policy") == "7 days"
    assert tool.respond("unknown") == "not found"


def test_dir_name_must_match_id(tmp_path: Path):
    root = _write_task(tmp_path, BASE, name="other-name")
    with pytest.raises(SpecError, match="必须与目录名"):
        load_task(root)


def test_unknown_field_is_rejected(tmp_path: Path):
    payload = {**BASE, "max_step": 5}  # 拼写错误
    with pytest.raises(SpecError, match="max_step"):
        load_task(_write_task(tmp_path, payload))


def test_unknown_check_kind_rejected(tmp_path: Path):
    payload = {**BASE, "verifier": {"checks": [{"name": "a", "kind": "magic_check"}]}}
    with pytest.raises(SpecError, match="未知检查项"):
        load_task(_write_task(tmp_path, payload))


def test_faults_only_allowed_for_rebound(tmp_path: Path):
    payload = {
        **BASE,
        "faults": [{"at_step": 1, "axis": "fault", "kind": "delete_file", "path": "x"}],
    }
    with pytest.raises(SpecError, match="rebound"):
        load_task(_write_task(tmp_path, payload))


def test_ask_user_requires_ambiguity(tmp_path: Path):
    payload = {**BASE, "tools": ["shell", "ask_user"]}
    with pytest.raises(SpecError, match="ambiguity"):
        load_task(_write_task(tmp_path, payload))


def test_duplicate_check_names_rejected(tmp_path: Path):
    payload = {
        **BASE,
        "verifier": {
            "checks": [
                {"name": "a", "kind": "file_exists", "path": "x"},
                {"name": "a", "kind": "file_exists", "path": "y"},
            ]
        },
    }
    with pytest.raises(SpecError, match="重复"):
        load_task(_write_task(tmp_path, payload))


def test_all_repository_tasks_load_and_are_unique():
    registry = Registry(default_suites_dir()).scan()
    assert not registry.errors, registry.errors
    ids = [t.id for t in registry.all()]
    assert len(ids) == len(set(ids))
    for task in registry.all():
        assert task.spec.verifier.checks
        assert task.spec.solution.actions, f"{task.id} 缺少 oracle solution"


def test_oracle_tool_calls_consistent_with_solution():
    registry = Registry(default_suites_dir()).scan()
    for task in registry.all():
        used = sum(1 for a in task.spec.solution_actions() if a.kind in ("shell", "tool"))
        if used and task.spec.budget.oracle_tool_calls != used:
            pytest.fail(f"{task.id}: oracle_tool_calls={task.spec.budget.oracle_tool_calls} 但 solution 用了 {used}")


def test_fingerprint_stable_and_content_sensitive(tmp_path: Path):
    task = load_task(_write_task(tmp_path, BASE))
    before = task.spec.fingerprint()
    assert before == task.spec.fingerprint()
    data = yaml.safe_load((task.root / "task.yaml").read_text(encoding="utf-8"))
    data["prompt"] = "do it differently"
    (task.root / "task.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert load_task(task.root).spec.fingerprint() != before
