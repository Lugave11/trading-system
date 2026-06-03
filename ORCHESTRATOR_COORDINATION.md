# Orchestrator - Multi-Bot Coordination

## Overview

The Orchestrator is the **central coordination layer** for all trading bots. It prevents conflicts, enables hedging, and manages capital allocation.

---

## Responsibilities

| Function | Description |
|----------|-------------|
| **Load Positions** | Reads `state/positions.json` (source of truth) |
| **Conflict Detection** | Prevents contradictory positions BEFORE creating tasks |
| **Hedging Logic** | Creates derivatives SHORT to hedge existing spot |
| **Conviction Boosting** | Creates spot + derivatives LONG on high conviction |
| **Capital Enforcement** | Enforces $25 max capital, $5 per position |
| **Task Routing** | Creates Kanban tasks with coordination metadata |

---

## Coordination Scenarios

### 1. **Conviction Boost** (Spot + Derivatives LONG)

**When:** RSI < 30 + Etherscan BUY/STRONG_BUY

```
BTC: RSI 28.5, Etherscan BUY (72/100)

→ Spot BUY (Mean Reversion bot)
→ Derivatives LONG 2x (Derivatives bot)

Metadata:
{
  "coordination": {
    "type": "conviction_boost",
    "coordinated_with": "spot_BUY",
    "etherscan_signal": "BUY"
  },
  "conflict_check": "passed"
}
```

### 2. **Hedge** (Spot + Derivatives SHORT)

**When:** Holding spot + RSI > 70 (overbought)

```
ETH: Already holding spot, RSI now 75.2

→ Derivatives SHORT 2x (hedge existing spot)

Metadata:
{
  "coordination": {
    "type": "hedge",
    "hedging": "spot_position",
    "spot_coin": "ETH",
    "spot_entry": {...}
  },
  "conflict_check": "passed"
}
```

### 3. **Pure Derivatives** (No Spot Conflict)

**When:** RSI > 70, no existing spot

```
ETH: RSI 75.2, no spot position

→ Derivatives SHORT 2x (pure play)

Metadata:
{
  "coordination": {
    "type": "pure_derivatives"
  },
  "conflict_check": "passed"
}
```

### 4. **Conflict Avoided** (NOT Created)

**When:** Would create contradictory positions

```
BTC: RSI 28 (spot BUY signal)
     Derivatives SHORT also triggered

→ Spot BUY created
→ Derivatives SHORT SKIPPED (would conflict)

Logged:
"Skipped derivatives SHORT for BTC - would conflict with spot BUY"
```

---

## Capital Allocation

| Limit | Value |
|-------|-------|
| **Total Capital** | $25.00 max |
| **Per Position** | $5.00 max |
| **Spot + Derivatives** | Counted separately |
| **Hedge** | Requires available capital |

**Example:**
```
Spot positions: $10 (2 coins × $5)
Derivatives: $10 (2 coins × $5)
Total: $20/25 deployed
Available: $5 for new positions
```

---

## Decision Matrix

| Scenario | Spot | Derivatives | Created? | Why |
|----------|------|-------------|----------|-----|
| RSI < 30, Etherscan BUY | BUY | LONG | ✅ Both | Conviction boost |
| RSI < 30, Etherscan HOLD | BUY | None | ✅ Spot only | No conviction for deriv |
| RSI < 30, Etherscan SELL | BUY | SHORT | ❌ Deriv skipped | Conflict! |
| RSI > 70, Holding spot | HOLD | SHORT | ✅ Hedge | Protect spot |
| RSI > 70, No spot | None | SHORT | ✅ Pure deriv | No conflict |
| RSI 50-70, Holding spot | HOLD | None | ✅ Hold | Wait for signal |

---

## Files

| File | Purpose |
|------|---------|
| `orchestrator.py` | Main coordination logic (18KB) |
| `state/positions.json` | Position state (source of truth) |
| `ORCHESTRATOR_COORDINATION.md` | This documentation |

---

## Usage

### Test Mode
```bash
cd /mnt/data/hermes/workspace/trading_system
python3 orchestrator.py
```

### Integration with Kanban
```bash
# Data Worker completes discovery task
# Orchestrator task created
hermes kanban create \
  "🎯 Orchestrator - Multi-Bot Coordination" \
  --assignee trading-orchestrator \
  --body '{"discovery_task_id": "t_XXXX"}'

# Orchestrator runs, creates child tasks:
# - Mean Reversion BUY/SELL tasks
# - Derivatives LONG/SHORT tasks
# - Each with coordination metadata
```

---

## Output Example

```
================================================================================
TRADING ORCHESTRATOR - Multi-Bot Coordination
================================================================================

Evaluating 4 coins...
Current positions: 0 spot, 0 derivatives
Capital deployed: $0.00 / $25.00

Tasks to create: 5
Conflicts detected: 0
Hedges created: 0
Conviction boosts: 2

KANBAN COMMANDS:
--------------------------------------------------------------------------------
hermes kanban create "🟢 BUY BTC - Mean Reversion" --assignee trading-mean-reversion ...
hermes kanban create "🟢 LONG BTC - Derivatives" --assignee trading-derivatives ...
hermes kanban create "🔴 SHORT ETH - Derivatives" --assignee trading-derivatives ...
hermes kanban create "🟢 BUY SOL - Mean Reversion" --assignee trading-mean-reversion ...
hermes kanban create "🟢 LONG SOL - Derivatives" --assignee trading-derivatives ...

CONVICTION BOOSTS:
--------------------------------------------------------------------------------
  • BTC: Spot BUY + Derivatives LONG (BUY)
  • SOL: Spot BUY + Derivatives LONG (STRONG_BUY)
```

---

## Key Principles

1. **Single Source of Truth:** `state/positions.json` tracks everything
2. **Prevent, Don't Fix:** Detect conflicts BEFORE creating tasks
3. **Metadata Matters:** Coordination info travels with Kanban task
4. **Final Check:** Bots double-check before executing
5. **Capital First:** Never exceed $25 total, $5 per position
