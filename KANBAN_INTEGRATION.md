# Kanban Integration - Whale Tracker

## Overview

The whale tracker automatically creates Kanban tasks for significant whale movements.

## How It Works

### 1. Signal Detection

```python
# Thresholds for Kanban task creation
KANBAN_THRESHOLDS = {
    'MAJOR': 5_000_000,      # >$5M always creates task
    'BEARISH': 2_000_000,    # >$2M exchange inflow
    'BULLISH': 2_000_000,    # >$2M exchange outflow
    'PORTFOLIO': 1_000_000,  # >$1M for portfolio coins
}
```

### 2. Task Creation Flow

```
Whale Movement Detected
         ↓
    Analyze Signal
         ↓
    Check Threshold
         ↓
    Create Kanban Task
         ↓
    Assign to Profile
         ↓
    Add Metadata
```

### 3. Task Structure

**Title Format:**
```
🐋 {SIGNAL_TYPE}: ${VALUE} {SYMBOL} - {FROM}... → {TO}...
```

**Example:**
```
🐋 BEARISH: $23,810,428 ETH - 0x77134cbc06... → Bitfinex...
```

**Body Content:**
```markdown
## 🚨 WHALE ALERT - BEARISH

**Token:** ETH
**Value:** $23,810,428 USD
**Timestamp:** 2026-06-03 04:13 UTC

### Movement Details
- **From:** `0x77134cbc06...` (Unknown Whale)
- **To:** `0x742d35cc66...` (Bitfinex)
- **Transaction:** [0x1a2b3c...](https://etherscan.io/tx/...)
- **Block:** 25230050

### Signal Analysis
- **Type:** BEARISH
- **From Exchange:** No
- **To Exchange:** Yes (Bitfinex)
- **Portfolio Coin:** Yes

### Recommended Action
**⚠️ POTENTIAL SELLING PRESSURE**

1. Monitor price action for next 1-4 hours
2. Check if this is part of a series of inflows
3. Consider reducing exposure if multiple bearish signals
4. Set tighter stop-losses on ETH positions
```

**Metadata (JSON):**
```json
{
  "task_type": "BEARISH_SIGNAL",
  "signal": {
    "symbol": "ETH",
    "value_usd": 23810428,
    "from": "0x77134cbc...",
    "to": "0x742d35cc...",
    "tx_hash": "0x1a2b3c...",
    "signal": "BEARISH"
  },
  "symbol": "ETH",
  "value_usd": 23810428,
  "tx_hash": "0x1a2b3c..."
}
```

### 4. Task Assignment

Tasks are assigned based on signal type:

| Signal Type | Assignee | Priority |
|-------------|----------|----------|
| MAJOR | `trading-data` | 🔴 HIGH |
| BEARISH | `trading-data` | 🟠 MEDIUM |
| BULLISH | `trading-data` | 🟢 LOW |
| PORTFOLIO | `trading-orchestrator` | 🟡 MEDIUM |

### 5. Command Example

```bash
# Create task via CLI
hermes kanban create \
  "🐋 BEARISH: $23,810,428 ETH - 0x77134cbc... → Bitfinex..." \
  --body "## 🚨 WHALE ALERT..." \
  --assignee trading-data \
  --metadata '{"task_type":"BEARISH_SIGNAL","symbol":"ETH","value_usd":23810428}'
```

### 6. Downstream Workflow

Once task is created:

```
Task Created (trading-data)
         ↓
Data Worker Analyzes
         ↓
Adds Comment with Context
         ↓
Completes Task with Result
         ↓
Orchestrator Task Auto-Created
         ↓
Orchestrator Makes Decision
         ↓
Trading-Floor Task Created
         ↓
Position Adjusted
```

### 7. Example Task Chain

**Parent Task (t_abc123):**
```
🐋 BEARISH: $23.8M ETH → Bitfinex
Assignee: trading-data
Status: completed
Result: "Confirmed: Large exchange inflow, 3rd in series"
```

**Child Task (t_def456):**
```
🎯 Evaluate ETH Position - Bearish Signal
Assignee: trading-orchestrator
Status: completed
Result: "Recommend: Reduce 50% of ETH position"
```

**Grandchild Task (t_ghi789):**
```
🚨 EXECUTE: Sell 50% ETH Position
Assignee: trading-floor
Status: completed
Result: "Sold 0.5 ETH @ $1,837 | PnL: +2.3%"
```

## Code Implementation

### Main Function

```python
def scan_and_create_tasks(self) -> Dict:
    """Full scan + Kanban task creation"""
    
    # 1. Scan for signals
    top10_signals = self.scan_all_whales()
    portfolio_signals = self.scan_portfolio_wallets()
    
    # 2. Deduplicate
    all_signals = deduplicate(top10_signals + portfolio_signals)
    
    # 3. Create tasks for significant signals
    tasks_created = []
    
    for signal in all_signals:
        if should_create_task(signal):
            task_id = self.create_kanban_task(signal)
            tasks_created.append({
                'task_id': task_id,
                'signal': signal,
            })
    
    return {
        'signals': all_signals,
        'tasks_created': tasks_created,
    }
```

### Task Creation

```python
def create_kanban_task(self, signal: Dict) -> Optional[str]:
    """Create Kanban task for a signal"""
    
    # Build title
    title = f"🐋 {signal['signal']}: ${signal['value_usd']:,.0f} {signal['symbol']}"
    
    # Build body
    body = f"""
## 🚨 WHALE ALERT

**Token:** {signal['symbol']}
**Value:** ${signal['value_usd']:,.2f}

### Movement
- **From:** {signal['from_label']}
- **To:** {signal['to_label']}
- **TX:** {signal['tx_hash']}

### Recommended Action
{get_recommendation(signal)}
"""
    
    # Execute CLI command
    cmd = [
        'hermes', 'kanban', 'create',
        title,
        '--body', body,
        '--assignee', 'trading-data',
        '--metadata', json.dumps(signal)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        return extract_task_id(result.stdout)
    return None
```

## Cron Integration

Run every 15 minutes:

```bash
# Add to crontab
*/15 * * * * cd /mnt/data/hermes/workspace/trading_system && \
  python3 kanban_whale_tracker.py >> /var/log/whale_tracker.log 2>&1
```

Or via Hermes cron:

```python
hermes cron create \
  --name "Whale Tracker (15min)" \
  --schedule "*/15 * * * *" \
  --prompt "Run kanban_whale_tracker.py and report tasks created"
```

## Testing

Test with mock signal:

```python
# test_kanban_integration.py
mock_signal = {
    'symbol': 'ETH',
    'value_usd': 5_000_000,
    'signal': 'BEARISH',
    'from': '0x123...',
    'to': '0x456...',
    'from_label': 'Test Whale',
    'to_label': 'Binance',
    'tx_hash': '0xabc...',
    'timestamp': int(time.time()),
}

tracker = KanbanWhaleTracker()
task_id = tracker.create_kanban_task(mock_signal)
print(f"Created task: {task_id}")
```

## Files

| File | Purpose |
|------|---------|
| `kanban_whale_tracker.py` | Main tracker with Kanban integration |
| `whale_reports/kanban_whale_*.md` | Human-readable reports |
| `whale_reports/kanban_whale_*.json` | Machine data with task IDs |
