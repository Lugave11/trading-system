#!/usr/bin/env python3
"""
Position Manager - State Management for Kanban-Driven Trading

Tracks open positions across Orchestrator cycles.
Persists to JSON file for crash recovery.

Usage:
    from position_manager import PositionManager
    
    pm = PositionManager()
    
    # Add position (after method bot entry)
    pm.add_position(
        symbol='BTC',
        side='LONG',
        entry_price=68500,
        quantity=0.00036,
        method='mean_reversion',
        stop_loss=66445,
        take_profit=72610,
        task_id='t_entry_abc123'
    )
    
    # Remove position (after exit)
    pm.remove_position('BTC')
    
    # Check if we have positions
    if pm.has_positions():
        positions = pm.get_all_positions()
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


class PositionManager:
    def __init__(self, state_file: str = None):
        if state_file is None:
            state_file = str(Path(__file__).parent / 'state' / 'open_positions.json')
        
        self.state_file = state_file
        self.positions = self.load()
    
    def load(self) -> List[Dict]:
        """Load positions from state file"""
        try:
            path = Path(self.state_file)
            if not path.exists():
                # Create empty state
                path.parent.mkdir(parents=True, exist_ok=True)
                self.save([])
                return []
            
            with open(path, 'r') as f:
                data = json.load(f)
                return data.get('positions', [])
        except Exception as e:
            print(f"⚠ Error loading positions: {e}")
            return []
    
    def save(self, positions: List[Dict] = None):
        """Persist positions to state file"""
        if positions is not None:
            self.positions = positions
        
        data = {
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'positions': self.positions,
            'count': len(self.positions),
        }
        
        # Ensure directory exists
        path = Path(self.state_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def add_position(self, symbol: str, side: str, entry_price: float, 
                     quantity: float, method: str, stop_loss: float, 
                     take_profit: float, task_id: str = None):
        """Add new position after trade execution"""
        position = {
            'symbol': symbol,
            'side': side,
            'entry_price': entry_price,
            'entry_time': datetime.now(timezone.utc).isoformat(),
            'quantity': quantity,
            'method': method,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'task_id': task_id,
            'status': 'open',
        }
        
        # Remove existing position for same symbol (shouldn't happen, but safety)
        self.positions = [p for p in self.positions if p['symbol'] != symbol]
        
        self.positions.append(position)
        self.save()
        
        print(f"✅ Position added: {symbol} {side} @ ${entry_price}")
    
    def remove_position(self, symbol: str) -> Optional[Dict]:
        """Remove position after exit"""
        for i, position in enumerate(self.positions):
            if position['symbol'] == symbol:
                removed = self.positions.pop(i)
                self.save()
                print(f"✅ Position removed: {symbol} (was {removed['side']} @ ${removed['entry_price']})")
                return removed
        
        print(f"⚠ Position not found: {symbol}")
        return None
    
    def get_all_positions(self) -> List[Dict]:
        """Return all open positions"""
        return self.positions
    
    def has_positions(self) -> bool:
        """Check if we have any open positions"""
        return len(self.positions) > 0
    
    def get_position_symbols(self) -> List[str]:
        """Return list of symbols with open positions"""
        return [p['symbol'] for p in self.positions]
    
    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get specific position by symbol"""
        for position in self.positions:
            if position['symbol'] == symbol:
                return position
        return None
    
    def update_position_status(self, symbol: str, status: str):
        """Update position status (open, closed, stopped, etc.)"""
        position = self.get_position(symbol)
        if position:
            position['status'] = status
            self.save()
    
    def get_total_capital_deployed(self) -> float:
        """Calculate total capital deployed across all positions"""
        total = 0
        for position in self.positions:
            total += position['entry_price'] * position['quantity']
        return total
    
    def get_unrealized_pnl(self, current_prices: Dict[str, float]) -> Dict:
        """
        Calculate unrealized PnL for all positions.
        
        Args:
            current_prices: Dict of {symbol: current_price}
        
        Returns:
            {
                'total_pnl_usd': float,
                'total_pnl_pct': float,
                'positions': [
                    {
                        'symbol': 'BTC',
                        'pnl_usd': float,
                        'pnl_pct': float,
                        'current_price': float,
                    },
                    ...
                ]
            }
        """
        total_pnl_usd = 0
        total_capital = 0
        position_pnls = []
        
        for position in self.positions:
            symbol = position['symbol']
            if symbol not in current_prices:
                continue
            
            current_price = current_prices[symbol]
            entry_price = position['entry_price']
            quantity = position['quantity']
            
            # Calculate PnL
            pnl_usd = (current_price - entry_price) * quantity
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
            
            total_pnl_usd += pnl_usd
            total_capital += entry_price * quantity
            
            position_pnls.append({
                'symbol': symbol,
                'pnl_usd': pnl_usd,
                'pnl_pct': pnl_pct,
                'current_price': current_price,
                'entry_price': entry_price,
            })
        
        total_pnl_pct = (total_pnl_usd / total_capital * 100) if total_capital > 0 else 0
        
        return {
            'total_pnl_usd': total_pnl_usd,
            'total_pnl_pct': total_pnl_pct,
            'total_capital_deployed': total_capital,
            'positions': position_pnls,
        }


# ============================================================================
# CLI / Testing
# ============================================================================

if __name__ == '__main__':
    # Test Position Manager
    pm = PositionManager()
    
    print("Testing Position Manager...")
    print(f"Current positions: {pm.get_all_positions()}")
    print(f"Has positions: {pm.has_positions()}")
    
    # Add test position
    pm.add_position(
        symbol='BTC',
        side='LONG',
        entry_price=68500,
        quantity=0.00036,
        method='mean_reversion',
        stop_loss=66445,
        take_profit=72610,
        task_id='test_123'
    )
    
    print(f"After add: {pm.get_all_positions()}")
    print(f"Symbols: {pm.get_position_symbols()}")
    
    # Remove test position
    pm.remove_position('BTC')
    print(f"After remove: {pm.get_all_positions()}")
