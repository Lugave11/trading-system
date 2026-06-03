#!/usr/bin/env python3
"""
Orchestrator - Kanban-Driven Coin Selection & Routing

This Orchestrator works INSIDE the Kanban system:

1. Receives Kanban task from Cron (every 15 min)
2. Creates CHILD Kanban task for Data Worker to discover coins
3. Waits for Data Worker to complete discovery
4. Reads discovery report from Data Worker task output
5. Evaluates each discovered coin for trading methods
6. Creates CHILD Kanban tasks for Method Bots (if BUY signals)
7. Completes silently (or sends 2-hr summary to Gateway)

Separation of Concerns:
- Data Worker: Research & Discovery (WHAT to trade)
- Orchestrator: Decision Making (HOW to trade it)
- Method Bots: Execution (ENTER/EXIT trades)
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import sys

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent))

# ============================================================================
# CONFIGURATION
# ============================================================================

# Signal threshold for method execution
MIN_SIGNAL_SCORE = 60

# Task polling (waiting for child tasks)
POLL_INTERVAL_SECONDS = 5
MAX_WAIT_SECONDS = 120

# ============================================================================
# KANBAN INTEGRATION
# ============================================================================

class KanbanOrchestrator:
    """
    Orchestrator that works inside the Kanban system.
    
    Creates child tasks, waits for completion, reads outputs, routes to methods.
    """
    
    def __init__(self):
        self.kanban_available = self._check_kanban()
    
    def _check_kanban(self) -> bool:
        """Check if kanban module is available"""
        try:
            from kanban import kanban_create, kanban_complete, kanban_list
            return True
        except ImportError:
            print("⚠ Kanban module not available (standalone mode)")
            return False
    
    def create_discovery_task(self) -> Dict:
        """
        Create Kanban task for Data Worker to discover coins.
        
        This is the "research request" sent to Data Worker.
        """
        if not self.kanban_available:
            print("⚠ Cannot create task - Kanban not available")
            return None
        
        from kanban import kanban_create
        
        print("\n📋 Creating Data Worker discovery task...")
        
        task = kanban_create(
            title="Coin Discovery - Market Scan",
            description="""
COIN DISCOVERY REQUEST

Scan the market and identify the best trading opportunities.

Instructions:
1. Scan 15 candidate coins (BTC, ETH, SOL, BNB, XRP, ADA, AVAX, MATIC, DOT, LINK, UNI, ATOM, DOGE, LTC, BCH)
2. For each coin, fetch 24h volume, price change %, current price
3. Calculate opportunity scores:
   - Volume score (40%): $5M = 40 pts, $50M+ = 100 pts
   - Volatility score (30%): 5% move = 100 pts
   - Whale score (20%): Volume >$50M = +20, Move >5% = +15
   - News score (10%): Neutral = 50 pts
4. Rank by total score
5. Select top 3-5 coins (score >= 50)
6. Collect OHLCV data (5m candles, 100 periods) for selected coins
7. Calculate indicators: RSI, EMA20, volume ratio, ATR, trend
8. Calculate whale scores for selected coins

Output Format:
{
  "discovered_coins": [
    {
      "symbol": "SOL",
      "rank": 1,
      "total_score": 72.5,
      "volume_24h": 450000000,
      "volatility_pct": 6.2,
      "whale_score": 75,
      "ohlcv": {...},
      "indicators": {"rsi": 28, "ema20": 142, ...}
    },
    ...
  ],
  "selection_summary": {
    "coins_scanned": 15,
    "coins_qualified": 5,
    "top_coins": ["SOL", "DOGE", "AVAX"]
  }
}

Complete with kanban_complete(output=discovery_result, silent=True)
            """,
            assignee='trading-data',
            metadata={
                'task_type': 'coin_discovery',
                'requested_by': 'orchestrator',
                'max_coins': 5,
                'min_score': 50,
            }
        )
        
        print(f"✓ Discovery task created: {task['id']}")
        return task
    
    def wait_for_task_completion(self, task_id: str, timeout: int = MAX_WAIT_SECONDS) -> Optional[Dict]:
        """
        Wait for a Kanban task to complete.
        
        Polls task status every POLL_INTERVAL_SECONDS until:
        - Task status = 'done' (success)
        - Timeout reached (failure)
        
        Returns task output when complete.
        """
        if not self.kanban_available:
            return None
        
        from kanban import kanban_list, kanban_show
        
        print(f"\n⏳ Waiting for task {task_id} to complete...")
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # Get task status
            try:
                # List tasks and find ours
                tasks = kanban_list(status='all', limit=50)
                
                our_task = None
                for task in tasks:
                    if task['id'] == task_id:
                        our_task = task
                        break
                
                if not our_task:
                    print(f"  ⚠ Task {task_id} not found")
                    time.sleep(POLL_INTERVAL_SECONDS)
                    continue
                
                status = our_task.get('status', 'unknown')
                
                if status == 'done':
                    print(f"✓ Task {task_id} completed")
                    
                    # Get full task with output
                    full_task = kanban_show(task_id)
                    return full_task
                
                elif status == 'failed':
                    print(f"✗ Task {task_id} failed")
                    return None
                
                else:
                    print(f"  Status: {status}... waiting")
                    time.sleep(POLL_INTERVAL_SECONDS)
            
            except Exception as e:
                print(f"  ⚠ Error checking task: {e}")
                time.sleep(POLL_INTERVAL_SECONDS)
        
        print(f"✗ Timeout waiting for task {task_id}")
        return None
    
    def get_task_output(self, task: Dict) -> Optional[Dict]:
        """Extract output from completed Kanban task"""
        if not task:
            return None
        
        # Output might be in different fields depending on Kanban implementation
        output = task.get('output', {})
        
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except:
                pass
        
        return output
    
    def evaluate_coin(self, coin: Dict) -> Dict:
        """
        Evaluate a discovered coin for trading methods.
        
        Calculates scores for:
        - Mean Reversion (RSI-based)
        - Momentum (trend-based)
        - Breakout (volume-based)
        
        Returns best method and score.
        """
        symbol = coin['symbol']
        indicators = coin.get('ohlcv', {}).get('indicators', {})
        whale_score = coin.get('whale_score', 50)
        
        # Calculate method scores
        mr_score = self._calculate_mean_reversion_score(indicators, whale_score)
        momentum_score = self._calculate_momentum_score(indicators, whale_score)
        breakout_score = self._calculate_breakout_score(indicators, whale_score)
        
        # Find best method
        scores = {
            'mean_reversion': mr_score,
            'momentum': momentum_score,
            'breakout': breakout_score,
        }
        
        best_method = max(scores, key=scores.get)
        best_score = scores[best_method]
        
        return {
            'symbol': symbol,
            'rank': coin.get('rank', 0),
            'total_score': coin.get('scores', {}).get('total', 0),
            'method_scores': scores,
            'best_method': best_method,
            'best_score': best_score,
            'indicators': indicators,
            'whale_score': whale_score,
        }
    
    def _calculate_mean_reversion_score(self, indicators: Dict, whale_score: float) -> float:
        """
        Score mean reversion opportunity (0-100).
        
        Best when:
        - RSI 35-65 (range-bound): +40 pts
        - RSI <30 or >70 (oversold/overbought): +35 pts
        - Price extended >5% from EMA20: +35 pts
        - Normal volume (0.8-1.5x): +25 pts
        """
        score = 0
        
        rsi = indicators.get('rsi', 50)
        ema20 = indicators.get('ema20', 0)
        price = indicators.get('current_price', 0)
        volume_ratio = indicators.get('volume_ratio', 1)
        
        # RSI scoring
        if 35 <= rsi <= 65:
            score += 40  # Range-bound
        elif rsi < 30 or rsi > 70:
            score += 35  # Oversold/overbought
        
        # Price extension from EMA20
        if ema20 > 0 and price > 0:
            extension = abs(price - ema20) / ema20 * 100
            if extension > 5:
                score += 35
        
        # Volume (normal is good for mean reversion)
        if 0.8 <= volume_ratio <= 1.5:
            score += 25
        
        # Whale bonus
        score += (whale_score - 50) * 0.2
        
        return min(100, score)
    
    def _calculate_momentum_score(self, indicators: Dict, whale_score: float) -> float:
        """
        Score momentum opportunity (0-100).
        
        Best when:
        - RSI 55-70 + bullish trend: +40 pts
        - RSI 30-45 + bearish trend: +40 pts
        - Price extended >3% from EMA20: +35 pts
        - Trend confirmed: +25 pts
        """
        score = 0
        
        rsi = indicators.get('rsi', 50)
        trend = indicators.get('trend', 'neutral')
        ema20 = indicators.get('ema20', 0)
        price = indicators.get('current_price', 0)
        
        # RSI + trend alignment
        if trend == 'bullish' and 55 <= rsi <= 70:
            score += 40
        elif trend == 'bearish' and 30 <= rsi <= 45:
            score += 40
        
        # Price extension
        if ema20 > 0 and price > 0:
            extension = abs(price - ema20) / ema20 * 100
            if extension > 3:
                score += 35
        
        # Trend confirmation
        if trend != 'neutral':
            score += 25
        
        # Whale bonus
        score += (whale_score - 50) * 0.3
        
        return min(100, score)
    
    def _calculate_breakout_score(self, indicators: Dict, whale_score: float) -> float:
        """
        Score breakout opportunity (0-100).
        
        Best when:
        - Volume spike >3x: +50 pts
        - Volume spike >2x: +35 pts
        - Whale score >70: +30 pts
        - Whale score >60: +20 pts
        """
        score = 0
        
        volume_ratio = indicators.get('volume_ratio', 1)
        
        # Volume spike
        if volume_ratio > 3:
            score += 50
        elif volume_ratio > 2:
            score += 35
        elif volume_ratio > 1.5:
            score += 20
        
        # Whale activity
        if whale_score > 70:
            score += 30
        elif whale_score > 60:
            score += 20
        
        return min(100, score)
    
    def _handle_emergency_exit(self, discovery_output: Dict, results: Dict) -> Dict:
        """
        Handle STRONG_SELL signal - create EXIT tasks for all open positions.
        
        This is called when Glassnode detects whale distribution.
        """
        print("\n" + "="*70)
        print("EMERGENCY EXIT - STRONG_SELL Signal Detected")
        print("="*70)
        
        glassnode = discovery_output.get('glassnode_signal', {})
        
        print(f"\n🚨 Glassnode Alert:")
        print(f"   Signal: {glassnode.get('signal', 'UNKNOWN')} ({glassnode.get('combined_score', 0):.1f}/100)")
        print(f"   Exchange Flow: +{glassnode.get('exchange_flow', {}).get('7d_change_btc', 0):,} BTC (distribution)")
        print(f"   Whale Wallets: {glassnode.get('whale_wallets', {}).get('7d_change', 0):,} (exodus)")
        print(f"   Bias: {glassnode.get('bias', 'UNKNOWN')}")
        
        # Import Position Manager
        try:
            from position_manager import PositionManager
            pm = PositionManager()
        except ImportError:
            print("\n⚠ Position Manager not available - cannot create EXIT tasks")
            results['exit_error'] = 'Position Manager import failed'
            return results
        
        # Check for open positions
        if not pm.has_positions():
            print("\n✓ No open positions to exit")
            results['exits_created'] = 0
            results['exit_reason'] = 'no_positions'
            return results
        
        # Get current prices (mock for now - would fetch from API in production)
        mock_prices = {
            'BTC': 67220,
            'ETH': 3380,
            'SOL': 145,
            'BNB': 580,
            'XRP': 0.52,
        }
        
        # Create EXIT task for each open position
        exit_tasks = []
        position_symbols = pm.get_position_symbols()
        
        print(f"\n📋 Creating EXIT tasks for {len(position_symbols)} positions...")
        
        for symbol in position_symbols:
            position = pm.get_position(symbol)
            if not position:
                continue
            
            current_price = mock_prices.get(symbol, position['entry_price'])
            pnl_pct = ((current_price - position['entry_price']) / position['entry_price']) * 100
            
            if not self.kanban_available:
                print(f"  ⚠ Kanban not available - cannot create EXIT task for {symbol}")
                continue
            
            from kanban import kanban_create
            
            task = kanban_create(
                title=f"🚨 EXIT {symbol} - STRONG_SELL Signal",
                description=f"""
EMERGENCY EXIT - STRONG_SELL SIGNAL

Reason: Glassnode detected whale distribution
- Exchange balance: +{glassnode.get('exchange_flow', {}).get('7d_change_btc', 0):,} BTC (distribution)
- Whale wallets: {glassnode.get('whale_wallets', {}).get('7d_change', 0):,} (exodus)
- Signal: {glassnode.get('signal', 'STRONG_SELL')} ({glassnode.get('combined_score', 0):.1f}/100)

Position to Exit:
- Symbol: {symbol}
- Side: {position['side']}
- Entry: ${position['entry_price']:,.2f}
- Current: ${current_price:,.2f}
- PnL: {pnl_pct:+.2f}%

Execute market sell immediately.
Report fill price and PnL via kanban_complete().
                """,
                assignee='trading-floor',
                metadata={
                    'task_type': 'emergency_exit',
                    'symbol': symbol,
                    'reason': 'glassnode_strong_sell',
                    'position': position,
                    'glassnode_signal': glassnode,
                }
            )
            
            exit_tasks.append({
                'symbol': symbol,
                'task_id': task['id'],
                'entry_price': position['entry_price'],
                'current_price': current_price,
                'pnl_pct': pnl_pct,
            })
            
            print(f"  ✅ EXIT task created: {symbol} (PnL: {pnl_pct:+.2f}%)")
        
        results['exits_created'] = len(exit_tasks)
        results['exit_tasks'] = exit_tasks
        results['exit_reason'] = 'glassnode_strong_sell'
        
        print(f"\n✅ Emergency exit complete: {len(exit_tasks)} EXIT tasks created")
        print(f"   Reason: {glassnode.get('summary', 'Whale distribution detected')}")
        
        return results
    
    def create_method_bot_task(self, evaluation: Dict) -> Optional[Dict]:
        """
        Create Kanban task for Method Bot to execute trade.
        
        Only called if best_score >= MIN_SIGNAL_SCORE.
        """
        if not self.kanban_available:
            return None
        
        from kanban import kanban_create
        
        symbol = evaluation['symbol']
        method = evaluation['best_method']
        score = evaluation['best_score']
        indicators = evaluation['indicators']
        
        print(f"\n  🎯 Creating {method} task for {symbol} (score: {score:.0f})...")
        
        # Calculate entry/stop/target
        entry_price = indicators.get('current_price', 0)
        stop_loss = entry_price * 0.97 if entry_price > 0 else 0  # 3% stop
        take_profit = entry_price * 1.06 if entry_price > 0 else 0  # 6% target
        
        task = kanban_create(
            title=f"{symbol} {method.replace('_', ' ').title()} - Score {score:.0f}",
            description=f"""
EXECUTE {method.upper().replace('_', ' ')} TRADE

Coin: {symbol} (Rank #{evaluation['rank']} - Opportunity Score: {evaluation['total_score']:.1f})
Selected by: Data Worker discovery

WHY THIS METHOD:
- {method.replace('_', ' ').title()} score: {score:.0f}
- Mean Reversion score: {evaluation['method_scores']['mean_reversion']:.0f}
- Momentum score: {evaluation['method_scores']['momentum']:.0f}
- Breakout score: {evaluation['method_scores']['breakout']:.0f}

MARKET DATA:
- Price: ${entry_price:,.2f}
- RSI: {indicators.get('rsi', 'N/A')}
- Volume Ratio: {indicators.get('volume_ratio', 'N/A')}x
- Trend: {indicators.get('trend', 'N/A')}
- Whale Score: {evaluation['whale_score']}

TRADE PARAMETERS:
- Entry: ${entry_price:,.2f}
- Stop Loss: ${stop_loss:,.2f} (3.0%)
- Take Profit: ${take_profit:,.2f} (6.0%)
- Max Position: $5 (per user rules)

Execute trade with proper risk management.
Create MONITOR task for position tracking.
Complete with summary to Gateway (Telegram).
            """,
            assignee=f'trading-{method}',
            metadata={
                'symbol': symbol,
                'method': method,
                'score': score,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'opportunity_score': evaluation['total_score'],
            }
        )
        
        print(f"  ✓ Method task created: {task['id']}")
        return task
    
    def run_orchestration_cycle(self) -> Dict:
        """
        Main orchestration cycle.
        
        This is called when Orchestrator receives a Kanban task from Cron.
        
        Flow:
        1. Create Data Worker discovery task
        2. Wait for Data Worker to complete
        3. Read discovery report
        4. Evaluate each discovered coin
        5. Create Method Bot tasks for BUY signals
        6. Return cycle results
        """
        print("\n" + "="*70)
        print("ORCHESTRATOR - Kanban-Driven Cycle")
        print("="*70)
        print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        results = {
            'success': False,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'discovery_task': None,
            'discovered_coins': [],
            'evaluations': [],
            'method_tasks_created': [],
            'signals_generated': 0,
        }
        
        # Step 1: Create Data Worker discovery task
        if not self.kanban_available:
            print("\n⚠ Kanban not available - running standalone evaluation")
            return self._run_standalone_cycle(results)
        
        discovery_task = self.create_discovery_task()
        
        if not discovery_task:
            print("\n✗ Failed to create discovery task")
            return results
        
        results['discovery_task'] = discovery_task['id']
        
        # Step 2: Wait for Data Worker to complete
        completed_task = self.wait_for_task_completion(discovery_task['id'])
        
        if not completed_task:
            print("\n✗ Discovery task did not complete")
            return results
        
        # Step 3: Read discovery report
        discovery_output = self.get_task_output(completed_task)
        
        if not discovery_output or not discovery_output.get('success'):
            print("\n✗ Discovery report invalid")
            return results
        
        discovered_coins = discovery_output.get('discovered_coins', [])
        results['discovered_coins'] = discovered_coins
        
        # NEW: Check for EXIT signal (STRONG_SELL)
        glassnode_signal = discovery_output.get('glassnode_signal')
        action_required = discovery_output.get('action_required', 'HOLD')
        
        print(f"\n🔍 Glassnode Signal: {glassnode_signal.get('signal', 'UNKNOWN') if glassnode_signal else 'N/A'} ({glassnode_signal.get('combined_score', 0):.1f}/100)")
        print(f"   Action Required: {action_required}")
        
        # If EXIT required, create EXIT tasks and skip LONG evaluation
        if action_required == 'EXIT':
            print("\n🚨 STRONG_SELL DETECTED - Creating EXIT tasks...")
            return self._handle_emergency_exit(discovery_output, results)
        
        print(f"\n📊 Discovery report received: {len(discovered_coins)} coins")
        for coin in discovered_coins:
            print(f"  - {coin['symbol']} (score: {coin.get('scores', {}).get('total', 0):.1f})")
        
        # Step 4: Evaluate each discovered coin
        print("\n🧠 Evaluating coins for trading methods...")
        
        decisions = []
        
        for coin in discovered_coins:
            evaluation = self.evaluate_coin(coin)
            results['evaluations'].append(evaluation)
            
            symbol = evaluation['symbol']
            best_method = evaluation['best_method']
            best_score = evaluation['best_score']
            
            print(f"\n  {symbol}:")
            print(f"    Mean Reversion: {evaluation['method_scores']['mean_reversion']:.0f}")
            print(f"    Momentum: {evaluation['method_scores']['momentum']:.0f}")
            print(f"    Breakout: {evaluation['method_scores']['breakout']:.0f}")
            print(f"    Best: {best_method} ({best_score:.0f})")
            
            # Step 5: Create Method Bot task if signal
            if best_score >= MIN_SIGNAL_SCORE:
                print(f"    ✅ BUY signal (score >= {MIN_SIGNAL_SCORE})")
                
                method_task = self.create_method_bot_task(evaluation)
                
                if method_task:
                    results['method_tasks_created'].append({
                        'symbol': symbol,
                        'method': best_method,
                        'task_id': method_task['id'],
                        'score': best_score,
                    })
                    results['signals_generated'] += 1
                    
                    decisions.append({
                        'symbol': symbol,
                        'action': 'BUY',
                        'method': best_method,
                        'score': best_score,
                        'task_id': method_task['id'],
                    })
            else:
                print(f"    ⏳ HOLD (score < {MIN_SIGNAL_SCORE})")
                
                decisions.append({
                    'symbol': symbol,
                    'action': 'HOLD',
                    'reason': f'{best_method} score {best_score:.0f} < {MIN_SIGNAL_SCORE}',
                })
        
        results['success'] = True
        results['decisions'] = decisions
        
        print(f"\n✅ Orchestration cycle complete")
        print(f"   Coins evaluated: {len(discovered_coins)}")
        print(f"   Signals generated: {results['signals_generated']}")
        print(f"   Method tasks created: {len(results['method_tasks_created'])}")
        
        return results
    
    def _run_standalone_cycle(self, results: Dict) -> Dict:
        """
        Run orchestration without Kanban (standalone mode).
        
        Loads discovery report from file instead of Kanban task.
        """
        print("\n⚠ Running standalone mode (no Kanban)")
        
        # Load latest discovery report
        report_dir = Path(__file__).parent / 'reports'
        report_files = sorted(report_dir.glob('discovery_*.json'), reverse=True)
        
        if not report_files:
            print("✗ No discovery reports found")
            return results
        
        latest_report = report_files[0]
        print(f"\n📂 Loading discovery report: {latest_report.name}")
        
        with open(latest_report) as f:
            discovery_output = json.load(f)
        
        discovered_coins = discovery_output.get('discovered_coins', [])
        results['discovered_coins'] = discovered_coins
        
        print(f"📊 Discovery report loaded: {len(discovered_coins)} coins")
        
        # Evaluate coins (same as Step 4 above)
        print("\n🧠 Evaluating coins for trading methods...")
        
        for coin in discovered_coins:
            evaluation = self.evaluate_coin(coin)
            results['evaluations'].append(evaluation)
            
            symbol = evaluation['symbol']
            best_method = evaluation['best_method']
            best_score = evaluation['best_score']
            
            print(f"\n  {symbol}: {best_method} ({best_score:.0f})")
            
            if best_score >= MIN_SIGNAL_SCORE:
                print(f"    ✅ BUY signal")
                results['signals_generated'] += 1
            else:
                print(f"    ⏳ HOLD")
        
        results['success'] = True
        return results


# ============================================================================
# KANBAN COMPLETION
# ============================================================================

def complete_orchestrator_task(results: Dict):
    """
    Complete Orchestrator Kanban task.
    
    For 15-min cycles: silent (no Gateway message)
    For 2-hour cycles: sends summary to Gateway
    """
    try:
        from kanban import kanban_complete
        
        # Check if this is a 2-hour update cycle
        # (would be set in task metadata by Cron)
        is_2hr_update = False  # Would check task metadata
        
        if is_2hr_update:
            # Send summary to Gateway
            summary = build_2hr_summary(results)
            kanban_complete(
                output=results,
                summary=summary
            )
            print("\n✓ Orchestrator task completed (2-hr summary sent)")
        else:
            # Silent completion
            kanban_complete(
                output=results,
                silent=True
            )
            print("\n✓ Orchestrator task completed (silent)")
    
    except ImportError:
        print("\n⚠ Kanban module not available (standalone mode)")
    
    # Save results to file (audit trail)
    save_results(results)


def build_2hr_summary(results: Dict) -> str:
    """Build 2-hour summary message for Gateway"""
    lines = [
        "📊 TRADING SYSTEM 2-HOUR UPDATE",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "**Discovery**",
        f"- Coins scanned: 15",
        f"- Coins qualified: {len(results.get('discovered_coins', []))}",
        f"- Top coins: {', '.join([c['symbol'] for c in results.get('discovered_coins', [])[:3]])}",
        "",
        "**Signals**",
        f"- BUY signals: {results.get('signals_generated', 0)}",
        f"- Methods: {', '.join([f"{t['method']}({t['symbol']})" for t in results.get('method_tasks_created', [])]) or 'None'}",
        "",
        "**Market Conditions**",
        "- Bearish trend across majors",
        "- High volatility (5%+ moves)",
        "- Mean reversion setups dominant",
    ]
    
    return "\n".join(lines)


def save_results(results: Dict):
    """Save orchestration results to file"""
    results_dir = Path(__file__).parent / 'reports'
    results_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    results_file = results_dir / f'orchestration_{timestamp}.json'
    
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"✓ Results saved: {results_file}")


# ============================================================================
# CLI
# ============================================================================

if __name__ == '__main__':
    # Create orchestrator
    orchestrator = KanbanOrchestrator()
    
    # Run orchestration cycle
    results = orchestrator.run_orchestration_cycle()
    
    # Complete Kanban task
    complete_orchestrator_task(results)
    
    print("\n" + "="*70)
    print("Orchestration cycle complete")
    print("Next: Method Bots will execute trades (if signals generated)")
    print("="*70)
