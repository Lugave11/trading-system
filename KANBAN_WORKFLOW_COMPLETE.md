# Kanban-Driven Trading System - Complete Workflow

## Overview

**100% Kanban-driven** - ALL operations flow through Kanban tasks. No standalone scripts.

---

## Complete Task Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  KANBAN BOARD - CENTRAL ORCHESTRATION                           │
│                                                                 │
│  Every action is a task. No background processes.               │
│  Board state = System state                                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Task Types

### 1. 📊 **Data Worker Task** (Every 5 min)

**Purpose:** Fetch live market data for all coins

**Task:**
```
Title: "📊 Data Worker - Live Market Data"
Assignee: trading-data
Interval: Every 5 minutes (auto-recreates)
Metadata: {"task_type": "data_worker", "coins": ["BTC","ETH",...]}
```

**What it does:**
- Fetches prices from Binance.US
- Calculates RSI (14-period)
- Fetches Etherscan signals (once for all coins)
- Saves to `state/discovery_results.json`
- Re-creates itself (5 min)

**Kanban Command:**
```bash
hermes kanban create \
  "📊 Data Worker - Live Market Data" \
  --assignee trading-data \
  --metadata '{"task_type":"data_worker","interval_seconds":300}'
```

---

### 2. 🎯 **Orchestrator Task** (Every 15 min)

**Purpose:** Analyze data and create trading tasks

**Task:**
```
Title: "🎯 Orchestrator - Signal Detection"
Assignee: trading-orchestrator
Interval: Every 15 minutes (auto-recreates)
Metadata: {"task_type": "orchestrator"}
```

**What it does:**
- Reads `discovery_results.json`
- Calls `should_enter_long/short()` for each coin
- Ranks signals by RSI extremity
- Selects best signals within capital limits
- Creates 🟢 LONG or 🔴 SHORT tasks
- Re-creates itself (15 min)

**Kanban Command:**
```bash
hermes kanban create \
  "🎯 Orchestrator - Signal Detection" \
  --assignee trading-orchestrator \
  --metadata '{"task_type":"orchestrator","interval_seconds":900}'
```

---

### 3. 🟢 **LONG Entry Task** (On Signal)

**Purpose:** Open derivatives LONG position

**Task:**
```
Title: "🟢 LONG BCH - Derivatives (2x)"
Assignee: trading-derivatives
Trigger: Orchestrator detects signal (RSI < 35 + Etherscan)
Metadata: {
  "task_type": "entry",
  "direction": "LONG",
  "coin": "BCH",
  "leverage": 2,
  "allocation": 5.00,
  "entry_price": 250.00,
  "stop_loss": 242.50,
  "take_profit": 265.00
}
```

**What it does:**
- Opens LONG position
- Saves to `state/positions.json`
- Creates 👁️ MONITOR task
- Completes entry task

**Created by:** Orchestrator (automatic)

---

### 4. 🔴 **SHORT Entry Task** (On Signal)

**Purpose:** Open derivatives SHORT position

**Task:**
```
Title: "🔴 SHORT UNI - Derivatives (2x)"
Assignee: trading-derivatives
Trigger: Orchestrator detects signal (RSI > 65 + Etherscan)
Metadata: {
  "task_type": "entry",
  "direction": "SHORT",
  "coin": "UNI",
  "leverage": 2,
  "allocation": 5.00,
  "entry_price": 2.91,
  "stop_loss": 3.00,
  "take_profit": 2.74
}
```

**What it does:**
- Opens SHORT position
- Saves to `state/positions.json`
- Creates 👁️ MONITOR task
- Completes entry task

**Created by:** Orchestrator (automatic)

---

### 5. 👁️ **Monitor Task** (Every 5 min)

**Purpose:** Monitor open positions for exits

**Task:**
```
Title: "👁️ Monitor: BCH LONG"
Assignee: trading-derivatives
Interval: Every 5 minutes (auto-recreates)
Metadata: {
  "task_type": "monitor",
  "trade_id": "deriv_BCH_LONG_...",
  "check_interval_seconds": 300
}
```

**What it does:**
- Loads position from `state/positions.json`
- Gets current price
- Calls `should_exit_position()`
- **IF EXIT:** Creates 🔴 CLOSE task
- **IF HOLD:** Re-creates 👁️ MONITOR (5 min)

**Created by:** Derivatives Bot (after entry)

---

### 6. 🔴 **Close Task** (On Exit)

**Purpose:** Close position on exit signal

**Task:**
```
Title: "🔴 CLOSE: BCH LONG"
Assignee: trading-derivatives
Trigger: Monitor detects exit (stop/target/time)
Metadata: {
  "task_type": "close",
  "trade_id": "deriv_BCH_LONG_...",
  "exit_reason": "take_profit"
}
```

**What it does:**
- Closes position
- Calculates PnL
- Updates `state/positions.json`
- Completes close task

**Created by:** Monitor task (on exit)

---

### 7. 🟢 **Spot BUY Task** (On Signal)

**Purpose:** Open spot position (mean reversion)

**Task:**
```
Title: "🟢 BUY BCH - Mean Reversion"
Assignee: trading-mean-reversion
Trigger: Orchestrator detects signal (RSI < 30)
Metadata: {
  "task_type": "spot_entry",
  "action": "BUY",
  "coin": "BCH",
  "allocation": 5.00,
  "reason": "RSI oversold (18.6 < 30)"
}
```

**What it does:**
- Opens spot position
- Saves to `state/positions.json`
- Creates 👁️ MONITOR task
- Completes entry task

**Created by:** Orchestrator (automatic)

---

### 8. 🟢 **Spot SELL Task** (On Signal)

**Purpose:** Close spot position (mean reversion)

**Task:**
```
Title: "🟢 SELL BCH - Mean Reversion"
Assignee: trading-mean-reversion
Trigger: Orchestrator detects signal (RSI > 50)
Metadata: {
  "task_type": "spot_exit",
  "action": "SELL",
  "coin": "BCH",
  "reason": "RSI mean reversion (> 50)"
}
```

**What it does:**
- Closes spot position
- Calculates PnL
- Updates `state/positions.json`
- Completes exit task

**Created by:** Orchestrator (automatic)

---

## Task Assignment (Profiles)

| Assignee | Responsibilities |
|----------|------------------|
| **trading-data** | Data Worker (fetch prices, RSI, Etherscan) |
| **trading-orchestrator** | Signal detection, task creation |
| **trading-derivatives** | LONG/SHORT entry, monitor, close |
| **trading-mean-reversion** | Spot BUY/SELL |
| **trading-momentum** | Momentum spot trades |

---

## State Files

All state is in `state/` directory:

| File | Purpose |
|------|---------|
| `discovery_results.json` | Latest market data (updated every 5 min) |
| `positions.json` | All open positions (spot + derivatives) |
| `coin_universe.json` | Active coin list |

---

## Capital Management

```
Total Capital: $25.00
├─ Spot (70%): $17.50
│  ├─ Mean Reversion: $12.50
│  └─ Momentum: $5.00
└─ Derivatives (30%): $7.50
   ├─ LONG positions: $5.00 max
   └─ SHORT positions: $2.50 max
```

**Enforced by:**
- Orchestrator (pre-task creation)
- Bots (pre-execution check)

---

## Automation Flow

### Initial Setup (One-time)

```bash
# 1. Data Worker (recurring every 5 min)
hermes kanban create \
  "📊 Data Worker - Live Market Data" \
  --assignee trading-data \
  --metadata '{"task_type":"data_worker","interval_seconds":300,"auto_recreate":true}'

# 2. Orchestrator (recurring every 15 min)
hermes kanban create \
  "🎯 Orchestrator - Signal Detection" \
  --assignee trading-orchestrator \
  --metadata '{"task_type":"orchestrator","interval_seconds":900,"auto_recreate":true}'
```

### Automatic Flow (No manual intervention)

```
Data Worker (5 min)
  ↓
Orchestrator (15 min)
  ↓
🟢 LONG / 🔴 SHORT (on signal)
  ↓
Monitor (5 min, auto-recreate)
  ↓
Close (on exit)
```

---

## Manual Override

All tasks can be created manually if needed:

```bash
# Manual LONG
hermes kanban create \
  "🟢 LONG BTC - Derivatives (2x)" \
  --assignee trading-derivatives \
  --metadata '{"direction":"LONG","coin":"BTC","leverage":2,"allocation":5.00}'

# Manual Close
hermes kanban create \
  "🔴 CLOSE: BTC LONG" \
  --assignee trading-derivatives \
  --metadata '{"task_type":"close","trade_id":"deriv_BTC_LONG_..."}'
```

---

## Monitoring

### View All Tasks

```bash
hermes kanban list
```

### View Open Positions

```bash
cat state/positions.json | jq
```

### View Latest Data

```bash
cat state/discovery_results.json | jq '.coins.BTC'
```

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| **Data Worker fails** | Task fails, retry next cycle (5 min) |
| **Orchestrator fails** | Task fails, retry next cycle (15 min) |
| **Bot fails** | Task fails, manual retry or auto-retry |
| **Position stuck** | Monitor task times out (48h), manual close |

---

## Benefits of 100% Kanban

| Benefit | Why It Matters |
|---------|----------------|
| **Visible** | See entire system state in board |
| **Auditable** | Full history of every action |
| **Resilient** | Tasks persist across restarts |
| **Manual Override** | Can intervene at any point |
| **No Background** | No zombie processes |
| **Clear State** | `state/` files = source of truth |
| **Simple** | One interface for everything |

---

## Migration from Standalone

### Before (Standalone)
```bash
# Running scripts directly
python3 data_worker_live.py
python3 orchestrator_live.py
python3 derivatives_bot.py
```

### After (Kanban-Driven)
```bash
# Create recurring tasks
hermes kanban create "📊 Data Worker" --assignee trading-data
hermes kanban create "🎯 Orchestrator" --assignee trading-orchestrator

# System runs automatically via tasks
```

---

**100% Kanban-driven - No standalone scripts, all operations through tasks!** 🎉
