#!/usr/bin/env python3
"""
Mean Reversion Method Bot - Executes mean reversion trades via Kanban.

SPOT TRADING BOT - Buy low, sell high.

Wraps the existing paper_trading_v4 RSI Mean Reversion strategy.
Triggered by Orchestrator BUY signals for mean_reversion method.

Strategy:
- Buy when RSI < 30 (oversold) - price dropped too far
- Sell when RSI > 50 (mean reversion complete) - price returned to mean
- Stop-loss: 3% below entry
- Take-profit: 6% above entry
"""

import sys
from pathlib import Path

# Add paper_trading_v4 to path (absolute path)
paper_trading_path = Path('/mnt/data/hermes/workspace/paper_trading_v4')
sys.path.insert(0, str(paper_trading_path))

print(f"Added to path: {paper_trading_path}")
print(f"Path exists: {paper_trading_path.exists()}")

# Verify strategy module
strategy_file = paper_trading_path / 'strategies' / 'rsi_mean_reversion.py'
print(f"Strategy file exists: {strategy_file.exists()}")

from strategies.rsi_mean_reversion import RSIMeanReversion

# Kanban imports (only available inside Hermes agent)
try:
    from kanban import kanban_complete, kanban_create
    KANBAN_AVAILABLE = True
except ImportError:
    KANBAN_AVAILABLE = False
    print("Note: kanban module not available (standalone mode)")

# ============================================================================
# CONFIGURATION
# ============================================================================

MEAN_REVERSION_CONFIG = {
    'rsi_period': 14,
    'oversold': 30,
    'overbought': 70,
    'max_position_size_usd': 5,  # $5 max per trade
    'stop_loss_pct': 3.0,  # 3% stop loss
    'take_profit_pct': 6.0,  # 6% take profit (2:1 R:R)
}


# ============================================================================
# EXECUTION LOGIC
# ============================================================================

def execute_mean_reversion(symbol: str, coin_data: dict, decision: dict) -> dict:
    """
    Execute mean reversion trade based on Orchestrator decision.
    
    Args:
        symbol: Trading symbol (e.g., 'ETH')
        coin_data: Full coin data from Data Worker
        decision: Orchestrator decision dict
    
    Returns:
        Execution result dict
    """
    # Get OHLCV data
    ohlcv = coin_data.get('ohlcv', {})
    if not ohlcv.get('success'):
        return {
            'success': False,
            'error': 'No OHLCV data available',
            'symbol': symbol,
        }
    
    candles = ohlcv.get('candles', [])
    if len(candles) < 50:
        return {
            'success': False,
            'error': f'Insufficient candles ({len(candles)} < 50)',
            'symbol': symbol,
        }
    
    # Convert to DataFrame for strategy
    import pandas as pd
    df = pd.DataFrame(candles)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    
    # Initialize strategy
    strategy = RSIMeanReversion(MEAN_REVERSION_CONFIG)
    
    # Generate signal
    signal = strategy.generate_signal(df)
    
    # Check if signal matches decision
    if signal.direction == 'FLAT':
        return {
            'success': True,
            'action': 'NO_TRADE',
            'symbol': symbol,
            'reason': f'RSI strategy says FLAT (RSI={signal.metadata.get("rsi", "N/A")})',
            'signal': signal.to_dict(),
        }
    
    # Get current price
    current_price = ohlcv.get('indicators', {}).get('current_price', candles[-1]['close'])
    
    # Calculate position size
    position_size_usd = min(
        MEAN_REVERSION_CONFIG['max_position_size_usd'],
        MEAN_REVERSION_CONFIG['max_position_size_usd']  # Could add dynamic sizing here
    )
    
    # Prepare execution result
    result = {
        'success': True,
        'action': 'OPEN_POSITION',
        'symbol': symbol,
        'direction': signal.direction,
        'entry_price': current_price,
        'position_size_usd': position_size_usd,
        'position_size_tokens': position_size_usd / current_price,
        'stop_loss': signal.stop_loss,
        'take_profit': signal.take_profit,
        'rsi': signal.metadata.get('rsi'),
        'signal_strength': signal.strength,
        'strategy': 'rsi_mean_reversion',
        'parameters': {
            'rsi_period': MEAN_REVERSION_CONFIG['rsi_period'],
            'oversold': MEAN_REVERSION_CONFIG['oversold'],
            'overbought': MEAN_REVERSION_CONFIG['overbought'],
        },
    }
    
    return result


def run_mean_reversion_bot(orchestrator_output: dict = None) -> dict:
    """
    Run Mean Reversion Bot for all BUY signals assigned to mean_reversion method.
    
    Args:
        orchestrator_output: Output from Orchestrator task (or None to fetch from Kanban)
    
    Returns:
        Execution results for all positions
    """
    from datetime import datetime, timezone
    
    start_time = datetime.now(timezone.utc)
    
    print(f"[{start_time.isoformat()}] Mean Reversion Bot starting...")
    
    # Get orchestrator output
    if orchestrator_output is None:
        # Would fetch from latest Orchestrator Kanban task
        # For now, return error
        return {
            'success': False,
            'error': 'No orchestrator output provided',
            'timestamp': start_time.isoformat(),
        }
    
    decisions = orchestrator_output.get('decisions', [])
    
    # Filter for mean_reversion BUY signals
    mr_signals = [
        d for d in decisions
        if d.get('assignment') == 'BUY' and d.get('best_method') == 'mean_reversion'
    ]
    
    if not mr_signals:
        print(f"  No mean reversion BUY signals found")
        return {
            'success': True,
            'executed': 0,
            'message': 'No mean reversion BUY signals',
            'timestamp': start_time.isoformat(),
        }
    
    print(f"  Found {len(mr_signals)} mean reversion BUY signal(s)")
    
    executions = []
    
    for decision in mr_signals:
        symbol = decision.get('symbol')
        print(f"  Processing {symbol}...")
        
        # Get coin data from decision (would come from parent Data Worker task)
        # For now, use placeholder
        coin_data = {
            'ohlcv': {
                'success': True,
                'candles': [],  # Would fetch from Data Worker output
                'indicators': {
                    'current_price': decision.get('current_price', 0),
                }
            }
        }
        
        # Execute
        result = execute_mean_reversion(symbol, coin_data, decision)
        executions.append(result)
        
        print(f"    {result.get('action', 'UNKNOWN')}: {result.get('reason', result.get('direction', 'N/A'))}")
        
        # Create monitor task if position opened
        if result.get('action') == 'OPEN_POSITION':
            position = {
                'coin': symbol,
                'action': 'BUY',  # SPOT BUY
                'entry_price': result.get('entry_price'),
                'stop_loss': result.get('stop_loss'),
                'take_profit': result.get('take_profit'),
                'size_usd': result.get('position_size_usd'),
                'rsi': result.get('rsi'),
                'opened_at': datetime.now(timezone.utc).isoformat(),
            }
            create_monitor_task(position)
    
    end_time = datetime.now(timezone.utc)
    
    summary = {
        'signals_processed': len(mr_signals),
        'positions_opened': sum(1 for e in executions if e.get('action') == 'OPEN_POSITION'),
        'no_trades': sum(1 for e in executions if e.get('action') == 'NO_TRADE'),
        'errors': sum(1 for e in executions if not e.get('success')),
        'duration_seconds': (end_time - start_time).total_seconds(),
    }
    
    print(f"\n[{end_time.isoformat()}] Bot complete: {summary}")
    
    return {
        'success': True,
        'summary': summary,
        'executions': executions,
        'timestamp': start_time.isoformat(),
    }


def create_monitor_task(position: dict) -> dict:
    """
    Create Kanban task for monitoring SPOT position.
    
    Uses SPOT TRADING terminology (BUY/SELL, not LONG/SHORT).
    
    Args:
        position: Position record with entry, stop_loss, take_profit, etc.
    
    Returns:
        Task creation result
    """
    if not KANBAN_AVAILABLE:
        print("Note: Cannot create monitor task - Kanban not available")
        return None
    
    coin = position.get('coin', position.get('symbol', 'UNKNOWN'))
    entry = position.get('entry_price', 0)
    stop = position.get('stop_loss', 0)
    target = position.get('take_profit', 0)
    size = position.get('size_usd', 0)
    rsi = position.get('rsi', 'N/A')
    
    # SPOT TRADING terminology (not LONG/SHORT)
    action = position.get('action', 'BUY')  # BUY or SELL for spot
    direction_label = f"SPOT {action}"
    
    task = kanban_create(
        title=f"Monitor: {coin} {direction_label} @ ${entry:.2f}",
        body=f"""
POSITION MONITORING TASK - SPOT TRADING

Trade Details:
- Coin: {coin}
- Action: {action} (SPOT)
- Entry: ${entry:.2f}
- Stop Loss: ${stop:.2f} (-{((entry-stop)/entry*100):.1f}%)
- Take Profit: ${target:.2f} (+{((target-entry)/entry*100):.1f}%)
- Position Size: ${size:.2f}
- RSI at Entry: {rsi}

Monitoring Rules:
1. Check price every 5 minutes
2. Exit if price <= stop loss (protect capital)
3. Exit if price >= take profit (secure gains)
4. Exit if RSI > 50 (mean reversion complete for BUY positions)
5. Time expiry: 48 hours from entry

Current Status: OPEN
Entry Time: {position.get('opened_at', 'N/A')}

Note: This is SPOT TRADING - no leverage, no derivatives.
""",
        assignee='trading-mean-reversion',
        metadata={
            'coin': coin,
            'action': action,
            'entry_price': entry,
            'stop_loss': stop,
            'take_profit': target,
            'size_usd': size,
            'rsi_entry': rsi,
            'monitoring_interval_minutes': 5,
            'position_type': 'SPOT',
        }
    )
    
    print(f"✓ Monitor task created: {task.get('id', 'UNKNOWN')}")
    return task


# ============================================================================
# TEST / DEMO
# ============================================================================

if __name__ == '__main__':
    print("="*60)
    print("MEAN REVERSION BOT - TEST")
    print("="*60)
    
    # Test with mock orchestrator output
    mock_output = {
        'decisions': [
            {
                'symbol': 'ETH',
                'assignment': 'BUY',
                'best_method': 'mean_reversion',
                'best_score': 65,
                'current_price': 3500,
            }
        ]
    }
    
    result = run_mean_reversion_bot(mock_output)
    print("\nResult:")
    import json
    print(json.dumps(result, indent=2, default=str))
