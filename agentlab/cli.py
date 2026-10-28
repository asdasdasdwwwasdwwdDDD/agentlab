"""命令行入口：list / validate / run / report / doctor。"""

from __future__ import annotations

import argparse
import platform
import sys
import tempfile
from pathlib import Path

from agentlab import __version__
from agentlab.agents.scripted import POLICIES
from agentlab.core.registry import Registry, default_suites_dir
from agentlab.core.spec import CHECK_REQUIRED_PARAMS
from agentlab.eval.report import write_report
from agentlab.eval.runner import RunConfig, run
from agentlab.eval.validate import validate_tasks
from agentlab.envs.base import default_shell_argv
from agentlab.models.openai_compat import probe

try:
    from rich.console import Console
    from rich.table import Table
    from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

    _console = Console()
    HAS_RICH = True
except Exception:  # pragma: no cover - rich 是可选展示依赖
    _console = None
    HAS_RICH = False


def console():
    return _console


def _print(message: str = "", style: str | None = None) -> None:
    if HAS_RICH:
        _console.print(message, style=style)
    else:
        print(message)


def _table(title: str, columns: list[str], rows: list[list[str]]) -> None:
    if HAS_RICH:
        table = Table(title=title, header_style="bold cyan", show_lines=False)
        for column in columns:
            table.add_column(column)
        for row in rows:
            table.add_row(*[str(c) for c in row])
        _console.print(table)
    else:
        print(f"\n== {title} ==")
        print(" | ".join(columns))
        for row in rows:
            print(" | ".join(str(c) for c in row))


# --------------------------------------------------------------------- list
def cmd_list(args: argparse.Namespace) -> int:
    registry = Registry(default_suites_dir()).scan()
    if registry.errors:
        for error in registry.errors:
            _print(f"[load error] {error}", "red")
        return 1
    tasks = registry.select(args.suite)
    rows = []
    for task in tasks:
        spec = task.spec
        extras = []
        if spec.faults:
            extras.append(f"faults={len(spec.faults)}")
        if spec.is_ambiguous:
            extras.append("ambiguous")
        rows.append(
            [
                spec.id,
                task.suite,
                spec.category,
                spec.difficulty,
                str(spec.max_steps),
                ", ".join(spec.tool_names),
                " ".join(extras) or "-",
            ]
        )
    _table(
        f"任务清单（{len(tasks)} 个，合计 {len(registry)} 个；suites: {', '.join(registry.suites()) or '无'}）",
        ["id", "suite", "category", "难度", "max_steps", "tools", "特性"],
        rows,
    )
    return 0


# ----------------------------------------------------------------- validate
def cmd_validate(args: argparse.Namespace) -> int:
    registry = Registry(default_suites_dir()).scan()
    if registry.errors:
        for error in registry.errors:
            _print(f"[load error] {error}", "red")
        return 1
    tasks = registry.select(args.suite, args.task)
    if not tasks:
        _print("没有匹配的任务", "yellow")
        return 1
    results = validate_tasks(tasks, policy=args.policy, workers=args.workers)
    rows = []
    for result in results:
        rows.append(
            [
                result.task_id,
                result.suite,
                result.difficulty,
                "PASS" if result.success else "FAIL",
                f"{result.score:.2f}",
                str(result.steps),
                str(result.tool_calls),
                ", ".join(result.failed_checks) or "-",
            ]
        )
    _table(f"任务自检（policy={args.policy}）", ["task", "suite", "难度", "结果", "score", "steps", "calls", "失败检查"], rows)
    failed = [r for r in results if not r.success]
    for result in failed:
        _print(f"\n[FAIL] {result.task_id}", "red")
        for detail in result.details:
            _print(f"  - {detail}")
        if result.error:
            _print(f"  error: {result.error.splitlines()[0] if result.error else ''}")
    _print(f"\n{len(results) - len(failed)}/{len(results)} 通过", "green" if not failed else "red")
    return 0 if not failed else 1


# ---------------------------------------------------------------------- run
def cmd_run(args: argparse.Namespace) -> int:
    config = RunConfig(
        suite=args.suite,
        task_ids=args.task,
        agent=args.agent,
        policy=args.policy,
        model=args.model,
        samples=args.samples,
        workers=args.workers,
        out_dir=args.out,
        run_id=args.run_id,
        noise=args.noise,
        seed=args.seed,
        limit=args.limit,
        temperature=args.temperature,
        keep_workspaces=not args.drop_workspaces,
        quiet=args.quiet,
    )
    progress_bar = None
    if HAS_RICH and not args.quiet:
        progress_bar = Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=_console,
            transient=True,
        )
        progress_bar.start()
        progress_task = progress_bar.add_task("评测中", total=args.samples * 1)

    counter = {"done": 0, "total": 0}

    def on_progress(done: int, total: int, episode) -> None:
        counter["done"], counter["total"] = done, total
        if progress_bar is not None:
            progress_bar.update(progress_task, total=total, completed=done)
        if episode.status == "error":
            _print(f"[warn] {episode.task_id} 运行异常: {(episode.error or '').splitlines()[0]}", "yellow")

    try:
        result = run(config, progress=on_progress)
    finally:
        if progress_bar is not None:
            progress_bar.stop()

    if result.errors:
        for error in result.errors:
            _print(f"[error] {error}", "red")

    overall = result.summary["overall"]
    _print("")
    _table(
        f"结果总览 · {result.paths.root.name}",
        ["指标", "值"],
        [
            ["episodes", str(overall["n"])],
            ["成功率", f"{overall['success_rate'] * 100:.1f}%  (CI {overall['wilson_ci'][0] * 100:.1f}–{overall['wilson_ci'][1] * 100:.1f}%)"],
            ["平均 calls / ES", f"{overall['avg_tool_calls']} / {overall['avg_efficiency']}"],
            ["平均 tokens / cost", f"{overall['avg_tokens']} / ${overall['avg_cost_usd']}"],
        ],
    )
    suite_rows = [
        [name, str(stats["n"]), f"{stats['success_rate'] * 100:.1f}%", str(stats["avg_tool_calls"]), str(stats["avg_efficiency"])]
        for name, stats in result.summary["by_suite"].items()
    ]
    _table("分 suite", ["suite", "n", "SR", "avg calls", "avg ES"], suite_rows)

    failed = [row for row in result.summary["per_task_rows"] if row["success_rate"] < 1.0]
    if failed:
        _table(
            "未满分的任务",
            ["task", "suite", "SR", "失败检查"],
            [[row["task_id"], row["suite"], f"{row['success_rate'] * 100:.0f}%", ", ".join(row["failed_checks"][:2]) or "-"] for row in failed[:12]],
        )

    if not args.no_report:
        try:
            report_path, _ = write_report(result.paths.root)
            _print(f"\n报告: {report_path}", "bold")
        except Exception as exc:  # pragma: no cover
            _print(f"[warn] 报告生成失败: {exc}", "yellow")
    _print(f"结果目录: {result.paths.root}", "dim")
    return 0


# ------------------------------------------------------------------- report
def cmd_report(args: argparse.Namespace) -> int:
    try:
        path, summary = write_report(args.run, with_charts=not args.no_charts)
    except FileNotFoundError as exc:
        _print(str(exc), "red")
        return 1
    overall = summary["overall"]
    _print(f"报告已生成: {path}", "bold")
    _print(f"SR={overall['success_rate'] * 100:.1f}% (n={overall['n']}), avg calls={overall['avg_tool_calls']}")
    return 0


# ------------------------------------------------------------------- doctor
def cmd_doctor(args: argparse.Namespace) -> int:
    registry = Registry(default_suites_dir()).scan()
    suites = {suite: len(registry.by_suite(suite)) for suite in registry.suites()}
    rows = [
        ["agentlab", __version__],
        ["python", sys.version.split()[0]],
        ["platform", platform.platform()],
        ["shell argv", " ".join(default_shell_argv())],
        ["suites dir", str(default_suites_dir())],
        ["tasks", f"{len(registry)} ({', '.join(f'{k}={v}' for k, v in suites.items()) or '无'})"],
        ["load errors", str(len(registry.errors))],
        ["check kinds", f"{len(CHECK_REQUIRED_PARAMS)}"],
        ["model", f"base_url={probe()['base_url']}, api_key_set={probe()['api_key_set']}"],
    ]
    _table("环境自检", ["项", "值"], rows)
    if registry.errors:
        for error in registry.errors:
            _print(f"[load error] {error}", "red")
        return 1
    if not suites:
        _print("提示: suites/ 为空，可先运行 `python -m agentlab list`", "yellow")
    _print("OK", "green")
    return 0


# ---------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentlab", description="Agent / RL 环境评测流水线")
    parser.add_argument("--version", action="version", version=f"agentlab {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    lst = sub.add_parser("list", help="列出任务")
    lst.add_argument("--suite")
    lst.set_defaults(func=cmd_list)

    val = sub.add_parser("validate", help="用 oracle 自检任务")
    val.add_argument("--suite")
    val.add_argument("--task", action="append")
    val.add_argument("--policy", default="oracle", choices=list(POLICIES))
    val.add_argument("--workers", type=int, default=4)
    val.set_defaults(func=cmd_validate)

    run_p = sub.add_parser("run", help="运行评测")
    run_p.add_argument("--suite")
    run_p.add_argument("--task", action="append")
    run_p.add_argument("--agent", default="scripted", help="oracle | scripted[:policy] | react")
    run_p.add_argument("--policy", default="oracle", choices=list(POLICIES))
    run_p.add_argument("--model", default="mock", help="mock | <OpenAI 兼容模型名>")
    run_p.add_argument("--samples", type=int, default=1)
    run_p.add_argument("--workers", type=int, default=4)
    run_p.add_argument("--out", default="experiments/results")
    run_p.add_argument("--run-id")
    run_p.add_argument("--noise", type=float, default=0.0)
    run_p.add_argument("--seed", type=int, default=0)
    run_p.add_argument("--limit", type=int)
    run_p.add_argument("--temperature", type=float, default=0.0)
    run_p.add_argument("--drop-workspaces", action="store_true")
    run_p.add_argument("--no-report", action="store_true")
    run_p.add_argument("--quiet", action="store_true")
    run_p.set_defaults(func=cmd_run)

    rep = sub.add_parser("report", help="从结果目录重算报告")
    rep.add_argument("--run", required=True)
    rep.add_argument("--no-charts", action="store_true")
    rep.set_defaults(func=cmd_report)

    doc = sub.add_parser("doctor", help="环境自检")
    doc.set_defaults(func=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
