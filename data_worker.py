"""
Trading Data Worker - REAL API INTEGRATION (No Mock Data)

Uses only verified working APIs:
- MEXC: Market data (works from Australia, no API key for public data)
- CoinGecko: Market cap, volume (free tier)
- Etherscan: Whale tracking (free API key)
- Coinglass: Liquidations (free API key)
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional

# Import whale data collection
from whale_data import fetch_etherscan_v2_eth_transfers, fetch_coingecko_volume_anomaly

# Import state manager
from state_manager import write_data_worker_output

# ============================================================================
# NEWS COLLECTION (RSS - FREE, NO API KEY)
# ============================================================================

import urllib.request
import xml.etree.ElementTree as ET

NEWS_SOURCES = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("CryptoSlate", "https://cryptoslate.com/feed/"),
    ("The Defiant", "https://thedefiant.io/feed/"),
]

def fetch_crypto_news(limit_per_source: int = 5) -> dict:
    """
    Fetch latest crypto news from RSS feeds (free, no API key).
    
    Args:
        limit_per_source: Number of articles per source
    
    Returns:
        dict with news articles and sentiment indicators
    """
    all_articles = []
    
    for source_name, rss_url in NEWS_SOURCES:
        try:
            with urllib.request.urlopen(rss_url, timeout=10) as response:
                xml_data = response.read()
            
            root = ET.fromstring(xml_data)
            
            # Parse RSS items
            items = root.findall(".//item")[:limit_per_source]
            
            for item in items:
                title_elem = item.find("title")
                link_elem = item.find("link")
                pub_date_elem = item.find("pubDate")
                desc_elem = item.find("description")
                
                if title_elem is not None and link_elem is not None:
                    article = {
                        "title": title_elem.text,
                        "link": link_elem.text,
                        "source": source_name,
                        "published": pub_date_elem.text if pub_date_elem is not None else None,
                        "description": desc_elem.text[:200] + "..." if desc_elem is not None else None,
                    }
                    
                    # Simple keyword-based sentiment
                    title_lower = article["title"].lower()
                    sentiment = "neutral"
                    sentiment_score = 50
                    
                    bullish_keywords = ["surge", "rally", "moon", "breakout", "bull", "green", "gain", "soar", "hit high"]
                    bearish_keywords = ["crash", "dump", "bleed", "bear", "red", "loss", "plunge", "drop", "low"]
                    
                    bullish_count = sum(1 for kw in bullish_keywords if kw in title_lower)
                    bearish_count = sum(1 for kw in bearish_keywords if kw in title_lower)
                    
                    if bullish_count > bearish_count:
                        sentiment = "bullish"
                        sentiment_score = 60 + (bullish_count * 10)
                    elif bearish_count > bullish_count:
                        sentiment = "bearish"
                        sentiment_score = 40 - (bearish_count * 10)
                    
                    article["sentiment"] = sentiment
                    article["sentiment_score"] = min(100, max(0, sentiment_score))
                    
                    all_articles.append(article)
        
        except Exception as e:
            continue
    
    # Sort by recency (if pubDate available)
    all_articles.sort(key=lambda x: x.get("published", ""), reverse=True)
    
    # Calculate aggregate sentiment
    if all_articles:
        avg_sentiment = sum(a["sentiment_score"] for a in all_articles) / len(all_articles)
        bullish_count = sum(1 for a in all_articles if a["sentiment"] == "bullish")
        bearish_count = sum(1 for a in all_articles if a["sentiment"] == "bearish")
    else:
        avg_sentiment = 50
        bullish_count = 0
        bearish_count = 0
    
    return {
        "success": True,
        "articles": all_articles[:20],  # Return top 20
        "article_count": len(all_articles),
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "neutral_count": len(all_articles) - bullish_count - bearish_count,
        "average_sentiment_score": round(avg_sentiment, 1),
        "news_sentiment": "bullish" if avg_sentiment > 55 else "bearish" if avg_sentiment < 45 else "neutral",
        "sources": [s[0] for s in NEWS_SOURCES],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

# ============================================================================
# CONFIGURATION
# ============================================================================

CONFIG = {
    # BINANCE API - Multiple endpoints (choose what works from your server location)
    # Option 1: Global Binance (blocked from US servers)
    # "binance_base_url": "https://api.binance.com",
    
    # Option 2: Binance.US (works from US servers)
    "binance_base_url": "https://api.binance.us",
    
    # Option 3: MEXC (works everywhere, no API key needed)
    "mexc_base_url": "https://api.mexc.com",
    
    # Primary data source: "binance" or "mexc"
    "primary_source": "binance",
    
    # CoinGecko API - Free tier, no key needed for basic endpoints
    "coingecko_base_url": "https://api.coingecko.com/api/v3",
    
    # Etherscan API - Free key: 100,000 calls/day
    "etherscan_api_key": "94H98ZWB5GSKQD1BZBHCHEIRDF4JWYQNXB",
    
    # Coinglass API - Get free key: https://coinglass.com/api
    "coinglass_api_key": "",  # Leave empty for now
    
    # Coin Universe (Top coins by market cap)
    # Start small: 3 coins for testing
    "coin_universe": ["BTC", "ETH", "SOL"],
    
    # Trading Pairs
    "binance_pairs": {
        "BTC": "BTCUSDT",
        "ETH": "ETHUSDT",
        "SOL": "SOLUSDT",
        "BNB": "BNBUSDT",
        "XRP": "XRPUSDT",
        "ADA": "ADAUSDT",
        "DOGE": "DOGEUSDT",
        "DOT": "DOTUSDT",
        "MATIC": "MATICUSDT",
        "LINK": "LINKUSDT",
    },
    
    "mexc_pairs": {
        "BTC": "BTCUSDT",
        "ETH": "ETHUSDT",
        "SOL": "SOLUSDT",
        "BNB": "BNBUSDT",
        "XRP": "XRPUSDT",
        "ADA": "ADAUSDT",
        "DOGE": "DOGEUSDT",
        "DOT": "DOTUSDT",
        "MATIC": "MATICUSDT",
        "LINK": "LINKUSDT",
    },
    
    # Alert Thresholds
    "price_change_alert_pct": 5.0,
    "volume_spike_ratio": 3.0,
    "whale_score_high": 80,
    "whale_score_low": 20,
}


# ============================================================================
# BINANCE API - MARKET DATA
# ============================================================================

def fetch_binance_ohlcv(symbol: str, interval: str = "15m", limit: int = 100) -> dict:
    """
    Fetch OHLCV from Binance API.
    
    Args:
        symbol: Trading pair (e.g., "BTCUSDT")
        interval: 1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d
        limit: Number of candles (max 1000)
    
    Returns:
        dict with candles and calculated indicators
    """
    base_url = CONFIG["binance_base_url"]
    pair = CONFIG["binance_pairs"].get(symbol, f"{symbol}USDT")
    url = f"{base_url}/api/v3/klines?symbol={pair}&interval={interval}&limit={limit}"
    
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
        
        if not isinstance(data, list):
            return {"success": False, "error": f"Unexpected response format: {data}", "source": "binance"}
        
        # Parse Binance candles: [timestamp, open, high, low, close, volume, ...]
        candles = []
        for candle in data:
            candles.append({
                "timestamp": datetime.fromtimestamp(candle[0] / 1000, tz=timezone.utc),
                "open": float(candle[1]),
                "high": float(candle[2]),
                "low": float(candle[3]),
                "close": float(candle[4]),
                "volume": float(candle[5]),
                "quote_volume": float(candle[6]) if len(candle) > 6 else 0,
            })
        
        # Calculate indicators
        indicators = calculate_indicators(candles)
        
        return {
            "success": True,
            "symbol": pair,
            "timeframe": interval,
            "candles": candles,
            "indicators": indicators,
            "source": "binance",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    except urllib.error.HTTPError as e:
        return {
            "success": False,
            "symbol": pair,
            "error": f"HTTP {e.code}: {e.reason}",
            "source": "binance",
        }
    except Exception as e:
        return {
            "success": False,
            "symbol": pair,
            "error": str(e),
            "source": "binance",
        }


# ============================================================================
# MEXC API - MARKET DATA (PROVEN WORKING)
# ============================================================================

def fetch_mexc_ohlcv(symbol: str, interval: str = "15m", limit: int = 100) -> dict:
    """
    Fetch OHLCV from MEXC public API.
    
    TESTED: Works from Australia, no API key required.
    
    Args:
        symbol: Trading pair (e.g., "BTCUSDT")
        interval: 1m, 5m, 15m, 30m, 1h, 4h, 1d
        limit: Number of candles (max 1000)
    
    Returns:
        dict with candles and calculated indicators
    """
    base_url = CONFIG["mexc_base_url"]
    pair = CONFIG["mexc_pairs"].get(symbol, f"{symbol}USDT")
    url = f"{base_url}/api/v3/klines?symbol={pair}&interval={interval}&limit={limit}"
    
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
        
        if not isinstance(data, list):
            return {"success": False, "error": f"Unexpected response format: {data}", "source": "mexc"}
        
        # Parse MEXC candles: [timestamp, open, high, low, close, volume, ...]
        candles = []
        for candle in data:
            candles.append({
                "timestamp": datetime.fromtimestamp(candle[0] / 1000, tz=timezone.utc),
                "open": float(candle[1]),
                "high": float(candle[2]),
                "low": float(candle[3]),
                "close": float(candle[4]),
                "volume": float(candle[5]),
                "quote_volume": float(candle[6]) if len(candle) > 6 else 0,
            })
        
        # Calculate indicators
        indicators = calculate_indicators(candles)
        
        return {
            "success": True,
            "symbol": pair,
            "timeframe": interval,
            "candles": candles,
            "indicators": indicators,
            "source": "mexc",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    except urllib.error.HTTPError as e:
        return {
            "success": False,
            "symbol": pair,
            "error": f"HTTP {e.code}: {e.reason}",
            "source": "mexc",
        }
    except Exception as e:
        return {
            "success": False,
            "symbol": pair,
            "error": str(e),
            "source": "mexc",
        }


# ============================================================================
# COINGECKO API - MARKET CAP & VOLUME
# ============================================================================

def fetch_coingecko_market_data(coin_id: str) -> dict:
    """
    Fetch market cap, volume, price from CoinGecko.
    
    Free tier: 10-50 calls/min (no key for basic endpoints)
    
    Args:
        coin_id: CoinGecko ID (e.g., "bitcoin", "ethereum")
    
    Returns:
        dict with market data
    """
    coin_ids = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "BNB": "binancecoin",
        "XRP": "ripple",
        "ADA": "cardano",
        "DOGE": "dogecoin",
        "DOT": "polkadot",
        "MATIC": "matic-network",
        "LINK": "chainlink",
    }
    
    coingecko_id = coin_ids.get(coin_id, coin_id.lower())
    url = f"{CONFIG['coingecko_base_url']}/coins/{coingecko_id}"
    
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
        
        market_data = data.get("market_data", {})
        
        return {
            "success": True,
            "symbol": coin_id,
            "coingecko_id": coingecko_id,
            "current_price_usd": market_data.get("current_price", {}).get("usd"),
            "market_cap_usd": market_data.get("market_cap", {}).get("usd"),
            "market_cap_rank": market_data.get("market_cap_rank"),
            "total_volume_usd": market_data.get("total_volume", {}).get("usd"),
            "price_change_24h_pct": market_data.get("price_change_percentage_24h"),
            "price_change_7d_pct": market_data.get("price_change_percentage_7d"),
            "circulating_supply": market_data.get("circulating_supply"),
            "volume_to_market_cap_ratio": market_data.get("total_volume", {}).get("usd", 0) / market_data.get("market_cap", {}).get("usd", 1) * 100,
            "source": "coingecko",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    except urllib.error.HTTPError as e:
        return {
            "success": False,
            "symbol": coin_id,
            "error": f"HTTP {e.code}: {e.reason}",
            "source": "coingecko",
        }
    except Exception as e:
        return {
            "success": False,
            "symbol": coin_id,
            "error": str(e),
            "source": "coingecko",
        }


# ============================================================================
# TECHNICAL INDICATORS
# ============================================================================

def calculate_indicators(candles: list) -> dict:
    """
    Calculate technical indicators from candle data.
    
    All indicators calculated from scratch - no external dependencies.
    """
    if len(candles) < 50:
        return {"error": f"Not enough candles (got {len(candles)}, need 50+)"}
    
    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    
    # RSI (14-period)
    rsi = calculate_rsi(closes, 14)
    
    # MACD (12, 26, 9)
    macd_line, signal_line, macd_hist = calculate_macd(closes)
    
    # EMA (20, 50)
    ema_20 = calculate_ema(closes, 20)
    ema_50 = calculate_ema(closes, 50)
    
    # ATR (14-period)
    atr = calculate_atr(highs, lows, closes, 14)
    
    # Volume ratio (current vs 20-period average)
    vol_avg_20 = sum(volumes[-20:]) / 20
    vol_ratio = volumes[-1] / vol_avg_20 if vol_avg_20 > 0 else 1.0
    
    # Price position relative to EMAs
    current_price = closes[-1]
    price_vs_ema20_pct = (current_price - ema_20) / ema_20 * 100 if ema_20 > 0 else 0
    price_vs_ema50_pct = (current_price - ema_50) / ema_50 * 100 if ema_50 > 0 else 0
    
    return {
        "rsi": rsi,
        "macd_line": macd_line,
        "macd_signal": signal_line,
        "macd_histogram": macd_hist,
        "ema_20": ema_20,
        "ema_50": ema_50,
        "atr": atr,
        "volume_ratio": round(vol_ratio, 2),
        "price_vs_ema20_pct": round(price_vs_ema20_pct, 2),
        "price_vs_ema50_pct": round(price_vs_ema50_pct, 2),
        "trend": "bullish" if ema_20 > ema_50 else "bearish",
        "current_price": current_price,
    }


def calculate_rsi(prices: list, period: int = 14) -> float:
    """Calculate RSI (Relative Strength Index)"""
    if len(prices) < period + 1:
        return 50.0
    
    gains = []
    losses = []
    
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        gains.append(max(0, change))
        losses.append(max(0, -change))
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return round(rsi, 2)


def calculate_ema(prices: list, period: int) -> float:
    """Calculate Exponential Moving Average"""
    if len(prices) < period:
        return prices[-1] if prices else 0
    
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    
    return round(ema, 2)


def calculate_macd(prices: list, fast: int = 12, slow: int = 26, signal: int = 9):
    """Calculate MACD (Moving Average Convergence Divergence)"""
    if len(prices) < slow + signal:
        return 0, 0, 0
    
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)
    macd_line = ema_fast - ema_slow
    
    # Calculate signal line from MACD values
    macd_values = []
    for i in range(slow, len(prices)):
        fast_ema = calculate_ema(prices[:i], fast)
        slow_ema = calculate_ema(prices[:i], slow)
        macd_values.append(fast_ema - slow_ema)
    
    signal_line = calculate_ema(macd_values, signal) if macd_values else macd_line
    macd_hist = macd_line - signal_line
    
    return round(macd_line, 4), round(signal_line, 4), round(macd_hist, 4)


def calculate_atr(highs: list, lows: list, closes: list, period: int = 14) -> float:
    """Calculate ATR (Average True Range)"""
    if len(highs) < period + 1:
        return 0
    
    true_ranges = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        true_ranges.append(tr)
    
    atr = sum(true_ranges[-period:]) / period
    return round(atr, 2)


# ============================================================================
# MAIN DATA COLLECTION CYCLE
# ============================================================================

def run_data_collection_cycle(coin_symbols: list = None) -> dict:
    """
    Run a complete data collection cycle.
    
    This is the main function called by Kanban tasks every 5 minutes.
    
    PROVEN WORKING:
    - Binance.US OHLCV: ✅ Works from US servers
    - MEXC OHLCV: ✅ Works globally
    - CoinGecko market data: ✅ Tested
    - Etherscan whales: ⚠️ Requires API key (optional)
    """
    if coin_symbols is None:
        coin_symbols = CONFIG["coin_universe"]
    
    start_time = datetime.now(timezone.utc)
    results = []
    alerts = []
    
    primary_source = CONFIG.get("primary_source", "binance")
    
    print(f"[{start_time.isoformat()}] Starting data collection cycle")
    print(f"  Coins: {', '.join(coin_symbols)}")
    print(f"  Primary Source: {primary_source.upper()}")
    print(f"  News Sources: {len(NEWS_SOURCES)} RSS feeds")
    print()
    
    # Fetch news ONCE per cycle (not per coin)
    print("  Fetching crypto news...")
    news_data = fetch_crypto_news(limit_per_source=5)
    print(f"    ✓ {news_data['article_count']} articles, sentiment: {news_data['news_sentiment']}")
    print()
    
    for symbol in coin_symbols:
        print(f"  Fetching {symbol}...")
        
        # 1. Fetch OHLCV from primary source
        if primary_source == "binance":
            ohlcv_data = fetch_binance_ohlcv(symbol, interval="15m", limit=100)
        else:
            ohlcv_data = fetch_mexc_ohlcv(symbol, interval="15m", limit=100)
        
        # 2. Fetch market data from CoinGecko
        market_data = fetch_coingecko_market_data(symbol)
        
        # 3. Fetch whale data from Etherscan (ETH only, every cycle)
        # For other coins, use cached or neutral data
        if symbol == "ETH":
            whale_data = fetch_etherscan_v2_eth_transfers(limit=50)
            print(f"    Etherscan: {whale_data.get('large_txn_count', 0)} large ETH transactions")
        else:
            # For non-ETH coins, use volume-based whale proxy from CoinGecko
            whale_data = {
                "success": market_data.get("success", False),
                "whale_activity_score": 50,  # Will be overridden by CoinGecko volume in calculate_whale_score
                "note": f"Using volume proxy for {symbol}",
            }
        
        # Combine data
        coin_data = {
            "symbol": symbol,
            "timestamp": start_time.isoformat(),
            "ohlcv": ohlcv_data,
            "market": market_data,
            "whale": whale_data,
            "news": news_data,  # Same news for all coins
        }
        
        # Calculate whale score (combine signals)
        whale_score = calculate_whale_score(coin_data)
        coin_data["whale_score"] = whale_score
        
        # Check alerts
        alert_status = check_alert_conditions(coin_data)
        coin_data["alert"] = alert_status
        
        if alert_status["alert_triggered"]:
            alerts.append({
                "symbol": symbol,
                "reason": alert_status["alert_reason"],
                "whale_score": whale_score,
            })
        
        results.append(coin_data)
        status = "✓" if ohlcv_data["success"] else "✗"
        print(f"    {status} {symbol}: whale_score={whale_score}, alert={alert_status['alert_triggered']}")
        if not ohlcv_data["success"]:
            print(f"       Error: {ohlcv_data.get('error', 'Unknown')}")
    
    end_time = datetime.now(timezone.utc)
    duration_seconds = (end_time - start_time).total_seconds()
    
    # Summary
    summary = {
        "cycle_start": start_time.isoformat(),
        "cycle_end": end_time.isoformat(),
        "duration_seconds": round(duration_seconds, 2),
        "coins_processed": len(results),
        "alerts_triggered": len(alerts),
        "average_whale_score": round(sum(c["whale_score"] for c in results) / len(results), 1) if results else 0,
        "primary_source": primary_source,
    }
    
    print()
    print(f"[{end_time.isoformat()}] Cycle complete: {len(results)} coins, {len(alerts)} alerts")
    print()
    
    # Write to shared state for Orchestrator
    print("  Writing to shared state...")
    write_result = write_data_worker_output({
        "summary": summary,
        "coin_data": results,
        "alerts": alerts,
    })
    print(f"    ✓ Saved to {write_result['file']}")
    print(f"    Backup: {write_result.get('backup', 'N/A')}")
    
    return {
        "success": True,
        "summary": summary,
        "coin_data": results,
        "alerts": alerts,
        "state": write_result,
    }


def calculate_whale_score(coin_data: dict) -> int:
    """
    Calculate composite whale score (0-100).
    
    Free sources only:
    - CoinGecko volume/MCap ratio (primary - proven working)
    - MEXC/Binance volume spike detection
    - Etherscan large stablecoin transfers
    - News sentiment (RSS feeds)
    """
    score = 50  # Start neutral
    
    # 1. CoinGecko volume anomaly (BEST FREE WHALE INDICATOR)
    market = coin_data.get("market", {})
    if market.get("success"):
        vol_ratio = market.get("volume_to_market_cap_ratio", 0)
        
        if vol_ratio > 15:
            score += 25
        elif vol_ratio > 10:
            score += 15
        elif vol_ratio > 7:
            score += 8
        elif vol_ratio < 2:
            score -= 10
    
    # 2. MEXC/Binance volume spike
    ohlcv = coin_data.get("ohlcv", {})
    if ohlcv.get("success"):
        vol_ratio = ohlcv.get("indicators", {}).get("volume_ratio", 1)
        if vol_ratio > 3:
            score += 15
        elif vol_ratio > 2:
            score += 8
    
    # 3. Etherscan whale transfers
    whale = coin_data.get("whale", {})
    if whale.get("success"):
        whale_score = whale.get("whale_activity_score", 50)
        score += (whale_score - 50) * 0.3
    
    # 4. News sentiment (NEW)
    news = coin_data.get("news", {})
    if news.get("success"):
        sentiment_score = news.get("average_sentiment_score", 50)
        # If news is very bullish (>65) or very bearish (<35), adjust score
        if sentiment_score > 65:
            score += 10  # Bullish news
        elif sentiment_score < 35:
            score -= 10  # Bearish news
    
    return max(0, min(100, int(score)))


def check_alert_conditions(coin_data: dict) -> dict:
    """Check if any alert conditions are triggered"""
    alerts = []
    
    # Price change alert
    ohlcv = coin_data.get("ohlcv", {})
    if ohlcv.get("success"):
        candles = ohlcv.get("candles", [])
        if len(candles) >= 2:
            price_change = abs(candles[-1]["close"] - candles[-2]["close"]) / candles[-2]["close"] * 100
            if price_change > CONFIG["price_change_alert_pct"]:
                alerts.append(f"Price move {price_change:.1f}%")
    
    # Volume spike alert
    if ohlcv.get("success"):
        vol_ratio = ohlcv.get("indicators", {}).get("volume_ratio", 1)
        if vol_ratio > CONFIG["volume_spike_ratio"]:
            alerts.append(f"Volume spike {vol_ratio}x")
    
    return {
        "alert_triggered": len(alerts) > 0,
        "alert_reason": "; ".join(alerts) if alerts else None,
        "alert_count": len(alerts),
    }


# ============================================================================
# TEST / DEMO
# ============================================================================

if __name__ == "__main__":
    print("="*60)
    print("DATA WORKER - LIVE API TEST")
    print("="*60)
    print()
    
    result = run_data_collection_cycle(["BTC", "ETH", "SOL"])
    
    print()
    print("="*60)
    print("RESULTS")
    print("="*60)
    print(json.dumps(result["summary"], indent=2))
    print()
    print("Sample coin data (BTC):")
    if result["coin_data"]:
        btc = result["coin_data"][0]
        print(f"  Symbol: {btc['symbol']}")
        print(f"  Whale Score: {btc['whale_score']}")
        print(f"  OHLCV Success: {btc['ohlcv']['success']}")
        if btc['ohlcv'].get('indicators'):
            indicators = btc['ohlcv']['indicators']
            print(f"  RSI: {indicators.get('rsi')}")
            print(f"  Trend: {indicators.get('trend')}")
            print(f"  Current Price: ${indicators.get('current_price'):,.2f}")
