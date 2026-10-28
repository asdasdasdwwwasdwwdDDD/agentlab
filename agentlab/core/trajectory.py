"""轨迹与运行产物落盘。

目录结构（DESIGN §3）：
  <run_dir>/run_meta.json     运行配置 + 任务指纹（可复现性）
  <run_dir>/results.jsonl     一行一个 episode 摘要
  <run_dir>/episodes/*.json   完整轨迹（含每步 observation）
  <run_dir>/summary.json      聚合指标
  <run_dir>/report.md         人类可读报告
  <run_dir>/charts/*.png
"""

from __future__ import annotations

import json
import platform
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentlab.core.types import Episode, Step, Action, CheckResult, FaultEvent, Verdict


@dataclass
class RunPaths:
    root: Path
    episodes: Path
    workspaces: Path
    results_jsonl: Path
    meta_json: Path
    summary_json: Path
    report_md: Path
    charts: Path

    @classmethod
    def prepare(cls, out_root: str | Path, run_id: str) -> "RunPaths":
        root = Path(out_root) / run_id
        paths = cls(
            root=root,
            episodes=root / "episodes",
            workspaces=root / "workspaces",
            results_jsonl=root / "results.jsonl",
            meta_json=root / "run_meta.json",
            summary_json=root / "summary.json",
            report_md=root / "report.md",
            charts=root / "charts",
        )
        for directory in (paths.episodes, paths.workspaces, paths.charts):
            directory.mkdir(parents=True, exist_ok=True)
        paths.results_jsonl.write_text("", encoding="utf-8")
        return paths


class ResultWriter:
    """线程安全地追加结果；episode 轨迹单独落盘。"""

    def __init__(self, paths: RunPaths):
        self.paths = paths
        self._lock = threading.Lock()
        self._count = 0

    def write(self, episode: Episode) -> None:
        safe_name = episode.task_id.replace("/", "_").replace("\\", "_")
        episode_path = self.paths.episodes / f"{safe_name}__{episode.agent}__s{episode.sample_idx}.json"
        payload = episode.to_dict(include_steps=True)
        with self._lock:
            episode_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            row = episode.to_dict(include_steps=False)
            with open(self.paths.results_jsonl, "a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            self._count += 1

    @property
    def count(self) -> int:
        return self._count


def write_meta(paths: RunPaths, config: dict[str, Any], tasks: list[dict[str, Any]]) -> None:
    meta = {
        "run_id": paths.root.name,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "config": config,
        "tasks": tasks,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "agentlab_version": _version(),
        },
    }
    paths.meta_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def read_rows(run_dir: str | Path) -> list[dict[str, Any]]:
    path = Path(run_dir)
    results = path / "results.jsonl" if path.is_dir() else path
    if not results.exists():
        raise FileNotFoundError(f"找不到结果文件: {results}")
    rows = []
    for line in results.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def episodes_from_rows(rows: list[dict[str, Any]]) -> list[Episode]:
    """从 results.jsonl 重建 Episode（不加载完整 steps，失败分类已在 metrics 中固化）。"""
    episodes = []
    for row in rows:
        verdict = None
        if row.get("verdict"):
            verdict = Verdict(
                success=row["verdict"]["success"],
                score=row["verdict"]["score"],
                message=row["verdict"].get("message", ""),
                checks=[CheckResult(**c) for c in row["verdict"].get("checks", [])],
            )
        episodes.append(
            Episode(
                run_id=row["run_id"],
                task_id=row["task_id"],
                suite=row["suite"],
                category=row["category"],
                difficulty=row["difficulty"],
                agent=row["agent"],
                model=row["model"],
                sample_idx=row.get("sample_idx", 0),
                status=row["status"],
                verdict=verdict,
                steps=[],
                n_steps=row.get("n_steps", 0),
                n_tool_calls=row.get("n_tool_calls", 0),
                prompt_tokens=row.get("prompt_tokens", 0),
                completion_tokens=row.get("completion_tokens", 0),
                wall_ms=row.get("wall_ms", 0),
                cost_usd=row.get("cost_usd", 0.0),
                faults=[FaultEvent(**f) for f in row.get("faults", [])],
                clarifications=row.get("clarifications", 0),
                useful_clarifications=row.get("useful_clarifications", 0),
                metrics=row.get("metrics", {}),
                error=row.get("error"),
            )
        )
    return episodes


def load_episode_file(path: Path) -> Episode:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    verdict = None
    if data.get("verdict"):
        verdict = Verdict(
            success=data["verdict"]["success"],
            score=data["verdict"]["score"],
            message=data["verdict"].get("message", ""),
            checks=[CheckResult(**c) for c in data["verdict"].get("checks", [])],
        )
    steps = [
        Step(
            idx=s["idx"],
            action=Action.from_dict(s["action"]),
            observation=s.get("observation", ""),
            done=s.get("done", False),
            reward_hint=s.get("reward_hint"),
            info=s.get("info", {}),
            t_ms=s.get("t_ms", 0),
        )
        for s in data.get("steps", [])
    ]
    return Episode(
        **{k: v for k, v in data.items() if k in Episode.__dataclass_fields__ and k not in ("steps", "verdict")},
        verdict=verdict,
        steps=steps,
    )


def _version() -> str:
    try:
        from agentlab import __version__

        return __version__
    except Exception:  # pragma: no cover
        return "unknown"
