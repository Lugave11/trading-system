# Orchestrator → Method Bot Routing

## Core Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR (Decision Layer)                │
│                                                                 │
│  Input: Data Worker discovery (Etherscan signals + whale data) │
│                                                                 │
│  Logic:                                                         │
│  1. Read Etherscan leading indicator (LONG/SHORT bias)         │
│  2. For each coin:                                             │
│     - If LONG bias + score >= 65 → Route to LONG bots          │
│     - If SHORT bias + score <= 30 → Route to SHORT bots        │
│     - If HOLD → No action                                      │
│                                                                 │
│  Output: Kanban tasks to method-specific bots                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
        ┌─────────────────────┴─────────────────────┐
        ↓                                           ↓
┌───────────────────┐                   ┌───────────────────┐
│  LONG BOTS        │                   │  SHORT BOTS       │
│  (Bullish only)   │                   │  (Bearish only)   │
│                   │                   │                   │
│  • Momentum LONG  │                   │  • Momentum SHORT │
│  • Mean Rev LONG  │                   │  • Mean Rev SHORT │
│  • Breakout LONG  │                   │  • Breakout SHORT │
└───────────────────┘                   └───────────────────┘
        ↓                                           ↓
        └─────────────────────┬─────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    TRADING-FLOOR (Execution)                    │
│  - Receives entry tasks from method bots                       │
│  - Executes market/limit orders                                │
│  - Manages stop-loss / take-profit                             │
│  - Reports PnL                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Signal Routing Logic

### Orchestrator Decision Matrix

| Etherscan Signal | Bias | Score | Action | Route To |
|-----------------|------|-------|--------|----------|
| STRONG_BUY | LONG | ≥80 | ENTER_LONG | Long Bots |
| BUY | LONG | ≥65 | ENTER_LONG | Long Bots |
| HOLD | NEUTRAL | 45-64 | HOLD | None |
| SELL | SHORT | 30-44 | ENTER_SHORT | Short Bots |
| STRONG_SELL | BLOCK_LONG | <30 | ENTER_SHORT | Short Bots |

---

## Method Bot Profiles

### Long Bots (Bullish Strategies)

| Bot | Strategy | Entry Trigger | Exit Trigger |
|-----|----------|---------------|--------------|
| **Momentum LONG** | Trend following | RSI > 50, MACD bullish | RSI > 70 or MACD bearish cross |
| **Mean Reversion LONG** | Oversold bounce | RSI < 35, price < BB lower | RSI > 50 or price > BB middle |
| **Breakout LONG** | Resistance break | Price > resistance + volume spike | Price < breakout level |

### Short Bots (Bearish Strategies)

| Bot | Strategy | Entry Trigger | Exit Trigger |
|-----|----------|---------------|--------------|
| **Momentum SHORT** | Trend following | RSI < 50, MACD bearish | RSI < 30 or MACD bullish cross |
| **Mean Reversion SHORT** | Overbought fade | RSI > 65, price > BB upper | RSI < 50 or price < BB middle |
| **Breakout SHORT** | Support break | Price < support + volume spike | Price > breakdown level |

---

## Kanban Task Flow

### LONG Signal Flow

```
1. ORCHESTRATOR creates task:
   hermes kanban create \
     "🟢 ENTER_LONG BTC - Momentum Strategy" \
     --assignee trading-momentum-long \
     --metadata '{"direction": "LONG", "coin": "BTC", "method": "momentum", "reason": "Etherscan BUY (75/100)"}'

2. MOMENTUM-LONG bot:
   - Validates LONG setup (RSI, MACD, volume)
   - Calculates entry price, position size
   - Creates execution task

3. TRADING-FLOOR executes:
   - Buys BTC @ market/limit
   - Sets stop-loss, take-profit
   - Reports PnL
```

### SHORT Signal Flow

```
1. ORCHESTRATOR creates task:
   hermes kanban create \
     "🔴 ENTER_SHORT ETH - Mean Reversion Strategy" \
     --assignee trading-mean-reversion-short \
     --metadata '{"direction": "SHORT", "coin": "ETH", "method": "mean_reversion", "reason": "Etherscan SELL (35/100)"}'

2. MEAN-REVERSION-SHORT bot:
   - Validates SHORT setup (RSI > 65, price > BB upper)
   - Calculates entry price, position size
   - Creates execution task

3. TRADING-FLOOR executes:
   - Sells ETH @ market/limit (or opens short position)
   - Sets stop-loss, take-profit
   - Reports PnL
```

---

## Profile Structure

### Current Profiles (from Kanban board)

| Profile | Purpose | Tasks |
|---------|---------|-------|
| `trading-data` | Discovery & analysis | Data Worker, Whale Tracking |
| `trading-orchestrator` | Decision making | LONG/SHORT routing |
| `trading-floor` | Execution | Market orders, PnL reporting |
| `trading-momentum` | Momentum strategy | LONG + SHORT (needs split) |

### Recommended New Profiles

| Profile | Purpose | Direction |
|---------|---------|-----------|
| `trading-momentum-long` | Momentum LONG entries | LONG only |
| `trading-momentum-short` | Momentum SHORT entries | SHORT only |
| `trading-mean-reversion-long` | Mean reversion LONG | LONG only |
| `trading-mean-reversion-short` | Mean reversion SHORT | SHORT only |
| `trading-breakout-long` | Breakout LONG | LONG only |
| `trading-breakout-short` | Breakout SHORT | SHORT only |

**Why Split?**
- Clear separation of concerns
- LONG bots only look for bullish setups
- SHORT bots only look for bearish setups
- Easier debugging and performance tracking
- Can enable/disable LONG or SHORT trading globally

---

## Orchestrator Logic (Code)

```python
def orchestrator_routing(data_worker_result: Dict) -> List[Dict]:
    """
    Route signals to appropriate method bots based on direction.
    """
    tasks_to_create = []
    
    for coin, analysis in data_worker_result['coins'].items():
        etherscan_signal = analysis.get('glassnode_signal', 'HOLD')
        score = analysis.get('discovery_score', 50)
        
        # Determine direction
        if etherscan_signal in ['STRONG_BUY', 'BUY'] and score >= 65:
            direction = 'LONG'
            methods = ['momentum', 'mean_reversion']  # Try multiple methods
        elif etherscan_signal in ['SELL', 'STRONG_SELL'] and score <= 40:
            direction = 'SHORT'
            methods = ['momentum', 'mean_reversion']
        else:
            continue  # HOLD - no action
        
        # Create task for each method
        for method in methods:
            task = {
                'title': f"{'🟢' if direction == 'LONG' else '🔴'} {direction} {coin} - {method.title()} Strategy",
                'assignee': f'trading-{method}-{direction.lower()}',
                'metadata': {
                    'direction': direction,
                    'coin': coin,
                    'method': method,
                    'reason': f"Etherscan {etherscan_signal} ({score}/100)",
                    'etherscan_score': score,
                    'etherscan_signal': etherscan_signal,
                }
            }
            tasks_to_create.append(task)
    
    return tasks_to_create
```

---

## Example Task Chain

### LONG Example (BTC Bullish)

```
t_abc123  🔍 Data Discovery - Etherscan Analysis
├─ Result: "BTC: BUY (75/100), LONG bias"
│
└── t_def456  🎯 Orchestrator - Route LONG Signals
    ├─ Result: "Routed BTC to LONG bots"
    │
    ├── t_ghi789  🟢 ENTER_LONG BTC - Momentum Strategy
    │   ├─ Assignee: trading-momentum-long
    │   ├─ Validates: RSI 55, MACD bullish, volume +20%
    │   ├─ Creates: t_jkl012 (execution)
    │   └─ Result: "Momentum LONG validated, entry @ $67,500"
    │
    ├── t_mno345  🟢 ENTER_LONG BTC - Mean Reversion Strategy
    │   ├─ Assignee: trading-mean-reversion-long
    │   ├─ Validates: RSI 42 (neutral, not oversold)
    │   └─ Result: "No entry - RSI not < 35" (SKIPPED)
    │
    └── t_jkl012  🚨 EXECUTE LONG BTC - Momentum
        ├─ Assignee: trading-floor
        ├─ Buys: 0.015 BTC @ $67,500
        ├─ Stop: $65,500 (-3%)
        ├─ Target: $71,500 (+6%)
        └─ Result: "Position opened, PnL: $0.00"
```

### SHORT Example (ETH Bearish)

```
t_pqr678  🔍 Data Discovery - Etherscan Analysis
├─ Result: "ETH: SELL (35/100), SHORT bias"
│
└── t_stu901  🎯 Orchestrator - Route SHORT Signals
    ├─ Result: "Routed ETH to SHORT bots"
    │
    ├── t_vwx234  🔴 ENTER_SHORT ETH - Momentum Strategy
    │   ├─ Assignee: trading-momentum-short
    │   ├─ Validates: RSI 45, MACD bearish, volume +15%
    │   ├─ Creates: t_yza567 (execution)
    │   └─ Result: "Momentum SHORT validated, entry @ $1,840"
    │
    ├── t_bcd890  🔴 ENTER_SHORT ETH - Mean Reversion Strategy
    │   ├─ Assignee: trading-mean-reversion-short
    │   ├─ Validates: RSI 68 (overbought), price > BB upper
    │   ├─ Creates: t_efg123 (execution)
    │   └─ Result: "Mean reversion SHORT validated, entry @ $1,842"
    │
    ├── t_yza567  🚨 EXECUTE SHORT ETH - Momentum
    │   ├─ Assignee: trading-floor
    │   ├─ Opens short: 0.05 ETH @ $1,840
    │   ├─ Stop: $1,900 (+3%)
    │   ├─ Target: $1,750 (-5%)
    │   └─ Result: "Short position opened"
    │
    └── t_efg123  🚨 EXECUTE SHORT ETH - Mean Reversion
        ├─ Assignee: trading-floor
        ├─ Opens short: 0.05 ETH @ $1,842
        ├─ Stop: $1,900 (+3%)
        ├─ Target: $1,750 (-5%)
        └─ Result: "Short position opened"
```

---

## Current State vs Target State

### Current (What We Have)

```
Orchestrator → trading-momentum (mixed LONG/SHORT)
            → trading-floor (execution)
```

**Issues:**
- Momentum bot handles both LONG and SHORT (confusing)
- No clear separation of bullish vs bearish strategies
- Hard to track LONG vs SHORT performance separately

### Target (What We Want)

```
Orchestrator → trading-momentum-long (LONG only)
            → trading-momentum-short (SHORT only)
            → trading-mean-reversion-long (LONG only)
            → trading-mean-reversion-short (SHORT only)
            → trading-floor (execution)
```

**Benefits:**
- Clear direction separation
- LONG bots only look for bullish setups
- SHORT bots only look for bearish setups
- Easy to disable all SHORT trading (or LONG) globally
- Better performance tracking per direction

---

## Implementation Steps

### 1. Create New Profiles
```bash
# Create profiles in Kanban config
trading-momentum-long
trading-momentum-short
trading-mean-reversion-long
trading-mean-reversion-short
```

### 2. Update Orchestrator Logic
- Route LONG signals to `*-long` profiles
- Route SHORT signals to `*-short` profiles

### 3. Split Method Bots
- `momentum_bot.py` → `momentum_long.py` + `momentum_short.py`
- `mean_reversion_bot.py` → `mean_reversion_long.py` + `mean_reversion_short.py`

### 4. Update Kanban Task Creation
```python
# OLD (mixed)
assignee = 'trading-momentum'

# NEW (direction-specific)
assignee = f'trading-{method}-{direction.lower()}'
# e.g., 'trading-momentum-long' or 'trading-momentum-short'
```

### 5. Test with Real Signals
- Create LONG task when Etherscan BUY
- Create SHORT task when Etherscan SELL
- Verify routing to correct profiles

---

## Summary

| Component | Current | Target |
|-----------|---------|--------|
| **Orchestrator** | Creates generic tasks | Routes LONG/SHORT to specific bots |
| **Momentum Bot** | Mixed LONG/SHORT | Split: `momentum-long`, `momentum-short` |
| **Mean Reversion** | Mixed LONG/SHORT | Split: `mean-reversion-long`, `mean-reversion-short` |
| **Profiles** | 4 (data, orchestrator, momentum, floor) | 8+ (direction-specific) |
| **Routing** | Manual/implicit | Automatic based on Etherscan bias |

**Next:** Do you want me to implement this architecture (split bots, update orchestrator routing, create new profiles)?
