#!/usr/bin/env python3
"""
Data Worker - Coin Discovery Specialist

This Data Worker does NOT collect data for assigned coins.
Instead, it DISCOVERS coins by scanning the market and presenting
the top 3-5 opportunities to the Orchestrator.

Flow:
1. Orchestrator creates Kanban task: "Discover Coins"
2. Data Worker scans 15 candidates
3. Calculates opportunity scores (volume + volatility + whale)
4. Ranks and selects top 3-5 (score >= 50)
5. Collects detailed OHLCV + indicators for selected coins
6. Reports back to Orchestrator via kanban_complete()

Separation of Concerns:
- Data Worker: Research & Discovery (WHAT to trade)
- Orchestrator: Decision Making (HOW to trade it)
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

# Candidate coins to scan (comprehensive list)
CANDIDATE_COINS = [
    'BTC', 'ETH', 'SOL',      # Majors - always scan
    'BNB', 'XRP', 'ADA',      # Large cap
    'AVAX', 'MATIC', 'DOT',   # Mid cap
    'LINK', 'UNI', 'ATOM',    # DeFi
    'DOGE', 'LTC', 'BCH',     # Legacy/Meme
]

# Selection thresholds
MIN_OPPORTUNITY_SCORE = 50   # Minimum score to qualify
MAX_COINS_TO_SELECT = 5      # Return top 5 max

# Volume thresholds for scoring
MIN_VOLUME_USD = 5_000_000   # $5M minimum for consideration
HIGH_VOLUME_USD = 50_000_000 # $50M+ = high volume bonus

# Whale detection
WHALE_VOLUME_THRESHOLD = 100_000  # $100K+ transfers

# Glassnode leading indicator thresholds
GLASSNODE_STRONG_BUY = 80    # Score >= 80: STRONG_BUY
GLASSNODE_BUY = 65           # Score >= 65: BUY
GLASSNODE_HOLD = 45          # Score >= 45: HOLD
GLASSNODE_SELL = 30          # Score >= 30: SELL
# Below 30: STRONG_SELL

# Score adjustment based on Glassnode signal
GLASSNODE_SCORE_BOOST = 20   # STRONG_BUY: +20 pts
GLASSNODE_BOOST = 15         # BUY: +15 pts
GLASSNODE_PENALTY = -30      # SELL: -30 pts (heavy penalty)
GLASSNODE_STRONG_PENALTY = -100  # STRONG_SELL: -100 pts (HARD BLOCK)

# Glassnode bias flags
BIAS_LONG = 'LONG'
BIAS_NEUTRAL = 'NEUTRAL'
BIAS_SHORT = 'SHORT'
BIAS_BLOCK_LONG = 'BLOCK_LONG'  # Hard block on LONG positions

# Global Glassnode signal (set by scan_all_candidates, used by run_coin_discovery)
glassnode_signal = None


# ============================================================================
# GLASSNODE INTEGRATION (REPLACED WITH ETHERSCAN)
# ============================================================================

def get_glassnode_signal(asset: str = 'ETH') -> Optional[Dict]:
    """
    Fetch Etherscan leading whale indicator for asset.
    
    REPLACED: Glassnode with Etherscan V2 API
    
    Analyzes:
    1. Exchange flows (inflow/outflow)
    2. Whale wallet activity
    3. On-chain momentum
    
    Returns:
    {
        'combined_score': 75.0,
        'signal': 'BUY',
        'action': 'Enter LONG',
        'confidence': 'High',
        'bias': 'LONG',  # LONG, NEUTRAL, SHORT, BLOCK_LONG
        'score_adjustment': +15,  # Points to add/subtract from opportunity score
        'allow_long': True,
        'allow_short': False,
    }
    """
    # Import Etherscan analyzer
    from etherscan_onchain_analysis import EtherscanAnalyzer
    
    analyzer = EtherscanAnalyzer()
    
    # Get leading indicator
    result = analyzer.get_leading_indicator(asset)
    
    # Convert to Glassnode-compatible format
    return {
        'combined_score': result['combined_score'],
        'signal': result['signal'],
        'action': f"Enter {result['bias']}" if result['bias'] != 'BLOCK_LONG' else "BLOCK LONG",
        'confidence': 'High' if result['combined_score'] > 70 else 'Medium' if result['combined_score'] > 40 else 'Low',
        'bias': result['bias'],
        'score_adjustment': result['score_adjustment'],
        'allow_long': result['allow_long'],
        'allow_short': result['allow_short'],
        'exchange_flow': result['exchange_flow'],
        'whale_wallets': result['whale_wallets'],
    }

# ============================================================================
# COIN SCANNING
# ============================================================================

def scan_all_candidates() -> List[Dict]:
    """
    Scan all 15 candidate coins and calculate opportunity scores.
    
    NEW: Fetches Glassnode leading indicator once, applies to all coins.
    
    Returns list of all candidates with scores (not filtered).
    """
    print(f"\n🔍 Scanning {len(CANDIDATE_COINS)} candidate coins...")
    
    # Fetch Glassnode leading indicator ONCE (applies to all coins)
    global glassnode_signal
    glassnode_signal = get_glassnode_signal('BTC')
    
    candidates = []
    
    for symbol in CANDIDATE_COINS:
        try:
            # Fetch 24h ticker from Binance.US
            url = f"https://api.binance.us/api/v3/ticker/24hr?symbol={symbol}USDT"
            
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())
            
            # Extract metrics
            volume_24h = float(data.get('quoteVolume', 0))
            price_change_pct = float(data.get('priceChangePercent', 0))
            current_price = float(data.get('lastPrice', 0))
            
            # Calculate component scores
            volume_score = calculate_volume_score(volume_24h)
            volatility_score = calculate_volatility_score(abs(price_change_pct))
            whale_score = calculate_whale_score(volume_24h, abs(price_change_pct))
            news_score = 50  # Neutral (would integrate RSS in production)
            
            # Calculate base weighted score
            base_score = (
                volume_score * 0.4 +      # 40% weight
                volatility_score * 0.3 +  # 30% weight
                whale_score * 0.2 +       # 20% weight
                news_score * 0.1          # 10% weight
            )
            
            # Apply Glassnode adjustment (NEW)
            score_adjustment = glassnode_signal.get('score_adjustment', 0) if glassnode_signal else 0
            total_score = max(0, min(100, base_score + score_adjustment))  # Clamp to 0-100
            
            # Check if LONG positions are blocked (HARD BLOCK for STRONG_SELL)
            allow_long = glassnode_signal.get('allow_long', True) if glassnode_signal else True
            if not allow_long:
                # Force score to 0 - this coin cannot be selected for LONG
                total_score = 0
                block_reason = 'Glassnode BLOCK_LONG'
            else:
                block_reason = None
            
            candidates.append({
                'symbol': symbol,
                'price': current_price,
                'volume_24h': volume_24h,
                'volatility_pct': abs(price_change_pct),
                'price_change_pct': price_change_pct,
                'scores': {
                    'volume': round(volume_score, 1),
                    'volatility': round(volatility_score, 1),
                    'whale': round(whale_score, 1),
                    'news': round(news_score, 1),
                    'base': round(base_score, 1),  # Before Glassnode adjustment
                    'adjustment': score_adjustment,  # Glassnode adjustment
                    'total': round(total_score, 1),  # After adjustment
                },
                'bias': glassnode_signal.get('bias', BIAS_NEUTRAL) if glassnode_signal else BIAS_NEUTRAL,
                'glassnode_signal': glassnode_signal.get('signal', 'UNKNOWN') if glassnode_signal else 'UNKNOWN',
                'allow_long': allow_long,
                'block_reason': block_reason,
                'rank': 0,  # Will be set after sorting
            })
            
            # Log progress
            status = "✓" if total_score >= MIN_OPPORTUNITY_SCORE else " "
            adj_str = f" ({score_adjustment:+d})" if score_adjustment != 0 else ""
            block_str = f" | 🚫 BLOCKED" if not allow_long else ""
            print(f"  {status} {symbol}: Score {total_score:.1f}{adj_str}{block_str} | " +
                  f"Vol: ${volume_24h/1e6:.1f}M | " +
                  f"Change: {price_change_pct:+.2f}% | " +
                  f"Whale: {whale_score:.0f} | " +
                  f"Bias: {glassnode_signal.get('bias', 'N/A') if glassnode_signal else 'N/A'}")
            
        except Exception as e:
            print(f"  ✗ {symbol}: Error - {e}")
            continue
    
    return candidates


def calculate_volume_score(volume_24h: float) -> float:
    """
    Calculate volume score (40% of total).
    
    Scoring:
    - $5M = 40 pts (minimum threshold)
    - $50M+ = 100 pts (excellent liquidity)
    """
    # $5M = 40 pts, $50M = 100 pts
    score = (volume_24h / MIN_VOLUME_USD) * 40
    return min(100, score)


def calculate_volatility_score(volatility_pct: float) -> float:
    """
    Calculate volatility score (30% of total).
    
    Scoring:
    - 1.5% = 30 pts (low volatility)
    - 5.0% = 100 pts (high volatility - max score)
    """
    # 5% move = 100 pts
    score = volatility_pct * 20
    return min(100, score)


def calculate_whale_score(volume_24h: float, volatility_pct: float) -> float:
    """
    Calculate whale activity score (20% of total).
    
    Scoring:
    - Base: 50 pts (neutral)
    - Volume >$50M: +20 pts (institutional activity)
    - Move >5%: +15 pts (whale-driven price action)
    - Maximum: 85 pts
    """
    score = 50  # Base neutral
    
    if volume_24h > HIGH_VOLUME_USD:
        score += 20  # High volume = whale activity
    
    if volatility_pct > 5:
        score += 15  # Big move = whale-driven
    
    return min(85, score)


# ============================================================================
# COIN SELECTION
# ============================================================================

def select_top_coins(candidates: List[Dict]) -> List[Dict]:
    """
    Rank candidates by total score and select top 3-5.
    
    Filtering:
    1. Only coins with score >= 50 (minimum opportunity threshold)
    2. Sort by total score (highest first)
    3. Return top 5 (or fewer if market is quiet)
    """
    print(f"\n📊 Ranking coins by opportunity score...")
    
    # Sort by total score (descending)
    candidates.sort(key=lambda x: x['scores']['total'], reverse=True)
    
    # Assign ranks
    for i, coin in enumerate(candidates):
        coin['rank'] = i + 1
    
    # Filter by minimum score
    qualified = [c for c in candidates if c['scores']['total'] >= MIN_OPPORTUNITY_SCORE]
    
    # Select top N
    selected = qualified[:MAX_COINS_TO_SELECT]
    
    print(f"\n📋 Top {len(selected)} coins selected:")
    for i, coin in enumerate(selected, 1):
        print(f"  #{i}: {coin['symbol']} (score: {coin['scores']['total']:.1f})")
    
    if len(qualified) == 0:
        print("  ⚠ No coins met minimum score threshold (50)")
    
    return selected


# ============================================================================
# DETAILED DATA COLLECTION
# ============================================================================

def fetch_ohlcv(symbol: str, timeframe: str = '5m', limit: int = 100) -> Optional[List[Dict]]:
    """
    Fetch OHLCV candles from Binance.US.
    
    Returns list of candles with timestamp, open, high, low, close, volume.
    """
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
        print(f"    ✗ {symbol} OHLCV error: {e}")
        return None


def calculate_indicators(candles: List[Dict]) -> Dict:
    """
    Calculate technical indicators from OHLCV data.
    
    Indicators:
    - RSI (14): Relative Strength Index
    - EMA20: Exponential Moving Average (20 periods)
    - Volume Ratio: Current volume vs 20-period average
    - ATR%: Average True Range as % of price (volatility)
    - Trend: Bullish/Bearish based on price vs EMA20
    """
    if len(candles) < 50:
        return {'error': 'Insufficient data', 'rsi': 50, 'trend': 'neutral'}
    
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
    
    # EMA20 (simple average for now - would calculate properly in production)
    ema20 = sum(closes[-20:]) / 20
    
    # Volume Ratio
    avg_volume = sum(volumes[-20:]) / 20
    volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 1
    
    # ATR (14) - volatility measure
    tr_list = []
    for i in range(1, min(15, len(candles))):
        high = candles[i]['high']
        low = candles[i]['low']
        prev_close = candles[i-1]['close']
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_list.append(tr)
    atr = sum(tr_list) / len(tr_list) if tr_list else 0
    atr_pct = (atr / closes[-1]) * 100
    
    # Trend
    current_price = closes[-1]
    trend = 'bullish' if current_price > ema20 else 'bearish' if current_price < ema20 else 'neutral'
    
    return {
        'rsi': round(rsi, 2),
        'ema20': round(ema20, 2),
        'volume_ratio': round(volume_ratio, 2),
        'atr_pct': round(atr_pct, 2),
        'current_price': round(current_price, 2),
        'trend': trend,
    }


def collect_detailed_data(coins: List[Dict]) -> List[Dict]:
    """
    For each selected coin, collect detailed OHLCV and indicators.
    
    This is the "research report" we present to the Orchestrator.
    """
    print(f"\n📈 Collecting detailed data for {len(coins)} selected coins...")
    
    enriched_coins = []
    
    for coin in coins:
        symbol = coin['symbol']
        print(f"\n  Fetching {symbol}...")
        
        # Fetch OHLCV
        candles = fetch_ohlcv(symbol, timeframe='5m', limit=100)
        
        if not candles:
            print(f"    ✗ Failed to fetch OHLCV")
            continue
        
        # Calculate indicators
        indicators = calculate_indicators(candles)
        
        # Enrich coin data
        enriched = {
            **coin,  # Copy existing data (symbol, price, scores, etc.)
            'ohlcv': {
                'success': True,
                'timeframe': '5m',
                'candles_count': len(candles),
                'candles': candles[-50:],  # Last 50 for strategy
                'indicators': indicators,
            },
        }
        
        enriched_coins.append(enriched)
        
        print(f"    ✓ {symbol}: RSI {indicators['rsi']:.1f} | " +
              f"Vol ratio {indicators['volume_ratio']:.2f}x | " +
              f"Trend: {indicators['trend']} | " +
              f"Price: ${indicators['current_price']:,.2f}")
    
    return enriched_coins


# ============================================================================
# MAIN DISCOVERY CYCLE
# ============================================================================

def run_coin_discovery():
    """
    Main coin discovery cycle.
    
    This is called when Orchestrator creates a "Discover Coins" Kanban task.
    
    Returns complete discovery report for Orchestrator.
    """
    print("\n" + "="*70)
    print("DATA WORKER - Coin Discovery")
    print("="*70)
    print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    # Step 1: Scan all candidates
    candidates = scan_all_candidates()
    
    if not candidates:
        print("\n✗ Scan failed - no data retrieved")
        return {
            'success': False,
            'error': 'Scan failed - no data retrieved',
            'discovered_coins': [],
            'glassnode_signal': None,
            'action_required': 'HOLD',
            'bias': 'NEUTRAL',
            'selection_summary': {
                'coins_scanned': 0,
                'coins_qualified': 0,
                'top_coins': [],
            }
        }
    
    # Step 2: Select top coins
    selected = select_top_coins(candidates)
    
    if not selected:
        print("\n⚠ No coins met minimum criteria - market too quiet")
        return {
            'success': True,
            'discovered_coins': [],
            'glassnode_signal': glassnode_signal,  # Include even when no coins selected
            'action_required': 'EXIT' if glassnode_signal and glassnode_signal.get('signal') == 'STRONG_SELL' else 'HOLD',
            'bias': glassnode_signal.get('bias', 'NEUTRAL') if glassnode_signal else 'NEUTRAL',
            'selection_summary': {
                'coins_scanned': len(candidates),
                'coins_qualified': 0,
                'top_coins': [],
                'reason': 'No coins scored >= 50',
            }
        }
    
    # Step 3: Collect detailed data for selected coins
    enriched_coins = collect_detailed_data(selected)
    
    # Step 4: Build discovery report
    report = {
        'success': True,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'discovered_coins': enriched_coins,
        'all_candidates': candidates,  # Include full list for transparency
        'glassnode_signal': glassnode_signal,  # NEW: Include for exit decision
        'action_required': 'EXIT' if glassnode_signal and glassnode_signal.get('signal') == 'STRONG_SELL' else 'HOLD',  # NEW
        'selection_summary': {
            'coins_scanned': len(candidates),
            'coins_qualified': len(selected),
            'top_coins': [c['symbol'] for c in enriched_coins],
            'average_score': sum(c['scores']['total'] for c in enriched_coins) / len(enriched_coins) if enriched_coins else 0,
            'market_condition': 'active' if len(enriched_coins) >= 3 else 'quiet',
        },
        'scoring_criteria': {
            'volume_weight': 0.4,
            'volatility_weight': 0.3,
            'whale_weight': 0.2,
            'news_weight': 0.1,
            'min_score_threshold': MIN_OPPORTUNITY_SCORE,
            'max_coins_to_select': MAX_COINS_TO_SELECT,
        }
    }
    
    print(f"\n✅ Discovery complete: {len(enriched_coins)} coins presented to Orchestrator")
    print(f"   Top coin: {enriched_coins[0]['symbol']} (score: {enriched_coins[0]['scores']['total']:.1f})")
    print(f"   Market condition: {report['selection_summary']['market_condition']}")
    
    return report


# ============================================================================
# KANBAN INTEGRATION
# ============================================================================

def complete_discovery_task(report: Dict):
    """
    Complete Kanban task and report back to Orchestrator.
    
    This sends the discovery report back via kanban_complete().
    The Orchestrator will read this and make routing decisions.
    """
    try:
        from kanban import kanban_complete
        
        # Complete silently (internal task - no Gateway message)
        kanban_complete(
            output=report,
            silent=True  # No Telegram message - Orchestrator will report
        )
        print("\n✓ Kanban task completed (silent - reported to Orchestrator)")
        
    except ImportError:
        print("\n⚠ Kanban module not available (standalone mode)")
        print("   Report saved to discovery_report.json")
    
    # Always save report to file (for debugging/audit)
    save_report(report)


def save_report(report: Dict):
    """Save discovery report to file for audit trail."""
    report_dir = Path(__file__).parent / 'reports'
    report_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    report_file = report_dir / f'discovery_{timestamp}.json'
    
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"✓ Discovery report saved: {report_file}")


# ============================================================================
# CLI
# ============================================================================

if __name__ == '__main__':
    # Run discovery
    report = run_coin_discovery()
    
    # Complete Kanban task (report to Orchestrator)
    complete_discovery_task(report)
    
    print("\n" + "="*70)
    print("Discovery cycle complete")
    print("Next: Orchestrator will evaluate and route to methods")
    print("="*70)
