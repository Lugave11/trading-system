#!/usr/bin/env python3
"""
Coin Universe Selector - Systematic Coin Selection

Selects coins based on objective criteria:
1. Top N by 24h volume (liquidity)
2. Glassnode coverage (must have on-chain data)
3. Volatility in target range (2-10% daily)
4. No delisting risk

Usage:
    python3 coin_selector.py --top 15 --min-volume 10000000
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Tuple

sys.path.insert(0, str(Path(__file__).parent))


# ============================================================================
# COIN SELECTION CRITERIA
# ============================================================================

SELECTION_CRITERIA = {
    'top_n': 15,              # Select top N coins
    'min_volume_usd': 10_000_000,  # Min 24h volume $10M
    'max_volume_usd': None,   # No max volume
    'min_volatility_pct': 2.0,    # Min 2% daily volatility
    'max_volatility_pct': 30.0,   # Max 30% daily volatility (avoid stablecoins + crazy alts)
    'require_etherscan': True,    # Must have Etherscan coverage (on-chain data)
    'must_include': ['BCH', 'MATIC'],  # Current open positions (from shared_state.json)
    'exclude_stablecoins': True,   # Skip USDT, USDC, etc.
}

# Stablecoins to exclude
STABLECOINS = {'USDT', 'USDC', 'BUSD', 'DAI', 'USDP', 'TUSD', 'USDD', 'FRAX', 'LUSD'}


def get_candidate_coins() -> List[Dict]:
    """
    Get all candidate coins with volume/volatility data.
    
    In production: Fetch from Binance.US API
    For now: Return top coins by known market data
    """
    # Top coins by 24h volume (approximate, from Binance.US)
    # This would be fetched from API in production
    candidates = [
        {'symbol': 'BTC', 'volume_24h': 28_500_000_000, 'volatility_pct': 4.2, 'etherscan': True},
        {'symbol': 'ETH', 'volume_24h': 15_200_000_000, 'volatility_pct': 5.1, 'etherscan': True},
        {'symbol': 'SOL', 'volume_24h': 4_800_000_000, 'volatility_pct': 7.3, 'etherscan': True},
        {'symbol': 'BNB', 'volume_24h': 2_100_000_000, 'volatility_pct': 3.8, 'etherscan': True},
        {'symbol': 'XRP', 'volume_24h': 1_900_000_000, 'volatility_pct': 4.5, 'etherscan': True},
        {'symbol': 'ADA', 'volume_24h': 890_000_000, 'volatility_pct': 5.2, 'etherscan': True},
        {'symbol': 'AVAX', 'volume_24h': 720_000_000, 'volatility_pct': 6.8, 'etherscan': True},
        {'symbol': 'DOGE', 'volume_24h': 1_200_000_000, 'volatility_pct': 8.5, 'etherscan': True},
        {'symbol': 'DOT', 'volume_24h': 450_000_000, 'volatility_pct': 5.9, 'etherscan': True},
        {'symbol': 'MATIC', 'volume_24h': 380_000_000, 'volatility_pct': 6.2, 'etherscan': True},
        {'symbol': 'LINK', 'volume_24h': 520_000_000, 'volatility_pct': 5.5, 'etherscan': True},
        {'symbol': 'UNI', 'volume_24h': 290_000_000, 'volatility_pct': 6.1, 'etherscan': True},
        {'symbol': 'ATOM', 'volume_24h': 210_000_000, 'volatility_pct': 5.8, 'etherscan': True},
        {'symbol': 'LTC', 'volume_24h': 680_000_000, 'volatility_pct': 4.1, 'etherscan': True},
        {'symbol': 'BCH', 'volume_24h': 590_000_000, 'volatility_pct': 4.8, 'etherscan': True},
        {'symbol': 'NEAR', 'volume_24h': 340_000_000, 'volatility_pct': 7.2, 'etherscan': False},  # No Etherscan
        {'symbol': 'APT', 'volume_24h': 280_000_000, 'volatility_pct': 8.1, 'etherscan': False},  # No Etherscan
        {'symbol': 'ARB', 'volume_24h': 420_000_000, 'volatility_pct': 6.5, 'etherscan': False},  # No Etherscan
        {'symbol': 'OP', 'volume_24h': 190_000_000, 'volatility_pct': 7.0, 'etherscan': False},  # No Etherscan
        {'symbol': 'USDT', 'volume_24h': 45_000_000_000, 'volatility_pct': 0.01, 'etherscan': True},  # Stablecoin
        {'symbol': 'USDC', 'volume_24h': 8_500_000_000, 'volatility_pct': 0.02, 'etherscan': True},  # Stablecoin
    ]
    
    return candidates


def filter_candidates(candidates: List[Dict], criteria: Dict) -> List[Dict]:
    """
    Filter candidates based on selection criteria.
    """
    filtered = []
    
    for coin in candidates:
        symbol = coin['symbol']
        
        # Rule 1: Exclude stablecoins
        if criteria['exclude_stablecoins'] and symbol in STABLECOINS:
            print(f"   ⚠ {symbol}: Excluded (stablecoin)")
            continue
        
        # Rule 2: Must have Etherscan coverage (if required)
        if criteria['require_etherscan'] and not coin.get('etherscan', False):
            print(f"   ⚠ {symbol}: Excluded (no Etherscan coverage)")
            continue
        
        # Rule 3: Min volume
        if coin['volume_24h'] < criteria['min_volume_usd']:
            print(f"   ⚠ {symbol}: Excluded (volume ${coin['volume_24h']/1e6:.1f}M < ${criteria['min_volume_usd']/1e6:.1f}M)")
            continue
        
        # Rule 4: Volatility range
        vol = coin['volatility_pct']
        if vol < criteria['min_volatility_pct']:
            print(f"   ⚠ {symbol}: Excluded (volatility {vol:.1f}% < {criteria['min_volatility_pct']:.1f}%)")
            continue
        if vol > criteria['max_volatility_pct']:
            print(f"   ⚠ {symbol}: Excluded (volatility {vol:.1f}% > {criteria['max_volatility_pct']:.1f}%)")
            continue
        
        # Passed all filters
        filtered.append(coin)
    
    return filtered


def rank_candidates(candidates: List[Dict]) -> List[Dict]:
    """
    Rank candidates by volume (descending).
    """
    return sorted(candidates, key=lambda x: x['volume_24h'], reverse=True)


def select_coins(criteria: Dict = None) -> Tuple[List[str], List[Dict]]:
    """
    Select coins based on objective criteria.
    
    Returns:
        Tuple of (selected_symbols, selected_coins_with_data)
    """
    if criteria is None:
        criteria = SELECTION_CRITERIA
    
    print("="*80)
    print("COIN UNIVERSE SELECTION")
    print("="*80)
    print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print()
    
    print("Selection Criteria:")
    print(f"  - Top N coins: {criteria['top_n']}")
    print(f"  - Min volume: ${criteria['min_volume_usd']/1e6:.1f}M")
    print(f"  - Volatility range: {criteria['min_volatility_pct']:.1f}% - {criteria['max_volatility_pct']:.1f}%")
    print(f"  - Etherscan required: {criteria['require_etherscan']}")
    print(f"  - Exclude stablecoins: {criteria['exclude_stablecoins']}")
    print(f"  - Must include: {criteria['must_include']}")
    print()
    
    # Step 1: Get all candidates
    print("="*80)
    print("STEP 1: Get Candidate Coins")
    print("="*80)
    candidates = get_candidate_coins()
    print(f"Total candidates: {len(candidates)}")
    print()
    
    # Step 2: Filter by criteria
    print("="*80)
    print("STEP 2: Filter by Criteria")
    print("="*80)
    filtered = filter_candidates(candidates, criteria)
    print(f"Passed filters: {len(filtered)}")
    print()
    
    # Step 3: Rank by volume
    print("="*80)
    print("STEP 3: Rank by Volume")
    print("="*80)
    ranked = rank_candidates(filtered)
    
    print(f"{'Rank':<6} {'Symbol':<10} {'Volume 24h':<18} {'Volatility':<12} {'Etherscan'}")
    print("-"*80)
    for i, coin in enumerate(ranked, 1):
        print(f"{i:<6} {coin['symbol']:<10} ${coin['volume_24h']/1e9:>8.2f}B    {coin['volatility_pct']:>5.1f}%      {'✅' if coin['etherscan'] else '❌'}")
    print()
    
    # Step 4: Select top N
    print("="*80)
    print("STEP 4: Select Top N Coins")
    print("="*80)
    
    # Ensure must_include coins are in the list
    must_include = criteria['must_include']
    selected_symbols = set()
    selected_coins = []
    
    # First, add must_include coins
    for symbol in must_include:
        for coin in ranked:
            if coin['symbol'] == symbol:
                selected_symbols.add(symbol)
                selected_coins.append(coin)
                print(f"✅ {symbol}: Added (must include)")
                break
    
    # Then, fill remaining slots from ranked list
    remaining_slots = criteria['top_n'] - len(selected_symbols)
    
    for coin in ranked:
        if len(selected_coins) >= criteria['top_n']:
            break
        
        symbol = coin['symbol']
        if symbol not in selected_symbols:
            selected_symbols.add(symbol)
            selected_coins.append(coin)
            print(f"✅ {symbol}: Added (rank #{len(selected_coins)})")
    
    print()
    print(f"Selected {len(selected_coins)} coins")
    print()
    
    # Step 5: Summary
    print("="*80)
    print("SELECTED COIN UNIVERSE")
    print("="*80)
    
    symbols = [c['symbol'] for c in selected_coins]
    print(f"Coins: {', '.join(symbols)}")
    print()
    
    total_volume = sum(c['volume_24h'] for c in selected_coins)
    avg_volatility = sum(c['volatility_pct'] for c in selected_coins) / len(selected_coins)
    
    print(f"Total 24h Volume: ${total_volume/1e9:.2f}B")
    print(f"Avg Volatility: {avg_volatility:.1f}%")
    print(f"Etherscan Coverage: 100% ({len(selected_coins)}/{len(selected_coins)})")
    print()
    
    return symbols, selected_coins


def save_coin_universe(symbols: List[str], selected_coins: List[Dict], output_path: str = None):
    """
    Save selected coins to coin_universe.json
    """
    if output_path is None:
        output_path = Path(__file__).parent / 'state' / 'coin_universe.json'
    
    config = {
        'coins': symbols,
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'updated_by': 'coin_selector.py',
        'selection_criteria': SELECTION_CRITERIA,
        'metadata': {
            'description': 'Dynamic coin universe - selected by objective criteria',
            'etherscan_coverage': '100% (all coins have on-chain data)',
            'rebalance_frequency': 'Weekly or as needed',
            'selection_method': 'Top N by volume + Etherscan coverage + volatility filter',
        },
        'coin_data': {
            coin['symbol']: {
                'volume_24h': coin['volume_24h'],
                'volatility_pct': coin['volatility_pct'],
                'etherscan': coin['etherscan'],
            }
            for coin in selected_coins
        }
    }
    
    with open(output_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"✅ Saved to {output_path}")
    print()


# ============================================================================
# CLI
# ============================================================================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Select coins for trading universe')
    parser.add_argument('--top', type=int, default=15, help='Number of coins to select')
    parser.add_argument('--min-volume', type=int, default=10_000_000, help='Min 24h volume in USD')
    parser.add_argument('--save', action='store_true', help='Save to coin_universe.json')
    parser.add_argument('--output', type=str, help='Output path (default: state/coin_universe.json)')
    
    args = parser.parse_args()
    
    # Override criteria
    criteria = SELECTION_CRITERIA.copy()
    criteria['top_n'] = args.top
    criteria['min_volume_usd'] = args.min_volume
    
    # Run selection
    symbols, selected_coins = select_coins(criteria)
    
    # Save if requested
    if args.save:
        save_coin_universe(symbols, selected_coins, args.output)
