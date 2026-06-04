#!/usr/bin/env python3
"""
Derivatives Trading Bot - KANBAN-DRIVEN

Handles both LONG and SHORT positions with leverage.
ALL operations through Kanban tasks - no background processes.

Strategy: RSI Extremes + On-Chain Confirmation
- LONG: RSI < 35 + Etherscan BUY/STRONG_BUY
- SHORT: RSI > 65 + Etherscan SELL/STRONG_SELL
- Leverage: 2x standard, 3x high conviction
- Stop-loss: 3% (hard)
- Take-profit: 6% (hard)
- Time expiry: 48 hours

Capital Allocation:
- Total capital: $25
- Derivatives: $7.50 (30%)
- Max per trade: $5
- Max concurrent: 1-2 positions

Kanban Task Types:
1. 🟢 LONG Entry - Open LONG position
2. 🔴 SHORT Entry - Open SHORT position
3. 👁️ Monitor - Check position every 5 min (re-creates itself)
4. 🔴 Close - Close position on exit signal

Usage:
  hermes kanban create "🟢 LONG BTC - Derivatives (3x)" \\
    --assignee trading-derivatives \\
    --metadata '{"direction": "LONG", "coin": "BTC", "leverage": 3, "allocation": 5.00}'
"""

import os
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass

# Import strategy functions
from derivatives_strategy import (
    should_enter_long,
    should_enter_short,
    should_exit_position,
    calculate_position_pnl,
    get_available_derivatives_capital,
    can_open_new_position,
    DERIVATIVES_ALLOCATION,
    MAX_PER_TRADE,
)

# ===== CONFIGURATION =====
MAX_LEVERAGE = 3
DEFAULT_LEVERAGE = 2
STOP_LOSS_PCT = 0.03
TAKE_PROFIT_PCT = 0.06
MAX_ALLOCATION = 5.00

# State directory
STATE_DIR = Path(__file__).parent / "state"
STATE_DIR.mkdir(exist_ok=True)
POSITIONS_FILE = STATE_DIR / "derivatives_positions.json"


@dataclass
class Position:
    """Represents an open derivatives position"""
    trade_id: str
    symbol: str
    direction: str
    leverage: int
    entry_price: float
    position_size_usd: float
    position_size_coins: float
    stop_loss: float
    take_profit: float
    entry_timestamp: str
    status: str = 'OPEN'
    exit_price: Optional[float] = None
    exit_timestamp: Optional[str] = None
    exit_reason: Optional[str] = None
    final_pnl_usd: Optional[float] = None
    final_pnl_pct: Optional[float] = None


class DerivativesBot:
    """Derivatives bot - ALL operations via Kanban tasks"""
    
    def __init__(self):
        self.positions = self._load_positions()
    
    def _load_positions(self) -> Dict[str, Position]:
        """Load positions from state file"""
        if not POSITIONS_FILE.exists():
            return {}
        
        try:
            with open(POSITIONS_FILE, 'r') as f:
                data = json.load(f)
            
            positions = {}
            for trade_id, pos_data in data.items():
                positions[trade_id] = Position(**pos_data)
            return positions
        except:
            return {}
    
    def _save_positions(self):
        """Save positions to state file"""
        data = {}
        for trade_id, pos in self.positions.items():
            data[trade_id] = pos.__dict__
        
        with open(POSITIONS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _get_price(self, symbol: str) -> float:
        """Get current price (simplified - uses mock for now)"""
        # In production: fetch from Binance.US API
        mock_prices = {
            'BTC': 67000,
            'ETH': 1870,
            'SOL': 75,
        }
        return mock_prices.get(symbol.upper(), 100)
    
    def open_position(self, metadata: Dict) -> Dict:
        """Open derivatives position from Kanban task"""
        direction = metadata.get('direction', '').upper()
        coin = metadata.get('coin', metadata.get('symbol', ''))
        leverage = metadata.get('leverage', DEFAULT_LEVERAGE)
        allocation = min(metadata.get('allocation', MAX_ALLOCATION), MAX_ALLOCATION)
        reason = metadata.get('reason', '')
        
        # Validate
        if direction not in ['LONG', 'SHORT']:
            return {'status': 'error', 'reason': f'Invalid direction: {direction}'}
        
        if not coin:
            return {'status': 'error', 'reason': 'No coin specified'}
        
        if leverage > MAX_LEVERAGE:
            return {'status': 'error', 'reason': f'Leverage {leverage}x exceeds max {MAX_LEVERAGE}x'}
        
        # Get price - use metadata price if provided (from Kanban task), otherwise fetch
        entry_price = metadata.get('entry_price') or self._get_price(coin)
        if entry_price <= 0:
            return {'status': 'error', 'reason': f'Invalid price for {coin}'}
        
        # Calculate position - use metadata values if provided
        position_size_coins = allocation / entry_price
        
        # Use stop_loss/take_profit from metadata if provided, otherwise calculate
        if 'stop_loss' in metadata and 'take_profit' in metadata:
            stop_loss = metadata['stop_loss']
            take_profit = metadata['take_profit']
        elif direction == 'LONG':
            stop_loss = entry_price * (1 - STOP_LOSS_PCT)
            take_profit = entry_price * (1 + TAKE_PROFIT_PCT)
        else:  # SHORT
            stop_loss = entry_price * (1 + STOP_LOSS_PCT)
            take_profit = entry_price * (1 - TAKE_PROFIT_PCT)
        
        # Create position
        timestamp = datetime.now(timezone.utc).isoformat()
        trade_id = f"deriv_{coin}_{direction}_{timestamp[:19].replace(':', '-')}"
        
        position = Position(
            trade_id=trade_id,
            symbol=coin.upper(),
            direction=direction,
            leverage=leverage,
            entry_price=entry_price,
            position_size_usd=allocation,
            position_size_coins=round(position_size_coins, 8),
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            entry_timestamp=timestamp,
        )
        
        # Save
        self.positions[trade_id] = position
        self._save_positions()
        
        print(f"✅ OPENED: {direction} {coin} @ ${entry_price:,.2f}")
        print(f"   Leverage: {leverage}x")
        print(f"   Size: ${allocation:.2f} ({position_size_coins:.8f} {coin})")
        print(f"   Stop: ${stop_loss:,.2f} (-3%)")
        print(f"   Target: ${take_profit:,.2f} (+6%)")
        print(f"   Trade ID: {trade_id}")
        
        # Create MONITOR task
        self.create_monitor_task(position)
        
        return {
            'status': 'opened',
            'trade_id': trade_id,
            'symbol': coin.upper(),
            'direction': direction,
            'entry_price': entry_price,
            'position_size_coins': round(position_size_coins, 8),
            'position_size_usd': allocation,
            'leverage': leverage,
            'stop_loss': round(stop_loss, 2),
            'take_profit': round(take_profit, 2),
        }
    
    def close_position(self, trade_id: str, reason: str = 'manual') -> Dict:
        """Close position"""
        if trade_id not in self.positions:
            return {'status': 'error', 'reason': f'Position {trade_id} not found'}
        
        position = self.positions[trade_id]
        
        if position.status != 'OPEN':
            return {'status': 'error', 'reason': f'Position already {position.status}'}
        
        # Get exit price
        exit_price = self._get_price(position.symbol)
        
        # Calculate PnL
        if position.direction == 'LONG':
            pnl_pct = (exit_price - position.entry_price) / position.entry_price
        else:
            pnl_pct = (position.entry_price - exit_price) / position.entry_price
        
        pnl_usd = pnl_pct * position.position_size_usd
        
        # Update position
        position.status = 'CLOSED'
        position.exit_price = exit_price
        position.exit_timestamp = datetime.now(timezone.utc).isoformat()
        position.exit_reason = reason
        position.final_pnl_usd = pnl_usd
        position.final_pnl_pct = pnl_pct
        
        self._save_positions()
        
        print(f"✅ CLOSED: {position.direction} {position.symbol}")
        print(f"   Exit: ${exit_price:,.2f}")
        print(f"   PnL: ${pnl_usd:.2f} ({pnl_pct*100:+.2f}%)")
        print(f"   Reason: {reason}")
        
        return {
            'status': 'closed',
            'trade_id': trade_id,
            'symbol': position.symbol,
            'direction': position.direction,
            'entry_price': position.entry_price,
            'exit_price': exit_price,
            'pnl_usd': round(pnl_usd, 2),
            'pnl_pct': round(pnl_pct * 100, 2),
            'reason': reason,
        }
    
    def create_monitor_task(self, position: Position) -> Optional[Dict]:
        """Create Kanban monitor task (re-creates every 5 min)"""
        try:
            from kanban import kanban_create
        except ImportError:
            print("Note: Kanban not available (standalone mode)")
            return None
        
        task = kanban_create(
            title=f"👁️ Monitor: {position.symbol} {position.direction}",
            body=f"""
POSITION MONITOR - DERIVATIVES

Trade ID: {position.trade_id}
Symbol: {position.symbol}
Direction: {position.direction}
Leverage: {position.leverage}x

Entry: ${position.entry_price:,.2f}
Stop-Loss: ${position.stop_loss:,.2f}
Take-Profit: ${position.take_profit:,.2f}

Opened: {position.entry_timestamp}

Monitoring:
- Check every 5 minutes
- Exit on stop-loss or take-profit
- Time expiry: 48 hours
""",
            assignee='trading-derivatives',
            metadata={
                'task_type': 'monitor',
                'trade_id': position.trade_id,
                'symbol': position.symbol,
                'direction': position.direction,
                'check_interval_seconds': 300,
            }
        )
        
        print(f"✅ Monitor task: {task.get('id', 'UNKNOWN')}")
        return task
    
    def handle_monitor_task(self, metadata: Dict) -> Dict:
        """Handle monitor task - check exit or re-monitor"""
        trade_id = metadata.get('trade_id')
        
        if not trade_id or trade_id not in self.positions:
            return {'status': 'error', 'reason': f'Position {trade_id} not found'}
        
        position = self.positions[trade_id]
        
        if position.status != 'OPEN':
            return {'status': 'skipped', 'reason': f'Already {position.status}'}
        
        # Check exit
        current_price = self._get_price(position.symbol)
        position_dict = {
            'direction': position.direction,
            'entry_price': position.entry_price,
            'stop_loss': position.stop_loss,
            'take_profit': position.take_profit,
            'opened_at': position.entry_timestamp,
        }
        
        should_exit, exit_reason = should_exit_position(position_dict, current_price)
        
        if should_exit:
            # Create CLOSE task
            try:
                from kanban import kanban_create
                close_task = kanban_create(
                    title=f"🔴 CLOSE: {position.symbol} {position.direction}",
                    body=f"""
CLOSE POSITION

Trade ID: {trade_id}
Exit Reason: {exit_reason}
Current Price: ${current_price:,.2f}
""",
                    assignee='trading-derivatives',
                    metadata={
                        'task_type': 'close',
                        'trade_id': trade_id,
                        'exit_reason': exit_reason,
                    }
                )
                print(f"✅ Close task: {close_task.get('id')}")
                return {'status': 'exit_detected', 'close_task_id': close_task.get('id')}
            except ImportError:
                return self.close_position(trade_id, exit_reason)
        else:
            # Re-create MONITOR
            self.create_monitor_task(position)
            return {'status': 'monitoring', 'current_price': current_price}
    
    def handle_close_task(self, metadata: Dict) -> Dict:
        """Handle close task"""
        trade_id = metadata.get('trade_id')
        exit_reason = metadata.get('exit_reason', 'manual')
        return self.close_position(trade_id, exit_reason)


# ============================================================================
# KANBAN ENTRY POINT
# ============================================================================

def handle_kanban_task(task_metadata: Dict) -> Dict:
    """
    Main entry point for Kanban tasks.
    
    Task Types:
    - Entry: direction, coin, leverage, allocation
    - Monitor: task_type='monitor', trade_id
    - Close: task_type='close', trade_id
    """
    bot = DerivativesBot()
    
    task_type = task_metadata.get('task_type', 'entry')
    
    if task_type == 'monitor':
        return bot.handle_monitor_task(task_metadata)
    elif task_type == 'close':
        return bot.handle_close_task(task_metadata)
    else:
        # Entry task (LONG/SHORT)
        direction = task_metadata.get('direction', '').upper()
        if direction in ['LONG', 'SHORT']:
            return bot.open_position(task_metadata)
        else:
            return {'status': 'error', 'reason': f'Unknown task type: {task_type}'}


if __name__ == '__main__':
    print("="*80)
    print("DERIVATIVES BOT - KANBAN TEST")
    print("="*80)
    
    # Test open
    print("\n📊 Test 1: Open LONG BTC")
    result = handle_kanban_task({
        'direction': 'LONG',
        'coin': 'BTC',
        'leverage': 2,
        'allocation': 5.00,
    })
    print(f"Status: {result['status']}")
    
    # Test monitor
    print("\n📊 Test 2: Monitor Task")
    if result['status'] == 'opened':
        monitor_result = handle_kanban_task({
            'task_type': 'monitor',
            'trade_id': result['trade_id'],
        })
        print(f"Monitor: {monitor_result['status']}")
    
    print("\n" + "="*80)
