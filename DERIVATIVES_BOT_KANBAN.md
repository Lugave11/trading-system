# Derivatives Bot - Kanban Integration

## Overview

Single bot handling both LONG and SHORT positions with leverage.
Direction is specified in Kanban task metadata.

---

## Kanban Task Creation

### Open LONG Position

```bash
hermes kanban create \
  "🟢 LONG BTC - Derivatives (2x)" \
  --assignee trading-derivatives \
  --metadata '{
    "action": "open",
    "direction": "LONG",
    "coin": "BTC",
    "leverage": 2,
    "allocation": 5.00,
    "reason": "Etherscan BUY (75/100)"
  }'
```

### Open SHORT Position

```bash
hermes kanban create \
  "🔴 SHORT ETH - Derivatives (2x)" \
  --assignee trading-derivatives \
  --metadata '{
    "action": "open",
    "direction": "SHORT",
    "coin": "ETH",
    "leverage": 2,
    "allocation": 5.00,
    "reason": "Etherscan SELL (38/100)"
  }'
```

### Check Positions

```bash
hermes kanban create \
  "📊 Check Derivatives Positions" \
  --assignee trading-derivatives \
  --metadata '{"action": "check"}'
```

### Close Position

```bash
hermes kanban create \
  "🚨 CLOSE deriv_BTC_LONG_20260603_051020" \
  --assignee trading-derivatives \
  --metadata '{
    "action": "close",
    "trade_id": "deriv_BTC_LONG_20260603_051020",
    "reason": "Etherscan flipped to SELL"
  }'
```

---

## Orchestrator Integration

```python
def route_to_derivatives(coin: str, etherscan_signal: str, score: float):
    """
    Create derivatives trading tasks based on Etherscan signal.
    """
    if score >= 80:  # STRONG_BUY
        return {
            'title': f"🟢 LONG {coin} - Derivatives (3x)",
            'assignee': 'trading-derivatives',
            'metadata': {
                'action': 'open',
                'direction': 'LONG',
                'coin': coin,
                'leverage': 3,
                'allocation': 5.00,
                'reason': f'Etherscan STRONG_BUY ({score}/100)',
            }
        }
    
    elif score >= 65:  # BUY
        return {
            'title': f"🟢 LONG {coin} - Derivatives (2x)",
            'assignee': 'trading-derivatives',
            'metadata': {
                'action': 'open',
                'direction': 'LONG',
                'coin': coin,
                'leverage': 2,
                'allocation': 5.00,
                'reason': f'Etherscan BUY ({score}/100)',
            }
        }
    
    elif score <= 35:  # SELL or STRONG_SELL
        leverage = 3 if score < 30 else 2
        return {
            'title': f"🔴 SHORT {coin} - Derivatives ({leverage}x)",
            'assignee': 'trading-derivatives',
            'metadata': {
                'action': 'open',
                'direction': 'SHORT',
                'coin': coin,
                'leverage': leverage,
                'allocation': 5.00,
                'reason': f'Etherscan {etherscan_signal} ({score}/100)',
            }
        }
    
    else:  # HOLD (45-64)
        return None  # No action
```

---

## Bot Features

### Position Management

| Feature | Description |
|---------|-------------|
| **LONG/SHORT** | Single bot handles both directions |
| **Leverage** | 2x-3x max (configurable) |
| **Stop-Loss** | Mandatory 3% max loss |
| **Take-Profit** | 6% target (1:2 risk/reward) |
| **Position Sizing** | $5 base allocation × leverage |
| **Auto-Close** | Checks stop-loss/take-profit |
| **PnL Tracking** | Real-time unrealized PnL |

### State Management

- **File:** `state/derivatives_positions.json`
- **Format:** JSON with all position details
- **Persistence:** Positions survive bot restarts

---

## Test Results

```
TEST 1: Open LONG BTC (2x)
✅ Status: opened
   Trade ID: deriv_BTC_LONG_20260603_051020
   Entry: $67,000.00
   Size: 0.00014925 BTC ($10.00)
   Leverage: 2x
   Stop-Loss: $64,990.00 (-3%)
   Take-Profit: $71,020.00 (+6%)

TEST 2: Open SHORT ETH (2x)
✅ Status: opened
   Trade ID: deriv_ETH_SHORT_20260603_051020
   Entry: $1,837.00
   Size: 0.00544366 ETH ($10.00)
   Leverage: 2x
   Stop-Loss: $1,892.11 (+3%)
   Take-Profit: $1,726.78 (-6%)

TEST 3: Check Positions
✅ Open Positions: 2
✅ Total PnL: $0.00 (just opened)
```

---

## Current Market Application

**Etherscan: SELL (38.2/100)** → SHORT bias

**Orchestrator should create:**
```bash
hermes kanban create \
  "🔴 SHORT ETH - Derivatives (2x)" \
  --assignee trading-derivatives \
  --metadata '{
    "action": "open",
    "direction": "SHORT",
    "coin": "ETH",
    "leverage": 2,
    "allocation": 5.00,
    "reason": "Etherscan SELL (38/100)"
  }'
```

**Bot will:**
1. Validate bearish setup
2. Open SHORT 2x @ ~$1,837
3. Set stop-loss @ $1,892 (+3%)
4. Set take-profit @ $1,727 (-6%)
5. Track PnL every 5 minutes

---

## Files Created

| File | Purpose |
|------|---------|
| `derivatives_bot.py` | Main bot (LONG+SHORT, 19KB) |
| `DERIVATIVES_BOT_KANBAN.md` | This documentation |
| `state/derivatives_positions.json` | Position state (auto-created) |

---

## Next Steps

1. **Add to Kanban profile** - Register `trading-derivatives` assignee
2. **Update Orchestrator** - Route SELL signals to derivatives bot
3. **Add price monitoring** - Check positions every 5 minutes
4. **Add Binance integration** - Replace mock prices with real API
5. **Add Telegram alerts** - Notify on position open/close

---

## Risk Management

| Rule | Value |
|------|-------|
| **Max Capital** | $25 total |
| **Per Trade** | $5 allocation |
| **Max Leverage** | 3x |
| **Max Loss/Trade** | 3% ($0.15) |
| **Target Gain** | 6% ($0.30) |
| **Risk/Reward** | 1:2 |

**With $25 capital:**
- Max 5 open positions ($5 each)
- Max loss per position: $0.15
- Max total loss (all 5 hit stop): $0.75 (3% of capital)
- Max gain per position: $0.30
- Potential total gain (all 5 hit target): $1.50 (6% of capital)

**Paper trading only** (user's rule) - no real money at risk.
