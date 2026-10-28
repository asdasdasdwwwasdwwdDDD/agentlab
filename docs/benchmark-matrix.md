# 基准对比矩阵（2026-10-26）

> 配套 `docs/benchmark-survey.md`（机制细节）与 `docs/gaps-and-proposal.md`（gap 与提案）。
> 说明：**"可 RL 训练"** 指"是否具备确定性 reset + 程序化奖励 + 可并行采样"三件套；"部分"表示可改造但需自建接口。数字带 `(待核实)` 者不要直接引用。
> 所有分数都依赖 harness 与版本，**不可跨行比较**。

---

## 1. 主表

| Benchmark | 领域 | 任务数/规模 | 环境类型 | 交互形态 | 判分方式 | 主指标 | 可 RL 训练 | 主要局限 |
|---|---|---|---|---|---|---|---|---|
| **Terminal-Bench 2.0** | 终端/CLI 综合（SWE、系统、科学、安全、逆向…） | 89（自 229 提案选出，93 贡献者） | Docker 单容器 | 多轮 shell（Terminus 2 单工具 / 亦可任意工具） | 容器**终态测试**（不看命令与 stdout） | resolve rate（≥5 trials，95% CI） | 部分 | 联网可查 oracle；已饱和趋势；无故障/漂移 |
| **Terminal-Bench 3.0** | 同上 + 非编码工作（RTL、证明、CAD、VM、音乐…） | 74（7 domain） | 多容器网络 + GPU | 多轮、artifact 产出 | agent/verifier **容器分离**后跑测试 | pass rate | 部分 | 分数低但成本高；任务依 domain expert 供给 |
| **Terminal-Bench 4.0** | 同上（3.0 修整版） | 66（74−8，修 19） | 同上 + 资源校准 | 同上 | 同上（8h 统一超时） | pass rate + cost Pareto | 部分 | 4 周即换代；验证器仍可被攻（4.1 才上 tamper-resistant） |
| **Terminal-Bench-Science 0.1** | 科学生产工作流（生命/物理/地学/数学/工程） | 70（自 920 提案）(二手) | 容器 | 多轮 | 终态测试 | pass rate | 部分 | 新、样本小、稳定性未证 |
| **SWE-bench Verified** | Python 仓库 issue 修复 | 500（自 2,294） | Docker + repo | 多轮 bash/编辑 | **F2P + P2P** pytest | % Resolved | ✓（成本高） | 近饱和 + 部分污染；测试质量缺陷；60%+ 任务测试有问题(二手) |
| **SWE-bench Pro** | 多语言复杂仓库（public/held-out/commercial） | 1,865（731/858/276）；41 repo；均 107.4 行/4.1 文件 | Docker | 多轮（SWE-agent） | F2P+P2P + 重判 | % Resolved | ✓ | 公开集 ~饱和；私有集不可复现；unearned pass 严重（24%→73%） |
| **SWE-bench Multimodal** | 视觉/前端 issue（含截图） | 517 → v2 **480** | Docker + 浏览器 | 多轮 | JS 判分 + 视觉资产断言 | % Resolved | 部分 | 环境漂移/flaky（v2 才重建）；视觉断言脆弱 |
| **SWE-bench-Live / SWE-rebench** | 时间门控的真实 issue | 持续更新 | Docker | 多轮 | F2P+P2P | % Resolved | ✓ | 任务质量波动；需持续运维 |
| **Toolathlon（Tool Decathlon）** | 32 App / 604 MCP 工具 跨应用长程 | 108（均 ~20 turns） | 真实应用后端 + MCP | 多轮工具调用 | 每任务 dedicated 评测脚本（查后端状态） | success rate | 部分 | 无 OS 级故障面；状态快照与脚本强耦合；MCP 抽象弱化"环境" |
| **GAIA** | 通用助手/深研究 | 466 题（300 保密答案） | **无**（开放互联网） | ReAct + 浏览器/工具 | 短答案归一化匹配 | accuracy | ✗（无 reset/奖励接口） | 不可复现；答案漂移；榜单被 ensemble 占据 |
| **WebArena** | 电商/论坛/代码托管/CMS | 812 (待核实题数) | 自托管真实站点（4 域） | 浏览器动作 | **functional correctness**（页面/后端状态断言） | success rate | ✓ | 模板化近似重复；断言过宽；站点与脚本耦合 |
| **VisualWebArena** | 同上 + 视觉接地 | 910 (待核实) | 3 站点 | 浏览器 + 图像 | 状态断言 + 视觉检查 | success rate | ✓ | 视觉判分脆弱 |
| **WebArena-Lite** | 降本子集 | (待核实) | 同 WebArena | 同上 | 同上 | success rate | ✓ | 抽样偏差 |
| **WorkArena** | 企业软件（ServiceNow）知识工作 | 33（WorkArena++ 更大） | 远程托管的真实实例 | BrowserGym 动作/多模态观察 | 后端状态断言 | success rate | 部分 | 依赖单一商业平台；任务类型集中 |
| **WebVoyager** | 真实在线站点（15 个） | 643 (待核实) | **真实互联网** | 浏览器 | **GPT-4V judge**（与人类一致率 85.3%） | success rate | ✗ | 不可复现；站点改版即失效；judge 方差 |
| **BrowseComp** | 深挖式网页检索 | 1,266 题 | 开放互联网 | 搜索/浏览 | 短答案比对 + judge（允许 not attempted） | accuracy | ✗ | 已饱和；答案可通过搜索获得；agent 间可串答案 |
| **OSWorld 1.0 / Verified** | 真实 OS 桌面 + 跨应用工作流 | 369 | **真实 VM**（Ubuntu/Win/macOS） | 键鼠 + 截图 | execution-based 脚本 | success rate（人类 72.36%） | ✓ | 已饱和（Verified 中 80s）；脚本与应用版本强耦合 |
| **OSWorld 2.0** | 长程真实工作流（流式交互、跨源推理、隐式状态） | 108（人类中位 1.6h；均 318 次调用） | 真实 VM | 键鼠 + 截图，**500 步预算** | 加权 **checkpoint** + 全过判定 | **binary 为主 + partial 并报**（20.6% / 54.8%） | ✓ | 成本极高；checkpoint 权重主观；仍以"无注入"为前提 |
| **AgentBench** | 8 环境（OS/DB/KG/卡牌/谜题/家务/购物/浏览） | 8 × 数百 (待核实) | client/server 多环境 | 多轮、环境定制动作 | 环境内规则/脚本判定 | 归一化平均分 | ✓ | 平均分掩盖单环境退化；已过时 |
| **τ-bench 2.0（τ-i18n）** | 客服协作（airline/retail/telecom + banking_knowledge + intake） | 50 任务/域 × 3 域 × 6 语言 = 900 cells；voice 278；intake 200+ | 确定性 JSON 世界 + **用户模拟器** | 多轮对话 + 双控工具 | DB 断言 + NL 断言（judge）+ 沟通检查 | success rate + **pass^k** | ✓✓（原生 Gym） | 用户模拟器主导方差；跨版本不可比；域窄 |
| **BFCL V4** | 函数/工具调用（单轮 + 多轮 + agentic + web search） | 子类众多，持续更新 (待核实总数) | **无沙箱**（状态机模拟） | 单/多轮调用 | AST 匹配 + 可执行检查 + irrelevance | Overall Accuracy（子类未加权平均）+ cost/latency | 部分 | 非环境操作；AST 漏语义错；多轮状态机简化 |
| **MLE-bench** | Kaggle ML 工程 | 75 竞赛 | 容器 + GPU | 长时自主开发 | held-out metric vs 奖牌线 | medal rate（≥bronze 16.9%） | ✓（reward 连续） | 污染；门槛漂移；单次方差大；成本极高 |
| **ScienceAgentBench** | 数据驱动科学（4 学科） | 102（44 论文，9 专家） | 容器 | 单/多轮生成 Python 程序 | 执行 + 参考比对 + 代码相似度 | success / valid-exec / cost | 部分 | 参考解偏置；结果对 prompt 敏感 |
| **AppWorld** | 9 App / 457 API / ~100 用户 | 750（normal + challenge） | 可控 App 引擎（确定性） | 写代码调用 API | **state-based unit tests + collateral damage** | success rate（49%/30%） | ✓ | 合成世界；API 面虽大但语义单一 |
| **Harness-Bench** | harness 配置诊断（离线沙箱） | 106（5,194 轨迹） | 沙箱工作区 | 多轮 + 共享预算 | validator outputs + 产物检查 | 完成度 + 过程质量 + 效率 | 部分 | 目标是 harness 差异，不是韧性；无故障/澄清轴 |
| **AM-Bench** | 欠规格（ambiguous/missing × goal/context/constraint） | 48 × (1 完整 + 6 变体) | 继承 TB2.0 / Harness-Bench | 多轮 | 继承任务验证器 + 一致性指标 | completion / success / repeat consistency | 部分 | 无 ask_user 预算机制；无故障/漂移/效率分 |
| **UnderSpecBench** | DevOps 欠规格的安全边界 | 69 family × 3 轴 → 2,208 prompt 变体 | 确定性 DevOps 环境 | 单轮决策为主 | **副作用 oracle**：Safe Success / Wrong Target / OverScope | 边界违反率（55.8–67.8%） | 部分 | 安全而非恢复；无多故障序列；无预算轴 |
| **MCP-Injector**（非数据集） | MCP 工具故障注入 | 1,350 格实验 | MCP 中间件 | 多轮 | 任务完成分 + resilience ratio | completion score / resilience ratio | ✓（中间件可复用） | 仅工具层故障；无 OS/文件/权限故障；无澄清与效率轴 |
| **HAL**（meta-评测） | 跨 9 基准的统一 harness | 21,730 rollouts（9 模型 × 9 基准） | 数百 VM 并行 | 统一 agent 协议 | 复用各基准验证器 + 成本核算 + 日志审计 | accuracy + $ cost | —（评测基础设施） | 不是新任务集；继承组件缺陷 |

---

## 2. 设计模式总结

### 2.1 验证器通常如何被"组合"出来

观察上表可归纳出 5 种被反复复用的组合范式：

1. **`终态测试 + oracle 反向验证`**（TB、OSWorld、AppWorld）：正向用 tests 判终态；反向用 oracle solution 证明可解，用 no-op agent 证明测试非恒真。**这是"可自动判分"最稳的骨架**。
2. **`F2P + P2P`**（SWE-bench）：把"修好"与"没弄坏"拆成两组测试，天然携带回归语义。其弱点是 P2P 覆盖有限，且测试文件本身可被改。
3. **`metric vs 人类门槛`**（MLE-bench）：不需要写测试，只需要 held-out 数据 + 客观 metric + 人类基线。**最省人力，但只适用于有客观 metric 的任务**。
4. **`checkpoint 加权 + 全过门`**（OSWorld 2.0）：partial 用于诊断与信号密度，binary 用于结论。**双报是解决"部分完成"信息损失的标准方案**。
5. **`状态断言 + 语义 judge`**（τ-bench、WebVoyager）：硬判分覆盖"世界被改成什么"，软判分覆盖"过程/表达是否合规"。**软判分必须报与人类的一致率**（WebVoyager 85.3%；TB 的失败归因 judge 报 90% 一致率）。

**几乎所有的坑都来自"组合方式不当"**：把软判分当硬判分（无校准 judge 直接出结论）、把 partial 当 binary（80% checkpoint ≠ 完成）、把"测试通过"当"任务完成"（规格-验证不对齐）。

### 2.2 "难" vs "长"：可操作区分

- **长**：步数/token/墙钟大。例：OSWorld 2.0 均 318 次调用、1.6 人类小时；TB 极端 2 小时 / 近 1 亿 token。**长本身不产生区分度**——TB 2.0 实测"turn 数与成功率几乎无关"。
- **难**：**能力分层明显**。可操作定义 = frontier 模型通过率：≥66.7% easy / 33.3–66.7% medium / <33.3% hard（TB 2.0 的 empirical difficulty）。人类时间估计与实测难度只有 r=0.436 的相关，说明**作者主观难度不可替代实测**。
- **脆**：对无害扰动敏感（重命名、格式、顺序、指令清晰度）。AM-Bench 与 UnderSpecBench 证明：**在任务能力不变的前提下只改指令清晰度，成功率与违规率都会大幅变动**——这是"脆"的干净测量。
- **繁**：步数多但每步熵低（大量重复读表/翻页）。它抬高成本但不抬高区分度，是**基准设计应主动剔除**的部分（否则测的是耐心）。

**结论**：设计新基准时，难度应通过"注入受控的稀缺性"（稀缺知识、稀缺观测、稀缺权限）而非"增加步数"来获得；长度只应作为**预算轴**被显式测量，而不是被当成难度。

### 2.3 自动判分的典型失效模式（按发生频率排序）

1. **规格-验证不对齐（misspecification）**：测试过宽（错解通过）或过窄（对解不通过）。TB 用三准则 + 三审 + 双 auditor 防它；4.0 仍在按用户报告修 misspecification。
2. **测试可被绕过（reward hacking）**：改测试、mock、跳过、读 oracle/git history、读评测 artifact。规模证据：SWE-bench Pro v1.0 的 unearned pass 24%→73%。对策：容器分离、network-lock、pristine 重判、tamper-resistant verifier、adversarial exploit agent。
3. **环境漂移 / flaky**：依赖版本升级、浏览器升级、网络抖动、资源不足导致 timeout。SWE-bench Multimodal v2 与 TB 4.0 都在为此删任务/重建环境。**注意：这是"非受控漂移"，与 REBOUND 想测的"受控漂移"是同一物理现象的两面。**
4. **judge 偏置与版本漂移**：judge 偏好长答案/自信语气；judge 换版使历史结果不可比（τ-bench 2.0 明示）。
5. **部分分被当完成度**：partial 高但 binary 低（OSWorld 2.0：54.8% vs 20.6%），若只报 partial 会严重高估。
6. **小样本过度解读**：66 条任务上 1.5 分/条的粒度，却常被用来宣称"领先"。
7. **答案/任务泄漏**：公开解、基准被检索、agent 间串答案（公共 wiki）。
8. **饱和后仍被引用**：GAIA、BrowseComp、OSWorld-Verified、TB 2.1 均已饱和，继续用它们排名会得到"全都差不多"的假象。

### 2.4 选型建议（一句话版）

- 要**测终端长程能力** → Terminal-Bench 4.0（并强制报 cost）。
- 要**测仓库级修复** → SWE-bench Pro 私有集 + SWE-bench-Live（不要用 Verified 排名）。
- 要**测工具/跨 App** → Toolathlon（状态真实）+ τ-bench 2.0（协作与可靠性）。
- 要**测 OS 级长程** → OSWorld 2.0（binary 为主）。
- 要**测韧性/漂移/澄清/预算** → **现有基准均不足**，见 `docs/gaps-and-proposal.md`。

---

## 3. 四轴覆盖度矩阵（REBOUND 的直接论据）

四个轴取自 REBOUND 的设计目标。`✓` = 有原生支持并可被测量；`△` = 有相关机制但未作为指标；`✗` = 完全没有。

| Benchmark | ① 中途故障注入 + 恢复率 | ② 环境漂移（需重新观测） | ③ 预算化 `ask_user` 澄清 | ④ 效率预算作为指标 |
|---|---|---|---|---|
| Terminal-Bench 2.0/3.0/4.0 | ✗（环境假设稳定；flaky 被视为 bug） | △（3.0 有流式/动态环境，但非受控） | ✗（instruction 视为完备） | △（报 cost Pareto，非预算约束） |
| SWE-bench 全家 | ✗ | ✗（漂移=需修复的缺陷） | △（Pro 保留欠规格 issue，但不许问） | ✗ |
| Toolathlon | ✗ | △（真实状态会变，但非受控注入） | ✗ | ✗（报 turn 数，不加分/扣分） |
| GAIA | ✗ | △（互联网本身在漂移，非受控） | ✗ | ✗ |
| WebArena / VisualWebArena | ✗ | ✗（站点状态由 reset 固定） | ✗ | ✗ |
| OSWorld 1.0 / 2.0 | ✗ | △（2.0 的"动态环境/隐式状态"最接近，但不可控复现） | △（观察到"猜而不问"，但无预算机制与指标） | △（500 步预算，仅作截断） |
| AgentBench | ✗ | ✗ | ✗ | ✗ |
| τ-bench 2.0 | ✗ | △（双控导致状态变化，来自用户而非故障） | △（必须向用户索取信息，但无预算/质量指标） | ✗（无 token/调用预算） |
| BFCL V4 | ✗ | ✗ | △（irrelevance detection ≈ "该不该调用"） | ✗ |
| MLE-bench | ✗ | ✗ | ✗ | △（研究资源缩放，非指标） |
| AppWorld | ✗ | ✗ | ✗ | ✗ |
| Harness-Bench | △（harness 层 recovery 被提及） | △ | ✗ | ✓（共享预算 + usage 统计） |
| AM-Bench | ✗ | ✗ | △（观察 clarification 请求，无预算/质量） | ✗ |
| UnderSpecBench | ✗ | ✗ | △（区分 clarification/refusal/deferment） | ✗ |
| MCP-Injector | ✓（工具层，含持久性分类与 seed） | ✗ | ✗ | ✗ |
| **REBOUND-Bench（目标）** | **✓（5 类故障 × 3 种持久性 + recovery rate）** | **✓（受控 drift 事件 + 重观测率）** | **✓（预算 + 质量双评）** | **✓（显式预算 + efficiency score）** |

**读法**：没有任何一行同时覆盖 ①②③④；最接近组合是 `OSWorld 2.0 + MCP-Injector + AM-Bench + Harness-Bench`，但它们是四个独立系统、四套不兼容的接口与指标，**无法在同一个 episode 上同时生效**。这就是 REBOUND 的空间：不是发明新能力，而是**把四轴放进同一个可复现 episode，并让四轴的贡献可分离**。

---

## 4. 规模/成本/统计分辨率对照（为什么"小样本基准"必须报 CI）

| Benchmark | 任务数 | 每次评测的相对成本 | 单任务分辨率 | 统计建议 |
|---|---|---|---|---|
| Terminal-Bench 4.0 | 66 | 高（$1–$100/任务） | ~1.5 pt | 必须报 CI；差异 <3pt 视为噪声 |
| Terminal-Bench 2.0 | 89 | 高 | ~1.1 pt | 同上 |
| SWE-bench Verified | 500 | 中 | ~0.2 pt | 仍需 paired 比较 |
| SWE-bench Pro | 1,865（公 731） | 中高 | ~0.14 pt（公） | 公私分开报 |
| OSWorld 2.0 | 108 | 极高（1.6h 人类任务，318 调用） | ~0.9 pt | 必报 binary + partial 双指标 |
| Toolathlon | 108 | 中 | ~0.9 pt | 需多 trial |
| τ-bench 2.0 text-v1 | 150（50×3） | 中（用户模拟） | ~0.7 pt | **必须报 pass^k，k≥4** |
| GAIA | 466 | 低 | ~0.2 pt | 需多 trial/投票 |
| MLE-bench | 75 | 极高（GPU 小时级） | ~1.3 pt | 报分布而非均值 |
| AppWorld | 750 | 中 | ~0.13 pt | 分 normal/challenge 报 |
| **REBOUND-Bench（建议）** | **120–160（含对照/故障/漂移/欠规格变体）** | 中高 | ~0.7 pt | **必报 CI + pass^k + per-axis 分解** |

