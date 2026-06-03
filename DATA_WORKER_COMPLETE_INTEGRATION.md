# Data Worker - Complete Function Integration

## Overview

The Unified Data Worker (`data_worker_unified.py`) integrates **ALL** Data Worker functions built throughout development:

| Function | Module | Purpose | Status |
|----------|--------|---------|--------|
| **1. Coin Discovery** | `data_worker_discovery.py` | Scan 15 candidates, select top 3-5 | ✅ Integrated |
| **2. Whale Tracking** | `kanban_whale_tracker.py` | Monitor TOP 10 + Portfolio coins | ✅ Integrated |
| **3. Glassnode Analysis** | `glassnode_bulk_fetch.py` | On-chain metrics per coin | ✅ Integrated |
| **4. Technical Analysis** | `momentum_bot.py`, `mean_reversion_bot.py` | RSI, MACD, Bollinger Bands | ⚠️ Placeholder (execution phase) |

---

## Function 1: Coin Discovery

**File:** `data_worker_discovery.py`

**What It Does:**
1. Scans all 15 candidate coins (BTC, ETH, SOL, BNB, XRP, ADA, AVAX, MATIC, DOT, LINK, UNI, ATOM, DOGE, LTC, BCH)
2. Fetches 24h volume, volatility, price change from Binance.US
3. Calculates opportunity scores:
   - Volume score (40% weight)
   - Volatility score (30% weight)
   - Whale activity score (20% weight)
   - News/sentiment score (10% weight)
4. Fetches Glassnode leading indicator (ONCE for all coins)
5. Applies Glassnode adjustment (-100 to +20 points)
6. Filters coins with score >= 50 and not BLOCKED
7. Selects top 3-5 coins

**Glassnode Integration:**
```python
# Fetch ONCE for all coins
glassnode_signal = get_glassnode_signal('BTC')

# Apply to all coins
if glassnode_signal['signal'] == 'STRONG_SELL':
    score_adjustment = -100  # HARD BLOCK
    allow_long = False
elif glassnode_signal['signal'] == 'STRONG_BUY':
    score_adjustment = +20
    allow_long = True
```

**Output:**
```json
{
  "scanned": 15,
  "qualified": 5,
  "selected": [
    {
      "symbol": "ETH",
      "rank": 1,
      "scores": {"total": 72.5},
      "volume_24h": 1800000000,
      "bias": "LONG",
      "allow_long": true
    }
  ]
}
```

---

## Function 2: Whale Tracking

**File:** `kanban_whale_tracker.py`

**What It Does:**
1. Scans TOP 10 tokens by market cap (ex-stablecoins): WBTC, ETH, BNB, TRX, ADA, LINK, UNI, AVAX, DOT, MATIC
2. Scans Portfolio coins from `coin_universe.json` (15 coins)
3. Monitors 13 whale wallets (exchanges, bridges, Vitalik)
4. Detects movements >$1M (portfolio coins) or >$5M (major)
5. Classifies signals: MAJOR, BEARISH (to exchange), BULLISH (from exchange)
6. Creates Kanban tasks for significant movements

**Thresholds:**
```python
KANBAN_THRESHOLDS = {
    'MAJOR': 5_000_000,      # >$5M always creates task
    'BEARISH': 2_000_000,    # >$2M exchange inflow
    'BULLISH': 2_000_000,    # >$2M exchange outflow
    'PORTFOLIO': 1_000_000,  # >$1M for portfolio coins
}
```

**Output:**
```json
{
  "signals": [
    {
      "symbol": "ETH",
      "value_usd": 23810428,
      "signal": "BEARISH",
      "from": "0x77134cbc...",
      "to": "0x742d35cc... (Bitfinex)",
      "tx_hash": "0xabc123..."
    }
  ],
  "counts": {
    "total": 3,
    "major": 1,
    "bearish": 1,
    "bullish": 1
  }
}
```

---

## Function 3: Glassnode Analysis

**File:** `glassnode_bulk_fetch.py`

**What It Does:**
1. Loads coin list from `state/coin_universe.json` (dynamic, not hardcoded)
2. Fetches on-chain metrics for ALL coins in single bulk call:
   - Exchange balance (7d change)
   - Whale wallet count (7d change)
3. Calculates per-coin signals:
   - STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL
4. Returns structured data for Orchestrator

**Bulk Fetch:**
```python
def fetch_glassnode_bulk(coins: List[str]) -> Dict:
    """Fetch all coins in single API call"""
    
    # Load dynamic coin list
    if not coins:
        coins = load_coin_universe()
    
    # Fetch exchange balance + whale wallets for all coins
    results = []
    for coin in coins:
        exchange_data = fetch_exchange_balance(coin)
        whale_data = fetch_whale_wallets(coin)
        
        signal = calculate_signal(exchange_data, whale_data)
        results.append({
            'coin': coin,
            'signal': signal,
            'score': combined_score,
        })
    
    return {'success': True, 'data': results}
```

**Output:**
```json
{
  "success": true,
  "data": [
    {
      "coin": "BTC",
      "signal": "STRONG_SELL",
      "score": 17.5,
      "metrics": {
        "exchange_balance": {"7d_change_pct": 0.52},
        "whale_wallets": {"7d_change_pct": -2.62}
      }
    }
  ]
}
```

---

## Function 4: Technical Analysis (Placeholder)

**Files:** `momentum_bot.py`, `mean_reversion_bot.py`

**Current Status:** ⚠️ **Execution Phase Only**

These bots are designed to work **after** Orchestrator makes decisions. They require:
- Orchestrator's EXIT/ENTER/HOLD decision
- Position sizing
- Entry/exit prices

**Future Integration:**
```python
# In production, this would run during discovery
def run_technical_analysis(coins: List[str]) -> Dict:
    for coin in coins:
        # Momentum
        rsi = calculate_rsi(coin)
        macd = calculate_macd(coin)
        momentum_signal = 'BUY' if rsi < 30 else 'SELL' if rsi > 70 else 'HOLD'
        
        # Mean Reversion
        bb_upper, bb_lower = calculate_bollinger_bands(coin)
        mr_signal = 'BUY' if price < bb_lower else 'SELL' if price > bb_upper else 'HOLD'
        
        signals[coin] = {
            'momentum': momentum_signal,
            'mean_reversion': mr_signal,
        }
```

---

## Unified Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR (15 min)                        │
│  Creates Kanban task: "🔍 Data Discovery"                       │
│  Metadata: {"mode": "discovery", "coins": null}                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              DATA WORKER (runs all 4 functions)                 │
│                                                                 │
│  1️⃣  COIN DISCOVERY                                            │
│      - Scan 15 candidates                                       │
│      - Calculate scores (volume + volatility + whale)           │
│      - Apply Glassnode bias (LONG blocked if STRONG_SELL)       │
│      - Select top 3-5 coins                                     │
│                                                                 │
│  2️⃣  WHALE TRACKING                                            │
│      - Scan TOP 10 (ex-stablecoins)                             │
│      - Scan Portfolio coins                                     │
│      - Create Kanban tasks for >$5M moves                       │
│                                                                 │
│  3️⃣  GLASSNODE ANALYSIS                                        │
│      - Fetch on-chain metrics for selected coins                │
│      - Calculate per-coin signals                               │
│                                                                 │
│  4️⃣  TECHNICAL ANALYSIS (placeholder)                           │
│      - Deferred to execution phase                              │
│                                                                 │
│  📊 AGGREGATE RESULTS                                           │
│      - Combine all 4 functions                                  │
│      - Calculate final sentiment per coin                       │
│      - Generate unified report                                  │
│                                                                 │
│  ✅ COMPLETE KANBAN TASK                                        │
│      - Result: "Analyzed 15 coins, selected 3"                  │
│      - Metadata: {coins: [...], signals: {...}}                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR (resumes)                       │
│  Reads unified report                                           │
│  Makes per-coin decisions:                                      │
│  - ETH: ENTER_LONG (bullish whale flow)                         │
│  - BTC: HOLD (neutral)                                          │
│  - SOL: EXIT (bearish Glassnode)                                │
│                                                                 │
│  Creates Trading-Floor tasks                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Running The Unified Worker

### Manual Execution
```bash
cd /mnt/data/hermes/workspace/trading_system
python3 data_worker_unified.py
```

### Cron Schedule (Production)
```bash
# Every 5 minutes
*/5 * * * * cd /mnt/data/hermes/workspace/trading_system && \
  python3 data_worker_unified.py >> /var/log/data_worker.log 2>&1
```

### Via Hermes Cron
```python
hermes cron create \
  --name "Data Worker - Unified" \
  --schedule "*/5 * * * *" \
  --prompt "Run data_worker_unified.py and report results"
```

---

## Output Files

| File | Format | Location |
|------|--------|----------|
| `unified_worker_YYYYMMDD_HHMMSS.json` | JSON (full data) | `whale_reports/` |
| `unified_worker_YYYYMMDD_HHMMSS.md` | Markdown (summary) | `whale_reports/` |
| `state/data_worker_latest.json` | JSON (latest state) | `state/` |

---

## Key Integration Points

### 1. Glassnode Bias Applies To All Coins
```python
# Single Glassnode fetch (BTC leading indicator)
glassnode_signal = get_glassnode_signal('BTC')

# If STRONG_SELL, ALL coins are BLOCKED for LONG
if glassnode_signal['signal'] == 'STRONG_SELL':
    for coin in candidates:
        coin['allow_long'] = False
        coin['scores']['total'] = 0
```

### 2. Whale Tracking Independent Of Discovery
```python
# Whale tracking runs regardless of coin selection
whale_signals = tracker.scan_all_whales()

# Creates Kanban tasks automatically
for signal in whale_signals:
    if signal['value_usd'] > THRESHOLD:
        create_kanban_task(signal)
```

### 3. Glassnode Analysis For Selected Coins Only
```python
# Only analyze coins that passed discovery
coins_to_analyze = [c['symbol'] for c in discovery['selected']]

glassnode_result = fetch_glassnode_bulk(coins_to_analyze)
```

---

## Current Limitations

1. **Glassnode MCP Not Configured**
   - Currently using cached test data (STRONG_SELL for BTC)
   - Need to configure MCP in Hermes config

2. **Technical Analysis Deferred**
   - `momentum_bot.py` and `mean_reversion_bot.py` require Orchestrator decisions
   - Would need separate analysis functions for discovery phase

3. **No Real-Time Price Data**
   - Binance.US API works but limited volume data
   - Consider Massive.com for broader coverage

---

## Next Steps

1. **Configure Glassnode MCP**
   ```yaml
   # config.yaml
   mcp:
     glassnode:
       transport: http
       url: https://api.glassnode.com/mcp
       api_key: ${GLASSNODE_API_KEY}
   ```

2. **Add Technical Analysis Functions**
   - Create `technical_analysis.py` with standalone RSI/MACD/Bollinger functions
   - Integrate into `data_worker_unified.py`

3. **Set Up Cron**
   - Deploy to production cron
   - Monitor logs for errors

4. **Test With Real Data**
   - Wait for whale movements
   - Verify Kanban task creation
   - Validate end-to-end flow
