#!/usr/bin/env python3
"""
Orchestrator - Dynamic Coin Discovery & Routing

Every 15 minutes:
1. Discovers coins (scans market, ranks by opportunity)
2. Assigns top coins to Data Worker for collection
3. Evaluates collected data
4. Routes to best-fit method bots

No hardcoded lists - dynamically selects what to trade based on real-time conditions.
"""

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import sys

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent))

# ============================================================================
# CONFIGURATION
# ============================================================================

# Candidate coins to scan (not hardcoded to trade - just to scan)
CANDIDATE_COINS = [
    'BTC', 'ETH', 'SOL',      # Majors
    'BNB', 'XRP', 'ADA',      # Large cap
    'AVAX', 'MATIC', 'DOT',   # Mid cap
    'LINK', 'UNI', 'ATOM',    # DeFi
    'DOGE', 'LTC', 'BCH',     # Legacy
]

# Selection thresholds
MIN_OPPORTUNITY_SCORE = 50
MAX_COINS_TO_SELECT = 5

# Signal threshold
MIN_SIGNAL_SCORE = 60

# ============================================================================
# COIN DISCOVERY
# ============================================================================

def discover_coins() -> List[Dict]:
    """
    Scan Binance.US and rank coins by opportunity score.
    
    Scoring:
    - Volume (40%): Liquidity
    - Volatility (30%): Movement
    - Whale Activity (20%): Institutional interest
    - News (10%): Catalysts
    """
    print(f"\n🔍 Discovering coins... (scanning {len(CANDIDATE_COINS)} candidates)")
    
    ranked = []
    
    for symbol in CANDIDATE_COINS:
        try:
            # Fetch 24h ticker
            url = f"https://api.binance.us/api/v3/ticker/24hr?symbol={symbol}USDT"
            
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())
            
            volume_24h = float(data.get('quoteVolume', 0))
            price_change_pct = float(data.get('priceChangePercent', 0))
            current_price = float(data.get('lastPrice', 0))
            
            # Calculate scores
            volume_score = min(100, (volume_24h / 5_000_000) * 40)  # $5M = 40 pts
            volatility_score = min(100, abs(price_change_pct) * 20)  # 5% = 100 pts
            
            # Whale score
            whale_score = 50  # Base
            if volume_24h > 50_000_000:
                whale_score += 20
            if abs(price_change_pct) > 5:
                whale_score += 15
            
            # News score (simplified - would integrate RSS)
            news_score = 50  # Neutral
            
            # Total weighted score
            total_score = (
                volume_score * 0.4 +
                volatility_score * 0.3 +
                whale_score * 0.2 +
                news_score * 0.1
            )
            
            ranked.append({
                'symbol': symbol,
                'price': current_price,
                'volume_24h': volume_24h,
                'volatility_pct': abs(price_change_pct),
                'volume_score': round(volume_score, 1),
                'volatility_score': round(volatility_score, 1),
                'whale_score': round(whale_score, 1),
                'news_score': round(news_score, 1),
                'total_score': round(total_score, 1),
            })
            
            print(f"  {symbol}: Score {total_score:.1f} | Vol: ${volume_24h/1e6:.1f}M | Change: {price_change_pct:+.2f}%")
            
        except Exception as e:
            print(f"  ✗ {symbol}: Error - {e}")
            continue
    
    # Sort by total score
    ranked.sort(key=lambda x: x['total_score'], reverse=True)
    
    # Filter by minimum score
    qualified = [c for c in ranked if c['total_score'] >= MIN_OPPORTUNITY_SCORE]
    
    # Select top N
    selected = qualified[:MAX_COINS_TO_SELECT]
    
    print(f"\n📊 Top {len(selected)} coins selected for this cycle:")
    for i, coin in enumerate(selected, 1):
        print(f"  #{i}: {coin['symbol']} (score: {coin['total_score']:.1f})")
    
    return selected


# ============================================================================
# METHOD SCORING
# ============================================================================

def calculate_mean_reversion_score(indicators: Dict, whale_score: float) -> float:
    """
    Score mean reversion opportunity (0-100).
    
    Best when:
    - RSI 35-65 (range-bound)
    - RSI <30 or >70 (oversold/overbought)
    - Price extended from EMA20
    - Normal volume (not spike)
    """
    score = 0
    
    rsi = indicators.get('rsi', 50)
    ema20 = indicators.get('ema20', 0)
    price = indicators.get('current_price', 0)
    volume_ratio = indicators.get('volume_ratio', 1)
    
    # RSI scoring
    if 35 <= rsi <= 65:
        score += 40  # Range-bound
    elif rsi < 30 or rsi > 70:
        score += 35  # Oversold/overbought
    
    # Price extension from EMA20
    if ema20 > 0:
        extension = abs(price - ema20) / ema20 * 100
        if extension > 5:
            score += 35  # Extended
    
    # Volume (normal is good for mean reversion)
    if 0.8 <= volume_ratio <= 1.5:
        score += 25  # Normal volume
    
    # Whale bonus
    score += (whale_score - 50) * 0.2
    
    return min(100, score)


def calculate_momentum_score(indicators: Dict, whale_score: float) -> float:
    """
    Score momentum opportunity (0-100).
    
    Best when:
    - RSI 55-70 + bullish trend
    - RSI 30-45 + bearish trend
    - Price extended from EMA20
    - MACD confirms trend
    """
    score = 0
    
    rsi = indicators.get('rsi', 50)
    trend = indicators.get('trend', 'neutral')
    ema20 = indicators.get('ema20', 0)
    price = indicators.get('current_price', 0)
    
    # RSI + trend alignment
    if trend == 'bullish' and 55 <= rsi <= 70:
        score += 40
    elif trend == 'bearish' and 30 <= rsi <= 45:
        score += 40
    
    # Price extension
    if ema20 > 0:
        extension = abs(price - ema20) / ema20 * 100
        if extension > 3:
            score += 35
    
    # MACD (simplified - would calculate properly)
    # Assuming trend indicates MACD direction
    if trend != 'neutral':
        score += 25
    
    # Whale bonus
    score += (whale_score - 50) * 0.3
    
    return min(100, score)


def calculate_breakout_score(indicators: Dict, whale_score: float) -> float:
    """
    Score breakout opportunity (0-100).
    
    Best when:
    - Volume spike >3x
    - Price breaking consolidation
    - High whale activity
    """
    score = 0
    
    volume_ratio = indicators.get('volume_ratio', 1)
    
    # Volume spike
    if volume_ratio > 3:
        score += 50
    elif volume_ratio > 2:
        score += 35
    elif volume_ratio > 1.5:
        score += 20
    
    # Consolidation break (simplified - would detect ranges)
    # Assuming high volume indicates breakout
    
    # Whale activity
    if whale_score > 70:
        score += 30
    elif whale_score > 60:
        score += 20
    
    return min(100, score)


# ============================================================================
# MAIN CYCLE
# ============================================================================

def run_orchestrator_cycle():
    """Main orchestrator cycle"""
    print("\n" + "="*70)
    print("ORCHESTRATOR - Dynamic Coin Discovery & Routing")
    print("="*70)
    print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    # Step 1: Discover coins
    discovered = discover_coins()
    
    if not discovered:
        print("\n✗ No coins met opportunity criteria - market too quiet")
        return {
            'success': False,
            'coins_discovered': 0,
            'coins_assigned': 0,
            'decisions': [],
        }
    
    # Step 2: Select coins to assign
    selected = discovered[:MAX_COINS_TO_SELECT]
    selected_symbols = [c['symbol'] for c in selected]
    
    print(f"\n📋 Assigning {len(selected_symbols)} coins to Data Worker: {', '.join(selected_symbols)}")
    
    # Step 3: Read collected data from shared state
    # (In production, Data Worker would have just completed)
    state_file = Path(__file__).parent / 'state' / 'shared_state.json'
    
    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)
        
        coin_data_list = state.get('coin_data', [])
        print(f"\n📊 Read collected data for {len(coin_data_list)} coins")
    else:
        print("\n⚠ No shared state found - simulating data for demo")
        coin_data_list = []
        
        # Simulate data for selected coins
        for coin in selected:
            coin_data_list.append({
                'symbol': coin['symbol'],
                'ohlcv': {
                    'indicators': {
                        'rsi': 50 + (coin['volatility_pct'] * 2),  # Simulated
                        'ema20': coin['price'] * 0.99,
                        'current_price': coin['price'],
                        'volume_ratio': 1.0 + (coin['volume_score'] / 100),
                        'trend': 'bullish' if coin['volatility_pct'] > 2 else 'bearish',
                    }
                },
                'whale_score': coin['whale_score'],
            })
    
    # Step 4: Evaluate and route
    decisions = []
    
    print("\n🧠 Evaluating coins and routing to methods:")
    
    for coin_data in coin_data_list:
        symbol = coin_data['symbol']
        indicators = coin_data['ohlcv']['indicators']
        whale_score = coin_data['whale_score']
        
        # Calculate method scores
        mr_score = calculate_mean_reversion_score(indicators, whale_score)
        momentum_score = calculate_momentum_score(indicators, whale_score)
        breakout_score = calculate_breakout_score(indicators, whale_score)
        
        # Find best method
        scores = {
            'mean_reversion': mr_score,
            'momentum': momentum_score,
            'breakout': breakout_score,
        }
        
        best_method = max(scores, key=scores.get)
        best_score = scores[best_method]
        
        # Route if score >= threshold
        if best_score >= MIN_SIGNAL_SCORE:
            action = 'BUY'
            reason = f'{best_method} score {best_score:.0f} >= {MIN_SIGNAL_SCORE}'
        else:
            action = 'HOLD'
            reason = f'No method scored >= {MIN_SIGNAL_SCORE} (best: {best_method} {best_score:.0f})'
        
        decision = {
            'symbol': symbol,
            'action': action,
            'method': best_method if action == 'BUY' else None,
            'score': best_score,
            'scores': scores,
            'reason': reason,
        }
        
        decisions.append(decision)
        
        status = '✅' if action == 'BUY' else '⏳'
        print(f"  {status} {symbol}: {action} ({best_method} {best_score:.0f}) - {reason}")
    
    # Step 5: Build output
    output = {
        'success': True,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'discovery': {
            'coins_scanned': len(CANDIDATE_COINS),
            'coins_qualified': len(discovered),
            'coins_selected': len(selected),
            'selected_coins': selected_symbols,
        },
        'decisions': decisions,
        'summary': {
            'signals_generated': len([d for d in decisions if d['action'] == 'BUY']),
            'coins_evaluated': len(decisions),
        }
    }
    
    print(f"\n✅ Orchestrator cycle complete: {len(decisions)} evaluated, {output['summary']['signals_generated']} signals")
    
    return output


# ============================================================================
# KANBAN INTEGRATION
# ============================================================================

def complete_kanban_task(output: Dict):
    """Complete Kanban task silently (no Gateway message for 15-min cycles)"""
    try:
        from kanban import kanban_complete
        
        kanban_complete(
            output=output,
            silent=True  # No Telegram message
        )
        print("✓ Kanban task completed (silent)")
        
    except ImportError:
        print("⚠ Kanban module not available (standalone mode)")
    
    # Save to orchestrator state
    save_to_orchestrator_state(output)


def save_to_orchestrator_state(output: Dict):
    """Save orchestrator decisions"""
    state_dir = Path(__file__).parent / 'state'
    state_dir.mkdir(exist_ok=True)
    
    state_file = state_dir / 'orchestrator_latest.json'
    
    with open(state_file, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"✓ Orchestrator state saved: {state_file}")


# ============================================================================
# CLI
# ============================================================================

if __name__ == '__main__':
    output = run_orchestrator_cycle()
    
    # Save state
    save_to_orchestrator_state(output)
    
    # Complete Kanban task
    complete_kanban_task(output)
    
    print("\n" + "="*70)
    print("Next cycle: 15 minutes")
    print("="*70)
