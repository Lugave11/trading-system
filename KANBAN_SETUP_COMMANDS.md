# Trading System - Kanban Setup Commands

## Complete Kanban-Driven Trading System

**ALL operations through Kanban tasks. No standalone scripts.**

---

## Initial Setup (Run These Commands)

### 1. Start Data Worker (Recurring Every 5 Min)

```bash
hermes kanban create \
  "📊 Data Worker - Live Market Data" \
  --assignee trading-data \
  --metadata '{
    "task_type": "data_worker",
    "interval_seconds": 300,
    "auto_recreate": true,
    "coins": ["BTC","ETH","SOL","BNB","XRP","ADA","AVAX","MATIC","DOT","LINK","UNI","ATOM","DOGE","LTC","BCH"]
  }'
```

**What it does:**
- Fetches live prices from Binance.US
- Calculates RSI (14-period)
- Fetches Etherscan signals
- Saves to `state/discovery_results.json`
- Auto-recreates every 5 minutes

---

### 2. Start Orchestrator (Recurring Every 15 Min)

```bash
hermes kanban create \
  "🎯 Orchestrator - Signal Detection" \
  --assignee trading-orchestrator \
  --metadata '{
    "task_type": "orchestrator",
    "interval_seconds": 900,
    "auto_recreate": true
  }'
```

**What it does:**
- Reads `discovery_results.json`
- Calls `should_enter_long/short()` for each coin
- Ranks signals by RSI extremity
- Auto-selects best signals within capital limits
- Creates 🟢 LONG or 🔴 SHORT tasks
- Auto-recreates every 15 minutes

---

## System Flow (Automatic)

```
📊 Data Worker (5 min)
  ↓
🎯 Orchestrator (15 min)
  ↓
🟢 LONG / 🔴 SHORT (on signal)
  ↓
👁️ Monitor (5 min, auto-recreate)
  ↓
🔴 Close (on exit)
```

---

## Task Types

### Recurring Tasks (Auto-Recreate)

| Task | Interval | Assignee | Purpose |
|------|----------|----------|---------|
| 📊 Data Worker | 5 min | trading-data | Fetch market data |
| 🎯 Orchestrator | 15 min | trading-orchestrator | Create trading tasks |
| 👁️ Monitor | 5 min | trading-derivatives | Check positions |

### Event-Driven Tasks (On Signal)

| Task | Trigger | Assignee | Purpose |
|------|---------|----------|---------|
| 🟢 LONG | Orchestrator signal | trading-derivatives | Open LONG |
| 🔴 SHORT | Orchestrator signal | trading-derivatives | Open SHORT |
| 🟢 BUY | RSI < 30 | trading-mean-reversion | Spot buy |
| 🟢 SELL | RSI > 50 | trading-mean-reversion | Spot sell |
| 🔴 CLOSE | Exit detected | trading-derivatives | Close position |

---

## Monitoring Commands

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
cat state/discovery_results.json | jq '.coins | keys'
cat state/discovery_results.json | jq '.coins.BCH'
```

---

## Manual Override Commands

### Manual LONG Entry
```bash
hermes kanban create \
  "🟢 LONG BCH - Derivatives (2x)" \
  --assignee trading-derivatives \
  --metadata '{
    "task_type": "entry",
    "direction": "LONG",
    "coin": "BCH",
    "leverage": 2,
    "allocation": 5.00,
    "entry_price": 252.80,
    "stop_loss": 245.22,
    "take_profit": 267.97,
    "reason": "RSI 21.6 EXTREME oversold"
  }'
```

### Manual Close
```bash
hermes kanban create \
  "🔴 CLOSE: BCH LONG" \
  --assignee trading-derivatives \
  --metadata '{
    "task_type": "close",
    "trade_id": "deriv_BCH_LONG_2026-06-03T09-42-49",
    "exit_reason": "manual"
  }'
```

### Force Data Refresh
```bash
hermes kanban create \
  "📊 Data Worker - Immediate Refresh" \
  --assignee trading-data \
  --metadata '{
    "task_type": "data_worker",
    "refresh_now": true
  }'
```

---

## Capital Management

```
Total Capital: $25.00
├─ Spot (70%): $17.50
│  ├─ Mean Reversion: $12.50
│  └─ Momentum: $5.00
└─ Derivatives (30%): $7.50
   ├─ LONG: $5.00 max
   └─ SHORT: $2.50 max
```

**Enforced by:**
- Orchestrator (pre-task creation)
- Bots (pre-execution check)

---

## Automated Selection Logic

**Orchestrator automatically selects highest conviction:**

```
Signals Found:
  1. BCH: RSI 21.6 ← BEST (extreme oversold)
  2. MATIC: RSI 34.4

Auto-Selection:
  ✅ BCH: $5.00 (selected - highest conviction)
  ⏭️ MATIC: SKIP (only $2.50 capital left)
```

---

## Error Recovery

| Failure | Recovery |
|---------|----------|
| Data Worker fails | Auto-retry next cycle (5 min) |
| Orchestrator fails | Auto-retry next cycle (15 min) |
| Bot fails | Task fails, manual retry via Kanban |
| Position stuck | Manual close via Kanban task |

---

## State Files

| File | Purpose | Updated By |
|------|---------|------------|
| `state/discovery_results.json` | Market data | Data Worker |
| `state/positions.json` | All positions | Bots |
| `state/coin_universe.json` | Coin list | Manual |

---

## Quick Start

```bash
# 1. Start Data Worker
hermes kanban create "📊 Data Worker - Live Market Data" \
  --assignee trading-data \
  --metadata '{"task_type":"data_worker","interval_seconds":300,"auto_recreate":true}'

# 2. Start Orchestrator
hermes kanban create "🎯 Orchestrator - Signal Detection" \
  --assignee trading-orchestrator \
  --metadata '{"task_type":"orchestrator","interval_seconds":900,"auto_recreate":true}'

# 3. Monitor
hermes kanban list
```

**System runs automatically!**

---

## Current Signals (As of Last Run)

| Coin | RSI | Etherscan | Status |
|------|-----|-----------|--------|
| **BCH** | 21.6 | HOLD | ✅ SELECTED (extreme oversold) |
| **MATIC** | 34.4 | HOLD | ⏭️ SKIPPED (capital limit) |
| **BNB** | 37.4 | HOLD | Watching |
| **ETH** | 38.4 | HOLD | Watching |

---

**100% KANBAN-DRIVEN - No standalone scripts!** 🎉
