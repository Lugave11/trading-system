# Coin Universe Logic - Complete Documentation

## Overview

**Coin universe is 100% DYNAMIC** - no hardcoding anywhere.

Managed by Orchestrator via Kanban tasks, stored in `state/coin_universe.json`.

---

## File Structure

```
trading_system/
├── state/
│   └── coin_universe.json      # Dynamic config (managed by Orchestrator)
├── glassnode_bulk_fetch.py     # Load logic
├── data_worker_discovery.py    # Uses loaded coins
└── COIN_UNIVERSE_LOGIC.md      # This doc
```

---

## 1. Configuration File

**File:** `state/coin_universe.json`

```json
{
  "coins": [
    "BTC", "ETH", "SOL", "BNB", "XRP",
    "ADA", "AVAX", "MATIC", "DOT", "LINK",
    "UNI", "ATOM", "DOGE", "LTC", "BCH"
  ],
  "updated_at": "2026-06-03T00:00:00Z",
  "updated_by": "initial_setup",
  "metadata": {
    "description": "Dynamic coin universe - managed by Orchestrator via Kanban tasks",
    "glassnode_coverage": "100% (all coins have on-chain data)",
    "rebalance_frequency": "As needed (Orchestrator decision)"
  }
}
```

### Fields

| Field | Type | Purpose |
|-------|------|---------|
| `coins` | `string[]` | List of coin symbols to track |
| `updated_at` | `ISO8601` | Last modification timestamp |
| `updated_by` | `string` | Task ID or user who updated |
| `metadata.description` | `string` | Human-readable description |
| `metadata.glassnode_coverage` | `string` | Coverage status |
| `metadata.rebalance_frequency` | `string` | How often to rebalance |

---

## 2. Load Logic

**File:** `glassnode_bulk_fetch.py`

### Function: `load_coin_universe()`

```python
def load_coin_universe() -> List[str]:
    """
    Load coin universe from dynamic config file.
    
    This file is managed by the Orchestrator via Kanban tasks.
    Path: state/coin_universe.json
    
    Returns:
        List of coin symbols, or empty list if file doesn't exist
    """
    config_path = Path(__file__).parent / 'state' / 'coin_universe.json'
    
    if not config_path.exists():
        print(f"   ⚠ Coin universe config not found: {config_path}")
        return []
    
    try:
        import json
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        coins = config.get('coins', [])
        updated = config.get('updated_at', 'unknown')
        
        print(f"   📋 Loaded coin universe: {len(coins)} coins (updated: {updated})")
        
        return coins
    
    except Exception as e:
        print(f"   ❌ Error loading coin universe: {e}")
        return []
```

### How It Works

1. **Path Resolution:**
   ```python
   config_path = Path(__file__).parent / 'state' / 'coin_universe.json'
   ```
   - Resolves to: `/mnt/data/hermes/workspace/trading_system/state/coin_universe.json`

2. **File Check:**
   ```python
   if not config_path.exists():
       return []  # Empty list if missing
   ```

3. **JSON Parse:**
   ```python
   with open(config_path, 'r') as f:
       config = json.load(f)
   
   coins = config.get('coins', [])
   ```

4. **Logging:**
   ```python
   print(f"   📋 Loaded coin universe: {len(coins)} coins (updated: {updated})")
   ```

5. **Return:**
   ```python
   return coins  # List of strings: ['BTC', 'ETH', ...]
   ```

---

## 3. Usage in Data Worker

**File:** `data_worker_discovery.py`

```python
from glassnode_bulk_fetch import load_coin_universe, fetch_glassnode_bulk

def scan_all_candidates():
    # Step 1: Load coin universe (DYNAMIC, NOT HARDCODED)
    coins = load_coin_universe()
    
    if not coins:
        print("⚠ No coins configured - using defaults")
        coins = ['BTC', 'ETH', 'SOL']
    
    # Step 2: Fetch Glassnode for ALL coins in universe
    glassnode_data = fetch_glassnode_bulk(coins)
    
    # Step 3: Process each coin
    for symbol in coins:
        signal = glassnode_data.get(symbol, get_default_signal())
        
        # Build discovery report
        coin_data = {
            'symbol': symbol,
            'glassnode_signal': signal,
            'action_required': signal.get('action', 'HOLD'),
        }
    
    return {
        'discovered_coins': discovered_coins,
        'summary': {
            'coins_to_exit': [...],
            'coins_to_enter': [...],
            'coins_to_hold': [...],
        }
    }
```

### Key Points

1. **No Hardcoding:**
   ```python
   coins = load_coin_universe()  # ← Dynamic load
   # NOT: coins = ['BTC', 'ETH', 'SOL', ...]  ← Hardcoded
   ```

2. **Fallback Safety:**
   ```python
   if not coins:
       coins = ['BTC', 'ETH', 'SOL']  # Minimal fallback
   ```

3. **Automatic Adaptation:**
   - When Orchestrator updates `coin_universe.json`, next cycle automatically uses new coins
   - No code changes, no restart needed

---

## 4. Orchestrator Rebalance Logic

**How Orchestrator Updates Coin Universe**

### Trigger Conditions

Orchestrator creates rebalance task when:

1. **New High-Opportunity Coin:**
   - Volume spike > 300%
   - Glassnode adds coverage
   - Volatility in target range (2-10%)

2. **Dying Coin:**
   - Volume < $1M/day for 30 days
   - Delisting risk
   - Glassnode removes coverage

3. **Sector Rotation:**
   - Market regime shift (e.g., DeFi season)
   - Rotate from weak sectors to strong sectors

### Kanban Task Creation

```python
kanban_create(
    title="🔄 REBALANCE: Add PEPE to Coin Universe",
    assignee='trading-orchestrator',
    body="""
    **Current Universe:** 15 coins
    **Proposed Change:** Add PEPE
    **Reason:** Volume spike $50M→$500M, Glassnode coverage added
    
    **New Universe:**
    BTC, ETH, SOL, BNB, XRP, ADA, AVAX, MATIC, DOT, LINK, UNI, ATOM, DOGE, LTC, BCH, PEPE
    """,
    metadata={
        'task_type': 'coin_universe_rebalance',
        'current_coins': ['BTC', 'ETH', ...],  # 15 coins
        'proposed_coins': ['BTC', 'ETH', ..., 'PEPE'],  # 16 coins
        'reason': 'Volume spike + Glassnode coverage',
    }
)
```

### Execution Logic

```python
def execute_rebalance(task):
    """
    Update coin_universe.json with new coin list.
    """
    proposed_coins = task.metadata['proposed_coins']
    
    # Validate
    if not validate_coin_universe(proposed_coins):
        raise ValueError("Invalid coin universe")
    
    # Build new config
    config = {
        'coins': proposed_coins,
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'updated_by': task['id'],  # Task ID for audit trail
        'reason': task.metadata['reason'],
        'metadata': {
            'description': 'Dynamic coin universe - managed by Orchestrator',
            'glassnode_coverage': '100%',
            'rebalance_frequency': 'As needed',
        }
    }
    
    # Write to file
    config_path = Path(__file__).parent / 'state' / 'coin_universe.json'
    
    with open(config_path, 'w') as f:
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

## 5. Validation Rules

```python
def validate_coin_universe(coins: List[str]) -> bool:
    """
    Validate proposed coin universe.
    """
    # Rule 1: Must have at least 3 coins
    if len(coins) < 3:
        print("❌ Validation failed: Less than 3 coins")
        return False
    
    # Rule 2: Must have BTC + ETH (core holdings)
    if 'BTC' not in coins or 'ETH' not in coins:
        print("❌ Validation failed: Missing BTC or ETH")
        return False
    
    # Rule 3: Max 30 coins (manageable universe)
    if len(coins) > 30:
        print("❌ Validation failed: More than 30 coins")
        return False
    
    # Rule 4: All coins must have Glassnode coverage
    for coin in coins:
        if not has_glassnode_coverage(coin):
            print(f"❌ Validation failed: {coin} has no Glassnode coverage")
            return False
    
    # Rule 5: No duplicates
    if len(coins) != len(set(coins)):
        print("❌ Validation failed: Duplicate coins")
        return False
    
    print("✅ Validation passed")
    return True
```

---

## 6. Example Scenarios

### Scenario 1: Add PEPE (Volume Spike)

**Before:**
```json
{
  "coins": ["BTC", "ETH", "SOL", ..., "BCH"],  // 15 coins
  "updated_at": "2026-06-03T00:00:00Z"
}
```

**Trigger:** PEPE volume spikes from $50M → $500M, Glassnode adds coverage

**Orchestrator Decision:**
```
Current: 15 coins
Proposed: Add PEPE
New: 16 coins
```

**After:**
```json
{
  "coins": ["BTC", "ETH", "SOL", ..., "BCH", "PEPE"],  // 16 coins
  "updated_at": "2026-06-15T12:00:00Z",
  "updated_by": "t_abc123",
  "reason": "PEPE volume spike $50M→$500M, Glassnode coverage added"
}
```

---

### Scenario 2: Remove LUNA (Delisting Risk)

**Before:**
```json
{
  "coins": ["BTC", "ETH", ..., "LUNA", ...],  // 16 coins
  "updated_at": "2026-06-15T12:00:00Z"
}
```

**Trigger:** LUNA volume < $1M/day for 30 days, delisting risk

**Orchestrator Decision:**
```
Current: 16 coins
Proposed: Remove LUNA
New: 15 coins
```

**After:**
```json
{
  "coins": ["BTC", "ETH", ..., "BCH", "PEPE"],  // 15 coins (no LUNA)
  "updated_at": "2026-06-20T08:00:00Z",
  "updated_by": "t_def456",
  "reason": "LUNA volume < $1M for 30 days, delisting risk"
}
```

---

### Scenario 3: Sector Rotation (DeFi Season)

**Before:**
```json
{
  "coins": ["BTC", "ETH", "SOL", "LTC", "BCH", "XRP", ...],  // Legacy-heavy
  "updated_at": "2026-06-01T00:00:00Z"
}
```

**Trigger:** DeFi season detected (UNI, AAVE, COMP volume surge)

**Orchestrator Decision:**
```
Current: 15 coins (heavy on legacy: LTC, BCH, XRP)
Proposed: Remove LTC, BCH, XRP; Add AAVE, COMP, MKR
New: 15 coins (rotated to DeFi)
```

**After:**
```json
{
  "coins": ["BTC", "ETH", "SOL", "AAVE", "COMP", "MKR", ...],  // DeFi-heavy
  "updated_at": "2026-07-01T00:00:00Z",
  "updated_by": "t_ghi789",
  "reason": "DeFi season detected - rotate from legacy to DeFi"
}
```

---

## 7. Audit Trail

Every change is tracked:

| Field | Purpose | Example |
|-------|---------|---------|
| `updated_at` | When | `2026-06-15T12:00:00Z` |
| `updated_by` | Who (Task ID) | `t_abc123` |
| `reason` | Why | `"PEPE volume spike + Glassnode coverage"` |

**View History:**
```bash
# Check Git history (if version controlled)
git log -- state/coin_universe.json

# Or check Kanban task history
hermes kanban list | grep "REBALANCE"
```

---

## 8. Benefits

| Benefit | Old (Hardcoded) | New (Dynamic) |
|---------|-----------------|---------------|
| **Coin Changes** | Edit code + restart | Update JSON file |
| **Tracking** | Git commit history | Kanban task + JSON metadata |
| **Flexibility** | Low (code changes) | High (config changes) |
| **Audit Trail** | Code commits | Task ID + timestamp + reason |
| **Autonomy** | Manual edits | Orchestrator decides via Kanban |
| **Safety** | None | Validation rules |
| **Adaptation** | Restart required | Automatic (next cycle) |

---

## 9. Files Reference

| File | Purpose | Lines |
|------|---------|-------|
| `state/coin_universe.json` | Dynamic config | 26 |
| `glassnode_bulk_fetch.py::load_coin_universe()` | Load logic | 38 |
| `glassnode_bulk_fetch.py::fetch_glassnode_bulk()` | Bulk fetch | ~100 |
| `COIN_UNIVERSE_LOGIC.md` | This doc | - |
| `COIN_UNIVERSE_MANAGEMENT.md` | Management guide | - |

---

## 10. Quick Reference

### Load Coins (Python)
```python
from glassnode_bulk_fetch import load_coin_universe

coins = load_coin_universe()
print(f"Loaded {len(coins)} coins: {coins}")
```

### Fetch Glassnode
```python
from glassnode_bulk_fetch import fetch_glassnode_bulk

coins = load_coin_universe()
data = fetch_glassnode_bulk(coins)

for symbol, signal in data.items():
    print(f"{symbol}: {signal['signal']} ({signal['score']:.1f}/100)")
```

### Update via Kanban
```bash
# Create rebalance task
hermes kanban create "🔄 REBALANCE: Add PEPE" \
  --assignee trading-orchestrator \
  --body "Add PEPE to coin universe (volume spike)"

# Execute (in Orchestrator profile)
# Updates state/coin_universe.json automatically
```

---

**Coin universe is 100% dynamic, Kanban-managed, zero hardcoding.**
