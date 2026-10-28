"""端到端：任务自检 + 策略对比 + 报告生成。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentlab.core.registry import Registry, default_suites_dir
from agentlab.core.trajectory import read_rows
from agentlab.eval.report import write_report
from agentlab.eval.runner import RunConfig, run
from agentlab.eval.validate import validate_tasks

pytestmark = pytest.mark.e2e


def all_tasks():
    registry = Registry(default_suites_dir()).scan()
    assert not registry.errors, registry.errors
    return registry.all()


def test_every_task_is_solvable_by_oracle(tmp_path: Path):
    tasks = all_tasks()
    assert tasks, "suites/ 下没有任务"
    results = validate_tasks(tasks, policy="oracle", workers=4)
    failures = [r for r in results if not r.success]
    assert not failures, "\n".join(f"{r.task_id}: {r.failed_checks}" for r in failures)


def test_runner_measures_recovery_gap(tmp_path: Path):
    oracle = run(
        RunConfig(suite="rebound", agent="scripted", policy="oracle", samples=1, workers=2, out_dir=str(tmp_path), run_id="oracle"),
    )
    fragile = run(
        RunConfig(suite="rebound", agent="scripted", policy="fragile", samples=1, workers=2, out_dir=str(tmp_path), run_id="fragile"),
    )
    oracle_sr = oracle.summary["overall"]["success_rate"]
    fragile_sr = fragile.summary["overall"]["success_rate"]
    assert oracle_sr == 1.0
    assert fragile_sr < oracle_sr
    assert fragile.summary["recovery"]["fault"]["success_rate"] == 0.0
    assert oracle.summary["recovery"]["fault"]["success_rate"] == 1.0
    rows = read_rows(fragile.paths.root)
    assert len(rows) == len(fragile.episodes) > 0
    assert all("failure_mode" in row["metrics"] for row in rows)


def test_report_generation(tmp_path: Path):
    result = run(
        RunConfig(suite="rebound", agent="scripted", policy="oracle", samples=1, workers=2, out_dir=str(tmp_path), run_id="report"),
        progress=None,
    )
    report_path, summary = write_report(result.paths.root)
    text = report_path.read_text(encoding="utf-8")
    assert "AgentLab 评测报告" in text
    assert "REBOUND" in text
    assert summary["overall"]["n"] == len(result.episodes)
    assert (result.paths.root / "summary.json").exists()
    charts = list((result.paths.root / "charts").glob("*.png"))
    assert charts, "未生成图表"


def test_ambiguous_task_rewards_clarification(tmp_path: Path):
    silent = run(
        RunConfig(task_ids=["rb-ambiguity-port"], agent="scripted", policy="silent", samples=1, workers=1, out_dir=str(tmp_path), run_id="silent"),
    )
    oracle = run(
        RunConfig(task_ids=["rb-ambiguity-port"], agent="scripted", policy="oracle", samples=1, workers=1, out_dir=str(tmp_path), run_id="clarify"),
    )
    assert oracle.summary["overall"]["success_rate"] == 1.0
    assert silent.summary["overall"]["success_rate"] == 0.0
    silent_episode = json.loads(
        (silent.paths.episodes / "rb-ambiguity-port__scripted__s0.json").read_text(encoding="utf-8")
    )
    failed = [c["name"] for c in silent_episode["verdict"]["checks"] if not c["passed"]]
    assert "clarification_done" in failed
    assert "manifest_content" not in failed
