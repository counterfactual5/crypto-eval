#!/usr/bin/env python3
"""
crypto-eval: 统一 CLI 入口
用法:
  python3 crypto_eval.py evaluate NIGHT              # 完整流水线
  python3 crypto_eval.py evaluate 0x... --chain eth   # 合约地址
  python3 crypto_eval.py auto NIGHT                   # 只跑自动评分
  python3 crypto_eval.py merge NIGHT --llm llm.json   # 合并 LLM 结果
  python3 crypto_eval.py show NIGHT                   # 显示已有评估
  python3 crypto_eval.py list                         # 列出所有评估
  python3 crypto_eval.py test                         # 跑测试
"""
import json, sys, os, argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EVAL_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "memory", "evaluations"))
SCRIPTS_DIR = os.path.join(SCRIPT_DIR, "scripts")

def ensure_dirs():
    os.makedirs(EVAL_DIR, exist_ok=True)

def run_cmd(cmd):
    import subprocess
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    return result.stdout, result.stderr, result.returncode

def cmd_evaluate(args):
    """完整流水线: collect → auto_score → (可选)LLM → merge"""
    ensure_dirs()
    symbol = args.symbol.upper()
    
    # Step 1: 采集
    raw_path = os.path.join(EVAL_DIR, f"{symbol}_raw.json")
    print(f"📡 Step 1: 采集 {symbol} 数据...")
    stdout, stderr, rc = run_cmd(f"python3 {SCRIPTS_DIR}/collect.py '{args.symbol}' --json-output '{raw_path}'")
    if rc != 0 and not os.path.exists(raw_path):
        print(f"❌ 采集失败: {stderr}")
        return 1
    
    # Step 2: 自动评分
    auto_path = os.path.join(EVAL_DIR, f"{symbol}_auto.json")
    print(f"⚙️  Step 2: 自动评分...")
    stdout, stderr, rc = run_cmd(f"python3 {SCRIPTS_DIR}/auto_score.py '{symbol}' --output '{auto_path}'")
    if rc != 0:
        print(f"❌ 自动评分失败: {stderr}")
        return 1
    
    result = json.loads(stdout)
    needs_llm = result.get("needs_llm", [])
    auto_pct = result.get("auto_partial_weight", 0) * 100
    
    print(f"   自动评分覆盖: {auto_pct:.0f}%")
    for dim_id, info in result["auto_scores"].items():
        if info.get("score") is not None:
            print(f"   ✅ {dim_id}: {info['score']}分 — {info['note']}")
    
    if needs_llm:
        dims_str = ", ".join(d["dimension"] for d in needs_llm)
        print(f"\n🤖 Step 3: 需要 LLM 评估: {dims_str}")
        llm_task_path = os.path.join(EVAL_DIR, f"{symbol}_llm_task.json")
        stdout, stderr, rc = run_cmd(f"python3 {SCRIPTS_DIR}/generate_llm_task.py '{symbol}' --output '{llm_task_path}'")
        
        if args.llm_file and os.path.exists(args.llm_file):
            # 有 LLM 结果文件，直接合并
            print(f"📋 使用 LLM 结果: {args.llm_file}")
            llm_path = args.llm_file
        else:
            # 保存 prompt，等用户/LLM 处理
            prompt_path = os.path.join(EVAL_DIR, f"{symbol}_prompt.txt")
            if os.path.exists(llm_task_path):
                with open(llm_task_path) as f:
                    task = json.load(f)
                if task.get("needs_llm"):
                    with open(prompt_path, "w") as f:
                        f.write(task["prompt"])
                    print(f"   Prompt 已保存: {prompt_path}")
                    print(f"   请将 LLM 输出保存到: memory/evaluations/{symbol}_llm.json")
                    print(f"   然后运行: python3 crypto_eval.py merge {symbol} --llm {symbol}_llm.json")
                    return 0  # 等待 LLM
            llm_path = None
    else:
        print(f"\n✅ 所有维度自动评分完成，无需 LLM")
        llm_path = None
    
    # Step 4: 合并
    final_path = os.path.join(EVAL_DIR, f"{symbol}.json")
    llm_arg = f"--llm '{llm_path}'" if llm_path else ""
    stdout, stderr, rc = run_cmd(f"python3 {SCRIPTS_DIR}/merge_score.py '{symbol}' {llm_arg} --output '{final_path}'")
    if rc != 0:
        print(f"❌ 合并失败: {stderr}")
        return 1
    
    result = json.loads(stdout)
    print(f"\n📊 最终评级:")
    print(f"   {result['symbol']} — {result['grade_label']}（{result['score']}分）")
    for dim_id, info in result["dimensions"].items():
        src_tag = "🤖" if info["source"] == "llm" else "⚙️" if info["source"] == "auto" else "❓"
        print(f"   {src_tag} {dim_id}: {info['score']} — {info['note']}")
    if result.get("summary"):
        print(f"   📝 {result['summary']}")
    if result.get("risk"):
        print(f"   ⚠️  {result['risk']}")
    
    return 0

def cmd_auto(args):
    """只跑自动评分"""
    ensure_dirs()
    stdout, stderr, rc = run_cmd(f"python3 {SCRIPTS_DIR}/auto_score.py '{args.symbol}'")
    print(stdout)
    return rc

def cmd_merge(args):
    """合并 LLM 结果"""
    ensure_dirs()
    llm_arg = f"--llm '{args.llm_file}'" if args.llm_file else ""
    stdout, stderr, rc = run_cmd(f"python3 {SCRIPTS_DIR}/merge_score.py '{args.symbol}' {llm_arg}")
    print(stdout)
    return rc

def cmd_show(args):
    """显示已有评估"""
    path = os.path.join(EVAL_DIR, f"{args.symbol.upper()}.json")
    if not os.path.exists(path):
        print(f"❌ 未找到 {args.symbol} 的评估记录")
        return 1
    with open(path) as f:
        data = json.load(f)
    print(f"{data['symbol']} — {data['grade_label']}（{data['score']}分）")
    print(f"评估时间: {data.get('evaluated_at', 'unknown')}")
    for dim_id, info in data.get("dimensions", {}).items():
        src = info.get("source", "?")
        print(f"  {src}: {dim_id} {info['score']} — {info['note']}")
    if data.get("summary"): print(f"\n{data['summary']}")
    if data.get("risk"): print(f"风险: {data['risk']}")
    return 0

def cmd_list(args):
    """列出所有评估"""
    if not os.path.exists(EVAL_DIR):
        print("无评估记录")
        return 0
    files = [f for f in os.listdir(EVAL_DIR) if f.endswith(".json") and not f.endswith("_raw.json") and not f.endswith("_auto.json") and not f.endswith("_llm.json") and not f.endswith("_llm_task.json")]
    if not files:
        print("无评估记录")
        return 0
    print(f"{'Symbol':<12} {'Grade':<4} {'Score':>6} {'Label':<20} {'Time'}")
    print("-" * 70)
    for f in sorted(files):
        path = os.path.join(EVAL_DIR, f)
        try:
            with open(path) as fp:
                d = json.load(fp)
            print(f"{d.get('symbol','?'):<12} {d.get('grade','?'):<4} {d.get('score',0):>6.1f} {d.get('grade_label',''):<20} {d.get('evaluated_at','')[:16]}")
        except:
            print(f"{f:<12} (parse error)")
    return 0

def cmd_test(args):
    """运行测试"""
    import subprocess
    test_dir = os.path.join(SCRIPT_DIR, "tests")
    if not os.path.exists(test_dir):
        print("❌ tests/ 目录不存在")
        return 1
    result = subprocess.run([sys.executable, "-m", "pytest", test_dir, "-v"], capture_output=False)
    return result.returncode

def main():
    parser = argparse.ArgumentParser(description="crypto-eval: 加密资产评估流水线")
    sub = parser.add_subparsers(dest="command")
    
    # evaluate
    p_eval = sub.add_parser("evaluate", help="完整评估流水线")
    p_eval.add_argument("symbol", help="Symbol / 合约地址 / 项目名")
    p_eval.add_argument("--llm-file", help="LLM 结果 JSON 文件路径")
    
    # auto
    p_auto = sub.add_parser("auto", help="仅自动评分")
    p_auto.add_argument("symbol", help="Symbol")
    
    # merge
    p_merge = sub.add_parser("merge", help="合并 LLM 结果")
    p_merge.add_argument("symbol", help="Symbol")
    p_merge.add_argument("--llm-file", help="LLM 结果 JSON 文件")
    
    # show
    p_show = sub.add_parser("show", help="显示已有评估")
    p_show.add_argument("symbol", help="Symbol")
    
    # list
    sub.add_parser("list", help="列出所有评估")
    
    # test
    sub.add_parser("test", help="运行测试")
    
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0
    
    commands = {
        "evaluate": cmd_evaluate,
        "auto": cmd_auto,
        "merge": cmd_merge,
        "show": cmd_show,
        "list": cmd_list,
        "test": cmd_test,
    }
    return commands[args.command](args)

if __name__ == "__main__":
    sys.exit(main())
