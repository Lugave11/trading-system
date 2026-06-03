# Kanban-Driven Data Worker - Complete Workflow

## Core Principle

**NO standalone scripts. EVERYTHING flows through Kanban tasks.**

```
❌ WRONG: python3 data_worker_unified.py
✅ RIGHT: hermes kanban create "🔍 Data Discovery" --assignee trading-data
```

---

## Complete Kanban Flow

### Phase 1: Orchestrator Initiates Discovery

```bash
# Orchestrator creates discovery task
hermes kanban create \
  "🔍 Data Discovery - Find Top Opportunities" \
  --assignee trading-data \
  --metadata '{
    "task_type": "data_discovery",
    "mode": "discovery",
    "coins": null,
    "instructions": "Scan all 15 candidates, select top 3-5 opportunities"
  }'
```

**Result:**
```
Created task: t_abc123
Status: todo
Assignee: trading-data
```

---

### Phase 2: Data Worker Executes (Via Kanban)

**Worker picks up task from Kanban board:**

```bash
# Worker checks assigned tasks
hermes kanban list --assignee trading-data --status todo

# Output:
# ✓ t_abc123  todo  trading-data  🔍 Data Discovery - Find Top Opportunities
```

**Worker executes ALL 4 functions:**

```python
# data_worker_kanban_execution.py

import json
import subprocess
from pathlib import Path

# 1. Get task from Kanban
task_id = "t_abc123"
task = get_kanban_task(task_id)  # Via hermes kanban show

# 2. Load task metadata
metadata = json.loads(task['metadata'])
mode = metadata.get('mode', 'discovery')
assigned_coins = metadata.get('coins')

# 3. Execute Function 1: Coin Discovery
print("📊 FUNCTION 1: Coin Discovery")
discovery_result = run_coin_discovery()
# Returns: {selected: [ETH, SOL, BNB], ...}

# 4. Execute Function 2: Whale Tracking
print("🐋 FUNCTION 2: Whale Tracking")
whale_result = run_whale_tracking()
# Returns: {signals: [...], counts: {...}}

# 5. Execute Function 3: Glassnode Analysis
print("🔍 FUNCTION 3: Glassnode Analysis")
coins_to_analyze = [c['symbol'] for c in discovery_result['selected']]
glassnode_result = run_glassnode_bulk(coins_to_analyze)
# Returns: {signals: {ETH: 'BUY', SOL: 'HOLD', ...}}

# 6. Execute Function 4: Technical Analysis (placeholder)
print("📈 FUNCTION 4: Technical Analysis")
ta_result = run_technical_placeholder(coins_to_analyze)

# 7. Aggregate Results
unified_result = aggregate_all(discovery_result, whale_result, glassnode_result, ta_result)

# 8. Create Child Tasks for Significant Findings
child_tasks = []

# Create tasks for whale alerts
for signal in whale_result['signals']:
    if signal['value_usd'] > 5_000_000:
        child_task = create_kanban_task(
            title=f"🐋 {signal['signal']}: ${signal['value_usd']:,.0f} {signal['symbol']}",
            assignee='trading-data',
            parent=task_id,
            metadata={'type': 'whale_alert', 'signal': signal}
        )
        child_tasks.append(child_task)

# Create tasks for coin-specific analysis
for coin in unified_result['coins'].values():
    if coin['final_signal'] == 'BEARISH' or coin['final_signal'] == 'BULLISH':
        child_task = create_kanban_task(
            title=f"{get_emoji(coin['final_signal'])} {coin['symbol']} - {coin['recommendation']}",
            assignee='trading-data',
            parent=task_id,
            metadata={'type': 'coin_analysis', 'coin': coin}
        )
        child_tasks.append(child_task)

# 9. Complete Parent Task
complete_kanban_task(
    task_id=task_id,
    result=f"✅ Analyzed {len(coins_to_analyze)} coins, found {len(whale_result['signals'])} whale signals, created {len(child_tasks)} tasks",
    summary=json.dumps({
        'coins_analyzed': len(coins_to_analyze),
        'selected_coins': coins_to_analyze,
        'whale_signals': len(whale_result['signals']),
        'child_tasks': len(child_tasks),
        'sentiment': unified_result['summary'],
    }),
    metadata=unified_result
)
```

---

### Phase 3: Orchestrator Reviews & Decides

**Orchestrator task is auto-created or triggered:**

```bash
# Orchestrator checks completed Data Worker tasks
hermes kanban list --assignee trading-orchestrator --status todo

# Output:
# ✓ t_def456  todo  trading-orchestrator  🎯 Evaluate Discovery Results
```

**Orchestrator reads Data Worker results:**

```python
# orchestrator_kanban_execution.py

# 1. Get completed Data Worker task
dw_task = get_completed_task('t_abc123')
dw_metadata = json.loads(dw_task['metadata'])

# 2. Review unified results
coins = dw_metadata['coins']
whale_signals = dw_metadata['whale']['signals']

# 3. Make per-coin decisions
decisions = {}
for symbol, coin in coins.items():
    # Combine signals
    discovery_score = coin.get('discovery_score', 0)
    glassnode_signal = coin.get('glassnode_signal', 'HOLD')
    whale_sentiment = get_whale_sentiment(symbol, whale_signals)
    
    # Decision logic
    if glassnode_signal == 'STRONG_SELL':
        decisions[symbol] = 'EXIT'
    elif glassnode_signal == 'STRONG_BUY' and discovery_score > 70:
        decisions[symbol] = 'ENTER_LONG'
    elif whale_sentiment == 'BEARISH' and discovery_score > 60:
        decisions[symbol] = 'REDUCE'
    else:
        decisions[symbol] = 'HOLD'

# 4. Create Trading-Floor tasks for decisions
for symbol, decision in decisions.items():
    if decision in ['EXIT', 'ENTER_LONG', 'REDUCE']:
        create_kanban_task(
            title=f"🚨 {decision} {symbol} Position",
            assignee='trading-floor',
            parent=orchestrator_task_id,
            metadata={
                'type': 'execution',
                'coin': symbol,
                'decision': decision,
                'reasoning': f"Based on {glassnode_signal} + whale {whale_sentiment}"
            }
        )

# 5. Complete Orchestrator task
complete_kanban_task(
    task_id=orchestrator_task_id,
    result=f"Made decisions for {len(decisions)} coins: {decisions}",
    metadata={'decisions': decisions}
)
```

---

### Phase 4: Trading Floor Executes

```bash
# Trading-Floor checks assigned tasks
hermes kanban list --assignee trading-floor --status todo

# Output:
# ✓ t_ghi789  todo  trading-floor  🚨 EXIT ETH Position
# ✓ t_jkl012  todo  trading-floor  🚨 ENTER_LONG SOL Position
```

**Execution:**

```python
# trading_floor_execution.py

# 1. Get task
task = get_kanban_task('t_ghi789')
metadata = json.loads(task['metadata'])

symbol = metadata['coin']
decision = metadata['decision']

# 2. Execute trade
if decision == 'EXIT':
    result = execute_sell(symbol)
elif decision == 'ENTER_LONG':
    result = execute_buy(symbol)
elif decision == 'REDUCE':
    result = execute_partial_sell(symbol, percentage=50)

# 3. Complete task with result
complete_kanban_task(
    task_id='t_ghi789',
    result=f"✅ {decision} {symbol}: Sold {result['amount']} @ ${result['price']} | PnL: {result['pnl']:.2f}%",
    metadata={'execution': result}
)
```

---

## Complete Task Chain Example

```
t_abc123  🔍 Data Discovery - Find Top Opportunities
├─ Assignee: trading-data
├─ Status: completed
├─ Result: "Analyzed 15 coins, found 2 whale signals, created 3 tasks"
│
├── t_def456  🎯 Evaluate Discovery Results
│   ├─ Assignee: trading-orchestrator
│   ├─ Status: completed
│   ├─ Result: "Decisions: ETH=EXIT, SOL=ENTER_LONG, BNB=HOLD"
│   │
│   ├── t_ghi789  🚨 EXIT ETH Position
│   │   ├─ Assignee: trading-floor
│   │   ├─ Status: completed
│   │   └─ Result: "Sold 0.5 ETH @ $1,837 | PnL: +2.3%"
│   │
│   └── t_jkl012  🚨 ENTER_LONG SOL Position
│       ├─ Assignee: trading-floor
│       ├─ Status: completed
│       └─ Result: "Bought 0.3 SOL @ $142 | Position opened"
│
├── t_mno345  🐋 BEARISH: $23.8M ETH - 0x77134cbc... → Bitfinex...
│   ├─ Assignee: trading-data
│   ├─ Status: completed
│   └─ Result: "Confirmed: Large exchange inflow, 3rd in series"
│
└── t_pqr678  🟢 SOL - ENTER_LONG
    ├─ Assignee: trading-data
    ├─ Status: completed
    └─ Result: "High opportunity score (78), Glassnode BUY, whale accumulation"
```

---

## Kanban Commands Reference

### Create Task
```bash
hermes kanban create \
  "TITLE" \
  --assignee trading-data \
  --body "Detailed description..." \
  --metadata '{"key": "value"}' \
  --parent t_parent_id
```

### List Tasks
```bash
# All tasks for profile
hermes kanban list --assignee trading-data

# Filter by status
hermes kanban list --assignee trading-data --status todo

# Filter by parent
hermes kanban list --parent t_abc123
```

### Show Task
```bash
hermes kanban show t_abc123
```

### Complete Task
```bash
hermes kanban complete t_abc123 \
  --result "✅ Completed with X" \
  --summary "Brief summary" \
  --metadata '{"data": "value"}'
```

### Add Comment
```bash
hermes kanban comment t_abc123 \
  "Additional context or analysis..."
```

### Link Tasks (Dependency)
```bash
# t_def456 depends on t_abc123
hermes kanban link t_abc123 t_def456
```

### Unlink Tasks
```bash
hermes kanban unlink t_abc123 t_def456
```

---

## Profiles & Responsibilities

| Profile | Responsibilities | Tasks |
|---------|-----------------|-------|
| **trading-data** | - Coin discovery<br>- Whale tracking<br>- Glassnode analysis<br>- Technical analysis | - 🔍 Data Discovery<br>- 🐋 Whale Alerts<br>- 📊 Coin Analysis |
| **trading-orchestrator** | - Review discovery results<br>- Make EXIT/ENTER/HOLD decisions<br>- Create execution tasks | - 🎯 Evaluate Results<br>- 🎯 Make Decisions |
| **trading-floor** | - Execute trades<br>- Monitor positions<br>- Report PnL | - 🚨 EXIT Position<br>- 🚨 ENTER Position<br>- 📊 Monitor |
| **trading-momentum** | - Momentum-specific analysis<br>- Run momentum strategies | - 📈 Momentum Analysis<br>- 📊 Run Strategy |

---

## Cron Integration (Kanban-Driven)

```bash
# Orchestrator - Every 15 minutes
*/15 * * * * /mnt/data/hermes/workspace/.local/bin/hermes kanban create \
  "🔍 Data Discovery - Scheduled Run" \
  --assignee trading-data \
  --metadata '{"type": "scheduled", "schedule": "15min"}' \
  >> /var/log/kanban_orchestrator.log 2>&1

# Data Worker - Polls every 5 minutes for new tasks
*/5 * * * * /mnt/data/hermes/workspace/.local/bin/hermes kanban list \
  --assignee trading-data --status todo \
  | grep -q "🔍" && python3 /mnt/data/hermes/workspace/trading_system/data_worker_kanban_execution.py \
  >> /var/log/kanban_data_worker.log 2>&1
```

---

## Key Principles

1. **NO Standalone Execution**
   - ❌ `python3 data_worker_unified.py`
   - ✅ `hermes kanban create "🔍 Data Discovery"` → Worker picks up task

2. **Tasks Carry All Context**
   - Metadata contains: mode, coins, thresholds, instructions
   - Body contains: Detailed requirements
   - Comments contain: Updates during execution

3. **Parent-Child Relationships**
   - Orchestrator task → Data Worker task → Analysis tasks
   - Completion of parent auto-unblocks children

4. **Results in Metadata**
   - Every completed task has structured metadata
   - Downstream tasks read parent metadata
   - No external state files needed

5. **Audit Trail**
   - Every decision tracked in Kanban
   - Full history of who did what when
   - Easy to debug/replay

---

## Files to Create

1. **`data_worker_kanban_execution.py`** - Worker that polls Kanban and executes tasks
2. **`orchestrator_kanban_execution.py`** - Orchestrator that reviews & decides
3. **`trading_floor_execution.py`** - Executes trades from tasks
4. **`kanban_workflow.md`** - This document (workflow reference)

---

## Next Steps

1. **Create Kanban execution scripts** (no standalone runs)
2. **Test full flow** with real Kanban tasks
3. **Set up cron** to create Orchestrator tasks every 15 min
4. **Monitor & iterate** based on real execution
