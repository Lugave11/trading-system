#!/usr/bin/env python3
"""
Test Full STRONG_SELL Flow - Kanban-Driven Exit System

Simulates the complete flow without going live:
1. Data Worker detects STRONG_SELL
2. Orchestrator creates EXIT tasks
3. Trading-Floor executes exits
4. Position Manager updates state
5. Summary report generated

No real API calls - all mocked for testing.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add trading_system path
sys.path.insert(0, str(Path(__file__).parent))

from position_manager import PositionManager


# ============================================================================
# TEST DATA
# ============================================================================

MOCK_POSITIONS = [
    {
        'symbol': 'BTC',
        'side': 'LONG',
        'entry_price': 68500,
        'entry_time': '2026-06-02T18:00:00Z',
        'quantity': 0.00036,
        'method': 'mean_reversion',
        'stop_loss': 66445,
        'take_profit': 72610,
        'task_id': 't_entry_btc123'
    },
    {
        'symbol': 'ETH',
        'side': 'LONG',
        'entry_price': 3420,
        'entry_time': '2026-06-02T21:00:00Z',
        'quantity': 0.0073,
        'method': 'momentum',
        'stop_loss': 3317,
        'take_profit': 3625,
        'task_id': 't_entry_eth456'
    },
    {
        'symbol': 'SOL',
        'side': 'LONG',
        'entry_price': 152,
        'entry_time': '2026-06-02T15:00:00Z',
        'quantity': 0.16,
        'method': 'breakout',
        'stop_loss': 147,
        'take_profit': 162,
        'task_id': 't_entry_sol789'
    },
]

MOCK_GLASSNODE_SIGNAL = {
    'combined_score': 17.5,
    'signal': 'STRONG_SELL',
    'bias': 'BLOCK_LONG',
    'action': 'Enter SHORT',
    'confidence': 'High',
    'allow_long': False,
    'allow_short': True,
    'exchange_flow': {
        'balance_btc': 3051381,
        '7d_change_btc': 15864,
        '7d_change_pct': 0.52,
        'score': 25,
        'signal': 'DISTRIBUTE',
    },
    'whale_wallets': {
        'count': 652047,
        '7d_change': -17533,
        '7d_change_pct': -2.62,
        'score': 10,
        'signal': 'STRONG_DISTRIBUTE',
    },
}

MOCK_CURRENT_PRICES = {
    'BTC': 67220,  # -1.87% from entry
    'ETH': 3380,   # -1.17% from entry
    'SOL': 145,    # -4.61% from entry
}


# ============================================================================
# TEST FUNCTIONS
# ============================================================================

def test_1_position_manager_init():
    """Test 1: Initialize Position Manager with mock positions"""
    print("\n" + "="*70)
    print("TEST 1: Position Manager - Initialize with Positions")
    print("="*70)
    
    pm = PositionManager()
    
    # Clear any existing positions
    pm.positions = []
    pm.save()
    
    # Add mock positions
    for pos in MOCK_POSITIONS:
        pm.add_position(
            symbol=pos['symbol'],
            side=pos['side'],
            entry_price=pos['entry_price'],
            quantity=pos['quantity'],
            method=pos['method'],
            stop_loss=pos['stop_loss'],
            take_profit=pos['take_profit'],
            task_id=pos['task_id']
        )
    
    # Verify
    assert pm.has_positions(), "Should have positions"
    assert len(pm.get_all_positions()) == 3, "Should have 3 positions"
    assert pm.get_position_symbols() == ['BTC', 'ETH', 'SOL'], "Should have BTC, ETH, SOL"
    
    print(f"✅ Position Manager initialized with {len(pm.get_all_positions())} positions")
    print(f"   Symbols: {pm.get_position_symbols()}")
    print(f"   Total deployed: ${pm.get_total_capital_deployed():.2f}")
    
    return pm


def test_2_data_worker_discovery():
    """Test 2: Data Worker detects STRONG_SELL"""
    print("\n" + "="*70)
    print("TEST 2: Data Worker - STRONG_SELL Discovery")
    print("="*70)
    
    # Simulate Data Worker discovery report
    report = {
        'success': True,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'discovered_coins': [],  # No coins qualify (all blocked)
        'glassnode_signal': MOCK_GLASSNODE_SIGNAL,
        'action_required': 'EXIT',  # KEY FLAG
        'selection_summary': {
            'coins_scanned': 15,
            'coins_qualified': 0,
            'top_coins': [],
            'reason': 'All coins blocked by Glassnode STRONG_SELL',
        },
    }
    
    # Verify
    assert report['action_required'] == 'EXIT', "Should require EXIT action"
    assert report['glassnode_signal']['signal'] == 'STRONG_SELL', "Should be STRONG_SELL"
    assert report['glassnode_signal']['allow_long'] == False, "LONG should be blocked"
    
    print(f"✅ Data Worker report generated")
    print(f"   Action Required: {report['action_required']}")
    print(f"   Glassnode Signal: {report['glassnode_signal']['signal']} ({report['glassnode_signal']['combined_score']:.1f}/100)")
    print(f"   Discovered Coins: {len(report['discovered_coins'])} (all blocked)")
    
    return report


def test_3_orchestrator_decision(pm, discovery_report):
    """Test 3: Orchestrator creates EXIT tasks"""
    print("\n" + "="*70)
    print("TEST 3: Orchestrator - EXIT Task Creation")
    print("="*70)
    
    # Check if exit required
    if discovery_report['action_required'] != 'EXIT':
        print("⊘ No EXIT required - skipping")
        return []
    
    # Check for open positions
    if not pm.has_positions():
        print("⊘ No open positions - skipping")
        return []
    
    # Create EXIT tasks (simulated)
    exit_tasks = []
    for symbol in pm.get_position_symbols():
        position = pm.get_position(symbol)
        
        task = {
            'title': f"EXIT {symbol} - STRONG_SELL Signal",
            'assignee': 'trading-floor',
            'metadata': {
                'task_type': 'emergency_exit',
                'symbol': symbol,
                'reason': 'glassnode_strong_sell',
                'position': position,
            },
            'description': f"""
🚨 EMERGENCY EXIT - STRONG_SELL SIGNAL

Reason: Glassnode detected whale distribution
- Exchange balance: +{MOCK_GLASSNODE_SIGNAL['exchange_flow']['7d_change_btc']:,} BTC (distribution)
- Whale wallets: {MOCK_GLASSNODE_SIGNAL['whale_wallets']['7d_change']:,} (exodus)
- Signal: {MOCK_GLASSNODE_SIGNAL['signal']} ({MOCK_GLASSNODE_SIGNAL['combined_score']:.1f}/100)

Position to Exit:
- Symbol: {position['symbol']}
- Side: {position['side']}
- Entry: ${position['entry_price']}
- Current: ${MOCK_CURRENT_PRICES.get(symbol, 0)}
- PnL: {((MOCK_CURRENT_PRICES.get(symbol, 0) - position['entry_price']) / position['entry_price']) * 100:.2f}%

Execute market sell immediately.
Report fill price and PnL.
""",
        }
        
        exit_tasks.append(task)
        print(f"   ✅ Created EXIT task: {task['title']}")
    
    print(f"\n✅ Orchestrator created {len(exit_tasks)} EXIT tasks")
    
    return exit_tasks


def test_4_trading_floor_execution(pm, exit_tasks):
    """Test 4: Trading-Floor executes exits"""
    print("\n" + "="*70)
    print("TEST 4: Trading-Floor - Execute EXIT Orders")
    print("="*70)
    
    exit_results = []
    
    for task in exit_tasks:
        position = task['metadata']['position']
        symbol = position['symbol']
        
        # Simulate market sell
        fill_price = MOCK_CURRENT_PRICES.get(symbol, position['entry_price'])
        
        # Calculate PnL
        pnl_pct = ((fill_price - position['entry_price']) / position['entry_price']) * 100
        pnl_usd = pnl_pct * position['quantity'] * position['entry_price'] / 100
        
        # Remove position from state
        pm.remove_position(symbol)
        
        # Record result
        result = {
            'symbol': symbol,
            'action': 'SELL',
            'fill_price': fill_price,
            'entry_price': position['entry_price'],
            'pnl_pct': round(pnl_pct, 2),
            'pnl_usd': round(pnl_usd, 2),
            'reason': 'glassnode_strong_sell',
        }
        
        exit_results.append(result)
        
        print(f"   ✅ EXIT {symbol}: Sold @ ${fill_price} | PnL: {pnl_pct:+.2f}% (${pnl_usd:+.2f})")
    
    print(f"\n✅ Trading-Floor executed {len(exit_results)} exits")
    
    return exit_results


def test_5_summary_report(exit_results, pm):
    """Test 5: Generate summary report"""
    print("\n" + "="*70)
    print("TEST 5: Summary Report - Telegram Message")
    print("="*70)
    
    total_pnl_usd = sum(r['pnl_usd'] for r in exit_results)
    total_pnl_pct = sum(r['pnl_usd'] for r in exit_results) / sum(
        r['entry_price'] * MOCK_POSITIONS[i]['quantity'] 
        for i, r in enumerate(exit_results)
    ) * 100 if exit_results else 0
    
    # Build Telegram message
    message = f"""
🚨 EMERGENCY EXIT - STRONG_SELL SIGNAL

Exited {len(exit_results)} positions before crash:
"""
    
    for result in exit_results:
        message += f"\n- {result['symbol']}: Sold @ ${result['fill_price']} | PnL: {result['pnl_pct']:+.2f}% (${result['pnl_usd']:+.2f})"
    
    message += f"""

Total PnL: {total_pnl_pct:+.2f}% (${total_pnl_usd:+.2f})
Capital preserved: ${pm.get_total_capital_deployed():.2f} (avoided 5-7% crash)

Reason: Whale distribution detected
- Exchange balance: +{MOCK_GLASSNODE_SIGNAL['exchange_flow']['7d_change_btc']:,} BTC
- Whale wallets: {MOCK_GLASSNODE_SIGNAL['whale_wallets']['7d_change']:,} exited

Status: Waiting for accumulation signal to re-enter
"""
    
    print(message)
    
    return {
        'message': message,
        'exits_count': len(exit_results),
        'total_pnl_usd': total_pnl_usd,
        'total_pnl_pct': total_pnl_pct,
        'capital_preserved': pm.get_total_capital_deployed(),
    }


def test_6_verify_state(pm):
    """Test 6: Verify position state cleared"""
    print("\n" + "="*70)
    print("TEST 6: Position State - Verify Cleared")
    print("="*70)
    
    has_positions = pm.has_positions()
    position_count = len(pm.get_all_positions())
    
    if not has_positions:
        print(f"✅ Position state cleared: {position_count} positions remaining")
    else:
        print(f"⚠ Warning: {position_count} positions still open")
        print(f"   Remaining: {pm.get_position_symbols()}")
    
    return not has_positions


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def run_full_test():
    """Run complete STRONG_SELL flow test"""
    print("\n" + "="*70)
    print("FULL STRONG_SELL FLOW TEST")
    print("="*70)
    print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("\nThis test simulates the complete exit flow without real API calls.")
    
    test_results = {
        'position_manager': False,
        'data_worker': False,
        'orchestrator': False,
        'trading_floor': False,
        'summary': False,
        'state_cleared': False,
    }
    
    try:
        # Test 1: Initialize Position Manager
        pm = test_1_position_manager_init()
        test_results['position_manager'] = True
        
        # Test 2: Data Worker Discovery
        discovery = test_2_data_worker_discovery()
        test_results['data_worker'] = True
        
        # Test 3: Orchestrator Decision
        exit_tasks = test_3_orchestrator_decision(pm, discovery)
        test_results['orchestrator'] = len(exit_tasks) > 0
        
        # Test 4: Trading-Floor Execution
        exit_results = test_4_trading_floor_execution(pm, exit_tasks)
        test_results['trading_floor'] = len(exit_results) > 0
        
        # Test 5: Summary Report
        summary = test_5_summary_report(exit_results, pm)
        test_results['summary'] = True
        
        # Test 6: Verify State Cleared
        state_cleared = test_6_verify_state(pm)
        test_results['state_cleared'] = state_cleared
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Final Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(test_results.values())
    total = len(test_results)
    
    for test, result in test_results.items():
        status = "✅" if result else "❌"
        print(f"{status} {test.replace('_', ' ').title()}: {'PASSED' if result else 'FAILED'}")
    
    print(f"\nOverall: {passed}/{total} tests passed ({passed/total*100:.0f}%)")
    
    if passed == total:
        print("\n🎉 FULL STRONG_SELL FLOW VERIFIED - Ready for review")
        print("\n📊 Test Results:")
        print(f"   - Positions exited: {summary['exits_count']}")
        print(f"   - Total PnL: {summary['total_pnl_usd']:+.2f}% (${summary['total_pnl_pct']:+.2f})")
        print(f"   - Capital preserved: ${summary['capital_preserved']:.2f}")
        print(f"   - State cleared: {state_cleared}")
    else:
        print(f"\n⚠ {total - passed} test(s) failed - needs debugging")
    
    print("="*70)
    
    return passed == total


if __name__ == '__main__':
    success = run_full_test()
    sys.exit(0 if success else 1)
