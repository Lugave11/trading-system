#!/usr/bin/env python3
"""
Derivatives Strategy - RSI Extremes + On-Chain Confirmation

Simple, tactical derivatives strategy for hedging and transitions.

Capital Allocation:
- Total capital: $25
- Derivatives allocation: $7.50 (30%)
- Max per trade: $5
- Max concurrent positions: 1-2 (capital limited)

Strategy Logic:
- LONG: RSI < 35 + Etherscan BUY/STRONG_BUY/HOLD (neutral allowed)
- SHORT: RSI > 65 + Etherscan SELL/STRONG_SELL/HOLD (neutral allowed)
- Leverage: 2x standard, 3x high conviction
- Stop-loss: 3% (hard)
- Take-profit: 6% (hard)
- Time expiry: 48 hours

Use Cases:
1. Hedge spot positions (protect from pullbacks)
2. Tactical shorts during coin transitions
3. Conviction plays (RSI extremes + on-chain confirmation)
"""

from typing import Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timezone


# ============================================================================
# CONFIGURATION
# ============================================================================

# Capital allocation (user's rules)
TOTAL_CAPITAL = 25.00
DERIVATIVES_ALLOCATION = 7.50  # 30% of total
MAX_PER_TRADE = 5.00
MAX_CONCURRENT_POSITIONS = 2  # Limited by capital

# Leverage limits
MAX_LEVERAGE = 3
DEFAULT_LEVERAGE = 2

# Risk management
STOP_LOSS_PCT = 0.03  # 3% hard stop
TAKE_PROFIT_PCT = 0.06  # 6% target
TIME_EXPIRY_HOURS = 48

# RSI thresholds
RSI_OVERSOLD = 35  # LONG entry threshold
RSI_OVERBOUGHT = 65  # SHORT entry threshold
RSI_HIGH_CONVICTION_LONG = 30  # 3x leverage threshold
RSI_HIGH_CONVICTION_SHORT = 70  # 3x leverage threshold


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class DerivativesSignal:
    """Represents a derivatives trading signal"""
    symbol: str
    direction: str  # 'LONG' or 'SHORT'
    leverage: int  # 2 or 3
    entry_price: float
    stop_loss: float
    take_profit: float
    allocation: float  # USD to allocate
    reason: str
    rsi: float
    etherscan_signal: str
    timestamp: str
    coordination_type: str  # 'hedge', 'conviction_boost', 'pure_derivatives'


# ============================================================================
# STRATEGY LOGIC
# ============================================================================

def should_enter_long(
    coin_data: dict,
    spot_position: Optional[dict] = None,
    available_capital: float = DERIVATIVES_ALLOCATION
) -> Tuple[bool, Optional[DerivativesSignal]]:
    """
    Check if we should enter a LONG position.
    
    Conditions:
    1. RSI < 35 (oversold)
    2. Etherscan: BUY or STRONG_BUY
    3. Available capital >= $5
    4. No conflicting spot SHORT (not applicable for mean reversion)
    
    Args:
        coin_data: Coin data from Data Worker
        spot_position: Existing spot position (if any)
        available_capital: Available derivatives capital
    
    Returns:
        Tuple of (should_enter, signal_or_none)
    """
    symbol = coin_data.get('symbol', coin_data.get('coin', 'UNKNOWN'))
    rsi = coin_data.get('rsi', 100)
    etherscan_signal = coin_data.get('etherscan_signal', 'HOLD')
    price = coin_data.get('price', 0)
    
    # Check capital
    if available_capital < MAX_PER_TRADE:
        return False, None
    
    # Check RSI condition
    if rsi >= RSI_OVERSOLD:
        return False, None
    
    # Check Etherscan confirmation (HOLD/neutral allowed for RSI extremes)
    # BUY/STRONG_BUY = strong confirmation, HOLD = neutral (allowed)
    if etherscan_signal not in ['BUY', 'STRONG_BUY', 'HOLD']:
        return False, None
    
    # Determine leverage (3x only for STRONG_BUY, 2x for BUY or HOLD)
    if rsi < RSI_HIGH_CONVICTION_LONG and etherscan_signal == 'STRONG_BUY':
        leverage = 3
        reason = f'High conviction LONG (RSI {rsi:.1f} + STRONG_BUY)'
    else:
        leverage = 2
        reason = f'LONG (RSI {rsi:.1f} oversold + {etherscan_signal})'
    
    # Calculate levels
    stop_loss = price * (1 - STOP_LOSS_PCT)
    take_profit = price * (1 + TAKE_PROFIT_PCT)
    
    # Determine coordination type
    if spot_position:
        coordination_type = 'conviction_boost'  # Spot + Derivatives LONG
    else:
        coordination_type = 'pure_derivatives'
    
    # Create signal
    signal = DerivativesSignal(
        symbol=symbol,
        direction='LONG',
        leverage=leverage,
        entry_price=price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        allocation=MAX_PER_TRADE,
        reason=reason,
        rsi=rsi,
        etherscan_signal=etherscan_signal,
        timestamp=datetime.now(timezone.utc).isoformat(),
        coordination_type=coordination_type,
    )
    
    return True, signal


def should_enter_short(
    coin_data: dict,
    spot_position: Optional[dict] = None,
    available_capital: float = DERIVATIVES_ALLOCATION
) -> Tuple[bool, Optional[DerivativesSignal]]:
    """
    Check if we should enter a SHORT position.
    
    Conditions:
    1. RSI > 65 (overbought)
    2. Etherscan: SELL or STRONG_SELL
    3. Available capital >= $5
    4. Either: (a) Hedging existing spot, or (b) No spot conflict
    
    Args:
        coin_data: Coin data from Data Worker
        spot_position: Existing spot position (if any)
        available_capital: Available derivatives capital
    
    Returns:
        Tuple of (should_enter, signal_or_none)
    """
    symbol = coin_data.get('symbol', coin_data.get('coin', 'UNKNOWN'))
    rsi = coin_data.get('rsi', 100)
    etherscan_signal = coin_data.get('etherscan_signal', 'HOLD')
    price = coin_data.get('price', 0)
    
    # Check capital
    if available_capital < MAX_PER_TRADE:
        return False, None
    
    # Check RSI condition
    if rsi <= RSI_OVERBOUGHT:
        return False, None
    
    # Check Etherscan confirmation (HOLD/neutral allowed for RSI extremes)
    # SELL/STRONG_SELL = strong confirmation, HOLD = neutral (allowed)
    if etherscan_signal not in ['SELL', 'STRONG_SELL', 'HOLD']:
        return False, None
    
    # Check if this is a hedge or pure derivatives
    if spot_position:
        # Hedging existing spot - always allowed
        coordination_type = 'hedge'
    else:
        # Pure derivatives SHORT - allowed (no spot conflict)
        coordination_type = 'pure_derivatives'
    
    # Determine leverage (3x only for STRONG_SELL, 2x for SELL or HOLD)
    if rsi > RSI_HIGH_CONVICTION_SHORT and etherscan_signal == 'STRONG_SELL':
        leverage = 3
        reason = f'High conviction SHORT (RSI {rsi:.1f} + STRONG_SELL)'
    else:
        leverage = 2
        if spot_position:
            reason = f'Hedge SHORT (RSI {rsi:.1f} overbought, protecting spot)'
        else:
            reason = f'SHORT (RSI {rsi:.1f} overbought + {etherscan_signal})'
    
    # Calculate levels
    stop_loss = price * (1 + STOP_LOSS_PCT)  # SHORT: stop is above entry
    take_profit = price * (1 - TAKE_PROFIT_PCT)  # SHORT: target is below entry
    
    # Create signal
    signal = DerivativesSignal(
        symbol=symbol,
        direction='SHORT',
        leverage=leverage,
        entry_price=price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        allocation=MAX_PER_TRADE,
        reason=reason,
        rsi=rsi,
        etherscan_signal=etherscan_signal,
        timestamp=datetime.now(timezone.utc).isoformat(),
        coordination_type=coordination_type,
    )
    
    return True, signal


def should_exit_position(
    position: dict,
    current_price: float,
    current_rsi: Optional[float] = None
) -> Tuple[bool, str]:
    """
    Check if we should exit an existing position.
    
    Exit conditions:
    1. Stop-loss hit (hard exit)
    2. Take-profit hit (hard exit)
    3. Time expiry (48 hours)
    4. RSI reversal (optional, for early exit)
    
    Args:
        position: Open position dict
        current_price: Current market price
        current_rsi: Current RSI (optional)
    
    Returns:
        Tuple of (should_exit, reason)
    """
    direction = position.get('direction', '')
    entry_price = position.get('entry_price', 0)
    stop_loss = position.get('stop_loss', 0)
    take_profit = position.get('take_profit', 0)
    opened_at = position.get('opened_at', '')
    
    # 1. Check stop-loss
    if direction == 'LONG':
        if current_price <= stop_loss:
            pnl = (current_price - entry_price) / entry_price * 100
            return True, f'STOP-LOSS HIT (-3%): ${current_price:.2f} (PnL: {pnl:.2f}%)'
    else:  # SHORT
        if current_price >= stop_loss:
            pnl = (entry_price - current_price) / entry_price * 100
            return True, f'STOP-LOSS HIT (-3%): ${current_price:.2f} (PnL: {pnl:.2f}%)'
    
    # 2. Check take-profit
    if direction == 'LONG':
        if current_price >= take_profit:
            pnl = (current_price - entry_price) / entry_price * 100
            return True, f'TAKE-PROFIT HIT (+6%): ${current_price:.2f} (PnL: {pnl:.2f}%)'
    else:  # SHORT
        if current_price <= take_profit:
            pnl = (entry_price - current_price) / entry_price * 100
            return True, f'TAKE-PROFIT HIT (+6%): ${current_price:.2f} (PnL: {pnl:.2f}%)'
    
    # 3. Check time expiry (48 hours)
    if opened_at:
        try:
            open_time = datetime.fromisoformat(opened_at.replace('Z', '+00:00'))
            age_hours = (datetime.now(timezone.utc) - open_time).total_seconds() / 3600
            
            if age_hours >= TIME_EXPIRY_HOURS:
                pnl_pct = ((current_price - entry_price) / entry_price * 100) if direction == 'LONG' else ((entry_price - current_price) / entry_price * 100)
                return True, f'TIME EXPIRY (48h): ${current_price:.2f} (PnL: {pnl_pct:.2f}%)'
        except:
            pass
    
    # 4. Optional: RSI reversal (early exit signal)
    if current_rsi is not None:
        if direction == 'LONG' and current_rsi > 60:
            return True, f'RSI REVERSAL: RSI {current_rsi:.1f} > 60 (uptrend exhausted)'
        if direction == 'SHORT' and current_rsi < 40:
            return True, f'RSI REVERSAL: RSI {current_rsi:.1f} < 40 (downtrend exhausted)'
    
    # No exit signal
    return False, 'HOLD'


def calculate_position_pnl(position: dict, current_price: float) -> dict:
    """
    Calculate PnL for an open position.
    
    Args:
        position: Open position dict
        current_price: Current market price
    
    Returns:
        Dict with PnL calculations
    """
    direction = position.get('direction', '')
    entry_price = position.get('entry_price', 0)
    allocation = position.get('allocation', position.get('size_usd', 5.0))
    leverage = position.get('leverage', 2)
    
    if direction == 'LONG':
        pnl_pct = (current_price - entry_price) / entry_price * 100
    else:  # SHORT
        pnl_pct = (entry_price - current_price) / entry_price * 100
    
    pnl_usd = allocation * (pnl_pct / 100) * leverage
    
    return {
        'direction': direction,
        'entry_price': entry_price,
        'current_price': current_price,
        'pnl_pct': round(pnl_pct, 2),
        'pnl_usd': round(pnl_usd, 2),
        'leverage': leverage,
        'allocation': allocation,
    }


# ============================================================================
# CAPITAL MANAGEMENT
# ============================================================================

def get_available_derivatives_capital(positions: list) -> float:
    """
    Calculate available derivatives capital.
    
    Args:
        positions: List of open derivatives positions
    
    Returns:
        Available capital for new trades
    """
    deployed = sum(p.get('allocation', p.get('size_usd', 0)) for p in positions)
    return max(0.0, DERIVATIVES_ALLOCATION - deployed)


def can_open_new_position(positions: list) -> bool:
    """
    Check if we can open a new position (capital + count limits).
    
    Args:
        positions: List of open derivatives positions
    
    Returns:
        True if new position allowed
    """
    # Check position count
    if len(positions) >= MAX_CONCURRENT_POSITIONS:
        return False
    
    # Check capital
    available = get_available_derivatives_capital(positions)
    if available < MAX_PER_TRADE:
        return False
    
    return True


# ============================================================================
# TESTING
# ============================================================================

if __name__ == '__main__':
    print("="*80)
    print("DERIVATIVES STRATEGY - TEST")
    print("="*80)
    print()
    
    # Test LONG signal
    print("Test 1: LONG Signal (Oversold + BUY)")
    btc_data = {
        'symbol': 'BTC',
        'price': 67000,
        'rsi': 28.5,
        'etherscan_signal': 'STRONG_BUY',
    }
    
    enter, signal = should_enter_long(btc_data)
    if enter:
        print(f"  ✅ LONG signal generated")
        print(f"     Symbol: {signal.symbol}")
        print(f"     Leverage: {signal.leverage}x")
        print(f"     Entry: ${signal.entry_price:,.2f}")
        print(f"     Stop: ${signal.stop_loss:,.2f} (-3%)")
        print(f"     Target: ${signal.take_profit:,.2f} (+6%)")
        print(f"     Reason: {signal.reason}")
        print(f"     Coordination: {signal.coordination_type}")
    else:
        print(f"  ❌ No LONG signal")
    print()
    
    # Test SHORT signal
    print("Test 2: SHORT Signal (Overbought + SELL)")
    eth_data = {
        'symbol': 'ETH',
        'price': 1870,
        'rsi': 72.3,
        'etherscan_signal': 'STRONG_SELL',
    }
    
    enter, signal = should_enter_short(eth_data)
    if enter:
        print(f"  ✅ SHORT signal generated")
        print(f"     Symbol: {signal.symbol}")
        print(f"     Leverage: {signal.leverage}x")
        print(f"     Entry: ${signal.entry_price:,.2f}")
        print(f"     Stop: ${signal.stop_loss:,.2f} (+3%)")
        print(f"     Target: ${signal.take_profit:,.2f} (-6%)")
        print(f"     Reason: {signal.reason}")
        print(f"     Coordination: {signal.coordination_type}")
    else:
        print(f"  ❌ No SHORT signal")
    print()
    
    # Test exit
    print("Test 3: Exit Check (Take Profit Hit)")
    test_position = {
        'direction': 'LONG',
        'entry_price': 67000,
        'stop_loss': 64990,
        'take_profit': 71020,
        'opened_at': datetime.now(timezone.utc).isoformat(),
    }
    
    should_exit, reason = should_exit_position(test_position, 71500)
    if should_exit:
        print(f"  ✅ Exit signal: {reason}")
    else:
        print(f"  ℹ️  No exit: {reason}")
    print()
    
    # Test capital management
    print("Test 4: Capital Management")
    print(f"  Total derivatives allocation: ${DERIVATIVES_ALLOCATION:.2f} (30% of $25)")
    print(f"  Max per trade: ${MAX_PER_TRADE:.2f}")
    print(f"  Max concurrent positions: {MAX_CONCURRENT_POSITIONS}")
    print(f"  Available capital (no positions): ${get_available_derivatives_capital([]):.2f}")
    print(f"  Available capital (1 position): ${get_available_derivatives_capital([{'allocation': 5.0}]):.2f}")
    print()
    
    print("="*80)
    print("TEST COMPLETE")
    print("="*80)
