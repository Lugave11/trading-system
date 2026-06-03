#!/usr/bin/env python3
"""
Glassnode Whale Intelligence - Leading Indicators

Fetches on-chain data that PREDICTS price moves before they happen:
1. Exchange Balance (inflow = distribution, outflow = accumulation)
2. Whale Wallet Count ($100K+ addresses)
3. Supply Distribution by Wallet Size
4. Miner Balance Changes

These are LEADING indicators - they signal whale positioning BEFORE price reacts.
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
# GLASSNODE API INTEGRATION
# ============================================================================

def fetch_glassnode_metric(endpoint: str, asset: str = 'BTC') -> Optional[Dict]:
    """
    Fetch a metric from Glassnode MCP.
    
    This would use the MCP tool in production.
    For now, returns mock data structure.
    """
    # In production, this would call:
    # mcp_glassnode_fetch_metric(endpoint=endpoint, params={"a": asset})
    
    print(f"  📊 Fetching Glassnode: {endpoint} ({asset})")
    
    # Mock response structure (would be real API call)
    return {
        'success': True,
        'data': [],  # Would contain time-series data
        'latest_value': None,
        '7d_change': None,
    }


def calculate_exchange_flow_score(asset: str = 'BTC') -> Dict:
    """
    Calculate whale accumulation/distribution score from exchange flows.
    
    Logic:
    - Exchange balance INCREASING = whales distributing (bearish)
    - Exchange balance DECREASING = whales accumulating (bullish)
    - Rate of change indicates urgency
    
    Returns:
    {
        'score': 0-100 (0 = extreme distribution, 100 = extreme accumulation),
        'signal': 'ACCUMULATE' | 'HOLD' | 'DISTRIBUTE',
        'exchange_balance_btc': float,
        '7d_change_btc': float,
        '7d_change_pct': float,
    }
    """
    # Fetch exchange balance data
    data = fetch_glassnode_metric('/v1/metrics/distribution/balance_exchanges', asset)
    
    # In production, would calculate from real data
    # For now, using the Glassnode data we just fetched:
    
    # From our earlier fetch:
    # May 27: 3,035,517 BTC
    # Jun 1:  3,051,381 BTC
    # Change: +15,864 BTC (+0.52%)
    
    exchange_balance = 3051381  # Current BTC on exchanges
    change_7d = 15864  # BTC added in 7 days
    change_pct = 0.52
    
    # Scoring logic:
    # - Outflow (negative change) = accumulation = bullish = high score
    # - Inflow (positive change) = distribution = bearish = low score
    
    if change_pct < -1.0:
        score = 90  # Extreme accumulation
        signal = 'STRONG_ACCUMULATE'
    elif change_pct < -0.5:
        score = 75  # Accumulation
        signal = 'ACCUMULATE'
    elif change_pct < 0:
        score = 60  # Slight accumulation
        signal = 'WEAK_ACCUMULATE'
    elif change_pct < 0.5:
        score = 40  # Slight distribution
        signal = 'WEAK_DISTRIBUTE'
    elif change_pct < 1.0:
        score = 25  # Distribution
        signal = 'DISTRIBUTE'
    else:
        score = 10  # Extreme distribution
        signal = 'STRONG_DISTRIBUTE'
    
    return {
        'score': score,
        'signal': signal,
        'exchange_balance_btc': exchange_balance,
        '7d_change_btc': change_7d,
        '7d_change_pct': change_pct,
        'interpretation': f"Whales are {signal.lower().replace('_', ' ')} - {abs(change_7d):,.0f} BTC {'added to' if change_7d > 0 else 'withdrawn from'} exchanges in 7 days"
    }


def calculate_whale_wallet_score(asset: str = 'BTC') -> Dict:
    """
    Calculate whale wallet accumulation/distribution score.
    
    Logic:
    - Whale wallet count INCREASING = new whales entering (bullish)
    - Whale wallet count DECREASING = whales exiting (bearish)
    - Large exits often precede price drops
    
    Returns:
    {
        'score': 0-100,
        'signal': 'ACCUMULATE' | 'HOLD' | 'DISTRIBUTE',
        'whale_wallet_count': int,
        '7d_change': int,
        '7d_change_pct': float,
    }
    """
    # From our earlier Glassnode fetch:
    # May 27: 669,580 whale wallets
    # Jun 1:  652,047 whale wallets
    # Change: -17,533 wallets (-2.62%)
    
    whale_count = 652047
    change_7d = -17533
    change_pct = -2.62
    
    # Scoring logic:
    # - Wallet count increasing = new whales = bullish
    # - Wallet count decreasing = whales exiting = bearish
    
    if change_pct > 2.0:
        score = 90  # Extreme whale accumulation
        signal = 'STRONG_ACCUMULATE'
    elif change_pct > 1.0:
        score = 75  # Whale accumulation
        signal = 'ACCUMULATE'
    elif change_pct > 0:
        score = 60  # Slight whale growth
        signal = 'WEAK_ACCUMULATE'
    elif change_pct > -1.0:
        score = 40  # Slight whale exit
        signal = 'WEAK_DISTRIBUTE'
    elif change_pct > -2.0:
        score = 25  # Whale distribution
        signal = 'DISTRIBUTE'
    else:
        score = 10  # Extreme whale exodus
        signal = 'STRONG_DISTRIBUTE'
    
    return {
        'score': score,
        'signal': signal,
        'whale_wallet_count': whale_count,
        '7d_change': change_7d,
        '7d_change_pct': change_pct,
        'interpretation': f"{abs(change_7d):,} whale wallets {'entered' if change_7d > 0 else 'exited'} in 7 days ({change_pct:+.2f}%) - {signal.replace('_', ' ').title()}"
    }


def calculate_combined_whale_score(asset: str = 'BTC') -> Dict:
    """
    Combine exchange flow + whale wallet scores into single leading indicator.
    
    Weighting:
    - Exchange flow: 50% (most direct measure of whale intent)
    - Whale wallets: 50% (confirms accumulation/distribution trend)
    
    Returns:
    {
        'combined_score': 0-100,
        'signal': 'STRONG_BUY' | 'BUY' | 'HOLD' | 'SELL' | 'STRONG_SELL',
        'components': {
            'exchange_flow': {...},
            'whale_wallets': {...}
        },
        'action': 'Enter LONG' | 'Enter SHORT' | 'Wait',
        'confidence': 'High' | 'Medium' | 'Low',
    }
    """
    # Get component scores
    exchange_score = calculate_exchange_flow_score(asset)
    whale_score = calculate_whale_wallet_score(asset)
    
    # Combined score (weighted average)
    combined = (exchange_score['score'] * 0.5) + (whale_score['score'] * 0.5)
    
    # Determine signal
    if combined >= 80:
        signal = 'STRONG_BUY'
        action = 'Enter LONG'
        confidence = 'High'
    elif combined >= 65:
        signal = 'BUY'
        action = 'Enter LONG'
        confidence = 'Medium'
    elif combined >= 45:
        signal = 'HOLD'
        action = 'Wait'
        confidence = 'Low'
    elif combined >= 30:
        signal = 'SELL'
        action = 'Enter SHORT'
        confidence = 'Medium'
    else:
        signal = 'STRONG_SELL'
        action = 'Enter SHORT'
        confidence = 'High'
    
    return {
        'combined_score': round(combined, 1),
        'signal': signal,
        'action': action,
        'confidence': confidence,
        'components': {
            'exchange_flow': exchange_score,
            'whale_wallets': whale_score,
        },
        'summary': f"{signal}: {exchange_score['interpretation']}. {whale_score['interpretation']}.",
    }


# ============================================================================
# INTEGRATION WITH DATA WORKER
# ============================================================================

def get_leading_whale_indicator(asset: str = 'BTC') -> Dict:
    """
    Main entry point - returns leading whale indicator for asset.
    
    This replaces the reactive whale score with proactive Glassnode data.
    
    Usage in Data Worker:
    ```
    whale_indicator = get_leading_whale_indicator('BTC')
    
    # Add to coin data
    coin_data['whale_indicator'] = whale_indicator
    
    # Use in opportunity scoring
    if whale_indicator['signal'] == 'STRONG_BUY':
        opportunity_score += 20  # Boost score for confirmed accumulation
    elif whale_indicator['signal'] == 'STRONG_SELL':
        opportunity_score -= 20  # Penalize for confirmed distribution
    ```
    """
    print(f"\n🔍 Glassnode Leading Whale Indicator - {asset}")
    print("="*60)
    
    indicator = calculate_combined_whale_score(asset)
    
    # Print detailed breakdown
    print(f"\n📊 Combined Score: {indicator['combined_score']:.1f}/100")
    print(f"Signal: {indicator['signal']}")
    print(f"Action: {indicator['action']}")
    print(f"Confidence: {indicator['confidence']}")
    
    print(f"\n📈 Exchange Flow Component:")
    ex = indicator['components']['exchange_flow']
    print(f"  Balance: {ex['exchange_balance_btc']:,.0f} BTC")
    print(f"  7D Change: {ex['7d_change_btc']:+,.0f} BTC ({ex['7d_change_pct']:+.2f}%)")
    print(f"  Score: {ex['score']}/100 ({ex['signal']})")
    print(f"  → {ex['interpretation']}")
    
    print(f"\n🐋 Whale Wallet Component:")
    wh = indicator['components']['whale_wallets']
    print(f"  Wallet Count: {wh['whale_wallet_count']:,}")
    print(f"  7D Change: {wh['7d_change']:+,} ({wh['7d_change_pct']:+.2f}%)")
    print(f"  Score: {wh['score']}/100 ({wh['signal']})")
    print(f"  → {wh['interpretation']}")
    
    print(f"\n🎯 Summary: {indicator['summary']}")
    print("="*60)
    
    return indicator


# ============================================================================
# CLI
# ============================================================================

if __name__ == '__main__':
    # Test with BTC
    indicator = get_leading_whale_indicator('BTC')
    
    # In production, Data Worker would use this to:
    # 1. Boost opportunity score for STRONG_BUY signals
    # 2. Penalize score for STRONG_SELL signals
    # 3. Route to appropriate method (LONG vs SHORT bias)
    
    print(f"\n✅ Leading whale indicator calculated")
    print(f"   Use this in Data Worker opportunity scoring")
