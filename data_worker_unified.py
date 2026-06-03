#!/usr/bin/env python3
"""
Data Worker - Unified Integration

Combines ALL Data Worker functions into a single Kanban-driven worker:

1. **Coin Discovery** (data_worker_discovery.py)
   - Scans 15 candidate coins
   - Calculates opportunity scores (volume + volatility + whale + Glassnode)
   - Selects top 3-5 coins (score >= 50, not BLOCKED)

2. **Whale Tracking** (kanban_whale_tracker.py)
   - Scans TOP 10 tokens (ex-stablecoins)
   - Scans portfolio coins from coin_universe.json
   - Creates Kanban tasks for significant movements

3. **Glassnode Analysis** (glassnode_bulk_fetch.py)
   - Fetches on-chain metrics for all assigned coins
   - Calculates per-coin sentiment (EXIT/ENTER/HOLD)

4. **Technical Analysis** (momentum_bot.py, mean_reversion_bot.py)
   - Calculates RSI, MACD, Bollinger Bands
   - Generates method-specific signals

Workflow:
1. Orchestrator creates task: "🔍 Data Discovery"
2. Data Worker runs ALL 4 functions
3. Aggregates results into unified report
4. Creates Kanban tasks for significant findings
5. Completes task with comprehensive discovery report
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Add trading_system to path
sys.path.insert(0, '/mnt/data/hermes/workspace/trading_system')

# Import all Data Worker modules
from data_worker_discovery import (
    scan_all_candidates,
    CANDIDATE_COINS,
    MIN_OPPORTUNITY_SCORE,
    MAX_COINS_TO_SELECT,
)
from kanban_whale_tracker import KanbanWhaleTracker, KANBAN_THRESHOLDS
from glassnode_bulk_fetch import load_coin_universe

# Note: Glassnode replaced with Etherscan in data_worker_discovery.py
# get_glassnode_signal() now calls EtherscanAnalyzer internally

# Note: momentum_bot and mean_reversion_bot are execution-focused, not analysis
# They require Orchestrator decisions as input, so we skip them in discovery phase

# ===== CONFIGURATION =====

STATE_DIR = Path('/mnt/data/hermes/workspace/trading_system/state')
REPORTS_DIR = Path('/mnt/data/hermes/workspace/trading_system/whale_reports')
HERMES_CLI = '/mnt/data/hermes/workspace/.local/bin/hermes'


def load_orchestrator_task() -> Optional[Dict]:
    """
    Load the current Orchestrator task metadata.
    In production, this comes from Kanban task metadata.
    """
    # Check for task file (created by Orchestrator)
    task_file = STATE_DIR / 'current_task.json'
    
    if task_file.exists():
        with open(task_file, 'r') as f:
            return json.load(f)
    
    # Fallback: return default task
    return {
        'task_id': 't_default',
        'task_type': 'data_discovery',
        'coins': None,  # None = discover new coins
        'mode': 'discovery',  # 'discovery' or 'analysis'
    }


def run_coin_discovery() -> Dict:
    """
    Function 1: Coin Discovery
    Scans all 15 candidates and selects top 3-5 opportunities.
    """
    print("\n" + "="*80)
    print("FUNCTION 1: COIN DISCOVERY")
    print("="*80)
    
    # Scan all candidates
    candidates = scan_all_candidates()
    
    # Filter and rank
    qualified = [c for c in candidates if c['scores']['total'] >= MIN_OPPORTUNITY_SCORE and c['allow_long']]
    qualified.sort(key=lambda x: x['scores']['total'], reverse=True)
    
    # Select top N
    selected = qualified[:MAX_COINS_TO_SELECT]
    
    # Assign ranks
    for i, coin in enumerate(selected, 1):
        coin['rank'] = i
    
    print(f"\n📊 DISCOVERY RESULTS:")
    print(f"   Scanned: {len(candidates)} coins")
    print(f"   Qualified: {len(qualified)} (score >= {MIN_OPPORTUNITY_SCORE})")
    print(f"   Selected: {len(selected)} (top {MAX_COINS_TO_SELECT})")
    
    if selected:
        print(f"\n🎯 TOP {len(selected)} OPPORTUNITIES:")
        for coin in selected:
            print(f"   #{coin['rank']} {coin['symbol']}: {coin['scores']['total']:.1f} pts | "
                  f"Vol: ${coin['volume_24h']/1e6:.1f}M | "
                  f"Change: {coin['price_change_pct']:+.2f}% | "
                  f"Bias: {coin['bias']}")
    
    return {
        'scanned': len(candidates),
        'qualified': len(qualified),
        'selected': selected,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }


def run_whale_tracking() -> Dict:
    """
    Function 2: Whale Tracking
    Scans TOP 10 + Portfolio coins for whale movements.
    """
    print("\n" + "="*80)
    print("FUNCTION 2: WHALE TRACKING")
    print("="*80)
    
    tracker = KanbanWhaleTracker()
    
    # Get prices
    tracker.get_eth_price()
    print(f"\n📊 Prices: ETH ${tracker.eth_price:,.2f} | BTC ${tracker.token_prices['BTC']:,.0f}")
    
    # Scan
    print("\n   Scanning whale wallets...")
    top10_signals = tracker.scan_all_whales()
    portfolio_signals = tracker.scan_portfolio_wallets()
    
    # Combine and deduplicate
    all_signals = top10_signals + portfolio_signals
    seen_hashes = set()
    unique_signals = []
    for s in all_signals:
        if s['tx_hash'] not in seen_hashes:
            seen_hashes.add(s['tx_hash'])
            unique_signals.append(s)
    
    print(f"\n📊 WHALE RESULTS:")
    print(f"   Total signals: {len(unique_signals)}")
    
    # Count by type
    major = len([s for s in unique_signals if s['signal'] == 'MAJOR'])
    bearish = len([s for s in unique_signals if s['signal'] == 'BEARISH'])
    bullish = len([s for s in unique_signals if s['signal'] == 'BULLISH'])
    
    print(f"   Major: {major} | Bearish: {bearish} | Bullish: {bullish}")
    
    return {
        'signals': unique_signals,
        'counts': {
            'total': len(unique_signals),
            'major': major,
            'bearish': bearish,
            'bullish': bullish,
        },
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }


def run_glassnode_analysis(coins: List[str]) -> Dict:
    """
    Function 3: Etherscan On-Chain Analysis (REPLACED GLASSNODE)
    Fetches on-chain metrics for assigned coins using Etherscan V2 API.
    """
    print("\n" + "="*80)
    print("FUNCTION 3: ETHERSCAN ON-CHAIN ANALYSIS (Replaced Glassnode)")
    print("="*80)
    
    if not coins:
        print("   ⚠️  No coins assigned - skipping Etherscan analysis")
        return {'coins': [], 'signals': {}}
    
    print(f"\n📊 Analyzing {len(coins)} coins with Etherscan...")
    
    try:
        # Import Etherscan analyzer
        from etherscan_onchain_analysis import analyze_all_tokens
        
        # Fetch Etherscan data for all coins
        result = analyze_all_tokens(coins)
        
        if result['success']:
            print(f"\n✅ Etherscan analysis successful")
            print(f"   Coins analyzed: {len(result['data'])}")
            
            # Count by signal
            signal_counts = {}
            for coin, data in result['data'].items():
                sig = data['signal']
                signal_counts[sig] = signal_counts.get(sig, 0) + 1
            
            print(f"\n📊 SIGNAL BREAKDOWN:")
            for sig, count in sorted(signal_counts.items()):
                print(f"   {sig}: {count} coins")
            
            return {
                'coins': coins,
                'signals': result['data'],
                'success': True,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
        else:
            print(f"\n❌ Etherscan analysis failed: {result.get('error', 'Unknown error')}")
            return {
                'coins': coins,
                'signals': {},
                'success': False,
                'error': result.get('error'),
            }
    
    except Exception as e:
        print(f"\n❌ Etherscan error: {e}")
        return {
            'coins': coins,
            'signals': {},
            'success': False,
            'error': str(e),
        }


def run_technical_analysis_placeholder(coins: List[str]) -> Dict:
    """
    Function 4: Technical Analysis (Placeholder)
    
    Note: momentum_bot and mean_reversion_bot are execution-focused.
    They require Orchestrator decisions as input.
    
    In production, this would:
    - Calculate RSI, MACD, Bollinger Bands
    - Run momentum analysis
    - Run mean reversion analysis
    - Generate method-specific signals
    """
    print("\n" + "="*80)
    print("FUNCTION 4: TECHNICAL ANALYSIS (Placeholder)")
    print("="*80)
    
    if not coins:
        print("   ⚠️  No coins assigned - skipping TA")
        return {'signals': {}}
    
    print(f"\n📊 Technical analysis deferred to execution phase")
    print(f"   (momentum_bot and mean_reversion_bot require Orchestrator decisions)")
    print(f"   Coins queued for TA: {len(coins)}")
    
    return {
        'signals': {},
        'note': 'Technical analysis runs during execution phase, not discovery',
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }


def aggregate_results(discovery, whale, glassnode, technical) -> Dict:
    """
    Aggregate all 4 functions into unified report.
    """
    print("\n" + "="*80)
    print("AGGREGATING RESULTS")
    print("="*80)
    
    # Combine coin lists
    discovered_coins = [c['symbol'] for c in discovery.get('selected', [])]
    glassnode_coins = list(glassnode.get('signals', {}).keys())
    ta_coins = list(technical.get('signals', {}).keys())
    
    # Build unified coin analysis
    unified_coins = {}
    
    # Add discovered coins
    for coin_data in discovery.get('selected', []):
        symbol = coin_data['symbol']
        unified_coins[symbol] = {
            'symbol': symbol,
            'discovery_score': coin_data['scores']['total'],
            'discovery_rank': coin_data.get('rank', 0),
            'volume_24h': coin_data['volume_24h'],
            'price_change_pct': coin_data['price_change_pct'],
            'bias': coin_data.get('bias', 'NEUTRAL'),
            'glassnode_signal': glassnode.get('signals', {}).get(symbol, {}).get('signal', 'N/A'),
            'momentum_signal': technical.get('signals', {}).get(symbol, {}).get('momentum', {}).get('signal', 'N/A'),
            'mean_reversion_signal': technical.get('signals', {}).get(symbol, {}).get('mean_reversion', {}).get('signal', 'N/A'),
        }
    
    # Determine final recommendation per coin
    for symbol, data in unified_coins.items():
        signals = []
        
        # Discovery (opportunity score)
        if data['discovery_score'] >= 70:
            signals.append(('DISCOVERY', 'BULLISH', 0.4))
        elif data['discovery_score'] >= 50:
            signals.append(('DISCOVERY', 'NEUTRAL', 0.2))
        
        # Glassnode
        gn_signal = data['glassnode_signal']
        if gn_signal in ['STRONG_BUY', 'BUY']:
            signals.append(('GLASSNODE', 'BULLISH', 0.3))
        elif gn_signal in ['STRONG_SELL', 'SELL']:
            signals.append(('GLASSNODE', 'BEARISH', 0.3))
        
        # Technical (placeholder for now)
        data['momentum_signal'] = 'N/A (execution phase)'
        data['mean_reversion_signal'] = 'N/A (execution phase)'
        
        # Calculate final sentiment
        bullish_weight = sum(w for _, sig, w in signals if sig == 'BULLISH')
        bearish_weight = sum(w for _, sig, w in signals if sig == 'BEARISH')
        
        if bullish_weight > 0.6:
            final_signal = 'BULLISH'
            recommendation = 'ENTER_LONG'
        elif bearish_weight > 0.6:
            final_signal = 'BEARISH'
            recommendation = 'EXIT'
        else:
            final_signal = 'NEUTRAL'
            recommendation = 'HOLD'
        
        data['final_signal'] = final_signal
        data['recommendation'] = recommendation
        data['confidence'] = max(bullish_weight, bearish_weight)
    
    # Summary
    summary = {
        'total_coins_analyzed': len(unified_coins),
        'bullish_coins': len([c for c in unified_coins.values() if c['final_signal'] == 'BULLISH']),
        'bearish_coins': len([c for c in unified_coins.values() if c['final_signal'] == 'BEARISH']),
        'neutral_coins': len([c for c in unified_coins.values() if c['final_signal'] == 'NEUTRAL']),
        'whale_signals': whale.get('counts', {}),
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
    
    print(f"\n📊 UNIFIED RESULTS:")
    print(f"   Coins analyzed: {len(unified_coins)}")
    print(f"   Bullish: {summary['bullish_coins']}")
    print(f"   Bearish: {summary['bearish_coins']}")
    print(f"   Neutral: {summary['neutral_coins']}")
    
    return {
        'coins': unified_coins,
        'summary': summary,
        'discovery': discovery,
        'whale': whale,
        'glassnode': glassnode,
        'technical': technical,
    }


def run_unified_data_worker() -> Dict:
    """
    Main entry point - runs ALL 4 Data Worker functions.
    """
    print("="*80)
    print("UNIFIED DATA WORKER - ALL FUNCTIONS")
    print(f"Executed: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("="*80)
    
    # Load task from Orchestrator
    task = load_orchestrator_task()
    print(f"\n📋 Task: {task.get('task_id', 'N/A')}")
    print(f"   Type: {task.get('task_type', 'N/A')}")
    print(f"   Mode: {task.get('mode', 'discovery')}")
    print(f"   Assigned coins: {task.get('coins', 'None (discovery mode)')}")
    
    # Function 1: Coin Discovery (always runs)
    discovery = run_coin_discovery()
    
    # Get coin list for other functions
    if task.get('mode') == 'analysis' and task.get('coins'):
        # Use assigned coins
        coins_to_analyze = task['coins']
    else:
        # Use discovered coins
        coins_to_analyze = [c['symbol'] for c in discovery['selected']]
    
    print(f"\n📋 Coins for analysis: {', '.join(coins_to_analyze[:10])}{'...' if len(coins_to_analyze) > 10 else ''}")
    
    # Function 2: Whale Tracking (always runs)
    whale = run_whale_tracking()
    
    # Function 3: Glassnode Analysis (runs for assigned/discovered coins)
    glassnode = run_glassnode_analysis(coins_to_analyze)
    
    # Function 4: Technical Analysis (placeholder - runs in execution phase)
    technical = run_technical_analysis_placeholder(coins_to_analyze)
    
    # Aggregate all results
    unified = aggregate_results(discovery, whale, glassnode, technical)
    
    # Save report
    save_unified_report(unified)
    
    print("\n" + "="*80)
    print("✅ UNIFIED DATA WORKER COMPLETE")
    print("="*80)
    
    return unified


def save_unified_report(result: Dict):
    """Save comprehensive report"""
    REPORTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Save JSON
    json_path = REPORTS_DIR / f'unified_worker_{timestamp}.json'
    with open(json_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    # Save summary markdown
    md_path = REPORTS_DIR / f'unified_worker_{timestamp}.md'
    
    summary = result['summary']
    coins = result['coins']
    
    md_content = f"""# Unified Data Worker Report

**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}

## Summary
- Coins Analyzed: {summary['total_coins_analyzed']}
- Bullish: {summary['bullish_coins']}
- Bearish: {summary['bearish_coins']}
- Neutral: {summary['neutral_coins']}

## Top Opportunities

| Rank | Coin | Score | Glassnode | TA | Final |
|------|------|-------|-----------|-----|-------|
"""
    
    # Add top 5 coins
    sorted_coins = sorted(coins.values(), key=lambda x: x.get('discovery_score', 0), reverse=True)[:5]
    for coin in sorted_coins:
        md_content += f"| {coin.get('discovery_rank', 'N/A')} | {coin['symbol']} | {coin.get('discovery_score', 0):.1f} | {coin.get('glassnode_signal', 'N/A')} | {coin.get('momentum_signal', 'N/A')} | {coin['recommendation']} |\n"
    
    with open(md_path, 'w') as f:
        f.write(md_content)
    
    print(f"\n💾 Reports saved:")
    print(f"   {json_path.name}")
    print(f"   {md_path.name}")


if __name__ == '__main__':
    result = run_unified_data_worker()
    
    # Exit status
    if result['summary']['total_coins_analyzed'] > 0:
        print(f"\n✅ Analysis complete - {result['summary']['total_coins_analyzed']} coins analyzed")
        sys.exit(0)
    else:
        print(f"\n⚠️  No coins analyzed")
        sys.exit(1)
