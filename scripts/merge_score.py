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
    llm_summary = llm_raw.get("summary", "") if llm_path and os.path.exists(llm_path) else ""
    llm_risk = llm_raw.get("risk", "") if llm_path and os.path.exists(llm_path) else ""
    llm_opp = llm_raw.get("opportunity", "") if llm_path and os.path.exists(llm_path) else ""
    llm_sources = llm_raw.get("sources", []) if llm_path and os.path.exists(llm_path) else []

    result = {
        "symbol": symbol.upper(),
        "name": auto.get("name", ""),
        "evaluated_at": datetime.now(CST).isoformat(),
        "grade": grade,
        "grade_label": grade_label,
        "score": round(total, 1),
        "dimensions": final_dims,
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
