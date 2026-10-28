# 空白分析与 REBOUND-Bench 提案

> 版本: v1.1 ｜ 2026-10-26 ｜ 作者: bench-survey
> 前置阅读：`docs/benchmark-survey.md`（机制）、`docs/benchmark-matrix.md`（对比与四轴覆盖度）、`docs/DESIGN.md`（实现契约）。
>
> 结构：**§1 gap 分析（11 条）** → **§2 提案（轴、指标、schema、基线、威胁）** → **§3 实现对照（AgentLab v0.1）** → **§4 与同类工作差异化**。
> §2 中标注「已实现」的口径以 `docs/DESIGN.md` 与已落地代码为准；标注「建议」的是**尚未实现**的扩展，需先改 DESIGN.md 再实现。

---

## 0. 一句话结论

现有基准把 **"环境在 episode 内稳定"、"指令可执行"、"预算无限"** 当作默认前提，并用单一 `success rate` 汇报结果。于是**"一次做对"与"坏了能修好"、"问清楚再做"与"猜着做"、"高效完成"与"堆 token 完成"在指标上无法区分**。已有碎片化先例（MCP-Injector、AM-Bench、UnderSpecBench、Harness-Bench、OSWorld 2.0 的定性观察）各自只覆盖一轴且互不兼容。REBOUND-Bench 的目标不是发明新能力维度，而是**把四轴放进同一个可复现 episode，并让四轴的贡献在指标上可分离**。

---

## 1. Gap 分析（每条绑定具体基准与可核查证据）

### G1. 环境被假设为 episode 内稳定，"漂移"被视为缺陷而非测量对象

- **证据**：Terminal-Bench 4.0 的更新日志删除 8 条任务（2 saturation、2 refusal、2 **public solutions**、2 质量/平台）并修复 19 条以处理"用户报告的 flakiness 或 misspecification"；SWE-bench Multimodal v2 因 "known flaky or ungradeable tests" 删任务并重建 Docker 以解决 "dependency and browser drift"。**两处都把环境漂移当作要消灭的 bug。**
- **后果**：没有基准能回答"状态在脚下变化时，agent 会不会重新观测"。OSWorld 2.0 把 "dynamic environments / implicit-state inference" 列为核心挑战，但那是**情境设计**而非**可控注入**——同一任务重复运行得不到同一个漂移。
- **对应**：REBOUND 的 `axis: drift`（已实现 `drift_write` / `drift_delete`，见 §3）。

### G2. "恢复成功"没有独立指标，与"一次成功"混在同一个 success rate 里

- **证据**：Terminal-Bench、SWE-bench、OSWorld、AppWorld、Toolathlon 的主指标都是"最终状态对不对"。MCP-Injector 虽做故障注入并报告"任务完成分从 8.08 掉到 3.23（-60%）"与 resilience ratio，但它是**工具层中间件 + 聚合分**，没有任务级 recovery rate。
- **后果**：无法区分①本来就不会做；②会做但一遇故障就崩；③会做且能修但修得慢/贵。
- **对应**：REBOUND 的 `RRS` / `clean SR` / `recovery_lift`（已实现）+ 建议新增条件化 `CRR`（§2.4、§3 R1）。

### G3. 故障注入的先例只覆盖"工具调用层"，缺 OS 级故障面

- **证据**：MCP-Injector 的注入点在 **MCP 协议路径**，故障模型由 1,774 个 MCP 仓库的 57,240 条 issue/PR 校准，持久性分 permanent / transient / intermittent。它没有文件删除、权限变更、端口占用、配置漂移这些**终端事故**最常见形态；而 Terminal-Bench / OSWorld 的沙箱恰好能承载这些。
- **后果**：结论（"scale does not purchase fault tolerance, p=0.96"）只在工具协议层成立，无法外推到运维/终端场景。
- **对应**：REBOUND 的 6 种 fault kind（已实现：文件删除/写入/追加/批量删除/命令阻断/内容损坏），见 §2.3。

### G4. 澄清（clarification）被观察到，但没有预算机制、没有质量指标

- **证据**：AM-Bench 用 48 任务 ×（1 完整规格 + 6 变体）跑 5 模型 × 4 harness × 20,160 runs，结论是 missingness 比 ambiguity 更伤成功率、clarification 可挽回未完成工作但多数 constraint violation 不可挽回；UnderSpecBench 用 69 task family、2,208 prompt 变体，把非动作运行分为 clarification / refusal / deferment，结论是 **55.8–67.8% 的运行至少违反一个动作边界**；OSWorld 2.0 定性观察到 "guess rather than ask the user"。
- **后果**：**没有基准同时度量"该问有没有问"与"不该问有没有乱问"**，于是两个方向都能刷：疯狂提问，或从不提问赌默认值。
- **对应**：`budget` 中的 `ask_user` 上限 + `CQ`（已实现）；precision 侧与 `PAR` 仍缺（§3 R4/R5）。

### G5. 效率不是指标，只是附录里的 Pareto 图

- **证据**：Terminal-Bench 2.0 单任务 $1–$100、极端 2 小时 / 近 1 亿 token，但主指标仍是 resolve rate；附录明确 **"平均 turn 数与成功率几乎无关"**、**"更高 token 数不必然更好"**；HAL 发现更高 reasoning effort 在多数运行中反而降低准确率。TB 3.0 与 HAL 给了 cost-aware Pareto，但**没有基准把预算做成约束并给效率打分**。
- **后果**：排行榜奖励"堆 token"，与生产相反。
- **对应**：`budget.max_tool_calls` 硬约束 + `ES`（已实现，公式见 §2.4）。

### G6. 能力与韧性在指标上不可分离，"resilient but incompetent" 与 "capable but brittle" 无法排序

- **证据**：单一 success rate 是二者的混合。OSWorld 2.0 的 binary 20.6% / partial 54.8% 说明同一行可以差 30+ 点，但仍不区分"是否被扰动"。
- **后果**：稳定 80%/遇故障 30% 的 agent 与稳定 50%/遇故障 45% 的 agent，在榜单上是"80% vs 50%"，而后者更该进生产。
- **对应**：复合分**并列**分量 `C / RRS / ES / CQ`（已实现四分量报告）+ 建议乘积式 `RAS_ε` 与 `C`-`CRR` 散点（§3 R2）。

### G7. 恢复过程造成的二次破坏（collateral damage）未被纳入恢复评测

- **证据**：AppWorld 的 state-based unit tests **已经**检查 collateral damage（"任务完成但把别的改坏"要判失败），是最好的机制先例；UnderSpecBench 的 OverScope 也度量"超出爆炸半径"。但二者都**未与故障恢复结合**：恢复动作本身（重启服务、回滚配置、重装依赖）极易二次破坏。
- **后果**：现有恢复研究只问"是否恢复"，不问"恢复代价与副作用"。
- **对应**：`checks` 里的 `state_unchanged` / `file_absent` 已能表达 residue 与误伤（已实现机制，但尚无"每个 fault 任务必须至少一条"的规范，§3 R7）。

### G8. 故障/漂移没有共享分类学，结果无法跨论文累积

- **证据**：MCP-Injector 用 `failure mode × persistence`；AM-Bench 用 `goal/context/constraint × missing/ambiguous`；UnderSpecBench 用 `intent clarity / target certainty / blast radius`。三套 taxonomy 互不映射。
- **后果**：每个新基准重新发明坐标系（TB 系列因此要自己重建 3.0/4.0）。
- **对应**：本提案的三维故障标注（category × persistence × visibility）+ 四类漂移 + 四轴欠规格（§2.3；persistence/visibility 尚未实现，§3 R6）。

### G9. 多数基准不可用于 RL 训练（无 Gym 接口、无 seed 化扰动、无部分分）

- **证据**：τ-bench 是少数提供 Gymnasium 兼容接口（`--extra gym`，含 train/test split）的对话式基准；Terminal-Bench 的 Harbor 格式可承载 RL，但故障/漂移不可 seed、奖励二值；OSWorld 有 checkpoint partial 但环境极重；GAIA/BrowseComp 完全没有 harness。
- **后果**：RL 需要"可重放 + 稠密奖励 + 大规模并行"，现有基准至多满足一项。
- **对应**：`status=budget` 仍跑 verifier 以保留部分分（已实现）、按 `at_step` 的确定性注入（已实现）、`samples`/`seeds` 记录（已实现）；缺 per-axis reward 与 Gym 包装（§3 未实现清单）。

### G10. 统计口径薄弱：小样本 + 无 CI + 无配对设计

- **证据**：TB 4.0 只有 66 条任务（**~1.5 pt/条**），TB 2.0 报 95% CI 是少数正面案例；多数基准单次运行报点估计；τ-bench 的 `pass^k` 是少数处理可靠性的设计。
- **后果**：3 pt 以内的差异被当结论；"某 domain 更好"多半是噪声。
- **对应**：`SR` 附 Wilson CI（已实现）、同任务多样本（`samples`）、`n` 显式展示（已实现）；配对检验与 `pass^k` 待补（§3 R8）。

### G11. harness 效应与评测意识（eval-awareness）未被控制

- **证据**：TB 2.0 中同模型换 scaffold 提升 17 分；Harness-Bench（106 任务 / 5,194 轨迹）主张能力必须按 model-harness 配置报告；HAL（21,730 rollouts / 约 $40k）用日志审计发现 agent 去 HuggingFace 搜基准答案；SWE-bench Pro v1.0 审计发现 unearned pass 随能力从 24% 升到 73%。
- **后果**：不控 harness 与作弊面，测到的是"脚手架 + 作弊能力"。
- **对应**：中性工具面（`tools: [shell, read_file, write_file, list_dir]`）+ `scripted`/`react` 双 agent + 判分只看 workspace 终态而不信 agent 自述（已实现）；容器隔离未实现（DESIGN.md 明确 `local` backend 非安全沙箱）。

---

## 2. REBOUND-Bench 提案

**名称**：**REBOUND** — *Resilient Execution under Budget, Observations, and Unexpected eNvironment Drift*。

### 2.1 定义

在**同一批长程任务**上，用**受控、可复现的故障与漂移**扰动环境，用**计费的 `ask_user`** 暴露欠规格，用**硬预算**限制资源，最终把 agent 表现分解为 **capability / recovery / efficiency / clarification** 四个可分离的量。

### 2.2 设计原则（每条对应一个 gap）

| 原则 | 对应 gap | 实现状态 |
|---|---|---|
| **配对而非独立**（同任务多臂比较） | G2, G6, G10 | 部分：同一任务用 `faults` 开关 + `samples` 多采样对比，尚无独立 arm 字段 |
| **受控而非自然**（seed/schedule 决定注入） | G1, G9 | ✅ `at_step` 确定性触发 |
| **静默优先**（无报错、只有错误结果） | G3 | ✅ `announce: false`（drift 恒静默；fault 可配） |
| **两侧度量**（澄清的 recall 与 precision） | G4 | 部分：只有 recall 侧（`useful/required`），precision 与 `PAR` 待补 |
| **预算内生**（硬约束 + 效率分） | G5 | ✅ `budget` + `ES` |
| **终态不变量**（含 residue / 误伤） | G7 | 机制已具备（`state_unchanged` 等），规范未强制 |
| **共享分类学** | G8 | 部分：kind 已固定 8 种；persistence/visibility 未建模 |
| **可判分可审计** | G11 | 部分：终态判分已实现；容器隔离与 adversarial agent 未实现 |

### 2.3 扰动分类学（对最初五类故障的精化）

**精化 1：故障 ≠ 漂移。**
- **fault**：环境**损坏**，可修（repair）或绕过（bypass），存在"正确终态"。
- **drift**：环境**合法地变了**（上游数据更新、并发编辑、服务自愈回默认、时间推进），**无法修回去**，只能重新观测并改计划。
- 现有基准混淆二者：SWE-bench 把 dependency drift 当 flaky，OSWorld 2.0 把 dynamic environment 当难度。REBOUND 用两条独立执行路径区分（`faults` vs `drift_*`），并分别算 `RRS` 与 drift success rate。

**精化 2：故障用三维标注，而不是平铺。**

| 维度 | 取值 | 为什么必要 | 实现状态 |
|---|---|---|---|
| **category** | `file_loss`（`delete_file`/`remove_file_pattern`）、`config_drift`（`write_file`/`append_file`/`corrupt_file`）、`process_port`（`block_command`）、以及规划中的 `permission`、`dependency` | 覆盖真实终端事故；每类对应不同检测/修复技能 | 4/6 已实现（`block_command` 为进程/端口类的最小替代） |
| **persistence** | `permanent` / `transient` / `intermittent` | MCP-Injector 校准结论：真实生态以 permanent 为主，且伤害最大 | ❌ 未实现（`block_command` 触发一次、重试即恢复，等价于一次性 transient） |
| **visibility** | `loud`（有报错）/ `silent`（只有错误结果） | **silent 是"重观测"与"错误处理"的分水岭** | ✅ 部分：`announce` 字段控制；drift 恒静默 |

**精化 3：漂移分四类，并定义"陈旧动作"。**
`upstream_data` / `concurrent_edit` / `self_heal` / `time`。判分关注 **stale-action rate**：关键状态已变后，agent 是否仍按旧观测执行变更动作。
现状：`drift_write` / `drift_delete` 可实现前两类与前者的组合；`self_heal`、`time` 与 stale-action 指标未实现。

**精化 4：欠规格分四轴，并区分"可问出"与"不可问出"。**
`goal` / `context` / `constraint` / `target`（借鉴 AM-Bench 三轴 + UnderSpecBench 的 target certainty）。关键新增 `answer_policy`：
- `answerable`：`ask_user` 能给出确定答案；
- `refuse`：用户回答"这没规定"——考察 agent 在信息不足时是否选保守/可逆动作，而不是编默认值继续。
依据：AM-Bench 的 "constraint violation 无法被澄清挽回" + UnderSpecBench 的 "blast-radius cues 几乎不降低行动倾向"。
现状：`ambiguity.answers[].match/reply` + `default` 回复已能表达 `refuse`（不命中任何 `match` 即走 `default`），但缺少"该题期望保守行为"的显式声明与对应检查（§3 R5）。

### 2.4 指标

#### (A) 已实现口径（以此为准）

**记号**：任务 `i`，样本 `s`（`samples`），episode 结果 `succ_{i,s}`，`used_calls` = shell + tool 动作数，`cap = budget.max_tool_calls`，`oracle = budget.oracle_tool_calls`。

```
SR            = success / total                                  （附 Wilson 95% CI）
RRS           = success rate over episodes with axis=fault
clean_SR      = success rate over episodes with no faults
recovery_lift = RRS − clean_SR
drift_SR      = success rate over episodes with axis=drift      （单独报告）
```

```
ES  = success × clip( 1 − max(0, used_calls − oracle) / max(1, cap − oracle), 0, 1 )
CQ  = min(1, useful_clarifications / required_clarifications)
```

```
REBOUND = 0.40·SR + 0.25·RRS + 0.20·mean(ES) + 0.15·CQ          （仅 rebound suite；无 RRS 时回退为 SR）
```

- `useful_clarification`：提问命中 `ambiguity.answers[].match` 正则。提问次数受 `ambiguity.clarification_budget` 限制（`ask_user` 计入预算）。
- "沉默型"基线（不问直接猜）由一条专门检查判失败，避免 `CQ` 被 0 分白送。
- 报告必须显示 `n`（每格样本数），让小样本显式暴露。
- 失败分类优先级（已实现）：`error > gave_up > budget > timeout > loop > no_attempt > fault_unrecovered > wrong_output > incomplete`。

#### (B) 建议扩展（尚未实现，需先改 DESIGN.md）

**① 条件化恢复率 `CRR`（对应 §3 R1）**

```
S_ctrl = { i : 该 agent 在无故障 episode 中至少成功一次 }
CRR    = Σ_{i∈S_ctrl} 1[该任务 fault episode 成功] / |S_ctrl|
```

`RRS` 不条件化时会把"本来就不会做"算成"不韧性"；`CRR` 只在"该 agent 有能力完成"的任务上问"扰动后是否还能完成"。这也是相对 MCP-Injector 的 resilience ratio 的方法学改进：**比值的分子分母必须在同一任务子集上取**。

**② 过早行动率 `PAR`（对应 §3 R5）**

```
PAR = (1/n) Σ_i 1[ 存在变更类动作作用于依赖某 critical unknown 的资源，且该 unknown 尚未解决 ]
```

UnderSpecBench 说明"欠规格不是让 agent 失败，而是让它猜"；`PAR` 把"猜"变成可计数的违规事件。可用现成 `tool_log` 与 `clarifications` 的时间序算出。

**③ 澄清精度 `CP` 与 `CQ′`**

```
CP  = useful_asks / max(1, total_asks)
CQ′ = min(1, useful/required) · (α + (1−α)·CP),  α = 0.5
```

现口径在 `required=1` 时"问 1 次命中即满分，问 100 次也满分"，正好奖励"把用户当搜索引擎"。

**④ 剂量-反应 `k*`**

令 `succ(k)` 为注入 `k` 个故障时的成功率（`k=0,1,2,3`），`k*` = 使 `succ(k*) ≤ 0.5·succ(0)` 的最小 `k`（不存在则报 `>3`）。用于区分"扛得住一个故障"与"扛得住连锁故障"。

**⑤ 乘积式复合分 `RAS_ε`（对应 §3 R2）**

```
RAS_ε = C · (ε + (1−ε)·CRR) · (ε + (1−ε)·ES) · (ε + (1−ε)·CQ),  ε = 0.01
```

线性加权允许完全补偿（`SR=0.9, RRS=0.2` 会击败 `SR=0.5, RRS=0.45`）。乘积式保证任一维趋零则总分趋零。

**⑥ `pass^k`（可靠性，与 `pass@k` 方向相反）**

```
pass^k = (1/n) Σ_i 1[ 该任务 k 次采样全部成功 ]
```

`pass@k` 衡量"至少一次成功"（可达性），`pass^k` 衡量"k 次全成功"（可靠性）。τ-bench 用后者，因为生产要稳定复现。

**统计口径（建议）**：每臂 ≥3 样本；按任务重采样做 paired bootstrap；跨模型比较用 McNemar（同任务配对）；多指标做 Holm/BH 校正；报告效应量而非只报 p 值；固定输出 `C` vs `CRR` 散点——若 `corr(C, CRR) > 0.9`，说明两轴未分离，REBOUND 的核心卖点不成立。

### 2.5 任务规格 schema

**(A) 已实现字段（与 `docs/DESIGN.md` §4 完全一致，勿改语义）**

```yaml
id: rb-fault-retry               # 全局唯一；目录名必须等于 id
name: 日志归档与服务重试
category: rebound                # terminal | repo | tools | rebound
difficulty: medium               # easy | medium | hard
tags: [fault, retry]
visibility: public               # public | hidden

prompt: |
  服务日志需要归档到 logs/archive/，并生成汇总报告……

max_steps: 14                    # 单 episode 最大动作数
timeout_s: 90                    # 单条 shell 命令超时（秒），不是整局

workspace:
  copy_files: true               # 把本任务包 files/ 复制进 workspace
  files:                         # 也可内联写入（路径相对 workspace 根）
    config/app.ini: |
      [server]
      port = 8080

tools: [shell, read_file, write_file, list_dir]   # 允许的动作；shell 必须显式声明
# 全写形式（挂 mock 工具）：
# tools:
#   - name: shell
#   - name: search_docs
#     kind: mock_tool
#     description: "搜索内部文档"
#     mock:
#       - match: "退款|refund"
#         response: "退款政策：7 天内可退……"
#       - default: "未找到相关文档"
#   - name: create_ticket
#     kind: mock_tool
#     description: "创建工单"
#     effect: {ticket: true}

budget:
  max_tool_calls: 16
  max_tokens: 30000
  max_wall_s: 300
  oracle_tool_calls: 5           # 效率分归一化用（任务作者填 oracle 的调用数）

faults:
  - at_step: 2
    axis: fault                  # fault | drift
    kind: block_command          # delete_file | write_file | append_file | remove_file_pattern
                                 # | block_command | corrupt_file | drift_write | drift_delete
    match: "flask run"           # block_command 用（正则），触发一次，重试可恢复
    announce: true               # true=环境主动报错；false=静默（drift 恒静默）
    note: "模拟端口冲突或进程被占"
  - at_step: 4
    axis: drift
    kind: drift_write
    path: config/app.ini
    content: "[server]\nport = 9090\n"
    announce: false

ambiguity:
  clarification_budget: 2        # 允许的 ask_user 次数（计入预算）
  required_clarifications: 1     # 计入 CQ 的"充分询问"下限
  answers:
    - match: "端口|port"          # 正则，命中即答（计为 useful）
      reply: "生产端口是 8080"
    - default: "这个信息不能透露"   # 不命中任何 match 时返回

verifier:
  pass_threshold: 1.0            # required 全过；score 阈值兜底
  checks:
    - name: report_exists
      kind: file_exists
      path: report/summary.md
      weight: 1.0
      required: true
    - name: other_logs_intact
      kind: state_unchanged      # 防误伤 / residue
      paths: [logs/app.log]
    - name: custom_logic
      kind: python
      func: check_schema         # 对应 checks.py 中的 def check_schema(ctx)
      weight: 2.0

solution:                        # 供 oracle agent / validate 使用
  actions:
    - kind: shell
      command: python -c '...'
```

检查项 `kind` 取值（已实现）：`file_exists` / `file_absent` / `dir_exists` / `file_contains` /
`file_not_contains` / `file_equals` / `file_line_count` / `shell` / `state_changed` /
`state_unchanged` / `tool_called` / `python`。判分规则：`score = Σ(weight·passed)/Σweight`；
`success = 所有 required 通过 and score >= pass_threshold`。

**(B) 建议扩展字段（未实现；必须先改 `DESIGN.md` §4 再落地）**

```yaml
# 建议：fault 的持久性与触发方式（对应 §3 R6）
faults:
  - at_step: 2                              # 现有：绝对步序号
    after_action: "write:config/app.ini"    # 建议：动作触发（避免 scaffold 不同导致注入点漂移）
    persistence: transient                  # 建议：permanent | transient | intermittent
    heal_after_steps: 3                     # 建议：transient 的自愈延迟
    visibility: silent                      # 建议：由 announce 提升为一等字段

# 建议：效率分的显式参考成本（对应 §3 R3）
budget:
  reference_cost: { tool_calls: 5, tokens: 9000, wall_s: 120, usd: 0.02 }

# 建议：不变量与残骸（对应 §3 R7）
invariants:
  - id: inv-no-residue
    desc: "workspace 内不存在 *.corrupt / *.bak"
  - id: inv-no-collateral
    desc: "非目标任务文件 hash 与初始快照一致"

# 建议：臂与预注册（评测侧，不属于单任务）
protocol:
  arms: [ctrl, fault, drift, under, mixed]
  trials_per_arm: 3
  seed_namespace: "rb-fault-retry"
```

### 2.6 臂设计与期望现象

| 臂 | 注入 | 目的 | 期望读出的现象 |
|---|---|---|---|
| `ctrl` | 无 | 能力基准 | `clean_SR` 应落在可区分区间（不饱和） |
| `fault` | 1–3 个 fault（≥50% silent） | 恢复能力 | `RRS ≪ clean_SR`；silent 的 `RRS` 显著低于 loud |
| `drift` | 1–2 次合法变更 | 重观测能力 | 出现 stale action 而非直接崩溃 |
| `under` | 1–3 个 critical unknown（含 refuse 型） | 澄清能力 | `CQ` 与 `PAR` 反向；预算 0→2 时 useful 升、precision 降 |
| `mixed` | 同时注入 | 交互效应 | 关键检验：恢复是否依赖先澄清（顺序依赖） |

现状：`fault` / `drift` / `under` / `mixed` 可由任务数据组合表达（同一 `task.yaml` 的不同变体 + `samples`），但**没有 arm 字段**，report 侧靠 `axis` 聚合；建议加 `protocol.arms` 以便配对统计。

### 2.7 基线与消融计划

| ID | 内容 | 作用 |
|---|---|---|
| B0 | `oracle`（`solution.actions` 回放） | 上界；也是 `validate` 的判据 |
| B1 | `careless` / `no-op` | 下界，必须 0；验证 verifier 非恒真 |
| B2 | `react × mock` | 无 key 的 pipeline 自检（报告须标 synthetic） |
| B3 | `react × frontier`（2–3 个模型，中性工具面） | 主结果 |
| B4 | `react × frontier + 恢复提示`（"完成后自检，状态可能已变"） | 分离"能力"与"知道要检查"，**最能证明 REBOUND 有诊断价值** |
| B5 | `fragile` / `recoverer` / `adaptive` 脚本 agent | 校准指标方向性（synthetic，仅用于自检） |

消融（8 组，按可实施性排序）：

| ID | 消融 | 要回答的问题 | 可行性 |
|---|---|---|---|
| A1 | 仅 fault（无 drift/ambiguity） | 恢复率是否独立于澄清 | ✅ |
| A2 | 仅 drift | drift 是否产生不同失败形态 | ✅ |
| A3 | `announce: true` vs `false` 同构任务 | "静默"的代价（预期 silent 更差） | ✅ |
| A4 | `at_step` 早 vs 晚 | 注入时机是否与 scaffold 交互 | ✅ |
| A5 | `clarification_budget` 0 / 1 / 2 | 澄清边际收益与过度提问成本 | ✅ |
| A6 | 预算 `cap` 松 vs 紧（2× vs 1× oracle） | `ES` 是否区分"省"与"堆" | ✅ |
| A7 | `oracle_tool_calls` 人为偏移 ±50% | `ES` 对 oracle 估计误差的敏感性 | ✅ |
| A8 | 加/不加 residue 检查 | 二次破坏比例 | ✅ |

**预注册假设**（写进 README，避免事后解释）：
- H1：`clean_SR` 与 `RRS` 的相关 `r < 0.7`（否则两轴未分离，REBOUND 价值不成立）；
- H2：silent 故障的 `RRS` 比 loud 低 ≥10 pt；
- H3：`clarification_budget` 0→2 使 `CQ` 上升，超过 2 后平台化；
- H4：`cap` 收紧使 `ES` 下降、`budget` 状态比例上升；
- H5：B4（恢复提示）提升 `RRS` 但不提升 `clean_SR` → "知道要检查"与"会做"是两种能力。

### 2.8 反作弊与数据卫生

1. **判分只看终态**：基于 workspace 终态与命令副作用，不信 agent 自述；`python` 检查项禁止读 `solution`（已实现）。
2. **三条必须失败**：no-op agent、只删故障标记不修状态的"假修复"、直接改 `checks` 目标文件的 patch。建议加 adversarial exploit agent 回归集（未实现）。
3. **故障不可从噪声识别**：control 与 fault 臂的 `prompt` 必须**逐字一致**；注入形态取自真实事故（参照 MCP-Injector 的 57,240 条 issue 校准方法）。
4. **污染控制**：`visibility: hidden` 用于内部回归、不进公开集（已实现）；建议 ≥60% 任务新撰写、保留 20% 私有 held-out、全库 canary。
5. **隔离**：`local` backend **不是安全沙箱**（DESIGN.md §11 已明确），接真实模型前须换容器；网络策略建议 `locked`。
6. **评测意识**：日志审计检索 benchmark/oracle/verifier 等关键词（HAL 做法，未实现）。

### 2.9 规模与成本（工程估计）

| 项 | 建议 | 理由 |
|---|---|---|
| 基础任务数 | 120–160 | 每条约 0.7 pt 分辨率，配对设计下足以检出 8 pt 差异 |
| 变体/臂 | 5 | ctrl / fault / drift / under / mixed |
| samples/臂 | 3（最终 5） | 支持 CI 与 `pass^3` |
| 总 episode | 1,800–2,400 | 120×5×3 |
| 单 episode 成本 | $0.3–$3（长任务 $10） | 参照 TB 2.0 的 $1–$100 区间 |
| 单模型单 scaffold 全量 | $1k–$8k | 与 HAL 的 $40k 全景评测相比可接受 |
| 任务创作 | 4–8 人时/任务 | TB 2.0 约 3 人时纯评审；REBOUND 另需扰动与不变量设计 |
| 首要风险 | 任务供给 < 评测需求 | 先做 40 条 pilot 验 H1–H5 再扩 |

### 2.10 威胁与效度（Threats to Validity）

**构念效度**
1. `RRS` / `CRR` 混合"检测故障""修复故障""重规划"三种子能力 → 建议记录 `detection_step` / `repair_step`，把恢复分解为 `detect → repair → finish` 漏斗率。
2. `CQ` 假设"关键未知"可客观枚举 → `ambiguity.answers` 由两人独立标注并报 Cohen's κ，只保留一致项。
3. `ES` 以 `oracle_tool_calls` 为参考，而 oracle 未必最优 → 取 oracle 与最强 baseline 的较小者；报告 `used/cap` 分布而非只看均值。
4. 模拟用户 ≠ 真实用户 → 明确只测"询问策略"不测"人际沟通"；`default` 回复措辞固定。

**内部效度**
5. 注入痕迹可被识别（eval-awareness）→ control/fault 的 prompt 逐字一致 + 盲测。
6. 注入时机 × 模型采样随机性 → 多样本、报 CI，记录温度/effort。
7. verifier 与注入器耦合 → verifier 只读终态与 `tool_log`，不读注入调度；注入事件写在独立 `faults` 记录中。
8. 检查项过严会误杀合法解法 → 每条 required 检查须"oracle 通过 + ≥3 种合法解法论证"。

**外部效度**
9. 6 种 fault kind × 2 种 drift ≠ 真实事故分布 → 用真实事故语料校准抽样权重并公开。
10. 任务域偏工程（terminal/devops/data-eng）→ 首批覆盖 ≥5 domain，报 per-domain `RRS`，不做跨 domain 平均后宣称总体更好。
11. **与 OSWorld 2.0 重叠**（dynamic environment / implicit state / 猜而不问）→ 差异化必须落在 (i) 受控可复现注入、(ii) 条件化恢复率、(iii) 预算化 ask_user 两侧度量；论文必须做"同任务无注入 vs 注入"对照。

**统计效度 · 可复现性**
12. 多指标 → 预注册主指标（`RRS`/`CQ`/`ES`），其余标 exploratory。
13. 小样本 cell → 每条指标附 `n` 与 CI 宽度；`n < 10` 时只报合并结论。
14. 镜像/依赖/注入调度/答复/verifier 版本须同时 pin；版本采用语义化 `x.y.z`（`x` 重跑、`y` 重判、`z` 复用，采纳 TB 4.0 约定）。

---

## 3. 实现对照（AgentLab v0.1）

本节把提案里的每个概念映射到**已落地**的代码位置、任务 id 与字段。代码组织以 `docs/DESIGN.md` §2 的目录约定为准；具体函数名以仓库为准（标 `(待核实)` 者未逐行核对）。

### 3.1 概念 → 实现

| 提案概念 | 实现位置 / 字段 | 任务 id | 状态 |
|---|---|---|---|
| 任务包与加载 | `suites/<suite>/<task_id>/task.yaml`；`agentlab/core/`（加载、注册表） | 全部 | ✅ |
| capability `SR`（+ Wilson CI） | `agentlab/core/metrics.py`；`eval/report` 聚合 | terminal-lite / repo-fix / tool-use / rebound | ✅ |
| `clean SR` / `RRS` / `recovery_lift` | 按 `axis=fault` 与"无 faults"分组；`recovery_lift = RRS − clean_SR` | `rb-fault-retry` | ✅ |
| drift 成功率（单独报告） | 按 `axis=drift` 分组 | `rb-drift-config` | ✅ |
| `ES` 效率分 | `success × clip(1 − max(0,used−oracle)/max(1,cap−oracle),0,1)`；`used_calls` = shell + tool，`cap = budget.max_tool_calls`，`oracle = budget.oracle_tool_calls` | `rb-budget-oneshot`（补充中） | ✅ |
| `CQ` 澄清质量 | `min(1, useful/required)`；`useful` = 命中 `ambiguity.answers[].match`；`ambiguity.clarification_budget` 限制次数 | `rb-ambiguity-port` | ✅ |
| 沉默型 agent 判失败 | 专用 check（未澄清即行动 → fail） | `rb-ambiguity-port` | ✅ |
| REBOUND 复合分 | `0.40·SR + 0.25·RRS + 0.20·mean(ES) + 0.15·CQ`（仅 rebound suite；无 RRS 回退 `SR`） | rebound suite | ✅ |
| fault 注入（6 种） | `agentlab/envs/faults.py`（`FaultInjector`，`step()` 前消费）；字段 `at_step/axis/kind/path/content/match/announce/note` | `rb-fault-retry` | ✅ |
| `block_command` 一次性阻断 | 正则匹配命令 → 注入一次失败；重试即恢复（等价 transient） | `rb-fault-retry` | ✅ |
| drift（静默） | `drift_write` / `drift_delete`；`announce: false` | `rb-drift-config` | ✅ |
| 预算硬约束 | `budget.max_tool_calls / max_tokens / max_wall_s`；超限 → `status=budget`，仍跑 verifier 保留部分分 | `rb-budget-oneshot` | ✅ |
| 状态快照 / 误伤检查 | `reset()` 后 sha256 `state_before`，结束 `state_after`；`state_changed` / `state_unchanged` | 全部 | ✅ |
| 失败分类（9 类优先级） | `error > gave_up > budget > timeout > loop > no_attempt > fault_unrecovered > wrong_output > incomplete` | 全部 | ✅ |
| 轨迹落盘 | `experiments/results/<run_id>/results.jsonl` + `episodes/<task>__s<sample>.json` | 全部 | ✅ |
| CLI | `run --suite rebound --agent scripted\|react --model mock\|<model>`、`validate`、`report`、`doctor` | — | ✅ |
| `pass@k` | `agentlab/core/metrics.py`（无偏估计） | — | ✅ |
| **`CRR` 条件化恢复率** | 未实现（report 侧 join 即可） | — | ❌ R1 |
| **`PAR` 过早行动率** | 未实现（`tool_log` + `clarifications` 时间序可算） | — | ❌ R5 |
| **`CP` 澄清精度 / `CQ′`** | 未实现 | — | ❌ R4 |
| **`pass^k`** | 未实现（已有 `pass@k`） | — | ❌ R8 |
| **`RAS_ε` 乘积复合分** | 未实现 | — | ❌ R2 |
| **persistence / after_action** | 未实现（`at_step` + 一次性 `block_command`） | — | ❌ R6 |
| **residue 强制规范** | 机制已有（`file_absent`/`state_unchanged`），无强制 | — | ❌ R7 |
| **容器隔离 / adversarial agent** | 未实现（`local` backend 非安全沙箱） | — | ❌ |

### 3.2 未实现部分的优先级（给 Lead 的 9 条）

- **R1（高｜极低成本）加 `CRR`**：`episodes/*.json` 已有 `task_id`/`status`/`faults`，report 阶段 join 即可，无需重跑；报告须显示分母 `|S_ctrl|`。
- **R2（高｜低成本）并列乘积式 `RAS_ε`**：线性 `0.40/0.25/0.20/0.15` 允许 `SR=0.9, RRS=0.2` 击败 `SR=0.5, RRS=0.45`；建议保留线性榜面，同时输出 `RAS_ε = C·(ε+(1−ε)CRR)·(ε+(1−ε)ES)·(ε+(1−ε)CQ)` 与 `C`-`CRR` 散点。若 `corr(C, CRR) > 0.9` 则说明两轴未分离，这本身是论文结论。
- **R3（中｜极低成本）`ES` 分母复核**：`cap` 很松时（如 `cap=64, oracle=5`）几乎人人接近 1，区分度塌陷；`cap` 很紧时又对 `oracle_tool_calls`（作者手填）极敏感。建议并列 `min(1, oracle/used)`，并分开报 `mean(ES|success)`（现 `mean(ES)` 是"全体 episode 的平均有效效率"，易被误读）。
- **R4（中｜低成本）`CQ` 惩罚滥问**：`required=1` 时"问 1 次命中"与"问 100 次命中"同分。加 `CP = useful/total_asks`、`CQ′ = CQ·(α+(1−α)CP)`；并确认 `ask_user` 已计入 `n_tool_calls` 与 token 预算，否则提问在成本上免费。
- **R5（中｜低成本）加 `PAR`**：UnderSpecBench 的核心发现是"欠规格让 agent 猜"，现有 `CQ` 只奖励问到、不惩罚先改后问。建议作为 ambiguity 任务的**独立指标**（勿并入 `CQ`）。
- **R6（低｜中成本）`faults` 加 `persistence` 与 `after_action`**：`at_step` 会让同一任务在不同 scaffold 下注入点漂移，破坏跨 scaffold 可比性；`transient` 目前只能用"两条 fault 手动抵消"模拟，语义不清。
- **R7（低｜极低成本）residue 规范化**：含 `faults` 的任务强制至少一条 `file_absent: "*.corrupt"` 或 `state_unchanged`，否则"修好目标但留垃圾"照样满分。
- **R8（低｜低成本）补 `pass^k`**：`pass@k`（可达性）与 `pass^k`（可靠性）方向相反不可互替；`samples ≥ 3` 时并列输出 `k=3`。
- **R9（低｜极低成本）失败分类与预算归类**：`budget` 排在 `fault_unrecovered` 之前会把"因预算耗尽而未恢复"归为 `budget`，掩盖韧性信号；建议先判"注入非空且 required 失败 → `fault_unrecovered`"，并把预算耗尽占比作为 `budget_fail_rate` 单独报。

### 3.3 预算语义的取舍（需 Lead 明确）

DESIGN.md 选择"超限 → `status=budget`，仍跑 verifier 保留部分分"；本提案 §2.4(A) 沿用该软语义（信息量大、可实现），而 §2.9 的成本估计按硬约束理解。两者结论不同：软语义测"在预算内尽量多做"，硬约束测"能否在预算内完成"。建议主榜用软语义，另报 `budget_fail_rate` 与 `mean(ES|success)`，使读者能还原硬约束视角。

---

## 4. 与同类工作的差异化（论文必须明写）

| 对比对象 | 它做了什么 | REBOUND 的增量 | 必须做的对照实验 |
|---|---|---|---|
| MCP-Injector | 工具层故障注入 + resilience ratio | 扩到 OS 级文件/配置/命令故障；**任务级 recovery rate + 条件化 CRR**；加 drift / 澄清 / 预算 | 同任务：仅工具层故障 vs 全故障面 |
| AM-Bench | 欠规格 3 轴 × 2 模态，4 harness | **计费 ask_user + recall/precision**（precision 待补）；与 fault/drift 共存 | 同任务：无预算 ask vs 预算 ask |
| UnderSpecBench | 副作用 oracle（Safe/WrongTarget/OverScope） | 多轮长程而非单轮决策；恢复过程中的二次破坏 | 同任务：单轮边界 vs 多轮恢复 |
| Harness-Bench | harness 配置诊断，共享预算 | 把预算变成**指标**而非控制变量；加扰动轴 | 同任务：共享预算 vs 硬预算 |
| OSWorld 2.0 | 长程 + 动态环境 + binary/partial 双报 | **可控可复现**的故障与漂移；条件化恢复率 | 同任务：自然动态 vs 注入动态 |
| Terminal-Bench 4.0 | 终端长程 + 语义化版本 + 容器分离 | 在稳定环境上**叠加扰动轴**，复用其 schema 与质检流程 | 同任务：TB 原设置 vs REBOUND 设置 |

**一句话**：REBOUND 不主张"首次研究故障"（已有 MCP-Injector），而主张**首次把四轴（故障/漂移/欠规格/预算）放进同一 episode 并给出可分离指标**（`SR`/`RRS`/`ES`/`CQ` 四分量 + 建议的 `CRR`/`PAR` 联合）。

---

## 5. 参考来源

- Terminal-Bench 2.0（三准则、质检流程、失败分类、附录 G 的 turn/token 负结果）https://ar5iv.labs.arxiv.org/html/2601.11868v1 ｜ ICLR 2026 https://proceedings.iclr.cc/paper_files/paper/2026/hash/444a3737adaee10d86ad2ef5f74468e6-Abstract-Conference.html
- Terminal-Bench 3.0（74 任务/7 域、agent 与 verifier 容器分离、artifact 类型）https://www.tbench.ai/news/terminal-bench-3-0
- Terminal-Bench 4.0（删 8 修 19、8h 超时、资源校准、语义化版本、4.1 tamper-resistant verifier）https://www.tbench.ai/news/terminal-bench-4-0
- Harbor 框架与 registry https://www.harborframework.com/ ｜ https://github.com/harbor-framework/terminal-bench
- SWE-bench Verified（500 条）https://www.swebench.com/verified.html
- SWE-bench Multimodal v2（480 条、flaky/drift 清理）https://www.swebench.com/multimodal
- SWE-Bench Pro（1,865 / 107.4 行 / GPT-5 23.3%）https://scale.com/blog/swe-bench-pro
- Unearned pass 审计（24% → 73%）https://arxiv.org/abs/2609.34262
- Toolathlon / The Tool Decathlon（32 App / 604 工具 / 108 任务）https://arxiv.org/abs/2510.25726
- OSWorld（369 任务）https://arxiv.org/abs/2404.07972
- OSWorld 2.0（108 任务、500 步、binary 20.6% / partial 54.8%、"猜而不问"）https://arxiv.org/abs/2606.29537
- AppWorld（collateral damage 判分）https://arxiv.org/abs/2407.18901
- τ-bench 家族（pass^k、Gym 接口、frozen benchmark）https://github.com/sierra-research/tau2-bench ｜ https://arxiv.org/abs/2506.07982
- MCP-Injector（故障持久性分类、resilience ratio、p=0.96）https://arxiv.org/abs/2610.32555
- AM-Bench（48 任务 × 7 变体、20,160 runs、missing > ambiguity）https://arxiv.org/abs/2610.18090
- UnderSpecBench（69 family / 2,208 变体 / 55.8–67.8% 违规）https://arxiv.org/abs/2607.02294
- Harness-Bench（106 任务 / 5,194 轨迹 / 共享预算）https://arxiv.org/abs/2605.27922
- HAL（21,730 rollouts、$40k、日志审计发现作弊、effort 非单调）https://arxiv.org/abs/2510.11977
- MLE-bench（75 竞赛、污染分析）https://arxiv.org/abs/2410.07095
- ScienceAgentBench（102 任务 / 44 论文 / 9 专家）https://arxiv.org/abs/2410.05080
- WebVoyager（judge 与人类一致率 85.3%）https://arxiv.org/abs/2401.13919
- GAIA（466 题、人 92% vs 15%）https://arxiv.org/abs/2311.12983
- WebArena（functional correctness、14.41% vs 78.24%）https://arxiv.org/abs/2307.13854
- AgentBench（8 环境、client/server）https://arxiv.org/abs/2308.03688
- BFCL V4（AST / 多轮 / irrelevance）https://gorilla.cs.berkeley.edu/leaderboard.html
