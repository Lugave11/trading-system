#!/usr/bin/env python3
"""
Data Worker - Kanban-Driven Whale Analysis

This is the Data Worker that runs every 5 minutes as part of the trading system.
It integrates whale tracking with coin discovery and Glassnode-style analysis.

Workflow:
1. Load assigned coins from Orchestrator state
2. Run whale tracking scan (TOP 10 + Portfolio)
3. Analyze signals per coin
4. Create Kanban tasks for significant movements
5. Complete task with discovery report

Usage:
  python3 data_worker_kanban.py
"""

import os
import sys
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

# Add trading_system to path
sys.path.insert(0, '/mnt/data/hermes/workspace/trading_system')

from kanban_whale_tracker import KanbanWhaleTracker, KANBAN_THRESHOLDS

# ===== CONFIGURATION =====

STATE_DIR = Path('/mnt/data/hermes/workspace/trading_system/state')
REPORTS_DIR = Path('/mnt/data/hermes/workspace/trading_system/whale_reports')

# Kanban CLI path
HERMES_CLI = '/mnt/data/hermes/workspace/.local/bin/hermes'


def load_orchestrator_state() -> Dict:
    """Load latest Orchestrator state (assigned coins, etc.)"""
    state_file = STATE_DIR / 'orchestrator_latest.json'
    
    if state_file.exists():
        with open(state_file, 'r') as f:
            return json.load(f)
    
    # Fallback to coin_universe.json
    config_file = STATE_DIR / 'coin_universe.json'
    if config_file.exists():
        with open(config_file, 'r') as f:
            config = json.load(f)
            return {
                'coins': config.get('coins', []),
                'updated_at': config.get('updated_at', ''),
            }
    
    return {'coins': ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']}


def save_worker_state(result: Dict):
    """Save Data Worker execution state"""
    STATE_DIR.mkdir(exist_ok=True)
    
    state_file = STATE_DIR / 'data_worker_latest.json'
    
    with open(state_file, 'w') as f:
        json.dump({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'status': result.get('status', 'unknown'),
            'signals_found': result.get('signals_found', 0),
            'tasks_created': result.get('tasks_created', 0),
            'coin_analysis': result.get('coin_analysis', {}),
        }, f, indent=2, default=str)
    
    print(f"💾 Worker state saved: {state_file.name}")


def analyze_coin_signals(coin: str, signals: List[Dict]) -> Dict:
    """
    Analyze all signals for a specific coin.
    Returns per-coin summary with recommendation.
    """
    coin_signals = [s for s in signals if s.get('symbol') == coin or 
                    (coin == 'BTC' and s.get('symbol') == 'WBTC')]
    
    if not coin_signals:
        return {
            'coin': coin,
            'signal_count': 0,
            'net_flow_usd': 0,
            'sentiment': 'NEUTRAL',
            'recommendation': 'HOLD',
            'confidence': 0.5,
        }
    
    # Calculate net flow
    inflows = sum(s['value_usd'] for s in coin_signals if s.get('to_exchange'))
    outflows = sum(s['value_usd'] for s in coin_signals if s.get('from_exchange'))
    net_flow = outflows - inflows  # Positive = bullish (more outflow)
    
    # Determine sentiment
    if net_flow > 5_000_000:
        sentiment = 'BULLISH'
        confidence = min(1.0, net_flow / 20_000_000)
        recommendation = 'ENTER_LONG' if confidence > 0.7 else 'ACCUMULATE'
    elif net_flow < -5_000_000:
        sentiment = 'BEARISH'
        confidence = min(1.0, abs(net_flow) / 20_000_000)
        recommendation = 'EXIT' if confidence > 0.7 else 'REDUCE'
    else:
        sentiment = 'NEUTRAL'
        confidence = 0.5
        recommendation = 'HOLD'
    
    return {
        'coin': coin,
        'signal_count': len(coin_signals),
        'total_volume_usd': sum(s['value_usd'] for s in coin_signals),
        'inflows_usd': inflows,
        'outflows_usd': outflows,
        'net_flow_usd': net_flow,
        'sentiment': sentiment,
        'recommendation': recommendation,
        'confidence': confidence,
        'largest_signal': max(coin_signals, key=lambda x: x['value_usd']) if coin_signals else None,
    }


def create_discovery_task(coin: str, analysis: Dict, parent_task_id: str = None) -> Optional[str]:
    """
    Create a Kanban task for coin-specific whale analysis.
    This is called when significant whale activity is detected for a portfolio coin.
    """
    if analysis['signal_count'] == 0:
        return None
    
    # Only create task if significant activity
    if analysis['total_volume_usd'] < KANBAN_THRESHOLDS['PORTFOLIO']:
        return None
    
    sentiment = analysis['sentiment']
    volume = analysis['total_volume_usd']
    recommendation = analysis['recommendation']
    
    # Task title
    emoji = {'BULLISH': '🟢', 'BEARISH': '🔴', 'NEUTRAL': '⚪'}[sentiment]
    title = f"{emoji} {coin} Whale Activity: ${volume:,.0f} - {recommendation}"
    
    # Task body
    body = f"""
## 🐋 WHALE ACTIVITY ANALYSIS - {coin}

**Sentiment:** {sentiment}
**Confidence:** {analysis['confidence']:.0%}
**Total Volume:** ${volume:,.2f}

### Flow Analysis
- **Exchange Inflows:** ${analysis['inflows_usd']:,.2f} (potential selling)
- **Exchange Outflows:** ${analysis['outflows_usd']:,.2f} (accumulation)
- **Net Flow:** ${analysis['net_flow_usd']:,.2f} ({'Bullish' if analysis['net_flow_usd'] > 0 else 'Bearish'})

### Signal Count
- **Total Signals:** {analysis['signal_count']}
"""
    
    if analysis.get('largest_signal'):
        largest = analysis['largest_signal']
        body += f"""
### Largest Movement
- **Amount:** ${largest['value_usd']:,.2f} {largest['symbol']}
- **Type:** {largest['signal']}
- **From:** {largest['from_label'] or largest['from'][:20]}
- **To:** {largest['to_label'] or largest['to'][:20]}
- **TX:** [`{largest['tx_hash'][:10]}...`](https://etherscan.io/tx/{largest['tx_hash']})
"""
    
    body += f"""
### Recommendation
**{recommendation}**

Based on whale flow analysis:
- Net exchange flow: ${analysis['net_flow_usd']:,.0f}
- Signal count: {analysis['signal_count']}
- Confidence: {analysis['confidence']:.0%}

**Action Required:**
"""
    
    if recommendation == 'EXIT':
        body += """
1. Review current {coin} position size
2. Consider reducing exposure by 25-50%
3. Set tighter stop-loss if holding
4. Monitor for additional bearish signals
""".format(coin=coin)
    elif recommendation == 'ENTER_LONG':
        body += """
1. Check current allocation to {coin}
2. Consider entry at current levels
3. Set stop-loss below recent support
4. Monitor for follow-up buying
""".format(coin=coin)
    else:
        body += """
1. Maintain current position
2. Monitor for new signals
3. No immediate action required
"""
    
    # Create task
    try:
        import subprocess
        
        cmd = [
            HERMES_CLI,
            'kanban', 'create',
            title,
            '--body', body,
            '--assignee', 'trading-data',
            '--metadata', json.dumps({
                'task_type': 'WHALE_ANALYSIS',
                'coin': coin,
                'analysis': analysis,
                'parent_task': parent_task_id,
            })
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            output = result.stdout.strip()
            if 'Created' in output:
                task_id = output.split()[-1]
                print(f"   ✅ Created task: {task_id} ({coin})")
                return task_id
        
        print(f"   ⚠️  Task creation failed for {coin}")
        return None
        
    except Exception as e:
        print(f"   ❌ Error creating task for {coin}: {e}")
        return None


def run_data_worker() -> Dict:
    """
    Main Data Worker execution.
    This runs every 5 minutes as part of the trading system.
    """
    print("="*80)
    print("DATA WORKER - WHALE ANALYSIS")
    print(f"Executed: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("="*80)
    
    # Step 1: Load assigned coins from Orchestrator
    print("\n📋 Step 1: Loading assigned coins...")
    orchestrator_state = load_orchestrator_state()
    assigned_coins = orchestrator_state.get('coins', [])
    print(f"   Assigned coins: {len(assigned_coins)}")
    print(f"   Coins: {', '.join(assigned_coins[:10])}{'...' if len(assigned_coins) > 10 else ''}")
    
    # Step 2: Run whale tracking scan
    print("\n🔍 Step 2: Running whale tracking scan...")
    tracker = KanbanWhaleTracker()
    
    # Get prices
    tracker.get_eth_price()
    print(f"   ETH: ${tracker.eth_price:,.2f} | BTC: ${tracker.token_prices['BTC']:,.0f}")
    
    # Scan for signals
    print("\n   Scanning TOP 10 + Portfolio coins...")
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
    
    print(f"\n   📊 Found {len(unique_signals)} unique signals")
    
    # Step 3: Analyze per-coin
    print("\n📈 Step 3: Per-coin whale analysis...")
    coin_analysis = {}
    
    for coin in assigned_coins:
        analysis = analyze_coin_signals(coin, unique_signals)
        coin_analysis[coin] = analysis
        
        # Print summary
        emoji = {'BULLISH': '🟢', 'BEARISH': '🔴', 'NEUTRAL': '⚪'}[analysis['sentiment']]
        if analysis['signal_count'] > 0:
            print(f"   {emoji} {coin:6s} | {analysis['signal_count']:2d} signals | "
                  f"Net: ${analysis['net_flow_usd']:>12,.0f} | {analysis['recommendation']}")
        else:
            print(f"   ⚪ {coin:6s} | No significant whale activity")
    
    # Step 4: Create Kanban tasks for significant activity
    print("\n📋 Step 4: Creating Kanban tasks...")
    tasks_created = []
    
    for coin, analysis in coin_analysis.items():
        if analysis['signal_count'] > 0 and analysis['total_volume_usd'] >= KANBAN_THRESHOLDS['PORTFOLIO']:
            task_id = create_discovery_task(coin, analysis, parent_task_id=None)
            if task_id:
                tasks_created.append({
                    'task_id': task_id,
                    'coin': coin,
                    'analysis': analysis,
                })
    
    print(f"\n   ✅ Created {len(tasks_created)} Kanban tasks")
    
    # Step 5: Generate discovery report
    print("\n📝 Step 5: Generating discovery report...")
    
    # Count by sentiment
    bullish_coins = [c for c, a in coin_analysis.items() if a['sentiment'] == 'BULLISH']
    bearish_coins = [c for c, a in coin_analysis.items() if a['sentiment'] == 'BEARISH']
    neutral_coins = [c for c, a in coin_analysis.items() if a['sentiment'] == 'NEUTRAL']
    
    # Create summary
    summary = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'coins_analyzed': len(assigned_coins),
        'signals_found': len(unique_signals),
        'tasks_created': len(tasks_created),
        'sentiment_breakdown': {
            'bullish': len(bullish_coins),
            'bearish': len(bearish_coins),
            'neutral': len(neutral_coins),
        },
        'coin_analysis': coin_analysis,
        'signals': unique_signals,
        'tasks': tasks_created,
    }
    
    # Save state
    save_worker_state(summary)
    
    # Save detailed report
    REPORTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file = REPORTS_DIR / f'data_worker_{timestamp}.json'
    
    with open(report_file, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    
    print(f"   💾 Report saved: {report_file.name}")
    
    # Step 6: Print summary
    print("\n" + "="*80)
    print("DISCOVERY SUMMARY")
    print("="*80)
    print(f"Coins Analyzed: {len(assigned_coins)}")
    print(f"Whale Signals: {len(unique_signals)}")
    print(f"Kanban Tasks: {len(tasks_created)}")
    print(f"\nSentiment:")
    print(f"  🟢 Bullish: {len(bullish_coins)} coins ({', '.join(bullish_coins[:3])}{'...' if len(bullish_coins) > 3 else ''})")
    print(f"  🔴 Bearish: {len(bearish_coins)} coins ({', '.join(bearish_coins[:3])}{'...' if len(bearish_coins) > 3 else ''})")
    print(f"  ⚪ Neutral: {len(neutral_coins)} coins")
    
    if tasks_created:
        print(f"\n📋 TASKS CREATED:")
        for task in tasks_created:
            a = task['analysis']
            print(f"  • {task['task_id']} | {task['coin']} | {a['recommendation']} | ${a['total_volume_usd']:,.0f}")
    
    print("\n" + "="*80)
    print("✅ DATA WORKER COMPLETE")
    print("="*80)
    
    return summary


def complete_kanban_task(task_id: str, result: Dict):
    """
    Complete the Kanban task with discovery results.
    This is called after the worker finishes analysis.
    """
    try:
        import subprocess
        
        # Build result summary
        result_text = f"✅ Analyzed {result['coins_analyzed']} coins, found {result['signals_found']} signals"
        
        if result['tasks_created'] > 0:
            result_text += f", created {result['tasks_created']} tasks"
        
        # Sentiment summary
        sentiment = result['sentiment_breakdown']
        if sentiment['bearish'] > sentiment['bullish']:
            result_text += " | 🔴 Bearish bias"
        elif sentiment['bullish'] > sentiment['bearish']:
            result_text += " | 🟢 Bullish bias"
        else:
            result_text += " | ⚪ Neutral"
        
        cmd = [
            HERMES_CLI,
            'kanban', 'complete',
            task_id,
            '--result', result_text,
            '--summary', f"Analyzed {result['coins_analyzed']} coins, {result['signals_found']} whale signals detected",
            '--metadata', json.dumps({
                'coins_analyzed': result['coins_analyzed'],
                'signals_found': result['signals_found'],
                'tasks_created': result['tasks_created'],
                'sentiment': result['sentiment_breakdown'],
            })
        ]
        
        subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        print(f"✅ Completed Kanban task: {task_id}")
        
    except Exception as e:
        print(f"⚠️  Failed to complete task: {e}")


if __name__ == '__main__':
    # Run Data Worker
    result = run_data_worker()
    
    # If running as part of a Kanban task, complete it
    # (In production, task_id would come from environment or arguments)
    # complete_kanban_task(os.environ.get('KANBAN_TASK_ID'), result)
