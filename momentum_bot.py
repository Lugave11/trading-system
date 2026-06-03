#!/usr/bin/env python3
"""
Momentum Method Bot - Executes momentum trades via Kanban.

SPOT TRADING - Trend following with no leverage.
Handles both BUY (uptrend) and SELL (downtrend) positions.

Note: This is SPOT trading only - no leverage, no derivatives.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# Kanban imports (only available inside Hermes agent)
try:
    from kanban import kanban_complete, kanban_create, kanban_comment
    KANBAN_AVAILABLE = True
except ImportError:
    KANBAN_AVAILABLE = False
    print("Note: kanban module not available (standalone mode)")


# ============================================================================
# CONFIGURATION
# ============================================================================

MOMENTUM_CONFIG = {
    'max_position_size_usd': 5,  # $5 max per trade (user rule)
    'stop_loss_pct': 5.0,  # 5% stop loss
    'take_profit_pct': 10.0,  # 10-15% take profit (trend-dependent)
    'trailing_stop_trigger_pct': 5.0,  # Move stop to breakeven at +5%
    'rsi_entry_buy': 60,  # RSI > 60 for BUY (uptrend)
    'rsi_entry_sell': 40,  # RSI < 40 for SELL (downtrend)
}


# ============================================================================
# EXECUTION LOGIC
# ============================================================================

def execute_momentum_trade(
    symbol: str,
    action: str,  # 'BUY' or 'SELL' (SPOT)
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    position_size_usd: float = 5.0,
    reason: str = "",
    whale_score: float = 0.0
) -> dict:
    """
    Execute momentum trade (SPOT TRADING - no leverage).
    
    Args:
        symbol: Trading symbol (e.g., 'UNI')
        action: 'BUY' (uptrend) or 'SELL' (downtrend)
        entry_price: Entry price
        stop_loss: Stop loss price
        take_profit: Take profit price
        position_size_usd: Position size in USD
        reason: Trade reason
        whale_score: Whale activity score
    
    Returns:
        Execution result dict
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Calculate position size (coins)
    position_size_coins = position_size_usd / entry_price
    
    # Calculate risk/reward (SPOT trading)
    if action == 'BUY':
        risk = entry_price - stop_loss
        reward = take_profit - entry_price
    else:  # SELL
        risk = stop_loss - entry_price
        reward = entry_price - take_profit
    
    risk_reward_ratio = reward / risk if risk > 0 else 0
    
    # Create trade record (SPOT terminology)
    trade = {
        'trade_id': f"momentum_{symbol}_{timestamp[:19].replace(':', '-')}",
        'symbol': symbol,
        'action': action,  # BUY or SELL (not LONG/SHORT)
        'method': 'momentum',
        'position_type': 'SPOT',  # Explicitly SPOT
        'entry_price': entry_price,
        'stop_loss': stop_loss,
        'take_profit': take_profit,
        'position_size_usd': position_size_usd,
        'position_size_coins': round(position_size_coins, 4),
        'risk_reward_ratio': round(risk_reward_ratio, 2),
        'whale_score': whale_score,
        'reason': reason,
        'entry_timestamp': timestamp,
        'status': 'OPEN',
        'trailing_stop_active': False,
        'pnl_usd': 0.0,
        'pnl_pct': 0.0,
    }
    
    # Save trade to state file
    state_dir = Path('/mnt/data/hermes/workspace/trading_system/state')
    state_dir.mkdir(parents=True, exist_ok=True)
    
    trades_file = state_dir / 'momentum_trades.json'
    existing_trades = []
    if trades_file.exists():
        with open(trades_file, 'r') as f:
            existing_trades = json.load(f)
    
    existing_trades.append(trade)
    with open(trades_file, 'w') as f:
        json.dump(existing_trades, f, indent=2)
    
    print(f"✓ Trade recorded: {trade['trade_id']}")
    print(f"  Symbol: {symbol} {direction}")
    print(f"  Entry: ${entry_price:.4f}")
    print(f"  Stop: ${stop_loss:.4f}")
    print(f"  Target: ${take_profit:.4f}")
    print(f"  Size: ${position_size_usd} ({position_size_coins:.4f} coins)")
    print(f"  R:R: {risk_reward_ratio:.2f}")
    
    return {
        'success': True,
        'trade': trade,
        'state_file': str(trades_file),
    }


def create_monitor_task(trade: dict) -> dict:
    """
    Create Kanban task for monitoring SPOT momentum position.
    
    Uses SPOT TRADING terminology (BUY/SELL, not LONG/SHORT).
    
    Args:
        trade: Trade record
    
    Returns:
        Task creation result
    """
    if not KANBAN_AVAILABLE:
        print("Note: Cannot create monitor task - Kanban not available")
        return None
    
    symbol = trade['symbol']
    action = trade.get('action', trade.get('direction', 'BUY'))  # BUY or SELL
    entry = trade['entry_price']
    stop = trade['stop_loss']
    target = trade['take_profit']
    
    # SPOT TRADING terminology (not LONG/SHORT)
    position_type = trade.get('position_type', 'SPOT')
    
    task = kanban_create(
        title=f"Monitor: {symbol} {position_type} {action} @ ${entry:.4f}",
        body=f"""
POSITION MONITORING TASK - SPOT TRADING

Trade Details:
- Trade ID: {trade['trade_id']}
- Symbol: {symbol}
- Action: {action} ({position_type})
- Method: Momentum
- Entry: ${entry:.4f}
- Stop Loss: ${stop:.4f}
- Take Profit: ${target:.4f}
- Position Size: ${trade['position_size_usd']}

Monitoring Rules:
1. Check price every 5 minutes
2. Exit if price crosses stop loss
3. Exit if price hits take profit
4. Exit if trend breaks (price below EMA20 for BUY, above for SELL)
5. Move stop to breakeven at +5% profit

Current Status: OPEN
Entry Time: {trade['entry_timestamp']}

Note: This is SPOT TRADING - no leverage, no derivatives.
""",
        assignee='trading-momentum',
        metadata={
            'trade_id': trade['trade_id'],
            'symbol': symbol,
            'action': action,
            'position_type': position_type,
            'entry_price': entry,
            'stop_loss': stop,
            'take_profit': target,
            'monitoring_interval_minutes': 5,
        }
    )
    
    print(f"✓ Monitor task created: {task['id']}")
    return task


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == '__main__':
    # Task parameters from Kanban task
    SYMBOL = 'UNI'
    ACTION = 'SELL'  # Bearish momentum (SPOT SELL)
    ENTRY_PRICE = 2.7964
    STOP_LOSS = 3.0206  # +8.0%
    TAKE_PROFIT = 2.6778  # -4.2%
    POSITION_SIZE = 5.0  # $5 max
    WHALE_SCORE = 85.0
    REASON = "High volatility (5.66% 24h change), whale activity (score 85), bearish momentum"
    
    print("="*60)
    print("MOMENTUM BOT - Trade Execution (SPOT)")
    print("="*60)
    print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print()
    
    # Execute the trade
    result = execute_momentum_trade(
        symbol=SYMBOL,
        action=ACTION,
        entry_price=ENTRY_PRICE,
        stop_loss=STOP_LOSS,
        take_profit=TAKE_PROFIT,
        position_size_usd=POSITION_SIZE,
        reason=REASON,
        whale_score=WHALE_SCORE,
    )
    
    if not result['success']:
        print(f"✗ Trade execution failed: {result.get('error', 'Unknown error')}")
        sys.exit(1)
    
    trade = result['trade']
    
    # Create monitoring task
    monitor_task = create_monitor_task(trade)
    
    # Complete the Kanban task with full execution details
    if KANBAN_AVAILABLE:
        kanban_complete(
            summary=f"Executed {SYMBOL} {ACTION} momentum trade (SPOT) - Entry ${ENTRY_PRICE:.4f}, Stop ${STOP_LOSS:.4f}, Target ${TAKE_PROFIT:.4f}, Size $5. Monitor task: {monitor_task['id'] if monitor_task else 'N/A'}",
            metadata={
                'trade_id': trade['trade_id'],
                'symbol': SYMBOL,
                'direction': DIRECTION,
                'entry_price': ENTRY_PRICE,
                'stop_loss': STOP_LOSS,
                'take_profit': TAKE_PROFIT,
                'position_size_usd': POSITION_SIZE,
                'position_size_coins': trade['position_size_coins'],
                'risk_reward_ratio': trade['risk_reward_ratio'],
                'whale_score': WHALE_SCORE,
                'status': 'OPEN',
                'monitor_task_id': monitor_task['id'] if monitor_task else None,
                'state_file': result['state_file'],
            },
            created_cards=[monitor_task['id']] if monitor_task else [],
        )
    else:
        print()
        print("Trade executed successfully (standalone mode)")
        print(f"State saved to: {result['state_file']}")
