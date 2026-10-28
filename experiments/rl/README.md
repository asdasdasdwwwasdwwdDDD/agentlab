# RL Rollout 数据集

- suite: `rebound`
- reward_mode: `shaped`（step_cost=0.01）
- episodes: 16
- dataset: `rollouts.jsonl`

| policy | episodes | success | mean reward | mean steps | mean calls |
|---|---|---|---|---|---|
| fragile | 4 | 50.0% | 0.465 | 3.5 | 1.0 |
| oracle | 4 | 100.0% | 0.96 | 4.0 | 1.5 |
| retry | 4 | 100.0% | 0.9425 | 5.75 | 2.5 |
| silent | 4 | 75.0% | 0.9025 | 3.5 | 1.5 |

> 轨迹由脚本化策略生成，仅用于验证环境/奖励接口与数据格式；训练真实策略请把 agent 换成模型 rollout。
