"""判分与检查项测试（不需要真实环境）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentlab.core.spec import load_task
from agentlab.core.types import Action
from agentlab.verifiers.grader import grade

CHECKS_PY = '''
import json


def check_json(ctx):
    if not ctx.exists("out.json"):
        return False, "missing"
    data = json.loads(ctx.read("out.json"))
    return data.get("ok") is True, f"ok={data.get('ok')}"


def check_bool_true(ctx):
    return True


def check_explode(ctx):
    raise RuntimeError("boom")
'''


def build_task(tmp_path: Path, checks: list[dict], threshold: float = 1.0):
    root = tmp_path / "suites" / "unit" / "grade-demo"
    root.mkdir(parents=True)
    import yaml

    payload = {
        "id": "grade-demo",
        "name": "grade demo",
        "category": "terminal",
        "prompt": "demo",
        "verifier": {"pass_threshold": threshold, "checks": checks},
    }
    (root / "task.yaml").write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    (root / "checks.py").write_text(CHECKS_PY, encoding="utf-8")
    return load_task(root)


def run_grade(task, workspace: Path, tool_log=None, actions=None, meta=None):
    return grade(
        task=task,
        workspace=workspace,
        state_before={"data.txt": "old", "keep.txt": "same"},
        state_after={"data.txt": "new", "keep.txt": "same"},
        tool_log=tool_log or [],
        actions=actions or [],
        meta=meta or {},
    )


def test_file_checks_and_weighted_score(tmp_path: Path):
    workspace = tmp_path / "ws"
    (workspace / "out").mkdir(parents=True)
    (workspace / "out" / "a.txt").write_text("hello\nworld\n", encoding="utf-8")
    (workspace / "out.json").write_text('{"ok": true}', encoding="utf-8")
    task = build_task(
        tmp_path,
        [
            {"name": "exists", "kind": "file_exists", "path": "out/a.txt"},
            {"name": "contains", "kind": "file_contains", "path": "out/a.txt", "pattern": "wor"},
            {"name": "not_absent", "kind": "file_absent", "path": "out/none.txt"},
            {"name": "python", "kind": "python", "func": "check_json"},
            {"name": "lines", "kind": "file_line_count", "path": "out/a.txt", "min": 2, "max": 3},
        ],
    )
    verdict = run_grade(task, workspace)
    assert verdict.success, verdict.message
    assert verdict.score == 1.0


def test_required_failure_blocks_success(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    task = build_task(
        tmp_path,
        [
            {"name": "missing", "kind": "file_exists", "path": "nope.txt", "weight": 1.0, "required": True},
            {"name": "pass", "kind": "python", "func": "check_bool_true", "weight": 10.0},
        ],
    )
    verdict = run_grade(task, workspace)
    assert not verdict.success
    assert verdict.score == pytest.approx(10 / 11, abs=1e-4)


def test_optional_failure_allowed_by_threshold(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    task = build_task(
        tmp_path,
        [
            {"name": "pass", "kind": "python", "func": "check_bool_true", "weight": 3.0},
            {"name": "opt", "kind": "file_exists", "path": "missing", "weight": 1.0, "required": False},
        ],
        threshold=0.7,
    )
    verdict = run_grade(task, workspace)
    assert verdict.success
    assert verdict.score == 0.75


def test_exception_is_visible_not_silent(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    task = build_task(tmp_path, [{"name": "boom", "kind": "python", "func": "check_explode"}])
    verdict = run_grade(task, workspace)
    assert not verdict.success
    assert verdict.checks[0].severity == "error"
    assert "boom" in verdict.checks[0].detail


def test_state_and_tool_checks(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    task = build_task(
        tmp_path,
        [
            {"name": "changed", "kind": "state_changed", "paths": ["data.txt"]},
            {"name": "untouched", "kind": "state_unchanged", "paths": ["keep.txt"]},
            {"name": "called", "kind": "tool_called", "tool": "search_docs", "min_times": 1, "args_contains": "退款"},
        ],
    )
    tool_log = [{"tool": "search_docs", "args": {"query": "退款政策"}, "response": "7 天", "step": 0}]
    verdict = run_grade(task, workspace, tool_log=tool_log)
    assert verdict.success, verdict.message


def test_shell_check(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "x.txt").write_text("abc", encoding="utf-8")
    task = build_task(
        tmp_path,
        [
            {
                "name": "grep_like",
                "kind": "shell",
                "command": "python -c \"print(open('x.txt').read().strip().upper())\"",
                "stdout_contains": "ABC",
            }
        ],
    )
    verdict = run_grade(task, workspace)
    assert verdict.success, verdict.detail if hasattr(verdict, "detail") else verdict.message


def test_file_equals_normalizes_trailing_newline(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "out.txt").write_bytes(b"hello\r\n")
    task = build_task(tmp_path, [{"name": "eq", "kind": "file_equals", "path": "out.txt", "content": "hello"}])
    assert run_grade(task, workspace).success


def test_actions_available_to_python_checks(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    root = tmp_path / "suites" / "unit" / "grade-demo"
    root.mkdir(parents=True)
    payload = {
        "id": "grade-demo",
        "name": "grade demo",
        "category": "terminal",
        "prompt": "demo",
        "verifier": {"checks": [{"name": "n", "kind": "python", "func": "check_actions"}]},
    }
    import yaml

    (root / "task.yaml").write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    (root / "checks.py").write_text(
        "def check_actions(ctx):\n    return len(ctx.actions) == 2, f'{len(ctx.actions)} actions'\n", encoding="utf-8"
    )
    task = load_task(root)
    verdict = run_grade(task, workspace, actions=[Action("shell", {"command": "ls"}), Action("finish", {})])
    assert verdict.success
