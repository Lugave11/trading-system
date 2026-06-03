#!/usr/bin/env python3
"""
Trading Orchestrator - Multi-Bot Coordination

Routes signals to appropriate bots (spot, derivatives) with:
- Conflict detection (no contradictory positions)
- Hedging logic (spot + derivatives SHORT)
- Conviction boosting (spot + derivatives LONG)
- Capital allocation enforcement ($25 max)

Reads from: state/positions.json (source of truth)
Writes to: Kanban board (creates tasks for bots)
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(SCRIPT_DIR, 'state')
POSITIONS_FILE = os.path.join(STATE_DIR, 'positions.json')

# Capital limits
MAX_CAPITAL = 25.00
MAX_SINGLE_POSITION = 5.00  # Max per position (spot or derivatives)


class TradingOrchestrator:
    """
    Central coordination layer for all trading bots.
    
    Responsibilities:
    1. Load existing positions (spot + derivatives)
    2. Evaluate new signals from Data Worker
    3. Detect conflicts BEFORE routing
    4. Create Kanban tasks with coordination metadata
    5. Enforce capital limits
    """
    
    def __init__(self):
        self.positions = self.load_positions()
        self.kanban_tasks = []
        self.conflicts_detected = []
        self.hedges_created = []
        self.conviction_boosts = []
    
    def load_positions(self) -> Dict:
        """Load current positions from state file."""
        if not os.path.exists(POSITIONS_FILE):
            return {
                'spot_positions': [],
                'derivatives_positions': [],
                'last_updated': datetime.now().isoformat(),
                'total_capital_deployed': 0.0,
                'capital_limit': MAX_CAPITAL
            }
        
        with open(POSITIONS_FILE, 'r') as f:
            return json.load(f)
    
    def get_spot_holdings(self) -> List[str]:
        """Get list of coins with active spot positions."""
        return [p['coin'] for p in self.positions.get('spot_positions', [])]
    
    def get_derivatives_positions(self) -> List[Dict]:
        """Get list of active derivatives positions."""
        return self.positions.get('derivatives_positions', [])
    
    def get_spot_position(self, coin: str) -> Optional[Dict]:
        """Get spot position for specific coin."""
        for pos in self.positions.get('spot_positions', []):
            if pos['coin'] == coin:
                return pos
        return None
    
    def get_derivatives_position(self, coin: str, direction: str = None) -> Optional[Dict]:
        """Get derivatives position for specific coin (optionally filter by direction)."""
        for pos in self.positions.get('derivatives_positions', []):
            if pos['coin'] == coin:
                if direction is None or pos['direction'] == direction:
                    return pos
        return None
    
    def calculate_deployed_capital(self) -> float:
        """Calculate total capital currently deployed."""
        spot_capital = sum(p.get('size_usd', 0) for p in self.positions.get('spot_positions', []))
        deriv_capital = sum(p.get('size_usd', 0) for p in self.positions.get('derivatives_positions', []))
        return spot_capital + deriv_capital
    
    def check_capital_available(self, required: float) -> bool:
        """Check if capital is available for new position."""
        deployed = self.calculate_deployed_capital()
        return (deployed + required) <= MAX_CAPITAL
    
    def evaluate_coin(self, coin_data: Dict) -> List[Dict]:
        """
        Evaluate single coin and determine appropriate actions.
        
        Args:
            coin_data: Dict with keys:
                - symbol: str (e.g., 'BTC')
                - rsi: float
                - etherscan_signal: str ('BUY', 'SELL', 'HOLD', etc.)
                - etherscan_score: float (0-100)
                - price: float
        
        Returns:
            List of task definitions (may be 0, 1, or 2 tasks)
        """
        coin = coin_data['symbol']
        rsi = coin_data['rsi']
        etherscan = coin_data.get('etherscan_signal', 'HOLD')
        etherscan_score = coin_data.get('etherscan_score', 50)
        price = coin_data.get('price', 0)
        
        spot_holdings = self.get_spot_holdings()
        derivatives_positions = self.get_derivatives_positions()
        has_spot = coin in spot_holdings
        has_deriv_long = self.get_derivatives_position(coin, 'LONG') is not None
        has_deriv_short = self.get_derivatives_position(coin, 'SHORT') is not None
        
        tasks = []
        
        # === SPOT EVALUATION (Mean Reversion Bot) ===
        
        if not has_spot and rsi < 30:
            # No spot position + oversold → BUY signal
            if self.check_capital_available(MAX_SINGLE_POSITION):
                tasks.append({
                    'assignee': 'trading-mean-reversion',
                    'action': 'BUY',
                    'coin': coin,
                    'reason': f'RSI oversold ({rsi:.1f} < 30)',
                    'metadata': {
                        'rsi': rsi,
                        'etherscan_signal': etherscan,
                        'etherscan_score': etherscan_score,
                        'coordination': {
                            'type': 'spot_entry',
                            'potential_derivatives': 'LONG' if etherscan in ['BUY', 'STRONG_BUY'] else None
                        },
                        'conflict_check': 'passed'
                    }
                })
            else:
                self.conflicts_detected.append({
                    'coin': coin,
                    'issue': 'Insufficient capital for spot BUY',
                    'deployed': self.calculate_deployed_capital()
                })
        
        elif has_spot and rsi > 50:
            # Holding spot + mean reversion complete → SELL signal
            tasks.append({
                'assignee': 'trading-mean-reversion',
                'action': 'SELL',
                'coin': coin,
                'reason': f'Mean reversion complete (RSI {rsi:.1f} > 50)',
                'metadata': {
                    'rsi': rsi,
                    'spot_entry': self.get_spot_position(coin),
                    'coordination': {
                        'type': 'spot_exit'
                    }
                }
            })
        
        # === DERIVATIVES EVALUATION ===
        
        # Scenario 1: Hedge existing spot (RSI > 70, overbought)
        if has_spot and rsi > 70 and not has_deriv_short:
            if self.check_capital_available(MAX_SINGLE_POSITION):
                tasks.append({
                    'assignee': 'trading-derivatives',
                    'action': 'SHORT',
                    'coin': coin,
                    'reason': f'Hedge overbought spot (RSI {rsi:.1f} > 70)',
                    'metadata': {
                        'rsi': rsi,
                        'leverage': 2,
                        'coordination': {
                            'type': 'hedge',
                            'hedging': 'spot_position',
                            'spot_coin': coin,
                            'spot_entry': self.get_spot_position(coin)
                        },
                        'conflict_check': 'passed'  # Intentional hedge
                    }
                })
                self.hedges_created.append({
                    'coin': coin,
                    'spot_entry': self.get_spot_position(coin),
                    'derivatives_action': 'SHORT'
                })
        
        # Scenario 2: High conviction LONG (spot + derivatives, RSI < 30, Etherscan BUY)
        elif not has_spot and rsi < 30 and etherscan in ['BUY', 'STRONG_BUY'] and not has_deriv_long:
            # Already added spot BUY above, now add derivatives LONG
            if self.check_capital_available(MAX_SINGLE_POSITION):
                tasks.append({
                    'assignee': 'trading-derivatives',
                    'action': 'LONG',
                    'coin': coin,
                    'reason': f'High conviction LONG (RSI {rsi:.1f} + Etherscan {etherscan})',
                    'metadata': {
                        'rsi': rsi,
                        'leverage': 2 if etherscan == 'BUY' else 3,
                        'coordination': {
                            'type': 'conviction_boost',
                            'coordinated_with': 'spot_BUY',
                            'etherscan_signal': etherscan
                        },
                        'conflict_check': 'passed'
                    }
                })
                self.conviction_boosts.append({
                    'coin': coin,
                    'spot_action': 'BUY',
                    'derivatives_action': 'LONG',
                    'etherscan': etherscan
                })
        
        # Scenario 3: Pure derivatives SHORT (no spot, RSI > 70)
        elif not has_spot and rsi > 70 and not has_deriv_short and not has_deriv_long:
            if self.check_capital_available(MAX_SINGLE_POSITION):
                tasks.append({
                    'assignee': 'trading-derivatives',
                    'action': 'SHORT',
                    'coin': coin,
                    'reason': f'Overbought (RSI {rsi:.1f} > 70), no spot conflict',
                    'metadata': {
                        'rsi': rsi,
                        'leverage': 2,
                        'coordination': {
                            'type': 'pure_derivatives'
                        },
                        'conflict_check': 'passed'
                    }
                })
        
        # Scenario 4: Pure derivatives LONG (no spot, RSI < 30, Etherscan BUY)
        elif not has_spot and rsi < 30 and etherscan in ['BUY', 'STRONG_BUY'] and not has_deriv_long:
            # Only if NOT doing spot (e.g., capital constraint or skipped)
            if not any(t['coin'] == coin and t['assignee'] == 'trading-mean-reversion' for t in tasks):
                if self.check_capital_available(MAX_SINGLE_POSITION):
                    tasks.append({
                        'assignee': 'trading-derivatives',
                        'action': 'LONG',
                        'coin': coin,
                        'reason': f'Derivatives LONG (RSI {rsi:.1f} + Etherscan {etherscan})',
                        'metadata': {
                            'rsi': rsi,
                            'leverage': 2,
                            'coordination': {
                                'type': 'pure_derivatives'
                            },
                            'conflict_check': 'passed'
                        }
                    })
        
        # === CONFLICT DETECTION (Explicit Conflicts) ===
        
        # Check: Would create contradictory positions
        if has_spot and not has_deriv_short:
            # Holding spot, considering derivatives SHORT → Valid hedge (already handled above)
            pass
        
        if has_deriv_long and rsi > 70:
            # Holding derivatives LONG, RSI now overbought → Flag for review
            self.conflicts_detected.append({
                'coin': coin,
                'issue': 'Derivatives LONG held while RSI overbought',
                'recommendation': 'Consider closing LONG or adding hedge'
            })
        
        return tasks
    
    def evaluate_all_coins(self, coin_data_list: List[Dict]) -> List[Dict]:
        """
        Evaluate all coins and return list of Kanban tasks to create.
        
        Args:
            coin_data_list: List of coin data dicts from Data Worker
        
        Returns:
            List of task definitions for Kanban creation
        """
        all_tasks = []
        
        for coin_data in coin_data_list:
            tasks = self.evaluate_coin(coin_data)
            all_tasks.extend(tasks)
        
        return all_tasks
    
    def create_kanban_commands(self, tasks: List[Dict]) -> List[str]:
        """
        Convert task definitions to Hermes Kanban CLI commands.
        
        Returns:
            List of shell commands to create Kanban tasks
        """
        commands = []
        
        for task in tasks:
            coin = task['coin']
            action = task['action']
            assignee = task['assignee']
            reason = task['reason']
            metadata = task.get('metadata', {})
            
            # Determine emoji and title
            if assignee == 'trading-mean-reversion':
                if action == 'BUY':
                    emoji = '🟢'
                    title = f"BUY {coin} - Mean Reversion"
                else:  # SELL
                    emoji = '🔴'
                    title = f"SELL {coin} - Mean Reversion"
            elif assignee == 'trading-derivatives':
                if action == 'LONG':
                    emoji = '🟢'
                    title = f"LONG {coin} - Derivatives"
                else:  # SHORT
                    emoji = '🔴'
                    title = f"SHORT {coin} - Derivatives"
            else:
                emoji = '⚙️'
                title = f"{action} {coin}"
            
            # Build metadata JSON
            metadata['action'] = action
            metadata['coin'] = coin
            metadata['reason'] = reason
            
            import json as json_lib
            metadata_json = json_lib.dumps(metadata)
            
            # Build command
            cmd = f"""hermes kanban create "{emoji} {title}" --assignee {assignee} --body '{metadata_json}'"""
            commands.append(cmd)
        
        return commands
    
    def run(self, coin_data_list: List[Dict]) -> Dict:
        """
        Main orchestration run.
        
        Args:
            coin_data_list: List of coin data from Data Worker
        
        Returns:
            Summary dict with tasks created, conflicts, hedges, etc.
        """
        print("="*80)
        print("TRADING ORCHESTRATOR - Multi-Bot Coordination")
        print("="*80)
        print(f"\nEvaluating {len(coin_data_list)} coins...")
        print(f"Current positions: {len(self.get_spot_holdings())} spot, {len(self.get_derivatives_positions())} derivatives")
        print(f"Capital deployed: ${self.calculate_deployed_capital():.2f} / ${MAX_CAPITAL:.2f}")
        print()
        
        # Evaluate all coins
        tasks = self.evaluate_all_coins(coin_data_list)
        
        # Generate Kanban commands
        commands = self.create_kanban_commands(tasks)
        
        # Print summary
        print(f"Tasks to create: {len(tasks)}")
        print(f"Conflicts detected: {len(self.conflicts_detected)}")
        print(f"Hedges created: {len(self.hedges_created)}")
        print(f"Conviction boosts: {len(self.conviction_boosts)}")
        print()
        
        if tasks:
            print("KANBAN COMMANDS:")
            print("-" * 80)
            for cmd in commands:
                print(cmd)
            print()
        
        if self.conflicts_detected:
            print("CONFLICTS DETECTED:")
            print("-" * 80)
            for conflict in self.conflicts_detected:
                print(f"  • {conflict['coin']}: {conflict['issue']}")
                if 'recommendation' in conflict:
                    print(f"    → {conflict['recommendation']}")
            print()
        
        if self.hedges_created:
            print("HEDGES CREATED:")
            print("-" * 80)
            for hedge in self.hedges_created:
                print(f"  • {hedge['coin']}: Spot + Derivatives SHORT")
            print()
        
        if self.conviction_boosts:
            print("CONVICTION BOOSTS:")
            print("-" * 80)
            for boost in self.conviction_boosts:
                print(f"  • {boost['coin']}: Spot BUY + Derivatives LONG ({boost['etherscan']})")
            print()
        
        return {
            'tasks_created': len(tasks),
            'kanban_commands': commands,
            'conflicts': self.conflicts_detected,
            'hedges': self.hedges_created,
            'conviction_boosts': self.conviction_boosts,
            'capital_deployed': self.calculate_deployed_capital()
        }


# ============================================================================
# MAIN EXECUTION (Test Mode)
# ============================================================================

if __name__ == '__main__':
    # Test data simulating Data Worker output
    test_coin_data = [
        {
            'symbol': 'BTC',
            'rsi': 28.5,
            'etherscan_signal': 'BUY',
            'etherscan_score': 72,
            'price': 67000
        },
        {
            'symbol': 'ETH',
            'rsi': 75.2,
            'etherscan_signal': 'HOLD',
            'etherscan_score': 45,
            'price': 1837
        },
        {
            'symbol': 'SOL',
            'rsi': 25.8,
            'etherscan_signal': 'STRONG_BUY',
            'etherscan_score': 85,
            'price': 145
        },
        {
            'symbol': 'BNB',
            'rsi': 52.3,
            'etherscan_signal': 'HOLD',
            'etherscan_score': 55,
            'price': 580
        }
    ]
    
    print("TEST MODE - Simulating orchestration")
    print()
    
    orchestrator = TradingOrchestrator()
    result = orchestrator.run(test_coin_data)
    
    print("="*80)
    print("ORCHESTRATION COMPLETE")
    print("="*80)
