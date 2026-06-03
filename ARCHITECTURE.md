# Trading System - Kanban Architecture

## Overview
Fully automated crypto trading system using Hermes Kanban for orchestration.
Each component runs as a separate Kanban task with dedicated profiles.

---

## Profiles

| Profile | Role | Status |
|---------|------|--------|
| `trading-data` | Collects market data, whale activity, news | ✅ Ready |
| `trading-orchestrator` | Makes routing decisions (BUY/HOLD/SWITCH) | ✅ Ready |
| `trading-mean-reversion` | Executes mean reversion trades (RSI strategy) | ✅ Ready |
| `trading-momentum` | Executes momentum trades (trend following) | ✅ Ready |
| `trading-breakout` | Executes breakout trades (consolidation breaks) | ✅ Ready |
| `trading-analyst` | Performance reporting, PnL tracking | ✅ Ready |

---

## Cron Jobs

| Job | Schedule | Creates Task For | Deliver To |
|-----|----------|-----------------|------------|
| **Data Collection** | `*/5 * * * *` | `trading-data` | local (silent) |
| **Orchestrator** | `*/15 * * * *` | `trading-orchestrator` | local (silent) |

**Next Runs:**
- Data: Every 5 minutes (XX:00, XX:05, XX:10, ...)
- Orchestrator: Every 15 minutes (XX:00, XX:15, XX:30, ...)

---

## Kanban Flow

```
Every 5 min: Cron → Data Collection Task (trading-data)
    ↓
    Fetches: OHLCV (Binance), Whale Data (Etherscan), News (RSS)
    ↓
    kanban_complete(output={coin_data, alerts, whale_scores})
    
Every 15 min: Cron → Orchestrator Task (trading-orchestrator)
    ↓
    Reads: Parent Data Worker output
    ↓
    Evaluates: Momentum, Mean Reversion, Breakout scores
    ↓
    Decides: BUY / HOLD / SWITCH for each coin
    ↓
    For each BUY: Creates child task → Method Bot profile
    ↓
    kanban_complete(output={decisions, tasks_created})

Method Bot (trading-{method}):
    ↓
    Reads: Orchestrator decision + coin data
    ↓
    Executes: Entry, stop loss, take profit
    ↓
    kanban_complete(output={entry, size, status})
    ↓
    Creates: Monitor Position task (every 5 min)
```

---

## Data Flow

**Shared State Files** (for fast handoff):
- `state/shared_state.json` - Latest Data Worker output
- `state/orchestrator_latest.json` - Latest decisions
- `state/data_worker_*.json` - Timestamped backups

**Kanban Task Output** (for history & audit):
- Every task reports via `kanban_complete(output=...)`
- Full JSON preserved in task history
- Can replay/debug any past decision

---

## Current Configuration

**Coin Universe:** BTC, ETH, SOL (3 coins)

**Data Sources:**
- OHLCV: Binance.US (free, no key)
- Market Cap/Volume: CoinGecko (free, no key)
- Whale Tracking: Etherscan V2 (free key configured)
- News: 4 RSS feeds (CoinDesk, Cointelegraph, etc.)

**Strategy Parameters:**

| Method | Entry Criteria | Stop Loss | Take Profit | Max Position |
|--------|---------------|-----------|-------------|--------------|
| Mean Reversion | RSI < 30, price extended | 3% | 6% | $5 |
| Momentum | RSI > 60, trend bullish, MACD+ | 5% / EMA20 | 10-15% | $5 |
| Breakout | Range break + volume 2x | 3-5% below breakout | 8-12% | $5 |

**Risk Limits:**
- Total capital: $25 MAX
- Max per position: $5
- Max concurrent positions: 3-5 (1-2 per method)
- Paper trading ONLY (no real orders yet)

---

## Monitoring

**Check Kanban Board:**
```bash
hermes kanban list
hermes kanban show <task_id> --json
```

**Check Cron Jobs:**
```bash
hermes cron list
hermes cron run <job_id>  # Manual trigger
```

**Check State Files:**
```bash
cat trading_system/state/shared_state.json | jq
cat trading_system/state/orchestrator_latest.json | jq
```

---

## Alerts

**Telegram Notifications:**
- ❌ DISABLED for routine cron jobs (set to `local` delivery)
- ✅ ENABLED for:
  - Whale alerts (whale score > 80)
  - Major news catalysts
  - Trade executions (entry/exit)
  - Stop loss / target hits

**Configure alerts in:**
- `data_worker.py` - Alert thresholds
- Method bots - Trade notifications

---

## Phase 1 Status

| Component | Status | Notes |
|-----------|--------|-------|
| Data Worker | ✅ Complete | Real APIs, whale tracking, news |
| Orchestrator | ✅ Complete | Method scoring, task creation |
| Mean Reversion Bot | ✅ Complete | Uses existing RSI strategy |
| Momentum Bot | ⏳ TODO | Build execution logic |
| Breakout Bot | ⏳ TODO | Build execution logic |
| Position Monitor | ⏳ TODO | Build monitoring loop |
| Analyst Reports | ⏳ TODO | Build PnL aggregation |

---

## Next Steps

1. **Test full flow** - Wait for BUY signal or manually trigger
2. **Build Momentum Bot** - Copy mean_reversion_bot.py pattern
3. **Build Breakout Bot** - Copy mean_reversion_bot.py pattern
4. **Add Position Monitor** - Cron job to check open positions
5. **Enable live mode** - Add MEXC API keys when ready for real trades

---

## Files

**Core Modules:**
- `trading_system/data_worker.py` - Data collection
- `trading_system/orchestrator.py` - Decision logic
- `trading_system/mean_reversion_bot.py` - RSI execution
- `trading_system/whale_data.py` - Etherscan whale tracking
- `trading_system/state_manager.py` - State handoff (legacy)

**Scripts:**
- `trading_system/scripts/create_data_task.py` - Cron script
- `trading_system/scripts/create_orchestrator_task.py` - Cron script

**Configs:**
- `trading_system/kanban_tasks.md` - Task definitions
- `trading_system/README.md` - Module documentation
- Each profile's `SOUL.md` - Role definition

---

## Troubleshooting

**Data Worker fails:**
- Check Binance.US API (should work from US servers)
- Check Etherscan API key (100K/day limit)
- Check RSS feeds (network access)

**Orchestrator fails:**
- Ensure parent Data Worker task completed
- Check shared state file exists
- Verify method scoring logic

**Method Bot fails:**
- Check OHLCV data available (need 50+ candles)
- Verify strategy module imports
- Check position size limits

**Kanban tasks stuck:**
- `hermes kanban list` - Check status
- `hermes kanban show <id>` - View details
- `hermes kanban block <id> "reason"` - Block for review
- `hermes kanban unblock <id>` - Resume after fix
