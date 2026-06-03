#!/usr/bin/env python3
"""
Mean Reversion Method Bot - Kanban-Driven Execution

This bot runs as a Kanban task assigned to trading-mean-reversion profile.
All messaging goes through Hermes Gateway via kanban_complete().

Triggered by: Orchestrator BUY signal for mean_reversion method
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# Add paper_trading_v4 to path
sys.path.insert(0, str(Path('/mnt/data/hermes/workspace/paper_trading_v4')))

from strategies.rsi_mean_reversion import RSIMeanReversion

# Kanban imports (only available inside Hermes agent context)
try:
    from kanban import kanban_complete, kanban_create
    KANBAN_AVAILABLE = True
except ImportError:
    KANBAN_AVAILABLE = False
    print("Note: kanban module not available (standalone mode)")


# ============================================================================
# CONFIGURATION
# ============================================================================

CONFIG = {
    'max_position_size_usd': 5.0,
    'stop_loss_pct': 3.0,
    'take_profit_pct': 6.0,
    'rsi_period': 14,
    'oversold': 30,
    'overbought': 70,
}


# ============================================================================
# MEAN REVERSION EXECUTION
# ============================================================================

def execute_mean_reversion(coin_data: dict, decision: dict) -> dict:
    """
    Execute mean reversion trade using existing RSI strategy.
    
    Args:
        coin_data: Data from Data Worker (ohlcv, indicators, etc.)
        decision: Orchestrator decision (assignment, best_method, etc.)
    
    Returns:
        Execution result with entry, stop, target, position_size
    """
    symbol = coin_data.get('symbol', 'UNKNOWN')
    indicators = coin_data.get('ohlcv', {}).get('indicators', {})
    current_price = indicators.get('current_price', 0)
    
    if not current_price:
        return {
            'success': False,
            'error': 'No price data available',
            'symbol': symbol,
        }
    
    # Get historical candles for strategy
    candles = coin_data.get('ohlcv', {}).get('candles', [])
    if len(candles) < 50:
        return {
            'success': False,
            'error': f'Insufficient data ({len(candles)} candles, need 50+)',
            'symbol': symbol,
        }
    
    # Convert to DataFrame for strategy
    import pandas as pd
    df = pd.DataFrame(candles)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    
    # Initialize strategy
    strategy = RSIMeanReversion(CONFIG)
    
    try:
        # Generate signal
        signal = strategy.generate_signal(df)
        
        if signal.direction == 'FLAT':
            return {
                'success': True,
                'action': 'NO_TRADE',
                'symbol': symbol,
                'reason': 'Strategy says FLAT - no setup',
                'rsi': signal.metadata.get('rsi'),
            }
        
        # Calculate position size
        position_size = min(CONFIG['max_position_size_usd'], 5.0)
        
        # Build execution result
        result = {
            'success': True,
            'action': 'OPEN_POSITION',
            'symbol': symbol,
            'direction': signal.direction,
            'entry_price': current_price,
            'position_size_usd': position_size,
            'stop_loss': signal.stop_loss,
            'take_profit': signal.take_profit,
            'rsi': signal.metadata.get('rsi'),
            'reason': decision.get('reason', 'Mean reversion setup'),
            'method': 'mean_reversion',
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
        
        return result
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Strategy execution failed: {str(e)}',
            'symbol': symbol,
        }


# ============================================================================
# KANBAN TASK EXECUTION
# ============================================================================

def run_mean_reversion_bot(parent_task_id: Optional[str] = None, coin_data: Optional[dict] = None):
    """
    Main bot execution - runs as Kanban task.
    
    This function is called by the Kanban worker when a task is assigned
    to the trading-mean-reversion profile.
    """
    print("="*70)
    print("MEAN REVERSION BOT - KANBAN EXECUTION")
    print("="*70)
    
    # Get input from parent task (Orchestrator decision)
    if coin_data is None:
        # In Kanban mode, data comes from parent task output
        # This would be passed via kanban task context
        print("✗ No coin data provided - expecting Kanban task context")
        
        if not KANBAN_AVAILABLE:
            print("ERROR: Kanban not available and no data provided")
            return {
                'success': False,
                'error': 'No data available',
            }
    
    # Execute mean reversion
    print(f"\nProcessing mean reversion for {coin_data.get('symbol', 'UNKNOWN')}...")
    
    # Mock decision object (in production, comes from Orchestrator task)
    decision = {
        'assignment': 'BUY',
        'best_method': 'mean_reversion',
        'best_score': 65,
        'reason': 'RSI oversold + price below EMA20',
    }
    
    result = execute_mean_reversion(coin_data, decision)
    
    # Report via Kanban
    if KANBAN_AVAILABLE:
        print(f"\n✓ Execution complete: {result.get('action', 'UNKNOWN')}")
        
        # Build message for Telegram (via Hermes Gateway)
        if result.get('action') == 'OPEN_POSITION':
            message = f"""
🎯 **Mean Reversion Signal - {result['symbol']}**

**Direction:** {result['direction']}
**Entry:** ${result['entry_price']:,.2f}
**Stop Loss:** ${result['stop_loss']:,.2f} ({CONFIG['stop_loss_pct']}%)
**Take Profit:** ${result['take_profit']:,.2f} ({CONFIG['take_profit_pct']}%)
**Position Size:** ${result['position_size_usd']:.2f}
**RSI:** {result['rsi']:.1f}
**Reason:** {result['reason']}

*Risk/Reward: 1:2*
"""
        elif result.get('action') == 'NO_TRADE':
            message = f"""
⏸️ **Mean Reversion - No Trade**

**Symbol:** {result['symbol']}
**Reason:** {result['reason']}
**RSI:** {result.get('rsi', 'N/A')}
"""
        else:
            message = f"Mean Reversion Bot: {result.get('action', 'Complete')} - {result.get('symbol', 'UNKNOWN')}"
        
        # Complete Kanban task with output
        # Hermes Gateway will send this to Telegram
        kanban_complete(
            output=result,
            summary=message.strip(),
        )
        
        print(f"\n✓ Kanban task completed - message queued for Telegram")
    else:
        # Standalone mode - just print result
        print(f"\nResult: {json.dumps(result, indent=2)}")
    
    return result


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Mean Reversion Bot')
    parser.add_argument('--symbol', type=str, default='BTC', help='Coin symbol')
    parser.add_argument('--test', action='store_true', help='Test mode (mock data)')
    
    args = parser.parse_args()
    
    if args.test:
        # Test with mock data
        mock_coin_data = {
            'symbol': args.symbol,
            'ohlcv': {
                'success': True,
                'indicators': {
                    'current_price': 70000,
                    'rsi': 28,
                    'ema20': 71500,
                },
                'candles': [{'close': 70000 + i*100} for i in range(100)],  # Mock candles
            }
        }
        run_mean_reversion_bot(coin_data=mock_coin_data)
    else:
        # Production mode - expects Kanban context
        run_mean_reversion_bot()
