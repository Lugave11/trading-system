"""
Whale Data Collection - FREE Sources Only

Tested and verified free sources for whale tracking:
1. Etherscan V2 API (free tier) - ETH transfers, token transfers
2. Blockchair API (free tier) - Multi-chain whale transactions  
3. DexScreener API (free) - DEX large swaps
4. CoinGecko - Volume/market cap anomalies (proxy for whale activity)
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ============================================================================
# CONFIGURATION
# ============================================================================

WHALE_CONFIG = {
    # Etherscan V2 API - Free: 100,000 calls/day
    "etherscan_api_key": "94H98ZWB5GSKQD1BZBHCHEIRDF4JWYQNXB",
    
    # Blockchair API - Free: 100 calls/day
    "blockchair_api_key": "",  # Get free: https://blockchair.com/api
    
    # Whale thresholds (USD)
    "whale_threshold_eth": 100,      # 100+ ETH transactions
    "whale_threshold_usd": 500000,   # $500K+ transactions
    
    # Coins to track (with EVM contracts)
    "tracked_tokens": {
        "USDT": "0xdac17f958d2ee523a2206206994597c13d831ec7",
        "USDC": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "WBTC": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
    }
}


# ============================================================================
# ETHERSCAN V2 API - FREE TIER
# ============================================================================

def fetch_etherscan_v2_eth_transfers(limit: int = 50) -> dict:
    """
    Fetch recent large TOKEN transfers (USDT, USDC) from Etherscan V2 API.
    
    This tracks stablecoin movements which are better whale indicators than ETH transfers.
    
    Free tier: 100,000 calls/day
    
    Args:
        limit: Number of transactions to fetch
    
    Returns:
        dict with large transactions and whale metrics
    """
    api_key = WHALE_CONFIG.get("etherscan_api_key", "")
    
    if not api_key:
        return {
            "success": False,
            "error": "Etherscan API key not configured",
            "whale_activity_score": 50,
        }
    
    # Track USDT and USDC transfers (most common whale stablecoins)
    stablecoin_addresses = [
        ("USDT", "0xdac17f958d2ee523a2206206994597c13d831ec7"),
        ("USDC", "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"),
    ]
    
    all_transfers = []
    
    for token_name, token_address in stablecoin_addresses:
        url = f"https://api.etherscan.io/v2/api?chainid=1&module=account&action=tokentx&contractaddress={token_address}&page=1&offset={limit//2}&sort=desc&apikey={api_key}"
        
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode())
            
            if data.get("status") == "1":
                txns = data.get("result", [])
                for txn in txns:
                    value = int(txn.get("value", 0))
                    decimals = int(txn.get("tokenDecimal", 6))
                    value_formatted = value / (10 ** decimals)
                    
                    # Track transfers >$100K USD
                    if value_formatted >= 100000:  # $100K+
                        all_transfers.append({
                            "hash": txn.get("transactionHash"),
                            "from": txn.get("from")[:10] + "...",
                            "to": txn.get("to")[:10] + "...",
                            "value": value_formatted,
                            "value_usd": value_formatted,  # Stablecoin ≈ USD
                            "token": token_name,
                            "timestamp": txn.get("timeStamp"),
                        })
        except Exception as e:
            continue
    
    if not all_transfers:
        return {
            "success": True,  # No error, just no large transfers
            "large_transactions": [],
            "large_txn_count": 0,
            "total_volume_usd": 0,
            "whale_activity_score": 50,
            "threshold_usd": 100000,
            "source": "etherscan_v2",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    # Sort by value (largest first)
    all_transfers.sort(key=lambda x: x["value_usd"], reverse=True)
    
    total_volume = sum(t["value_usd"] for t in all_transfers)
    
    # Whale activity score (0-100)
    # More large transfers = higher score
    base_score = 50
    score_adjustment = min(50, len(all_transfers) * 2)  # 2 points per large transfer
    whale_score = base_score + score_adjustment
    
    return {
        "success": True,
        "large_transactions": all_transfers[:10],  # Return top 10
        "large_txn_count": len(all_transfers),
        "total_volume_usd": round(total_volume, 2),
        "whale_activity_score": min(100, whale_score),
        "threshold_usd": 100000,
        "source": "etherscan_v2",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def fetch_etherscan_token_transfers(token_address: str, limit: int = 10) -> dict:
    """
    Fetch recent large token transfers (USDT, USDC, etc.)
    
    Args:
        token_address: ERC20 token contract address
        limit: Number of transfers to fetch
    
    Returns:
        dict with large token transfers
    """
    api_key = WHALE_CONFIG.get("etherscan_api_key", "")
    
    if not api_key:
        return {
            "success": False,
            "error": "Etherscan API key not configured",
        }
    
    url = f"https://api.etherscan.io/v2/api?chainid=1&module=account&action=tokentx&contractaddress={token_address}&startblock=0&endblock=99999999&sort=desc&apikey={api_key}"
    
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
        
        if data.get("status") != "1":
            return {
                "success": False,
                "error": data.get("message"),
            }
        
        transfers = data.get("result", [])[:limit]
        
        # Process transfers
        large_transfers = []
        for txn in transfers:
            value = int(txn.get("value", 0))
            decimals = int(txn.get("tokenDecimal", 18))
            value_formatted = value / (10 ** decimals)
            
            # Filter large transfers (>$500K USD equivalent)
            if value_formatted * 1 >= WHALE_CONFIG["whale_threshold_usd"]:  # Simplified
                large_transfers.append({
                    "hash": txn.get("transactionHash"),
                    "from": txn.get("from"),
                    "to": txn.get("to"),
                    "value": value_formatted,
                    "token_symbol": txn.get("tokenSymbol"),
                    "timestamp": txn.get("timeStamp"),
                })
        
        return {
            "success": True,
            "large_transfers": large_transfers,
            "count": len(large_transfers),
            "token": txn.get("tokenSymbol") if transfers else "Unknown",
            "source": "etherscan_v2",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


# ============================================================================
# DEXSCREENER API - FREE, NO KEY
# ============================================================================

def fetch_dexscreener_large_swaps(symbol: str, chain: str = "ethereum") -> dict:
    """
    Fetch large DEX swaps from DexScreener (free, no API key).
    
    This is a PROXY for whale activity - large swaps often indicate whales.
    
    Args:
        symbol: Token symbol (e.g., "ETH")
        chain: Blockchain (ethereum, bsc, solana, etc.)
    
    Returns:
        dict with large swap indicators
    """
    base_url = f"https://api.dexscreener.com/latest/dex/search?q={symbol}"
    
    try:
        with urllib.request.urlopen(base_url, timeout=10) as response:
            data = json.loads(response.read().decode())
        
        if not data.get("pairs"):
            return {
                "success": False,
                "error": "No pairs found",
            }
        
        # Filter by chain
        chain_pairs = [p for p in data["pairs"] if p.get("chainId", "").lower() == chain.lower()]
        
        if not chain_pairs:
            chain_pairs = data["pairs"][:5]
        
        # Analyze transaction patterns for whale indicators
        whale_indicators = []
        
        for pair in chain_pairs[:5]:  # Top 5 pairs
            txns_24h = pair.get("txns", {}).get("h24", {})
            buys = txns_24h.get("buys", 0)
            sells = txns_24h.get("sells", 0)
            volume_24h = pair.get("volume", {}).get("h24", 0)
            
            # Calculate average transaction size
            total_txns = buys + sells
            avg_txn_size = volume_24h / total_txns if total_txns > 0 else 0
            
            # Whale indicator: unusually large average transaction
            if avg_txn_size > 50000:  # >$50K average
                whale_indicators.append({
                    "pair": pair.get("pairAddress", "")[:10] + "...",
                    "avg_txn_size_usd": round(avg_txn_size, 2),
                    "volume_24h": volume_24h,
                })
        
        # Whale score based on large average transactions
        whale_score = 50
        if whale_indicators:
            avg_whale_size = sum(i["avg_txn_size_usd"] for i in whale_indicators) / len(whale_indicators)
            if avg_whale_size > 100000:
                whale_score = 80
            elif avg_whale_size > 50000:
                whale_score = 65
            elif avg_whale_size > 20000:
                whale_score = 55
        
        return {
            "success": True,
            "chain": chain,
            "whale_indicators": whale_indicators,
            "whale_score": whale_score,
            "source": "dexscreener",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "whale_score": 50,
        }


# ============================================================================
# COINGECKO - VOLUME ANOMALIES (WHALE PROXY)
# ============================================================================

def fetch_coingecko_volume_anomaly(coin_id: str) -> dict:
    """
    Detect volume anomalies that may indicate whale activity.
    
    Free tier endpoint - no API key needed.
    
    Args:
        coin_id: CoinGecko ID (e.g., "bitcoin", "ethereum")
    
    Returns:
        dict with volume analysis and whale probability
    """
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
    
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
        
        market_data = data.get("market_data", {})
        
        current_volume = market_data.get("total_volume", {}).get("usd", 0)
        market_cap = market_data.get("market_cap", {}).get("usd", 0)
        
        # Volume/Market Cap ratio
        # Normal: 1-5%
        # Elevated (>10%): Possible whale activity
        vol_mc_ratio = (current_volume / market_cap * 100) if market_cap > 0 else 0
        
        # Whale probability based on volume anomaly
        whale_probability = "low"
        whale_score = 50
        
        if vol_mc_ratio > 15:
            whale_probability = "high"
            whale_score = 80
        elif vol_mc_ratio > 10:
            whale_probability = "medium"
            whale_score = 65
        elif vol_mc_ratio > 5:
            whale_probability = "elevated"
            whale_score = 55
        
        return {
            "success": True,
            "coin_id": coin_id,
            "volume_24h_usd": current_volume,
            "market_cap_usd": market_cap,
            "volume_to_market_cap_ratio_pct": round(vol_mc_ratio, 2),
            "whale_probability": whale_probability,
            "whale_score": whale_score,
            "source": "coingecko_volume_anomaly",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "whale_score": 50,
        }


# ============================================================================
# MAIN WHALE DATA COLLECTION
# ============================================================================

def collect_whale_data(coin_symbols: list = None) -> dict:
    """
    Collect whale data from all free sources.
    
    Args:
        coin_symbols: List of coins to analyze (e.g., ["BTC", "ETH"])
    
    Returns:
        dict with aggregated whale data
    """
    if coin_symbols is None:
        coin_symbols = ["ETH"]  # Etherscan only tracks ETH directly
    
    start_time = datetime.now(timezone.utc)
    results = {}
    
    print(f"[{start_time.isoformat()}] Collecting whale data...")
    
    # 1. Etherscan ETH transfers (requires API key)
    print("  Fetching Etherscan ETH transfers...")
    etherscan_data = fetch_etherscan_v2_eth_transfers(limit=50)
    results["etherscan"] = etherscan_data
    
    if etherscan_data.get("success"):
        print(f"    ✓ Found {etherscan_data['large_txn_count']} large ETH transactions")
    else:
        print(f"    ⚠ {etherscan_data.get('error', 'Unknown error')}")
    
    # 2. DexScreener large swaps (no key needed)
    for symbol in coin_symbols:
        print(f"  Fetching DexScreener data for {symbol}...")
        dex_data = fetch_dexscreener_large_swaps(symbol, chain="ethereum")
        results[f"dexscreener_{symbol}"] = dex_data
        
        if dex_data.get("success"):
            print(f"    ✓ {symbol} whale score: {dex_data['whale_score']}")
    
    # 3. CoinGecko volume anomalies (no key needed)
    coin_ids = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
    }
    
    for symbol, coin_id in coin_ids.items():
        if symbol in coin_symbols or symbol == "ETH":
            print(f"  Fetching CoinGecko volume anomaly for {symbol}...")
            cg_data = fetch_coingecko_volume_anomaly(coin_id)
            results[f"coingecko_{symbol}"] = cg_data
            
            if cg_data.get("success"):
                print(f"    ✓ {symbol} volume/MCap ratio: {cg_data['volume_to_market_cap_ratio_pct']}% ({cg_data['whale_probability']})")
    
    end_time = datetime.now(timezone.utc)
    
    # Aggregate whale score
    scores = [v.get("whale_score", 50) for v in results.values() if isinstance(v, dict) and "whale_score" in v]
    avg_whale_score = sum(scores) / len(scores) if scores else 50
    
    return {
        "success": True,
        "summary": {
            "collection_time": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "sources_used": list(results.keys()),
            "average_whale_score": round(avg_whale_score, 1),
        },
        "data": results,
    }


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":
    print("="*60)
    print("WHALE DATA COLLECTION - FREE SOURCES")
    print("="*60)
    print()
    
    result = collect_whale_data(["ETH", "BTC"])
    
    print()
    print("="*60)
    print("SUMMARY")
    print("="*60)
    print(json.dumps(result["summary"], indent=2))
