# Contributing to crypto-eval

## Setup

```bash
git clone https://github.com/counterfactual5/crypto-eval.git
cd crypto-eval
uv pip install -e ".[dev]"
```

## Running Tests

```bash
uv run pytest tests/ -v
```

21 tests covering auto_score dimensions, grade calculation, merge logic, and batch evaluation.

## Project Structure

```
crypto-eval/
├── crypto_eval.py              # Main entry point (CLI)
├── scripts/
│   ├── collect.py              # CoinGecko data collection
│   ├── auto_score.py           # Deterministic rule engine
│   ├── generate_llm_task.py    # LLM prompt generation
│   └── merge_score.py          # Auto + LLM → final grade
├── references/
│   └── eval-dimensions.json    # Dimension definitions + weights
└── tests/
    └── test_auto_score.py      # Unit tests for scoring
```

## Code Style

- Python 3.10+ compatible
- Public functions have docstrings
- Ruff configured for linting: `uv run ruff check .`

## How It Works

The pipeline minimizes LLM dependency:
1. `collect.py` — fetches CoinGecko data (cached 24h)
2. `auto_score.py` — deterministic rule engine scores 6/7 dimensions
3. `generate_llm_task.py` — creates prompt for unscored dimensions
4. `merge_score.py` — merges auto + LLM scores into final A/B/C/D grade

## Adding a New Dimension

1. Define in `references/eval-dimensions.json`
2. Add scoring logic in `scripts/auto_score.py`
3. Update weight distribution
4. Add tests for edge cases

## Pull Requests

1. Fork → feature branch → changes + tests → PR to `main`
