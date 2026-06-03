#!/usr/bin/env python3
"""
Price Feed - Live Cryptocurrency Prices

Fetches real-time prices from Binance public API (no auth required).
Fallback to CoinGecko if Binance fails.

Usage:
    from core.price_feed import get_price, get_prices_batch
    
    # Single price
    btc_price = get_price('BTC')
    
    # Batch prices
    prices = get_prices_batch(['BTC', 'ETH', 'SOL'])
"""

import requests
import time
from typing import Dict, Optional, List
from datetime import datetime, timezone

# Cache to avoid excessive API calls
_price_cache = {}
_CACHE_TTL_SECONDS = 300  # Cache prices for 5 minutes (reduce API calls)


def _get_binance_symbol(coin: str) -> str:
    """Convert coin symbol to Binance format"""
    coin = coin.upper().strip()
    
    # Map common symbols to Binance format
    symbol_map = {
        'BTC': 'BTCUSDT',
        'ETH': 'ETHUSDT',
        'SOL': 'SOLUSDT',
        'BNB': 'BNBUSDT',
        'XRP': 'XRPUSDT',
        'ADA': 'ADAUSDT',
        'AVAX': 'AVAXUSDT',
        'MATIC': 'MATICUSDT',
        'DOT': 'DOTUSDT',
        'LINK': 'LINKUSDT',
        'UNI': 'UNIUSDT',
        'ATOM': 'ATOMUSDT',
        'DOGE': 'DOGEUSDT',
        'LTC': 'LTCUSDT',
        'BCH': 'BCHUSDT',
    }
    
    return symbol_map.get(coin, f'{coin}USDT')


def _fetch_binance_price(symbol: str) -> Optional[float]:
    """
    Fetch price from Binance.US public API
    
    Args:
        symbol: Binance symbol (e.g., 'BTCUSDT')
    
    Returns:
        Price in USDT, or None if failed
    """
    try:
        # Use Binance.US (works from Australia)
        url = f'https://api.binance.us/api/v3/ticker/price?symbol={symbol}'
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            price = float(data['price'])
            return price
        else:
            print(f"Binance.US API error: {response.status_code} for {symbol}")
            return None
    
    except requests.exceptions.RequestException as e:
        print(f"Binance.US request failed for {symbol}: {e}")
        return None
    except (KeyError, ValueError) as e:
        print(f"Binance.US parse error for {symbol}: {e}")
        return None


def _fetch_coingecko_price(coin: str) -> Optional[float]:
    """
    Fallback: Fetch price from CoinGecko public API
    
    Args:
        coin: Coin symbol (e.g., 'bitcoin')
    
    Returns:
        Price in USD, or None if failed
    """
    # Map symbols to CoinGecko IDs
    coingecko_ids = {
        'BTC': 'bitcoin',
        'ETH': 'ethereum',
        'SOL': 'solana',
        'BNB': 'binancecoin',
        'XRP': 'ripple',
        'ADA': 'cardano',
        'AVAX': 'avalanche-2',
        'MATIC': 'matic-network',
        'DOT': 'polkadot',
        'LINK': 'chainlink',
        'UNI': 'uniswap',
        'ATOM': 'cosmos',
        'DOGE': 'dogecoin',
        'LTC': 'litecoin',
        'BCH': 'bitcoin-cash',
    }
    
    coin_id = coingecko_ids.get(coin.upper())
    if not coin_id:
        return None
    
    try:
        url = f'https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd'
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            price = data.get(coin_id, {}).get('usd')
            return float(price) if price else None
        else:
            print(f"CoinGecko API error: {response.status_code} for {coin_id}")
            return None
    
    except requests.exceptions.RequestException as e:
        print(f"CoinGecko request failed for {coin_id}: {e}")
        return None
    except (KeyError, ValueError) as e:
        print(f"CoinGecko parse error for {coin_id}: {e}")
        return None


def _fetch_coincap_price(coin: str) -> Optional[float]:
    """
    Third fallback: Fetch price from CoinCap API
    
    Args:
        coin: Coin symbol (e.g., 'bitcoin')
    
    Returns:
        Price in USD, or None if failed
    """
    # Map symbols to CoinCap IDs
    coincap_ids = {
        'BTC': 'bitcoin',
        'ETH': 'ethereum',
        'SOL': 'solana',
        'BNB': 'binance-coin',
        'XRP': 'xrp',
        'ADA': 'cardano',
        'AVAX': 'avalanche',
        'MATIC': 'polygon',
        'DOT': 'polkadot',
        'LINK': 'chainlink',
        'UNI': 'uniswap',
        'ATOM': 'cosmos',
        'DOGE': 'dogecoin',
        'LTC': 'litecoin',
        'BCH': 'bitcoin-cash',
    }
    
    coin_id = coincap_ids.get(coin.upper())
    if not coin_id:
        return None
    
    try:
        url = f'https://api.coincap.io/v2/assets/{coin_id}'
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            price = data.get('data', {}).get('priceUsd')
            return float(price) if price else None
        else:
            print(f"CoinCap API error: {response.status_code} for {coin_id}")
            return None
    
    except requests.exceptions.RequestException as e:
        print(f"CoinCap request failed for {coin_id}: {e}")
        return None
    except (KeyError, ValueError) as e:
        print(f"CoinCap parse error for {coin_id}: {e}")
        return None


def get_price(coin: str, use_cache: bool = True) -> Optional[float]:
    """
    Get current price for a coin (USDT)
    
    Tries in order:
    1. CoinGecko (most reliable)
    2. CoinCap (good fallback)
    3. Binance.US (works from Australia)
    
    CRITICAL: NO MOCK DATA. Returns None if ALL sources fail.
    
    Args:
        coin: Coin symbol (e.g., 'BTC', 'ETH')
        use_cache: Use cached price if available (default: True)
    
    Returns:
        Price in USDT, or None if ALL sources failed
    """
    coin = coin.upper().strip()
    now = datetime.now(timezone.utc).timestamp()
    
    # Check cache
    if use_cache and coin in _price_cache:
        cached_time, cached_price = _price_cache[coin]
        if now - cached_time < _CACHE_TTL_SECONDS:
            return cached_price
    
    # Try CoinGecko first (most reliable)
    price = _fetch_coingecko_price(coin)
    
    # Fallback to CoinCap
    if price is None:
        print(f"  ⚠️  CoinGecko failed for {coin}, trying CoinCap...")
        price = _fetch_coincap_price(coin)
    
    # Fallback to Binance.US
    if price is None:
        print(f"  ⚠️  CoinCap failed for {coin}, trying Binance.US...")
        binance_symbol = _get_binance_symbol(coin)
        price = _fetch_binance_price(binance_symbol)
    
    # NO MOCK FALLBACK - return None if all failed
    if price is not None:
        _price_cache[coin] = (now, price)
        return price
    else:
        print(f"  ❌ CRITICAL: All price sources failed for {coin} - NO MOCK DATA")
        return None


def get_prices_batch(coins: List[str], use_cache: bool = True) -> Dict[str, float]:
    """
    Get prices for multiple coins
    
    Args:
        coins: List of coin symbols
        use_cache: Use cached prices if available
    
    Returns:
        Dict mapping coin -> price (only successful fetches)
    """
    prices = {}
    
    for coin in coins:
        price = get_price(coin, use_cache)
        if price is not None:
            prices[coin.upper()] = price
    
    return prices


def clear_cache():
    """Clear price cache (useful for testing)"""
    global _price_cache
    _price_cache = {}


def get_cache_info() -> Dict:
    """Get cache statistics"""
    return {
        'cached_coins': list(_price_cache.keys()),
        'cache_size': len(_price_cache),
        'cache_ttl': _CACHE_TTL_SECONDS
    }


# ============================================================================
# MAIN (Test Mode)
# ============================================================================

if __name__ == '__main__':
    print("="*80)
    print("PRICE FEED - LIVE TEST")
    print("="*80)
    print()
    
    # Test coins
    test_coins = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']
    
    print(f"Fetching prices for: {', '.join(test_coins)}")
    print()
    
    prices = get_prices_batch(test_coins, use_cache=False)
    
    if prices:
        print("✅ SUCCESS - Live Prices:")
        print("-" * 80)
        for coin, price in sorted(prices.items()):
            print(f"  {coin}: ${price:,.2f}")
        print("-" * 80)
        print(f"Total: {len(prices)}/{len(test_coins)} coins fetched")
    else:
        print("❌ FAILED - Could not fetch any prices")
    
    print()
    print("Cache info:", get_cache_info())
