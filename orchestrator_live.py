#!/usr/bin/env python3
"""
Orchestrator - Live Multi-Bot Coordination (Kanban-Driven)

Reads discovery results from Data Worker and creates Kanban tasks for:
- Mean Reversion Bot (spot trading)
- Derivatives Bot (LONG/SHORT with leverage)

Strategy Integration:
- Uses derivatives_strategy.should_enter_long/short() for signals
- Capital allocation: 70% spot ($17.50), 30% derivatives ($7.50)
- Coordination: conviction_boost, hedge, pure_derivatives

CRITICAL: Uses ONLY live data from discovery_results.json
NO MOCK DATA - skips coins with missing data.

Usage:
  python3 orchestrator_live.py

Or via Kanban:
  hermes kanban create "🎯 Orchestrator" --assignee trading-orchestrator
"""

import os
import sys
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add trading_system to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import derivatives strategy
from derivatives_strategy import (
    should_enter_long,
    should_enter_short,
    get_available_derivatives_capital,
    can_open_new_position,
    DERIVATIVES_ALLOCATION,
    MAX_PER_TRADE,
)

# State directory
STATE_DIR = Path(__file__).parent / 'state'
DISCOVERY_FILE = STATE_DIR / 'discovery_results.json'
POSITIONS_FILE = STATE_DIR / 'positions.json'

# Capital limits (user's rules)
MAX_CAPITAL = 25.00  # $25 total
MAX_PER_POSITION = 5.00  # $5 per trade


# ============================================================================
# ORCHESTRATOR
# ============================================================================

class Orchestrator:
    """
    Live orchestrator - reads discovery results and routes to bots via Kanban.
    
    Coordination types:
    - conviction_boost: Spot + Derivatives LONG (high conviction)
    - hedge: Spot + Derivatives SHORT (protect spot)
    - pure_derivatives: Derivatives only (no spot conflict)
    
    NO MOCK DATA - uses only live discovery results.
    """
    
    def __init__(self):
        """Initialize orchestrator"""
        self.discovery_data = None
        self.positions = None
        self.tasks_to_create = []
        
    def load_discovery_results(self) -> bool:
        """Load discovery results from Data Worker"""
        if not DISCOVERY_FILE.exists():
            print(f"❌ Discovery file not found: {DISCOVERY_FILE}")
            print(f"   Run data_worker_live.py first")
            return False
        
        try:
            with open(DISCOVERY_FILE, 'r') as f:
                self.discovery_data = json.load(f)
            
            # Check data freshness (max 15 minutes old)
            timestamp = self.discovery_data.get('timestamp', '')
            if timestamp:
                data_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                age = (datetime.now(timezone.utc) - data_time).total_seconds() / 60
                
                if age > 15:
                    print(f"⚠️  Discovery data is {age:.0f} minutes old (max 15)")
                    print(f"   Consider running data_worker_live.py again")
            
            coin_count = len(self.discovery_data.get('coins', {}))
            print(f"✅ Loaded discovery results: {coin_count} coins")
            print(f"   Data age: {age:.1f} minutes")
            return True
        
        except Exception as e:
            print(f"❌ Error loading discovery results: {e}")
            return False
    
    def load_positions(self) -> bool:
        """Load current positions"""
        if not POSITIONS_FILE.exists():
            print(f"⚠️  No positions file found, starting fresh")
            self.positions = {
                'spot_positions': [],
                'derivatives_positions': [],
                'total_deployed': 0.0
            }
            return True
        
        try:
            with open(POSITIONS_FILE, 'r') as f:
                self.positions = json.load(f)
            
            # Ensure structure exists
            if 'spot_positions' not in self.positions:
                self.positions['spot_positions'] = []
            if 'derivatives_positions' not in self.positions:
                self.positions['derivatives_positions'] = []
            if 'total_deployed' not in self.positions:
                spot_total = sum(p.get('size_usd', 0) for p in self.positions['spot_positions'])
                deriv_total = sum(p.get('size_usd', 0) for p in self.positions['derivatives_positions'])
                self.positions['total_deployed'] = spot_total + deriv_total
            
            spot_count = len(self.positions['spot_positions'])
            deriv_count = len(self.positions['derivatives_positions'])
            deployed = self.positions.get('total_deployed', 0)
            
            print(f"✅ Loaded positions: {spot_count} spot, {deriv_count} derivatives")
            print(f"   Capital deployed: ${deployed:.2f} / ${MAX_CAPITAL:.2f}")
            return True
        
        except Exception as e:
            print(f"❌ Error loading positions: {e}")
            self.positions = {
                'spot_positions': [],
                'derivatives_positions': [],
                'total_deployed': 0.0
            }
            return True
    
    def get_available_capital(self) -> float:
        """Calculate available capital"""
        deployed = self.positions.get('total_deployed', 0.0)
        return max(0.0, MAX_CAPITAL - deployed)
    
    def is_holding_spot(self, coin: str) -> bool:
        """Check if already holding spot position for coin"""
        coin = coin.upper()
        for pos in self.positions.get('spot_positions', []):
            if pos.get('coin', '').upper() == coin:
                return True
        return False
    
    def has_derivatives_position(self, coin: str, direction: str) -> bool:
        """Check if already has derivatives position for coin"""
        coin = coin.upper()
        direction = direction.upper()
        for pos in self.positions.get('derivatives_positions', []):
            if (pos.get('coin', '').upper() == coin and 
                pos.get('direction', '').upper() == direction):
                return True
        return False
    
    def evaluate_coin(self, coin: str, data: Dict) -> List[Dict]:
        """
        Evaluate a single coin using derivatives strategy.
        
        Args:
            coin: Coin symbol
            data: Discovery data for this coin
        
        Returns:
            List of task definitions (may be empty)
        """
        tasks = []
        
        # Skip if no live price (NO MOCK DATA)
        if data.get('price') is None:
            print(f"  ❌ {coin}: No live price - SKIPPED")
            return tasks
        
        # Get spot position for this coin (if any)
        spot_position = None
        for pos in self.positions.get('spot_positions', []):
            if pos.get('coin', '').upper() == coin.upper():
                spot_position = pos
                break
        
        # Get derivatives capital
        deriv_positions = self.positions.get('derivatives_positions', [])
        available_deriv_capital = get_available_derivatives_capital(deriv_positions)
        
        # Check derivatives LONG signal
        if can_open_new_position(deriv_positions) and not self.has_derivatives_position(coin, 'LONG'):
            enter_long, long_signal = should_enter_long(
                data,
                spot_position=spot_position,
                available_capital=available_deriv_capital,
            )
            
            if enter_long:
                tasks.append({
                    'type': 'derivatives',
                    'action': 'LONG',
                    'coin': coin,
                    'reason': long_signal.reason,
                    'metadata': {
                        'direction': 'LONG',
                        'leverage': long_signal.leverage,
                        'entry_price': long_signal.entry_price,
                        'stop_loss': long_signal.stop_loss,
                        'take_profit': long_signal.take_profit,
                        'allocation': long_signal.allocation,
                        'rsi': long_signal.rsi,
                        'etherscan_signal': long_signal.etherscan_signal,
                        'coordination': {
                            'type': long_signal.coordination_type,
                            'spot_position': spot_position is not None,
                        }
                    }
                })
        
        # Check derivatives SHORT signal
        if can_open_new_position(deriv_positions) and not self.has_derivatives_position(coin, 'SHORT'):
            enter_short, short_signal = should_enter_short(
                data,
                spot_position=spot_position,
                available_capital=available_deriv_capital,
            )
            
            if enter_short:
                tasks.append({
                    'type': 'derivatives',
                    'action': 'SHORT',
                    'coin': coin,
                    'reason': short_signal.reason,
                    'metadata': {
                        'direction': 'SHORT',
                        'leverage': short_signal.leverage,
                        'entry_price': short_signal.entry_price,
                        'stop_loss': short_signal.stop_loss,
                        'take_profit': short_signal.take_profit,
                        'allocation': short_signal.allocation,
                        'rsi': short_signal.rsi,
                        'etherscan_signal': short_signal.etherscan_signal,
                        'coordination': {
                            'type': short_signal.coordination_type,
                            'spot_position': spot_position is not None,
                        }
                    }
                })
        
        # Check spot signals (mean reversion) - only if no derivatives conflict
        rsi = data.get('rsi', 100)
        rsi_available = data.get('rsi_available', False)
        available_capital = self.get_available_capital()
        holding_spot = self.is_holding_spot(coin)
        
        if rsi_available and rsi < 30 and not holding_spot and available_capital >= MAX_PER_POSITION:
            # Check no conflicting derivatives SHORT
            if not self.has_derivatives_position(coin, 'SHORT'):
                tasks.append({
                    'type': 'spot',
                    'action': 'BUY',
                    'coin': coin,
                    'reason': f'RSI oversold ({rsi:.1f} < 30)',
                    'metadata': {
                        'rsi': rsi,
                        'price': data.get('price'),
                        'etherscan_signal': data.get('etherscan_signal', 'HOLD'),
                        'coordination': {
                            'type': 'spot_entry',
                        }
                    }
                })
        
        return tasks
    
    def select_best_signals(self, all_tasks: List[Dict]) -> List[Dict]:
        """
        Select the best signals based on RSI extremity and capital limits.
        
        Automatically chooses:
        - LONG: Lowest RSI (most oversold) first
        - SHORT: Highest RSI (most overbought) first
        
        Respects capital limits:
        - Derivatives: $7.50 max (30% of $25)
        - Max per trade: $5.00
        
        Args:
            all_tasks: List of all potential tasks
        
        Returns:
            List of selected tasks (within capital limits)
        """
        if not all_tasks:
            return []
        
        # Separate LONG and SHORT signals
        long_signals = [t for t in all_tasks if t.get('action') == 'LONG']
        short_signals = [t for t in all_tasks if t.get('action') == 'SHORT']
        
        # Sort by RSI extremity
        # LONG: Lowest RSI first (most oversold = best)
        long_signals.sort(key=lambda x: x['metadata'].get('rsi', 100))
        
        # SHORT: Highest RSI first (most overbought = best)
        short_signals.sort(key=lambda x: x['metadata'].get('rsi', 0), reverse=True)
        
        print()
        print("="*80)
        print("SIGNAL RANKING (by RSI extremity)")
        print("="*80)
        print()
        
        if long_signals:
            print("🟢 LONG Signals (sorted by RSI - lowest first):")
            for i, signal in enumerate(long_signals, 1):
                coin = signal['coin']
                rsi = signal['metadata'].get('rsi', 0)
                etherscan = signal['metadata'].get('etherscan_signal', 'HOLD')
                print(f"  {i}. {coin}: RSI {rsi:.1f} ({etherscan})")
            print()
        
        if short_signals:
            print("🔴 SHORT Signals (sorted by RSI - highest first):")
            for i, signal in enumerate(short_signals, 1):
                coin = signal['coin']
                rsi = signal['metadata'].get('rsi', 0)
                etherscan = signal['metadata'].get('etherscan_signal', 'HOLD')
                print(f"  {i}. {coin}: RSI {rsi:.1f} ({etherscan})")
            print()
        
        # Select within capital limits
        selected = []
        remaining_capital = DERIVATIVES_ALLOCATION  # $7.50
        
        # Alternate between LONG and SHORT for diversification (optional)
        # For now: take best LONGs first, then best SHORTs
        
        # Select LONG signals
        for signal in long_signals:
            allocation = signal['metadata'].get('allocation', MAX_PER_TRADE)
            if allocation <= remaining_capital:
                selected.append(signal)
                remaining_capital -= allocation
                print(f"✅ SELECTED: LONG {signal['coin']} (RSI {signal['metadata']['rsi']:.1f}) - ${allocation:.2f}")
            else:
                print(f"⏭️  SKIPPED: LONG {signal['coin']} - insufficient capital (${remaining_capital:.2f} left)")
        
        # Select SHORT signals
        for signal in short_signals:
            allocation = signal['metadata'].get('allocation', MAX_PER_TRADE)
            if allocation <= remaining_capital:
                selected.append(signal)
                remaining_capital -= allocation
                print(f"✅ SELECTED: SHORT {signal['coin']} (RSI {signal['metadata']['rsi']:.1f}) - ${allocation:.2f}")
            else:
                print(f"⏭️  SKIPPED: SHORT {signal['coin']} - insufficient capital (${remaining_capital:.2f} left)")
        
        print()
        print(f"Capital used: ${DERIVATIVES_ALLOCATION - remaining_capital:.2f} / ${DERIVATIVES_ALLOCATION:.2f}")
        print(f"Remaining: ${remaining_capital:.2f}")
        print()
        
        return selected
    
    def create_tasks(self) -> int:
        """
        Create Kanban tasks for best signals (auto-selected by RSI extremity).
        
        Automatically selects the highest conviction signals within capital limits.
        
        Returns:
            Number of tasks created
        """
        if not self.discovery_data:
            return 0
        
        coins = self.discovery_data.get('coins', {})
        all_potential_tasks = []
        
        print()
        print("="*80)
        print("ORCHESTRATOR - EVALUATING COINS")
        print("="*80)
        print()
        
        # First pass: collect all potential signals
        for coin, data in coins.items():
            print(f"Evaluating {coin}...")
            print(f"  Price: ${data.get('price', 'N/A')}")
            print(f"  RSI: {data.get('rsi', 'N/A')}")
            print(f"  Etherscan: {data.get('etherscan_signal', 'HOLD')} ({data.get('etherscan_score', 50)}/100)")
            
            # Evaluate coin
            tasks = self.evaluate_coin(coin, data)
            
            if tasks:
                for task in tasks:
                    all_potential_tasks.append(task)
            else:
                print(f"  ℹ️  No action")
            print()
        
        # Second pass: select best signals within capital limits
        print("="*80)
        print("AUTOMATED SIGNAL SELECTION")
        print("="*80)
        print()
        
        selected_tasks = self.select_best_signals(all_potential_tasks)
        
        # Store selected tasks for submission
        self.tasks_to_create = selected_tasks
        
        return len(selected_tasks)
    
    def submit_tasks(self) -> int:
        """
        Submit all tasks to Kanban.
        
        Returns:
            Number of tasks submitted
        """
        if not self.tasks_to_create:
            print("="*80)
            print("No tasks to create")
            print("="*80)
            return 0
        
        print("="*80)
        print(f"CREATING {len(self.tasks_to_create)} KANBAN TASKS")
        print("="*80)
        print()
        
        submitted = 0
        
        for task_def in self.tasks_to_create:
            task_type = task_def.get('type', '')
            action = task_def.get('action', '')
            coin = task_def.get('coin', '')
            reason = task_def.get('reason', '')
            metadata = task_def.get('metadata', {})
            
            # Create task title
            if task_type == 'derivatives':
                leverage = metadata.get('leverage', 2)
                emoji = '🟢' if action == 'LONG' else '🔴'
                title = f"{emoji} {action} {coin} - Derivatives ({leverage}x)"
                assignee = 'trading-derivatives'
            elif task_type == 'spot':
                emoji = '🟢' if action == 'BUY' else '🔴'
                title = f"{emoji} {action} {coin} - Mean Reversion"
                assignee = 'trading-mean-reversion'
            else:
                continue
            
            # Create via subprocess (Kanban CLI)
            try:
                cmd = [
                    'hermes', 'kanban', 'create',
                    title,
                    '--assignee', assignee,
                    '--metadata', json.dumps(metadata)
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    # Extract task ID from output
                    output = result.stdout.strip()
                    if 'Task ID:' in output:
                        task_id = output.split('Task ID:')[1].strip().split()[0]
                        print(f"✅ Created: {title}")
                        print(f"   Task ID: {task_id}")
                        print(f"   Reason: {reason}")
                        submitted += 1
                    else:
                        print(f"⚠️  Created: {title} (ID not parsed)")
                        submitted += 1
                else:
                    print(f"❌ Failed to create {title}: {result.stderr.strip()}")
            
            except Exception as e:
                print(f"❌ Error creating {title}: {e}")
        
        print()
        print("="*80)
        print(f"SUMMARY: {submitted}/{len(self.tasks_to_create)} tasks created")
        print("="*80)
        
        return submitted
    
    def run(self) -> dict:
        """
        Run full orchestrator cycle.
        
        Returns:
            Summary dict
        """
        start_time = datetime.now(timezone.utc)
        
        print("="*80)
        print("ORCHESTRATOR - LIVE MULTI-BOT COORDINATION")
        print("="*80)
        print()
        
        # Load data
        if not self.load_discovery_results():
            return {'success': False, 'error': 'Failed to load discovery results'}
        
        if not self.load_positions():
            return {'success': False, 'error': 'Failed to load positions'}
        
        # Evaluate and create tasks
        tasks_evaluated = self.create_tasks()
        tasks_submitted = self.submit_tasks()
        
        # Summary
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        summary = {
            'success': True,
            'duration_seconds': round(duration, 2),
            'coins_evaluated': len(self.discovery_data.get('coins', {})),
            'tasks_created': tasks_submitted,
            'capital_deployed': self.positions.get('total_deployed', 0),
            'capital_available': self.get_available_capital(),
            'timestamp': end_time.isoformat(),
        }
        
        print()
        print("="*80)
        print("ORCHESTRATOR - SUMMARY")
        print("="*80)
        print(f"  Duration: {duration:.1f} seconds")
        print(f"  Coins evaluated: {summary['coins_evaluated']}")
        print(f"  Tasks created: {summary['tasks_created']}")
        print(f"  Capital deployed: ${summary['capital_deployed']:.2f}")
        print(f"  Capital available: ${summary['capital_available']:.2f}")
        print()
        print("✅ Orchestrator completed successfully")
        
        return summary


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    orchestrator = Orchestrator()
    result = orchestrator.run()
    
    if not result.get('success'):
        sys.exit(1)
