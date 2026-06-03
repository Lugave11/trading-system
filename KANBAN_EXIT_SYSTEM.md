# Kanban-Driven Position Exit System

## Overview

**Problem:** Current system only enters LONG positions. When Glassnode detects STRONG_SELL (whale distribution), we need to EXIT existing positions before the crash.

**Solution:** Pure Kanban-driven exit flow - no direct API calls, all through Kanban tasks.

---

## Architecture

### New Components

| Component | File | Purpose |
|-----------|------|---------|
| **Trading-Floor Profile** | `/mnt/data/hermes/profiles/trading-floor/` | Position execution specialist |
| **Position Manager** | `position_manager.py` | State management (open positions, PnL) |
| **EXIT Tasks** | Kanban tasks | Emergency exit orders from Orchestrator |

### Modified Components

| Component | Change |
|-----------|--------|
| **Data Worker** | Returns `action_required: 'EXIT'` on STRONG_SELL |
| **Orchestrator** | Creates EXIT tasks when `action_required == 'EXIT'` |

---

## Complete Flow: STRONG_SELL Scenario

```
┌─────────────────────────────────────────────────────────────────┐
│  CYCLE: 2026-06-03 00:30 UTC                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. CRON (*/15 * * * *)                                         │
│     │                                                           │
│     └─→ Creates: t_orch_123 (Orchestrator Cycle)                │
│         Assignee: trading-orchestrator                          │
│                                                                 │
│  2. ORCHESTRATOR Executes                                       │
│     │                                                           │
│     ├─→ Creates child: t_data_456 (Coin Discovery)              │
│     │   Assignee: trading-data                                  │
│     │                                                           │
│  3. DATA WORKER Executes                                        │
│     │                                                           │
│     ├─→ Scans 15 coins                                          │
│     ├─→ Fetches Glassnode: STRONG_SELL (17.5/100)              │
│     ├─→ Applies HARD BLOCK (-100 pts)                           │
│     ├─→ Result: 0 coins qualify (all blocked)                   │
│     │                                                           │
│     └─→ Completes with report:                                  │
│         {                                                       │
│           'discovered_coins': [],                               │
│           'glassnode_signal': {                                 │
│             'signal': 'STRONG_SELL',                            │
│             'bias': 'BLOCK_LONG',                               │
│           },                                                    │
│           'action_required': 'EXIT'  ← KEY FLAG                 │
│         }                                                       │
│                                                                 │
│  4. ORCHESTRATOR Reads Report                                   │
│     │                                                           │
│     ├─→ Sees: action_required = 'EXIT'                          │
│     ├─→ Checks: position_manager.has_positions() → TRUE         │
│     │   (BTC, ETH, SOL positions open from previous cycles)     │
│     │                                                           │
│     ├─→ Creates EXIT tasks:                                     │
│     │   • t_exit_789: EXIT BTC - STRONG_SELL Signal             │
│     │   • t_exit_012: EXIT ETH - STRONG_SELL Signal             │
│     │   • t_exit_345: EXIT SOL - STRONG_SELL Signal             │
│     │   Assignee: trading-floor                                 │
│     │   Metadata: {position: {...}}                             │
│     │                                                           │
│     └─→ Completes silently (waits for EXIT tasks)               │
│                                                                 │
│  5. TRADING-FLOOR Executes (3 parallel tasks)                   │
│     │                                                           │
│     ├─→ t_exit_789 (BTC):                                       │
│     │   - Reads position from metadata                          │
│     │   - Executes market sell (Binance.US API)                 │
│     │   - Updates position_manager.remove_position('BTC')       │
│     │   - Completes: "🚨 EXIT BTC: Sold @ $67,220 | PnL: -1.87%"│
│     │                                                           │
│     ├─→ t_exit_012 (ETH):                                       │
│     │   - Executes market sell                                  │
│     │   - Completes: "🚨 EXIT ETH: Sold @ $3,380 | PnL: -1.17%" │
│     │                                                           │
│     └─→ t_exit_345 (SOL):                                       │
│         - Executes market sell                                  │
│         - Completes: "🚨 EXIT SOL: Sold @ $145 | PnL: -4.61%"   │
│                                                                 │
│  6. ORCHESTRATOR Summary (2-hour cycle)                         │
│     │                                                           │
│     └─→ Sends Telegram:                                         │
│         "🚨 EMERGENCY EXIT - STRONG_SELL SIGNAL                 │
│                                                                  │
│          Exited 3 positions before crash:                        │
│          - BTC: Sold @ $67,220 | PnL: -1.87% (-$0.47)           │
│          - ETH: Sold @ $3,380 | PnL: -1.17% (-$0.29)            │
│          - SOL: Sold @ $145 | PnL: -4.61% (-$0.35)              │
│                                                                  │
│          Total PnL: -$1.11 (-4.5%)                               │
│          Capital preserved: $23.89 (avoided 5-7% crash)          │
│                                                                  │
│          Reason: Whale distribution detected                     │
│          (+15,864 BTC to exchanges, -17,533 wallets)             │
│                                                                  │
│          Status: Waiting for accumulation signal to re-enter"    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Task Tree Structure

```
t_orch_123 (Orchestrator Cycle)
│
├── t_data_456 (Coin Discovery)
│   └─→ Returns: action_required = 'EXIT'
│
├── t_exit_789 (EXIT BTC)
│   Assignee: trading-floor
│   Metadata: {position: {...}}
│   └─→ kanban_complete: "🚨 EXIT BTC: Sold @ $67,220"
│
├── t_exit_012 (EXIT ETH)
│   Assignee: trading-floor
│   Metadata: {position: {...}}
│   └─→ kanban_complete: "🚨 EXIT ETH: Sold @ $3,380"
│
└── t_exit_345 (EXIT SOL)
    Assignee: trading-floor
    Metadata: {position: {...}}
    └─→ kanban_complete: "🚨 EXIT SOL: Sold @ $145"
```

**All communication via kanban_complete() → Gateway → Telegram**

---

## Position State Management

### State File Location
`/mnt/data/hermes/workspace/trading_system/state/open_positions.json`

### Structure
```json
{
  "last_updated": "2026-06-03T00:30:00Z",
  "positions": [
    {
      "symbol": "BTC",
      "side": "LONG",
      "entry_price": 68500,
      "entry_time": "2026-06-02T18:00:00Z",
      "quantity": 0.00036,
      "method": "mean_reversion",
      "stop_loss": 66445,
      "take_profit": 72610,
      "task_id": "t_entry_abc123"
    },
    {
      "symbol": "ETH",
      "side": "LONG",
      "entry_price": 3420,
      "entry_time": "2026-06-02T21:00:00Z",
      "quantity": 0.0073,
      "method": "momentum",
      "stop_loss": 3317,
      "take_profit": 3625,
      "task_id": "t_entry_def456"
    }
  ],
  "count": 2,
  "total_capital_deployed": 24.50,
  "total_unrealized_pnl": -0.76
}
```

### Operations

**Add Position (Method Bot Entry):**
```python
from position_manager import PositionManager

pm = PositionManager()
pm.add_position(
    symbol='BTC',
    side='LONG',
    entry_price=68500,
    quantity=0.00036,
    method='mean_reversion',
    stop_loss=66445,
    take_profit=72610,
    task_id='t_entry_abc123'
)
```

**Remove Position (Trading-Floor Exit):**
```python
pm.remove_position('BTC')
```

**Check for Exits (Orchestrator):**
```python
if discovery['action_required'] == 'EXIT':
    if pm.has_positions():
        # Create EXIT tasks
        for symbol in pm.get_position_symbols():
            position = pm.get_position(symbol)
            kanban_create(
                title=f"EXIT {symbol} - STRONG_SELL Signal",
                assignee='trading-floor',
                metadata={'position': position}
            )
```

---

## Trading-Floor Bot Logic

### Task: EXIT Position

**Input:**
```python
{
    'title': 'EXIT BTC - STRONG_SELL Signal',
    'assignee': 'trading-floor',
    'metadata': {
        'task_type': 'emergency_exit',
        'symbol': 'BTC',
        'reason': 'glassnode_strong_sell',
        'position': {
            'symbol': 'BTC',
            'side': 'LONG',
            'entry_price': 68500,
            'quantity': 0.00036,
            ...
        }
    }
}
```

**Execution:**
```python
def execute_exit(task):
    position = task.metadata['position']
    symbol = position['symbol']
    
    # 1. Get current price
    current_price = get_current_price(symbol)
    
    # 2. Calculate PnL
    pnl_pct = ((current_price - position['entry_price']) / position['entry_price']) * 100
    pnl_usd = pnl_pct * position['quantity'] * position['entry_price'] / 100
    
    # 3. Execute market sell
    fill_price = execute_market_sell(symbol, position['quantity'])
    
    # 4. Update state
    pm.remove_position(symbol)
    
    # 5. Report via Kanban
    kanban_complete(
        summary=f"🚨 EXIT {symbol}: Sold @ ${fill_price} | PnL: {pnl_pct:+.2f}% (${pnl_usd:+.2f}) | Reason: Whale distribution",
        output={
            'symbol': symbol,
            'action': 'SELL',
            'fill_price': fill_price,
            'entry_price': position['entry_price'],
            'pnl_pct': pnl_pct,
            'pnl_usd': pnl_usd,
            'reason': 'glassnode_strong_sell',
        }
    )
```

---

## Benefits of Kanban-Driven Approach

| Benefit | Explanation |
|---------|-------------|
| **Audit Trail** | Every exit is a Kanban task with metadata |
| **Retry Logic** | Failed exits can be retried via Kanban |
| **Parallel Execution** | Multiple EXIT tasks run in parallel |
| **Human Oversight** | Can pause/cancel EXIT tasks before execution |
| **No State Loss** | Position state persisted to JSON |
| **Clean Separation** | Orchestrator decides, Trading-Floor executes |

---

## Implementation Checklist

- [x] **Create Trading-Floor Profile**
- [x] **Write SOUL.md** (Trading-Floor responsibilities)
- [x] **Position Manager Module** (state management)
- [x] **Data Worker Update** (action_required flag)
- [ ] **Orchestrator Update** (create EXIT tasks)
- [ ] **Trading-Floor Bot Script** (execute exits)
- [ ] **Test Flow** (STRONG_SELL scenario)
- [ ] **Test Position State** (add/remove operations)
- [ ] **Test Kanban Integration** (task creation/completion)

---

## Next Steps

1. **Update Orchestrator** - Add EXIT task creation logic
2. **Build Trading-Floor Bot** - Execute market sells
3. **Integrate Position Manager** - Wire into Kanban flow
4. **Test End-to-End** - Simulate STRONG_SELL scenario
5. **Go Live** - Enable for real trading cycles

---

## Current Status

**Components Built:**
- ✅ Trading-Floor profile + SOUL.md
- ✅ Position Manager module
- ✅ Data Worker (action_required flag)

**Components Pending:**
- ⏳ Orchestrator (EXIT task creation)
- ⏳ Trading-Floor bot (execution logic)
- ⏳ Full integration test
