# Coin Swap Mechanism - Kanban System

## Problem Statement

**Current Issue:** Coins are hardcoded in Data Worker tasks (`BTC/ETH/SOL`), preventing dynamic selection based on market conditions.

**Solution:** Orchestrator discovers and selects coins every 15 minutes → Assigns to Data Worker → Data Worker collects → Orchestrator evaluates.

---

## Correct Flow (Step-by-Step)

### Step 1: Orchestrator Wakes Up (Every 15 Min)

**Trigger:** Cron job creates Kanban task for `trading-orchestrator`

```markdown
**Task:** Orchestrator Cycle - Coin Discovery & Routing
**Assignee:** trading-orchestrator
**Body:**
1. Scan market and discover coins (see discover_coins() function)
2. Rank by opportunity score (volume + volatility + whale activity)
3. Select top 3-5 coins (score >= 50)
4. Create Data Worker child task with assigned coins
5. Wait for Data Worker completion
6. Evaluate collected data
7. Route to method bots
```

**Python Logic:**
```python
def run_orchestrator():
    # STEP 1: Discover coins
    discovered = discover_coins()  # Scans 15 candidates
    selected = discovered[:5]      # Top 5 by score
    selected_symbols = [c['symbol'] for c in selected]
    
    print(f"Discovered: {[c['symbol'] for c in discovered]}")
    print(f"Selected: {selected_symbols}")
    
    # STEP 2: Create Data Worker task with assigned coins
    from kanban import kanban_create
    
    data_task = kanban_create(
        title=f'Data Collection - {", ".join(selected_symbols)}',
        description=f'''
        COLLECT MARKET DATA FOR ASSIGNED COINS
        
        Assigned by Orchestrator (dynamic selection):
        {chr(10).join(f"- {coin['symbol']}: Score {coin['total_score']:.1f}" for coin in selected)}
        
        Selection Reason:
        - Average volatility: {sum(c['volatility_pct'] for c in selected)/len(selected):.1f}%
        - Average whale score: {sum(c['whale_score'] for c in selected)/len(selected):.0f}
        
        Collect 5m OHLCV, RSI, MACD, EMAs, whale scores, news.
        Store in shared_state.json.
        Complete silently.
        ''',
        assignee='trading-data',
        metadata={
            'assigned_coins': selected_symbols,
            'discovery_scores': selected,
        }
    )
    
    # STEP 3: Wait for Data Worker to complete
    # (In Kanban system, this happens via task lifecycle)
    wait_for_task_completion(data_task['id'])
    
    # STEP 4: Read collected data
    state = read_shared_state()
    coin_data_list = state.get('coin_data', [])
    
    # STEP 5: Evaluate and route
    for coin_data in coin_data_list:
        symbol = coin_data['symbol']
        # ... calculate scores, create method bot tasks
```

---

### Step 2: Data Worker Collects (Assigned Coins Only)

**Trigger:** Child task created by Orchestrator

**Key Change:** Data Worker does NOT select coins — it collects data for **assigned coins only**.

```python
def run_data_worker():
    # Read assigned coins from parent task or metadata
    assigned_coins = get_assigned_coins_from_parent_task()
    
    # Fallback if no assignment (shouldn't happen in production)
    if not assigned_coins:
        assigned_coins = ['BTC', 'ETH', 'SOL']  # Emergency fallback
        print("⚠ No coins assigned - using fallback")
    
    print(f"Collecting data for: {', '.join(assigned_coins)}")
    
    # Collect data ONLY for assigned coins
    coin_data_list = []
    for symbol in assigned_coins:
        data = collect_coin_data(symbol)
        coin_data_list.append(data)
    
    # Store in shared state
    save_to_shared_state({
        'assigned_coins': assigned_coins,
        'coin_data': coin_data_list,
    })
    
    # Complete silently
    kanban_complete(output={...}, silent=True)
```

**Output:**
```json
{
  "assigned_coins": ["BTC", "XRP", "SOL"],  // From Orchestrator
  "coin_data": [
    {"symbol": "BTC", "price": 67703, "rsi": 57.4, ...},
    {"symbol": "XRP", "price": 2.15, "rsi": 32.1, ...},
    {"symbol": "SOL", "price": 145.2, "rsi": 68.5, ...}
  ]
}
```

---

### Step 3: Orchestrator Evaluates & Routes

**Same task, continues after Data Worker completes:**

```python
# Read collected data (from Step 2)
state = read_shared_state()
coin_data_list = state.get('coin_data', [])

# Evaluate each coin
decisions = []
for coin_data in coin_data_list:
    symbol = coin_data['symbol']
    indicators = coin_data['ohlcv']['indicators']
    
    # Calculate method scores
    mr_score = calc_mean_reversion(indicators)
    momentum_score = calc_momentum(indicators)
    breakout_score = calc_breakout(indicators)
    
    # Find best method
    best_method = max(mr_score, momentum_score, breakout_score)
    
    # Create method bot task if score >= 60
    if best_method >= 60:
        method_task = kanban_create(
            title=f'{symbol} {best_method} - Score {best_method:.0f}',
            assignee=f'trading-{best_method}',
            metadata={'symbol': symbol, 'method': best_method}
        )
        decisions.append({'symbol': symbol, 'action': 'BUY', ...})
    else:
        decisions.append({'symbol': symbol, 'action': 'HOLD', ...})

# Complete silently (15-min cycle)
kanban_complete(output={'decisions': decisions}, silent=True)
```

---

### Step 4: Method Bots Execute (On Signal)

**Trigger:** Child task created by Orchestrator

```python
# Method Bot (Mean Reversion example)
def execute_mean_reversion():
    # Read coin data from shared state
    symbol = task.metadata['symbol']
    coin_data = get_coin_data(symbol)
    
    # Execute trade
    entry = coin_data['ohlcv']['indicators']['current_price']
    stop_loss = entry * 0.97
    take_profit = entry * 1.06
    
    # Complete with Gateway message
    kanban_complete(
        output={'entry': entry, 'stop': stop_loss, 'target': take_profit},
        summary=f'🎯 {symbol} BUY - Entry ${entry}, Stop ${stop_loss}, Target ${take_profit}'
    )
```

---

## Coin Swap Timeline

```
Time    Event                              Coins Selected
─────────────────────────────────────────────────────────
15:00   Orchestrator wakes up              Scans 15 candidates
        → Discovers: BTC(60), XRP(52),     Selected: BTC, XRP, SOL
           SOL(51), ETH(48), DOGE(45)
        → Creates Data Worker task
           "Collect: BTC, XRP, SOL"
        
15:02   Data Worker completes              Data stored for:
        → Collects OHLCV for BTC, XRP, SOL BTC, XRP, SOL only
        
15:03   Orchestrator evaluates             Decisions:
        → BTC: HOLD (RSI 57, no setup)     BTC: HOLD
        → XRP: BUY (RSI 32, MR score 68)   XRP: BUY (Mean Rev)
        → SOL: HOLD (RSI 68, no setup)     SOL: HOLD
        → Creates XRP Mean Reversion task
        
15:05   Method Bot executes                XRP LONG opened
        → Opens XRP position               Entry: $2.15
                                           Stop: $2.08
                                           Target: $2.28
        
─────────────────────────────────────────────────────────
15:15   Orchestrator wakes up (new cycle)  Scans 15 candidates
        → Discovers: SOL(72), DOGE(65),    Selected: SOL, DOGE, ETH
           ETH(58), BTC(45), XRP(42)       (XRP dropped - already ran)
        → Creates Data Worker task
           "Collect: SOL, DOGE, ETH"
        
15:17   Data Worker completes              Data stored for:
        → Collects OHLCV for SOL, DOGE, ETH SOL, DOGE, ETH only
        
15:18   Orchestrator evaluates             Decisions:
        → SOL: BUY (RSI 25, MR score 72)   SOL: BUY (Mean Rev)
        → DOGE: BUY (breakout, score 68)   DOGE: BUY (Breakout)
        → ETH: HOLD (no setup)             ETH: HOLD
```

**Key Points:**
- **Coin list changes every 15 minutes** based on market conditions
- **Data Worker only collects for assigned coins** (no hardcoded lists)
- **Orchestrator controls the swap** (discovers → assigns → evaluates)
- **Previous coins can drop off** if score falls below threshold

---

## Implementation Checklist

### Orchestrator Changes
- [ ] Add `discover_coins()` function (scan 15 candidates, rank by score)
- [ ] Add coin selection logic (top 5 with score >= 50)
- [ ] Create Data Worker task with `assigned_coins` in metadata
- [ ] Wait for Data Worker completion (task lifecycle)
- [ ] Read `assigned_coins` from shared state (not hardcoded)
- [ ] Evaluate only assigned coins

### Data Worker Changes
- [ ] Remove coin discovery logic (moved to Orchestrator)
- [ ] Read `assigned_coins` from parent task metadata
- [ ] Collect data ONLY for assigned coins
- [ ] Fallback to BTC/ETH/SOL if no assignment (emergency only)
- [ ] Store `assigned_coins` in shared state (for audit trail)

### Kanban Task Templates
- [ ] Update Orchestrator template: "Discover coins, assign to Data Worker"
- [ ] Update Data Worker template: "Collect for assigned coins only"
- [ ] Add metadata field: `assigned_coins: [...]`
- [ ] Remove hardcoded coin lists from all templates

### Cron Jobs
- [ ] Orchestrator cron: Creates task every 15 min (discovers coins)
- [ ] Data Worker cron: **REMOVE** (no longer needed - triggered by Orchestrator)
- [ ] 2-hour update cron: Unchanged (reports on assigned coins)

---

## Testing the Coin Swap

### Test 1: Manual Coin Assignment
```bash
# Create Orchestrator task manually
hermes kanban create "Orchestrator - Coin Swap Test" \
  --assignee trading-orchestrator \
  --body "Discover coins, assign to Data Worker, evaluate"

# Check which coins were selected
hermes kanban show t_<task_id> --json | jq '.metadata.assigned_coins'

# Expected: Dynamic list (e.g., ["BTC", "XRP", "SOL"])
```

### Test 2: Verify Data Worker Respects Assignment
```bash
# Check Data Worker task description
hermes kanban show t_<data_task_id>

# Expected: "Collect data for: BTC, XRP, SOL" (from Orchestrator)
# NOT: "Collect data for: BTC, ETH, SOL" (hardcoded)
```

### Test 3: Full Cycle (15 min)
```bash
# Wait for next 15-min cycle
# Check Telegram for 2-hour update

# Expected message:
"📊 Trading Update
Coins evaluated: SOL(3), DOGE(2), ETH(2)
(Previous cycle: BTC, XRP, SOL)
→ Coin swap working!"
```

---

## Benefits of Dynamic Coin Swap

| Benefit | Hardcoded (Old) | Dynamic (New) |
|---------|-----------------|---------------|
| **Adaptability** | ❌ Trades dead coins | ✅ Trades what's moving |
| **Opportunity** | ❌ Misses altcoin pumps | ✅ Catches volatility spikes |
| **Risk** | ❌ Overexposed to 3 coins | ✅ Diversified across opportunities |
| **Performance** | ❌ Suboptimal setups | ✅ Best setups each cycle |
| **Market Regime** | ❌ Same in all conditions | ✅ Adapts to vol/quiet markets |

---

## Next Steps

1. **Update Orchestrator SOUL.md** (already done ✅)
2. **Update Data Worker SOUL.md** (already done ✅)
3. **Implement `discover_coins()` in orchestrator_dynamic.py** (already done ✅)
4. **Update Data Worker to read assigned coins** (needs implementation)
5. **Remove Data Worker cron job** (Orchestrator triggers it)
6. **Test full coin swap cycle** (manual → cron)

**Ready to implement?**
