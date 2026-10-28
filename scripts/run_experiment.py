"""跑一组对照实验并生成 experiments/comparison.md。

矩阵设计目的：
1. 用 scripted 策略证明同一个任务集能区分"会不会重试 / 敢不敢问 / 是否提前交卷"；
2. 用 react + mock 噪声验证真实模型的文本协议、解析与轨迹记录链路；
3. 汇总成 REBOUND 分解表，作为 docs/experiment-report.md 的数据源。

注意：这里没有调用任何真实 LLM（本机无 key），所以分数是 **harness 自检**，不是模型排名。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentlab.core.metrics import aggregate  # noqa: E402
from agentlab.core.registry import Registry, default_suites_dir  # noqa: E402
from agentlab.core.trajectory import episodes_from_rows, read_rows  # noqa: E402
from agentlab.eval.report import write_report  # noqa: E402
from agentlab.eval.runner import RunConfig, run  # noqa: E402

# (name, description, RunConfig kwargs, suites)
MATRIX = [
    ("oracle", "脚本化 oracle：按解重放", dict(agent="scripted", policy="oracle", samples=2), None),
    ("fragile", "遇错即放弃（不恢复）", dict(agent="scripted", policy="fragile", samples=2), "rebound"),
    ("retry", "失败后重试同一动作", dict(agent="scripted", policy="retry", samples=2), "rebound"),
    ("silent", "跳过澄清直接猜", dict(agent="scripted", policy="silent", samples=2), "rebound"),
    ("early-stop", "提前交卷（少做最后一步）", dict(agent="scripted", policy="early_stop", samples=2), "rebound"),
    ("react-noise", "ReAct + mock 模型 + 30% 行为噪声", dict(agent="react", model="mock:0.3", samples=2), None),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suites", default=None, help="逗号分隔；缺省用 suites/ 下全部")
    parser.add_argument("--out", default="experiments/results")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--no-report", action="store_true")
    args = parser.parse_args(argv)

    registry = Registry(default_suites_dir()).scan()
    if registry.errors:
        print("\n".join(registry.errors), file=sys.stderr)
        return 1
    available = set(registry.suites())
    requested = [s.strip() for s in args.suites.split(",")] if args.suites else sorted(available)
    missing = [s for s in requested if s not in available]
    if missing:
        print(f"[warn] 跳过不存在的 suite: {missing}", file=sys.stderr)
    suites = [s for s in requested if s in available]
    if not suites:
        print("没有可运行的 suite", file=sys.stderr)
        return 1
    print(f"suites = {suites}")

    summary_rows = []
    for name, description, kwargs, suite_filter in MATRIX:
        if suite_filter and suite_filter not in suites:
            continue
        run_id = f"exp-{name}"
        config = RunConfig(
            suite=suite_filter,
            samples=kwargs.get("samples", 1),
            workers=args.workers,
            out_dir=args.out,
            run_id=run_id,
            keep_workspaces=False,
            quiet=True,
            **{k: v for k, v in kwargs.items() if k != "samples"},
        )
        print(f"\n=== {name} ({description}) ===")
        result = run(config)
        overall = result.summary["overall"]
        print(
            f"episodes={overall['n']} SR={overall['success_rate'] * 100:.1f}% "
            f"RRS={(result.summary['recovery']['fault']['success_rate'] or 0) * 100:.1f}% "
            f"mean_calls={overall['avg_tool_calls']} rebound_score={result.summary['rebound']['score']}"
        )
        if not args.no_report:
            write_report(result.paths.root)
        summary_rows.append(
            {
                "name": name,
                "description": description,
                "run_id": run_id,
                "suite_filter": suite_filter,
                "config": config.to_dict(),
                "summary": {
                    "n": overall["n"],
                    "success_rate": overall["success_rate"],
                    "wilson_ci": overall["wilson_ci"],
                    "avg_tool_calls": overall["avg_tool_calls"],
                    "avg_efficiency": overall["avg_efficiency"],
                    "avg_steps": overall["avg_steps"],
                    "pass_at_k": result.summary.get("pass_at_k", {}),
                    "recovery": result.summary.get("recovery", {}),
                    "rebound": result.summary.get("rebound", {}),
                    "taxonomy": result.summary.get("taxonomy", {}),
                },
            }
        )

    out_root = Path(args.out)
    (out_root / "comparison.json").write_text(json.dumps(summary_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown, chart = _render_comparison(summary_rows, out_root)
    (out_root / "comparison.md").write_text(markdown, encoding="utf-8")
    print(f"\n对照结果: {out_root / 'comparison.md'}")
    if chart:
        print(f"图表: {chart}")
    return 0


def _render_comparison(rows: list[dict], out_root: Path) -> tuple[str, str | None]:
    lines = [
        "# AgentLab 对照实验",
        "",
        "> 所有 agent 均为 scripted 或 mock 模型：本表用于验证评测流水线能区分行为，**不是模型能力结论**。",
        "",
        "| 变体 | 说明 | episodes | SR | 95% CI | RRS | 平均 calls | 平均 ES | REBOUND |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        s = row["summary"]
        ci = f"{s['wilson_ci'][0] * 100:.0f}–{s['wilson_ci'][1] * 100:.0f}%"
        rrs = (s["recovery"].get("fault") or {}).get("success_rate")
        rebound = s["rebound"].get("score")
        lines.append(
            f"| `{row['name']}` | {row['description']} | {s['n']} | {s['success_rate'] * 100:.1f}% | {ci} | "
            f"{_pct(rrs)} | {s['avg_tool_calls']} | {s['avg_efficiency']} | {_num(rebound)} |"
        )
    lines += ["", "## 恢复 / 漂移分解", "", "| 变体 | clean SR | fault SR | drift SR | recovery lift |", "|---|---|---|---|---|"]
    for row in rows:
        rec = row["summary"]["recovery"]
        lines.append(
            f"| `{row['name']}` | {_pct((rec.get('clean') or {}).get('success_rate'))} | "
            f"{_pct((rec.get('fault') or {}).get('success_rate'))} | "
            f"{_pct((rec.get('drift') or {}).get('success_rate'))} | {_num(rec.get('recovery_lift'), signed=True)} |"
        )
    lines += ["", "## 失败模式", "", "| 变体 | 主要失败模式 |", "|---|---|"]
    for row in rows:
        taxonomy = {k: v for k, v in row["summary"]["taxonomy"].items() if k != "none" and v}
        top = sorted(taxonomy.items(), key=lambda kv: kv[1], reverse=True)[:4]
        lines.append(f"| `{row['name']}` | {', '.join(f'{k}={v}' for k, v in top) or '-'} |")
    lines += [
        "",
        "## 读法",
        "",
        "- `oracle` 是上界（按任务解重放），任何 <100% 都说明任务本身或判分有问题，应先修任务。",
        "- `fragile` 与 `retry` 的差值近似「恢复行为」的贡献；`silent` 验证澄清质量 CQ 与成功率解耦。",
        "- `react-noise` 用 30% 丢步/替换动作模拟不完美策略，用于验证 ReAct 文本协议与轨迹记录链路。",
        "- Wilson 区间在 n 很小时会非常宽，不要把个位数 episode 的差值当结论。",
        "",
        "## 明细",
        "",
        "每个变体的完整报告在 `experiments/results/exp-<name>/report.md`。",
    ]

    chart = None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        names = [row["name"] for row in rows]
        values = [row["summary"]["success_rate"] * 100 for row in rows]
        fig, ax = plt.subplots(figsize=(8, 3.6), dpi=140)
        bars = ax.bar(names, values, color="#3b6ea5")
        ax.set_ylabel("success rate (%)")
        ax.set_ylim(0, 105)
        ax.set_title("Synthetic agents: success rate by variant")
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, value + 2, f"{value:.0f}%", ha="center", fontsize=8)
        fig.tight_layout()
        chart_path = out_root / "comparison.png"
        fig.savefig(chart_path)
        plt.close(fig)
        chart = str(chart_path)
        lines += ["", "![comparison](comparison.png)"]
    except Exception as exc:  # pragma: no cover
        lines += ["", f"> 图表生成失败: {exc}"]
    return "\n".join(lines) + "\n", chart


def _pct(value) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _num(value, signed: bool = False) -> str:
    if value is None:
        return "—"
    return f"{value:+.3f}" if signed else f"{value:.3f}"


if __name__ == "__main__":
    raise SystemExit(main())
