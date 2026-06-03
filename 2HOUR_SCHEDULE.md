# Trading System - 2-Hour Update Schedule

## ✅ Changes Made

### Removed
- ❌ Data Collection cron job (every 5 minutes) - **REMOVED**
- ❌ Orchestrator cron job (every 15 minutes) - **REMOVED**
- ❌ All frequent notifications - **STOPPED**

### Added
- ✅ **Single cron job** running **every 2 hours**
- ✅ **Kanban-driven** workflow (all messaging through Gateway)
- ✅ **Silent delivery** (`--deliver local`) - no spam

---

## How It Works

### Cron Job: `3002be8f6b4c`

```bash
Schedule: every 120m (2 hours)
Name: Trading System Update (2h)
Deliver: local (silent)
Skill: trading-system
```

**What happens every 2 hours:**

1. **Cron creates ONE Kanban task**
   - Assigned to: `trading-data` profile
   - Title: `Trading Update - Jun 02 HH:MM`
   
2. **Data Worker executes full cycle:**
   - Fetches BTC, ETH, SOL price data (Binance.US 5m candles)
   - Calculates indicators (RSI, MACD, EMAs, volume)
   - Calculates whale scores (Etherscan + volume anomaly)
   - Analyzes news sentiment (RSS feeds)
   
3. **Orchestrator evaluates:**
   - Scores each coin for 3 methods (MR, Momentum, Breakout)
   - Routes to best-fit method if score >= 60
   - Creates child Kanban tasks for BUY signals
   
4. **Method Bots execute (if signals):**
   - Mean Reversion, Momentum, or Breakout strategy
   - Each creates MONITOR task for position tracking
   
5. **All tasks complete via `kanban_complete()`:**
   ```python
   from kanban import kanban_complete
   
   kanban_complete(
       output={...},
       summary='📊 Trading Update - 1 BUY signal (ETH Mean Reversion)'
   )
   ```
   
6. **Hermes Gateway sends to Telegram**
   - Only ONE message per 2-hour cycle
   - Includes: signals, trades, whale alerts, PnL

---

## Kanban Function Reference

### `kanban_create()` - Create Tasks

```python
from kanban import kanban_create

# Create a task
task = kanban_create(
    description='Full description of what to do',
    assignee='trading-data',  # Profile name
    title='Optional title'
)

print(f'Created task: {task["id"]}')
```

### `kanban_complete()` - Complete Tasks (SENDS TO TELEGRAM)

```python
from kanban import kanban_complete

# Complete with output and summary
kanban_complete(
    output={
        'success': True,
        'coin_data': [...],
        'whale_score': 72,
    },
    summary='📊 Data Complete - whale score 72, no alerts'
)
```

**This is the ONLY way to send messages to Telegram!**

### `kanban_update()` - Update Task Status

```python
from kanban import kanban_update

# Update task (e.g., add child tasks)
kanban_update(
    task_id='t_xxx',
    status='in_progress',
    notes='Working on it...'
)
```

---

## SOUL.md Updates

All trading profiles updated to use `kanban_complete()`:

### trading-data
- ✅ Must use `kanban_complete()` for all messaging
- ✅ NEVER send direct Telegram messages
- ✅ Complete tasks with summary for Gateway

### trading-orchestrator  
- ✅ Creates child tasks via `kanban_create()`
- ✅ Completes with decision summary
- ✅ Routes coins to method-specific profiles

### trading-mean-reversion / momentum / breakout
- ✅ Execute strategies
- ✅ Complete with trade details
- ✅ Create MONITOR tasks for open positions

---

## Schedule (NSW Timezone = UTC+10)

| Time (NSW) | Time (UTC) | Action |
|------------|------------|--------|
| 08:00 | 22:00 | Trading Update |
| 10:00 | 00:00 | Trading Update |
| 12:00 | 02:00 | Trading Update |
| 14:00 | 04:00 | Trading Update |
| 16:00 | 06:00 | Trading Update |
| 18:00 | 08:00 | Trading Update |
| 20:00 | 10:00 | Trading Update |
| 22:00 | 12:00 | Trading Update |
| 00:00 | 14:00 | Trading Update |
| 02:00 | 16:00 | Trading Update |
| 04:00 | 18:00 | Trading Update |
| 06:00 | 20:00 | Trading Update |

**12 updates per day** (was 96+ with 5-min/15-min cycles)

---

## Expected Telegram Messages

### Normal Cycle (No Signals)
```
📊 Trading Update - Dec 02 20:00

Data Collection: Complete (BTC/ETH/SOL)
Whale Scores: BTC 52, ETH 48, SOL 55
Orchestrator: All HOLD (no setups >= 60)
Signals: 0
Trades: 0
```

### Active Cycle (With Signals)
```
🎯 Trading Update - Dec 02 20:00

BUY SIGNAL: ETH Mean Reversion
  Entry: $3,850
  Stop: $3,735 (-3%)
  Target: $4,081 (+6%)
  Confidence: 68%

Data: Complete | Whale: 64 | News: Neutral
Signals: 1 | Trades: 1
```

---

## Manual Testing

### Trigger a test update now:
```bash
/mnt/data/hermes/workspace/.local/bin/hermes cron run 3002be8f6b4c
```

### Check Kanban board:
```bash
/mnt/data/hermes/workspace/.local/bin/hermes kanban list
```

### Watch for Telegram message:
- Should arrive within 1-2 minutes
- From your bot token
- Single message (not spam)

---

## Troubleshooting

### No Telegram message?
1. Check Gateway is running: `hermes gateway status`
2. Check task completed: `hermes kanban list`
3. Check task output: `hermes kanban show t_xxx`

### Too many messages?
- Verify cron job: `hermes cron list`
- Should only see ONE job: "Trading System Update (2h)"
- Remove old jobs: `hermes cron remove <job_id>`

### Tasks not completing?
- Check SOUL.md files use `kanban_complete()`
- Verify profile assignment matches task assignee
- Check logs: `hermes logs --follow`

---

## Summary

✅ **Cron:** Every 2 hours (was every 5 min / 15 min)
✅ **Messaging:** Via `kanban_complete()` → Hermes Gateway → Telegram
✅ **Notifications:** Silent (`--deliver local`)
✅ **Kanban:** YES - all workflow through Kanban tasks
✅ **Updates:** 12 per day (was 96+)

**No more spam. Clean, professional updates every 2 hours.** 🎯
