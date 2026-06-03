# Trading Data Worker

## Overview
Fetches market data, whale activity, and news for the trading system. Runs every 5 minutes via Kanban task system.

## Modes

### Development Mode (Default)
Uses mock data - no API keys required. Perfect for:
- Testing the Kanban workflow
- Developing the orchestrator logic
- Backtesting with historical data

### Live Mode
Uses real API data. Requires API keys (see configuration below).

## Configuration

Edit `data_worker.py` CONFIG dictionary:

```python
CONFIG = {
    # Development Mode
    "use_mock_data": True,  # Set to False when going live
    
    # MEXC API (for trade execution - Phase 2+)
    "mexc_api_key": "YOUR_KEY_HERE",
    "mexc_api_secret": "YOUR_SECRET_HERE",
    "mexc_testnet": True,
    
    # Etherscan API (whale tracking - free tier)
    "etherscan_api_key": "YOUR_KEY_HERE",  # Get from etherscan.io/myapikey
    
    # CryptoPanic API (news sentiment - free tier)
    "cryptopanic_api_key": "YOUR_KEY_HERE",  # Get from cryptopanic.com/developers
    
    # Alert Thresholds
    "whale_alert_threshold_usd": 1_000_000,
    "price_change_alert_pct": 5.0,
}
```

## Usage

### Test Locally
```bash
cd /mnt/data/hermes/workspace/trading_system
python3 data_worker.py
```

### Run via Kanban Task
The orchestrator creates tasks like:
```python
kanban_create(
    title="Data Collection Cycle #42",
    assignee="trading-data",
    body="Run 5-minute data collection for top 10 coins",
)
```

The trading-data profile executes:
```bash
cd /mnt/data/hermes/workspace/trading_system
python3 data_worker.py
```

Then reports results via `kanban_complete()`.

## Output Format

```json
{
  "success": true,
  "summary": {
    "cycle_start": "2026-06-02T06:53:04.100777+00:00",
    "cycle_end": "2026-06-02T06:53:04.103364+00:00",
    "duration_seconds": 0.002587,
    "coins_processed": 3,
    "alerts_triggered": 0,
    "average_whale_score": 51.33,
    "news_sentiment": 45,
    "mode": "mock"
  },
  "coin_data": [
    {
      "symbol": "BTC",
      "whale_score": 52,
      "alert": {
        "alert_triggered": false,
        "alert_reason": null
      },
      "ohlcv": {...},
      "dex": {...},
      "whale": {...}
    }
  ],
  "alerts": [],
  "news": {...}
}
```

## Data Sources

### Mock Data (Development)
- OHLCV: Realistic random walk around actual prices
- DEX: Simulated volume and transaction counts
- Whale: Random scores 40-70 (mostly neutral)
- News: Random sentiment 45-65 (slight bullish bias)

### Live APIs (Production)
| Data Type | Source | Free Tier | Key Required |
|-----------|--------|-----------|--------------|
| OHLCV | Binance Public API | Unlimited | No |
| DEX Swaps | DexScreener API | Rate limited | No |
| ETH Whales | Etherscan API | 100k/day | Yes (free) |
| News | CryptoPanic API | 500/day | Yes (free) |
| Liquidations | Coinglass API | 60/min | Yes (free) |

## Alert Conditions

The Data Worker triggers alerts when:
- Price moves >5% in single candle
- DEX volume >$100M in 24h
- Whale score >80 or <20 (unusual activity)
- Large transaction count spikes >3x normal

## Next Steps

1. **Test with mock data** (current phase) ✅
2. **Get free API keys** when ready for live data
3. **Integrate with Kanban** for automated 5-min cycles
4. **Add backtesting mode** to fetch historical data

## File Structure

```
/mnt/data/hermes/workspace/trading_system/
├── data_worker.py       # This file
├── orchestrator.py      # (Next: Decision logic)
├── momentum_bot.py      # (Next: Strategy execution)
└── README.md           # This file
```
