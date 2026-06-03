# Spot vs Derivatives Trading Architecture

## Core Separation

```
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR (Decision Layer)                │
│                                                                 │
│  Input: Data Worker discovery (Etherscan signals)              │
│                                                                 │
│  Decision:                                                      │
│  - STRONG_BUY/BUY  → Spot Trading OR Long/Short (LONG)         │
│  - SELL/STRONG_SELL → Long/Short (SHORT) ONLY                  │
│  - HOLD → No action                                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
        ┌─────────────────────┴─────────────────────┐
        ↓                                           ↓
┌───────────────────┐                   ┌───────────────────┐
│   SPOT TRADING    │                   │  LONG/SHORT       │
│   (LONG only)     │                   │  (BOTH directions)│
│                   │                   │                   │
│  • Buy & hold     │                   │  • LONG (bullish) │
│  • No leverage    │                   │  • SHORT (bearish)│
│  • Low risk       │                   │  • Leverage       │
│  • Accumulation   │                   │  • High risk      │
└───────────────────┘                   └───────────────────┘
        ↓                                           ↓
        └─────────────────────┬─────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    TRADING-FLOOR (Execution)                    │
│  - Spot: Simple buy/sell orders                                │
│  - Derivatives: Open/close long/short positions                │
│  - Manages stop-loss / take-profit for both                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## When To Use Each

### Spot Trading (LONG Only)

| Use Case | Why Spot |
|----------|----------|
| **Accumulation** | Building long-term positions |
| **Moderate bullish** (BUY signal) | Want exposure without leverage risk |
| **Uncertain market** (HOLD signal) | Small position, can DCA |
| **Low confidence** | Risk only what you can afford to lose |

**Characteristics:**
- ✅ LONG only (buy low, sell high)
- ✅ No liquidation risk
- ✅ No leverage
- ✅ Simple execution
- ❌ Can't profit from downturns
- ❌ Capital tied up longer

---

### Long/Short Trading (Derivatives)

| Use Case | Why Derivatives |
|----------|-----------------|
| **Strong bullish** (STRONG_BUY) | Leverage gains on confirmed uptrend |
| **Strong bearish** (STRONG_SELL) | Profit from downturns (can't do with spot) |
| **Short-term trades** | Quick in/out, capital efficient |
| **High confidence** | Willing to risk liquidation for higher returns |

**Characteristics:**
- ✅ LONG and SHORT (profit both directions)
- ✅ Leverage available (2x-10x)
- ✅ Capital efficient
- ✅ Can hedge spot positions
- ❌ Liquidation risk
- ❌ Funding fees (perpetuals)
- ❌ Higher complexity

---

## Orchestrator Routing Logic

### Decision Matrix

| Etherscan Signal | Score | Bias | Route To | Action |
|-----------------|-------|------|----------|--------|
| **STRONG_BUY** | ≥80 | LONG | Spot + Long/Short | Accumulate spot + leveraged LONG |
| **BUY** | 65-79 | LONG | Spot only | Buy spot (no leverage) |
| **HOLD** | 45-64 | NEUTRAL | None | Wait (no action) |
| **SELL** | 30-44 | SHORT | Long/Short (SHORT) | Open SHORT position |
| **STRONG_SELL** | <30 | BLOCK_LONG | Long/Short (SHORT) | Strong SHORT, exit any LONG |

---

## Kanban Task Flow

### Spot Trading (LONG Only)

```
1. ORCHESTRATOR creates task:
   hermes kanban create \
     "🟢 SPOT BUY BTC - Accumulation" \
     --assignee trading-spot \
     --metadata '{
       "direction": "LONG",
       "coin": "BTC",
       "type": "spot",
       "reason": "Etherscan BUY (70/100)",
       "allocation": "$5.00"
     }'

2. SPOT BOT:
   - Validates: Bullish signal confirmed
   - Calculates: Position size ($5 max)
   - Creates: Execution task

3. TRADING-FLOOR executes:
   - Buys BTC on spot market
   - No stop-loss (long-term hold)
   - Reports: "Bought 0.000074 BTC @ $67,500"
```

### Long/Short - LONG Position

```
1. ORCHESTRATOR creates task:
   hermes kanban create \
     "🟢 LONG ETH - Momentum (3x)" \
     --assignee trading-derivatives \
     --metadata '{
       "direction": "LONG",
       "coin": "ETH",
       "type": "derivatives",
       "reason": "Etherscan STRONG_BUY (85/100)",
       "leverage": "3x",
       "allocation": "$5.00"
     }'

2. DERIVATIVES BOT:
   - Validates: Strong bullish setup
   - Calculates: Entry, stop-loss, take-profit
   - Creates: Execution task

3. TRADING-FLOOR executes:
   - Opens LONG 3x @ $1,850
   - Stop: $1,800 (-2.7%)
   - Target: $1,950 (+5.4%)
   - Reports: "Opened LONG 3x ETH @ $1,850"
```

### Long/Short - SHORT Position

```
1. ORCHESTRATOR creates task:
   hermes kanban create \
     "🔴 SHORT BTC - Breakdown (2x)" \
     --assignee trading-derivatives \
     --metadata '{
       "direction": "SHORT",
       "coin": "BTC",
       "type": "derivatives",
       "reason": "Etherscan SELL (35/100)",
       "leverage": "2x",
       "allocation": "$5.00"
     }'

2. DERIVATIVES BOT:
   - Validates: Bearish setup confirmed
   - Calculates: Entry, stop-loss, take-profit
   - Creates: Execution task

3. TRADING-FLOOR executes:
   - Opens SHORT 2x @ $67,000
   - Stop: $69,000 (+3%)
   - Target: $63,000 (-6%)
   - Reports: "Opened SHORT 2x BTC @ $67,000"
```

---

## Profile Structure

| Profile | Purpose | Direction | Type |
|---------|---------|-----------|------|
| `trading-spot` | Spot accumulation | LONG only | Spot |
| `trading-derivatives` | Leveraged trading | LONG + SHORT | Derivatives |
| `trading-floor` | Execution | Both | Execution |
| `trading-data` | Discovery | N/A | Analysis |
| `trading-orchestrator` | Routing | N/A | Decision |

**Total: 5 profiles** (minimal, clean separation)

---

## Bot Logic

### Spot Bot (LONG Only)

```python
def execute_spot_buy(task_metadata: Dict) -> Dict:
    """
    Spot trading: LONG only, no leverage, accumulation.
    """
    coin = task_metadata['coin']
    allocation = float(task_metadata.get('allocation', 5.00))
    
    # Simple validation
    price = get_price(coin)
    amount = allocation / price
    
    # No stop-loss for spot (long-term hold)
    return {
        'action': 'BUY_SPOT',
        'coin': coin,
        'amount': amount,
        'allocation_usd': allocation,
        'stop_loss': None,  # No stop for spot
        'take_profit': None,  # Sell on signal change
        'leverage': '1x',
    }
```

### Derivatives Bot (LONG + SHORT)

```python
def execute_derivative_trade(task_metadata: Dict) -> Dict:
    """
    Derivatives trading: Handles both LONG and SHORT.
    """
    direction = task_metadata['direction']  # 'LONG' or 'SHORT'
    coin = task_metadata['coin']
    leverage = int(task_metadata.get('leverage', 2))
    allocation = float(task_metadata.get('allocation', 5.00))
    
    price = get_price(coin)
    position_size = (allocation * leverage) / price
    
    if direction == 'LONG':
        # Bullish setup
        stop_loss = price * 0.97  # -3%
        take_profit = price * 1.06  # +6%
        
        return {
            'action': 'OPEN_LONG',
            'coin': coin,
            'size': position_size,
            'leverage': leverage,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
        }
    
    else:  # SHORT
        # Bearish setup
        stop_loss = price * 1.03  # +3%
        take_profit = price * 0.94  # -6%
        
        return {
            'action': 'OPEN_SHORT',
            'coin': coin,
            'size': position_size,
            'leverage': leverage,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
        }
```

---

## Current Market Example

**Etherscan: SELL (38.2/100)** → SHORT bias

### What Happens:

| Bot Type | Action | Why |
|----------|--------|-----|
| **Spot** | ❌ NO ACTION | Spot is LONG only, market is bearish |
| **Derivatives** | ✅ OPEN SHORT | Can profit from downturn |

### Kanban Task Created:

```bash
hermes kanban create \
  "🔴 SHORT ETH - Derivatives (2x)" \
  --assignee trading-derivatives \
  --metadata '{
    "direction": "SHORT",
    "coin": "ETH",
    "type": "derivatives",
    "leverage": "2x",
    "reason": "Etherscan SELL (38/100)"
  }'
```

**Spot bot does NOTHING** (correct - why buy spot in a downtrend?)

**Derivatives bot opens SHORT** (correct - profit from the drop)

---

## Spot vs Derivatives Decision Tree

```
Etherscan Signal Received
         ↓
    ┌────┴────┐
    │         │
  BUY     SELL
 (≥65)    (<45)
    │         │
    ↓         ↓
┌───┴───┐ ┌──┴──────┐
│       │ │         │
SPOT   DERIV  DERIV   (NO ACTION)
LONG   LONG  SHORT   (HOLD 45-64)
       (if   (if
       ≥80)  <45)
```

**Rules:**
1. **BUY (65-79):** Spot LONG only (safe accumulation)
2. **STRONG_BUY (≥80):** Spot + Derivatives LONG (aggressive)
3. **HOLD (45-64):** No action (wait)
4. **SELL/STRONG_SELL (<45):** Derivatives SHORT only (spot stays in cash)

---

## Capital Allocation

### Spot Trading
- **Per trade:** $1-5 (user's $25 max capital rule)
- **Strategy:** DCA on strong BUY signals
- **Exit:** When Etherscan flips to SELL

### Derivatives Trading
- **Per trade:** $1-5 (same capital, but leveraged)
- **Leverage:** 2x-3x max (user's risk tolerance)
- **Stop-loss:** Mandatory (3-5% max loss)
- **Exit:** Stop-loss, take-profit, or signal reversal

---

## Advantages of This Split

| Aspect | Spot | Derivatives |
|--------|------|-------------|
| **Risk** | Low (no liquidation) | High (liquidation possible) |
| **Direction** | LONG only | LONG + SHORT |
| **Leverage** | 1x (none) | 2x-10x |
| **Time Horizon** | Days/weeks | Hours/days |
| **Use Case** | Accumulation | Tactical trades |
| **Bear Market** | Sit in cash | Profit from SHORT |

---

## Implementation Steps

### 1. Create Spot Bot
```python
# spot_bot.py
def execute_spot_buy(metadata):
    # Simple buy logic, no leverage
    ...
```

### 2. Create Derivatives Bot
```python
# derivatives_bot.py
def execute_derivative_trade(metadata):
    # Handle LONG and SHORT
    ...
```

### 3. Update Orchestrator
```python
# Route based on signal strength
if score >= 80:
    create_spot_task()   # Accumulate
    create_deriv_task('LONG')  # Leveraged long
elif score >= 65:
    create_spot_task()   # Spot only
elif score <= 45:
    create_deriv_task('SHORT')  # Short only
# else: HOLD - no action
```

### 4. Update Trading-Floor
```python
# Handle both spot and derivatives execution
if task_type == 'spot':
    execute_spot_buy(...)
elif task_type == 'derivatives':
    if direction == 'LONG':
        open_long(...)
    else:
        open_short(...)
```

---

## Summary

| Question | Answer |
|----------|--------|
| **What's the split?** | Spot (LONG) vs Derivatives (LONG+SHORT) |
| **When Spot?** | BUY signals (65-79), accumulation |
| **When Derivatives?** | STRONG_BUY (LONG) or SELL (SHORT) |
| **When Nothing?** | HOLD (45-64), wait for clarity |
| **Current Market?** | SELL (38/100) → Derivatives SHORT only |

**This gives you:**
- ✅ Safe spot accumulation in bull markets
- ✅ Ability to profit from bear markets (SHORT)
- ✅ Clear separation of risk profiles
- ✅ Simple Kanban-driven routing

---

**Want me to implement this architecture?** (spot_bot.py, derivatives_bot.py, update orchestrator)
