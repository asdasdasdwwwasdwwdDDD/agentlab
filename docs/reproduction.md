# Benchmark 机制复现说明

> 目标不是"把 Terminal-Bench 原样搬一遍"，而是把每个主流 benchmark 的**关键机制**在
> AgentLab 里实现成可运行、可判分、可复用的组件，并明确当前复现到什么程度、差距在哪里。
> 逐条事实与引用见 `docs/benchmark-survey.md`，本文件只讲"对应到代码的哪一层"。

## 0. 复现程度分级

| 级别 | 含义 |
|---|---|
| **机制级** | 任务 schema、环境交互、判分逻辑都能在本仓库跑通，可用自己的任务集验证 |
| **接口级** | 抽象/协议就位，但缺少真实后端（浏览器、VM、真实 SaaS） |
| **未复现** | 只有文档分析，无代码 |

## 1. 对照表

| Benchmark | 核心机制 | AgentLab 中的实现 | 级别 | 差距 |
|---|---|---|---|---|
| Terminal-Bench | 自然语言指令 + 容器内终端 + 预写测试判分；任务即目录 | `envs/shell.py`（子进程终端、超时、输出截断）+ `core/spec.py` 任务包 + `verifiers/checks.py`（`shell`/`file_*`/`python`）+ `suites/terminal-lite/` | 机制级 | 无容器隔离；无多阶段测试权重；任务规模小 |
| SWE-bench | 仓库快照 + issue + FAIL_TO_PASS/PASS_TO_PASS 隐藏测试 | `suites/repo-fix/`：`files/` 放仓库快照，`checks.py` 用 `importlib`/`sys.path` 直接跑隐藏测试，`state_unchanged` 防止改测试作弊 | 机制级 | 无 per-repo 环境镜像；无真实 PR 数据；无 P2P 回归集规模 |
| Toolathlon / Tool Decathlon | 多 App、多 MCP 工具、长程组合调用；按应用最终状态判分 | `envs/shell.py` 的 mock tool（`mock_tool` + `effect`）、`tool_called` 检查、`suites/tool-use/` | 机制级 | mock 工具而非真实 SaaS/MCP server；任务长度短 |
| GAIA | 真实世界问题、三级难度、答案精确匹配、允许浏览/工具 | 判分侧支持 JSON 精确/正则/`python` 断言；`answer` 类任务可写成 `file_equals` | 接口级 | 未提供 GAIA 数据与浏览器/文件工具组合；未实现官方 evaluator 的规范化答案规则 |
| WebArena / VisualWebArena | 真实网站 + 浏览器动作空间 + 状态型判分（DB/页面断言） | `state_changed`/`state_unchanged` 的 workspace 状态快照可迁移为 DB 状态断言 | 接口级 | 无 Playwright/浏览器后端；无站点镜像 |
| OSWorld | VM + 键鼠/截图 + 执行型验证脚本 | `ShellEnv` 可承载 OS 级命令；`Environment` 协议可换 backend | 接口级 | 无 VM/截图/多应用；无 desktop action 空间 |
| AgentBench | 多环境（OS/DB/KG/Web/卡牌…）统一 agent 协议 | 统一 `Action`/`Environment`/`Agent` 协议 + `Registry` 按 suite 扩展 | 机制级 | 只实现 terminal/repo/tools 三类环境 |
| τ-bench | 用户模拟器 + 工具调用 + pass^k | `ask_user` + `ambiguity`（澄清预算、必答项、CQ 指标）+ `pass@k` 无偏估计 | 机制级 | 用户模拟器是规则匹配而非 LLM；未实现官方 pass^k 多 trial 协议 |
| BFCL | 函数调用 AST/可执行匹配 | `parse_action` 的宽容归一化 + `tool_called` 检查 | 接口级 | 无 BFCL 数据集与官方 AST 指标 |

## 2. 关键机制是怎么落地的

### 2.1 任务 = 目录 + 声明式 YAML + 可选 checks.py

和 Terminal-Bench 的 "task 目录" 一样，一个任务自包含：指令、初始文件、工具集、预算、
扰动、判分检查、参考解。加载期做严格 schema 校验（`extra=forbid`），任何拼写错误直接报错，
避免"任务写错了但静默 0 分"这种 benchmark 维护灾难。

### 2.2 判分 = 确定性检查项组合

SWE-bench 的教训是：判分必须基于**执行结果**而不是模型自述。AgentLab 的 `Verdict` 由
`checks` 列表加权聚合，`required` 决定是否一票否决；`python` 检查项拿到 `CheckContext`
（workspace、状态快照、工具日志、动作序列），可以写任意严格断言，但**拿不到 solution**。

### 2.3 环境 = 可重置 workspace + 可注入扰动

- `reset()`：建 workspace、写入初始文件、做 sha256 快照。
- `step()`：执行动作、截断输出、记录 `info`（exit code / timeout / injected）。
- `FaultInjector`：按 `at_step` 注入 `fault`（需要恢复）与 `drift`（静默变化），
  这是 Terminal-Bench / WebArena 这类"环境会动"的 benchmark 里最容易被忽略的维度。
- 判分前再快照一次，`state_changed` / `state_unchanged` 就能做"副作用"断言。

### 2.4 Agent = 文本协议 + 动作解析

复现 AgentBench/GAIA 的 agent 侧差异时，把"模型怎么想"与"环境怎么执行"分开：
`ReActAgent` 只负责把模型文本解析成 `Action`，格式漂移（XML/fenced/顶层参数）在
`agents/parsing.py` 归一化；失败给一次纠正机会。这样换模型不需要改环境。

## 3. 从复现到新 benchmark：REBOUND-Bench

调研中反复出现的四个空白：① 只测"一次做对"，不测**故障后恢复**；② 环境默认静态，
不测**漂移下的重新观察**；③ 信息缺失时鼓励猜，不度量**澄清质量**；④ 只看成功率，
不看**预算内的效率**。REBOUND-Bench 把四者做成可度量的轴：

| 轴 | 机制 | 指标 |
|---|---|---|
| fault | `faults[].kind ∈ {delete_file, write_file, append_file, remove_file_pattern, block_command, corrupt_file}` | RRS、recovery_lift |
| drift | `faults[].axis=drift`，`announce=false`，静默改文件 | DRS（drift success rate） |
| ambiguity | `ambiguity` + `ask_user` + 澄清预算 | CQ |
| budget | `budget.max_tool_calls / max_tokens / max_wall_s` | ES |

综合分 `0.40·SR + 0.25·RRS + 0.20·ES + 0.15·CQ`；完整定义、任务 schema、baseline 与
效度威胁见 `docs/gaps-and-proposal.md`。

## 4. 复现一个 benchmark 的标准步骤（可复用 recipe）

1. **读官方 harness**：确认它怎么起环境、怎么 reset、判分读什么状态（文件/DB/HTTP/截图）。
2. **映射到 AgentLab**：任务包 → `TaskSpec`；环境 → 新 `Environment` backend；判分 →
   `checks.py` + `verifier.checks`；预算/步数 → `budget`/`max_steps`。
3. **先写 oracle**：`solution.actions` 必须 100% 通过；跑 `python -m agentlab validate`。
4. **做负向测试**：故意写"看似合理但错误"的解，确认检查项会拒绝（防假阳性）。
5. **对齐口径**：把官方的 primary metric 映射到 SR/RRS/ES，并在报告里注明差异。
6. **留档**：在 `docs/benchmark-survey.md` 补一节、在 `docs/experiment-report.md` 记录数字。

## 5. 当前明确未做的部分

- 容器/VM/浏览器隔离（`SandboxBackend` 接口未实现，只有 `local` 子进程）。
- 官方数据集导入器（Terminal-Bench / SWE-bench / GAIA 的原始格式转换）。
- 多 trial 的 pass^k 协议、统计显著性检验（当前只有 Wilson 区间与无偏 pass@k）。
- LLM-as-judge 的辅助评分（刻意不放进主指标，避免不可复现）。
