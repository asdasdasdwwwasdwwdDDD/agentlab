# AgentLab 架构设计（实现契约）

> 本文件是 **代码与任务数据的唯一契约**。所有实现与任务作者都必须以此为准；如需变更，
> 先改本文件并在 PR/提交说明里写清迁移影响。

## 1. 目标与非目标

**目标**

1. 一套可复用的 **Agent / RL 评测骨架**：任务加载 → 环境初始化 → 模型/Agent 循环 → 轨迹记录 →
   自动判分 → 指标聚合 → 报告。
2. 环境是可交互、可重置、可注入扰动的：支持 terminal、repo-fix、tool-use 三类环境，
   并额外支持 fault / drift / ambiguity / budget 四个扰动轴（REBOUND-Bench）。
3. 判分完全可复现：verifier 是确定性的、由任务作者声明的检查项组合；LLM-judge 只作为
   可选补充，不参与主指标。
4. 零外部依赖即可跑通：`mock` 模型与脚本化 agent 让整条 pipeline 在没有 API key 的机器上
   端到端可运行。

**非目标（明确不做，避免过度承诺）**

- 不做安全沙箱。默认 `local` backend 在临时目录里执行 shell，**不是**强隔离。生产环境应
  替换成 Docker / firecracker backend（`SandboxBackend` 已预留接口）。README 必须写明该限制。
- 不追求 SOTA 数字。mock agent 的分数只用来说明 pipeline 能区分行为，**不能**作为模型能力结论。
- 不实现分布式调度、数据库、Web UI。

## 2. 目录结构

```
agentlab/                     # Python 包（flat layout，无需安装即可 python -m agentlab）
  core/                       # 类型、任务加载、注册表、轨迹 I/O、指标、失败分类
  envs/                       # Environment 实现：shell / tool / faults
  models/                     # 模型客户端：mock 与 OpenAI 兼容
  agents/                     # Agent：scripted / react
  verifiers/                  # 检查项实现与 grader
  eval/                       # runner（并行、预算、重试）与 report（聚合、图表）
  rl/                         # Gym 风格环境封装（reward 与 verifier 同源）
  cli.py
suites/<suite>/<task_id>/     # 任务包（数据），每个包一个目录
  task.yaml
  checks.py                   # 可选：python 检查项
  files/                      # 可选：需要复制进 workspace 的初始文件
docs/                         # 调研、设计、实验报告
experiments/results/<run_id>/ # 运行产物：results.jsonl / episodes/ / workspaces/ / report
scripts/                      # 一键实验脚本
tests/                        # pytest
```

## 3. 运行时数据模型（`agentlab/core/types.py`）

```python
Action:      kind ∈ {shell, read_file, write_file, list_dir, ask_user, tool, finish, give_up}
             args: dict, raw: str | None
Step:        idx, action, observation, reward_hint, done, info, t_ms
Episode:     run_id, task_id, suite, category, difficulty, agent, model, sample_idx,
             status ∈ {success, failure, error, timeout, budget},
             verdict: Verdict, steps: list[Step], n_steps, n_tool_calls,
             prompt_tokens, completion_tokens, wall_ms, cost_usd,
             faults: list[FaultEvent], clarifications: int, metrics: dict, error: str|None
Verdict:     success: bool, score: float ∈ [0,1], checks: list[CheckResult], message: str
CheckResult: name, kind, passed, weight, required, detail, severity ∈ {ok, warn, error}
```

轨迹落盘：每个 episode 一个 JSON（`episodes/<task>__s<sample>.json`，含完整 steps），
一行一个 episode 摘要（`results.jsonl`）。**不记录**任何 API key。

## 4. 任务包格式（`task.yaml`）

```yaml
id: term-fs-01                # 全局唯一；目录名必须等于 id
name: 日志归档与清洗
category: terminal            # terminal | repo | tools | rebound
difficulty: easy              # easy | medium | hard
tags: [fs, shell, csv]
visibility: public            # public | hidden（hidden 任务用于防污染，不计入公开集）

prompt: |                     # 给 agent 的自然语言任务（不含答案）
  在 workspace 里完成……

max_steps: 12                 # 单 episode 最大动作数
timeout_s: 90                 # 单条 shell 命令超时（秒），不是整局

workspace:
  copy_files: true            # 把本任务包 files/ 复制进 workspace
  files:                      # 也可内联写入（路径相对 workspace 根）
    config/app.ini: |
      [server]
      port = 8080

tools: [shell, read_file, write_file, list_dir]   # 允许的动作；shell 必须显式声明

budget:                       # 可选；缺省用全局默认
  max_tool_calls: 16
  max_tokens: 30000
  max_wall_s: 300
  oracle_tool_calls: 5        # 用于效率分归一化（任务作者填 oracle 的调用数）

faults:                       # 可选；REBOUND 用。按 step 序号触发（在第 at_step 步执行前生效）
  - at_step: 2
    axis: fault               # fault | drift
    kind: delete_file         # delete_file | write_file | append_file | remove_file_pattern
                              # | block_command | corrupt_file | drift_write
    path: config/app.ini
    content: "..."            # write / corrupt 用
    match: "flask run"        # block_command 用（正则）
    announce: true            # true=环境主动报错；false=静默漂移（agent 必须重新观察）
    note: "模拟配置文件被回滚"

ambiguity:                    # 可选；欠定任务
  clarification_budget: 2
  answers:
    - match: "端口|port"       # 正则，命中即答
      reply: "生产端口是 8080"
    - default: "这个信息不能透露"
  required_clarifications: 1  # 至少要问几次才算信息获取充分（计入 CQ）

verifier:
  pass_threshold: 1.0         # 所有 required 检查必须通过；score 阈值兜底
  checks:
    - name: report_exists
      kind: file_exists
      path: report/summary.md
      weight: 1.0
      required: true
    - name: report_content
      kind: file_contains
      path: report/summary.md
      pattern: "total_rows:\\s*120"
    - name: custom_logic
      kind: python
      func: check_schema        # 对应 checks.py 中的 def check_schema(ctx)
      weight: 2.0

solution:                     # 供 oracle agent / validate 使用
  actions:
    - kind: shell
      command: python -c '...'
```

### 4.1 检查项（verifier checks）

| kind | 参数 | 语义 |
|---|---|---|
| `file_exists` | `path` | workspace 内文件存在 |
| `file_absent` | `path` | 不存在 |
| `dir_exists` | `path` | 目录存在 |
| `file_contains` | `path`, `pattern`, `flags?` | 正则搜索，命中即通过 |
| `file_not_contains` | `path`, `pattern`, `flags?` | 正则不命中 |
| `file_equals` | `path`, `content` 或 `content_file` | 内容精确相等（去除尾部换行差异） |
| `file_line_count` | `path`, `min?`, `max?` | 行数范围 |
| `shell` | `command`, `expect_exit=0`, `stdout_contains?`, `timeout_s?` | 在 workspace 内执行并断言 |
| `state_changed` | `paths` | 与初始快照相比内容变化 |
| `state_unchanged` | `paths` | 与初始快照相比未变化（防误伤） |
| `tool_called` | `tool`, `min_times=1`, `args_contains?` | 工具调用日志断言 |
| `python` | `func`, `args?` | 调用 `checks.py` 的函数，返回 `bool` / `(bool, str)` / `dict` |

`python` 检查项收到 `CheckContext`：

```python
ctx.task, ctx.workspace (Path), ctx.state_before, ctx.state_after,
ctx.tool_log (list[dict]), ctx.actions (list[Action]), ctx.meta (dict)
ctx.read("rel/path") -> str      # 越界会抛错
ctx.exists("rel/path") -> bool
```

**判分规则**：`score = Σ(weight·passed) / Σweight`；`success = 所有 required 通过 and score >= pass_threshold`。
检查项本身抛异常 → 记 `severity=error`, `passed=False`，episode 仍正常收尾（不得静默吞掉，需在结果中可见）。

### 4.2 快照与状态断言

环境在 `reset()` 后对 workspace 做 sha256 快照（`state_before`），episode 结束后再做一次（`state_after`）。
`state_changed` / `state_unchanged` 基于该快照，忽略 `.agentlab/` 与 `__pycache__`。

## 5. 环境协议（`agentlab/envs/base.py`）

```python
class Environment(Protocol):
    def reset(task: TaskSpec, workspace: Path) -> Observation
    def step(action: Action) -> StepResult          # observation, done, info, reward_hint
    def close() -> None
    def snapshot() -> dict[str, str]
    tool_names: list[str]
```

`Observation` = `{text: str, data: dict}`；文本即模型看到的 observation（含 exit code、截断后的
stdout/stderr、被注入事件的可见提示）。

实现：

- `ShellEnv`：临时 workspace + subprocess 执行。Windows 用 `pwsh -NoProfile -NonInteractive -Command`，
  POSIX 用 `/bin/sh -c`。输出截断保留头 6KB + 尾 6KB。动作：`shell` / `read_file` / `write_file` /
  `list_dir` / `ask_user` / `finish` / `give_up`。文件类动作强制路径在 workspace 内（realpath 校验）。
- `ToolEnv`：在 `ShellEnv` 之上挂载任务声明的 mock 工具（`tools:` 段扩展为对象列表时启用），
  工具调用写入 `tool_log`，可产生状态副作用（如 `create_ticket`）。
- `FaultInjector`：在 `step()` 之前按 `at_step` 消费 faults；`block_command` 通过匹配命令正则
  注入一次性失败；`drift_*` 静默修改文件。每次注入追加 `FaultEvent` 到 episode。

`tools` 的两种写法：

```yaml
tools: [shell, read_file]                 # 简写：内置动作
tools:                                    # 全写：内置 + mock 工具
  - name: shell
  - name: search_docs
    kind: mock_tool
    description: "搜索内部文档"
    mock:
      - match: "退款|refund"
        response: "退款政策：7 天内可退……"
      - default: "未找到相关文档"
  - name: create_ticket
    kind: mock_tool
    description: "创建工单"
    effect: {ticket: true}                # 记录到 env state，供 verifier 检查
```

## 6. Agent 与模型

```python
class Agent(Protocol):
    name: str
    def act(observation, task) -> Action
    def observe_result(step) -> None
    def on_finish(episode) -> None
model: chat(messages, tools=..., temperature=...) -> ModelResponse(text, prompt_tokens,
        completion_tokens, cost_usd, raw)
```

- `ScriptedAgent(policy)`：`oracle` / `careless` / `fragile` / `recoverer` / `adaptive`。
  仅用于 pipeline 自检与消融，**在报告中必须标注为 synthetic**。
- `ReActAgent`：文本协议（`TOOL: shell\nARG: ...` 或 fenced code block），支持真实 OpenAI 兼容端点，
  带 observation 截断、重复动作检测、`finish` 解析。
- `MockModel`：按 task 的 `solution.actions` 回放，可配置 `noise`（丢步/改错/跳步），
  用于无 key 端到端演示。

## 7. Runner

```python
RunConfig: suite, task_ids, agent, model, samples, seeds, workers, out_dir, run_id,
           budget_overrides, mock_noise, fail_fast
```

- 任务加载 → 每 (task, sample) 一个 episode，`ThreadPoolExecutor(workers)` 并行。
- 每个 episode 独立 workspace：`<out>/workspaces/<task>__s<sample>/`。
- 预算：动作数 / tool calls / tokens / wall time；超限 → `status=budget`，仍执行 verifier 以保留部分分。
- 异常/超时 → `status=error|timeout`，记录 traceback（截断），不中断整批。
- 幂等：同一 run_id 重跑会覆盖 `results.jsonl`，episode 文件按名字覆盖。

## 8. 指标定义

- **成功率 SR**：`success/total`，附 Wilson 95% 置信区间。
- **pass@k（无偏）**：`1 - C(n-c, k) / C(n, k)`，n=samples per task，c=成功样本数。
- **恢复率 RRS**：只在注入 `axis=fault` 的 episode 上算 `success/with_fault`；并报告
  `clean SR` 作为对照，`recovery_lift = RRS - clean_SR`。
- **漂移鲁棒性 DRS**：`axis=drift` episode 的成功率。
- **效率分 ES**（per episode）：
  `ES = success × clip(1 − max(0, used_calls − oracle_calls) / max(1, cap − oracle_calls), 0, 1)`；
  `used_calls` 统计 shell + tool 动作；`oracle_calls` 取 `budget.oracle_tool_calls`，缺省用 1。
- **澄清质量 CQ**（ambiguity 任务）：`min(1, asked_useful / required_clarifications)`，
  其中 `asked_useful` 为命中 `answers.match` 的提问次数；同时记录提问总数（成本）。
- **REBOUND 综合分**：`0.40·SR + 0.25·RRS + 0.20·mean(ES) + 0.15·CQ`，每项先做 0-1 归一。
- **失败分类**（互斥，按优先级）：`gave_up` > `budget` > `timeout` > `loop` > `no_attempt` >
  `fault_unrecovered` > `wrong_output` > `incomplete` > `error`。

## 9. CLI

```
python -m agentlab list   [--suite S]
python -m agentlab validate [--suite S] [--task ID]      # 用 oracle 跑，验证任务可解 + 判分正确
python -m agentlab run --suite S --agent oracle|scripted|react --model mock|openai:MODEL
                       [--samples N] [--workers N] [--out DIR] [--noise F]
python -m agentlab report --run DIR [--open]
python -m agentlab doctor                                 # 环境自检
```

## 10. 可复现性与防作弊

- 每个 episode 记录 `seeds`、任务内容哈希、agent/model 标识、git commit（若可用）。
- `visibility: hidden` 任务只用于内部回归，公开报告不展示 prompt。
- 判分基于 workspace 终态 + 命令副作用，不基于 agent 自述；`python` 检查项禁止读 `solution`。
- 报告的 mock/synthetic 结果必须有显式标注，避免被误读为真实模型能力。

## 11. 安全边界（必须写进 README）

`local` backend 直接在宿主机子进程执行命令，仅用于评测自己编写的任务与 mock agent。
接入真实模型前必须换容器隔离，或仅在一次性机器/VM 内运行。

## 12. RL 环境接口（`agentlab/rl/env.py`）

```python
env = AgentEnv(task, workspace, reward_mode="terminal|shaped|binary",
               step_cost=0.01, success_bonus=0.0, max_steps=None)
obs = env.reset()
obs, reward, terminated, truncated, info = env.step(action)
record = env.rollout(agent)   # 返回 transitions / total_reward / verdict，可直接落盘
```

- **reward 与评测同源**：终局 reward 直接来自同一个 `grade()`，避免 reward model 与 eval
  口径漂移；`shaped` 模式用"非 shell 检查项"的分数增量做进度奖励（默认跳过 `shell`，
  避免每步执行任意命令），`binary` 只给 0/1。
- **episode 终止**：`terminated` = agent 主动 finish/give_up；`truncated` = 达到 `max_steps`
  或工具调用预算。
- **数据产出**：`scripts/rollout_dataset.py` 把 `rollout()` 结果写成 JSONL
  （`action/observation/reward/terminated/truncated/verdict`），用于 SFT 预热、reward model
  或 offline RL replay buffer。
- **注意**：轨迹默认由脚本化策略生成，只是数据格式与接口示例；用真实模型采样时必须做
  train/test 任务切分，并固定 verifier 版本。
