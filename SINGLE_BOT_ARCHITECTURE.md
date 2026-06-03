# Single Bot Architecture (Kanban-Driven)

## Core Principle

**One bot per strategy, direction specified in Kanban task metadata.**

```
❌ OVER-ENGINEERED (6 profiles):
   trading-momentum-long
   trading-momentum-short
   trading-mean-reversion-long
   trading-mean-reversion-short
   trading-breakout-long
   trading-breakout-short

✅ SIMPLE (3 profiles):
   trading-momentum
   trading-mean-reversion
   trading-breakout
```

---

## How It Works

### Kanban Task Metadata

```json
{
  "direction": "LONG",
  "coin": "BTC",
  "method": "momentum",
  "reason": "Etherscan BUY (75/100)",
  "etherscan_score": 75,
  "etherscan_signal": "BUY"
}
```

**OR for SHORT:**

```json
{
  "direction": "SHORT",
  "coin": "ETH",
  "method": "mean_reversion",
  "reason": "Etherscan SELL (35/100)",
  "etherscan_score": 35,
  "etherscan_signal": "SELL"
}
```

---

## Bot Logic (Single File)

```python
# momentum_bot.py

def execute_momentum_trade(task_metadata: Dict) -> Dict:
    """
    Single bot handles BOTH LONG and SHORT.
    Direction comes from Kanban task metadata.
    """
    
    direction = task_metadata['direction']  # 'LONG' or 'SHORT'
    coin = task_metadata['coin']
    
    if direction == 'LONG':
        # Bullish logic
        if not is_bullish_setup(coin):
            return {'status': 'SKIPPED', 'reason': 'No bullish setup'}
        
        entry_price = get_current_price(coin)
        stop_loss = entry_price * 0.97  # -3%
        take_profit = entry_price * 1.06  # +6%
        
        return {
            'action': 'BUY',
            'coin': coin,
            'entry': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'direction': 'LONG',
        }
    
    else:  # SHORT
        # Bearish logic
        if not is_bearish_setup(coin):
            return {'status': 'SKIPPED', 'reason': 'No bearish setup'}
        
        entry_price = get_current_price(coin)
        stop_loss = entry_price * 1.03  # +3%
        take_profit = entry_price * 0.94  # -6%
        
        return {
            'action': 'SELL',  # or 'SHORT' depending on exchange
            'coin': coin,
            'entry': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'direction': 'SHORT',
        }
```

---

## Kanban Task Examples

### LONG Task

```bash
hermes kanban create \
  "🟢 ENTER_LONG BTC - Momentum" \
  --assignee trading-momentum \
  --metadata '{
    "direction": "LONG",
    "coin": "BTC",
    "method": "momentum",
    "reason": "Etherscan BUY (75/100)"
  }'
```

### SHORT Task

```bash
hermes kanban create \
  "🔴 ENTER_SHORT ETH - Momentum" \
  --assignee trading-momentum \
  --metadata '{
    "direction": "SHORT",
    "coin": "ETH",
    "method": "momentum",
    "reason": "Etherscan SELL (35/100)"
  }'
```

---

## Orchestrator Routing (Simple)

```python
def create_method_tasks(coin: str, etherscan_signal: str, score: float):
    """
    Create tasks for method bots.
    Direction determined by Etherscan signal.
    """
    tasks = []
    
    # Determine direction
    if score >= 65:
        direction = 'LONG'
        emoji = '🟢'
    elif score <= 35:
        direction = 'SHORT'
        emoji = '🔴'
    else:
        return []  # HOLD - no action
    
    # Create task for each method
    for method in ['momentum', 'mean_reversion']:
        task = {
            'title': f"{emoji} {direction} {coin} - {method.title()} Strategy",
            'assignee': f'trading-{method}',  # Single profile per method
            'metadata': {
                'direction': direction,
                'coin': coin,
                'method': method,
                'reason': f"Etherscan {etherscan_signal} ({score}/100)",
            }
        }
        tasks.append(task)
    
    return tasks
```

---

## Bot Validation Logic

### Momentum Bot (Handles Both)

```python
def validate_momentum_entry(coin: str, direction: str) -> bool:
    """
    Validate entry based on direction.
    """
    rsi = get_rsi(coin)
    macd = get_macd(coin)
    
    if direction == 'LONG':
        # Bullish setup
        return rsi > 50 and macd['signal'] == 'bullish'
    else:  # SHORT
        # Bearish setup
        return rsi < 50 and macd['signal'] == 'bearish'
```

### Mean Reversion Bot (Handles Both)

```python
def validate_mean_reversion_entry(coin: str, direction: str) -> bool:
    """
    Validate mean reversion based on direction.
    """
    rsi = get_rsi(coin)
    bb_position = get_bollinger_position(coin)  # 0=lower, 1=middle, 2=upper
    
    if direction == 'LONG':
        # Oversold bounce
        return rsi < 35 and bb_position == 0  # Below lower band
    else:  # SHORT
        # Overbought fade
        return rsi > 65 and bb_position == 2  # Above upper band
```

---

## Complete Task Flow

### LONG Example

```
1. DATA WORKER:
   - Etherscan: BUY (75/100) for BTC
   - Bias: LONG

2. ORCHESTRATOR:
   - Creates: "🟢 ENTER_LONG BTC - Momentum"
   - Assignee: trading-momentum
   - Metadata: {"direction": "LONG", ...}

3. MOMENTUM BOT:
   - Reads direction: LONG
   - Validates: RSI 58 (>50 ✓), MACD bullish ✓
   - Calculates: Entry $67,500, Stop $65,475, Target $71,550
   - Creates execution task

4. TRADING-FLOOR:
   - Executes: BUY 0.015 BTC @ $67,500
   - Sets stop/target
   - Reports PnL
```

### SHORT Example

```
1. DATA WORKER:
   - Etherscan: SELL (35/100) for ETH
   - Bias: SHORT

2. ORCHESTRATOR:
   - Creates: "🔴 ENTER_SHORT ETH - Momentum"
   - Assignee: trading-momentum
   - Metadata: {"direction": "SHORT", ...}

3. MOMENTUM BOT:
   - Reads direction: SHORT
   - Validates: RSI 42 (<50 ✓), MACD bearish ✓
   - Calculates: Entry $1,840, Stop $1,895, Target $1,730
   - Creates execution task

4. TRADING-FLOOR:
   - Executes: SELL 0.05 ETH @ $1,840
   - Sets stop/target
   - Reports PnL
```

---

## Profile Structure (Minimal)

| Profile | Purpose | Handles |
|---------|---------|---------|
| `trading-data` | Discovery & analysis | All coins, all signals |
| `trading-orchestrator` | Routing | LONG/SHORT decisions |
| `trading-momentum` | Momentum strategy | LONG + SHORT (single bot) |
| `trading-mean-reversion` | Mean reversion | LONG + SHORT (single bot) |
| `trading-breakout` | Breakout strategy | LONG + SHORT (single bot) |
| `trading-floor` | Execution | All trades |

**Total: 6 profiles** (vs 10+ with split approach)

---

## Advantages of Single Bot

| Advantage | Explanation |
|-----------|-------------|
| **Simpler** | 3 bots instead of 6 |
| **Less Code** | No duplication of logic |
| **Easier Maintenance** | Fix bug once, not twice |
| **Consistent** | Same validation for both directions |
| **Flexible** | Easy to add new methods |
| **Kanban-Driven** | Direction in metadata, not profile name |

---

## Current State → Target State

### Current (What You Have)

```
✅ trading-data
✅ trading-orchestrator
✅ trading-momentum (mixed, but works)
✅ trading-floor
```

### Add (Only What's Missing)

```
➕ trading-mean-reversion (single bot, handles LONG+SHORT)
➕ trading-breakout (single bot, handles LONG+SHORT)
```

**That's it!** No need to split existing profiles.

---

## Implementation (Minimal Changes)

### 1. Update `momentum_bot.py`

```python
# Add direction handling
def execute_momentum_trade(task_metadata: Dict) -> Dict:
    direction = task_metadata['direction']  # NEW
    
    if direction == 'LONG':
        # Existing bullish logic
        ...
    else:
        # NEW: Bearish logic (mirror of LONG)
        ...
```

### 2. Update `mean_reversion_bot.py`

```python
# Add direction handling
def execute_mean_reversion(symbol: str, decision: Dict) -> Dict:
    direction = decision.get('direction', 'LONG')  # NEW
    
    if direction == 'LONG':
        # Existing oversold bounce logic
        ...
    else:
        # NEW: Overbought fade logic
        ...
```

### 3. Update Orchestrator

```python
# Route based on Etherscan signal
if score >= 65:
    direction = 'LONG'
elif score <= 35:
    direction = 'SHORT'
else:
    return  # HOLD

# Create task with direction in metadata
hermes kanban create \
  f"{'🟢' if direction == 'LONG' else '🔴'} {direction} {coin} - {method}" \
  --assignee trading-{method} \
  --metadata '{"direction": "..."}'
```

---

## Summary

**Your instinct was correct:**

| Approach | Profiles | Complexity | Verdict |
|----------|----------|------------|---------|
| **Split Bots** | 6+ (long/short per method) | High | ❌ Over-engineered |
| **Single Bot** | 3 (one per method) | Low | ✅ **Correct** |

**Kanban metadata carries the direction** - no need for separate profiles.

**Current market (SELL 38.2/100):**
- Orchestrator creates SHORT tasks
- Momentum bot receives: `{"direction": "SHORT"}`
- Bot validates bearish setup
- Executes SHORT if valid

**Simple, clean, Kanban-driven.**

---

**Want me to update the existing bots to handle both directions?** (Should be ~20 lines of code per bot)
