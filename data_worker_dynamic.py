#!/usr/bin/env python3
"""
Data Worker - Dynamic Coin Discovery

Scans Binance.US every 5 minutes and discovers the best coins to trade.
No hardcoded lists - coins are ranked by volume, volatility, and whale activity.
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import sys

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent))

# ============================================================================
# CONFIGURATION
# ============================================================================

# Fallback coins if Orchestrator doesn't assign any (emergency only)
FALLBACK_COINS = ['BTC', 'ETH', 'SOL']

# Whale scoring
WHALE_THRESHOLD_USD = 100_000  # $100K+ transfers

# ============================================================================
# COIN ASSIGNMENT (From Orchestrator)
# ============================================================================

def get_assigned_coins() -> List[str]:
    """
    Get coins assigned by Orchestrator via Kanban task metadata.
    
    Priority:
    1. Read from parent task metadata (assigned_coins)
    2. Read from shared state (orchestrator_selected_coins)
    3. Fallback to FALLBACK_COINS (emergency only)
    """
    import os
    import json
    
    # Try to get from environment (set by Kanban system)
    assigned_coins_env = os.environ.get('KANBAN_ASSIGNED_COINS')
    if assigned_coins_env:
        assigned_coins = json.loads(assigned_coins_env)
        print(f"✓ Got assigned coins from environment: {', '.join(assigned_coins)}")
        return assigned_coins
    
    # Try to read from parent task metadata (shared state)
    state_file = Path(__file__).parent / 'state' / 'orchestrator_latest.json'
    if state_file.exists():
        try:
            with open(state_file) as f:
                state = json.load(f)
            
            discovery = state.get('discovery', {})
            selected_coins = discovery.get('selected_coins', [])
            
            if selected_coins:
                print(f"✓ Got assigned coins from orchestrator state: {', '.join(selected_coins)}")
                return selected_coins
        except Exception as e:
            print(f"⚠ Could not read orchestrator state: {e}")
    
    # Fallback (should not happen in production)
    print(f"⚠ No coins assigned by Orchestrator - using fallback: {', '.join(FALLBACK_COINS)}")
    return FALLBACK_COINS


# ============================================================================
# MARKET DATA
# ============================================================================

def fetch_ohlcv(symbol: str, timeframe: str = '5m', limit: int = 100) -> Optional[List[Dict]]:
    """Fetch OHLCV candles from Binance.US"""
    try:
        url = f"https://api.binance.us/api/v3/klines?symbol={symbol}USDT&interval={timeframe}&limit={limit}"
        
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
        
        candles = []
        for candle in data:
            candles.append({
                'timestamp': datetime.fromtimestamp(candle[0]/1000, tz=timezone.utc).isoformat(),
                'open': float(candle[1]),
                'high': float(candle[2]),
                'low': float(candle[3]),
                'close': float(candle[4]),
                'volume': float(candle[5]),
            })
        
        return candles
    
    except Exception as e:
        print(f"  ✗ {symbol} OHLCV error: {e}")
        return None


def calculate_indicators(candles: List[Dict]) -> Dict:
    """Calculate technical indicators"""
    if len(candles) < 50:
        return {'error': 'Insufficient data'}
    
    closes = [c['close'] for c in candles]
    volumes = [c['volume'] for c in candles]
    
    # RSI (14)
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    
    avg_gain = sum(gains[-14:]) / 14
    avg_loss = sum(losses[-14:]) / 14 if sum(losses[-14:]) > 0 else 0.0001
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    # EMA20
    ema20 = sum(closes[-20:]) / 20
    
    # Volume ratio
    avg_volume = sum(volumes[-20:]) / 20
    volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 1
    
    # ATR (14) - volatility
    tr_list = []
    for i in range(1, min(15, len(candles))):
        high = candles[i]['high']
        low = candles[i]['low']
        prev_close = candles[i-1]['close']
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_list.append(tr)
    atr = sum(tr_list) / len(tr_list) if tr_list else 0
    atr_pct = (atr / closes[-1]) * 100
    
    return {
        'rsi': round(rsi, 2),
        'ema20': round(ema20, 2),
        'volume_ratio': round(volume_ratio, 2),
        'atr_pct': round(atr_pct, 2),
        'current_price': closes[-1],
        'trend': 'bullish' if closes[-1] > ema20 else 'bearish',
    }


# ============================================================================
# MAIN CYCLE
# ============================================================================

def run_data_collection_cycle():
    """Main data collection cycle"""
    print("\n" + "="*70)
    print("DATA WORKER - Collecting for Assigned Coins")
    print("="*70)
    print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    # Step 1: Get assigned coins from Orchestrator
    assigned_coins = get_assigned_coins()
    
    if not assigned_coins:
        print("\n✗ No coins assigned - aborting cycle")
        return {
            'success': False,
            'assigned_coins': [],
            'coin_data': [],
            'error': 'No coins assigned by Orchestrator'
        }
    
    print(f"\n📋 Assigned coins: {', '.join(assigned_coins)}")
    
    # Step 2: Fetch data for assigned coins only
    coin_data_list = []
    
    for symbol in assigned_coins:
        print(f"\n  Fetching {symbol}...")
        
        # Fetch OHLCV
        candles = fetch_ohlcv(symbol, timeframe='5m', limit=100)
        
        if not candles:
            print(f"    ✗ Failed to fetch data for {symbol}")
            continue
        
        # Calculate indicators
        indicators = calculate_indicators(candles)
        
        # Get current price from 24h ticker (for volume/whale scoring)
        try:
            ticker_url = f"https://api.binance.us/api/v3/ticker/24hr?symbol={symbol}USDT"
            with urllib.request.urlopen(ticker_url, timeout=5) as response:
                ticker_data = json.loads(response.read().decode())
            
            volume_24h = float(ticker_data.get('quoteVolume', 0))
            price_change_pct = float(ticker_data.get('priceChangePercent', 0))
            current_price = float(ticker_data.get('lastPrice', 0))
            
            # Calculate whale score
            whale_score = 50  # Base
            if volume_24h > 50_000_000:
                whale_score += 20
            if abs(price_change_pct) > 5:
                whale_score += 15
        except:
            current_price = indicators.get('current_price', 0)
            volume_24h = 0
            price_change_pct = 0
            whale_score = 50
        
        coin_data = {
            'symbol': symbol,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'ohlcv': {
                'success': True,
                'candles': candles[-50:],  # Last 50 for strategy
                'indicators': indicators,
            },
            'market_data': {
                'price': current_price,
                'volume_24h': volume_24h,
                'volatility_pct': abs(price_change_pct),
            },
            'whale_score': min(100, whale_score),
        }
        
        coin_data_list.append(coin_data)
        print(f"    ✓ {symbol}: RSI {indicators['rsi']:.1f} | Vol ratio {indicators['volume_ratio']:.2f}x | Trend: {indicators['trend']} | Whale: {whale_score}")
    
    # Step 3: Build output
    output = {
        'success': True,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'assigned_coins': assigned_coins,
        'coin_data': coin_data_list,
        'summary': {
            'coins_assigned': len(assigned_coins),
            'coins_processed': len(coin_data_list),
            'average_whale_score': sum(c['whale_score'] for c in coin_data_list) / len(coin_data_list) if coin_data_list else 0,
        }
    }
    
    print(f"\n✅ Data collection complete: {len(coin_data_list)}/{len(assigned_coins)} coins")
    return output


# ============================================================================
# KANBAN INTEGRATION
# ============================================================================

def complete_kanban_task(output: Dict):
    """Complete Kanban task silently (no Gateway message)"""
    try:
        from kanban import kanban_complete
        
        kanban_complete(
            output=output,
            silent=True  # No Telegram message
        )
        print("✓ Kanban task completed (silent)")
        
    except ImportError:
        print("⚠ Kanban module not available (standalone mode)")
    
    # Always save to shared state
    save_to_shared_state(output)


def save_to_shared_state(output: Dict):
    """Save to shared state for Orchestrator"""
    state_dir = Path(__file__).parent / 'state'
    state_dir.mkdir(exist_ok=True)
    
    state_file = state_dir / 'shared_state.json'
    
    with open(state_file, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"✓ Shared state saved: {state_file}")


# ============================================================================
# CLI
# ============================================================================

if __name__ == '__main__':
    output = run_data_collection_cycle()
    
    # Save to shared state
    save_to_shared_state(output)
    
    # Try to complete Kanban task
    complete_kanban_task(output)
    
    print("\n" + "="*70)
    print("Next cycle: 5 minutes")
    print("="*70)
