# Derivatives Strategy - Implementation Guide

## Overview

**Purpose:** Tactical derivatives for hedging and transitions (NOT primary strategy)

**Capital Allocation:**
- Total capital: $25.00
- **Derivatives: $7.50 (30%)**
- Spot trading: $17.50 (70%)

---

## Strategy: RSI Extremes + On-Chain Confirmation

### Entry Conditions

#### LONG Entry (3 conditions)
```
1. RSI < 35 (oversold on 1h chart)
2. Etherscan: BUY or STRONG_BUY
3. Available capital >= $5

Leverage:
- 2x: Standard (RSI 30-35 + BUY)
- 3x: High conviction (RSI < 30 + STRONG_BUY)
```

#### SHORT Entry (3 conditions)
```
1. RSI > 65 (overbought on 1h chart)
2. Etherscan: SELL or STRONG_SELL
3. Available capital >= $5

Use Cases:
- Hedge: Protect existing spot position
- Pure derivatives: No spot conflict

Leverage:
- 2x: Standard (RSI 65-70 + SELL)
- 3x: High conviction (RSI > 70 + STRONG_SELL)
```

---

## Exit Conditions

### Hard Exits (Mandatory)

| Condition | Action |
|-----------|--------|
| **Stop-loss hit (-3%)** | Exit immediately |
| **Take-profit hit (+6%)** | Exit immediately |
| **Time expiry (48h)** | Exit at market |

### Soft Exits (Optional)

| Condition | Action |
|-----------|--------|
| **RSI reversal (LONG)** | Exit if RSI > 60 (uptrend exhausted) |
| **RSI reversal (SHORT)** | Exit if RSI < 40 (downtrend exhausted) |

---

## Risk Management

### Capital Limits
```
Total derivatives capital: $7.50 (30% of $25)
Max per trade: $5.00
Max concurrent positions: 2 (capital-limited)
Available after 1 trade: $2.50 (insufficient for 2nd)
```

**Practical limit: 1 position at a time** (due to $5 min + $7.50 total)

### Leverage Rules
```
Standard: 2x leverage
High conviction: 3x leverage

LONG high conviction:
- RSI < 30 AND Etherscan STRONG_BUY

SHORT high conviction:
- RSI > 70 AND Etherscan STRONG_SELL
```

### Position Sizing
```
Allocation per trade: $5.00 (fixed)
Effective exposure: $10-15 (2-3x leverage)
Max loss per trade: $0.30 (3% × $5 × 2x = $0.30)
Max gain per trade: $0.60 (6% × $5 × 2x = $0.60)
```

---

## Coordination with Spot

### Valid Combinations

| Scenario | Spot | Derivatives | Logic | Example |
|----------|------|-------------|-------|---------|
| **Conviction Boost** | BUY | LONG | Both bullish | RSI<30 + Etherscan BUY |
| **Hedge** | HOLD | SHORT | Protect spot | RSI>70, overbought |
| **Pure Derivatives** | None | LONG | No spot, bullish | Tactical LONG |
| **Pure Derivatives** | None | SHORT | No spot, bearish | Tactical SHORT |

### Invalid Combinations

| Scenario | Why Invalid |
|----------|-------------|
| Spot BUY + Derivatives SHORT | Contradictory (bullish + bearish) |
| Spot SELL + Derivatives LONG | Contradictory (bearish + bullish) |

---

## Expected Performance

### Win Rate Scenarios

| Win Rate | 10 Trades | Net PnL | Monthly (12 trades) |
|----------|-----------|---------|---------------------|
| 40% | 4W / 6L | +$0.60 | +$0.72 |
| 45% | 4.5W / 5.5L | +$0.90 | +$1.08 |
| 50% | 5W / 5L | +$1.50 | +$1.80 |
| 55% | 5.5W / 4.5L | +$1.95 | +$2.34 |
| 60% | 6W / 4L | +$2.40 | +$2.88 |

**Assumptions:**
- Win: +$0.60 (6% × $5 × 2x)
- Loss: -$0.30 (3% × $5 × 2x)
- R:R = 1:2

**Realistic expectation:** 45-55% win rate = **$1-2/month** on $7.50 capital

---

## Implementation Files

| File | Purpose |
|------|---------|
| `derivatives_strategy.py` | Core strategy logic (entry/exit) |
| `derivatives_bot.py` | Execution engine |
| `orchestrator_live.py` | Signal routing |
| `DERIVATIVES_STRATEGY.md` | This documentation |

---

## Usage Examples

### Example 1: LONG Signal

```python
from derivatives_strategy import should_enter_long

btc_data = {
    'symbol': 'BTC',
    'price': 67000,
    'rsi': 28.5,
    'etherscan_signal': 'STRONG_BUY',
}

enter, signal = should_enter_long(btc_data)

if enter:
    print(f"LONG {signal.symbol} @ ${signal.entry_price}")
    print(f"Leverage: {signal.leverage}x")
    print(f"Stop: ${signal.stop_loss}")
    print(f"Target: ${signal.take_profit}")
    # Output:
    # LONG BTC @ $67000
    # Leverage: 3x
    # Stop: $64990 (-3%)
    # Target: $71020 (+6%)
```

### Example 2: SHORT Hedge

```python
from derivatives_strategy import should_enter_short

# Existing spot position
spot_position = {
    'coin': 'ETH',
    'action': 'BUY',
    'entry_price': 1850,
}

eth_data = {
    'symbol': 'ETH',
    'price': 1870,
    'rsi': 72.3,
    'etherscan_signal': 'STRONG_SELL',
}

enter, signal = should_enter_short(eth_data, spot_position)

if enter:
    print(f"SHORT {signal.symbol} (HEDGE)")
    print(f"Coordination: {signal.coordination_type}")
    # Output:
    # SHORT ETH (HEDGE)
    # Coordination: hedge
```

### Example 3: Exit Check

```python
from derivatives_strategy import should_exit_position

position = {
    'direction': 'LONG',
    'entry_price': 67000,
    'stop_loss': 64990,
    'take_profit': 71020,
    'opened_at': '2026-06-03T07:00:00Z',
}

# Price hits take profit
should_exit, reason = should_exit_position(position, 71500)

if should_exit:
    print(f"EXIT: {reason}")
    # Output: EXIT: TAKE-PROFIT HIT (+6%): $71500.00 (PnL: 6.72%)
```

---

## Integration with Orchestrator

### Orchestrator Flow

```python
# In orchestrator_live.py

from derivatives_strategy import (
    should_enter_long,
    should_enter_short,
    can_open_new_position,
    get_available_derivatives_capital,
)

# Load derivatives positions
deriv_positions = positions_state.get('derivatives_positions', [])

# Check if we can open new position
if can_open_new_position(deriv_positions):
    available_capital = get_available_derivatives_capital(deriv_positions)
    
    # Check LONG
    enter_long, long_signal = should_enter_long(
        coin_data,
        spot_position=spot_position,
        available_capital=available_capital,
    )
    
    if enter_long:
        # Create Kanban task
        kanban_create(
            title=f"🟢 LONG {coin} - Derivatives ({long_signal.leverage}x)",
            assignee='trading-derivatives',
            metadata={
                'direction': 'LONG',
                'leverage': long_signal.leverage,
                'entry_price': long_signal.entry_price,
                'stop_loss': long_signal.stop_loss,
                'take_profit': long_signal.take_profit,
                'allocation': long_signal.allocation,
                'reason': long_signal.reason,
                'coordination_type': long_signal.coordination_type,
            }
        )
    
    # Check SHORT
    enter_short, short_signal = should_enter_short(
        coin_data,
        spot_position=spot_position,
        available_capital=available_capital,
    )
    
    if enter_short:
        # Create Kanban task
        kanban_create(
            title=f"🔴 SHORT {coin} - Derivatives ({short_signal.leverage}x)",
            assignee='trading-derivatives',
            metadata={
                'direction': 'SHORT',
                'leverage': short_signal.leverage,
                'entry_price': short_signal.entry_price,
                'stop_loss': short_signal.stop_loss,
                'take_profit': short_signal.take_profit,
                'allocation': short_signal.allocation,
                'reason': short_signal.reason,
                'coordination_type': short_signal.coordination_type,
            }
        )
```

---

## Testing Checklist

- [x] LONG signal generation (RSI < 35 + BUY)
- [x] SHORT signal generation (RSI > 65 + SELL)
- [x] High conviction leverage (3x)
- [x] Standard leverage (2x)
- [x] Stop-loss calculation
- [x] Take-profit calculation
- [x] Exit detection (stop/target/time)
- [x] Capital management
- [x] Coordination types (hedge, conviction, pure)
- [ ] Live paper trading (2 weeks)
- [ ] Win rate tracking
- [ ] Performance analysis

---

## Next Steps

1. **Update `derivatives_bot.py`** - Integrate strategy functions
2. **Update `orchestrator_live.py`** - Add derivatives routing
3. **Create monitoring script** - Track open positions
4. **Paper trade for 2 weeks** - Validate win rate
5. **Adjust thresholds if needed** - Based on performance

---

**Strategy is implemented and tested. Ready for integration!**
