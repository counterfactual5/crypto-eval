#!/usr/bin/env python3
"""
crypto-eval Stage 4: 合并自动评分 + LLM 评分 → 最终评级
输入: auto_score 结果 + LLM JSON 输出
输出: 最终评级 JSON
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
WORKSPACE = os.path.dirname(os.path.dirname(SKILL_DIR))
EVAL_DIR = os.path.join(WORKSPACE, "memory", "evaluations")
DIM_PATH = os.path.join(SKILL_DIR, "references", "eval-dimensions.json")

CST = timezone(timedelta(hours=8))


def detect_red_flags(auto_scores, raw_data):
    """Return list of red-flag dicts based on dangerous dimension combos."""
    flags = []

    # Helpers
    def score(dim):
        return (auto_scores.get(dim) or {}).get("score")

    md = raw_data.get("market_data") or {}
    gh = raw_data.get("github") or {}

    # 1. 新币 + 无主流交易所
    age_score = score("age")
    ex_score = score("exchange_coverage")
    if age_score is not None and age_score <= 45 and ex_score is not None and ex_score < 40:
        flags.append(
            {"level": "high", "rule": "new_coin_no_exchange", "msg": "新币（<180天）且未上主流交易所 — 极高风险"}
        )

    # 2. 高稀释 + 高市值
    tok_score = score("tokenomics")
    rank = raw_data.get("market_cap_rank")
    if tok_score is not None and tok_score <= 40 and rank is not None and rank <= 100:
        flags.append(
            {"level": "high", "rule": "high_dilution_top100", "msg": "Top100 市值但流通量极低 — 大量待解锁抛压"}
        )

    # 3. 低流动性 + 小市值
    liq_score = score("liquidity")
    mcap = md.get("market_cap_usd")
    if liq_score is not None and liq_score <= 30 and mcap is not None and mcap < 1e8:
        flags.append(
            {"level": "medium", "rule": "low_liquidity_small_cap", "msg": "小市值且流动性差 — 进出困难，易被套"}
        )

    # 4. GitHub 停滞
    last_commit = gh.get("last_commit_at")
    if last_commit:
        from datetime import datetime, timezone

        try:
            commit_dt = datetime.fromisoformat(last_commit.replace("Z", "+00:00"))
            days_ago = (datetime.now(timezone.utc) - commit_dt).days
            if days_ago > 365:
                flags.append(
                    {
                        "level": "medium",
                        "rule": "stale_github",
                        "msg": f"GitHub 最后提交在 {days_ago} 天前 — 开发可能停滞",
                    }
                )
        except (ValueError, TypeError):
            pass

    # 5. 无 GitHub 且背景需 LLM
    dev_score = score("dev_activity")
    if dev_score is None:
        flags.append({"level": "medium", "rule": "no_github", "msg": "无公开 GitHub 仓库 — 无法验证开发活跃度"})

    return flags


def merge(symbol, auto_path=None, llm_path=None, output_path=None):
    # 加载维度定义
    with open(DIM_PATH) as f:
        dims = json.load(f)
    weights = {d["id"]: d["weight"] for d in dims["dimensions"]}
    thresholds = dims["grade_thresholds"]

    # 加载自动评分
    auto_f = auto_path or os.path.join(EVAL_DIR, f"{symbol.upper()}_auto.json")
    with open(auto_f) as f:
        auto = json.load(f)

    # Schema version check
    current_version = dims.get("version", 1)
    auto_version = auto.get("schema_version", 1)
    if auto_version != current_version:
        print(
            f"⚠️  schema 版本不匹配: 评估使用 v{auto_version}, 当前规则 v{current_version}。"
            f"建议重新运行 evaluate 以获取最新评分。",
            file=sys.stderr,
        )

    # 加载原始采集数据（用于 red flags）
    raw_data = {}
    raw_path = os.path.join(EVAL_DIR, f"{symbol.upper()}_raw.json")
    if os.path.exists(raw_path):
        with open(raw_path) as f:
            raw_data = json.load(f)

    # 加载 LLM 评分（可选）
    llm_scores = {}
    if llm_path and os.path.exists(llm_path):
        with open(llm_path) as f:
            llm_raw = json.load(f)
            llm_scores = llm_raw.get("dimensions", {})

    # 合并
    final_dims = {}
    for dim_id in weights:
        auto_info = auto["auto_scores"].get(dim_id, {})
        if auto_info.get("auto") and auto_info.get("score") is not None:
            final_dims[dim_id] = {"score": auto_info["score"], "note": auto_info["note"], "source": "auto"}
        elif dim_id in llm_scores:
            final_dims[dim_id] = {
                "score": llm_scores[dim_id].get("score", 50),
                "note": llm_scores[dim_id].get("note", ""),
                "source": "llm",
            }
        else:
            final_dims[dim_id] = {"score": 50, "note": "数据不足", "source": "default"}

    # 加权总分
    total = sum(final_dims[d]["score"] * weights[d] for d in weights)

    # 评级
    grade = "D"
    grade_label = thresholds["D"]["label"]
    for g in ["A", "B", "C"]:
        if total >= thresholds[g]["min_score"]:
            grade = g
            grade_label = thresholds[g]["label"]
            break

    # LLM 补充字段
    has_llm = llm_path and os.path.exists(llm_path)
    llm_summary = llm_raw.get("summary", "") if has_llm else ""
    llm_risk = llm_raw.get("risk", "") if has_llm else ""
    llm_opp = llm_raw.get("opportunity", "") if has_llm else ""
    llm_sources = llm_raw.get("sources", []) if has_llm else []

    # Red flags
    red_flags = detect_red_flags(auto.get("auto_scores", {}), raw_data)

    result = {
        "symbol": symbol.upper(),
        "name": auto.get("name", ""),
        "evaluated_at": datetime.now(CST).isoformat(),
        "grade": grade,
        "grade_label": grade_label,
        "score": round(total, 1),
        "dimensions": final_dims,
        "red_flags": red_flags,
        "summary": llm_summary,
        "risk": llm_risk,
        "opportunity": llm_opp,
        "sources": llm_sources,
        "scoring_method": {
            "auto_weight_pct": round(auto.get("auto_partial_weight", 0) * 100),
            "llm_weight_pct": round(auto.get("remaining_llm_weight", 0) * 100),
        },
    }

    # 写入
    out_path = output_path or os.path.join(EVAL_DIR, f"{symbol.upper()}.json")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: merge_score.py <symbol> [--auto PATH] [--llm PATH] [--output PATH]")
        sys.exit(1)

    symbol = sys.argv[1]
    auto_path = llm_path = output_path = None

    for flag in ["--auto", "--llm", "--output"]:
        if flag in sys.argv:
            idx = sys.argv.index(flag)
            val = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
            if flag == "--auto":
                auto_path = val
            elif flag == "--llm":
                llm_path = val
            elif flag == "--output":
                output_path = val

    result = merge(symbol, auto_path, llm_path, output_path)
    print(json.dumps(result, indent=2, ensure_ascii=False))
