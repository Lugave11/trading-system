# Mean Reversion Monitor Task - FIXED ✅

## Problem

The BCH position monitor task `t_755ca421` was created with **derivatives terminology**:

```
❌ "Monitor BCH LONG position"
❌ "Direction: LONG"
```

This is **SPOT TRADING** (mean reversion), not derivatives. Mean reversion bot should use:
- ✅ SPOT BUY (not LONG)
- ✅ SPOT SELL (not SHORT)
- ✅ No leverage, no derivatives

---

## Solution

Added `create_monitor_task()` function to `mean_reversion_bot.py` with correct spot trading terminology.

---

## What Was Added

### 1. **Monitor Task Creator Function**

```python
def create_monitor_task(position: dict) -> dict:
    """
    Create Kanban task for monitoring SPOT position.
    
    Uses SPOT TRADING terminology (BUY/SELL, not LONG/SHORT).
    """
```

**Key Features:**
- Uses "SPOT BUY" / "SPOT SELL" (not LONG/SHORT)
- Explicitly states "This is SPOT TRADING - no leverage, no derivatives"
- Correct exit conditions for mean reversion (RSI > 50 for BUY positions)

---

### 2. **Task Title Format**

**Before (Wrong):**
```
Monitor BCH LONG @ $254.9
```

**After (Correct):**
```
Monitor: BCH SPOT BUY @ $254.90
```

---

### 3. **Task Body Template**

```
POSITION MONITORING TASK - SPOT TRADING

Trade Details:
- Coin: BCH
- Action: BUY (SPOT)
- Entry: $254.90
- Stop Loss: $247.25 (-3.0%)
- Take Profit: $270.19 (+6.0%)
- Position Size: $5.00
- RSI at Entry: 24.23

Monitoring Rules:
1. Check price every 5 minutes
2. Exit if price <= stop loss (protect capital)
3. Exit if price >= take profit (secure gains)
4. Exit if RSI > 50 (mean reversion complete for BUY positions)
5. Time expiry: 48 hours from entry

Current Status: OPEN
Entry Time: 2026-06-03T07:35:41Z

Note: This is SPOT TRADING - no leverage, no derivatives.
```

---

### 4. **Metadata**

```python
metadata={
    'coin': 'BCH',
    'action': 'BUY',  # Not 'LONG'
    'entry_price': 254.90,
    'stop_loss': 247.25,
    'take_profit': 270.19,
    'size_usd': 5.00,
    'rsi_entry': 24.23,
    'monitoring_interval_minutes': 5,
    'position_type': 'SPOT',  # Not 'DERIVATIVES'
}
```

---

### 5. **Auto-Creation After Trade**

Updated main execution to automatically create monitor task:

```python
if result.get('action') == 'OPEN_POSITION':
    position = {
        'coin': symbol,
        'action': 'BUY',  # SPOT BUY
        'entry_price': result.get('entry_price'),
        'stop_loss': result.get('stop_loss'),
        'take_profit': result.get('take_profit'),
        'size_usd': result.get('position_size_usd'),
        'rsi': result.get('rsi'),
        'opened_at': datetime.now(timezone.utc).isoformat(),
    }
    create_monitor_task(position)
```

---

## Terminology Comparison

| Context | Derivatives (Momentum) | Spot (Mean Reversion) |
|---------|------------------------|----------------------|
| **Entry** | LONG | SPOT BUY |
| **Exit** | SHORT | SPOT SELL |
| **Position Type** | DERIVATIVES | SPOT |
| **Leverage** | 2-3x | None |
| **Monitor Title** | `Monitor BTC LONG @ $70k` | `Monitor: BTC SPOT BUY @ $70k` |
| **Exit Trigger** | Trend break, stop, target | RSI > 50, stop, target |

---

## Files Updated

| File | Change |
|------|--------|
| `mean_reversion_bot.py` | Added `create_monitor_task()` function |
| `mean_reversion_bot.py` | Auto-creates monitor task after position open |
| `t_755ca421` | Added comment correcting terminology |

---

## Test Results

```
✅ Function exists and runs
✅ Uses SPOT BUY terminology (not LONG)
✅ Includes "SPOT TRADING - no leverage, no derivatives" note
✅ Correct exit conditions (RSI > 50 for mean reversion)
```

---

## Next Steps

The next time the mean reversion bot opens a position, it will:

1. ✅ Open SPOT BUY position
2. ✅ Automatically create monitor task with correct terminology
3. ✅ Monitor task title: "Monitor: BCH SPOT BUY @ $254.90"
4. ✅ Monitor task body: Clear spot trading language
5. ✅ Metadata: `position_type: 'SPOT'`

**No more derivatives jargon in mean reversion bot!**
