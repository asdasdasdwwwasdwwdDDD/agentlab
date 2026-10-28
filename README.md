# AgentLab · 可复现的 Agent / RL 环境评测栈

> 一个从 **benchmark 调研 → 复现 → 新 benchmark 设计 → 评测/RL 环境** 全链路落地的工程项目。
> 无需 API key 即可端到端运行；接入真实模型只需设置 `OPENAI_BASE_URL` / `OPENAI_API_KEY`。

**在线浏览**：[可交互运行流程图](https://asdasdasdwwwasdwwdddd.github.io/agentlab/agentlab-flow.html) · [项目首页](https://asdasdasdwwwasdwwdddd.github.io/agentlab/)

`AgentLab` 不是一个跑分榜单，而是一套**可读、可改、可验证**的评测骨架：

- **任务即数据**：一个目录 = 指令 + 初始文件 + 工具 + 预算 + 扰动 + 判分 + 参考解。
- **判分即代码**：12 种确定性检查项（文件/状态/命令/工具调用/Python），加权聚合 + `required` 一票否决。
- **环境即状态机**：`reset()/step()/snapshot()`，支持故障注入、静默漂移、澄清预算、工具调用与预算。
- **指标即公式**：SR/Wilson、无偏 pass@k、RRS、ES、CQ、REBOUND 综合分、9 类失败归因。
- **RL 同源**：评测环境直接暴露 Gym 风格接口与 shaped reward，可批量产出轨迹数据集。

---

## 1. 30 秒快速开始

```powershell
# 0) 依赖：Python 3.10+，pip install pydantic PyYAML httpx rich matplotlib pytest
python -m agentlab doctor                      # 环境自检（shell、任务数、模型配置）
python -m agentlab list                        # 列出全部任务
python -m agentlab validate --workers 4        # 用 oracle 证明每个任务可解、判分不误杀
python -m agentlab run --suite rebound --agent scripted --policy oracle --samples 2
python -m agentlab report --run experiments/results/<run_id>
```

一键复现（测试 + 自检 + 对照实验 + RL 数据）：

```powershell
python scripts/run_all.py
```

接入真实模型（任意 OpenAI 兼容端点）：

```powershell
$env:OPENAI_API_KEY="sk-..."
$env:OPENAI_BASE_URL="https://api.deepseek.com/v1"   # 或 vLLM / Ollama / OpenAI
python -m agentlab run --suite rebound --agent react --model deepseek-chat --samples 3 --workers 2
```

> ⚠️ **安全边界**：默认 `local` backend 在宿主机子进程执行命令，**不是安全沙箱**。
> 只应运行自己编写的任务；接入真实模型前请换容器/VM 隔离（README §8）。

---

## 2. 它解决了什么问题

| 岗位职责 | 本项目的对应实现 |
|---|---|
| Benchmark 调研与复现 | `docs/benchmark-survey.md`（595 行，逐 benchmark 拆解任务设计/环境/指标/判分/harness）、`docs/benchmark-matrix.md`（40+ 基准对照）、`docs/reproduction.md`（机制→代码映射） |
| 评测 Pipeline 搭建 | `agentlab/eval/runner.py`（并行、预算、超时、异常隔离、轨迹落盘）、`report.py`（聚合+图表+markdown）、`cli.py` |
| RL / Agent Environment | `agentlab/rl/env.py`（Gym API、terminal/shaped/binary reward）、`envs/shell.py`、`envs/faults.py`、`scripts/rollout_dataset.py` |
| 新 Benchmark 探索 | **REBOUND-Bench**：故障恢复 / 环境漂移 / 欠定澄清 / 预算效率四轴 + 综合分；设计文档 `docs/gaps-and-proposal.md` |
| 评测分析与优化 | 9 类失败归因、`report.md` 逐任务失败检查、轨迹 JSON 可回放、按难度/suite/agent 切片、`docs/experiment-report.md` |

---

## 3. 项目结构

```
agentlab/                     # 评测框架（约 3.5k 行）
  core/     types, spec(YAML schema), registry, metrics, taxonomy, trajectory
  envs/     shell(终端/工具), faults(故障/漂移), fsutil(快照/路径约束)
  verifiers/checks(12 种检查项), grader(加权判定)
  agents/   scripted(oracle/fragile/retry/silent/early_stop), react(文本协议), parsing
  models/   mock(离线), openai_compat(任意兼容端点)
  eval/     runner, report, validate
  rl/       AgentEnv (Gym 风格 + reward shaping)
suites/                       # 18 个任务，4 个环境域
  terminal-lite/  6  文件/日志/CSV/备份/端口诊断
  repo-fix/       4  真实小仓库 bugfix（隐藏测试判分）
  tool-use/       4  多工具决策（mock 工具 + 状态断言）
  rebound/        4  故障 / 漂移 / 澄清 / 预算
docs/                         # 调研、设计、实验、复现说明
experiments/results/          # 每次运行的 results.jsonl / 轨迹 / 报告 / 图表
scripts/                      # run_all / run_experiment / rollout_dataset
tests/                        # 106 个测试（单元 + 模型协议 + 任务契约 + 端到端）
```

## 4. 一个任务长什么样

```yaml
id: rb-fault-retry
name: 瞬时故障下的重试与数据汇总
category: rebound
difficulty: easy
prompt: |
  ...（给 agent 的指令）
max_steps: 8
workspace:
  files:
    data/orders.csv: "order_id,amount\nA001,19.99\n..."
tools: [shell, read_file, list_dir, write_file]
budget: {max_tool_calls: 8, oracle_tool_calls: 2}
faults:
  - at_step: 1
    axis: fault
    kind: block_command
    match: "python"
    announce: true
    note: "包索引瞬时不可用，请重试"
verifier:
  checks:
    - {name: summary_exists, kind: file_exists, path: out/summary.json}
    - {name: summary_values, kind: python, func: check_summary, weight: 2.0}
solution:
  actions:
    - {kind: read_file, args: {path: data/orders.csv}}
    - {kind: shell, args: {command: "python -c '...'"}}
    - {kind: finish, args: {message: done}}
```

写任务 → `validate` → 进实验，全流程不需要改框架代码。完整 schema 见 `docs/DESIGN.md §4`。

---

## 5. REBOUND-Bench：把"韧性"变成可测量的指标

现有 benchmark 默认环境是静态的、指令是充分的、预算是不计的；模型"一次做对"的分数掩盖了
**出错后能不能恢复、环境变了会不会重新观察、信息不足时敢不敢问、能不能在预算内完成**。

| 轴 | 注入方式 | 指标 | 定义 |
|---|---|---|---|
| fault | 删除/改坏文件、阻塞一次命令 | **RRS** | 有 fault 的 episode 成功率；对照 clean SR 得 `recovery_lift` |
| drift | 静默改文件、`announce=false` | **DRS** | 有 drift 的 episode 成功率 |
| ambiguity | `ask_user` + 澄清预算 + 必答项 | **CQ** | `min(1, 命中提问数 / required_clarifications)` |
| budget | `max_tool_calls/tokens/wall_s` | **ES** | `success × clip(1 − (used−oracle)/(cap−oracle), 0, 1)` |

综合分：`0.40·SR + 0.25·RRS + 0.20·mean(ES) + 0.15·CQ`。

关键设计：**判分只看 workspace 终态与工具副作用**，不看 agent 自述；fault 只触发一次（重试即可恢复），
drift 不发出任何提示（必须重新观察）；澄清质量与内容正确性分开检查，防止"猜对也算对"。

---

## 6. 实验结果（synthetic，可复现）

> 环境：Windows 11 / Python 3.12 / 本机无 LLM key。agent 为脚本化策略或 mock 模型，
> 目的是**验证 harness 的区分度与指标口径**，不是模型能力排名。数字由 `scripts/run_experiment.py` 生成。

| 变体 | 行为 | n | SR | RRS | 平均 calls | REBOUND |
|---|---|---|---|---|---|---|
| `oracle` | 按参考解重放 | 36 | 100% | 100% | 3.00 | 1.000 |
| `fragile` | 遇错即放弃 | 8 | 50% | 0% | 1.00 | 0.450 |
| `retry` | 失败后重试 | 8 | 100% | 100% | 2.50 | 0.970 |
| `silent` | 跳过澄清直接猜 | 8 | 75% | 100% | 1.50 | 0.700 |
| `early-stop` | 提前交卷 | 8 | 0% | 0% | 0.75 | 0.150 |
| `react-noise` | ReAct + 30% 行为噪声 | 36 | 44.4% | 50% | 3.06 | 0.458 |

噪声下分环境成功率：terminal-lite 75.0% > repo-fix 50.0% ≈ rebound 37.5% > tool-use 0.0%——
长依赖链（4–11 次工具调用）最脆弱。`fragile` 与 `retry` 的对照直接验证了恢复率指标：
clean 任务上都是 100%，故障注入后 RRS 从 0% 跳到 100%。

完整表格、逐任务失败检查、恢复/漂移分解与图表见 `experiments/results/comparison.md` 和
各 run 的 `report.md`。**先看 `oracle` 是否 100%**——不是 100% 就先修任务或判分，再看模型差异。

---

## 7. 判分与可复现性

- 每 episode 独立 workspace，结束后做 sha256 快照；`results.jsonl` 一行摘要，`episodes/*.json` 全轨迹。
- `run_meta.json` 记录任务指纹、Python/平台、运行配置；任务改动会导致指纹变化，结果不可静默复用。
- 失败归因 9 类：`error > gave_up > budget > timeout > loop > no_attempt > fault_unrecovered > wrong_output > incomplete`。
- 报告标注 synthetic；不会把 mock 结果当模型结论。

## 8. 局限与安全

- **无隔离**：`local` backend 直接执行 shell。生产请实现 `SandboxBackend`（Docker/firecracker）并禁用网络。
- **无官方数据集**：没有导入 Terminal-Bench / SWE-bench / GAIA 原始数据，任务为自建；复现的是机制而非榜单分数。
- **小样本**：18 个任务、每任务 1–2 样本，Wilson 区间很宽；结论只能用于工程验证。
- **无浏览器/VM**：WebArena/OSWorld 只做到接口级（见 `docs/reproduction.md`）。
- **用户模拟器**是规则匹配，不是 LLM；τ-bench 的 pass^k 协议未实现。

## 9. 路线图

1. `SandboxBackend`：Docker + network-lock + 资源限制（对齐 Terminal-Bench/OSWorld 隔离语义）。
2. 官方数据集导入器：Terminal-Bench task 目录、SWE-bench instance、GAIA JSONL → `TaskSpec`。
3. 多 trial `pass^k` 与 bootstrap 置信区间；`budget_fail_rate`、`mean(ES|success)` 双报。
4. 浏览器 backend（Playwright）复现 WebArena 的状态型判分。
5. 真实模型基线（≥2 个模型 × 3 次采样）与失败模式人工审阅。

## 10. 文档索引

| 文档 | 内容 |
|---|---|
| [`docs/benchmark-survey.md`](docs/benchmark-survey.md) | 8+ 个前沿 benchmark 的深度调研（任务/环境/指标/判分/harness） |
| [`docs/benchmark-matrix.md`](docs/benchmark-matrix.md) | 40+ 基准对比矩阵 + 判分设计模式 + 失效模式 |
| [`docs/gaps-and-proposal.md`](docs/gaps-and-proposal.md) | 11 个 gap 的证据链 + REBOUND-Bench 完整提案（公式/YAML/消融/效度） |
| [`docs/DESIGN.md`](docs/DESIGN.md) | 实现契约：数据模型、任务 schema、检查项、指标公式 |
| [`docs/reproduction.md`](docs/reproduction.md) | 各 benchmark 机制 → 本仓库代码的映射与复现程度 |
| [`docs/experiment-report.md`](docs/experiment-report.md) | 实验报告：设置、结果、失败分析、效度威胁 |
| `experiments/results/comparison.md` | 对照实验自动生成结果 |
