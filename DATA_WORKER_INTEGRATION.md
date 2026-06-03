# Data Worker - Complete Integration Guide

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         ORCHESTRATOR (15 min)                           │
│  - Discovers coins from coin_universe.json                              │
│  - Creates Data Worker task with assigned coins                         │
│  - Waits for Data Worker to complete                                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓ (creates task)
┌─────────────────────────────────────────────────────────────────────────┐
│                      DATA WORKER (5 min cycles)                         │
│  1. Load assigned coins from Orchestrator state                         │
│  2. Run whale tracking scan (TOP 10 + Portfolio)                        │
│  3. Analyze signals per coin                                            │
│  4. Create Kanban tasks for significant movements                       │
│  5. Complete task with discovery report                                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓ (completes task)
┌─────────────────────────────────────────────────────────────────────────┐
│                         ORCHESTRATOR (resumes)                          │
│  - Reads Data Worker results                                            │
│  - Makes per-coin decisions (EXIT/ENTER/HOLD)                           │
│  - Creates Trading-Floor tasks for execution                            │
└─────────────────────────────────────────────────────────────────────────┘
```

## Data Worker Flow (Step-by-Step)

### Step 1: Load Assigned Coins

```python
def load_orchestrator_state() -> Dict:
    """Load latest Orchestrator state"""
    state_file = STATE_DIR / 'orchestrator_latest.json'
    
    if state_file.exists():
        with open(state_file, 'r') as f:
            return json.load(f)
    
    # Fallback to coin_universe.json
    return {'coins': ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']}
```

**Input:** `state/orchestrator_latest.json`
```json
{
  "coins": ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX"],
  "updated_at": "2026-06-03T03:45:00Z",
  "task_id": "t_b1255f0a"
}
```

**Output:** List of coins to analyze

---

### Step 2: Run Whale Tracking Scan

```python
tracker = KanbanWhaleTracker()
tracker.get_eth_price()

# Scan TOP 10 tokens (ex-stablecoins)
top10_signals = tracker.scan_all_whales()

# Scan portfolio-specific coins
portfolio_signals = tracker.scan_portfolio_wallets()

# Combine and deduplicate
all_signals = deduplicate(top10_signals + portfolio_signals)
```

**What Gets Scanned:**
- **TOP 10:** WBTC, ETH, BNB, TRX, ADA, LINK, UNI, AVAX, DOT, MATIC
- **Portfolio:** All 15 coins from `coin_universe.json`
- **Wallets:** 13 known whale addresses (exchanges, bridges, Vitalik)

**Output:** List of signals (whale movements >$1M)

---

### Step 3: Per-Coin Analysis

```python
def analyze_coin_signals(coin: str, signals: List[Dict]) -> Dict:
    """Analyze all signals for a specific coin"""
    
    coin_signals = [s for s in signals if s['symbol'] == coin]
    
    # Calculate net flow
    inflows = sum(s['value_usd'] for s in coin_signals if s['to_exchange'])
    outflows = sum(s['value_usd'] for s in coin_signals if s['from_exchange'])
    net_flow = outflows - inflows  # Positive = bullish
    
    # Determine sentiment
    if net_flow > 5_000_000:
        return {
            'sentiment': 'BULLISH',
            'recommendation': 'ENTER_LONG',
            'confidence': 0.8,
        }
    elif net_flow < -5_000_000:
        return {
            'sentiment': 'BEARISH',
            'recommendation': 'EXIT',
            'confidence': 0.8,
        }
    else:
        return {
            'sentiment': 'NEUTRAL',
            'recommendation': 'HOLD',
            'confidence': 0.5,
        }
```

**Output per Coin:**
```json
{
  "coin": "ETH",
  "signal_count": 3,
  "inflows_usd": 23_810_428,
  "outflows_usd": 0,
  "net_flow_usd": -23_810_428,
  "sentiment": "BEARISH",
  "recommendation": "EXIT",
  "confidence": 0.95
}
```

---

### Step 4: Create Kanban Tasks

```python
for coin, analysis in coin_analysis.items():
    if analysis['total_volume_usd'] >= KANBAN_THRESHOLDS['PORTFOLIO']:
        task_id = create_discovery_task(coin, analysis)
        
        # Task created:
        # Title: "🔴 ETH Whale Activity: $23,810,428 - EXIT"
        # Assignee: trading-data
        # Metadata: {analysis, coin, task_type}
```

**Tasks Created:**
- One task per coin with significant whale activity
- Assigned to `trading-data` profile
- Contains full analysis in body
- Metadata includes structured data for downstream tasks

---

### Step 5: Complete Task with Report

```python
def complete_kanban_task(task_id: str, result: Dict):
    """Complete the Data Worker task"""
    
    result_text = f"✅ Analyzed {result['coins_analyzed']} coins"
    result_text += f", found {result['signals_found']} signals"
    result_text += f", created {result['tasks_created']} tasks"
    
    hermes kanban complete {task_id} \
      --result "{result_text}" \
      --summary "Whale analysis complete" \
      --metadata "{...}"
```

**Result Format:**
```
✅ Analyzed 15 coins, found 3 signals, created 2 tasks | 🔴 Bearish bias
```

---

## File Structure

```
/mnt/data/hermes/workspace/trading_system/
│
├── data_worker_kanban.py          # Main Data Worker (this file)
├── kanban_whale_tracker.py        # Whale tracking + Kanban integration
├── top10_whale_tracker.py         # TOP 10 token tracker
│
├── state/
│   ├── coin_universe.json         # Dynamic coin list (15 coins)
│   ├── orchestrator_latest.json   # Orchestrator state
│   └── data_worker_latest.json    # Latest worker results
│
└── whale_reports/
    ├── data_worker_20260603_041949.json
    ├── kanban_whale_20260603_041949.md
    └── ...
```

---

## Cron Schedule

```bash
# Data Worker - Every 5 minutes
*/5 * * * * cd /mnt/data/hermes/workspace/trading_system && \
  python3 data_worker_kanban.py >> /var/log/data_worker.log 2>&1

# Orchestrator - Every 15 minutes
*/15 * * * * cd /mnt/data/hermes/workspace/trading_system && \
  python3 orchestrator_kanban.py >> /var/log/orchestrator.log 2>&1
```

Or via Hermes cron:

```python
# Data Worker (5 min)
hermes cron create \
  --name "Data Worker - Whale Analysis" \
  --schedule "*/5 * * * *" \
  --prompt "Run data_worker_kanban.py"

# Orchestrator (15 min)
hermes cron create \
  --name "Orchestrator - Coin Decisions" \
  --schedule "*/15 * * * *" \
  --prompt "Run orchestrator_kanban.py"
```

---

## Example Execution

### Input (Orchestrator State)
```json
{
  "coins": ["BTC", "ETH", "SOL", "BNB"],
  "task_id": "t_b1255f0a"
}
```

### Data Worker Output
```
================================================================================
DATA WORKER - WHALE ANALYSIS
Executed: 2026-06-03 04:19 UTC
================================================================================

📋 Step 1: Loading assigned coins...
   Assigned coins: 4
   Coins: BTC, ETH, SOL, BNB

🔍 Step 2: Running whale tracking scan...
   ETH: $1,837.48 | BTC: $67,000
   
   Scanning TOP 10 + Portfolio coins...
   [1/13] Binance 8                 ✓
   [2/13] Binance Cold              ✓
   ...
   
   📊 Found 3 unique signals

📈 Step 3: Per-coin whale analysis...
   ⚪ BTC    | No significant whale activity
   🔴 ETH    |  2 signals | Net: $-23,810,428 | EXIT
   ⚪ SOL    | No significant whale activity
   ⚪ BNB    | No significant whale activity

📋 Step 4: Creating Kanban tasks...
   ✅ Created task: t_abc123 (ETH)
   
   ✅ Created 1 Kanban tasks

📝 Step 5: Generating discovery report...
   💾 Report saved: data_worker_20260603_041949.json

================================================================================
DISCOVERY SUMMARY
================================================================================
Coins Analyzed: 4
Whale Signals: 3
Kanban Tasks: 1

Sentiment:
  🟢 Bullish: 0 coins
  🔴 Bearish: 1 coins (ETH)
  ⚪ Neutral: 3 coins (BTC, SOL, BNB)

📋 TASKS CREATED:
  • t_abc123 | ETH | EXIT | $23,810,428

================================================================================
✅ DATA WORKER COMPLETE
================================================================================
```

---

## Integration Points

### 1. Orchestrator → Data Worker
- **Mechanism:** Kanban task creation
- **Data:** Assigned coins in task metadata
- **Frequency:** Every 15 minutes

### 2. Data Worker → Whale Tracker
- **Mechanism:** Function call
- **Data:** None (tracker scans all wallets)
- **Frequency:** Every 5 minutes

### 3. Data Worker → Kanban
- **Mechanism:** `hermes kanban create` CLI
- **Data:** Per-coin analysis tasks
- **Frequency:** As needed (when signals detected)

### 4. Data Worker → State Files
- **Mechanism:** JSON file write
- **Data:** Analysis results, signals, tasks
- **Frequency:** Every execution

### 5. Data Worker → Orchestrator (completion)
- **Mechanism:** `hermes kanban complete` CLI
- **Data:** Summary results in metadata
- **Frequency:** Every execution

---

## Error Handling

```python
try:
    # Scan whales
    signals = tracker.scan_all_whales()
    
    # Analyze
    coin_analysis = analyze_coins(signals)
    
    # Create tasks
    tasks = create_tasks(coin_analysis)
    
    # Complete
    complete_kanban_task(task_id, result)
    
except Exception as e:
    # Log error
    log_error(e)
    
    # Complete task with error status
    complete_kanban_task(task_id, {
        'status': 'error',
        'error': str(e),
    })
```

---

## Testing

### Unit Test
```python
def test_data_worker():
    result = run_data_worker()
    
    assert result['status'] == 'success'
    assert 'coins_analyzed' in result
    assert 'signals_found' in result
    assert 'coin_analysis' in result
```

### Integration Test
```python
def test_full_flow():
    # 1. Create Orchestrator task
    orch_task = create_orchestrator_task()
    
    # 2. Run Data Worker
    worker_result = run_data_worker()
    
    # 3. Verify tasks created
    assert worker_result['tasks_created'] >= 0
    
    # 4. Verify state saved
    assert state_file.exists()
    
    # 5. Verify Kanban completion
    assert task_is_completed(orch_task['id'])
```

---

## Next Steps

1. **Deploy to cron** - Set up 5-minute schedule
2. **Add Telegram alerts** - Notify when tasks created
3. **Integrate with Orchestrator** - Full end-to-end flow
4. **Add backtesting** - Validate whale signal accuracy
