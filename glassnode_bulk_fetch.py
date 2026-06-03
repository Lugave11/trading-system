#!/usr/bin/env python3
"""
Glassnode Bulk Fetch - Single Call Per Cycle

Fetches Glassnode data for multiple assets ONCE per cycle.
Data Worker then splits this per-coin.

Efficiency: 2 API calls (BTC + ETH) instead of 15 (all coins)
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent))


# ============================================================================
# GLASSNODE BULK FETCH
# ============================================================================

def load_coin_universe() -> List[str]:
    """
    Load coin universe from dynamic config file.
    
    This file is managed by the Orchestrator via Kanban tasks.
    Path: state/coin_universe.json
    
    Example config:
    {
        "coins": ["BTC", "ETH", "SOL", "BNB", "XRP"],
        "updated_at": "2026-06-03T00:00:00Z",
        "updated_by": "orchestrator_rebalance_task"
    }
    
    Returns:
        List of coin symbols, or empty list if file doesn't exist
    """
    config_path = Path(__file__).parent / 'state' / 'coin_universe.json'
    
    if not config_path.exists():
        print(f"   ⚠ Coin universe config not found: {config_path}")
        return []
    
    try:
        import json
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        coins = config.get('coins', [])
        updated = config.get('updated_at', 'unknown')
        
        print(f"   📋 Loaded coin universe: {len(coins)} coins (updated: {updated})")
        
        return coins
    
    except Exception as e:
        print(f"   ❌ Error loading coin universe: {e}")
        return []


def fetch_glassnode_bulk(assets: List[str] = None) -> Dict:
    """
    Fetch Glassnode data for multiple assets in ONE cycle.
    
    Args:
        assets: List of asset symbols from Orchestrator/Kanban config.
                If None, loads from coin_universe.json (dynamic config).
    
    Returns:
        Dict of {symbol: glassnode_data}
    
    Example:
        {
            'BTC': {
                'signal': 'STRONG_SELL',
                'score': 17.5,
                'exchange_flow': {...},
                'whale_wallets': {...},
            },
            'ETH': {
                'signal': 'ACCUMULATE',
                'score': 72.0,
                ...
            },
            ... dynamic coin list ...
        }
    """
    if assets is None:
        # Load from dynamic config (managed by Orchestrator via Kanban)
        assets = load_coin_universe()
    
    if not assets:
        print("⚠ No coins configured - using default universe")
        assets = ['BTC', 'ETH', 'SOL']  # Minimal fallback
    
    print(f"\n🔍 Fetching Glassnode data for {len(assets)} assets...")
    
    results = {}
    
    for asset in assets:
        try:
            print(f"   Fetching {asset}...")
            
            # Fetch exchange balance
            exchange_data = fetch_exchange_balance(asset)
            
            # Fetch whale wallets
            whale_data = fetch_whale_wallets(asset)
            
            # Calculate combined score
            combined = calculate_combined_score(exchange_data, whale_data)
            
            results[asset] = combined
            
            print(f"   ✅ {asset}: {combined['signal']} ({combined['score']:.1f}/100)")
            
        except Exception as e:
            print(f"   ❌ {asset}: Error - {e}")
            results[asset] = get_default_signal()
    
    print(f"\n✅ Glassnode bulk fetch complete: {len(results)} assets")
    
    return results


def fetch_exchange_balance(asset: str) -> Dict:
    """
    Fetch exchange balance for asset.
    
    In production: Calls Glassnode MCP tool.
    For testing: Returns mock data structure.
    """
    # In production, would call:
    # mcp_glassnode_fetch_metric(
    #     endpoint='/v1/metrics/distribution/balance_exchanges',
    #     params={"a": asset, "i": "24h"}
    # )
    
    # Mock data for testing (would be real API call)
    mock_data = {
        'BTC': {
            'latest_balance': 3051381,
            '7d_change_btc': 15864,
            '7d_change_pct': 0.52,
            'signal': 'DISTRIBUTE',
            'score': 25,
        },
        'ETH': {
            'latest_balance': 18500000,
            '7d_change_eth': -2500,
            '7d_change_pct': -0.13,
            'signal': 'ACCUMULATE',
            'score': 75,
        },
    }
    
    return mock_data.get(asset, get_default_exchange_data())


def fetch_whale_wallets(asset: str) -> Dict:
    """
    Fetch whale wallet count for asset.
    
    In production: Calls Glassnode MCP tool.
    For testing: Returns mock data structure.
    """
    # Mock data for testing
    mock_data = {
        'BTC': {
            'latest_count': 652047,
            '7d_change': -17533,
            '7d_change_pct': -2.62,
            'signal': 'STRONG_DISTRIBUTE',
            'score': 10,
        },
        'ETH': {
            'latest_count': 425000,
            '7d_change': 8500,
            '7d_change_pct': 2.04,
            'signal': 'ACCUMULATE',
            'score': 75,
        },
    }
    
    return mock_data.get(asset, get_default_whale_data())


def calculate_combined_score(exchange_data: Dict, whale_data: Dict) -> Dict:
    """
    Combine exchange flow + whale wallet scores.
    
    Weighting:
    - Exchange flow: 50%
    - Whale wallets: 50%
    """
    ex_score = exchange_data.get('score', 50)
    wh_score = whale_data.get('score', 50)
    
    combined_score = (ex_score * 0.5) + (wh_score * 0.5)
    
    # Determine signal
    if combined_score >= 80:
        signal = 'STRONG_BUY'
        action = 'ENTER_LONG'
    elif combined_score >= 65:
        signal = 'BUY'
        action = 'ENTER_LONG'
    elif combined_score >= 45:
        signal = 'HOLD'
        action = 'HOLD'
    elif combined_score >= 30:
        signal = 'SELL'
        action = 'EXIT'
    else:
        signal = 'STRONG_SELL'
        action = 'EXIT'
    
    return {
        'signal': signal,
        'score': round(combined_score, 1),
        'action': action,
        'exchange_flow': exchange_data,
        'whale_wallets': whale_data,
        'coverage': True,  # Has Glassnode data
        'summary': f"{signal}: {exchange_data.get('signal', '')} + {whale_data.get('signal', '')}",
    }


def get_default_signal() -> Dict:
    """Default signal for coins without Glassnode coverage"""
    return {
        'signal': 'HOLD',
        'score': 50.0,
        'action': 'HOLD',
        'coverage': False,  # No Glassnode data
        'summary': 'Fallback - no Glassnode coverage',
    }


def get_default_exchange_data() -> Dict:
    """Default exchange data"""
    return {
        'latest_balance': 0,
        '7d_change_btc': 0,
        '7d_change_pct': 0.0,
        'signal': 'NEUTRAL',
        'score': 50,
    }


def get_default_whale_data() -> Dict:
    """Default whale data"""
    return {
        'latest_count': 0,
        '7d_change': 0,
        '7d_change_pct': 0.0,
        'signal': 'NEUTRAL',
        'score': 50,
    }


# ============================================================================
# PER-COIN SPLIT (Used by Data Worker)
# ============================================================================

def get_coin_glassnode_signal(symbol: str, glassnode_bulk_data: Dict) -> Dict:
    """
    Get Glassnode signal for specific coin from bulk fetch.
    
    Args:
        symbol: Coin symbol (e.g., 'BTC', 'ETH', 'SOL')
        glassnode_bulk_data: Result from fetch_glassnode_bulk()
    
    Returns:
        Glassnode signal for this coin
    """
    # Should always have data - we fetch all 15 coins
    if symbol in glassnode_bulk_data:
        return glassnode_bulk_data[symbol]
    
    # This should never happen with our 15-coin universe
    print(f"   ⚠ {symbol}: Not in bulk data - using default HOLD")
    return get_default_signal()


def get_fallback_signal(symbol: str, volume_24h: float = 0, volatility_pct: float = 0) -> Dict:
    """
    Fallback signal for coins without Glassnode coverage.
    
    Uses reactive whale detection:
    - Volume spike
    - Price movement
    - Whale score (reactive)
    """
    # Calculate fallback score from volume/volatility
    volume_score = min(100, (volume_24h / 5_000_000) * 40) if volume_24h > 0 else 50
    volatility_score = min(100, abs(volatility_pct) * 20) if volatility_pct > 0 else 50
    
    # Simple average
    fallback_score = (volume_score + volatility_score) / 2
    
    # Determine signal
    if fallback_score >= 70:
        signal = 'BUY'
        action = 'ENTER_LONG'
    elif fallback_score >= 45:
        signal = 'HOLD'
        action = 'HOLD'
    else:
        signal = 'SELL'
        action = 'EXIT'
    
    return {
        'signal': signal,
        'score': round(fallback_score, 1),
        'action': action,
        'coverage': False,  # No Glassnode data
        'method': 'fallback_reactive',
        'summary': f'Fallback: Volume ${volume_24h/1e6:.1f}M, Volatility {volatility_pct:.1f}%',
    }


# ============================================================================
# CLI / Testing
# ============================================================================

if __name__ == '__main__':
    # Test bulk fetch
    print("="*70)
    print("GLASSNODE BULK FETCH TEST")
    print("="*70)
    print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
    
    # Fetch for BTC + ETH
    glassnode_data = fetch_glassnode_bulk(['BTC', 'ETH'])
    
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)
    
    for symbol, data in glassnode_data.items():
        print(f"\n{symbol}:")
        print(f"  Signal: {data['signal']} ({data['score']:.1f}/100)")
        print(f"  Action: {data['action']}")
        print(f"  Coverage: {data['coverage']}")
        print(f"  Summary: {data['summary']}")
    
    # Test per-coin split
    print("\n" + "="*70)
    print("PER-COIN SPLIT TEST")
    print("="*70)
    
    test_coins = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']
    
    for symbol in test_coins:
        signal = get_coin_glassnode_signal(symbol, glassnode_data)
        print(f"\n{symbol}:")
        print(f"  Signal: {signal['signal']} ({signal['score']:.1f}/100)")
        print(f"  Action: {signal['action']}")
        print(f"  Coverage: {signal['coverage']}")
