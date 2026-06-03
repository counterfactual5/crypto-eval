#!/usr/bin/env python3
"""
crypto-eval Stage 3: 生成 LLM prompt（只问需要 LLM 判断的维度）
读取 auto_score 的输出，只生成未自动评分的维度的问题
"""
import json, sys, os, textwrap

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
WORKSPACE = os.path.dirname(os.path.dirname(SKILL_DIR))
EVAL_DIR = os.path.join(WORKSPACE, "memory", "evaluations")
DIM_PATH = os.path.join(SKILL_DIR, "references", "eval-dimensions.json")

def generate_llm_prompt(symbol, auto_result_path=None):
    # 加载自动评分结果
    if auto_result_path and os.path.exists(auto_result_path):
        with open(auto_result_path) as f:
            auto = json.load(f)
    else:
        auto_path = os.path.join(EVAL_DIR, f"{symbol.upper()}_auto.json")
        if os.path.exists(auto_path):
            with open(auto_path) as f:
                auto = json.load(f)
        else:
            return {"error": "No auto_score result found. Run auto_score.py first."}
    
    needs_llm = auto.get("needs_llm", [])
    if not needs_llm:
        # 所有维度都自动评好了，不需要 LLM
        return {
            "needs_llm": False,
            "message": "All dimensions scored automatically. No LLM needed.",
            "auto_result": auto
        }
    
    # 加载采集数据作为上下文
    raw_path = os.path.join(EVAL_DIR, f"{symbol.upper()}_raw.json")
    raw_data = {}
    if os.path.exists(raw_path):
        with open(raw_path) as f:
            raw_data = json.load(f)
    
    # 加载维度定义
    with open(DIM_PATH) as f:
        dims = json.load(f)
    
    weights = {d["id"]: d["weight"] for d in dims["dimensions"]}
    
    # 构造 LLM 任务
    auto_summary = []
    for dim_id, info in auto["auto_scores"].items():
        if info["auto"] and info["score"] is not None:
            auto_summary.append(f"  {dim_id}: {info['score']}分（已自动评分） — {info['note']}")
    auto_text = "\n".join(auto_summary)
    
    llm_tasks = []
    for task in needs_llm:
        dim_id = task["dimension"]
        reason = task.get("reason", "")
        hint = task.get("hint", "")
        weight_pct = int(weights.get(dim_id, 0) * 100)
        llm_tasks.append(f"### 维度: {dim_id}（权重 {weight_pct}%）\n任务: {reason}\n{('补充信息: ' + hint) if hint else ''}")
    tasks_text = "\n\n".join(llm_tasks)
    
    context = json.dumps({
        "symbol": symbol,
        "description": (raw_data.get("description") or "")[:300],
        "categories": raw_data.get("categories", [])[:5],
        "links": raw_data.get("links", {}),
        "data_summary": auto.get("data_summary", {})
    }, indent=2, ensure_ascii=False)
    
    prompt = textwrap.dedent(f"""\
    你是一名加密资产分析师。请完成以下 **尚未自动评分** 的维度。

    ## 评估对象
    {symbol}

    ## 已自动评分的维度（你不需要重评）
    {auto_text}

    ## 自动评分总分: {auto.get('auto_partial_score', 0)}（权重覆盖 {auto.get('auto_partial_weight', 0)}%）

    ## 需要你评分的维度

    {tasks_text}

    ## 项目上下文
    <context>
    {context}
    </context>

    ## 输出要求
    只输出 JSON，不要其他文字：

    ```json
    {{
      "dimensions": {{
    """)
    
    # 为每个需要 LLM 的维度构造模板
    dim_templates = []
    for task in needs_llm:
        dim_id = task["dimension"]
        dim_templates.append(f'        "{dim_id}": {{"score": 0, "note": "（一句话，引用具体事实）"}}')
    
    prompt += ",\n".join(dim_templates)
    prompt += textwrap.dedent("""
      },
      "summary": "（一句话结论）",
      "risk": "（主要风险）",
      "opportunity": "（主要机会）",
      "sources": ["（信息来源）"]
    }
    ```

    ## 约束
    - note 必须引用具体事实
    - sources 必须列出你用的信息来源
    - 如果数据不足以判断，score 填 50，note 写"数据不足"
    """)
    
    return {
        "needs_llm": True,
        "llm_dimensions": [t["dimension"] for t in needs_llm],
        "prompt": prompt,
        "auto_result": auto
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: generate_llm_task.py <symbol> [--auto PATH] [--output PATH]")
        sys.exit(1)
    
    symbol = sys.argv[1]
    auto_path = None
    output_path = None
    
    if "--auto" in sys.argv:
        idx = sys.argv.index("--auto")
        auto_path = sys.argv[idx + 1]
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        output_path = sys.argv[idx + 1]
    
    result = generate_llm_prompt(symbol, auto_path)
    
    if isinstance(result, dict) and "error" in result:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(1)
    
    out = json.dumps(result, indent=2, ensure_ascii=False)
    
    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w") as f:
            f.write(out)
    
    # 默认只打印 prompt 部分
    if result.get("needs_llm"):
        print(result["prompt"])
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
