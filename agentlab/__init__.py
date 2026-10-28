"""AgentLab: 可复现的 Agent / RL 评测骨架。

模块划分见 docs/DESIGN.md。顶层只暴露稳定 API，内部实现可以自由调整。
"""

from agentlab.core.types import Action, Episode, Observation, Step, Verdict
from agentlab.core.spec import TaskSpec, load_task

__all__ = [
    "Action",
    "Episode",
    "Observation",
    "Step",
    "Verdict",
    "TaskSpec",
    "load_task",
    "__version__",
]

__version__ = "0.1.0"
