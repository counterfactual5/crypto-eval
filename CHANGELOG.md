# Changelog

## [0.5.0] — 2026-06-03

### Added
- Batch merge with `--quiet` and `--llm-file` flags
- LRU caching for collection/score pipelines

### Fixed
- KeyboardInterrupt no longer swallowed during evaluation

## [0.4.0] — 2026-06-02

### Added
- CI coverage (GitHub Actions)
- Confidence bar in output
- Batch evaluation mode

### Fixed
- C grade threshold corrected

## [0.3.0] — 2026-06-02

### Added
- Age dimension (genesis_date → survival years, 10%)
- Tokenomics dimension (supply ratio, 10%)
- Liquidity dimension (24h vol/cap ratio, 10%)

## [0.2.0] — 2026-06-01

### Changed
- Removed APY dimension
- Dimensions: 5→4, weights 25% each
- LLM contribution capped at 25%

## [0.1.0] — 2026-05-30

### Added
- 7-dimension evaluation framework
- 6/7 automatic scoring (deterministic)
- Only "Background" dimension requires LLM (20% weight)
- CoinGecko API integration with 24h cache
- CLI: evaluate, merge, show
- A/B/C/D grading scale

[0.5.0]: https://github.com/counterfactual5/crypto-eval/releases/tag/v0.5.0
[0.4.0]: https://github.com/counterfactual5/crypto-eval/releases/tag/v0.4.0
[0.3.0]: https://github.com/counterfactual5/crypto-eval/releases/tag/v0.3.0
[0.2.0]: https://github.com/counterfactual5/crypto-eval/releases/tag/v0.2.0
[0.1.0]: https://github.com/counterfactual5/crypto-eval/releases/tag/v0.1.0
