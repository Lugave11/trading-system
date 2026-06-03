# Trading System Kanban Tasks

## Overview
All trading system tasks run via Kanban board. Each task:
- Assigned to specific profile (trading-data, trading-orchestrator, trading-momentum)
- Outputs JSON via `kanban_complete()` for downstream tasks
- Runs on cron schedule or triggered by alerts

---

## Task 1: Data Collection (Every 5 Minutes)

**Assignee:** `trading-data`

**Prompt:**
```
Run the Data Worker to collect market data for BTC, ETH, SOL.

Execute:
```python
from data_worker import run_data_collection_cycle

result = run_data_collection_cycle(["BTC", "ETH", "SOL"])
```

Report via kanban_complete() with this exact structure:
```json
{
  "task": "data_collection",
  "timestamp": "<ISO timestamp>",
  "success": true/false,
  "summary": {
    "coins_processed": 3,
    "alerts_triggered": 0,
    "average_whale_score": 52.7
  },
  "coin_data": [
    {
      "symbol": "BTC",
      "whale_score": 50,
      "current_price": 70000,
      "ohlcv": {...},
      "market": {...},
      "whale": {...},
      "news": {...}
    }
  ],
  "alerts": []
}
```

If alerts are triggered (whale_score > 80 OR major news), also send immediate Telegram message to user.
```

**Cron Schedule:** `*/5 * * * *` (every 5 minutes)

**Output:** JSON saved to Kanban task, readable by Orchestrator

---

## Task 2: Make Decisions (Every 15 Minutes)

**Assignee:** `trading-orchestrator`

**Prompt:**
```
Run the Orchestrator to make trading decisions.

1. Find the latest completed "Data Collection" task output:
   - Use: kanban list --assignee trading-data --status completed
   - Read the most recent task's kanban_complete() output

2. Execute Orchestrator with that data:
```python
from orchestrator import run_orchestration_cycle

# Pass coin_data from Data Worker output
orchestrator_result = run_orchestration_cycle(data_worker_output=latest_data)
```

3. Report via kanban_complete() with this structure:
```json
{
  "task": "orchestration",
  "timestamp": "<ISO timestamp>",
  "success": true/false,
  "decisions": [
    {
      "symbol": "BTC",
      "assignment": "BUY|HOLD|SWITCH",
      "best_method": "momentum|mean_reversion|breakout",
      "best_score": 65,
      "reason": "..."
    }
  ],
  "summary": {
    "buy_signals": 2,
    "hold_signals": 1,
    "switch_signals": 0
  }
}
```

4. For each BUY decision, create a new Kanban task:
   - Assignee: trading-momentum (or appropriate method bot)
   - Body: Execute entry for {symbol} with details from decision
```

**Cron Schedule:** `*/15 * * * *` (every 15 minutes)

**Trigger:** Also runs immediately if Data Worker triggers alert

---

## Task 3: Execute Momentum (On BUY Signal)

**Assignee:** `trading-momentum`

**Prompt:**
```
Execute a momentum trade based on Orchestrator decision.

Input: Read from parent Orchestrator task output

Decision details:
- Symbol: {symbol}
- Action: BUY
- Method: momentum
- Max capital: $5

Execute:
1. Calculate entry price (current market price)
2. Calculate position size ($5 max, or less if risk management says so)
3. Place order (paper trading mode - just log, no real execution yet)
4. Monitor position every 5 minutes

Report via kanban_complete():
```json
{
  "task": "momentum_execution",
  "symbol": "BTC",
  "action": "BUY",
  "entry_price": 70000,
  "position_size_usd": 5,
  "stop_loss": 66500,
  "target": 73500,
  "status": "OPEN"
}
```
```

**Cron Schedule:** None (triggered by Orchestrator)

---

## Task 4: Monitor Positions (Every 5 Minutes)

**Assignee:** `trading-momentum`

**Prompt:**
```
Monitor all open positions.

1. Find all completed "Execute Momentum" tasks with status "OPEN"
2. For each position:
   - Fetch current price
   - Check exit conditions (stop loss, target, time-based)
   - Update position status

Report via kanban_complete():
```json
{
  "task": "position_monitor",
  "positions": [
    {
      "symbol": "BTC",
      "entry_price": 70000,
      "current_price": 70500,
      "pnl_usd": 2.50,
      "pnl_pct": 0.71,
      "status": "OPEN"
    }
  ]
}
```
```

**Cron Schedule:** `*/5 * * * *` (every 5 minutes)

---

## Task 5: Performance Report (Every 30 Minutes)

**Assignee:** `trading-analyst`

**Prompt:**
```
Generate performance report for the user.

1. Aggregate all completed tasks from:
   - Data Collection (last 30 min)
   - Orchestration (last 30 min)
   - Execution tasks (all today)

2. Calculate:
   - Total trades executed
   - Win rate
   - Total PnL
   - Best/worst performing method
   - Current open positions

3. Send Telegram message to user with summary
```

**Cron Schedule:** `*/30 * * * *` (every 30 minutes)

---

## State Management

**No shared state files.** All state lives in Kanban task outputs:

- Data Worker → `kanban_complete(output=json)`
- Orchestrator → Reads previous Data Worker task output via `kanban list`
- Method Bots → Reads Orchestrator task output

**Benefits:**
- All history preserved in Kanban board
- Can replay/debug any past decision
- No file I/O race conditions
- Native Hermes workflow

---

## Setup Commands

```bash
# Create Data Worker task (recurring)
hermes kanban create "Data Collection" \
  --assignee trading-data \
  --schedule "*/5 * * * *" \
  --prompt "<prompt from Task 1 above>"

# Create Orchestrator task (recurring)
hermes kanban create "Make Decisions" \
  --assignee trading-orchestrator \
  --schedule "*/15 * * * *" \
  --prompt "<prompt from Task 2 above>"

# Create Position Monitor task (recurring)
hermes kanban create "Monitor Positions" \
  --assignee trading-momentum \
  --schedule "*/5 * * * *" \
  --prompt "<prompt from Task 4 above>"

# Create Analyst task (recurring)
hermes kanban create "Performance Report" \
  --assignee trading-analyst \
  --schedule "*/30 * * * *" \
  --prompt "<prompt from Task 5 above>"
```
