#!/usr/bin/env python3
"""
crypto-eval Stage 2: 自动评分（不调 LLM）
读取采集数据 + eval-dimensions.json 的 auto_rules
输出: JSON，其中能自动评的维度已打好分，需要 LLM 的标 "needs_llm": true
"""

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
WORKSPACE = os.path.dirname(os.path.dirname(SKILL_DIR))
EVAL_DIR = os.path.join(WORKSPACE, "memory", "evaluations")
DIM_PATH = os.path.join(SKILL_DIR, "references", "eval-dimensions.json")


def load_dimensions():
    with open(DIM_PATH) as f:
        return json.load(f)


def auto_score_onchain(data, rules):
    rank = data.get("market_cap_rank")
    mc = (data.get("market_data") or {}).get("market_cap_usd")

    if rank is not None:
        for rule in rules:
            cond = rule["condition"]
            if cond.startswith("rank <="):
                threshold = int(cond.split("<=")[1].strip())
                if rank <= threshold:
                    return rule["score"], f"市值排名 #{rank}"
            elif "unranked" in cond:
                continue
        return 25, f"市值排名 #{rank}（>500）"

    # 无排名，用市值估算
    if mc:
        if mc > 1e10:
            return 90, f"市值 ${mc / 1e9:.1f}B（估算Top10）"
        if mc > 1e9:
            return 75, f"市值 ${mc / 1e9:.1f}B（估算Top50）"
        if mc > 1e8:
            return 55, f"市值 ${mc / 1e6:.0f}M（估算Top200）"
        return 30, f"市值 ${mc / 1e6:.0f}M（小币）"

    return None, "数据不足"


def auto_score_exchange(data, rules, major_exchanges):
    listed = set(data.get("exchanges", []))
    majors = set(major_exchanges)
    overlap = listed & majors

    has_binance = "Binance" in overlap
    has_okx = "OKX" in overlap
    has_coinbase = "Coinbase" in overlap

    if has_binance and has_okx and has_coinbase:
        return 95, "Binance+OKX+Coinbase 都上"
    if has_binance and len(overlap) >= 2:
        return 80, f"Binance + {len(overlap) - 1}家主流所"
    if has_binance:
        return 75, "Binance 已上"
    if len(overlap) >= 2:
        return 60, f"{len(overlap)}家主流所（无Binance）"
    if len(overlap) == 1:
        return 40, f"仅 {list(overlap)[0]}"
    if listed:
        return 20, f"仅 {len(listed)}家小所/DEX"
    return None, "交易所数据缺失"  # needs LLM


def auto_score_asset(symbol, data, rules):
    symbol_upper = symbol.upper()

    for rule in rules:
        cond = rule["condition"]
        if cond.startswith("symbol in ["):
            coins_str = cond.split("[")[1].split("]")[0]
            coins = [c.strip() for c in coins_str.split(",")]
            if symbol_upper in coins:
                return rule["score"], rule["note"]
        elif "ends with ON" in cond:
            if symbol_upper.endswith("ON"):
                return rule["score"], rule["note"]
        elif "symbol = " in cond:
            target = cond.split("=")[1].strip().split()[0]
            if symbol_upper == target:
                return rule["score"], rule["note"]
        elif "category contains" in cond:
            cat_part = cond.split("'")[1]
            categories = data.get("categories", [])
            if any(cat_part.lower() in (c or "").lower() for c in categories):
                return rule["score"], rule["note"]

    return None, None  # needs LLM


def auto_score(input_symbol, data_path=None):
    symbol = input_symbol.upper()

    # 加载采集数据
    raw_path = data_path or os.path.join(EVAL_DIR, f"{symbol}_raw.json")
    if os.path.exists(raw_path):
        with open(raw_path) as f:
            data = json.load(f)
    else:
        data = {}

    dims = load_dimensions()
    scoring = dims["scoring_rules"]

    result = {
        "symbol": symbol,
        "name": data.get("name", ""),
        "auto_scores": {},
        "needs_llm": [],
        "data_summary": {
            "market_cap_rank": data.get("market_cap_rank"),
            "exchanges": data.get("exchanges", [])[:10],
            "categories": data.get("categories", [])[:5],
            "platforms": data.get("platforms", []),
        },
    }

    # onchain_data
    score, note = auto_score_onchain(data, scoring["onchain_data"]["rules"])
    result["auto_scores"]["onchain_data"] = {"score": score, "note": note, "auto": score is not None}
    if score is None:
        result["needs_llm"].append({"dimension": "onchain_data", "reason": "无市值排名数据"})

    # exchange_coverage
    major_ex = scoring["exchange_coverage"].get("major_exchanges", [])
    score, note = auto_score_exchange(data, scoring["exchange_coverage"]["rules"], major_ex)
    result["auto_scores"]["exchange_coverage"] = {"score": score, "note": note, "auto": score is not None}
    if score is None:
        result["needs_llm"].append({"dimension": "exchange_coverage", "reason": "交易所数据缺失，需 web_search 补充"})

    # asset_backing
    score, note = auto_score_asset(symbol, data, scoring["asset_backing"]["auto_rules"])
    result["auto_scores"]["asset_backing"] = {"score": score, "note": note, "auto": score is not None}
    if score is None:
        result["needs_llm"].append({"dimension": "asset_backing", "reason": scoring["asset_backing"]["llm_task"]})

    # background (始终需要 LLM)
    result["auto_scores"]["background"] = {"score": None, "note": None, "auto": False}
    result["needs_llm"].append({"dimension": "background", "reason": scoring["background"]["llm_task"]})

    # 计算已有自动分的加权总分
    # 从 eval-dimensions.json 统一读取权重
    weights = {d["id"]: d["weight"] for d in dims["dimensions"]}
    total_score = 0
    total_weight = 0
    for dim_id, info in result["auto_scores"].items():
        if info["score"] is not None:
            total_score += info["score"] * weights[dim_id]
            total_weight += weights[dim_id]

    result["auto_partial_score"] = round(total_score, 1) if total_weight > 0 else 0
    result["auto_partial_weight"] = round(total_weight, 2)
    result["remaining_llm_weight"] = round(1 - total_weight, 2)

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: auto_score.py <symbol> [--data PATH] [--output PATH]")
        sys.exit(1)

    symbol = sys.argv[1]
    data_path = None
    output_path = None

    if "--data" in sys.argv:
        idx = sys.argv.index("--data")
        data_path = sys.argv[idx + 1]
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        output_path = sys.argv[idx + 1]

    result = auto_score(symbol, data_path)
    out = json.dumps(result, indent=2, ensure_ascii=False)

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w") as f:
            f.write(out)

    print(out)
