# Kanban-Driven Coin Selection - Complete Flow

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    KANBAN-DRIVEN FLOW                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. CRON (*/15 * * * *)                                        │
│     │                                                           │
│     └─→ Creates: "Orchestrator Cycle" task                      │
│         Assignee: trading-orchestrator                          │
│                                                                 │
│  2. ORCHESTRATOR Executes                                       │
│     │                                                           │
│     ├─→ Creates CHILD task: "Coin Discovery"                    │
│     │   Assignee: trading-data                                  │
│     │   Instruction: "Scan market, rank by opportunity"         │
│     │                                                           │
│     ├─→ WAITS for Data Worker completion                        │
│     │   (polls every 5s, timeout 120s)                          │
│     │                                                           │
│     ├─→ Reads discovery report from child task output           │
│     │   (4 coins: BTC, ETH, XRP, BNB)                           │
│     │                                                           │
│     ├─→ For each coin, calculates method scores:                │
│     │   - Mean Reversion (RSI-based)                            │
│     │   - Momentum (trend-based)                                │
│     │   - Breakout (volume-based)                               │
│     │                                                           │
│     ├─→ Creates CHILD tasks for Method Bots:                    │
│     │   - "BTC Momentum - Score 65" → trading-momentum          │
│     │   - "ETH Momentum - Score 65" → trading-momentum          │
│     │   - "XRP Momentum - Score 65" → trading-momentum          │
│     │   (BNB skipped - score 35 < 60)                           │
│     │                                                           │
│     └─→ Completes silently (or 2-hr summary to Gateway)         │
│                                                                 │
│  3. DATA WORKER Executes (child task)                           │
│     │                                                           │
│     ├─→ Scans 15 candidate coins                                │
│     ├─→ Calculates opportunity scores                           │
│     ├─→ Selects top 4 (BTC, ETH, XRP, BNB)                      │
│     ├─→ Collects OHLCV + indicators                             │
│     └─→ Completes with discovery report (silent)                │
│                                                                 │
│  4. METHOD BOTS Execute (child tasks)                           │
│     │                                                           │
│     ├─→ Read task metadata (entry, stop, target)                │
│     ├─→ Execute trade                                           │
│     ├─→ Create MONITOR task                                     │
│     └─→ Complete with Gateway message (Telegram)                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Task Tree Structure

```
t_orch_abc123 (Orchestrator Cycle)
│
├── t_data_def456 (Data Worker - Coin Discovery)
│   ├── Scanned: 15 coins
│   ├── Qualified: 4 coins (score >= 50)
│   └── Output: {discovered_coins: [BTC, ETH, XRP, BNB], ...}
│
├── t_mom_ghi789 (Momentum Bot - BTC)
│   ├── Reason: Momentum score 65 (best of 3 methods)
│   ├── Entry: $67,220
│   ├── Stop: $65,203 (3%)
│   ├── Target: $71,253 (6%)
│   └── Output: "🎯 BTC BUY - Entry $67,220"
│
├── t_mom_jkl012 (Momentum Bot - ETH)
│   ├── Reason: Momentum score 65
│   ├── Entry: $1,890
│   └── Output: "🎯 ETH BUY - Entry $1,890"
│
└── t_mom_mno345 (Momentum Bot - XRP)
    ├── Reason: Momentum score 65
    ├── Entry: $1.22
    └── Output: "🎯 XRP BUY - Entry $1.22"
```

**BNB NOT traded** - Best method (Mean Reversion) scored only 35 (< 60 threshold)

---

## Live Test Results

### Step 1: Data Worker Discovery

```
🔍 Scanning 15 candidate coins...
  ✓ BTC: Score 67.8 | Vol: $6.2M | Change: -5.31% | Whale: 65
  ✓ ETH: Score 53.0 | Vol: $1.6M | Change: -5.02% | Whale: 65
  ✓ XRP: Score 51.6 | Vol: $1.1M | Change: -5.55% | Whale: 65
  ✓ BNB: Score 50.5 | Vol: $0.8M | Change: -5.05% | Whale: 65
    SOL: Score 49.0 (rejected - below 50)
    ... (10 more coins rejected)

📋 Top 4 coins selected:
  #1: BTC (score: 67.8)
  #2: ETH (score: 53.0)
  #3: XRP (score: 51.6)
  #4: BNB (score: 50.5)

📈 Collecting detailed data...
  ✓ BTC: RSI 37.5 | Trend: bearish | Price: $67,220
  ✓ ETH: RSI 33.5 | Trend: bearish | Price: $1,890
  ✓ XRP: RSI 38.8 | Trend: bearish | Price: $1.22
  ✓ BNB: RSI 21.2 | Trend: bearish | Price: $657
```

---

### Step 2: Orchestrator Evaluation

| Coin | Mean Reversion | Momentum | Breakout | Best Method | Decision |
|------|---------------|----------|----------|-------------|----------|
| **BTC** | 40 | **65** ✅ | 0 | Momentum | 🟢 BUY |
| **ETH** | 0 | **65** ✅ | 0 | Momentum | 🟢 BUY |
| **XRP** | 40 | **65** ✅ | 0 | Momentum | 🟢 BUY |
| **BNB** | **35** | 25 | 35 | Mean Reversion | 🔴 HOLD |

**Why Momentum for BTC/ETH/XRP?**
- RSI 33-38 (oversold but not extreme)
- Bearish trend (price < EMA20)
- 5%+ daily moves (momentum conditions)

**Why HOLD for BNB?**
- RSI 21.2 (extremely oversold)
- But method scores all < 60
- Best: Mean Reversion 35 (needs RSI 35-65 for high score)

---

### Step 3: Method Bot Tasks Created

**3 BUY signals generated:**

1. **BTC Momentum** - Score 65
   - Entry: $67,220
   - Stop: $65,203 (3%)
   - Target: $71,253 (6%)

2. **ETH Momentum** - Score 65
   - Entry: $1,890
   - Stop: $1,833 (3%)
   - Target: $2,003 (6%)

3. **XRP Momentum** - Score 65
   - Entry: $1.22
   - Stop: $1.18 (3%)
   - Target: $1.29 (6%)

---

## Separation of Concerns

| Component | Responsibility | Output |
|-----------|---------------|--------|
| **Data Worker** | - Scan 15 candidates<br>- Calculate opportunity scores<br>- Select top 3-5<br>- Collect OHLCV + indicators | Discovery report (JSON) |
| **Orchestrator** | - Request discovery<br>- Evaluate method scores<br>- Select best method<br>- Create Method Bot tasks | Routing decisions |
| **Method Bots** | - Execute specific strategy<br>- Manage entry/stop/target<br>- Report to Gateway | Telegram message |

**Key Principle:** Data Worker does NOT make trading decisions. It only presents research. Orchestrator makes all routing decisions.

---

## Kanban Task Lifecycle

### Orchestrator Task (Parent)

```yaml
Task: t_orch_abc123
Title: "Orchestrator Cycle"
Assignee: trading-orchestrator
Status: in_progress → done
Children: [t_data_def456, t_mom_ghi789, t_mom_jkl012, t_mom_mno345]
Output: {
  "discovered_coins": 4,
  "signals_generated": 3,
  "decisions": [...]
}
Completion: silent (15-min cycle) or summary (2-hr cycle)
```

### Data Worker Task (Child 1)

```yaml
Task: t_data_def456
Title: "Coin Discovery - Market Scan"
Assignee: trading-data
Parent: t_orch_abc123
Status: in_progress → done
Output: {
  "discovered_coins": [BTC, ETH, XRP, BNB],
  "selection_summary": {...}
}
Completion: silent=True (internal research)
```

### Method Bot Tasks (Children 2-4)

```yaml
Task: t_mom_ghi789
Title: "BTC Momentum - Score 65"
Assignee: trading-momentum
Parent: t_orch_abc123
Status: in_progress → done
Metadata: {
  "symbol": "BTC",
  "method": "momentum",
  "entry_price": 67220,
  "stop_loss": 65203,
  "take_profit": 71253
}
Output: {
  "symbol": "BTC",
  "action": "LONG",
  "entry": 67220
}
Completion: summary="🎯 BTC BUY - Entry $67,220" (Gateway message)
```

---

## Benefits of Kanban-Driven Design

| Benefit | Explanation |
|---------|-------------|
| **Audit Trail** | Every decision traced: Discovery → Evaluation → Execution |
| **Task Isolation** | Each component runs in separate profile with own SOUL.md |
| **Retry Logic** | Failed tasks can be retried without restarting entire cycle |
| **Parallel Execution** | Method Bots can execute in parallel (BTC, ETH, XRP simultaneously) |
| **Human Readable** | Each task has clear title, description, metadata |
| **Gateway Integration** | Only Method Bots send Telegram messages (no spam) |
| **Flexible Scheduling** | Can change Orchestrator frequency without touching Data Worker |

---

## Implementation Checklist

- [x] **Data Worker Discovery** - `data_worker_discovery.py` (complete)
- [x] **Orchestrator Kanban** - `orchestrator_kanban.py` (complete)
- [x] **Test Discovery** - ✅ BTC, ETH, XRP, BNB selected
- [x] **Test Orchestration** - ✅ 3 BUY signals (BTC, ETH, XRP Momentum)
- [ ] **Kanban Integration** - Wire up `kanban_create`, `kanban_complete`
- [ ] **Cron Jobs** - Update to create Orchestrator task (not direct execution)
- [ ] **Method Bots** - Update to read from Kanban task metadata
- [ ] **End-to-End Test** - Full flow with real Kanban tasks

---

## Next Steps

1. **Update Cron Jobs** - Remove direct execution, create Kanban tasks instead
2. **Test Kanban Integration** - Run with real Kanban module
3. **Verify Task Tree** - Confirm parent-child relationships
4. **Test 2-Hour Summary** - Ensure Gateway messages work
5. **Monitor First Live Cycle** - Watch full flow in production

---

## Current Test Results Summary

**Discovery:** ✅ 4 coins qualified (BTC, ETH, XRP, BNB)
**Evaluation:** ✅ 3 BUY signals (BTC, ETH, XRP Momentum)
**Routing:** ✅ Method tasks would be created (Kanban not available in test)
**Execution:** ⏳ Pending Kanban integration

**Market Condition:** Bearish trend, high volatility (5%+ moves)
**Dominant Strategy:** Momentum (oversold + bearish trend)
**Skipped:** BNB (no method >= 60 threshold)
