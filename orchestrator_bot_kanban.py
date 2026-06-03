#!/usr/bin/env python3
"""
Orchestrator Bot - Kanban-Driven

Runs as Kanban task assigned to trading-orchestrator profile.
Creates child Kanban tasks for method bots when BUY signals detected.
All messaging through Hermes Gateway via kanban_complete().
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional

# Add trading_system to path
sys.path.insert(0, str(Path(__file__).parent))

# Kanban imports
try:
    from kanban import kanban_complete, kanban_create, kanban_list
    KANBAN_AVAILABLE = True
except ImportError:
    KANBAN_AVAILABLE = False
    print("Note: kanban module not available (standalone mode)")


# ============================================================================
# ORCHESTRATOR LOGIC
# ============================================================================

def assign_best_method(coin_data: dict) -> dict:
    """
    Determine best trading method for given coin data.
    
    Returns:
        dict with assignment, best_method, best_score, reason
    """
    indicators = coin_data.get('ohlcv', {}).get('indicators', {})
    rsi = indicators.get('rsi', 50)
    price = indicators.get('current_price', 0)
    ema20 = indicators.get('ema20', price)
    volume_ratio = indicators.get('volume_ratio', 1)
    
    # Mean Reversion Score (0-100)
    mr_score = 0
    if 35 <= rsi <= 65:
        mr_score = 40  # Neutral = good for mean reversion
    elif 30 <= rsi < 35 or 65 < rsi <= 70:
        mr_score = 25
    elif rsi < 30:
        mr_score = 35  # Oversold = strong mean reversion long
    elif rsi > 70:
        mr_score = 35  # Overbought = strong mean reversion short
    
    price_vs_ema = (price - ema20) / ema20 * 100 if ema20 > 0 else 0
    if abs(price_vs_ema) > 5:
        mr_score += 35  # Extended from mean
    elif abs(price_vs_ema) > 2:
        mr_score += 20
    else:
        mr_score += 10
    
    if 0.8 <= volume_ratio <= 1.5:
        mr_score += 25  # Normal volume
    else:
        mr_score += 10
    
    # Momentum Score (simplified)
    momentum_score = 50 + (rsi - 50) * 0.5
    
    # Breakout Score (simplified)
    breakout_score = 50 + (volume_ratio - 1) * 20
    
    methods = {
        'mean_reversion': min(100, mr_score),
        'momentum': min(100, momentum_score),
        'breakout': min(100, breakout_score),
    }
    
    best_method = max(methods, key=methods.get)
    best_score = methods[best_method]
    
    # Decide
    if best_score >= 60:
        assignment = 'BUY'
    elif best_score >= 45:
        assignment = 'HOLD'
    else:
        assignment = 'HOLD'
    
    # Build reason
    if best_method == 'mean_reversion':
        if rsi < 30:
            reason = f"RSI oversold ({rsi:.1f}) + price {'below' if price_vs_ema < 0 else 'above'} EMA20 ({price_vs_ema:.1f}%)"
        elif rsi > 70:
            reason = f"RSI overbought ({rsi:.1f}) + mean reversion short setup"
        else:
            reason = f"RSI neutral ({rsi:.1f}) + range-bound price action"
    elif best_method == 'momentum':
        reason = f"Strong momentum (RSI {rsi:.1f}, trend {'bullish' if price > ema20 else 'bearish'})"
    else:
        reason = f"Breakout setup (volume {volume_ratio:.1f}x average)"
    
    return {
        'assignment': assignment,
        'best_method': best_method,
        'best_score': round(best_score, 1),
        'all_scores': {k: round(v, 1) for k, v in methods.items()},
        'reason': reason,
        'signals': {
            'rsi': rsi,
            'price_vs_ema20': round(price_vs_ema, 2),
            'volume_ratio': round(volume_ratio, 2),
        }
    }


def create_method_bot_task(coin_data: dict, decision: dict) -> str:
    """
    Create child Kanban task for method bot execution.
    
    Returns:
        Task ID of created task
    """
    symbol = coin_data.get('symbol', 'UNKNOWN')
    method = decision['best_method']
    
    # Map method to profile
    profile_map = {
        'mean_reversion': 'trading-mean-reversion',
        'momentum': 'trading-momentum',
        'breakout': 'trading-breakout',
    }
    
    assignee = profile_map.get(method, 'trading-momentum')
    
    # Create task description
    task_body = f"""
Execute {method.replace('_', ' ').title()} trade for {symbol}.

**Decision Context:**
- Assignment: {decision['assignment']}
- Best Method: {method} (score: {decision['best_score']})
- Reason: {decision['reason']}
- Current Price: ${coin_data['ohlcv']['indicators']['current_price']:,.2f}

**Signals:**
- RSI: {decision['signals']['rsi']:.1f}
- Price vs EMA20: {decision['signals']['price_vs_ema20']:.1f}%
- Volume Ratio: {decision['signals']['volume_ratio']:.1f}x

**Instructions:**
1. Load historical data for {symbol}
2. Generate entry signal using {method} strategy
3. Calculate stop loss and take profit
4. Execute position (max $5)
5. Report via kanban_complete()
"""
    
    # Create Kanban task
    task_id = kanban_create(
        description=f"{method.replace('_', ' ').title()} Execution - {symbol}",
        body=task_body,
        assignee=assignee,
        parent_task_id=None,  # Will be set by Hermes
        metadata={
            'coin_data': coin_data,
            'decision': decision,
            'method': method,
            'symbol': symbol,
        }
    )
    
    print(f"  ✓ Created {method} task: {task_id} (assignee: {assignee})")
    return task_id


def run_orchestrator(data_worker_output: Optional[dict] = None):
    """
    Main Orchestrator execution - runs as Kanban task.
    """
    print("="*70)
    print("ORCHESTRATOR - KANBAN EXECUTION")
    print("="*70)
    
    if data_worker_output is None:
        print("✗ No data worker output - expecting Kanban task context")
        if not KANBAN_AVAILABLE:
            return {'error': 'No data available'}
    
    decisions = []
    child_tasks = []
    
    for coin_data in data_worker_output.get('coin_data', []):
        symbol = coin_data.get('symbol', 'UNKNOWN')
        print(f"\nEvaluating {symbol}...")
        
        # Make decision
        decision = assign_best_method(coin_data)
        decisions.append({
            'symbol': symbol,
            **decision,
        })
        
        print(f"  Assignment: {decision['assignment']}")
        print(f"  Best Method: {decision['best_method']} ({decision['best_score']})")
        print(f"  Reason: {decision['reason']}")
        
        # Create child task for BUY signals
        if decision['assignment'] == 'BUY':
            task_id = create_method_bot_task(coin_data, decision)
            child_tasks.append({
                'task_id': task_id,
                'symbol': symbol,
                'method': decision['best_method'],
            })
    
    # Build summary for Telegram
    buy_signals = [d for d in decisions if d['assignment'] == 'BUY']
    hold_signals = [d for d in decisions if d['assignment'] == 'HOLD']
    
    if buy_signals:
        message = f"""
🧠 **Orchestrator Decision**

**BUY Signals:** {len(buy_signals)}
**HOLD:** {len(hold_signals)}

"""
        for signal in buy_signals:
            message += f"""
🟢 **{signal['symbol']}** - {signal['best_method'].replace('_', ' ').title()}
   Score: {signal['best_score']} | {signal['reason']}
"""
    else:
        message = f"""
🧠 **Orchestrator Decision**

**No BUY signals** - All coins on HOLD

**Evaluated:** {', '.join(d['symbol'] for d in decisions)}
**Best opportunity:** {max(decisions, key=lambda x: x['best_score'])['symbol']} ({max(d['best_score'] for d in decisions)} score)

*Market conditions not favorable for entries*
"""
    
    # Complete Kanban task
    if KANBAN_AVAILABLE:
        kanban_complete(
            output={
                'decisions': decisions,
                'child_tasks': child_tasks,
                'summary': {
                    'buy_signals': len(buy_signals),
                    'hold_signals': len(hold_signals),
                }
            },
            summary=message.strip(),
        )
        print(f"\n✓ Orchestrator complete - {len(child_tasks)} child tasks created")
    else:
        print(f"\nResult: {json.dumps({'decisions': decisions, 'child_tasks': child_tasks}, indent=2)}")
    
    return {
        'decisions': decisions,
        'child_tasks': child_tasks,
    }


# ============================================================================
# CLI
# ============================================================================

if __name__ == '__main__':
    # Test mode with mock data
    mock_data = {
        'coin_data': [
            {
                'symbol': 'BTC',
                'ohlcv': {
                    'indicators': {
                        'current_price': 70000,
                        'rsi': 28,
                        'ema20': 71500,
                        'volume_ratio': 1.2,
                    }
                }
            },
            {
                'symbol': 'ETH',
                'ohlcv': {
                    'indicators': {
                        'current_price': 3500,
                        'rsi': 45,
                        'ema20': 3550,
                        'volume_ratio': 0.9,
                    }
                }
            },
        ]
    }
    
    run_orchestrator(data_worker_output=mock_data)
