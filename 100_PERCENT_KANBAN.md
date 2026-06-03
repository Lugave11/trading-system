# 100% Kanban-Driven Trading System ✅

## Complete Migration

**ALL operations now flow through Kanban tasks** - no standalone scripts running independently.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    KANBAN BOARD (Central)                       │
│                                                                 │
│  Every action is a task. No background processes.               │
│  Board state = System state                                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Task Chain (Automated)

```
📊 Data Worker (5 min, auto-recreate)
  ↓
🎯 Orchestrator (15 min, auto-recreate)
  ↓
🟢 LONG / 🔴 SHORT (on signal)
  ↓
👁️ Monitor (5 min, auto-recreate)
  ↓
🔴 Close (on exit)
```

---

## Components Updated

| Component | Status | Kanban Integration |
|-----------|--------|-------------------|
| **Data Worker** | ✅ Complete | Auto-recreates every 5 min |
| **Orchestrator** | ✅ Complete | Auto-recreates every 15 min, auto-selects best signals |
| **Derivatives Bot** | ✅ Complete | Entry/Monitor/Close handlers |
| **Mean Reversion Bot** | ✅ Complete | Spot BUY/SELL + Monitor |
| **Momentum Bot** | ✅ Complete | Spot momentum trades |

---

## Initial Setup (One-time)

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

**That's it!** System runs automatically.

---

## Task Types

### Recurring (Auto-recreate)

| Task | Interval | Assignee | Purpose |
|------|----------|----------|---------|
| 📊 Data Worker | 5 min | trading-data | Fetch market data |
| 🎯 Orchestrator | 15 min | trading-orchestrator | Create trading tasks |
| 👁️ Monitor | 5 min | trading-derivatives | Check positions for exit |

### Event-Driven (On signal)

| Task | Trigger | Assignee | Purpose |
|------|---------|----------|---------|
| 🟢 LONG | Orchestrator detects RSI < 35 | trading-derivatives | Open LONG |
| 🔴 SHORT | Orchestrator detects RSI > 65 | trading-derivatives | Open SHORT |
| 🟢 BUY | Orchestrator detects RSI < 30 | trading-mean-reversion | Spot buy |
| 🟢 SELL | Orchestrator detects RSI > 50 | trading-mean-reversion | Spot sell |
| 🔴 CLOSE | Monitor detects exit | trading-derivatives | Close position |

---

## Automated Selection Logic

**Orchestrator automatically selects highest conviction signals:**

### LONG Selection
```python
# Sort by RSI (lowest = most oversold = best)
long_signals.sort(key=lambda x: x['metadata']['rsi'])

# Select within capital limits ($7.50 total, $5.00 max per trade)
for signal in long_signals:
    if capital >= $5.00:
        SELECT (highest conviction first)
```

### Example
```
Signals found:
  1. BCH: RSI 18.6 ← BEST (extreme oversold)
  2. MATIC: RSI 34.4
  3. ETH: RSI 39.3

Selection:
  ✅ BCH: $5.00 (RSI 18.6 - extreme)
  ⏭️ MATIC: SKIP (only $2.50 left)
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

## State Files

All state in `state/` directory:

| File | Purpose | Updated By |
|------|---------|------------|
| `discovery_results.json` | Market data (prices, RSI, Etherscan) | Data Worker (5 min) |
| `positions.json` | All open positions | Bots (on entry/exit) |
| `coin_universe.json` | Active coin list | Manual/Orchestrator |

---

## Monitoring

### View Board
```bash
hermes kanban list
```

### View Positions
```bash
cat state/positions.json | jq
```

### View Latest Data
```bash
cat state/discovery_results.json | jq
```

---

## Error Recovery

| Failure | Recovery |
|---------|----------|
| **Data Worker fails** | Auto-retry next cycle (5 min) |
| **Orchestrator fails** | Auto-retry next cycle (15 min) |
| **Bot fails** | Task fails, manual retry |
| **Position stuck** | Manual close via Kanban task |

---

## Manual Override

Create any task manually:

```bash
# Manual LONG
hermes kanban create \
  "🟢 LONG BTC - Derivatives (2x)" \
  --assignee trading-derivatives \
  --metadata '{"direction":"LONG","coin":"BTC","leverage":2}'

# Manual Close
hermes kanban create \
  "🔴 CLOSE: BTC LONG" \
  --assignee trading-derivatives \
  --metadata '{"task_type":"close","trade_id":"deriv_BTC_LONG_..."}'
```

---

## Benefits

| Benefit | Why |
|---------|-----|
| **Visible** | See entire system in board |
| **Auditable** | Full history of every trade |
| **Resilient** | Tasks persist across restarts |
| **Manual Override** | Intervene at any point |
| **No Background** | No zombie processes |
| **Clear State** | `state/` files = truth |
| **Simple** | One interface for all |

---

## Files Updated

| File | Change |
|------|--------|
| `data_worker_live.py` | Added Kanban entry point + auto-recreate |
| `orchestrator_live.py` | Added `select_best_signals()` + auto-recreate |
| `derivatives_bot.py` | Entry/Monitor/Close handlers |
| `derivatives_strategy.py` | Allow HOLD (neutral) with RSI extremes |
| `KANBAN_WORKFLOW_COMPLETE.md` | Complete workflow documentation |

---

**100% KANBAN-DRIVEN - No standalone scripts, all operations through tasks!** 🎉

---

## Next Steps

1. **Start recurring tasks:**
   ```bash
   hermes kanban create "📊 Data Worker" --assignee trading-data --metadata '{"interval_seconds":300,"auto_recreate":true}'
   hermes kanban create "🎯 Orchestrator" --assignee trading-orchestrator --metadata '{"interval_seconds":900,"auto_recreate":true}'
   ```

2. **Monitor board:**
   ```bash
   hermes kanban list
   ```

3. **Watch for signals:**
   - BCH LONG (RSI 18.6) - highest conviction
   - MATIC LONG (RSI 34.4) - waiting for capital

**System is fully automated and Kanban-driven!**
