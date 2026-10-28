"""一键复现：测试 → 任务自检 → 对照实验 → RL 轨迹采样。

用法：
    python scripts/run_all.py [--skip-tests] [--skip-experiment]

要求：在仓库根目录运行（脚本会自动把根目录加入 sys.path）。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_step(name: str, argv: list[str]) -> tuple[bool, float]:
    print(f"\n{'=' * 72}\n▶ {name}\n  $ {' '.join(argv)}\n{'=' * 72}")
    started = time.perf_counter()
    env = dict(os.environ)
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")  # 不污染任务目录
    env.setdefault("PYTHONIOENCODING", "utf-8")
    proc = subprocess.run(argv, cwd=ROOT, env=env)
    elapsed = time.perf_counter() - started
    ok = proc.returncode == 0
    print(f"  -> {'OK' if ok else 'FAILED'} ({elapsed:.1f}s)")
    return ok, elapsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-experiment", action="store_true")
    parser.add_argument("--skip-rl", action="store_true")
    args = parser.parse_args(argv)

    steps: list[tuple[str, list[str]]] = []
    if not args.skip_tests:
        steps.append(("pytest", [sys.executable, "-m", "pytest", "-q"]))
    steps.append(("doctor", [sys.executable, "-m", "agentlab", "doctor"]))
    steps.append(("validate 全部任务（oracle 可解性）", [sys.executable, "-m", "agentlab", "validate", "--workers", "4"]))
    if not args.skip_experiment:
        steps.append(("对照实验", [sys.executable, "scripts/run_experiment.py"]))
    if not args.skip_rl:
        steps.append(
            (
                "RL 轨迹采样",
                [
                    sys.executable,
                    "scripts/rollout_dataset.py",
                    "--suite",
                    "rebound",
                    "--policies",
                    "oracle,fragile,retry,silent",
                    "--reward-mode",
                    "shaped",
                    "--out",
                    "experiments/rl",
                ],
            )
        )

    results = []
    for name, argv_ in steps:
        ok, elapsed = run_step(name, argv_)
        results.append((name, ok, elapsed))
        if not ok:
            print(f"\n[中止] 步骤失败: {name}")
            break

    print("\n" + "=" * 72)
    print("汇总")
    print("=" * 72)
    for name, ok, elapsed in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {elapsed:6.1f}s  {name}")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
