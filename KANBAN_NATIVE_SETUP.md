# 🚀 Kanban Trading System - Complete Setup

## Overview

**100% Native Kanban** - All trading operations execute through Kanban tasks with embedded scripts.

---

## Task Chain

```
📊 Data Worker (5 min)
  ↓ Executes: python3 data_worker_live.py
  ↓ Updates: state/discovery_results.json
  ↓ Creates: Next Data Worker task
  
🎯 Orchestrator (15 min)
  ↓ Executes: python3 orchestrator_live.py
  ↓ Reads: discovery_results.json
  ↓ Creates: LONG/SHORT trading tasks
  ↓ Creates: Next Orchestrator task

🟢 LONG / 🔴 SHORT (on signal)
  ↓ Executes: derivatives_bot.py with task metadata
  ↓ Opens position
  ↓ Creates: Monitor task

👁️ Monitor (5 min)
  ↓ Checks exit conditions
  ↓ Creates: Close task (if exit)
  ↓ Recreates: Monitor (if hold)
```

---

## Initial Setup Commands

Run these ONCE to start the system:

### 1. Data Worker (Recurring)

```bash
hermes kanban create "📊 Data Worker - Cycle 1" \
  --assignee trading-data \
  --body "EXECUTE: cd /mnt/data/hermes/workspace/trading_system && python3 data_worker_live.py

ACTIONS:
1. Run the script above
2. Verify state/discovery_results.json updated
3. Create next task:
   hermes kanban create '📊 Data Worker - Cycle 2' --assignee trading-data --body 'EXECUTE: cd /mnt/data/hermes/workspace/trading_system && python3 data_worker_live.py'

INTERVAL: 300 seconds (5 min)"
```

### 2. Orchestrator (Recurring)

```bash
hermes kanban create "🎯 Orchestrator - Cycle 1" \
  --assignee trading-orchestrator \
  --body "EXECUTE: cd /mnt/data/hermes/workspace/trading_system && python3 orchestrator_live.py

ACTIONS:
1. Wait for Data Worker to complete (check state/discovery_results.json timestamp)
2. Run the script above
3. Review signals created
4. Create next task:
   hermes kanban create '🎯 Orchestrator - Cycle 2' --assignee trading-orchestrator --body 'EXECUTE: cd /mnt/data/hermes/workspace/trading_system && python3 orchestrator_live.py'

INTERVAL: 900 seconds (15 min)"
```

### 3. Dispatch

```bash
hermes kanban dispatch
```

---

## Monitoring

### View Board
```bash
hermes kanban list | grep -E "(Data Worker|Orchestrator)"
```

### Check Latest Data
```bash
cat /mnt/data/hermes/workspace/trading_system/state/discovery_results.json | jq '.timestamp'
```

### Check Positions
```bash
cat /mnt/data/hermes/workspace/trading_system/state/derivatives_positions.json | jq 'keys'
```

---

## Task Body Template

Every task should have this structure:

```markdown
# Task Title

**EXECUTE:** <command to run>

**ACTIONS:**
1. <step 1>
2. <step 2>
3. <create next task>

**INTERVAL:** <recurring interval>
```

---

## Current Status

- Data Worker task created: t_4fda4d0a
- Orchestrator task: Pending creation
- System status: Starting...

---

## Next Steps

1. ✅ Data Worker task created
2. ⏳ Create Orchestrator task
3. ⏳ Dispatch both tasks
4. ⏳ Monitor execution
5. ⏳ Verify auto-recreate working

---

**Native Kanban System - No standalone scripts!**
