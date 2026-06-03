# Kanban-Driven Derivatives Flow - COMPLETE ✅

## Overview

**Entirely Kanban-driven** - no background processes, no standalone scripts running.

All operations flow through Kanban tasks with clear visibility and auditability.

---

## Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  ORCHESTRATOR (Every 15 min via Kanban task)                   │
│  - Reads discovery_results.json                                 │
│  - Calls should_enter_long/short() from derivatives_strategy    │
│  - Creates 🟢 LONG or 🔴 SHORT task if signal detected          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  🟢 LONG / 🔴 SHORT TASK (Assignee: trading-derivatives)       │
│  Title: "🟢 LONG BTC - Derivatives (3x)"                        │
│  Metadata: {direction, leverage, entry, stop, target, coin}     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  DERIVATIVES BOT (Executes task)                               │
│  - Reads metadata from task                                     │
│  - Opens position (paper trade)                                 │
│  - Saves to state/positions.json                                │
│  - Creates 👁️ MONITOR task                                      │
│  - Completes entry task                                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  👁️ MONITOR TASK (Every 5 min, re-creates itself)              │
│  Title: "👁️ Monitor: BTC LONG"                                  │
│  - Loads position from state/positions.json                     │
│  - Gets current price                                           │
│  - Calls should_exit_position()                                 │
│  - IF EXIT: Creates 🔴 CLOSE task                               │
│  - IF NO EXIT: Re-creates 👁️ MONITOR (5 min)                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  🔴 CLOSE TASK (Assignee: trading-derivatives)                 │
│  Title: "🔴 CLOSE BTC LONG"                                     │
│  - Closes position                                              │
│  - Calculates PnL                                               │
│  - Updates state/positions.json                                 │
│  - Completes close task                                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Task Types

| Task | Trigger | Assignee | Frequency | Metadata |
|------|---------|----------|-----------|----------|
| **🎯 Orchestrator** | Cron/schedule | `trading-orchestrator` | 15 min | None |
| **🟢 LONG Entry** | Orchestrator signal | `trading-derivatives` | On signal | direction, leverage, entry, stop, target |
| **🔴 SHORT Entry** | Orchestrator signal | `trading-derivatives` | On signal | direction, leverage, entry, stop, target |
| **👁️ Monitor** | Created by entry bot | `trading-derivatives` | 5 min | position_id, check_interval |
| **🔴 Close** | Monitor detects exit | `trading-derivatives` | On exit | position_id, exit_reason |

---

## State Management

### Single Source of Truth

```
state/positions.json
├─ spot_positions: [...]
└─ derivatives_positions: [
    {
      "coin": "BTC",
      "direction": "LONG",
      "leverage": 3,
      "entry_price": 67000,
      "stop_loss": 64990,
      "take_profit": 71020,
      "allocation": 5.00,
      "opened_at": "2026-06-03T07:00:00Z",
      "monitor_task_id": "t_xxxxx"
    }
  ]
```

### Monitor Task Re-creation

Monitor task re-creates itself every 5 minutes:

```python
def monitor_position(position_id):
    # Load position
    # Get current price
    # Check exit
    should_exit, reason = should_exit_position(position, current_price)
    
    if should_exit:
        # Create CLOSE task
        kanban_create(
            title=f"🔴 CLOSE {coin} {direction}",
            assignee='trading-derivatives',
            metadata={'position_id': position_id, 'exit_reason': reason}
        )
    else:
        # Re-create MONITOR task (5 min)
        kanban_create(
            title=f"👁️ Monitor: {coin} {direction}",
            assignee='trading-derivatives',
            metadata={'position_id': position_id, 'check_interval': 300}
        )
```

---

## Implementation Status

| Component | Status | File |
|-----------|--------|------|
| **Strategy Logic** | ✅ Complete | `derivatives_strategy.py` |
| **Orchestrator Integration** | ✅ Complete | `orchestrator_live.py` |
| **Derivatives Bot** | ✅ Ready | `derivatives_bot.py` |
| **Monitor Handler** | ⏳ TODO | Add to `derivatives_bot.py` |
| **Close Handler** | ⏳ TODO | Add to `derivatives_bot.py` |

---

## What's Implemented

### 1. **Strategy** (`derivatives_strategy.py`) ✅

```python
should_enter_long(coin_data, spot_position, available_capital)
should_enter_short(coin_data, spot_position, available_capital)
should_exit_position(position, current_price)
get_available_derivatives_capital(positions)
can_open_new_position(positions)
```

### 2. **Orchestrator** (`orchestrator_live.py`) ✅

```python
# Load discovery results
# Load positions
# For each coin:
#   - Call should_enter_long()
#   - Call should_enter_short()
#   - Create Kanban task if signal
```

### 3. **Capital Allocation** ✅

```
Total: $25.00
Spot: $17.50 (70%)
Derivatives: $7.50 (30%)
Max per trade: $5.00
Max concurrent derivatives: 1-2 positions
```

---

## What's Needed Next

### 1. **Derivatives Bot - Monitor Handler**

Add to `derivatives_bot.py`:

```python
def handle_monitor_task(task_metadata):
    """Monitor position and check for exits"""
    position_id = task_metadata['position_id']
    
    # Load position
    # Get current price
    # Check exit
    should_exit, reason = should_exit_position(position, current_price)
    
    if should_exit:
        # Create CLOSE task
        kanban_create(...)
    else:
        # Re-create MONITOR (5 min)
        kanban_create(...)
```

### 2. **Derivatives Bot - Close Handler**

```python
def handle_close_task(task_metadata):
    """Close position and record PnL"""
    position_id = task_metadata['position_id']
    exit_reason = task_metadata.get('exit_reason', 'Manual')
    
    # Get current price
    # Calculate PnL
    # Update state/positions.json
    # Mark position as CLOSED
```

### 3. **Derivatives Bot - Entry Handler Update**

Update existing entry handler to create monitor task:

```python
def execute_trade(task_metadata):
    # Open position
    # Save to state
    # CREATE MONITOR TASK ← Add this
    kanban_create(
        title=f"👁️ Monitor: {coin} {direction}",
        assignee='trading-derivatives',
        metadata={'position_id': position_id, 'check_interval': 300}
    )
```

---

## Testing Checklist

- [x] Strategy logic (LONG/SHORT signals)
- [x] Strategy logic (exit detection)
- [x] Orchestrator integration
- [x] Capital management (30% allocation)
- [x] Coordination types (hedge, conviction, pure)
- [ ] Monitor task creation (after entry)
- [ ] Monitor task re-creation (every 5 min)
- [ ] Close task creation (on exit)
- [ ] Position state updates
- [ ] Full end-to-end test

---

## Benefits of Kanban-Driven

| Benefit | Why It Matters |
|---------|----------------|
| **Visible** | See all open positions in board |
| **Auditable** | Full history of every trade |
| **Resilient** | Tasks persist if bot crashes |
| **Manual Override** | Can manually create/close tasks |
| **No Background Processes** | Everything is task-driven |
| **Clear State** | state/positions.json is source of truth |

---

## Example Task Flow

### Scenario: BTC LONG Signal

1. **Orchestrator** (15 min cycle)
   - Detects: RSI 28.5 + Etherscan STRONG_BUY
   - Creates: `🟢 LONG BTC - Derivatives (3x)`

2. **Derivatives Bot** (executes entry task)
   - Opens: LONG @ $67,000, 3x leverage
   - Stop: $64,990, Target: $71,020
   - Creates: `👁️ Monitor: BTC LONG`
   - Completes: Entry task

3. **Monitor Task** (every 5 min)
   - Check 1 (5 min): Price $67,200 → HOLD, re-create monitor
   - Check 2 (10 min): Price $67,500 → HOLD, re-create monitor
   - Check 3 (15 min): Price $68,000 → HOLD, re-create monitor
   - ...
   - Check N (45 min): Price $71,020 → EXIT HIT

4. **Monitor Task** (detects exit)
   - Creates: `🔴 CLOSE BTC LONG`
   - Reason: "TAKE-PROFIT HIT (+6%): $71,020"

5. **Derivatives Bot** (executes close task)
   - Closes: LONG @ $71,020
   - PnL: +$0.60 (6% × $5 × 3x)
   - Updates: state/positions.json
   - Completes: Close task

---

**Implementation: 80% complete. Monitor/close handlers needed in derivatives_bot.py**
