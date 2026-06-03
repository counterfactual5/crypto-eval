---
name: crypto-eval
description: "通用加密资产评估流水线。输入 symbol/合约地址/项目名，自动采集+自动评分+LLM补充，输出 A/B/C/D 评级。7维中6维全自动，仅1维需LLM。"
triggers:
  - 评估
  - evaluate
  - 评级
  - 这个币怎么样
  - 这个项目靠谱吗
  - 帮我评估
  - 调研一下
---

# Crypto Eval — 加密资产评估流水线

## 角色定位

资深加密资产分析师，数据驱动，拒绝 FOMO。输出面向需要快速决策的交易者。

## 适用场景

**何时用：** 评估任意加密资产（代币、DeFi 协议、交易所理财产品）
**何不用：** 纯技术问题（合约审计）；只查价格不问质量

## 设计原则：最小化 LLM 依赖

8 个评估维度中，**7 个全自动**（规则引擎），**最多 1 个需 LLM**：

| 维度 | 权重 | 自动? | 方法 |
|:---|:--:|:--:|:---|
| 链上数据 | 15% | ✅ 全自动 | CoinGecko 市值排名 → 分数 |
| 交易所覆盖 | 10% | ✅ 全自动 | 交易所列表匹配 → 分数 |
| 资产背书 | 15% | 半自动 | 稳定币/ON代币/BTC/ETH 自动，其余需 LLM |
| 存续时间 | 10% | ✅ 全自动 | genesis_date → 穿越牛熊年数 |
| 稀释风险 | 10% | ✅ 全自动 | 流通量/总供应量比 |
| 流动性 | 10% | ✅ 全自动 | 24h成交量/市值比 |
| 开发者活跃度 | 10% | ✅ 全自动 | GitHub stars + 最后提交时间 |
| 项目背景 | 20% | ❌ LLM | 团队/投资方/审计（无法自动化） |

**最坏情况**：LLM 只评 0-2 个维度（background + asset_backing 边缘），占分最多 35%。大部分代币评估 LLM 只占 20%。

## 执行流程

### Step 1: 信息采集（全自动）

```bash
python3 {仓库根}/skills/crypto-eval/scripts/collect.py "INPUT" --json-output memory/evaluations/SYMBOL_raw.json
```

INPUT 支持：symbol / 合约地址（0x...）/ 项目名

### Step 2: 自动评分（全自动，不调 LLM）

```bash
python3 {仓库根}/skills/crypto-eval/scripts/auto_score.py SYMBOL --output memory/evaluations/SYMBOL_auto.json
```

输出每个维度的自动分数和 `needs_llm` 列表。

### Step 3: LLM 补充（仅在 needs_llm 非空时）

```bash
python3 {仓库根}/skills/crypto-eval/scripts/generate_llm_task.py SYMBOL --output memory/evaluations/SYMBOL_llm_task.json
```

生成的 prompt 只包含 **未自动评分的维度**。将 prompt 交给 LLM，LLM 输出 JSON。

如果 `needs_llm` 为空（如 BTC/USDC 等知名币种），**跳过此步**。

如果数据不完整，用 web_search 补充后重跑 Step 2。

### Step 4: 合并评分 + 输出最终评级（全自动）

```bash
python3 {仓库根}/skills/crypto-eval/scripts/merge_score.py SYMBOL --llm memory/evaluations/SYMBOL_llm.json --output memory/evaluations/SYMBOL.json
```

### Step 5: 向用户展示

精简格式（不超过 5 行）：
```
SYMBOL — ★★☆ 有基本面（72分）
链上#94 | 交易所:Bitget | 资产:原生代币
亮点：IOG团队(Cardano)开发
风险：仅Bitget上线，高APY为推广补贴
```

### Step 6: 同步消费者（如有）

更新 `memory/earn-quality-tiers.json`。

## 评分规则速查

### 链上数据（全自动）
| 条件 | 分数 |
|:---|:--:|
| 市值 Top 10 | 95 |
| Top 20 | 88 |
| Top 50 | 80 |
| Top 100 | 72 |
| Top 200 | 60 |
| Top 500 | 45 |
| >500/无排名 | 25 |

### 交易所覆盖（全自动）
| 条件 | 分数 |
|:---|:--:|
| Binance+OKX+Coinbase | 95 |
| Binance + ≥1家主流 | 80 |
| 仅 Binance | 75 |
| ≥2家主流（无Binance） | 60 |
| 仅1家 | 40 |
| 仅DEX/小所 | 20 |

### 资产背书（半自动）
| 条件 | 分数 |
|:---|:--:|
| USDC/USDT/USDS/DAI | 95 |
| ON 代币（*ON） | 92 |
| BTC/WBTC | 98 |
| ETH | 95 |
| 其余 → 需 LLM 判断 | ? |

### 收益来源（半自动）
| 条件 | 分数 |
|:---|:--:|
| APY ≤5% | 80 |
| APY 5~15% | 70 |
| APY >30%（非ON）| 25 |
| ON 代币 APY>15% | 85 |

### 项目背景（仅 LLM）
| 条件 | 分数范围 |
|:---|:--:|
| 顶级VC（a16z/Paradigm） | ≥75 |
| 无已知投资方 | ≤50 |
| 匿名团队 | ≤30 |

## 被其他 Skill 调用

```bash
# 检查是否已有评估
cat memory/evaluations/SYMBOL.json | jq '.grade'

# 批量获取
ls memory/evaluations/*.json

# 仅自动评分（不调LLM，速度快）
python3 skills/crypto-eval/scripts/auto_score.py SYMBOL
```

评估有效期 7 天。

## 常见借口与反驳

| 借口 | 现实 |
|------|------|
| 信息不够跳过评估 | 自动评分不需要完整数据，缺的标 N/A |
| 每次都要调 LLM 太慢 | BTC/USDC 等知名币种全自动，0 次 LLM 调用 |
| 不同模型分数不一样 | 55% 的分数是确定性的，LLM 只影响最多 45% |
| 我直接凭印象评 | 禁止，必须跑流水线 |

## 危险信号

- 跳过 Step 1/2 直接 LLM 评 → 违反最小化 LLM 原则
- LLM 输出覆盖了已自动评分的维度 → merge 会保留 auto 分数
- 所有维度都标 needs_llm → 检查 Step 1 是否采集成功

## 验证

- [ ] Step 1 采集数据已存 `memory/evaluations/SYMBOL_raw.json`
- [ ] Step 2 自动评分已存 `memory/evaluations/SYMBOL_auto.json`
- [ ] needs_llm 列表 ≤ 2 个维度
- [ ] 如有 LLM 任务，LLM 输出已存 `memory/evaluations/SYMBOL_llm.json`
- [ ] Step 4 最终结果已存 `memory/evaluations/SYMBOL.json`
- [ ] score = Σ(维度分 × 权重)，grade 与 score 对应

## 关键路径

- 采集：`skills/crypto-eval/scripts/collect.py`
- 自动评分：`skills/crypto-eval/scripts/auto_score.py`
- LLM 任务生成：`skills/crypto-eval/scripts/generate_llm_task.py`
- 合并：`skills/crypto-eval/scripts/merge_score.py`
- 评分规则：`skills/crypto-eval/references/eval-dimensions.json`
- 评估记录：`memory/evaluations/SYMBOL.json`
- Bitget 理财评级：`memory/earn-quality-tiers.json`
