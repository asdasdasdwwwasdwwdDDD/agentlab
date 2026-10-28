"""从 AgentLab 环境批量采样轨迹，产出可训练的 JSONL 数据集。

示例：
    python scripts/rollout_dataset.py --suite rebound --policies oracle,fragile,retry,silent \
        --reward-mode shaped --out experiments/rl/rollouts.jsonl

每行一个 episode：task_id / agent / transitions[{action, observation, reward, done}] /
total_reward / success / score / verdict。可直接用于行为克隆预热、reward model 训练或
offline RL 的 replay buffer（需自行按 task 划分 train/test 以防泄漏）。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentlab.agents.scripted import ScriptedAgent  # noqa: E402
from agentlab.core.registry import Registry, default_suites_dir  # noqa: E402
from agentlab.rl.env import AgentEnv  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AgentLab rollout 数据集生成")
    parser.add_argument("--suite", default="rebound")
    parser.add_argument("--task", action="append")
    parser.add_argument("--policies", default="oracle,fragile,retry,silent")
    parser.add_argument("--reward-mode", default="shaped", choices=["terminal", "shaped", "binary"])
    parser.add_argument("--step-cost", type=float, default=0.01)
    parser.add_argument("--success-bonus", type=float, default=0.0)
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--out", default="experiments/rl")
    args = parser.parse_args(argv)

    registry = Registry(default_suites_dir()).scan()
    if registry.errors:
        print("\n".join(registry.errors), file=sys.stderr)
        return 1
    tasks = registry.select(args.suite, args.task)
    policies = [p.strip() for p in args.policies.split(",") if p.strip()]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = out_dir / "rollouts.jsonl"
    workspaces = out_dir / "workspaces"
    if workspaces.exists():
        shutil.rmtree(workspaces, ignore_errors=True)

    started = time.perf_counter()
    rows: list[dict] = []
    with open(dataset_path, "w", encoding="utf-8", newline="\n") as handle:
        for task in tasks:
            for policy in policies:
                for sample in range(args.samples):
                    workspace = workspaces / f"{task.id}__{policy}__s{sample}"
                    if workspace.exists():
                        shutil.rmtree(workspace, ignore_errors=True)
                    env = AgentEnv(
                        task,
                        workspace,
                        reward_mode=args.reward_mode,
                        step_cost=args.step_cost,
                        success_bonus=args.success_bonus,
                    )
                    agent = ScriptedAgent(task, policy=policy, seed=sample)
                    record = env.rollout(agent)
                    record["policy"] = policy
                    record["sample"] = sample
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                    rows.append(record)
                    env.close()
                    print(
                        f"[{task.id}] policy={policy} success={record['success']} "
                        f"reward={record['total_reward']:.3f} steps={record['n_steps']}"
                    )

    summary = _summarize(rows)
    summary["meta"] = {
        "suite": args.suite,
        "reward_mode": args.reward_mode,
        "step_cost": args.step_cost,
        "policies": policies,
        "episodes": len(rows),
        "dataset": str(dataset_path),
        "duration_s": round(time.perf_counter() - started, 2),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "README.md").write_text(_markdown(summary), encoding="utf-8")
    print(f"\n写入 {len(rows)} 条轨迹: {dataset_path}")
    print(json.dumps(summary["by_policy"], ensure_ascii=False, indent=2))
    return 0


def _summarize(rows: list[dict]) -> dict:
    by_policy = defaultdict(list)
    for row in rows:
        by_policy[row["policy"]].append(row)
    out = {}
    for policy, items in sorted(by_policy.items()):
        successes = sum(1 for item in items if item["success"])
        out[policy] = {
            "episodes": len(items),
            "success_rate": round(successes / len(items), 4),
            "mean_reward": round(sum(item["total_reward"] for item in items) / len(items), 4),
            "mean_steps": round(sum(item["n_steps"] for item in items) / len(items), 2),
            "mean_tool_calls": round(sum(item["n_tool_calls"] for item in items) / len(items), 2),
        }
    return {"by_policy": out}


def _markdown(summary: dict) -> str:
    meta = summary["meta"]
    lines = [
        "# RL Rollout 数据集",
        "",
        f"- suite: `{meta['suite']}`",
        f"- reward_mode: `{meta['reward_mode']}`（step_cost={meta['step_cost']}）",
        f"- episodes: {meta['episodes']}",
        f"- dataset: `{Path(meta['dataset']).name}`",
        "",
        "| policy | episodes | success | mean reward | mean steps | mean calls |",
        "|---|---|---|---|---|---|",
    ]
    for policy, stats in summary["by_policy"].items():
        lines.append(
            f"| {policy} | {stats['episodes']} | {stats['success_rate'] * 100:.1f}% | "
            f"{stats['mean_reward']} | {stats['mean_steps']} | {stats['mean_tool_calls']} |"
        )
    lines += [
        "",
        "> 轨迹由脚本化策略生成，仅用于验证环境/奖励接口与数据格式；训练真实策略请把 agent 换成模型 rollout。",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
