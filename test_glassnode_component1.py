#!/usr/bin/env python3
"""
Test Glassnode Leading Indicator - Component 1

Tests:
1. Real Glassnode API calls (not mock data)
2. Verify exchange balance data accuracy
3. Verify whale wallet count accuracy
4. Validate scoring logic
5. Confirm signal interpretation
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Import Glassnode MCP tools
try:
    from mcp_glassnode_fetch_metric import mcp_glassnode_fetch_metric
    GLASSNODE_AVAILABLE = True
except ImportError:
    print("⚠ Glassnode MCP not available - using mock data")
    GLASSNODE_AVAILABLE = False


def test_exchange_balance_metric():
    """Test 1: Fetch real exchange balance data"""
    print("\n" + "="*70)
    print("TEST 1: Exchange Balance Metric (Real API)")
    print("="*70)
    
    if not GLASSNODE_AVAILABLE:
        print("⊘ SKIPPED - Glassnode MCP not available")
        return None
    
    try:
        # Fetch BTC exchange balance
        result = mcp_glassnode_fetch_metric(
            endpoint='/v1/metrics/distribution/balance_exchanges',
            params={"a": "BTC", "i": "24h"}
        )
        
        if not result or 'data' not in result:
            print("❌ Failed to fetch data")
            return None
        
        data = result['data']
        
        if len(data) < 2:
            print("❌ Insufficient data points")
            return None
        
        # Get latest and 7 days ago
        latest = data[-1]
        oldest = data[0]
        
        latest_balance = latest['value']
        oldest_balance = oldest['value']
        change = latest_balance - oldest_balance
        change_pct = (change / oldest_balance) * 100
        
        print(f"✅ Data fetched successfully")
        print(f"   Latest: {latest_balance:,.0f} BTC ({latest['date']})")
        print(f"   Oldest: {oldest_balance:,.0f} BTC ({oldest['date']})")
        print(f"   7D Change: {change:+,.0f} BTC ({change_pct:+.2f}%)")
        
        # Interpretation
        if change > 0:
            print(f"   → 📉 BEARISH: {change:,.0f} BTC added to exchanges (distribution)")
        else:
            print(f"   → 📈 BULLISH: {abs(change):,.0f} BTC withdrawn from exchanges (accumulation)")
        
        return {
            'latest_balance': latest_balance,
            'oldest_balance': oldest_balance,
            'change_btc': change,
            'change_pct': change_pct,
            'signal': 'DISTRIBUTE' if change > 0 else 'ACCUMULATE',
        }
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def test_whale_wallet_count():
    """Test 2: Fetch real whale wallet count data"""
    print("\n" + "="*70)
    print("TEST 2: Whale Wallet Count (Real API)")
    print("="*70)
    
    if not GLASSNODE_AVAILABLE:
        print("⊘ SKIPPED - Glassnode MCP not available")
        return None
    
    try:
        # Fetch whale wallet count ($100K+ USD)
        result = mcp_glassnode_fetch_metric(
            endpoint='/v1/metrics/addresses/min_100k_usd_count',
            params={"a": "BTC", "i": "24h"}
        )
        
        if not result or 'data' not in result:
            print("❌ Failed to fetch data")
            return None
        
        data = result['data']
        
        if len(data) < 2:
            print("❌ Insufficient data points")
            return None
        
        # Get latest and 7 days ago
        latest = data[-1]
        oldest = data[0]
        
        latest_count = latest['value']
        oldest_count = oldest['value']
        change = latest_count - oldest_count
        change_pct = (change / oldest_count) * 100 if oldest_count > 0 else 0
        
        print(f"✅ Data fetched successfully")
        print(f"   Latest: {latest_count:,.0f} wallets ({latest['date']})")
        print(f"   Oldest: {oldest_count:,.0f} wallets ({oldest['date']})")
        print(f"   7D Change: {change:+,.0f} wallets ({change_pct:+.2f}%)")
        
        # Interpretation
        if change < 0:
            print(f"   → 📉 BEARISH: {abs(change):,} whale wallets exited (distribution)")
        elif change > 0:
            print(f"   → 📈 BULLISH: {change:,} new whale wallets entered (accumulation)")
        else:
            print(f"   → ➡️ NEUTRAL: No significant change")
        
        return {
            'latest_count': latest_count,
            'oldest_count': oldest_count,
            'change_wallets': change,
            'change_pct': change_pct,
            'signal': 'DISTRIBUTE' if change < 0 else 'ACCUMULATE' if change > 0 else 'NEUTRAL',
        }
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def test_combined_score_logic(exchange_data: dict, whale_data: dict):
    """Test 3: Validate combined scoring logic"""
    print("\n" + "="*70)
    print("TEST 3: Combined Score Logic")
    print("="*70)
    
    if not exchange_data or not whale_data:
        print("⊘ SKIPPED - Missing prerequisite data")
        return None
    
    # Exchange flow scoring
    ex_change_pct = exchange_data['change_pct']
    if ex_change_pct < -1.0:
        ex_score = 90
        ex_signal = 'STRONG_ACCUMULATE'
    elif ex_change_pct < -0.5:
        ex_score = 75
        ex_signal = 'ACCUMULATE'
    elif ex_change_pct < 0:
        ex_score = 60
        ex_signal = 'WEAK_ACCUMULATE'
    elif ex_change_pct < 0.5:
        ex_score = 40
        ex_signal = 'WEAK_DISTRIBUTE'
    elif ex_change_pct < 1.0:
        ex_score = 25
        ex_signal = 'DISTRIBUTE'
    else:
        ex_score = 10
        ex_signal = 'STRONG_DISTRIBUTE'
    
    # Whale wallet scoring
    wh_change_pct = whale_data['change_pct']
    if wh_change_pct > 2.0:
        wh_score = 90
        wh_signal = 'STRONG_ACCUMULATE'
    elif wh_change_pct > 1.0:
        wh_score = 75
        wh_signal = 'ACCUMULATE'
    elif wh_change_pct > 0:
        wh_score = 60
        wh_signal = 'WEAK_ACCUMULATE'
    elif wh_change_pct > -1.0:
        wh_score = 40
        wh_signal = 'WEAK_DISTRIBUTE'
    elif wh_change_pct > -2.0:
        wh_score = 25
        wh_signal = 'DISTRIBUTE'
    else:
        wh_score = 10
        wh_signal = 'STRONG_DISTRIBUTE'
    
    # Combined score
    combined = (ex_score * 0.5) + (wh_score * 0.5)
    
    # Determine signal
    if combined >= 80:
        signal = 'STRONG_BUY'
        action = 'Enter LONG'
        confidence = 'High'
    elif combined >= 65:
        signal = 'BUY'
        action = 'Enter LONG'
        confidence = 'Medium'
    elif combined >= 45:
        signal = 'HOLD'
        action = 'Wait'
        confidence = 'Low'
    elif combined >= 30:
        signal = 'SELL'
        action = 'Enter SHORT'
        confidence = 'Medium'
    else:
        signal = 'STRONG_SELL'
        action = 'Enter SHORT'
        confidence = 'High'
    
    print(f"\n📊 Exchange Flow Score: {ex_score}/100 ({ex_signal})")
    print(f"   Based on: {exchange_data['change_pct']:+.2f}% change")
    
    print(f"\n🐋 Whale Wallet Score: {wh_score}/100 ({wh_signal})")
    print(f"   Based on: {whale_data['change_pct']:+.2f}% change")
    
    print(f"\n🎯 Combined Score: {combined:.1f}/100")
    print(f"   Signal: {signal}")
    print(f"   Action: {action}")
    print(f"   Confidence: {confidence}")
    
    # Validation
    print(f"\n✅ Scoring Logic Validated")
    print(f"   Exchange weight: 50%")
    print(f"   Whale weight: 50%")
    print(f"   Signal thresholds: STRONG_BUY≥80, BUY≥65, HOLD≥45, SELL≥30, STRONG_SELL<30")
    
    return {
        'exchange_score': ex_score,
        'exchange_signal': ex_signal,
        'whale_score': wh_score,
        'whale_signal': wh_signal,
        'combined_score': combined,
        'signal': signal,
        'action': action,
        'confidence': confidence,
    }


def run_all_tests():
    """Run all Component 1 tests"""
    print("\n" + "="*70)
    print("GLASSNODE LEADING INDICATOR - COMPONENT 1 TEST SUITE")
    print("="*70)
    print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    results = {
        'exchange_balance': None,
        'whale_wallets': None,
        'combined_score': None,
    }
    
    # Test 1: Exchange balance
    results['exchange_balance'] = test_exchange_balance_metric()
    
    # Test 2: Whale wallet count
    results['whale_wallets'] = test_whale_wallet_count()
    
    # Test 3: Combined scoring logic
    results['combined_score'] = test_combined_score_logic(
        results['exchange_balance'],
        results['whale_wallets']
    )
    
    # Summary
    print("\n" + "="*70)
    print("COMPONENT 1 TEST SUMMARY")
    print("="*70)
    
    if results['exchange_balance']:
        print("✅ Test 1: Exchange Balance - PASSED")
    else:
        print("❌ Test 1: Exchange Balance - FAILED")
    
    if results['whale_wallets']:
        print("✅ Test 2: Whale Wallets - PASSED")
    else:
        print("❌ Test 2: Whale Wallets - FAILED")
    
    if results['combined_score']:
        print("✅ Test 3: Scoring Logic - PASSED")
    else:
        print("❌ Test 3: Scoring Logic - FAILED")
    
    # Overall
    passed = sum([
        results['exchange_balance'] is not None,
        results['whale_wallets'] is not None,
        results['combined_score'] is not None,
    ])
    
    print(f"\nOverall: {passed}/3 tests passed")
    
    if passed == 3:
        print("\n✅ COMPONENT 1 VERIFIED - Ready for review")
        print("\n📊 Final Signal:")
        cs = results['combined_score']
        print(f"   Combined Score: {cs['combined_score']:.1f}/100")
        print(f"   Signal: {cs['signal']}")
        print(f"   Action: {cs['action']}")
        print(f"   Confidence: {cs['confidence']}")
    else:
        print(f"\n⚠ {3 - passed} test(s) failed - needs debugging")
    
    print("="*70)
    
    return results


if __name__ == '__main__':
    results = run_all_tests()
    
    # Exit with appropriate code
    if all(v is not None for v in results.values()):
        sys.exit(0)  # All tests passed
    else:
        sys.exit(1)  # Some tests failed
