"""Runner：任务加载 → 环境初始化 → Agent 交互 → 轨迹落盘 → 自动判分。

设计约束：
- 每个 episode 独立 workspace，互不污染，可并行。
- Agent/环境异常不能拖垮整批；异常 episode 记为 error 并保留已完成轨迹。
- 判分始终对 workspace 终态进行（即使超预算/超时），以保留部分信号。
"""

from __future__ import annotations

import shutil
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from agentlab.agents import build_agent
from agentlab.core.metrics import aggregate, clarification_quality, efficiency_score
from agentlab.core.registry import Registry, default_suites_dir
from agentlab.core.taxonomy import classify
from agentlab.core.trajectory import ResultWriter, RunPaths, write_meta
from agentlab.core.types import Episode, Step
from agentlab.envs.shell import ShellEnv
from agentlab.verifiers.grader import grade


@dataclass
class RunConfig:
    suite: str | None = None
    task_ids: list[str] | None = None
    agent: str = "scripted"
    policy: str = "oracle"
    model: str = "mock"
    samples: int = 1
    workers: int = 4
    out_dir: str = "experiments/results"
    run_id: str | None = None
    noise: float = 0.0
    seed: int = 0
    limit: int | None = None
    temperature: float = 0.0
    keep_workspaces: bool = True
    quiet: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "task_ids": self.task_ids,
            "agent": self.agent,
            "policy": self.policy,
            "model": self.model,
            "samples": self.samples,
            "workers": self.workers,
            "noise": self.noise,
            "seed": self.seed,
            "limit": self.limit,
            "temperature": self.temperature,
        }

    def resolved_run_id(self) -> str:
        if self.run_id:
            return self.run_id
        stamp = time.strftime("%Y%m%d-%H%M%S")
        agent_part = self.agent.replace(":", "-")
        model_part = self.model.replace(":", "-").replace("/", "-")
        return f"{stamp}__{agent_part}__{model_part}"


@dataclass
class RunResult:
    paths: RunPaths
    summary: dict[str, Any]
    episodes: list[Episode] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


ProgressCallback = Callable[[int, int, Episode], None]


def run(config: RunConfig, registry: Registry | None = None, progress: ProgressCallback | None = None) -> RunResult:
    registry = registry or Registry(default_suites_dir()).scan()
    if registry.errors:
        raise RuntimeError("任务包加载失败:\n" + "\n".join(registry.errors))
    tasks = registry.select(config.suite, config.task_ids)
    if config.limit:
        tasks = tasks[: config.limit]
    if not tasks:
        raise RuntimeError(f"没有匹配的任务（suite={config.suite!r}, task_ids={config.task_ids}）")

    run_id = config.resolved_run_id()
    paths = RunPaths.prepare(config.out_dir, run_id)
    write_meta(
        paths,
        config={**config.to_dict(), "run_id": run_id},
        tasks=[{"id": t.id, "suite": t.suite, "fingerprint": t.spec.fingerprint(), "difficulty": t.spec.difficulty} for t in tasks],
    )
    writer = ResultWriter(paths)
    jobs = [(task, sample) for task in tasks for sample in range(max(1, config.samples))]
    total = len(jobs)
    episodes: list[Episode] = []
    errors: list[str] = []
    started = time.perf_counter()

    with ThreadPoolExecutor(max_workers=max(1, config.workers)) as pool:
        futures = {
            pool.submit(_run_episode, task, sample, config, paths, writer): (task.id, sample)
            for task, sample in jobs
        }
        for done, future in enumerate(as_completed(futures), start=1):
            task_id, sample = futures[future]
            try:
                episode = future.result()
            except Exception as exc:  # 理论上 _run_episode 已兜底
                errors.append(f"{task_id}#s{sample}: {type(exc).__name__}: {exc}\n{traceback.format_exc(limit=3)}")
                continue
            episodes.append(episode)
            if progress:
                progress(done, total, episode)

    episodes.sort(key=lambda e: (e.task_id, e.sample_idx))
    summary = aggregate(episodes)
    summary["run"] = {
        "run_id": run_id,
        "agent": config.agent,
        "model": config.model,
        "samples": config.samples,
        "duration_s": round(time.perf_counter() - started, 2),
        "tasks": len(tasks),
        "episodes": len(episodes),
        "errors": len(errors),
    }
    (paths.summary_json).write_text(_json(summary), encoding="utf-8")
    return RunResult(paths=paths, summary=summary, episodes=episodes, errors=errors)


def _run_episode(task, sample_idx: int, config: RunConfig, paths: RunPaths, writer: ResultWriter) -> Episode:
    spec = task.spec
    workspace = paths.workspaces / f"{task.id}__s{sample_idx}"
    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True, exist_ok=True)

    env = ShellEnv(task, workspace)
    agent = build_agent(
        config.agent,
        task,
        model=config.model,
        policy=config.policy,
        noise=config.noise,
        seed=config.seed + sample_idx,
        temperature=config.temperature,
    )
    budget = spec.budget
    deadline = time.monotonic() + max(1.0, budget.max_wall_s)
    started = time.perf_counter()
    steps: list[Step] = []
    status = "failure"
    error: str | None = None
    observation = env.reset()

    try:
        while True:
            if len(steps) >= spec.max_steps:
                status, error = "budget", f"超过 max_steps={spec.max_steps}"
                break
            if time.monotonic() > deadline:
                status, error = "timeout", f"超过 max_wall_s={budget.max_wall_s}"
                break
            action = agent.act(observation.text)
            result = env.step(action)
            step = Step(
                idx=len(steps),
                action=action,
                observation=result.observation.text,
                done=result.done,
                reward_hint=result.reward_hint,
                info=dict(result.info),
                t_ms=int(result.info.get("elapsed_ms", 0)),
            )
            steps.append(step)
            agent.observe(step)
            observation = result.observation
            if result.done:
                break
            if env.n_tool_calls > budget.max_tool_calls:
                status, error = "budget", f"超过 max_tool_calls={budget.max_tool_calls}"
                break
            usage = agent.usage()
            if usage["prompt_tokens"] + usage["completion_tokens"] > budget.max_tokens:
                status, error = "budget", f"超过 max_tokens={budget.max_tokens}"
                break
    except Exception as exc:
        status = "error"
        error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=4)[-1500:]}"

    verdict = None
    try:
        verdict = grade(
            task=task,
            workspace=env.workspace,
            state_before=env.snapshot_before,
            state_after=env.snapshot(),
            tool_log=env.tool_log,
            actions=[s.action for s in steps],
            meta={
                "state": dict(env.state),
                "clarifications": env.clarifications,
                "useful_clarifications": env.useful_clarifications,
                "faults": [f.to_dict() for f in env.fault_events],
            },
        )
    except Exception as exc:
        status = "error"
        error = (error or "") + f"\n判定失败: {type(exc).__name__}: {exc}\n{traceback.format_exc(limit=3)[-1200:]}"

    if status == "failure" and verdict is not None and verdict.success:
        status = "success"

    usage = agent.usage()
    wall_ms = int((time.perf_counter() - started) * 1000)
    episode = Episode(
        run_id=paths.root.name,
        task_id=task.id,
        suite=task.suite,
        category=spec.category,
        difficulty=spec.difficulty,
        agent=config.agent if config.agent != "oracle" else "scripted/oracle",
        model=agent.model_name,
        sample_idx=sample_idx,
        status=status,  # type: ignore[arg-type]
        verdict=verdict,
        steps=steps,
        n_steps=len(steps),
        n_tool_calls=env.n_tool_calls,
        prompt_tokens=int(usage["prompt_tokens"]),
        completion_tokens=int(usage["completion_tokens"]),
        wall_ms=wall_ms,
        cost_usd=float(usage["cost_usd"]),
        faults=list(env.fault_events),
        clarifications=env.clarifications,
        useful_clarifications=env.useful_clarifications,
        error=error,
    )
    success = bool(verdict and verdict.success and status == "success")
    episode.metrics = {
        "efficiency": efficiency_score(success, env.n_tool_calls, budget.oracle_tool_calls, budget.max_tool_calls),
        "has_ambiguity": spec.is_ambiguous,
        "clarification_quality": clarification_quality(episode, spec.ambiguity.required_clarifications)
        if spec.ambiguity
        else 0.0,
        "tool_calls": env.n_tool_calls,
        "oracle_tool_calls": budget.oracle_tool_calls,
        "max_tool_calls": budget.max_tool_calls,
        "task_fingerprint": spec.fingerprint(),
        "failure_mode": None,
    }
    episode.metrics["failure_mode"] = classify(episode)
    writer.write(episode)
    env.close()
    if not config.keep_workspaces:
        shutil.rmtree(workspace, ignore_errors=True)
    return episode


def _json(data: Any) -> str:
    import json

    return json.dumps(data, ensure_ascii=False, indent=2)
