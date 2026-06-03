"""测试自动评分逻辑 — 不需要网络"""

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))

from importlib import import_module  # noqa: E402

auto_score_mod = import_module("auto_score")

# 加载评分规则
DIM_PATH = os.path.join(SKILL_DIR, "references", "eval-dimensions.json")
with open(DIM_PATH) as f:
    DIMS = json.load(f)
SCORING = DIMS["scoring_rules"]
MAJOR_EX = SCORING["exchange_coverage"].get("major_exchanges", [])


# ===== onchain_data =====
def test_onchain_top10():
    score, note = auto_score_mod.auto_score_onchain({"market_cap_rank": 5}, SCORING["onchain_data"]["rules"])
    assert score == 95


def test_onchain_top100():
    score, note = auto_score_mod.auto_score_onchain({"market_cap_rank": 94}, SCORING["onchain_data"]["rules"])
    assert score == 72


def test_onchain_unranked():
    score, note = auto_score_mod.auto_score_onchain({"market_cap_rank": 800}, SCORING["onchain_data"]["rules"])
    assert score == 25


def test_onchain_by_marketcap():
    score, note = auto_score_mod.auto_score_onchain(
        {"market_data": {"market_cap_usd": 5e9}}, SCORING["onchain_data"]["rules"]
    )
    assert score == 75


# ===== exchange_coverage =====
def test_exchange_three_majors():
    score, note = auto_score_mod.auto_score_exchange(
        {"exchanges": ["Binance", "OKX", "Coinbase", "Kraken"]}, SCORING["exchange_coverage"]["rules"], MAJOR_EX
    )
    assert score == 95


def test_exchange_binance_only():
    score, note = auto_score_mod.auto_score_exchange(
        {"exchanges": ["Binance", "SomeDEX"]}, SCORING["exchange_coverage"]["rules"], MAJOR_EX
    )
    assert score == 75


def test_exchange_no_data():
    score, note = auto_score_mod.auto_score_exchange({}, SCORING["exchange_coverage"]["rules"], MAJOR_EX)
    assert score is None  # needs LLM


# ===== asset_backing =====
def test_asset_stablecoin():
    score, note = auto_score_mod.auto_score_asset("USDC", {}, SCORING["asset_backing"]["auto_rules"])
    assert score == 95


def test_asset_on_token():
    score, note = auto_score_mod.auto_score_asset("SLVON", {}, SCORING["asset_backing"]["auto_rules"])
    assert score == 92


def test_asset_btc():
    score, note = auto_score_mod.auto_score_asset("BTC", {}, SCORING["asset_backing"]["auto_rules"])
    assert score == 98


def test_asset_unknown():
    score, note = auto_score_mod.auto_score_asset("RANDOCOIN", {}, SCORING["asset_backing"]["auto_rules"])
    assert score is None  # needs LLM


# ===== 确定性测试 =====
def test_merge_deterministic():
    """同输入永远出同结果"""
    import tempfile

    merge_mod = import_module("merge_score")
    auto_data = {
        "symbol": "TEST",
        "name": "Test",
        "auto_scores": {
            "onchain_data": {"score": 80, "note": "test", "auto": True},
            "exchange_coverage": {"score": 75, "note": "test", "auto": True},
            "asset_backing": {"score": 95, "note": "test", "auto": True},
            "background": {"score": 80, "note": "test", "auto": True},
        },
        "auto_partial_score": 82.5,
        "auto_partial_weight": 1.0,
        "remaining_llm_weight": 0.0,
        "needs_llm": [],
        "data_summary": {},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(auto_data, f)
        auto_path = f.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        out_path = f.name

    r1 = merge_mod.merge("TEST", auto_path=auto_path, output_path=out_path)
    r2 = merge_mod.merge("TEST", auto_path=auto_path, output_path=out_path)
    assert r1["score"] == r2["score"]
    assert abs(r1["score"] - 82.5) < 0.1
    assert r1["grade"] == "A"
    os.unlink(auto_path)
    os.unlink(out_path)
