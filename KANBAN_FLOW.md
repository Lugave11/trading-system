# Kanban-Driven Trading System

## Architecture Overview

All trading system components run as **Kanban tasks** with dedicated profiles.
All messaging flows through **Hermes Gateway** → Telegram.

```
┌─────────────────────────────────────────────────────────────┐
│                    HERMES GATEWAY                           │
│              (Messaging Orchestrator)                       │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Telegram   │  │   Discord    │  │    Slack     │      │
│  └─────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            ↑
                            │ kanban_complete()
                            │
┌─────────────────────────────────────────────────────────────┐
│                      KANBAN BOARD                           │
│                                                             │
│  ┌────────────┐   ┌──────────────┐   ┌──────────────┐     │
│  │   Data     │ → │ Orchestrator │ → │ Method Bots  │     │
│  │  Worker    │   │              │   │              │     │
│  └────────────┘   └──────────────┘   └──────────────┘     │
│       ↑                  ↑                  ↑               │
│  trading-data     trading-orch       trading-mr            │
│  (5 min)          (15 min)           (on signal)           │
└─────────────────────────────────────────────────────────────┘
```

---

## Kanban Task Flow

### 1. Data Worker (Every 5 Minutes)

**Profile:** `trading-data`
**Trigger:** Cron job or manual
**Output:** Market data, whale scores, news

**Task Template:**
```markdown
**Description:** Data Collection - BTC/ETH/SOL

**Body:**
Run the Data Worker to collect market data.

**Instructions:**
1. Fetch 15m candles from Binance.US for BTC, ETH, SOL
2. Calculate indicators (RSI, EMA20, volume ratio)
3. Calculate whale scores (volume anomaly)
4. Fetch crypto news from RSS feeds
5. Detect alerts (RSI < 30 or > 70)
6. Complete task with kanban_complete(output=data)

**Working Directory:** /mnt/data/hermes/workspace/trading_system
**Script:** data_worker_kanban.py
```

**Output Structure:**
```json
{
  "success": true,
  "coin_data": [
    {
      "symbol": "BTC",
      "ohlcv": { "indicators": { "rsi": 28, "current_price": 70000 } },
      "whale_score": 58,
      "news": { "sentiment": "neutral" }
    }
  ],
  "alerts": [
    { "type": "oversold", "symbol": "BTC", "rsi": 28 }
  ],
  "summary": {
    "coins_processed": 3,
    "alerts_triggered": 1,
    "average_whale_score": 52
  }
}
```

**Telegram Message:**
```
📊 Data Collection Complete

Coins: 3
Avg Whale Score: 52
Alerts: 1 ⚠️

🟢 BTC - OVERSOLD (RSI 28.0)
```

---

### 2. Orchestrator (Every 15 Minutes)

**Profile:** `trading-orchestrator`
**Trigger:** Cron job or manual
**Input:** Data Worker output (from parent task or shared state)
**Output:** Routing decisions, child task creation

**Task Template:**
```markdown
**Description:** Orchestrator Decision Cycle

**Body:**
Evaluate all coins and route to best-fit trading methods.

**Instructions:**
1. Load latest Data Worker output
2. For each coin:
   - Calculate mean_reversion score
   - Calculate momentum score
   - Calculate breakout score
   - Select best method
   - Decide: BUY (≥60), HOLD (45-59), SWITCH (<45)
3. For BUY signals:
   - Create child Kanban task for method bot
   - Assign to correct profile (trading-mean-reversion, etc.)
4. Complete task with kanban_complete(output=decisions)

**Working Directory:** /mnt/data/hermes/workspace/trading_system
**Script:** orchestrator_bot_kanban.py
```

**Output Structure:**
```json
{
  "decisions": [
    {
      "symbol": "BTC",
      "assignment": "BUY",
      "best_method": "mean_reversion",
      "best_score": 65,
      "reason": "RSI oversold (28.0) + price below EMA20 (-2.1%)"
    }
  ],
  "child_tasks": [
    {
      "task_id": "t_abc123",
      "symbol": "BTC",
      "method": "mean_reversion"
    }
  ]
}
```

**Telegram Message (BUY signals):**
```
🧠 Orchestrator Decision

BUY Signals: 1
HOLD: 2

🟢 BTC - Mean Reversion
   Score: 65 | RSI oversold (28.0) + price below EMA20 (-2.1%)
```

**Telegram Message (No signals):**
```
🧠 Orchestrator Decision

No BUY signals - All coins on HOLD

Evaluated: BTC, ETH, SOL
Best opportunity: ETH (52 score)

Market conditions not favorable for entries
```

---

### 3. Method Bot Execution (On Signal)

**Profile:** `trading-mean-reversion`, `trading-momentum`, `trading-breakout`
**Trigger:** Child task created by Orchestrator
**Input:** Coin data + decision from parent task
**Output:** Trade execution result

**Task Template (Mean Reversion):**
```markdown
**Description:** Mean Reversion Execution - BTC

**Body:**
Execute mean reversion trade for BTC.

**Decision Context:**
- Assignment: BUY
- Best Method: mean_reversion (score: 65)
- Reason: RSI oversold (28.0) + price below EMA20 (-2.1%)
- Current Price: $70,000

**Instructions:**
1. Load historical data for BTC
2. Generate RSI mean reversion signal
3. Calculate entry, stop loss (3%), take profit (6%)
4. Execute position (max $5)
5. Report via kanban_complete()

**Working Directory:** /mnt/data/hermes/workspace/trading_system
**Script:** mean_reversion_bot_kanban.py
```

**Output Structure:**
```json
{
  "success": true,
  "action": "OPEN_POSITION",
  "symbol": "BTC",
  "direction": "LONG",
  "entry_price": 70000,
  "position_size_usd": 5.0,
  "stop_loss": 67900,
  "take_profit": 74200,
  "rsi": 28.0,
  "reason": "RSI oversold + mean reversion setup"
}
```

**Telegram Message:**
```
🎯 Mean Reversion Signal - BTC

Direction: LONG
Entry: $70,000.00
Stop Loss: $67,900.00 (3.0%)
Take Profit: $74,200.00 (6.0%)
Position Size: $5.00
RSI: 28.0
Reason: RSI oversold + mean reversion setup

Risk/Reward: 1:2
```

---

## Cron Job Configuration

### Data Collection (Every 5 Minutes)

```bash
hermes cron create \
  --name "Data Collection (5min)" \
  --skill trading-system \
  "*/5 * * * *" \
  "Create a Kanban task for data collection.

Use kanban_create to create a task:
- description: 'Data Collection - BTC/ETH/SOL'
- assignee: 'trading-data'
- body: 'Run the Data Worker to collect market data...'

The trading-data profile will execute data_worker_kanban.py"
```

### Orchestrator (Every 15 Minutes)

```bash
hermes cron create \
  --name "Orchestrator (15min)" \
  --skill trading-system \
  "*/15 * * * *" \
  "Create a Kanban task for the Orchestrator.

First, use kanban_list to find the latest Data Worker task.
Then use kanban_create to create an Orchestrator task:
- description: 'Orchestrator Decision Cycle'
- assignee: 'trading-orchestrator'
- body: 'Evaluate all coins and route to best-fit methods...'

The trading-orchestrator profile will execute orchestrator_bot_kanban.py"
```

---

## Profile Configuration

### trading-data
```markdown
# Data Collection Specialist

**Role:** Collect market data, whale activity, news sentiment
**Runs:** Every 5 minutes
**Outputs:** JSON with coin data, alerts, news

**Tools:**
- Binance.US API (market data)
- Etherscan API (whale tracking)
- RSS feeds (news)

**Messaging:** All via kanban_complete() → Hermes Gateway
```

### trading-orchestrator
```markdown
# System Orchestrator

**Role:** Evaluate coins, select methods, create execution tasks
**Runs:** Every 15 minutes
**Inputs:** Data Worker output
**Outputs:** Decisions, child task creation

**Methods:**
- Mean Reversion (RSI-based)
- Momentum (trend-following)
- Breakout (consolidation + volume)

**Messaging:** All via kanban_complete() → Hermes Gateway
```

### trading-mean-reversion
```markdown
# Mean Reversion Execution Specialist

**Role:** Execute RSI mean reversion trades
**Triggered:** By Orchestrator BUY signal
**Strategy:** paper_trading_v4/strategies/rsi_mean_reversion.py

**Parameters:**
- RSI Period: 14
- Oversold: < 30 (LONG)
- Overbought: > 70 (SHORT)
- Stop Loss: 3%
- Take Profit: 6%
- Max Position: $5

**Messaging:** All via kanban_complete() → Hermes Gateway
```

---

## Message Flow

```
┌─────────────────┐
│  Cron Job       │
│  (5 min)        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Kanban Create  │  →  Task: t_data_123
│  (Data Worker)  │     Assignee: trading-data
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  trading-data   │
│  Profile Runs   │
│  data_worker_   │
│  kanban.py      │
└────────┬────────┘
         │
         │ kanban_complete(output=data)
         ▼
┌─────────────────┐
│  Hermes Gateway │  →  Telegram: "📊 Data Complete"
└─────────────────┘


┌─────────────────┐
│  Cron Job       │
│  (15 min)       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Kanban Create  │  →  Task: t_orch_456
│  (Orchestrator) │     Assignee: trading-orchestrator
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  trading-orch   │
│  Profile Runs   │
│  orchestrator_  │
│  bot_kanban.py  │
└────────┬────────┘
         │
         │ For each BUY signal:
         │ kanban_create() → Task: t_mr_789
         │                 Assignee: trading-mean-reversion
         │
         │ kanban_complete(output=decisions)
         ▼
┌─────────────────┐
│  Hermes Gateway │  →  Telegram: "🧠 Orchestrator Decision"
└─────────────────┘


┌─────────────────┐
│  trading-mr     │
│  Profile Runs   │
│  mean_rev_      │
│  bot_kanban.py  │
└────────┬────────┘
         │
         │ kanban_complete(output=execution)
         ▼
┌─────────────────┐
│  Hermes Gateway │  →  Telegram: "🎯 BTC BUY Signal"
└─────────────────┘
```

---

## Testing the System

### Manual Test - Data Worker

```bash
cd /mnt/data/hermes/workspace/trading_system

# Create Kanban task manually
hermes kanban create "Data Collection - Test" \
  --assignee trading-data \
  --body "Run data_worker_kanban.py"

# Check task status
hermes kanban list

# View output
hermes kanban show t_<task_id> --json
```

### Manual Test - Full Flow

```bash
# 1. Create Data Worker task
hermes kanban create "Data Collection - Full Test" \
  --assignee trading-data

# 2. Wait for completion, then create Orchestrator task
hermes kanban create "Orchestrator - Full Test" \
  --assignee trading-orchestrator \
  --parent t_<data_task_id>

# 3. Check for child tasks (method bot executions)
hermes kanban list --status ready

# 4. Monitor Telegram for messages
```

### Cron Test

```bash
# Trigger cron job manually
hermes cron run <job_id>

# Check Kanban board for created tasks
hermes kanban list --limit 10
```

---

## Benefits of Kanban-Driven Architecture

✅ **Clean Separation:** Bot logic vs messaging (Hermes handles all Telegram)
✅ **Audit Trail:** Every decision/task logged on Kanban board
✅ **Retry Logic:** Failed tasks can be re-run manually
✅ **Human Oversight:** Can review/edit tasks before execution
✅ **Profile Isolation:** Each component has dedicated resources
✅ **Scalability:** Easy to add new methods/bots as new profiles
✅ **Unified Messaging:** All messages flow through Hermes Gateway

---

## Migration Checklist

- [x] Create Kanban versions of all bots
  - [x] data_worker_kanban.py
  - [x] orchestrator_bot_kanban.py
  - [x] mean_reversion_bot_kanban.py
- [ ] Update cron jobs to create Kanban tasks (not run scripts directly)
- [ ] Test full flow: Data → Orchestrator → Method Bot
- [ ] Verify Telegram messages via Hermes Gateway
- [ ] Remove standalone script execution from production
- [ ] Document Kanban task templates for each component
