# Trading System - Complete Setup

## ✅ Cron Jobs Configured

| Job | Schedule | Delivery | Purpose |
|-----|----------|----------|---------|
| **Data Worker** | `*/5 * * * *` (every 5 min) | `local` (silent) | Collect market data |
| **Orchestrator** | `*/15 * * * *` (every 15 min) | `local` (silent) | Evaluate & route coins |
| **Trading Update** | `every 2h` | `telegram` | **ONLY Gateway message** |

---

## How It Works

### 1. Data Worker (Every 5 Minutes) - SILENT

**Cron Job:** `d359d5c0c8f4`

```
┌─ Cron creates Kanban task
│   └─ Assignee: trading-data
│       └─ Title: "Data Collection - HH:MM"
│
└─ Data Worker executes:
    1. Fetch BTC/ETH/SOL 5m candles (Binance.US)
    2. Calculate indicators (RSI, MACD, EMAs)
    3. Calculate whale scores (Etherscan + volume)
    4. Analyze news sentiment (RSS feeds)
    5. Write to shared_state.json
    6. Complete SILENTLY (no Gateway message)
```

**SOUL.md Rule:**
```python
kanban_complete(
    output={...},
    silent=True  # ← NO Telegram message
)
```

---

### 2. Orchestrator (Every 15 Minutes) - SILENT

**Cron Job:** `ae6bfd68082a`

```
┌─ Cron creates Kanban task
│   └─ Assignee: trading-orchestrator
│       └─ Title: "Orchestrator - HH:MM"
│
└─ Orchestrator executes:
    1. Read shared_state.json (from Data Worker)
    2. Score each coin for 3 methods:
       - Mean Reversion (RSI-based)
       - Momentum (trend-following)
       - Breakout (consolidation + volume)
    3. If score >= 60:
       └─ Create child task for method bot
          └─ Assignee: trading-mean-reversion (or momentum/breakout)
    4. Complete SILENTLY (no Gateway message)
```

**SOUL.md Rule:**
```python
# 15-min cycles: silent
kanban_complete(output={...}, silent=True)

# 2-hour cycles: send to Gateway
kanban_complete(output={...}, summary='📊 Update...')
```

---

### 3. Method Bots (On Signal) - SENDS MESSAGE

**Triggered by:** Orchestrator child task creation

```
┌─ Method Bot receives task
│   └─ Execute strategy
│       ├─ If FLAT: Complete silently
│       └─ If TRADE:
│           ├─ Execute trade (paper trading)
│           ├─ Create MONITOR task
│           └─ Send to Gateway
│               └─ Telegram message: "🎯 BTC BUY..."
```

**SOUL.md Rule:**
```python
if signal.direction != 'FLAT':
    # Trade executed - SEND TO TELEGRAM
    kanban_complete(
        output={...},
        summary='🎯 BTC BUY - Entry $70k | Stop $67.9k | Target $74.2k'
    )
else:
    # No trade - silent
    kanban_complete(output={'signal': 'FLAT'}, silent=True)
```

---

### 4. Trading Update (Every 2 Hours) - SENDS MESSAGE

**Cron Job:** `efa617fe59ab`

```
┌─ Cron creates Kanban task
│   └─ Assignee: trading-orchestrator
│       └─ Title: "Trading Update Summary - Mon DD HH:MM"
│
└─ Orchestrator generates report:
    1. Count Data Worker cycles (last 2h)
    2. Count Orchestrator cycles (last 2h)
    3. List all trades executed
    4. Calculate total PnL
    5. Summarize whale alerts
    6. Send to Gateway
        └─ Telegram message: "📊 Trading Update..."
```

**Expected Message Format:**
```
📊 Trading Update - Jun 02 20:00

Data Cycles: 24
Orchestrator Cycles: 8
Signals: 3
Trades Executed: 3
Total PnL: +$0.33
Whale Alerts: 12

Open Positions:
- BTC: Long @ $70k (PnL: +2.1%)
- ETH: None
- SOL: Long @ $145 (PnL: -0.5%)

Recent Activity:
- 18:45: ETH BUY Mean Reversion (+$0.12)
- 16:30: BTC BUY Momentum (open)
- 14:15: SOL SELL Breakout (+$0.08)
```

---

## Message Flow Summary

| Component | Frequency | Gateway Message? | When |
|-----------|-----------|------------------|------|
| Data Worker | 5 min | ❌ Never | Always silent |
| Orchestrator | 15 min | ❌ Never | Always silent (except 2h update) |
| Method Bots | On signal | ✅ Yes | Only when trade executes |
| Trading Update | 2 hours | ✅ Yes | Every 2 hours (summary) |

---

## Expected Telegram Messages Per Day

| Message Type | Count/Day | Example |
|--------------|-----------|---------|
| **Method Bot Trades** | 0-10 | "🎯 BTC BUY - Entry $70k..." |
| **2-Hour Updates** | 12 | "📊 Trading Update - 24 cycles..." |
| **Total** | **12-22** | (~1 per hour average) |

**Before:** 96+ messages/day (5-min + 15-min spam)
**After:** 12-22 messages/day (only trades + 2h summaries)

---

## Kanban Task Lifecycle

### Data Worker (5 min)
```
[Created by cron] → [Collect data] → [Write shared state] → [Complete SILENT]
```

### Orchestrator (15 min)
```
[Created by cron] → [Read shared state] → [Score coins]
    ├─ [Create child: Method Bot] (if score >= 60)
    └─ [Complete SILENT]
```

### Method Bot (On signal)
```
[Created by Orchestrator] → [Execute strategy]
    ├─ FLAT → [Complete SILENT]
    └─ TRADE → [Execute] → [Create MONITOR] → [Complete + Gateway]
```

### Trading Update (2h)
```
[Created by cron] → [Query recent tasks] → [Generate report] → [Complete + Gateway]
```

---

## Testing

### Manual Test - Data Worker
```bash
# Trigger now
/mnt/data/hermes/workspace/.local/bin/hermes cron run d359d5c0c8f4

# Check Kanban board
/mnt/data/hermes/workspace/.local/bin/hermes kanban list

# Should see: "Data Collection - HH:MM" task completed
# Should NOT see: Telegram message
```

### Manual Test - Orchestrator
```bash
# Trigger now
/mnt/data/hermes/workspace/.local/bin/hermes cron run ae6bfd68082a

# Check for child tasks (if signals)
/mnt/data/hermes/workspace/.local/bin/hermes kanban list

# Should NOT see: Telegram message (unless method bot executes)
```

### Manual Test - Trading Update
```bash
# Trigger now
/mnt/data/hermes/workspace/.local/bin/hermes cron run efa617fe59ab

# Watch Telegram
# SHOULD see: "📊 Trading Update - ..." message
```

---

## Troubleshooting

### No Telegram messages at all?
1. Check Gateway running: `hermes gateway status`
2. Check 2h cron job: `hermes cron list | grep "Trading Update"`
3. Verify delivery: should be `telegram` not `local`

### Too many messages?
1. Check Data Worker SOUL.md has `silent=True`
2. Check Orchestrator SOUL.md has `silent=True` for 15-min cycles
3. Verify no duplicate cron jobs: `hermes cron list`

### Method bots not sending on trades?
1. Check SOUL.md includes `summary='...'` in `kanban_complete()`
2. Verify trade execution logic triggers Gateway message
3. Check task assignee matches profile name

### Tasks not completing?
1. Check profile SOUL.md files exist
2. Verify `kanban_complete()` is called
3. Check logs: `hermes logs --follow`

---

## File Locations

### Cron Jobs
- Data Worker: `d359d5c0c8f4`
- Orchestrator: `ae6bfd68082a`
- Trading Update: `efa617fe59ab`

### SOUL.md Files
- `/mnt/data/hermes/profiles/trading-data/SOUL.md`
- `/mnt/data/hermes/profiles/trading-orchestrator/SOUL.md`
- `/mnt/data/hermes/profiles/trading-mean-reversion/SOUL.md`
- `/mnt/data/hermes/profiles/trading-momentum/SOUL.md`
- `/mnt/data/hermes/profiles/trading-breakout/SOUL.md`

### Shared State
- `/mnt/data/hermes/workspace/trading_system/state/shared_state.json`

### Scripts
- Data Worker: `/mnt/data/hermes/workspace/trading_system/data_worker_kanban.py`
- Orchestrator: `/mnt/data/hermes/workspace/trading_system/orchestrator_bot_kanban.py`
- Method Bots: `/mnt/data/hermes/workspace/trading_system/mean_reversion_bot_kanban.py`

---

## Summary

✅ **Data Worker:** Every 5 min, silent, collects data
✅ **Orchestrator:** Every 15 min, silent, routes coins
✅ **Method Bots:** On signal only, sends trade notifications
✅ **Trading Update:** Every 2 hours, summary report via Gateway

**Result:** Clean, professional updates without spam. Only essential messages reach Telegram. 🎯
