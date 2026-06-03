# Coin Universe Management - Kanban-Driven

## Overview

**Coin universe is DYNAMIC** - not hardcoded. Managed by Orchestrator via Kanban tasks.

**Config File:** `state/coin_universe.json`

---

## How It Works

### 1. Initial Setup (Done)

```json
{
  "coins": ["BTC", "ETH", "SOL", "BNB", "XRP", ...],
  "updated_at": "2026-06-03T00:00:00Z",
  "updated_by": "initial_setup"
}
```

### 2. Rebalance Trigger (Orchestrator Decision)

**When Orchestrator detects:**
- New high-opportunity coins (volume + volatility spike)
- Existing coins dying (volume < threshold, delisting risk)
- Glassnode coverage changes
- Market regime shift (rotate to different sectors)

**Action:** Create Kanban task to update coin universe

---

## Kanban Task: Update Coin Universe

### Task Creation (Orchestrator)

```python
kanban_create(
    title="🔄 REBALANCE: Update Coin Universe",
    description="""
    Coin Universe Rebalance Proposal
    
    Current Universe: 15 coins
    Proposed Changes:
    - ADD: [NEW_COIN] (reason: volume spike, Glassnode coverage)
    - REMOVE: [DYING_COIN] (reason: volume < $1M, delisting risk)
    
    New Universe: [list of coins]
    
    Execute: Update state/coin_universe.json
    """,
    assignee='trading-orchestrator',
    metadata={
        'task_type': 'coin_universe_rebalance',
        'current_coins': [...],
        'proposed_coins': [...],
        'reason': '...',
    }
)
```

### Task Execution (Orchestrator)

```python
def execute_coin_universe_rebalance(task):
    """
    Update coin_universe.json with new coin list.
    """
    proposed_coins = task.metadata['proposed_coins']
    
    # Write new config
    config = {
        'coins': proposed_coins,
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'updated_by': task['id'],
        'reason': task.metadata['reason'],
    }
    
    with open('state/coin_universe.json', 'w') as f:
        json.dump(config, f, indent=2)
    
    kanban_complete(
        summary=f"✅ Coin universe updated: {len(proposed_coins)} coins",
        output={
            'coins': proposed_coins,
            'count': len(proposed_coins),
            'changes': task.metadata['reason'],
        }
    )
```

---

## Data Worker Integration

### Loading Coin Universe (Dynamic)

```python
# data_worker_discovery.py

from glassnode_bulk_fetch import fetch_glassnode_bulk, load_coin_universe

def scan_all_candidates():
    # 1. Load coin universe from config (NOT hardcoded)
    coins = load_coin_universe()
    
    if not coins:
        print("⚠ No coins configured - using defaults")
        coins = ['BTC', 'ETH', 'SOL']
    
    # 2. Fetch Glassnode for ALL coins in universe
    glassnode_data = fetch_glassnode_bulk(coins)
    
    # 3. Process each coin
    for symbol in coins:
        signal = glassnode_data.get(symbol, get_default_signal())
        # ... rest of logic ...
```

**Result:** Data Worker automatically adapts to coin universe changes.

---

## Example Rebalance Scenarios

### Scenario 1: Add High-Opportunity Coin

**Trigger:** PEPE volume spike ($50M → $500M), Glassnode adds coverage

**Orchestrator Decision:**
```
Current: 15 coins
Proposed: Add PEPE (reason: volume + Glassnode coverage)
New: 16 coins
```

**Kanban Task:**
```
Title: 🔄 REBALANCE: Add PEPE to Coin Universe
Assignee: trading-orchestrator
Metadata:
  - current_coins: [BTC, ETH, ...]
  - proposed_coins: [BTC, ETH, ..., PEPE]
  - reason: "Volume spike $50M→$500M, Glassnode coverage added"
```

**Execution:**
```json
{
  "coins": ["BTC", "ETH", ..., "PEPE"],
  "updated_at": "2026-06-15T12:00:00Z",
  "updated_by": "t_abc123",
  "reason": "Volume spike + Glassnode coverage"
}
```

---

### Scenario 2: Remove Dying Coin

**Trigger:** LUNA volume < $1M/day for 30 days, delisting risk

**Orchestrator Decision:**
```
Current: 16 coins
Proposed: Remove LUNA (reason: volume < $1M, delisting risk)
New: 15 coins
```

**Kanban Task:**
```
Title: 🔄 REBALANCE: Remove LUNA from Coin Universe
Assignee: trading-orchestrator
Metadata:
  - current_coins: [BTC, ETH, ..., LUNA, ...]
  - proposed_coins: [BTC, ETH, ...] (no LUNA)
  - reason: "Volume < $1M for 30 days, delisting risk"
```

---

### Scenario 3: Sector Rotation

**Trigger:** DeFi season detected (UNI, AAVE, COMP volume surge)

**Orchestrator Decision:**
```
Current: 15 coins (heavy on legacy: LTC, BCH, XRP)
Proposed: Remove LTC, BCH, XRP; Add AAVE, COMP, MKR
New: 15 coins (rotated to DeFi)
```

**Kanban Task:**
```
Title: 🔄 REBALANCE: Rotate to DeFi Sector
Assignee: trading-orchestrator
Metadata:
  - current_coins: [BTC, ETH, ..., LTC, BCH, XRP]
  - proposed_coins: [BTC, ETH, ..., AAVE, COMP, MKR]
  - reason: "DeFi season detected - rotate from legacy to DeFi"
```

---

## Governance Rules

### Who Can Change Coin Universe?

**Orchestrator** (via Kanban tasks) - autonomous decisions based on:
- Volume thresholds (> $10M/day)
- Volatility (2-10% daily)
- Glassnode coverage (must have on-chain data)
- Risk metrics (no delisting risk, no rug pulls)

### Change Frequency

- **Normal:** Once per week (weekly rebalance)
- **Volatile:** As needed (market regime shifts)
- **Emergency:** Immediate (delisting, exploit, rug pull)

### Validation Rules

```python
def validate_coin_universe(coins: List[str]) -> bool:
    """
    Validate proposed coin universe.
    """
    # Must have at least 3 coins
    if len(coins) < 3:
        return False
    
    # Must have BTC + ETH (core holdings)
    if 'BTC' not in coins or 'ETH' not in coins:
        return False
    
    # Max 30 coins (manageable universe)
    if len(coins) > 30:
        return False
    
    # All coins must have Glassnode coverage
    for coin in coins:
        if not has_glassnode_coverage(coin):
            return False
    
    return True
```

---

## Files

| File | Purpose |
|------|---------|
| `state/coin_universe.json` | Dynamic coin config (managed by Orchestrator) |
| `glassnode_bulk_fetch.py::load_coin_universe()` | Load coins from config |
| `glassnode_bulk_fetch.py::fetch_glassnode_bulk()` | Fetch for dynamic coin list |
| `COIN_UNIVERSE_MANAGEMENT.md` | This doc |

---

## Benefits

| Benefit | Explanation |
|---------|-------------|
| **Dynamic** | Coins change based on market conditions |
| **Kanban-Driven** | All changes tracked via tasks |
| **No Hardcoding** | Coin list in config, not code |
| **Auditable** | Every change has task ID + reason |
| **Autonomous** | Orchestrator decides when to rebalance |
| **Flexible** | Add/remove coins without code changes |

---

**Coin universe is now 100% dynamic and Kanban-managed.**
