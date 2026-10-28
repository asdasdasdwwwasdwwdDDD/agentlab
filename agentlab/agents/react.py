"""ReAct 风格 Agent：文本协议 + 有限格式重试 + observation 截断。

协议：模型每轮只输出一个 JSON 动作块（```json {"kind": ..., "args": {...}} ```）。
真实模型经常漂移（多余解释、XML、顶层参数），parse_action 做了有限归一化，
仍失败时再给一次"格式纠正"机会，避免一次解析失败就结束整个 episode。
"""

from __future__ import annotations

import json
from typing import Any

from agentlab.agents.parsing import parse_action
from agentlab.core.spec import LoadedTask
from agentlab.core.types import Action, Step
from agentlab.models.base import ModelClient

MAX_OBS_CHARS = 4000

SYSTEM_PROMPT = """你是一个在受限 workspace 中执行任务的终端 Agent。

可用动作（每次输出一个 JSON 对象，放在 ```json 代码块里）：
- {"kind":"shell","args":{"command":"<命令>"}}          在 workspace 根目录执行命令
- {"kind":"read_file","args":{"path":"<相对路径>"}}     读取文件
- {"kind":"write_file","args":{"path":"<相对路径>","content":"<内容>"}}  写文件
- {"kind":"list_dir","args":{"path":"<相对路径，默认'.'>"}}
__TOOL_LINES__
- {"kind":"ask_user","args":{"question":"<问题>"}}      向用户澄清（若可用，有次数限制）
- {"kind":"finish","args":{"message":"<一句话总结>"}}    认为任务完成时使用
- {"kind":"give_up","args":{"reason":"<原因>"}}         无法完成时使用

规则：
1. 每轮只输出一个动作 JSON，不要输出思考过程之外的额外格式；不要编造命令输出。
2. 先观察（list_dir / read_file）再动手；命令失败时读取 stderr 并修正，不要重复同一条失败命令。
3. 环境可能在执行过程中发生变化：关键文件在依赖前应重新读取确认。
4. 任务完成前自查交付物（存在、内容、格式、边界值），确认后再 finish。
5. 只在 workspace 内使用相对路径；没有网络访问。
"""


class ReActAgent:
    def __init__(self, model: ModelClient, task: LoadedTask, temperature: float = 0.0, max_format_retries: int = 1):
        self.model = model
        self.task = task
        self.temperature = temperature
        self.max_format_retries = max_format_retries
        self.name = f"react/{getattr(model, 'name', 'model')}"
        self.model_name = str(getattr(model, "name", "unknown"))
        self.messages: list[dict[str, str]] = []
        self._started = False
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._cost = 0.0
        self._format_errors = 0

    # ------------------------------------------------------------------ prompt
    def _system_prompt(self) -> str:
        lines = []
        for tool in self.task.spec.tools:
            if tool.kind == "builtin":
                continue
            desc = tool.description or "(无描述)"
            lines.append(f'- {{"kind":"tool","args":{{"name":"{tool.name}","args":{{...}}}}}}  {desc}')
        tool_lines = "\n".join(lines) if lines else ""
        names = ", ".join(self.task.spec.tool_names)
        return SYSTEM_PROMPT.replace("__TOOL_LINES__", tool_lines) + f"\n本任务可用工具: {names}\n"

    # --------------------------------------------------------------------- act
    def act(self, observation: str) -> Action:
        obs = _truncate(observation)
        if not self._started:
            self.messages = [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": f"任务:\n{self.task.spec.prompt}\n\n初始观测:\n{obs}"},
            ]
            self._started = True
        else:
            self.messages.append({"role": "user", "content": f"观测:\n{obs}"})

        for attempt in range(1 + self.max_format_retries):
            response = self.model.chat(self.messages, temperature=self.temperature)
            self._accumulate(response)
            action = parse_action(response.text)
            self.messages.append({"role": "assistant", "content": response.text or ""})
            if action is not None:
                return action
            self._format_errors += 1
            self.messages.append(
                {
                    "role": "user",
                    "content": "格式错误：只能输出一个 ```json 动作块，例如 {\"kind\":\"shell\",\"args\":{\"command\":\"ls\"}}。请重试。",
                }
            )
        return Action(kind="finish", args={"message": "多次格式错误，提前结束"}, raw="format_error")

    def observe(self, step: Step) -> None:
        return None

    def usage(self) -> dict[str, float]:
        return {
            "prompt_tokens": self._prompt_tokens,
            "completion_tokens": self._completion_tokens,
            "cost_usd": self._cost,
        }

    def _accumulate(self, response: Any) -> None:
        self._prompt_tokens += int(getattr(response, "prompt_tokens", 0) or 0)
        self._completion_tokens += int(getattr(response, "completion_tokens", 0) or 0)
        self._cost += float(getattr(response, "cost_usd", 0.0) or 0.0)
        if len(self.messages) > 18:
            system = self.messages[0]
            first_user = self.messages[1]
            self.messages = [system, first_user, {"role": "user", "content": "（历史观测已截断，仅保留最近交互）"}] + self.messages[-12:]

    def describe(self) -> dict[str, Any]:
        return {
            "agent": self.name,
            "format_errors": self._format_errors,
            "max_obs_chars": MAX_OBS_CHARS,
        }


def _truncate(text: str, limit: int = MAX_OBS_CHARS) -> str:
    if len(text) <= limit:
        return text
    head = limit // 2
    tail = limit - head
    return f"{text[:head]}\n...[观测截断 {len(text) - limit} 字符]...\n{text[-tail:]}"


def dumps_action(action: Action) -> str:
    return json.dumps({"kind": action.kind, "args": action.args}, ensure_ascii=False)
