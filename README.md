# crypto-eval

**Model-agnostic crypto asset evaluation pipeline.** Score any token, DeFi protocol, or exchange product on a standardized A/B/C/D scale.

## Why?

Different LLMs give different evaluation scores for the same asset. **crypto-eval minimizes LLM dependency** by using deterministic rule-based scoring for 6 out of 7 dimensions, leaving only 1 dimension to LLM judgment.

**Worst case: LLM influences only 20% of the final score. Best case: 0%.**

## Architecture

```
Input (symbol / contract / name)
    ↓
Step 1: collect.py      → CoinGecko API (auto, cached 24h)
    ↓
Step 2: auto_score.py   → Rule engine (deterministic)
    ↓                     outputs needs_llm list
Step 3: LLM task        → Only for unscored dimensions
    ↓
Step 4: merge_score.py  → Auto + LLM → final grade
    ↓
Output: SYMBOL.json (grade, score, dimensions)
```

## 7 Dimensions

| Dimension | Weight | Auto? | Method |
|:---|:--:|:--:|:---|
| On-chain Data | 20% | ✅ | Market cap rank → score table |
| Exchange Coverage | 15% | ✅ | Exchange list matching |
| Asset Backing | 15% | Partial | Stablecoins/ON/BTC auto; rest → LLM |
| Age | 10% | ✅ | genesis_date → survival years |
| Tokenomics | 10% | ✅ | circulating / max supply ratio |
| Liquidity | 10% | ✅ | 24h volume / market cap ratio |
| Background | 20% | ❌ | Team/investors/audit → LLM only |

## Quick Start

```bash
# Install
git clone https://github.com/counterfactual5/crypto-eval.git
cd crypto-eval

# Full pipeline (BTC = 100% auto, no LLM needed)
python3 crypto_eval.py evaluate BTC

# New token (needs LLM for background)
python3 crypto_eval.py evaluate NIGHT
# → saves prompt to memory/evaluations/NIGHT_prompt.txt
# → fill in LLM response to NIGHT_llm.json
# → then merge:
python3 crypto_eval.py merge NIGHT --llm-file NIGHT_llm.json

# Contract address
python3 crypto_eval.py evaluate 0x6982508145454Ce325dDbE47a25d4ec3d2311933

# View results
python3 crypto_eval.py show NIGHT
python3 crypto_eval.py list
```

## Run Tests

```bash
python3 -m pytest tests/ -v
```

## Grade Scale

| Grade | Label | Score |
|:--:|:---|:--:|
| A | ★★★ High Trust | ≥ 80 |
| B | ★★☆ Solid Fundamentals | ≥ 60 |
| C | ⏳ Special (locked, etc.) | N/A |
| D | ⚠️ Caution | < 60 |

## Scoring Rules (Deterministic)

### On-chain Data
| Market Cap Rank | Score |
|:--|:--:|
| ≤ 10 | 95 |
| ≤ 20 | 88 |
| ≤ 50 | 80 |
| ≤ 100 | 72 |
| ≤ 200 | 60 |
| ≤ 500 | 45 |
| > 500 | 25 |

### Exchange Coverage
| Condition | Score |
|:--|:--:|
| Binance + OKX + Coinbase | 95 |
| Binance + ≥1 major | 80 |
| Binance only | 75 |
| ≥2 majors (no Binance) | 60 |
| 1 major only | 40 |
| DEX/small only | 20 |

### Asset Backing (Auto)
| Asset | Score |
|:--|:--:|
| USDC/USDT/USDS/DAI | 95 |
| ON tokens (*ON) | 92 |
| BTC/WBTC | 98 |
| ETH | 95 |

### Age (Auto)
| Survival | Score |
|:--|:--:|
| > 5 years | 90 |
| > 3 years | 80 |
| > 1 year | 65 |
| > 180 days | 45 |
| <= 180 days | 25 |

### Tokenomics (Auto)
| Circulating / Max | Score |
|:--|:--:|
| > 90% | 90 |
| > 70% | 75 |
| > 50% | 60 |
| > 20% | 40 |
| <= 20% | 20 |

### Liquidity (Auto)
| Volume / MCap | Score |
|:--|:--:|
| > 20% | 90 |
| > 5% | 70 |
| > 1% | 50 |
| <= 1% | 30 |


## Project Structure

```
crypto-eval/
├── crypto_eval.py              # Unified CLI
├── SKILL.md                    # Skill definition (OpenClaw)
├── scripts/
│   ├── collect.py              # Stage 1: CoinGecko data collection
│   ├── auto_score.py           # Stage 2: Deterministic scoring
│   ├── generate_llm_task.py   # Stage 3: LLM prompt generation
│   └── merge_score.py          # Stage 4: Score merging
├── references/
│   └── eval-dimensions.json    # Scoring rules & weights
└── tests/
    └── test_auto_score.py      # 21 tests (all deterministic)
```

## Integration

This is designed as a library, not just a CLI:

```python
from scripts.auto_score import auto_score
result = auto_score("BTC")
# result["auto_scores"]["onchain_data"] → {"score": 95, "auto": True}
```

### OpenClaw Integration
When used as an OpenClaw skill, Step 3 (LLM) is handled by the agent automatically. Other skills consume results from `memory/evaluations/SYMBOL.json`.

## License

MIT

## Contributing

Issues and PRs welcome. Key areas:
- Additional data sources (DeFiLlama TVL, Etherscan holders)
- More auto-score rules (e.g., GitHub stars, audit status)
- Multi-language support
- Integration with more exchanges
