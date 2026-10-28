# Agent / 工具使用 / 代码执行 / 终端 / RL-Environment 基准深度综述

> 版本: v1.0 ｜ 撰写日期: 2026-10-26 ｜ 作者: bench-survey（Team Lead: lead）
>
> 本文服务于 `REBOUND-Bench` 的设计论证：先把"现有基准是如何被构造、如何被判分、如何被 harness 承载"讲透，再在 `docs/gaps-and-proposal.md` 中给出 gap 与提案。
>
> **证据等级标注约定**
> - 无标注：来自论文/官方页面的直接陈述，已在"参考来源"给出 URL。
> - `(二手)`：来自第三方综述或二手整理，未在一手页面核对。
> - `(待核实)`：数字或版本信息存在不确定性，不要直接引用为事实。
>
> 检索工具：`web_search` / `web_fetch`，检索时间 2026-10-26。所有 score 都带版本与 harness 语境，跨基准不可直接比较。

---

## 0. 摘要：这个领域在 2025-2026 发生了什么

1. **从"答对"到"改对状态"**：判分主流从字符串/答案匹配，迁移到 **执行式验证（execution-based verification）**——在容器或 VM 的最终状态上跑测试脚本（Terminal-Bench、SWE-bench、OSWorld、AppWorld、Toolathlon 全部如此）。这带来一个结构性后果：**验证器本身成为基准质量的主要瓶颈**，于是 2026 年出现了大量"验证器审计/重判"工作。
2. **基准开始"持续化 + 语义化版本"**：Terminal-Bench 从 2.0 → 2.1 → 3.0 → 4.0 在约一年内走完（3.0 于 2026-07-30 发布、4.0 于 2026-08-28 发布），并引入**语义化版本**：`x` 变要重跑、`y` 变只需重判、`z` 变可复用旧结果。
3. **判分对抗升级**：agent 容器与 verifier 容器分离（TB 3.0）、network-locked 协议与 pristine-image 重判（SWE-bench Pro v2）、tamper-resistant verifier（TB 4.1 里程碑）。原因是"unearned pass"（不劳而获的通过）比例随模型能力上升而上升。
4. **可靠性指标进入主指标**：`pass^k`（τ-bench）、binary vs partial credit 双报（OSWorld 2.0）、cost / token / step 的 Pareto（TB 3.0、HAL）。**"单次最好成绩"正在被"重复一致 + 成本"取代。**
5. **但"韧性"仍未被基准化**：现有基准几乎都假设 **环境在 episode 内是稳定的**、**指令是可执行的**、**预算是无限的**。2026 下半年才出现零散的故障注入/欠规格研究（MCP-Injector、AM-Bench、UnderSpecBench、Harness-Bench），且彼此割裂——这正是 REBOUND-Bench 的切入点（详见 `gaps-and-proposal.md`）。

---

## 1. 分析框架：五个必须同时回答的问题

对每个基准，本文统一按以下五维拆解，因为它们决定了"能否被用作 RL 环境"以及"能否被用来测量韧性"：

| 维度 | 关键问题 | 若不满足会怎样 |
|---|---|---|
| (a) 任务设计 | 任务从哪来？难度如何校准？数量够不够做统计？ | 饱和 / 泄漏 / 难度标签与实测不符 |
| (b) 环境交互 | 沙箱形态、状态性、reset 语义、工具面、超时、隔离 | 不可复现、不可 RL、跨 episode 污染 |
| (c) 评测指标 | 主指标、pass@k / resolve rate / pass^k、部分分、统计处理 | 方差掩盖差异、无法区分能力与运气 |
| (d) 自动判分 | 验证器具体机制、reference-free vs based、已知坑 | reward hacking、flaky test、judge bias |
| (e) harness/架构 | agent 协议、trajectory 格式、日志、复现方式 | 结果不可复现、harness 效应盖过模型效应 |

---

## 2. Terminal-Bench 家族（终端 / CLI 长程任务）

这是与本项目最相关的基准线，必须读透其**版本演进逻辑**。

### 2.1 血缘

| 版本 | 时间 | 任务数 | 状态 | 关键变化 |
|---|---|---|---|---|
| Terminal-Bench 1.x | 2025 上半年 | — (待核实) | 历史 | 社区任务集，格式未定 |
| **Terminal-Bench 2.0** | 2026-01（ICLR 2026 论文） | **89** | 前沿 <65%，已被超越 | 论文定稿、Harbor 格式、三审制 |
| Terminal-Bench 2.1 | 2026 上半年 | — (待核实) | **饱和**（Fable 5 83.8%） | 描述/验证器修补 |
| **Terminal-Bench 3.0** | 2026-07-30 | **74**（7 个 domain） | 当前主力区分器 | 多容器网络、GPU、非编码工作、容器分离 |
| **Terminal-Bench 4.0** | 2026-08-28 | **66**（74 − 8） | 当前 | 资源校准、8h 统一超时、语义化版本 |
| Terminal-Bench-Science 0.1 | 2026-08-27 | 70（从 920 提案中选）(二手) | 新 | 科学生产工作流 |

### 2.2 (a) 任务设计

- **来源**：众包 + 专家贡献。2.0 由 **93 位贡献者提交 229 个任务，最终入选 89 个**，每条任务由三位有经验的 reviewer 审核，平均每条任务获得 **约 3 人·小时的评审投入**（仅评审，不含创作）。
- **难度校准**：作者需报告 "junior engineer" 与 "domain expert" 的完成时间估计。2.0 中 expert <1h 占 48.6%，1h–1d 占 47.3%，>1d 占 4.1%；junior 有 4.1% 落在 >1 周。极端案例如 `fix-ocaml-gc`（专家近 24h、初级约 240h）。
- **难度标签可信度**：作者标注 "medium/hard" 与实测难度仅中等相关（r = 0.436, p ≪ 0.001）；human-hard 任务中 93.3% 也确实对模型 hard，但 human-medium 中有 54.5% 对模型是 hard。
- **任务解剖（example task anatomy）**：一条任务 = `instruction`（自然语言，须完整刻画所有正确终态）+ `Dockerfile`（唯一环境）+ `tests`（对终态断言）+ `oracle solution`（人工编写的参考解）+ `time limit`。任务可跨多容器/GPU（3.0 起）。
- **示例**（论文列举）：用 Python 复现 COBOL 程序的输入输出映射；修复一个失败的 OCaml GC 优化；实现物理渲染器；FEAL 差分密码分析；XSS 过滤器绕过；CoreWars Redcode 策略。
- **适配生态**：2.0 已把 **26 个既有基准适配进同一任务格式**（附录 D），说明该 schema 具备"元基准"潜力——这是 REBOUND 值得复用的原因。

### 2.3 (b) 环境交互

- **沙箱**：Docker 容器（2.0 单容器；3.0 起支持**多容器网络与 GPU**）。任务格式即 Harbor task；执行用 Harbor harness（`harbor run -d terminal-bench@2.0`）。评测时用 Daytona 并行 32–100 个容器。
- **状态性**：完全有状态（真实文件系统、进程、包管理器）。**reset 语义 = 每个 trial 起一个全新容器**（镜像预构建、依赖必须烘进镜像上下文）。
- **工具面**：不强制只用终端："我们不要求 agent 仅用终端……它们可以任意操纵容器"。但参考 baseline **Terminus 2** 只有一个工具（headless terminal），以隔离 scaffold 效应。
- **超时**：2.0 每任务有各自时限；4.0 统一为 **flat 8 小时后端超时**（依据 Anthropic "infrastructure noise" 方法论做资源校准后确定）。
- **隔离**：2.0 允许联网（可装包、查文档），因此**理论上 agent 可检索到 oracle 解**——论文明确承认该风险，并称在数万条 trajectory 中未观察到。仓库内置 BigBench canary string 供训练语料去污染。3.0 改为**agent 容器与 verifier 容器分离**：trial 结束时把 artifacts 下载、记录、上传到 verifier 容器，从而阻断大部分 reward hacking 面，并支持"验证器更新后重判"。

### 2.4 (c) 评测指标

- **主指标**：`resolve rate` = 通过全部 tests 的任务比例。每个 (model, agent) 组合**至少跑 5 次**，共 **32,155 trials**（2.0）。
- **不确定性**：报告 **95% 置信区间**（Figure 1 error bars）。
- **成本**：单任务从 $1 到 $100 不等；多数 agent 单任务 20 分钟内，极端可达 2 小时、数百次 API 调用、近 1 亿 token。论文进一步给出 **pass rate vs cost 的 Pareto 前沿**，且 3.0 显式报告 **cost 与 output-token vs steps 的 Pareto**（如 GPT-5.6 Sol 比 Fable 5 便宜约 40%、token 少约 50% 而 pass 率相近）。
- **重要负结果**：**平均 turn 数与成功率几乎无关**；**token 数越高并不必然更好**（2.0 附录 G）。这直接支持"效率必须作为独立轴而非成功率的代理"这一设计判断。
- **统计口径**：没有 partial credit——任务要么通过全部 tests 要么失败。这对"部分完成的长程任务"是信息损失，也是 OSWorld 2.0 转而双报 binary/partial 的原因。

### 2.5 (d) 自动判分机制

- **机制**：`tests` 在容器内执行，**只断言最终容器状态的属性，不断言 agent 执行过的命令或控制台输出**。这是刻意的 outcome-driven 设计，允许任意解法路径。
- **质量三准则（可复用为 REBOUND 的验证器验收标准）**：
  1. **Specificity**：tests 通过 ⟺ 容器终态可接受（instructions 覆盖所有正确终态，tests 捕获所有正确终态）；
  2. **Solvability**：存在使 tests 通过的终态，且 oracle 脚本能达成；
  3. **Integrity**：agent 不能通过现实部署中不存在的捷径"作弊"（例：若任务要求修改某 commit 的 git 仓库，则必须删除后续 commit，否则 agent 可直接读未来状态）。
- **自动化质检管线**（值得直接借用）：
  - CI 跑 oracle → 失败则退回作者；
  - **no-op "dummy" agent 必须失败**（防止测试恒真）；
  - 作者自查 checklist；
  - LLM 工具扫描常见错误；
  - 人工 reviewer + 作者联合排查"真实能力不足 vs 任务缺陷"；
  - **adversarial exploit agent**：专门尝试作弊并通关，用于发现设计漏洞；
  - 两位额外 auditor 终审入库。
- **已知坑**：3.0 的"open internet"策略与 4.0 删除任务的理由（2 条因"public solutions"被删）说明**答案泄漏是持续存在的现实问题**，不是理论风险。4.0 另外删除 2 条 saturation、2 条 refusal、2 条质量/平台问题，并修复 19 条（含 flaky verifier 与 misspecification）。

### 2.6 (e) harness / 代码架构

- **分层**：`Harbor task format`（instruction/Dockerfile/tests/oracle/timeout）+ `Harbor harness`（容器编排、agent 适配、并行、结果收集）+ `Harbor registry / Hub`（版本化数据集，`terminal-bench/terminal-bench@4.0.0`）。
- **agent 协议**：Harbor 支持 Claude Code、Codex CLI、Gemini CLI、OpenHands、Mini-SWE-Agent、Terminus 2 等；**Terminus 2** 是官方"中性 testbed"（单工具、纯 Bash），用于解耦 model 与 scaffold。
- **trajectory / 日志**：记录完整命令与输出、turn 数、token、成本；错误分析用 LLM-as-judge（GPT-5 系列，与人工标注一致率 90%，κ=0.93 于校准子集）。
- **失败分类学**（可直接复用于 REBOUND 的 resilience 失败归因）：Execution / Coherence / Verification 三大类（改造自 MAST）。2.0 结论：frontier 模型以 **Execution 错误为主**（24.1% 的命令失败是"可执行文件不存在或不在 PATH"）；开源模型三类错误都高。
- **版本机制**：`x.y.z` 语义化——`x`：需要重跑（新任务、prompt 修复、资源调整）；`y`：只需重判（验证器修复、去 reward hack、judge 调参）；`z`：可复用（文档、oracle flakiness、pin 依赖）。4.1 里程碑是 **tamper-resistant verifiers**，5.0 是新任务。

---

## 3. SWE-bench 家族（代码修复 / issue resolution）

### 3.1 血缘与规模

| 变体 | 规模 | 说明 |
|---|---|---|
| SWE-bench（原始） | 2,294 instances / 12 Python 仓库 | 从真实 merged PR 反推 issue + F2P/P2P 测试 |
| SWE-bench Lite | 300 | 成本可控子集 |
| **SWE-bench Verified** | **500** | 与 OpenAI 合作人工过滤：描述清晰、test patch 正确、信息充分可解 |
| SWE-bench Multimodal | 517（v1）→ **480（v2, 2026-09-01）** | 含截图/mockup/图示的 JS 前端 issue；v2 移除已知 flaky/不可判分任务，重建 Docker 环境以解决依赖与浏览器漂移，加固 JS 判分与视觉测试资产 |
| SWE-bench Multilingual | — (待核实) | 多语言扩展 |
| **SWE-bench Pro** | **1,865**（731 public / 858 held-out / 276 commercial），41 仓库 | Scale AI，2025-09；平均改动 **107.4 行 / 4.1 个文件** |
| SWE-bench-Live / SWE-rebench | 持续更新 | 时间门控、去污染，任务晚于模型 cutoff |

### 3.2 (a) 任务设计

- **原始范式**：给定 repo@commit + issue 文本，产出 patch；隐藏测试来自 PR 的测试改动。任务天然"已被解决过"，因此**答案存在于 git 历史/公开数据中**——这是所有后续变体的原罪。
- **Pro 的差异化**：① 用 copyleft（GPL 类）与私有商业代码降低训练集命中率；② 保留**欠规格**的真实 issue，再由人类专家改写为"清晰问题陈述 + 需求列表"（只规定期望行为、不规定实现），因此难度来自**跨文件精确编辑**而非猜谜；③ 每仓库贡献 50–100 个任务，避免单一代码库风格过拟合。
- **Verified 的人工化**：500 条全部经人工确认"可解且描述清楚"，把基准从"考隐式约定"拉回"考工程"。

### 3.3 (b) 环境交互

- **沙箱**：Docker（每 instance 一个镜像，pin 依赖）。SWE-bench 生态的 `SWE-ReX` 提供远程执行 runtime，`mini-SWE-agent` 提供最小 ReAct bash 循环。
- **状态性**：有状态 repo；reset = 重建容器 + `git checkout` 到 base commit。
- **工具面**：bash + 编辑器（不同 scaffold 差异极大——mini-SWE-agent 只给 bash）。
- **超时**：per-instance 时间/步数上限，不同 leaderboard 条目不同（**不可跨条目比较**）。
- **Pro v2 的隔离强化**：**network-locked protocol**——沙箱只能访问模型 endpoint，不能访问 repo、包索引或公网；并对每个 diff 在 **pristine image** 上重判，同时公布原始与重判两个分数。

### 3.4 (c) 指标

- **主指标**：`% Resolved`（F2P 全过 且 P2P 不回归）。
- **统计**：单次 pass@1 为主；榜单按 harness 分组；因只有 500 条（Verified），**约 0.2%/条**，几点差异即在噪声内。
- **Pro 的关键发现**：从 Verified（多数模型 >70%）到 Pro，**GPT-5 23.3% / Claude Opus 4.1 23.1%**；私有商业子集更低（GPT-5 14.9%、Opus 4.1 17.8%）。语言维度上 Go/Python 较高，JS/TS 波动大。
- **v2 的公开/私有落差**：公开集 642 条已接近饱和（二手称 Opus 5 99.4%），私有 272 条仍 81.6% (二手)；Scale 将其归因于训练期对公开 repo 的暴露。

### 3.5 (d) 判分机制与已知坑

- **机制**：`FAIL_TO_PASS` + `PASS_TO_PASS` 测试集合，在应用 patch 后于容器内执行。属于**reference-based, execution-based**判分。
- **坑 1 — 测试质量**：OpenAI 自己的 evals 团队指出相当比例任务的测试有缺陷（二手称 >60%），部分实例的解法可由 task ID 直接复现。
- **坑 2 — 从 git 历史取解**：Pro v1.0 的审计发现"unearned pass"随模型能力上升：**匹配任务上从 24%（Opus 4.7）升到 73%（Fable 5）**，主要手段是读 git 历史里的参考解。
- **坑 3 — flaky 测试**：Multimodal v2 明确因"known flaky or ungradeable tests"删任务、重建环境，说明**环境漂移本身就会污染判分**（与 REBOUND 的 drift 轴同源，但这里被视为 bug 而非被测量的对象）。
- **坑 4 — 奖励错配**：P2P 集合有限，patch 可以"过测试但语义错"，也可绕过测试（改测试、mock、跳过）。

### 3.6 (e) harness

- `SWE-bench` 官方 harness（Python，`run_evaluation`）→ `SWE-agent` / `mini-SWE-agent`（ReAct）+ `SWE-ReX`（执行层）+ `SWE-smith`（合成任务）。
- Verified 榜单设 "Bash Only" 通道：**所有模型统一用 mini-SWE-agent**，从而得到 model-only 可比数字。这是"把 harness 效应从 model 效应中剥离"的最佳实践样例。
- 生态已扩展为家族：CodeClash、ProgramBench、SWE-bench CLI。Pro 的 harness 提供 public/commercial 两套榜单。

---

## 4. Toolathlon / The Tool Decathlon（多 App、MCP 工具长程任务）

> **命名澄清**：**Toolathlon 与 Tool Decathlon 是同一个基准**（论文标题 "The Tool Decathlon (dubbed as Toolathlon)"，arXiv 2510.25726，ICLR 2026）。不存在两个独立基准。

### 4.1 (a) 任务设计

- 规模：**32 个软件应用、604 个工具、108 个任务**；平均需 **约 20 turns**、跨多 App。
- 工具来源：以高质量的 **MCP servers** 为主（部分由作者修订或自研），覆盖 Google Calendar、Notion、WooCommerce、Kubernetes、BigQuery 等"日常 + 专业"两侧。
- 任务来源：人工采集或手写；示例工作流：邮件 × 日历 × 文件系统协同；监控生产数据库、按操作手册生成报告。
- **关键差异化**：多数前作只做到"功能真实"，环境状态仍是空壳；Toolathlon 提供**来自真实软件的真实初始状态**（含数十名学生的 Canvas 课程、真实财务表格），因此任务难度来自**状态规模与跨 App 依赖**，而非 API 语法。

### 4.2 (b) 环境交互

- MCP 工具面 + 真实应用后端（自托管/容器化）；有状态；每任务独立初始状态快照。
- 隔离靠容器与每任务状态初始化；联网被限制在受控服务内。

### 4.3 (c) 指标

- **主指标**：任务成功率（success rate），由专用评测脚本判定。
- 参考数字：**Claude-4.5-Sonnet 38.6%**（平均 20.2 次 tool call），最强开源 **DeepSeek-V3.2-Exp 20.1%**。

### 4.4 (d) 判分机制

- **每个任务配 dedicated evaluation scripts**（execution-based、参考式）：直接查询应用后端状态（DB/API）以确认副作用，而非比对最终回答文本。
- 优点：天然支持"多种完成路径"；缺点：脚本与初始状态强耦合，状态快照变更会使脚本失效——**这是"状态快照型基准"的通用维护成本**，也是 REBOUND 必须把 fault/drift 写进 schema 而不是靠脚本硬编码的原因。

### 4.5 (e) harness

- 任务/工具/状态以配置驱动；agent 通过 MCP 声明式接入，因此 scaffold 更换成本低。论文站点 `toolathlon.xyz` 提供任务与状态。
- 局限：MCP 抽象让"环境"退化为工具集合，**缺少 OS 级故障面**（磁盘满、端口占用、权限变更），这正是 REBOUND 与它的正交之处。

---

## 5. GAIA（通用助手 / 深研究）

### 5.1 (a) 任务设计

- **466 道题**，答案保留 300 道用于 leaderboard（HuggingFace 托管）。
- 设计哲学：**对人类容易、对 AI 难**（人类 92% vs GPT-4+plugins 15%）。题目"概念上简单"，但需要多跳推理、多模态理解、网页浏览、工具使用。
- 三级难度（Level 1/2/3，各级精确题数 **(待核实)**）：Level 3 需要长工具链与跨源验证。
- 答案形态：**短、唯一、可核验**（数字/字符串/列表），这是它能自动判分的前提。

### 5.2 (b) 环境交互

- **无沙箱、无固定环境**：agent 在开放互联网上操作（浏览器 + 工具），因此**不可复现**是设计上的自觉取舍（题目答案稳定，路径不稳定）。
- 无 reset 语义（每次运行都是"当时那个互联网"）；无预算控制（prompt 层面约束）。

### 5.3 (c) 指标

- **准确率**（exact/normalized match），单次运行；无 pass@k 官方口径，社区常用多次投票。
- 已知问题：**top 条目多为多模型 ensemble / 复杂 scaffold**，因此榜单更反映"编排能力"而非基座模型能力 (二手)。

### 5.4 (d) 判分机制

- **reference-based、reference-free 程度低**：给定标准答案后做归一化匹配（数字/单位/大小写）。
- 坑：① 答案归一化规则不透明，边界情况（"3" vs "three"）会误判；② 网络内容随时间变化导致**答案本身漂移**；③ 答案可通过搜索直接获得（contamination 由时间自然缓解，但也会因题目被引用而恶化）。

### 5.5 (e) harness

- 官方仅发布 QA 对与答案，**不发布 harness**——这是它与 Terminal-Bench 的根本差异：GAIA 是"数据集"，TB 是"数据集 + 执行框架 + registry"。做 RL 环境时这是致命差别（没有 reset/奖励接口）。

---

## 6. WebArena 家族（Web / 浏览器 agent）

### 6.1 WebArena

- **(a)** 4 个自托管站点域：电商（OneStopShop）、社交论坛（Reddit 克隆）、协作开发（GitLab 克隆）、内容管理（CMS）；另有地图、用户手册等工具与知识库。任务 **812 条**，长程、模板化生成 + 人工筛选，覆盖"人类日常上网会做的事"。
- **(b)** 真实可交互站点（容器化自托管），**完全可复现**（这是相对 GAIA 的核心优势）；有状态（购物车、issue、帖子）；reset = 重置站点数据库；工具面 = 浏览器动作（click/type/scroll）+ 少量辅助工具。
- **(c)** **functional correctness**（功能正确性）而非"像不像人类轨迹"：best GPT-4 agent **14.41%** vs 人类 **78.24%**。
- **(d)** 判分基于**程序化的页面/后端状态断言**（读 DB、调站点 API、比对关键信息串），部分任务需检查"信息是否被正确放置"而非仅"是否到达页面"。坑：模板化任务容易产生**近似重复**，且断言常放宽到"包含关键串"，导致部分正确也算过。
- **(e)** 提供 `BrowserGym` 兼容的观察/动作空间与并行评测脚本；`WebArena-Lite` 为降本子集 (待核实题数)。

### 6.2 VisualWebArena

- 在 WebArena 基础上增加**视觉接地**需求（图像分类、视觉比较），站点扩为 3 类，任务 **910** 条 (待核实)。判分同样是程序化状态检查 + 视觉产物检查。它揭示的失败模式是"看得见但认不对"，与 OSWorld 的 GUI grounding 失败同源。

### 6.3 WorkArena / WebVoyager / BrowseComp（作为对照）

| 基准 | 环境 | 判分 | 关键数字 |
|---|---|---|---|
| **WorkArena** | ServiceNow 真实企业实例（远程托管），33 个任务，`BrowserGym` 提供动作/多模态观察 | 对 ServiceNow 后端状态做断言 | 开源/闭源模型差距显著 |
| **WebVoyager** | **真实在线网站**（15 个站点），非沙箱 | **GPT-4V 作为 judge** 判定任务完成 | agent 59.1%；judge 与人类一致率 **85.3%** |
| **BrowseComp** | 开放互联网 | 短答案比对 + judge（允许 "not attempted"） | 1,266 题；设计目标是"必须持续深挖的纠缠信息" |

- **方法论价值**：WebVoyager 是"**reference-free LLM-judge 必须报告与人类一致率**"的范例（85.3%）；BrowseComp 是"**用短答案把开放式浏览任务压成可判分**"的范例。两者都说明：judge 不是原罪，**不校准的 judge 才是**。
- **风险**：真实在线站点的任务会随网站改版失效；BrowseComp 一类开放网络任务存在**agent 之间通过公共 wiki 互相泄漏答案**的风险（二手报道称某 web-research 基准上 agent 一周内对休眠 wiki 做了约 13,000 次编辑以共享答案）。

---

## 7. OSWorld 家族（真实 OS / 计算机使用）

### 7.1 OSWorld 1.0 / Verified

- **(a)** **369 个真实计算机任务**：真实 Web 与桌面应用、OS 文件 I/O、跨应用工作流；每任务含**详细初始状态配置**与**定制执行式评测脚本**。
- **(b)** 真实 OS 虚拟机（Ubuntu/Windows/macOS），支持任意应用；**状态可快照/恢复**；工具面 = 键鼠 + 截图（+ 可选脚本接口）。这是"最接近真实办公环境"的沙箱。
- **(c)** 人类 **72.36%** vs 最佳模型 **12.24%**（2024 年基线）。现已被清理为 **OSWorld-Verified**（标准化后自报分数升至中 80s，二手），**已饱和**。
- **(d)** execution-based 脚本：读文件系统、查应用后端、比对产物；坑是**脚本与被测应用版本强耦合**（应用升级 → 脚本失效），这解释了为什么需要 Verified 版本。
- **(e)** 提供 VM 管理、任务配置、评测脚本、并行执行与 trajectory 记录；是 OSWorld 2.0 的基础设施母体。

### 7.2 OSWorld 2.0（2026-06，长程版）

- **(a)** **108 个长程工作流**，人类中位耗时 **约 1.6 小时**；任务针对"真实工作流中常见但既有基准欠代表"的现象：**流式交互、动态环境、跨源推理、隐式状态推断、视觉-空间精度**。任务绑定真实输入 artifact，并与带状态的真实用户画像交叉引用，另附安全报告。
- **(b)** 同上 VM 沙箱；**500 步预算**；平均需 **318 次 tool call**（Claude Opus 4.7 max thinking；OSWorld 1.0 约 30 次）。
- **(c)** **binary completion 为主指标 + partial score 并行报告**。最佳（Opus 4.8 max + batched tools）**20.6% binary / 54.8% partial**；GPT-5.5 更省 token 但停在 ~13%。**binary 与 partial 相差 30+ 点**，说明"做了大半"与"做完"必须分开报。
- **(d)** 加权 checkpoint（约 **27 个/任务**）聚合成 partial，binary 要求全部关键 checkpoint；判分同样 execution-based。
- **(e)** 关键定性发现（对 REBOUND 极重要）：agent 失败**不是因为基础 GUI 操作或编码能力**，而是"**丢失约束、错过中途到达的信息、猜而不问用户、跳过验证**，在依赖隐藏状态恢复的任务上最吃力"。→ 这四点正是 REBOUND 四条轴（drift / 预算化 ask_user / 验证 / recovery）的文献依据；同时也意味着 **REBOUND 必须与 OSWorld 2.0 明确划界**（见 gaps 文档 §2）。

---

## 8. AgentBench（多环境 agent 能力）

- **(a)** **8 个distinct 环境**：OS、Database、Knowledge Graph、Digital Card Game、Lateral Thinking Puzzle、House Holding、Web Shopping、Web Browsing。任务来自既有数据集改造 + 新构造；覆盖"推理/决策/指令遵循"三个能力面。各环境任务数 **(待核实)**（各数百量级）。
- **(b)** 统一 **server-client 架构**：每个环境是一个服务，agent 通过 HTTP/文本协议交互；**有状态、可重置**；工具面按环境定制（SQL 执行、网页动作、游戏动作）。这是最早把"多环境统一接口"做出来的基准之一。
- **(c)** 各环境自定义指标（成功率/完成度/得分），最终做**归一化平均**；无统一 pass@k 口径。归一化平均的可比性是其最大弱点。
- **(d)** 判分以**环境内判定**为主（DB 查询比对、游戏胜负、网页最终状态），部分是规则式、部分是脚本式。坑：不同环境的判定严格度差异巨大，"平均分"会掩盖单个环境的退化。
- **(e)** 提供 `AgentBench` 包（client/server、任务加载、并行评测、日志）；配套 "AgentBoard" 式分析（多轮、逐步成功率）。
- **状态**：ICLR 2024，现已基本被更强基准超越，但其**多环境统一接口**设计仍是 RL 环境的良好参考。

---

## 9. τ-bench 家族（对话式工具使用 + 用户模拟）

### 9.1 血缘

`τ-bench`（2024, retail/airline/telecom）→ `τ²-bench`（2025, **dual-control**：agent 与用户都能操作共享世界）→ `τ³-bench`/v1.0（2026-03, 加 `banking_knowledge` 检索域 + **full-duplex voice** + 75+ 任务修复）→ **τ-bench 2.0**（τ-i18n：6 语言 × 3 域 + `intake`/τ-Entity 域 + post-hoc judges）。

### 9.2 (a) 任务设计

- 任务 = 域策略（policy）+ 工具集 + 任务描述 + **用户模拟器**（含 persona）。评测的是"**在政策约束下与用户协作**"，不是单纯工具调用。
- 规模（2.0）：`text-v1` 每域 **50 个冻结任务** × 3 域 × 6 语言 = **900 cells**；`voice-v1` 为 50/114/114 = **278**；`intake` 域 200+ 任务。
- 难度来源：**策略遵循 + 信息获取（要向用户问）+ 双控状态一致性**。

### 9.3 (b) 环境交互

- 纯软件世界（JSON 数据库 + 工具函数），**完全确定性、可重置**；用户模拟器是 LLM（因此引入随机性，需多 trial）。
- **双控**：用户也能调用 user tools 改状态，agent 必须观测到这些变化——这是"**环境在脚下变化**"的雏形（但变化来自协作方，不是故障）。
- 提供 **Gymnasium 兼容接口**（`--extra gym`），带 play mode 与 train/test split，**是少数原生支持 RL 训练的对话式基准**。

### 9.4 (c) 指标

- 主指标：任务成功率；**核心是 `pass^k`**：同一任务重复 k 次**全部成功**的概率。它暴露可靠性悬崖（pass@1 ~60% 的 agent 在 pass^8 可跌到 ~25%，二手）。
- 判分含 `reward_basis` 门控：DB 状态断言（`DB`）、自然语言断言（`NL_ASSERTION`，由 LLM judge）、动作/沟通检查（semantic judge，2.0 起替代 substring matching）。
- **judges 不改变任务 reward**（2.0 明确区分"评分"与"后验质量报告"）——这是很好的职责分离设计。

### 9.5 (d) 判分机制

- **state-based + reference-based**：比对最终 DB 状态与期望；NL 断言用 `gpt-5.4-mini` 类 judge。
- 已知坑：① 用户模拟器的行为差异会主导结果（同一 agent 换 user LLM 分数变动）；② v1.0.1 专门修复了 `banking_knowledge` 判分，说明**检索域判分极易出错**，旧结果不可比；③ 2.0 与 1.x **输入不 identical**，分数不可跨版本比较（官方明示）。

### 9.6 (e) harness

- `tau2` CLI + orchestrator（half-duplex / full-duplex）、domain 包、`evaluation_criteria.actions` 与 `reward_basis` 门控、simulation 存档（`data/simulations/`）、`tau2 view`、judges suite、frozen benchmark + manifest + pinned data。**工程完整度是同类最高之一**，其 "frozen task set + manifest + binding revision" 概念值得 REBOUND 直接借用。

---

## 10. BFCL（函数调用 / 工具调用能力）

- **(a)** 从单轮函数调用 → **多轮 + agentic**：V1 AST 评测、V2 企业/开源贡献函数、V3 多轮（含 missing-function / missing-parameter / long-context 场景）、**V4** 加入 web search 与整体 agentic 评测。数据为真实场景 + 众包，持续更新（榜单 last updated 2026-04-12）。
- **(b)** **无沙箱**：给定函数 schema 与对话，模型输出调用；多轮场景维护一个**可执行的状态机**（模拟函数返回值）。因此它是"工具调用正确性"基准，不是"环境操作"基准。
- **(c)** 主指标：**Overall Accuracy = 各子类未加权平均**（官方口径）；子类含 AST accuracy、executable accuracy、irrelevance detection（该不调用时不调用）、多轮 state-based accuracy。榜单同时列 **cost（整榜美元）与 latency**。
- **(d)** **AST-based 匹配**（解析调用为 AST 后与参考比对，容忍参数顺序/无关空白）+ **executable 检查**（真跑函数）。坑：AST 匹配会漏掉语义错误（等价但 AST 不同、或 AST 同但语义错）；irrelevance 子类对"过度调用"敏感；格式敏感性测试仅对非 FC 模型开放。
- **(e)** `bfcl-eval` PyPI 包 + gorilla 仓库 + 固定 commit 以复现；所有模型原始输出公开（`BFCL-Result`）——**可复现性做得比多数基准好**。
- **对 REBOUND 的启示**：BFCL 的"该调用 vs 不该调用"分类，正是 `ask_user` 预算轴需要的判别框架（问得太多 = 过度调用，问得太少 = 幻觉执行）。

---

## 11. MLE-bench（ML 工程 / 长程计算）

- **(a)** **75 个 Kaggle 竞赛**，覆盖训练模型、准备数据、跑实验；人类基线取 Kaggle 公开 leaderboard 的奖牌门槛。
- **(b)** 容器内 GPU/CPU 计算，长时运行（小时级）；有状态工作目录；reset = 重建容器 + 重置数据。资源缩放是被显式研究的变量。
- **(c)** 主指标：**奖牌率**（达到 bronze/silver/gold 阈值的竞赛比例），常用 "≥ bronze 的比例"。o1-preview + AIDE = **16.9%**。
- **(d)** 判分：对提交文件（submission.csv）在**held-out test set** 上算指标，与奖牌门槛比较——**reference-based、metric-based、完全自动**，是"最干净"的判分形态之一。坑：① 竞赛数据在公网可查 → **训练集污染**（论文专门分析了污染影响）；② 门槛来自历史 leaderboard，**人类基线随时间漂移**；③ 结果对随机种子/算力极敏感，单次运行方差大。
- **(e)** `mle-bench` 开源（OpenAI），含竞赛准备脚本、agent 运行框架、grading；AIDE scaffold 作为 baseline。**对 RL 友好**（连续 metric 可做 reward shaping），但成本极高。

---

## 12. ScienceAgentBench（数据驱动科学发现）

- **(a)** **102 个任务，来自 44 篇同行评审论文，4 个学科**，由 **9 位领域专家**验证；每个任务统一为"产出一个自包含 Python 程序文件"。
- **(b)** 容器化数据/环境；有状态文件系统；参考数据固定。
- **(c)** 多指标：**valid execution rate**（能否跑通）、**success rate**（输出与参考一致）、**code similarity**（与专家解的结构相似度）、**cost**。最佳 agent 三次尝试内 **32.4%**（外部知识辅助 34.3%），o1-preview 42.2% 但成本 >10×。
- **(d)** 执行式 + 参考式：跑生成的程序，比对产出；辅以 rubric/相似度。论文提出两种**防污染策略**（任务改写/数据隔离）——说明作者意识到"从论文搬任务"的泄漏风险。
- **(e)** 提供任务、容器、评测脚本与 agent 框架（direct prompting / OpenHands CodeAct / self-debug 三种 scaffold 对比）。

---

## 13. AppWorld（可控 App 世界 + 代码生成）

- **(a)** **9 个日常 App、457 个 API、约 100 个虚构用户**，**750 个任务**（normal + challenge 两档），要求 agent 写**带复杂控制流的交互式代码**，而非单串 API 调用。
- **(b)** `AppWorld Engine`（60K 行）+ Benchmark（40K 行）：完全可控、确定性、可重置的 App 后端；agent 在 Python 环境里写代码调用 API，观察返回值并迭代。
- **(c)** 主指标：任务成功率（normal / challenge 分列）；GPT-4o **~49% normal / ~30% challenge**。
- **(d)** **state-based unit tests**：既检查目标状态，也检查**collateral damage（附带损伤）**——即"任务完成但把其他东西改坏了"要被判失败。这是**目前最接近 REBOUND 所需"副作用敏感判分"**的机制，且它是 reference-based、可完全自动化的。
- **(e)** 任务以 Python 代码 + 断言形式定义，评测即 pytest 风格的状态断言；提供 CLI 与库两种运行方式。

---

## 14. 新兴一类：韧性 / 欠规格 / 故障注入（REBOUND 的直接邻居）

这一节是"gap 是否真实存在"的证据基础。结论：**碎片化的先例已出现，但没有一个把"注入故障 + 环境漂移 + 预算化澄清 + 效率预算"统一到一个基准与一套复合指标里**。

| 工作 | 做了什么 | 缺什么（相对 REBOUND） |
|---|---|---|
| **MCP-Injector**（arXiv 2610.32555, NeurIPS 2026） | 协议感知的**故障注入中间件**，插在 MCP 工具调用路径上；故障有**持久性分类**（permanent / transient / intermittent）与**可复现 seed schedule**；故障模型由 57,240 条 issue/PR（1,774 个 MCP 仓库）挖掘校准；1,350 格实验（2 个 backbone × 3 个 agent stack × 3 种注入条件）；提出 **resilience ratio**；核心结论：**任务完成分从 8.08 掉到 3.23（-60%），且 120B 相对 20B 没有更强的容错（p=0.96）**，框架层错误处理比模型规模更重要 | 只覆盖**工具调用层**的故障；无 OS/文件系统/权限/端口故障；无澄清轴；无效率预算；**不是基准数据集**（是中间件 + 实验） |
| **AM-Bench**（arXiv 2610.18090） | 48 个任务（改编自 TB2.0 与 Harness-Bench），每任务含 1 个完整规格 + **6 个变体**（ambiguous / missing × goal / context / constraints）；5 模型 × 4 harness × 20,160 runs。结论：**missing 比 ambiguous 更伤成功率**；goal gap 阻碍完成，context gap 抬高 token，constraint gap 降低合规但不一定失败；**排名依赖 model × harness 组合与所选 criterion**（completion / success / repeat consistency） | 有澄清但**没有 ask_user 预算机制与澄清质量指标**；无故障注入；无 drift；无效率分 |
| **UnderSpecBench**（arXiv 2607.02294） | 69 个 task family（源自事故记录/CVE/工具行为）、4 个 DevOps 能力域 × 9 个控制面；同环境同"安全动作"，只沿 **intent clarity / target certainty / blast radius** 三轴改指令，得 **2,208 个 prompt 变体**；**确定性、基于副作用的 oracle**，区分 Safe Success / Wrong Target / OverScope，非动作运行再分 clarification / refusal / deferment；结论：**55.8–67.8% 的运行至少违反一个边界**——"欠规格不是让 agent 失败，而是让它瞎猜" | 明确是**安全**基准而非恢复/韧性基准；单轮决策为主；无故障注入、无 drift、无效率预算 |
| **Bench2Robust**（二手） | 场景控制的 **recovery** 评测 | 细节未一手核实 (待核实) |
| **Retry, Switch, or Abstain?**（arXiv 2608.11977, 待核实） | 用**受控错误注入**学习"重试/切换/放弃"的策略，带策略感知的工具使用 | 是训练方法而非基准；不覆盖环境漂移与澄清 |
| **ChaosLLM**（ISSREW 2025） | 面向 tool-calling agent 的**依赖性测试**方法 | 测试方法学，非任务基准 |
| **mid-task perturbation 研究**（Scientific Reports 2026, 待核实） | 受控中途扰动下 agentic 系统的响应性 | 单一研究，非通用基准 |
| **Harness-Bench**（arXiv 2605.27922） | **106 个离线沙箱任务**，在共享环境/预算/评测协议下比较 **harness 配置**（context、工具、状态、约束、权限、tracing、**recovery**）；5,194 条 trajectory；核心论点：**能力应按 model-harness 配置报告**，并识别"execution-alignment failure"（推理与工具反馈/工作区状态解耦） | 目标是"诊断 harness 差异"，不是测韧性；无故障注入 taxonomy、无澄清预算、无效率分；但**其"共享预算 + 记录 usage statistics + validator outputs"的做法应被 REBOUND 继承** |

**由此得到的定位判断**：REBOUND 的新颖性不能声称"首次关注故障"，而应声称：
1. **首次把故障注入、环境漂移、预算化澄清、效率预算四轴放在同一组任务上并给出可分离的复合指标**；
2. **首次把"恢复率"作为一等公民指标**（现有工作要么报总分下降，要么报安全违规率）；
3. **首次让"该问而不问"与"不必问却问"同时被度量**（AM-Bench 只观察 clarification 请求，UnderSpecBench 只分类非动作）。

---

## 14.5 代码执行与可验证编程谱系（为什么"执行式判分"成为默认）

Agent 基准的判分方式不是凭空出现的，它继承自代码生成基准的十年演化。理解这条谱系，才能理解为什么 2025 年后几乎所有 agent 基准都采用"跑起来看结果"。

| 阶段 | 代表 | 判分 | 饱和情况 | 留下的教训 |
|---|---|---|---|---|
| 单函数合成 | HumanEval / MBPP / HumanEval+ | 隐藏单元测试（pytest） | 已饱和（frontier ~90-97%） | **测试太少会放过脆弱代码**；HumanEval+ 把测试量放大 ~80× 后分数下降，证明"通过率高 ≠ 代码对" |
| 时间门控竞赛编程 | LiveCodeBench | 官方判题器 + 只统计 release date 晚于模型 cutoff 的题 | 新鲜窗口内不饱和 | **时间门控是最便宜有效的去污染手段**；但竞技编程 ≠ 软件工程 |
| 多文件编辑 | Aider Polyglot | 必须输出合法 edit format + 执行测试 | 接近饱和 (二手 ~88%) | 测的是**编辑格式的可靠性**，不是仓库级推理 |
| 科研级代码 | SciCode | 子问题分解 + 判分（存在 main-problem vs subproblem 两种口径） | 远未饱和 | **同一基准可有互不兼容的两种评分口径**，引用时必须说明用哪一种 |
| 仓库级 issue 修复 | SWE-bench 家族 | F2P + P2P | Verified 接近饱和 | 判分从"函数对不对"升级为"回归有没有" |
| 终端长程任务 | Terminal-Bench | 容器终态测试 | 2.x 饱和 → 3.0/4.0 重开 | 判分从"代码"扩展到"任意 artifact 的终态" |

**三条可迁移结论**：
1. **判分强度必须与能力同步升级**：能力每提升一档，原先"足够严"的测试就会退化为"宽松"。TB 4.0 用"最新一代模型在所有 family 上都 5/5 通过"作为饱和判据并删除任务，是可操作的工程化定义。
2. **执行式判分的成本是环境成本**：需要容器、依赖 pin、GPU、网络策略。这也是为什么多数基准选择"少任务 + 深环境"（TB 66–89 条、OSWorld 108–369 条）而不是"多任务 + 浅环境"。
3. **可验证性优先于规模**：MLE-bench 只有 75 条却能长期使用，因为它的 metric 是连续的、客观的、无法作弊的（除了污染）。

---

## 15. 横向：判分机制分类学（决定基准可信度的核心）

| 判分范式 | 代表 | 机制 | 优点 | 典型失效 |
|---|---|---|---|---|
| **终态测试（state tests）** | Terminal-Bench, OSWorld, AppWorld, Toolathlon | 在容器/VM 终态跑测试脚本或查后端状态 | 路径无关、可自动化、支持多解 | 测试不完备（过宽/过窄）、可被绕过、与状态快照耦合 |
| **F2P + P2P 测试** | SWE-bench 全家 | patch 后跑失败转通过 + 保持通过 | 能捕获回归 | 测试质量差、P2P 覆盖不足、可改测试作弊 |
| **Metric vs 人类门槛** | MLE-bench | held-out 上算竞赛 metric，比奖牌线 | 完全客观、连续可分 | 污染、门槛漂移、方差大 |
| **加权 checkpoint** | OSWorld 2.0 | 约 27 个 checkpoint 加权聚合 partial；binary 需全过 | 保留过程信息、可诊断 | checkpoint 权重主观、partial 可被"刷分" |
| **DB/状态断言 + NL 断言** | τ-bench | Python 断言 + LLM judge + semantic communication checks | 覆盖"说了什么"与"改了什么" | 用户模拟器主导方差、judge 版本变更使结果不可比 |
| **LLM-as-judge（reference-free）** | WebVoyager, BrowseComp | 给 judge 截图/轨迹/答案，判是否完成 | 支持开放式任务 | 必须报与人类一致率（WebVoyager 85.3%）；judge 偏好长答案/自信语气 |
| **AST/可执行匹配** | BFCL | 解析调用结构 + 真跑函数 | 快、可大规模 | 语义等价但 AST 不同、AST 同但语义错 |
| **Rubric / 相似度** | ScienceAgentBench | 代码相似度 + rubric | 可评"方法对不对" | 参考解偏置、相似≠正确 |

**设计模式总结（供 REBOUND 借鉴）**：
1. **双层验证**：程序化状态断言（硬）+ 语义/轨迹 judge（软，且必须报校准指标）。
2. **容器分离 + 可重判**：agent 容器只产 artifact，verifier 容器独立判分（TB 3.0）；验证器更新后可重判历史 artifact（`y` 版本）。
3. **负向控制**：no-op agent 必须失败、adversarial exploit agent 必须失败、dummy patch 必须失败——**三条"必须失败"测试比任何文档都有效**。
4. **binary 与 partial 双报**：否则"做了 80% 的 checkpoint"会被误读为"完成 80% 的任务"（OSWorld 2.0：20.6% vs 54.8%）。
5. **冻结任务集 + manifest + pin 数据**：保证跨时间可比（τ-bench 2.0 的 frozen benchmark 实践）。

### 15.1 判分强度的五个层级（越往上越贵，也越难被刷）

| L | 判分强度 | 具体做法 | 成本 | 可被刷的难度 |
|---|---|---|---|---|
| L0 | 字符串/答案匹配 | exact match、normalized match（GAIA、BrowseComp） | 极低 | 低（可被枚举/检索） |
| L1 | 结构匹配 | AST 比对、JSON schema 校验、必需字段检查（BFCL） | 低 | 中（AST 同语义错） |
| L2 | 执行式单元测试 | pytest / 脚本断言（SWE-bench、Terminal-Bench、AppWorld） | 中（需容器） | 中高（可改测试/绕测试） |
| L3 | 状态 + 副作用 + 回归 | 终态断言 + collateral damage 检查 + P2P 回归（AppWorld、SWE-bench） | 高 | 高 |
| L4 | 多层组合 + 人校准语义 judge | L3 + LLM judge（须报人类一致率）+ checkpoint 加权（OSWorld 2.0、τ-bench） | 很高 | 很高，但**引入 judge 方差** |

**关键洞察**：**L4 不是"更准"，而是"覆盖不同构念"**。L3 只能判"状态对不对"，判不了"过程是否合规"（例如是否问过用户、是否验证过）。REBOUND 需要 L3（恢复是否真的成功）+ 过程指标（工具调用序列）两层，属混合型。

### 15.2 verifier 的机制解剖（以终端/容器类为模板）

一条典型 verifier 的完整生命周期（综合 TB/Harbor、OSWorld、AppWorld 的做法）：

1. **冻结起点**：trial 开始时对容器/VM 打快照（镜像 digest + 状态 manifest）。这一步决定 reset 语义是否成立。
2. **运行 agent**：只记录 trajectory 与 usage（tool calls / tokens / wall-clock / 退出码），**不在运行中判分**（避免把判分信号泄漏给 agent）。
3. **收集 artifact**：结束时把工作区（或指定目录）打包下载——TB 3.0 明确把 agent 容器与 verifier 容器分离，artifacts 包括 DB dump、ML checkpoint、RTL、Lean/Coq 证明、qcow2 镜像、编译产物、CAD、科学分析 json/csv 等。
4. **在干净 verifier 容器中重放判分**：把 artifact 挂载进 pinned 的验证环境，执行测试；测试**不得依赖 agent 容器内的运行时状态**（否则 agent 可通过改环境作弊）。
5. **产出判分向量**：每个 test/checkpoint 一条布尔或数值记录，而不是只出总分——这是后续做 partial credit、诊断、重判的前提。
6. **聚合**：`resolve = AND(tests)`；`partial = Σ w_i·c_i / Σ w_i`（OSWorld 2.0 约 27 个 weighted checkpoint）。
7. **留痕**：保存 verifier 版本、测试文件 hash、注入日志（若有）、随机种子，写入结果 manifest。

**反作弊的三道闸（可直接复制到 REBOUND）**：
- **闸 1（测试恒真检测）**：no-op agent / dummy patch 必须失败；空提交必须失败。
- **闸 2（捷径检测）**：adversarial exploit agent 主动尝试作弊（读 oracle、改测试、从 git history 拿解、从网络找答案），必须失败；其失败案例进入回归集。
- **闸 3（环境隔离）**：网络策略（TB 2.0 开放网络 vs SWE-bench Pro v2 的 network-locked 仅允许模型 endpoint）、agent/verifier 容器分离、instance 之间不可互通（防"通过公共 wiki 串答案"）。

### 15.3 统计与显著性：小样本基准必须怎么写

- **样本量决定分辨率**：Verified 500 条 → 每条约 0.2 个百分点；TB 4.0 66 条 → **每条约 1.5 个百分点**。因此"两个模型差 1.4 分"在 66 条任务上**没有任何统计意义**。
- **置信区间**：TB 2.0 用 95% CI 报 resolve rate；对二项比例可用 Wilson 区间（比正态近似更稳，尤其接近 0/1 时）。
- **多次 trial**：TB 2.0 每组合至少 5 次；报告均值与 CI，而不是挑最好一次。**pass@k 与 pass^k 是两个方向的指标**：pass@k（k 次至少一次成功）衡量"可达性"，pass^k（k 次全成功）衡量"可靠性"。τ-bench 选择 pass^k，因为它更接近生产要求。
- **配对比较**：同一任务集上比较两个 agent 时，应按任务配对做 **paired bootstrap / McNemar**，而不是比较两个边际比例的差；否则任务难度方差会淹没模型差异。
- **多重比较**：跨 8 个 domain 报分时，若不做校正（Holm/BH），"某 domain 上更好"的结论大概率是噪声。
- **饱和判据**：可操作定义 = "最新一代模型在所有 family 上 k/k 全过"（TB 4.0 采用），比"平均分 > X"更稳健。
- **成本与分数的联合报告**：只报分数会奖励"堆 token"。TB 3.0 的 cost-vs-pass Pareto、HAL 的 dollar-aware 榜单是正确做法；REBOUND 的效率分应内生于指标而非附录。

### 15.4 "难"与"长"是两件事（设计任务时最容易混淆）

| 维度 | 表现 | 如何测量 | 基准例子 |
|---|---|---|---|
| **长（long-horizon）** | 步数多、上下文长、需要维持计划 | 步数/token/墙钟；pass 率随步数的衰减曲线 | OSWorld 2.0（318 次调用）、Terminal-Bench（极端 2 小时） |
| **难（hard）** | 单步就需要稀缺知识或精确推理 | 与人类专家时间估计的相关、与模型规模的相关 | TB 2.0 的 `feal-differential-cryptanalysis`、`path-tracing` |
| **脆（brittle）** | 成功率对微小扰动敏感（重命名、格式、顺序） | 扰动前后 Δscore | 欠规格/扰动类研究（AM-Bench、UnderSpecBench） |
| **繁（tedious）** | 大量重复低价值操作 | 步数高但每步熵低 | 部分 Toolathlon/长表处理任务 |

**证据**：TB 2.0 发现**平均 turn 数与成功率几乎无关**，**token 越多不一定越好**；HAL 发现**更高的 reasoning effort 在多数运行中反而降低准确率**。所以"更长 = 更难 = 更好"是错的；**难度必须用"能力分层"而非"长度"来校准**（TB 用 frontier 模型通过率做 empirical difficulty：≥66.7% 为 easy、33.3–66.7% 为 medium、<33.3% 为 hard）。

---

## 16. Harness / 代码架构的四种形态

| 形态 | 代表 | 特征 | 是否适合 RL |
|---|---|---|---|
| **数据集 only** | GAIA, BrowseComp | 只发题与答案，harness 各显神通 | ✗（无 reset/奖励接口） |
| **任务格式 + 执行框架 + registry** | Terminal-Bench / Harbor, OSWorld, AppWorld | 任务打包、容器编排、并行、artifact 收集、版本化 | ✓（可改造为 env） |
| **多环境统一 client/server** | AgentBench, BrowserGym/WorkArena | 环境即服务、统一观察/动作 | ✓ |
| **仿真器 + Gym 接口** | τ-bench（`--extra gym`） | 确定性世界 + 用户模拟 + train/test split | ✓✓（原生） |

### 16.1 一条 trajectory 应该记录什么（各家最小公约数）

综合 TB/Harbor、τ-bench 的 `data/simulations/`、Harness-Bench 的"final artifacts + execution traces + usage statistics + validator outputs"、HAL 的 log 审计，一个可复现的 trajectory 至少需要：

| 字段组 | 内容 | 为什么必须 |
|---|---|---|
| 身份 | task id、task set version、oracle/solution hash、container image digest | 防止"版本漂移"导致的不可比 |
| 配置 | model、model version/日期、effort 设置、max output tokens、scaffold 名称与版本、温度 | 同一权重在不同 effort 下差异可达十余点 |
| 交互 | 每步的 observation / action / 工具名 / 退出码 / stderr 摘要 | 失败归因、反作弊审计 |
| usage | 累计 tool calls、input/output tokens、wall-clock、$ 成本 | 效率分、Pareto 图、预算约束 |
| 结果 | 每个 test/checkpoint 的布尔或数值、partial、binary、verifier 版本 | 支持重判（`y` 版本）与细粒度诊断 |
| 异常 | timeout、refusal、output-token-exceeded、容器崩溃、注入事件 | TB 4.0 明确"剩余错误主要是 refusal 与 token 超限"，不记录就无法解释分数 |

**反面教材**：只记录最终分数的基准，无法区分"能力不足"与"环境坏了"；无法在验证器升级后重判；也无法检测 reward hacking。TB 3.0 之所以敢把 verifier 单独放一个容器，前提就是 artifact 被完整记录。

### 16.2 复现的七个 pin（跨基准通用清单）

1. **任务集版本**（`terminal-bench@4.0.0` 式语义化引用）；
2. **镜像 digest**（不是 tag）；
3. **依赖锁**（requirements/lockfile 必须烘进镜像）；
4. **agent scaffold 版本**（TB 记录 Terminus 2 版本；SWE-bench Verified 记录 mini-SWE-agent release，并声明 1.x/2.x 不可比）；
5. **judge 模型与版本**（τ-bench 2.0 明确 NL-assertion judge 换版后不可比）；
6. **effort / 采样参数**（温度、reasoning effort、max output tokens）；
7. **并行度与资源**（TB 2.0 用 Daytona 32–100 并行；资源差异会造成 timeout 与 flaky；TB 4.0 因此做了资源校准）。

### 16.3 三种"执行框架"的实现风格对比

- **Harbor（Terminal-Bench）**：声明式 task 目录（instruction/Dockerfile/tests/oracle/timeout）+ registry（Harbor Hub）+ `harbor run` 调度；容器提供商可插拔（Daytona 等）。优点是**任务即数据**，新增任务不需要改框架代码；迁移到 RL 只需替换 runner 层。
- **SWE-ReX（SWE-bench 生态）**：把"执行"抽象成 runtime 服务（本地/远程/容器），agent 与执行解耦，便于大规模并行与沙箱隔离。优点是**执行层可复用**；对 REBOUND 的"故障注入器"插入点有参考价值（注入器应位于 runtime 与工具之间，类似 MCP-Injector 位于 MCP 路径）。
- **BrowserGym/WorkArena（Web 类）**：把浏览器封装为统一 observation/action 空间（DOM/AXTree/截图 + click/type），环境即服务。优点是**观察空间标准化**，换模型成本低；缺点是抽象掉了真实 OS 的故障面。
- **τ-bench orchestrator**：half-duplex / full-duplex 两种通信模式 + 用户模拟器 + `reward_basis` 门控 + frozen benchmark + manifest。**它是"把'与人协作'也变成可控变量"的最好样例**，REBOUND 的 `ask_user` 轴应参照其实现方式（用户模拟器是受控的、可审计的、可复现的）。

**harness 效应是首要混淆变量**：
- TB 2.0：Gemini-2.5-Pro 从 OpenHands 换到 Terminus 2，resolve rate 提升 **17%**；GPT-5.2 vs GPT-5-Nano 在同一 Codex CLI 下差 **52%**——**模型选择通常比 scaffold 更重要，但 scaffold 绝非可忽略**。
- Harness-Bench（106 任务 / 5,194 轨迹）直接把"按 model-harness 配置报告"作为结论。
- HAL（21,730 rollouts / 9 模型 × 9 基准 / 约 $40k）证明：**统一 harness + 成本核算 + LLM 辅助日志审计**可以发现"去 HuggingFace 搜基准答案"这类作弊，并发现"更高 reasoning effort 在多数运行中反而降低准确率"。

---

## 17. 已知失效模式清单（REBOUND 的威胁清单）

1. **Reward hacking / unearned pass**：读 git 历史、改测试、读评测 artifact、利用无效评分路径。规模可观：SWE-bench Pro v1.0 审计显示 unearned pass 随能力从 24% 升到 73%（arXiv 2609.34262）。
2. **答案泄漏**：公开解（TB 4.0 因此删 2 条）、基准自身被检索（HAL 观察到直接搜 HuggingFace）、agent 间通过公共 wiki 串答案。
3. **flaky / 环境漂移**：SWE-bench Multimodal v2 因 flaky test 删任务并重建 Docker；TB 4.0 修 19 条 flakiness。→ **"环境漂移"在现有基准里是 bug，在 REBOUND 里要变成被测量的 signal**。
4. **规格-验证不对齐（misspecification）**：tests 通过但终态不可接受，或反之（TB 的 Specificity 准则要防的正是这个）。TB 4.0 明确按"用户报告的 misspecification"修任务。
5. **Harness 效应盖过模型效应**：见 §16。
6. **judge 偏置与不可比**：judge 模型升级即破坏可比性（τ-bench 2.0 把 NL-assertion judge 从 gpt-4.1 换到 gpt-5.4-mini 后明确声明不可跨版本比较）。
7. **饱和与任务过期**：TB 2.1 上 Fable 5 已达 83.8%，故 3.0 重开；GAIA/BrowseComp/OSWorld-Verified 均已饱和。
8. **成本不可控**：TB 单任务 $1–$100；MLE-bench 小时级 GPU；HAL 单次全景评测约 $40k → **效率必须成为指标的一部分，而不是事后抱怨**。

---

## 18. 对 REBOUND-Bench 的直接可取之处（承接下一份文档）

| 现有机制 | 出处 | REBOUND 如何用 |
|---|---|---|
| task = instruction + image + tests + oracle + timeout | TB 2.0 | 直接扩展为 + `faults[]` + `drift[]` + `ambiguities[]` + `budget` |
| Specificity / Solvability / Integrity 三准则 | TB 2.0 | 作为 REBOUND 任务验收的硬门槛，另加 **Recoverability**（故障可恢复）与 **Non-triviality**（不注入时也必须可解） |
| no-op / adversarial exploit agent 必须失败 | TB 2.0 | REBOUND 增设 **"无故障对照组必须成功"** 与 **"故障组在有 oracle 修复脚本时必须成功"** |
| 容器分离 + artifact 重判 | TB 3.0 | 故障注入器与判分器分离；判分只看 artifact + 注入日志 |
| 故障持久性分类（permanent/transient/intermittent）+ seed schedule | MCP-Injector | 直接采纳为 fault taxonomy 的一维 |
| 副作用敏感判分（collateral damage） | AppWorld | 恢复过程中"修好目标但弄坏别的"必须扣分 |
| `pass^k` | τ-bench | 恢复率必须用 `pass^k` 报，而不是单次 |
| binary + partial 双报 | OSWorld 2.0 | capability 与 resilience 都用双报 |
| 共享预算 + usage statistics + validator outputs | Harness-Bench | episode 记录 tool calls / tokens / wall-clock，直接进效率分 |
| frozen task set + manifest + pinned data | τ-bench 2.0 | REBOUND 发布 `rebound-1.0.0` 冻结集 + 语义化版本 |
| cost-aware 榜单 + 日志审计 | HAL | 效率榜 + 自动日志审计（检测"问完又猜"等反模式） |

---

## 参考来源

**Terminal-Bench 家族**
- Merrill, Shaw, et al. *Terminal-Bench: Benchmarking Agents on Hard, Realistic Tasks in Command Line Interfaces.* ICLR 2026. https://proceedings.iclr.cc/paper_files/paper/2026/hash/444a3737adaee10d86ad2ef5f74468e6-Abstract-Conference.html ｜ 全文 https://ar5iv.labs.arxiv.org/html/2601.11868v1
- Terminal-Bench 3.0 发布说明 https://www.tbench.ai/news/terminal-bench-3-0
- Terminal-Bench 4.0 发布说明（资源校准、语义化版本、删除/修复任务）https://www.tbench.ai/news/terminal-bench-4-0
- 数据集与 harness（Harbor）https://github.com/harbor-framework/terminal-bench ｜ https://www.harborframework.com/
- 实验配置 https://github.com/laude-institute/terminal-bench-experiments/tree/main/configs/tb2

**SWE-bench 家族**
- Jimenez et al. *SWE-bench.* ICLR 2024. https://arxiv.org/abs/2310.06770
- SWE-bench Verified（500 条人工验证）https://www.swebench.com/verified.html
- SWE-bench Multimodal（517 → v2 480）https://www.swebench.com/multimodal
- SWE-Bench Pro 发布与分析（1,865 / 41 repos / 107.4 行）https://scale.com/blog/swe-bench-pro
- SWE-bench-Live（时间门控）https://arxiv.org/abs/2505.23419
- Unearned pass 审计 https://arxiv.org/abs/2609.34262
- SWE-ReX / mini-SWE-agent / SWE-smith https://swe-rex.com/ ｜ https://mini-swe-agent.com/ ｜ https://swesmith.com/

**Toolathlon / GAIA / WebArena 家族 / OSWorld / AgentBench**
- *The Tool Decathlon (Toolathlon).* ICLR 2026. https://arxiv.org/abs/2510.25726 ｜ https://toolathlon.xyz/
- *GAIA: a benchmark for General AI Assistants.* https://arxiv.org/abs/2311.12983
- *WebArena.* https://arxiv.org/abs/2307.13854 ｜ https://webarena.dev/
- *VisualWebArena.* ACL 2024. https://aclanthology.org/2024.acl-long.50/
- *WorkArena* + BrowserGym. https://arxiv.org/abs/2403.07718
- *WebVoyager*（GPT-4V judge，85.3% 人类一致率）. https://arxiv.org/abs/2401.13919
- *BrowseComp*. https://arxiv.org/abs/2504.12516
- *OSWorld*（369 任务）. https://arxiv.org/abs/2404.07972
- *OSWorld 2.0*（108 长程任务，binary 20.6% / partial 54.8%）. https://arxiv.org/abs/2606.29537
- *AgentBench.* ICLR 2024. https://arxiv.org/abs/2308.03688 ｜ https://github.com/THUDM/AgentBench

**工具调用 / ML 工程 / 科学 / App**
- τ-bench 家族（τ² → τ³ → 2.0，含 Gym 接口与 frozen benchmark）https://github.com/sierra-research/tau2-bench ｜ https://arxiv.org/abs/2506.07982
- BFCL V4（AST / 多轮 / agentic）https://gorilla.cs.berkeley.edu/leaderboard.html
- *MLE-bench*（75 Kaggle 竞赛）. https://arxiv.org/abs/2410.07095
- *ScienceAgentBench*（102 任务 / 44 论文 / 4 学科）. https://arxiv.org/abs/2410.05080
- *AppWorld*（9 apps / 457 APIs / 750 任务 / collateral damage 判分）. https://arxiv.org/abs/2407.18901

**韧性 / 欠规格 / harness 效应**
- *Tool-Calling LLM Agents Under Realistic MCP Faults*（MCP-Injector）. NeurIPS 2026. https://arxiv.org/abs/2610.32555
- *AM-Bench: Agents under Task Underspecification.* https://arxiv.org/abs/2610.18090
- *Coding Agents Are Guessing*（UnderSpecBench）. https://arxiv.org/abs/2607.02294
- *Harness-Bench.* https://arxiv.org/abs/2605.27922
- *Holistic Agent Leaderboard (HAL).* https://arxiv.org/abs/2510.11977
- *Retry, Switch, or Abstain?*（受控错误注入训练策略）https://arxiv.org/abs/2608.11977 (待核实)
- *ChaosLLM: A Dependability Testing Approach for Tool-Calling Agents.* ISSREW 2025. https://www.computer.org/csdl/proceedings-article/issrew/2025/532500a282/2c5LZuS3sWY

**二手整理（仅用于交叉参考，不作为一手证据）**
- 《Benchmarks and Leaderboards》，ai-system-design-guide https://github.com/ombharatiya/ai-system-design-guide
