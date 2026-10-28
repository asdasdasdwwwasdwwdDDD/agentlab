# 实验报告：AgentLab v0.1 / REBOUND-Bench

> 日期：2026-10-26 · 代码版本：`agentlab 0.1.0` · 运行平台：Windows 11 / Python 3.12.7 / PowerShell 5.1
> 全部数字由 `scripts/run_experiment.py` 生成，产物在 `experiments/results/exp-*/`。
> **本报告不含任何真实 LLM 结果**（本机无 API key）：agent 为脚本化策略或 mock 模型。
> 结论只针对"评测流水线是否可用、指标是否有区分度"，不针对模型能力。

## 摘要

1. **可解性闸门通过**：18 个任务 × 2 样本 = 36 episodes，oracle 全部 100%（Wilson 95% CI 90.4%–100%）。
   这说明任务声明、环境和判分三者自洽，没有"任务本身做不出来/判分必错"的问题。
2. **流水线能区分行为**：同一个 rebound 任务集上，`fragile`（遇错放弃）RRS=0%、`retry`（失败重试）
   RRS=100%，恢复率增益从 −1.0 变到 0；`silent`（跳过澄清）成功率 75% 但 CQ=0。
3. **效率轴独立于成功率**：`oracle` 与 `retry` 都是 100% 成功，但 retry 平均多花 67% 的工具调用，
   ES 从 1.00 降到 0.85——说明"做对"和"做得省"确实是两个可分离的信号。
4. **ReAct 文本协议链路可用**：`react + mock(30% 噪声)` 跑完 36 episodes，SR 44.4%（CI 29.5%–60.4%），
   pass@2 72.2%，轨迹/解析/判分/报告全链路无异常。
5. **按环境难度排序符合直觉**：噪声下 terminal-lite 75% > repo-fix 50% ≈ rebound 37.5% > tool-use 0%
   （tool-use 依赖 4–11 次工具调用的长依赖链，丢一步就全错）。

## 1. 实验目的

本实验回答三个工程问题，而不是"哪个模型更强"：

- **Q1（正确性）**：任务、环境、判分是否自洽？→ oracle 闸门 + 负向策略。
- **Q2（区分度）**：指标能否区分"会恢复/不恢复""敢问/不问""做完/提前交卷""省/浪费"？
- **Q3（可复现性）**：同一条命令重跑，结果与产物是否稳定可审计？

## 2. 设置

### 2.1 任务集

| suite | 任务数 | 难度分布 | 环境交互 | 判分方式 |
|---|---|---|---|---|
| `terminal-lite` | 6 | easy 2 / medium 2 / hard 2 | shell + 文件工具，2–5 步 | 文件内容/JSON 语义/`state_unchanged` |
| `repo-fix` | 4 | medium 2 / hard 2 | 修复小仓库 bug，1–2 步写文件 | 隐藏测试（`checks.py` 内直接 import 被测模块） |
| `tool-use` | 4 | easy 1 / medium 1 / hard 2 | 4–11 次 mock 工具调用 + 副作用 | 最终 JSON + `tool_called` + 政策/状态一致性 |
| `rebound` | 4 | easy 1 / medium 3 | shell + 工具，含故障/漂移/澄清/预算 | 同左 + 恢复率/漂移/澄清质量/效率分 |

共 18 个任务，全部 `python -m agentlab validate` 通过（18/18）。任务指纹记录在每次运行的 `run_meta.json`。

### 2.2 对照矩阵

| 变体 | agent | 说明 | suites | samples |
|---|---|---|---|---|
| `oracle` | scripted/oracle | 按参考解重放（上界与闸门） | 全部 | 2 |
| `fragile` | scripted/fragile | 观测到失败立即 `give_up` | rebound | 2 |
| `retry` | scripted/retry | 失败后重复同一动作（≤3 次） | rebound | 2 |
| `silent` | scripted/silent | 跳过 `ask_user` 直接猜 | rebound | 2 |
| `early-stop` | scripted/early_stop | 跳过最后一个实质动作就交卷 | rebound | 2 |
| `react-noise` | react + mock:0.3 | 30% 概率丢步/替换动作，走完整 ReAct 文本协议 | 全部 | 2 |

### 2.3 运行环境

- 本机无 `OPENAI_API_KEY`；`react-noise` 的"模型"是确定性 `MockModel`，仅用于驱动协议链路。
- Shell backend：Windows PowerShell 5.1（`-NoProfile -NonInteractive -Command`），退出码显式透传。
- 并发 4；每 episode 独立 workspace；超时 30–90s/命令；预算见各任务 `budget`。

运行命令：

```powershell
python scripts/run_experiment.py --workers 4
python -m agentlab validate --workers 4
```

## 3. 结果

### 3.1 总表

| 变体 | n | SR | Wilson 95% CI | RRS | 平均 calls | 平均 ES | REBOUND |
|---|---|---|---|---|---|---|---|
| `oracle` | 36 | 100.0% | 90.4–100% | 100% | 3.00 | 1.000 | 1.000 |
| `fragile` | 8 | 50.0% | 21.5–78.5% | 0% | 1.00 | 0.500 | 0.450 |
| `retry` | 8 | 100.0% | 67.6–100% | 100% | 2.50 | 0.851 | 0.970 |
| `silent` | 8 | 75.0% | 40.9–92.9% | 100% | 1.50 | 0.750 | 0.700 |
| `early-stop` | 8 | 0.0% | 0–32.4% | 0% | 0.75 | 0.000 | 0.150 |
| `react-noise` | 36 | 44.4% | 29.5–60.4% | 50% | 3.06 | 0.438 | 0.458 |

> `REBOUND` 只在 rebound suite 上计算（n=8），因此 `oracle`/`react-noise` 的该列只反映 rebound 子集；
> `oracle` 与 `react-noise` 的 SR/calls 覆盖全部 4 个 suite（n=36），其余变体只跑 rebound（n=8）。
> 跨行比较 calls 时注意口径不同；同口径对比见 §3.4。

### 3.2 分环境（oracle 闸门 vs ReAct 噪声）

| suite | oracle n / SR | oracle calls / steps | react-noise n / SR | react-noise calls / steps |
|---|---|---|---|---|
| terminal-lite | 12 / 100% | 2.00 / 4.17 | 12 / 75.0% | 2.08 / 3.67 |
| repo-fix | 8 / 100% | 1.00 / 4.25 | 8 / 50.0% | 1.12 / 3.75 |
| tool-use | 8 / 100% | 8.00 / 11.00 | 8 / 0.0% | 7.62 / 9.88 |
| rebound | 8 / 100% | 1.50 / 4.00 | 8 / 37.5% | 1.88 / 3.75 |

按难度：react-noise 在 easy/medium/hard 上分别为 50.0% / 43.8% / 41.7%。噪声主导了性能衰减，
难度分层没有被拉开——这是"用 mock 噪声模拟能力"的固有局限（见 §5）。

### 3.3 恢复与漂移

| 变体 | clean SR (n) | fault SR (n) | drift SR (n) | recovery_lift |
|---|---|---|---|---|
| oracle | 100% (32) | 100% (2) | 100% (2) | 0.00 |
| fragile | 100% (4) | **0% (2)** | **0% (2)** | **−1.00** |
| retry | 100% (4) | 100% (2) | 100% (2) | 0.00 |
| silent | 50% (4) | 100% (2) | 100% (2) | +0.50 |
| early-stop | 0% (4) | 0% (2) | 0% (2) | 0.00 |
| react-noise | 43.8% (32) | 50% (2) | 50% (2) | +0.06 |

`fragile` 与 `retry` 的对照是本实验最强的信号：两者在 clean 任务上都是 100%，
唯一差别是遇到注入故障后是否重试；结果 RRS 从 0% 跳到 100%，`recovery_lift` 从 −1.0 到 0。
这证明 `faults` 注入、`FaultInjector` 的"只触发一次"语义、以及 RRS 公式确实在测量恢复行为，
而不是环境噪声。

### 3.4 效率

| 变体 | SR | 平均 calls | 平均 ES | 说明 |
|---|---|---|---|---|
| `oracle`（rebound） | 100% | 1.50 | 1.000 | 与 `oracle_tool_calls` 一致 |
| `retry`（rebound） | 100% | 2.50 | 0.851 | 为恢复多付 67% 调用 |
| `silent`（rebound） | 75% | 1.50 | 0.750 | 失败 episode 的 ES 记 0 |

ES 只在成功时给分，且相对 oracle 调用数归一；`retry` 展示了"成功但低效"这一被 SR 掩盖的维度。

### 3.5 失败归因

| 变体 | 失败模式分布 |
|---|---|
| `fragile` | `gave_up`=4, 成功=4 |
| `silent` | `no_attempt`=2, 成功=6 |
| `early-stop` | `fault_unrecovered`=4, `no_attempt`=4 |
| `react-noise` | `wrong_output`=18, `fault_unrecovered`=2, 成功=16 |

`react-noise` 的逐任务失败检查（节选）：

| task | SR | 失败检查 |
|---|---|---|
| `rb-ambiguity-port` | 0% | `clarification_done`, `manifest_content`, `manifest_exists` |
| `tool-refund-approval` | 0% | `decision_json`, `refund_side_effects`（工具调用链断） |
| `repo-invoice-round` | 50% | `all_items_and_tax`, `rounding_half_up` |
| `repo-log-rotate` | 50% | `keep_count_and_order`, `size_cap`, `tie_break_stability` |
| `rb-drift-config` | 50% | `config_restored`, `deploy_content` |

## 4. 分析与结论

**F1. oracle 闸门是必要的，不是"刷分"。** 18/18 通过意味着每个任务的 `prompt` 信息足够、
`files/` 初始状态正确、`checks.py` 不依赖不可达路径、`solution` 与 `budget` 自洽。
没有这一步，后面所有模型分数都可能被任务缺陷污染。

**F2. 恢复行为可被单独测量。** `fragile` vs `retry` 在 clean 任务上完全相同，仅在故障后分叉：
RRS 0% vs 100%。这说明"恢复率"不是成功率的同义反复，REBOUND 的核心主张在本任务集上成立。

**F3. 澄清质量与内容正确性解耦。** `silent` 写出了字段完全正确的 `manifest.json`，
但 `clarification_done` 失败（CQ=0，成功率 75%）。如果只做终态内容断言，这类"蒙对"会被误判为合格。

**F4. 长依赖链最脆弱。** tool-use 在 30% 噪声下 0% 成功，而 terminal-lite 仍有 75%。
原因是 tool-use 需要 4–11 次顺序调用且后一步依赖前一步结果（政策→订单→客户→写文件→副作用），
单点缺失即全错。这解释了为什么真实 benchmark 里 tool-use 类任务对 harness 稳定性极敏感。

**F5. 单样本评估不可信。** `react-noise` pass@1=44.4%，pass@2=72.2%。若只跑 1 个样本并据此排名，
会系统性低估能力；benchmark 报告应至少给 pass@k 或均值±区间。

**F6. 预算轴有独立信号。** 同为 100% 成功，`retry` 的 ES 比 `oracle` 低 15 个百分点。
在真实模型上，这对应"会不会无谓重试/反复读文件"，是成本优化最直接的抓手。

## 5. 效度威胁（必须与结论一起读）

1. **Synthetic agent ≠ 模型**：所有变体都是脚本或 mock，分数不反映任何真实模型能力。
   本实验只能证明"流水线能测"，不能证明"某个模型不能恢复"。
2. **样本极小**：fault/drift 各只有 2 个 episode，RRS 的 Wilson 区间会非常宽；本报告刻意同时给 n。
   要得到稳定结论，每个任务至少 5–10 次独立采样。
3. **任务作者偏差**：任务与判分由同一团队编写，verifier 可能继承作者的误解。
   缓解手段：oracle 闸门、负向策略（fragile/silent/early-stop）、以及逐任务"看似合理但错误"的解的审计。
4. **平台差异**：Windows PowerShell 5.1 的引号/退出码语义与 Linux bash 不同，
   任务命令按"双引号包裹 + 单引号字面量"的契约编写，但跨平台复现仍需在 Linux 容器里重跑一遍。
5. **无隔离**：`local` backend 直接在宿主机执行命令；真实模型接入前必须换容器，否则结果不可信且有安全风险。
6. **污染风险**：任务与参考解都在本仓库公开，若用于真实模型评测需拆出隐藏集并加 canary。
7. **难度分层失效**：mock 噪声不随任务难度变化，因此难度曲线平坦；这是 agent 设计的局限，不是任务集的。

## 6. 下一步

1. **真实模型基线**：`--agent react --model <model> --samples 3`，2 个模型 × 18 任务 × 3 样本 = 108 episodes；
   按当前平均 3 calls/episode 估算，单模型约 324 次工具调用，成本可控。
2. **容器化 backend**：Docker + network-lock + CPU/内存限制，复现 Terminal-Bench/OSWorld 的隔离语义。
3. **隐藏集与 canary**：拆 30% 任务为 `visibility: hidden`，报告中不展示 prompt，降低记忆/污染。
4. **统计升级**：多 trial `pass^k`、bootstrap CI、任务级配对检验（McNemar）。
5. **失败人工审阅**：对 20% 失败轨迹做人工归因，校准自动 taxonomy 的准确率。
6. **扩任务**：把 rebound 从 4 个扩到 12+，覆盖多故障序列、权限漂移、跨会话状态保持。

## 7. 复现

```powershell
# 1) 全量测试（106 项，含模型协议、端到端与 18 个任务的契约测试）
python -m pytest

# 2) 任务可解性闸门（必须 18/18）
python -m agentlab validate --workers 4

# 3) 对照实验 + 报告 + 图表
python scripts/run_experiment.py --workers 4

# 4) 单次评测与报告重算
python -m agentlab run --suite rebound --agent scripted --policy fragile --samples 2
python -m agentlab report --run experiments/results/<run_id>

# 5) RL 轨迹数据集（shaped reward）
python scripts/rollout_dataset.py --suite rebound --policies oracle,fragile,retry,silent \
    --reward-mode shaped --out experiments/rl
```

产物：`experiments/results/comparison.md|json|png`、`experiments/results/exp-*/report.md|summary.json|results.jsonl|episodes/`、
`experiments/rl/rollouts.jsonl`、`experiments/rl/README.md`。
