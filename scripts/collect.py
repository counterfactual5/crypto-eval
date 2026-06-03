#!/usr/bin/env python3
"""
crypto-eval Stage 1: 信息采集
输入: symbol / contract_address / name
输出: JSON 汇总数据到 stdout，供 LLM 消费

数据源（纯 API，不调 LLM）：
  - CoinGecko: 市值/排名/交易量/上线时间/交易所列表
  - DeFiLlama: TVL/协议类别（如果是 DeFi 协议）
  - 链上: 基础 holder 信息（Etherscan 公开 API）
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request

CACHE_DIR = os.environ.get("CACHE_DIR", os.path.expanduser("~/openclaw-workspace/memory/.cache/crypto-eval"))
CACHE_TTL = int(os.environ.get("CACHE_TTL", "86400"))
os.makedirs(CACHE_DIR, exist_ok=True)


def cached_fetch(url, prefix="generic"):
    """带缓存的 HTTP GET"""
    import hashlib

    h = hashlib.md5(url.encode()).hexdigest()[:12]
    fpath = os.path.join(CACHE_DIR, f"{prefix}_{h}.json")
    if os.path.exists(fpath):
        age = time.time() - os.path.getmtime(fpath)
        if age < CACHE_TTL:
            with open(fpath) as f:
                return json.load(f)
    try:
        time.sleep(1.2)  # 防限流：CoinGecko 免费 ~30 req/min
        req = urllib.request.Request(url, headers={"User-Agent": "crypto-eval/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        with open(fpath, "w") as f:
            json.dump(data, f)
        return data
    except Exception as e:
        # 返回缓存（即使过期）或空
        if os.path.exists(fpath):
            with open(fpath) as f:
                return json.load(f)
        return {"error": str(e)}


def search_coingecko(query):
    """通过 CoinGecko search 找到 coin_id"""
    url = f"https://api.coingecko.com/api/v3/search?query={urllib.parse.quote(query)}"
    data = cached_fetch(url, "cg_search")
    coins = data.get("coins", [])
    if not coins:
        return None
    return coins[0]["id"]


def get_coin_detail(coin_id):
    """CoinGecko coin detail: 交易所列表、市值、描述、上线时间"""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}?localization=false&tickers=true&community_data=false&developer_data=false"
    return cached_fetch(url, "cg_detail")


def get_market_data(coin_id):
    """CoinGecko market data"""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days=30"
    return cached_fetch(url, "cg_market")


def get_defillama_protocol(slug):
    """DeFiLlama TVL"""
    url = f"https://api.llama.fi/protocol/{slug}"
    return cached_fetch(url, "dllama")


def resolve_input(raw_input):
    """
    解析输入: symbol / contract_address / name → CoinGecko coin_id
    """
    raw = raw_input.strip()

    # 以 0x 开头 = 合约地址
    if raw.startswith("0x"):
        url = f"https://api.coingecko.com/api/v3/coins/ethereum/contract/{raw}"
        data = cached_fetch(url, "cg_contract")
        if "id" in data:
            return data["id"]
        # 尝试其他链
        for chain in ["bsc", "polygon", "arbitrum-one", "optimism", "base"]:
            url = f"https://api.coingecko.com/api/v3/coins/{chain}/contract/{raw}"
            data = cached_fetch(url, f"cg_contract_{chain}")
            if "id" in data:
                return data["id"]
        return None

    # 否则当 symbol 或 name 搜索
    coin_id = search_coingecko(raw)
    return coin_id


def collect(coin_id):
    """采集全量数据"""
    detail = get_coin_detail(coin_id)
    if "error" in detail and "id" not in detail:
        return {"error": f"Cannot fetch detail for {coin_id}", "raw": detail}

    result = {
        "coin_id": coin_id,
        "symbol": detail.get("symbol", "").upper(),
        "name": detail.get("name", ""),
        "description": (detail.get("description", {}).get("en", "") or "")[:500],
        "categories": detail.get("categories", []),
        "market_cap_rank": detail.get("market_cap_rank"),
        "market_data": {},
        "links": {},
        "exchanges": [],
        "platforms": list((detail.get("platforms") or {}).keys()),
        "genesis_date": detail.get("genesis_date"),
    }

    md = detail.get("market_data", {})
    if md:
        result["market_data"] = {
            "current_price_usd": md.get("current_price", {}).get("usd"),
            "market_cap_usd": md.get("market_cap", {}).get("usd"),
            "total_volume_24h": md.get("total_volume", {}).get("usd"),
            "circulating_supply": md.get("circulating_supply"),
            "total_supply": md.get("total_supply"),
            "max_supply": md.get("max_supply"),
            "ath_usd": md.get("ath", {}).get("usd"),
            "ath_date": md.get("ath_date", {}).get("usd"),
            "price_change_30d_pct": md.get("price_change_percentage_30d"),
            "price_change_7d_pct": md.get("price_change_percentage_7d"),
        }

    # 交易所列表 — 从 /coins/{id}/tickers 独立端点获取
    ticker_url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/tickers?exchange_ids=binance,okx,coinbase,bybit,bitget,kraken,gate,kucoin,huobi,bitstamp&depth=false"
    ticker_data = cached_fetch(ticker_url, f"cg_tickers_{coin_id}")
    exchanges = set()
    for t in (ticker_data.get("tickers") or [])[:100]:
        ex = (t.get("market", {}) or {}).get("name", "")
        if ex:
            exchanges.add(ex)
    # 兜底：从 detail 里也取
    for t in (detail.get("tickers") or [])[:50]:
        ex = (t.get("market", {}) or {}).get("name", "")
        if ex:
            exchanges.add(ex)
    result["exchanges"] = sorted(exchanges)

    # 链接
    links = detail.get("links", {})
    result["links"] = {
        "homepage": (links.get("homepage") or [None])[0],
        "twitter": links.get("twitter_screen_name"),
        "github": (links.get("repos_url", {}).get("github") or [None])[0],
        "telegram": links.get("telegram_channel_identifier"),
    }

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: collect.py <symbol|contract_address|name> [--json-output PATH]")
        print("  Collects data and prints JSON to stdout")
        print("  --json-output PATH: also save to file")
        sys.exit(1)

    raw_input = sys.argv[1]
    output_path = None
    if "--json-output" in sys.argv:
        idx = sys.argv.index("--json-output")
        output_path = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None

    coin_id = resolve_input(raw_input)
    if not coin_id:
        print(json.dumps({"error": f"Cannot resolve: {raw_input}", "input": raw_input}, indent=2, ensure_ascii=False))
        sys.exit(1)

    data = collect(coin_id)
    out = json.dumps(data, indent=2, ensure_ascii=False)

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w") as f:
            f.write(out)

    print(out)
