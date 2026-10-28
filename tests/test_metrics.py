"""指标与失败分类测试。"""

from __future__ import annotations

import math

import pytest

from agentlab.core.metrics import (
    aggregate,
    clarification_quality,
    efficiency_score,
    pass_at_k,
    wilson_ci,
)
from agentlab.core.taxonomy import classify
from agentlab.core.types import Action, CheckResult, Episode, FaultEvent, Step, Verdict


def make_episode(task_id="t1", suite="terminal", success=True, status="success", **kwargs) -> Episode:
    verdict = Verdict(success=success, score=1.0 if success else 0.0, checks=kwargs.pop("checks", []))
    episode = Episode(
        run_id="r",
        task_id=task_id,
        suite=suite,
        category=kwargs.pop("category", "terminal"),
        difficulty=kwargs.pop("difficulty", "easy"),
        agent=kwargs.pop("agent", "scripted/oracle"),
        model="mock",
        status=status,
        verdict=verdict,
        **kwargs,
    )
    return episode


def test_wilson_ci_bounds():
    low, high = wilson_ci(0, 10)
    assert low == 0.0 and 0 < high < 0.35
    low, high = wilson_ci(10, 10)
    assert low > 0.65 and high == 1.0
    assert wilson_ci(0, 0) == (0.0, 0.0)


def test_pass_at_k_unbiased():
    assert pass_at_k(4, 2, 1) == pytest.approx(0.5)
    assert pass_at_k(4, 1, 1) == pytest.approx(0.25)
    assert pass_at_k(4, 1, 4) == pytest.approx(1.0)
    assert pass_at_k(4, 0, 2) == 0.0
    assert pass_at_k(4, 4, 2) == pytest.approx(1.0)


def test_efficiency_score():
    assert efficiency_score(False, 2, 2, 6) == 0.0
    assert efficiency_score(True, 2, 2, 6) == 1.0
    assert efficiency_score(True, 4, 2, 6) == pytest.approx(0.5)
    assert efficiency_score(True, 9, 2, 6) == 0.0
    # cap 不合法时不应出现除零
    assert 0.0 <= efficiency_score(True, 3, 3, 3) <= 1.0


def test_clarification_quality():
    episode = make_episode(useful_clarifications=1)
    assert clarification_quality(episode, 2) == 0.5
    assert clarification_quality(episode, 0) == 1.0


def test_recovery_aggregation():
    clean = make_episode("c", suite="rebound")
    fault_ok = make_episode("f", suite="rebound", faults=[FaultEvent(1, "fault", "delete_file")])
    fault_bad = make_episode(
        "f2", suite="rebound", success=False, status="failure", faults=[FaultEvent(1, "fault", "delete_file")]
    )
    drift = make_episode("d", suite="rebound", faults=[FaultEvent(1, "drift", "drift_delete")])
    for episode in (clean, fault_ok, fault_bad, drift):
        episode.metrics["efficiency"] = 1.0
    summary = aggregate([clean, fault_ok, fault_bad, drift])
    recovery = summary["recovery"]
    assert recovery["clean"]["success_rate"] == 1.0
    assert recovery["fault"]["success_rate"] == 0.5
    assert recovery["drift"]["success_rate"] == 1.0
    assert recovery["recovery_lift"] == pytest.approx(0.5 - 1.0)
    assert summary["rebound"]["score"] == pytest.approx(
        0.40 * 0.75 + 0.25 * 0.5 + 0.20 * 1.0 + 0.15 * 1.0, abs=1e-3
    )


def test_taxonomy_priority():
    gave_up = make_episode("g", success=False, status="failure")
    gave_up.steps = [Step(0, Action("shell", {"command": "ls"}), ""), Step(1, Action("give_up", {}), "", done=True)]
    assert classify(gave_up) == "gave_up"

    budget = make_episode("b", success=False, status="budget")
    budget.steps = [Step(0, Action("shell", {"command": "ls"}), "")]
    assert classify(budget) == "budget"

    loop = make_episode("l", success=False, status="failure")
    loop.steps = [Step(i, Action("shell", {"command": "ls"}), "exit_code: 0") for i in range(3)]
    assert classify(loop) == "loop"

    no_attempt = make_episode("n", success=False, status="failure")
    no_attempt.steps = [Step(0, Action("finish", {}), "任务结束。", done=True)]
    assert classify(no_attempt) == "no_attempt"

    wrong = make_episode(
        "w",
        success=False,
        status="failure",
        checks=[CheckResult("c", "file_equals", False)],
    )
    wrong.steps = [Step(0, Action("shell", {"command": "echo x"}), "exit_code: 0")]
    assert classify(wrong) == "wrong_output"

    ok = make_episode("ok")
    assert classify(ok) == "none"


def test_pass_at_k_aggregation():
    episodes = []
    for task_id, successes in (("a", [True, True]), ("b", [True, False])):
        for index, success in enumerate(successes):
            episodes.append(
                make_episode(task_id, success=success, status="success" if success else "failure", sample_idx=index)
            )
    summary = aggregate(episodes)
    assert summary["pass_at_k"]["pass@2"] == pytest.approx(1.0)
    assert summary["overall"]["n"] == 4
