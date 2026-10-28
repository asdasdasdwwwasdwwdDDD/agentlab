"""报告生成：summary.json + report.md + charts/*.png。

只从 results.jsonl 复算，保证“报告 = 原始轨迹”的可追溯性。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from agentlab.core.metrics import REBOUND_WEIGHTS, aggregate
from agentlab.core.trajectory import episodes_from_rows, read_rows


def write_report(run_dir: str | Path, with_charts: bool = True) -> tuple[Path, dict[str, Any]]:
    root = Path(run_dir)
    rows = read_rows(root)
    episodes = episodes_from_rows(rows)
    summary = aggregate(episodes)
    meta = _load_meta(root)
    summary["run"] = {
        **(summary.get("run") or {}),
        "run_id": root.name,
        "agent": meta.get("config", {}).get("agent"),
        "model": meta.get("config", {}).get("model"),
        "episodes": len(episodes),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    (root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    chart_paths: dict[str, str] = {}
    if with_charts and episodes:
        try:
            chart_paths = _make_charts(root, summary, episodes)
        except Exception as exc:  # 图表失败不应影响报告主体
            summary["chart_error"] = f"{type(exc).__name__}: {exc}"

    markdown = _render(root, summary, meta, chart_paths)
    report_path = root / "report.md"
    report_path.write_text(markdown, encoding="utf-8")
    return report_path, summary


# ------------------------------------------------------------------ charts
def _make_charts(root: Path, summary: dict[str, Any], episodes) -> dict[str, str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    charts = root / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    out: dict[str, str] = {}

    by_suite = summary["by_suite"]
    if by_suite:
        names = list(by_suite)
        values = [by_suite[n]["success_rate"] * 100 for n in names]
        lows = [max(0.0, (by_suite[n]["success_rate"] - by_suite[n]["wilson_ci"][0]) * 100) for n in names]
        highs = [max(0.0, (by_suite[n]["wilson_ci"][1] - by_suite[n]["success_rate"]) * 100) for n in names]
        fig, ax = plt.subplots(figsize=(7, 3.6), dpi=130)
        bars = ax.bar(names, values, yerr=[lows, highs], capsize=4, color="#3b6ea5")
        ax.set_ylim(0, 105)
        ax.set_ylabel("success rate (%)")
        ax.set_title("Success rate by suite (Wilson 95% CI)")
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, value + 2, f"{value:.0f}%", ha="center", fontsize=9)
        fig.tight_layout()
        path = charts / "success_by_suite.png"
        fig.savefig(path)
        plt.close(fig)
        out["success_by_suite"] = str(path.relative_to(root)).replace("\\", "/")

    taxonomy = {k: v for k, v in summary["taxonomy"].items() if k != "none" and v}
    if taxonomy:
        names = list(taxonomy)
        values = [taxonomy[n] for n in names]
        fig, ax = plt.subplots(figsize=(7, 3.6), dpi=130)
        ax.barh(names[::-1], values[::-1], color="#b5573f")
        ax.set_xlabel("episodes")
        ax.set_title("Failure taxonomy (failed episodes only)")
        fig.tight_layout()
        path = charts / "failure_taxonomy.png"
        fig.savefig(path)
        plt.close(fig)
        out["failure_taxonomy"] = str(path.relative_to(root)).replace("\\", "/")

    recovery = summary.get("recovery") or {}
    axes = [(k, (recovery.get(k) or {}).get("success_rate"), (recovery.get(k) or {}).get("n", 0)) for k in ("clean", "fault", "drift")]
    axes = [(k, v, n) for k, v, n in axes if v is not None and n]
    if len(axes) > 1:
        labels = [f"{k}\n(n={n})" for k, _, n in axes]
        values = [v * 100 for _, v, _ in axes]
        fig, ax = plt.subplots(figsize=(5.5, 3.6), dpi=130)
        bars = ax.bar(labels, values, color=["#4c9a6a", "#c08b30", "#7d5ba6"][: len(values)])
        ax.set_ylim(0, 105)
        ax.set_ylabel("success rate (%)")
        ax.set_title("Resilience: clean vs fault vs drift")
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, value + 2, f"{value:.0f}%", ha="center", fontsize=9)
        fig.tight_layout()
        path = charts / "resilience_axes.png"
        fig.savefig(path)
        plt.close(fig)
        out["resilience_axes"] = str(path.relative_to(root)).replace("\\", "/")

    if episodes:
        fig, ax = plt.subplots(figsize=(6.5, 3.4), dpi=130)
        counts = [e.n_tool_calls for e in episodes]
        ax.hist(counts, bins=min(20, max(3, len(counts))), color="#3b6ea5", edgecolor="white")
        ax.set_xlabel("tool calls (shell + tool)")
        ax.set_ylabel("episodes")
        ax.set_title("Tool-call budget usage")
        fig.tight_layout()
        path = charts / "tool_calls.png"
        fig.savefig(path)
        plt.close(fig)
        out["tool_calls"] = str(path.relative_to(root)).replace("\\", "/")
    return out


# ---------------------------------------------------------------- markdown
def _render(root: Path, summary: dict[str, Any], meta: dict[str, Any], charts: dict[str, str]) -> str:
    overall = summary["overall"]
    run = summary.get("run", {})
    config = meta.get("config", {})
    lines: list[str] = []
    add = lines.append

    add(f"# AgentLab 评测报告：`{root.name}`")
    add("")
    add(f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}  ")
    add(f"Agent：`{config.get('agent')}` · 模型：`{config.get('model')}` · 样本/task：{config.get('samples')} · "
        f"episodes：{run.get('episodes', overall['n'])}  ")
    add("")
    synthetic = str(config.get("agent", "")).startswith(("scripted", "oracle")) or config.get("model") == "mock"
    if synthetic:
        add("> ⚠️ **本报告是 harness 自检结果，不是模型能力结论。** agent 为 scripted/mock，"
            "分数只说明流水线能区分行为、判分与指标计算正确。真实模型评测需以 `--agent react --model <真实模型>` 运行。")
        add("")
    add("## 1. 总览")
    add("")
    add("| 指标 | 值 |")
    add("|---|---|")
    add(f"| Episodes | {overall['n']} |")
    add(f"| 成功率 SR | **{_pct(overall['success_rate'])}** (Wilson 95% CI {_pct(overall['wilson_ci'][0])} – {_pct(overall['wilson_ci'][1])}) |")
    add(f"| 平均动作数 | {overall['avg_steps']} |")
    add(f"| 平均 tool calls | {overall['avg_tool_calls']} |")
    add(f"| 平均效率分 ES | {overall['avg_efficiency']} |")
    add(f"| 平均 tokens | {overall['avg_tokens']} |")
    add(f"| 平均成本 | ${overall['avg_cost_usd']} |")
    if summary.get("pass_at_k"):
        add(f"| pass@k | {', '.join(f'{k}={v}' for k, v in summary['pass_at_k'].items())} |")
    add("")

    add("## 2. 分环境")
    add("")
    add("| Suite | n | SR | 95% CI | 平均 calls | 平均 ES | p50 耗时 |")
    add("|---|---|---|---|---|---|---|")
    for suite, stats in summary["by_suite"].items():
        add(f"| `{suite}` | {stats['n']} | {_pct(stats['success_rate'])} | "
            f"{_pct(stats['wilson_ci'][0])}–{_pct(stats['wilson_ci'][1])} | {stats['avg_tool_calls']} | "
            f"{stats['avg_efficiency']} | {stats['p50_wall_ms']} ms |")
    add("")

    add("## 3. 分难度")
    add("")
    add("| 难度 | n | SR | 平均 calls | 平均 ES |")
    add("|---|---|---|---|---|")
    for diff, stats in summary["by_difficulty"].items():
        add(f"| {diff} | {stats['n']} | {_pct(stats['success_rate'])} | {stats['avg_tool_calls']} | {stats['avg_efficiency']} |")
    add("")

    recovery = summary.get("recovery", {})
    rebound = summary.get("rebound", {})
    add("## 4. 韧性与 REBOUND 综合分")
    add("")
    add("| 轴 | n | 成功率 |")
    add("|---|---|---|")
    for axis in ("clean", "fault", "drift"):
        entry = recovery.get(axis) or {}
        if entry.get("n"):
            add(f"| {axis} | {entry['n']} | {_pct(entry['success_rate'])} |")
    if recovery.get("recovery_lift") is not None:
        add("")
        add(f"恢复率增益 recovery_lift = RRS − clean_SR = **{recovery['recovery_lift']:+.4f}**")
    if rebound.get("n"):
        add("")
        add(f"REBOUND 综合分 = 0.40·SR + 0.25·RRS + 0.20·ES + 0.15·CQ = **{rebound['score']}**  "
            f"(SR={rebound['sr']}, RRS={rebound['rrs']}, ES={rebound['es']}, CQ={rebound['cq']})")
        add("")
        add("> 权重定义见 `docs/gaps-and-proposal.md`；CQ 只在含 ambiguity 的任务上计算。")
    add("")

    taxonomy = summary.get("taxonomy", {})
    add("## 5. 失败分类")
    add("")
    add("| 模式 | episodes | 占比 |")
    add("|---|---|---|")
    failed = sum(v for k, v in taxonomy.items() if k != "none") or 1
    for name, count in taxonomy.items():
        if name == "none" or not count:
            continue
        add(f"| `{name}` | {count} | {count / failed * 100:.0f}% |")
    add("")

    add("## 6. 逐任务")
    add("")
    add("| Task | Suite | 难度 | n | SR | calls | ES | 失败检查 | 失败模式 |")
    add("|---|---|---|---|---|---|---|---|---|")
    for row in summary["per_task_rows"]:
        checks = ", ".join(row["failed_checks"][:3]) or "-"
        modes = ", ".join(m for m in row["failure_modes"] if m) or "-"
        add(f"| `{row['task_id']}` | {row['suite']} | {row['difficulty']} | {row['n']} | "
            f"{_pct(row['success_rate'])} | {row['avg_tool_calls']} | {row['avg_efficiency']} | {checks} | {modes} |")
    add("")

    if charts:
        add("## 7. 图表")
        add("")
        for key, rel in charts.items():
            add(f"![{key}]({rel})")
            add("")

    add("## 8. 复现方式")
    add("")
    add("```bash")
    add(f"python -m agentlab run --suite {config.get('suite') or '<suite>'} "
        f"--agent {config.get('agent')} --model {config.get('model')} "
        f"--samples {config.get('samples')} --out {Path(root).parent}")
    add("```")
    add("")
    add("口径说明：")
    add("")
    add("- SR = `status==success 且 verdict.success` 的 episode 占比；success 要求全部 `required` 检查通过且加权分 ≥ `pass_threshold`。")
    add("- pass@k 使用无偏估计 `1 − C(n−c,k)/C(n,k)`，按 task 计算后取平均。")
    add("- ES = `success × clip(1 − (used−oracle)/(cap−oracle), 0, 1)`；故障/超预算 episode 的 ES 为 0。")
    add("- 缺失值（如无 fault episode 时的 RRS）在聚合中记为 `null`，不参与综合分。")
    add("")
    add("产物：`results.jsonl`（逐 episode 摘要）、`episodes/`（完整轨迹）、`workspaces/`（终态文件，便于人工复核）、"
        "`summary.json`、`run_meta.json`（含任务指纹，可校验任务是否被改动）。")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ helpers
def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def _load_meta(root: Path) -> dict[str, Any]:
    path = root / "run_meta.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


__all__ = ["write_report", "REBOUND_WEIGHTS"]
