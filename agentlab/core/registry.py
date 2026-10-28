"""任务注册表：扫描 suites/ 并加载全部任务包。"""

from __future__ import annotations

from pathlib import Path

from agentlab.core.spec import LoadedTask, SpecError, load_task


class Registry:
    def __init__(self, suites_dir: Path):
        self.suites_dir = Path(suites_dir)
        self._tasks: dict[str, LoadedTask] = {}
        self.errors: list[str] = []

    def scan(self) -> "Registry":
        self._tasks.clear()
        self.errors.clear()
        if not self.suites_dir.is_dir():
            return self
        for task_yaml in sorted(self.suites_dir.glob("*/*/task.yaml")):
            try:
                task = load_task(task_yaml)
            except SpecError as exc:
                self.errors.append(f"{task_yaml}: {exc}")
                continue
            if task.id in self._tasks:
                self.errors.append(f"任务 id 重复: {task.id} ({task_yaml})")
                continue
            self._tasks[task.id] = task
        return self

    def __len__(self) -> int:
        return len(self._tasks)

    def all(self) -> list[LoadedTask]:
        return sorted(self._tasks.values(), key=lambda t: (t.suite, t.spec.difficulty, t.id))

    def suites(self) -> list[str]:
        return sorted({t.suite for t in self._tasks.values()})

    def by_suite(self, suite: str) -> list[LoadedTask]:
        return [t for t in self.all() if t.suite == suite]

    def get(self, task_id: str) -> LoadedTask:
        if task_id not in self._tasks:
            raise KeyError(f"未知任务: {task_id}")
        return self._tasks[task_id]

    def select(self, suite: str | None = None, task_ids: list[str] | None = None) -> list[LoadedTask]:
        tasks = self.by_suite(suite) if suite else self.all()
        if task_ids:
            wanted = set(task_ids)
            missing = wanted - {t.id for t in tasks}
            if missing:
                raise KeyError(f"suite {suite!r} 中不存在任务: {sorted(missing)}")
            tasks = [t for t in tasks if t.id in wanted]
        return tasks


def default_suites_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "suites"
