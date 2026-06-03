#!/usr/bin/env python3
"""
Top 10 Token Whale Tracker - Etherscan V2 API

Tracks whale movements for TOP 10 tokens by market cap (excluding stablecoins):
1. Bitcoin (via WBTC on Ethereum)
2. Ethereum (ETH native)
3. BNB (ERC-20 version)
4. XRP (ERC-20 version)  
5. Solana (via wrapped SOL)
6. TRON (TRX ERC-20)
7. Dogecoin (wrapped DOGE)
8. Cardano (wrapped ADA)
9. Chainlink (LINK)
10. Polkadot (DOT)

Skips stablecoins (USDT, USDC) as large movements are usually minting/redemption.
"""

import os
import requests
import time
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional
from pathlib import Path

# Load API key
def get_api_key() -> str:
    env_path = Path('/mnt/data/hermes/.env')
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                if line.startswith('ETHERSCAN_API_KEY='):
                    return line.split('=')[1].strip()
    raise ValueError("ETHERSCAN_API_KEY not found in .env")

API_KEY = get_api_key()
BASE_URL = "https://api.etherscan.io/v2/api"

# ===== CONFIGURATION =====

# Whale threshold (USD)
WHALE_THRESHOLD_USD = 1_000_000  # $1M+

# TOP 10 tokens by market cap (excluding stablecoins)
# Only includes tokens with ERC-20 representation on Ethereum
TOP_10_TOKENS = {
    'WBTC': {
        'contract': '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599',
        'decimals': 8,
        'name': 'Wrapped Bitcoin',
        'rank': 1,
    },
    # ETH is tracked natively (not ERC-20)
    'BNB': {
        'contract': '0xB8c77482e45F1F44dE1745F52C74426C631bDD52',
        'decimals': 18,
        'name': 'Binance Coin',
        'rank': 3,
    },
    # XRP doesn't have major ERC-20 presence - skip
    # Wrapped SOL on Ethereum is minimal - skip
    'TRX': {
        'contract': '0x50327c6c5a14DCaDE707ABad2E27eB517df87AB5',
        'decimals': 6,
        'name': 'TRON',
        'rank': 6,
    },
    # Wrapped DOGE is minimal - skip
    'ADA': {
        'contract': '0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47',
        'decimals': 18,
        'name': 'Cardano',
        'rank': 9,
    },
    'LINK': {
        'contract': '0x514910771af9ca656af840dff83e8264ecf986ca',
        'decimals': 18,
        'name': 'Chainlink',
        'rank': 8,
    },
    'UNI': {
        'contract': '0x1f9840a85d5af5bf1d1762f925bdaddc4201f984',
        'decimals': 18,
        'name': 'Uniswap',
        'rank': 11,  # Close to top 10
    },
    'AVAX': {
        'contract': '0x85f138bfEE4ef8e540890CFb48F620571d67Eda3',
        'decimals': 18,
        'name': 'Avalanche',
        'rank': 9,
    },
    'DOT': {
        'contract': '0x7083609fCE4d1d8Dc0C979AAb8c869Ea2C873402',
        'decimals': 18,
        'name': 'Polkadot',
        'rank': 10,
    },
    'MATIC': {
        'contract': '0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0',
        'decimals': 18,
        'name': 'Polygon',
        'rank': 12,
    },
    'LTC': {
        'contract': '0x6c6EE5e31d828De241282B9606C8e98Ea48526E2',
        'decimals': 18,
        'name': 'Wrapped Litecoin',
        'rank': 15,
    },
}

# Known whale wallets (exchanges, institutions)
WHALE_WALLETS = {
    # Binance
    "0xF977814e90dA44bFA03b6295A0616a897441aceC": "Binance 8",
    "0x47ac0Fb4F2D84898e4D9E7b4DaB3C24507a6D503": "Binance Cold",
    "0x28C6c06298d514Db089934071355E5743bf21d60": "Binance 14",
    "0x21a31Ee1afC51d94C2eFcCAa2092aD1028285549": "Binance 15",
    "0xDFd5293D8e347dFe59E90eFd55b2956a1343963d": "Binance 16",
    
    # Coinbase
    "0xA9D1e08C7793af67e9d92fe308d5697FB81d3E43": "Coinbase 1",
    "0x503828976D22510aad0201ac7EC88293211D23Da": "Coinbase 2",
    
    # Kraken
    "0x2910543Af39abA0Cd09dBb2D50200b3E800A63D2": "Kraken 1",
    "0x5A52E96BAcdaBb82fd05763E25335261B270Efcb": "Kraken 2",
    
    # Bitfinex
    "0x742d35Cc6634C0532925a3b844Bc454e4438f44e": "Bitfinex",
    
    # Bridges
    "0x0716a17FBAeE714f1E6aB0f9d59edbC5f09815C0": "Arbitrum Bridge",
    "0x40ec5B33f54e0E8A33A975908C5BA1c14e5BbbDf": "Polygon Bridge",
    
    # Vitalik
    "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045": "Vitalik",
}

# Token prices (USD) - approximate
TOKEN_PRICES = {
    'BTC': 67000,
    'ETH': 1830,
    'BNB': 620,
    'TRX': 0.15,
    'ADA': 0.25,
    'LINK': 10,
    'UNI': 6,
    'AVAX': 25,
    'DOT': 5,
    'MATIC': 0.50,
    'LTC': 85,
}


class Top10WhaleTracker:
    """Track whale movements for top 10 tokens (ex-stablecoins)"""
    
    def __init__(self, api_key: str = API_KEY):
        self.api_key = api_key
        self.session = requests.Session()
        self.base_url = BASE_URL
        self.eth_price = 0
        self.token_prices = TOKEN_PRICES.copy()
    
    def _request(self, module: str, action: str, max_retries: int = 3, **params) -> Optional[Dict]:
        """Request with rate limiting"""
        params['chainid'] = 1
        params['apikey'] = self.api_key
        params['module'] = module
        params['action'] = action
        
        for attempt in range(max_retries):
            try:
                time.sleep(0.25)
                response = self.session.get(self.base_url, params=params, timeout=15)
                data = response.json()
                
                if data.get('status') == '1':
                    return data.get('result')
                elif 'rate limit' in str(data.get('message', '')).lower():
                    if attempt < max_retries - 1:
                        wait_time = 2 ** (attempt + 1)
                        print(f"   ⏳ Waiting {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                return None
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return None
        return None
    
    def get_eth_price(self) -> float:
        """Get ETH and BTC prices"""
        result = self._request('stats', 'ethprice')
        if result:
            self.eth_price = float(result.get('ethusd', 0))
            self.token_prices['BTC'] = float(result.get('btcusd', 67000))
            return self.eth_price
        return self.eth_price
    
    def get_token_transfers(self, address: str, limit: int = 10) -> List[Dict]:
        """Get all ERC-20 transfers for an address"""
        return self._request('account', 'tokentx', 
                            address=address, 
                            page=1, 
                            offset=limit, 
                            sort='desc') or []
    
    def get_eth_transfers(self, address: str, limit: int = 5) -> List[Dict]:
        """Get ETH transfers"""
        return self._request('account', 'txlist',
                            address=address,
                            startblock=0,
                            endblock=99999999,
                            page=1,
                            offset=limit,
                            sort='desc') or []
    
    def analyze_transfer(self, transfer: Dict, symbol: str) -> Optional[Dict]:
        """Analyze a transfer for whale signals"""
        # Get token info
        if symbol == 'ETH':
            decimals = 18
            price = self.eth_price
        else:
            token_info = TOP_10_TOKENS.get(symbol)
            if not token_info:
                return None
            decimals = token_info['decimals']
            price = self.token_prices.get(symbol, 1)
        
        # Calculate values
        value_raw = int(transfer.get('value', 0))
        value_token = value_raw / (10 ** decimals)
        value_usd = value_token * price
        
        # Skip if below threshold
        if value_usd < WHALE_THRESHOLD_USD:
            return None
        
        from_addr = transfer.get('from', '')
        to_addr = transfer.get('to', '')
        
        from_label = WHALE_WALLETS.get(from_addr)
        to_label = WHALE_WALLETS.get(to_addr)
        
        # Exchange detection
        exchange_keywords = ['binance', 'coinbase', 'kraken', 'bitfinex']
        from_exchange = any(k in (from_label or '').lower() for k in exchange_keywords)
        to_exchange = any(k in (to_label or '').lower() for k in exchange_keywords)
        
        # Signal
        signal = 'NEUTRAL'
        if to_exchange:
            signal = 'BEARISH'  # To exchange
        elif from_exchange:
            signal = 'BULLISH'  # From exchange
        elif value_usd > WHALE_THRESHOLD_USD * 5:
            signal = 'MAJOR'
        
        return {
            'symbol': symbol,
            'value_token': value_token,
            'value_usd': value_usd,
            'from': from_addr,
            'from_label': from_label,
            'to': to_addr,
            'to_label': to_label,
            'from_exchange': from_exchange,
            'to_exchange': to_exchange,
            'signal': signal,
            'tx_hash': transfer.get('hash', ''),
            'block': transfer.get('blockNumber', ''),
            'timestamp': int(transfer.get('timeStamp', 0)),
        }
    
    def scan_wallet(self, address: str, label: str) -> List[Dict]:
        """Scan wallet for ETH + top 10 token transfers"""
        signals = []
        
        # ETH transfers
        eth_txs = self.get_eth_transfers(address, limit=2)
        for tx in eth_txs[:1]:
            if int(tx.get('value', 0)) > 0:
                analysis = self.analyze_transfer(tx, 'ETH')
                if analysis:
                    signals.append(analysis)
        
        # ERC-20 transfers (all at once, filter by TOP_10)
        token_txs = self.get_token_transfers(address, limit=15)
        
        for tx in token_txs[:10]:
            symbol = tx.get('tokenSymbol', '')
            if symbol in TOP_10_TOKENS:
                analysis = self.analyze_transfer(tx, symbol)
                if analysis:
                    signals.append(analysis)
        
        return signals
    
    def scan_all_whales(self) -> List[Dict]:
        """Scan all whale wallets"""
        print(f"\n🔍 Scanning TOP 10 TOKENS (ex-stablecoins)")
        print(f"   Tokens: {', '.join(TOP_10_TOKENS.keys())}")
        print(f"   Wallets: {len(WHALE_WALLETS)}")
        print(f"   Threshold: ${WHALE_THRESHOLD_USD:,}+")
        print(f"   ETH: ${self.eth_price:,.2f} | BTC: ${self.token_prices['BTC']:,.0f}")
        print()
        
        all_signals = []
        
        for i, (address, label) in enumerate(WHALE_WALLETS.items(), 1):
            print(f"[{i:2d}/{len(WHALE_WALLETS)}] {label:25s}", end=" ")
            
            signals = self.scan_wallet(address, label)
            
            if signals:
                # Show largest
                largest = max(signals, key=lambda x: x['value_usd'])
                print(f"→ {largest['symbol']} ${largest['value_usd']:,.0f} ({largest['signal']})")
                all_signals.extend(signals)
            else:
                print("✓")
        
        return all_signals
    
    def generate_report(self, signals: List[Dict]) -> str:
        """Generate report"""
        if not signals:
            return "🐋 **TOP 10 WHALE REPORT**\n\nNo significant movements."
        
        # Group by token
        by_token = {}
        for s in signals:
            sym = s['symbol']
            if sym not in by_token:
                by_token[sym] = []
            by_token[sym].append(s)
        
        # Group by signal
        bearish = [s for s in signals if s['signal'] == 'BEARISH']
        bullish = [s for s in signals if s['signal'] == 'BULLISH']
        major = [s for s in signals if s['signal'] == 'MAJOR']
        
        report = [
            "🐋 **TOP 10 WHALE REPORT** (Ex-Stablecoins)",
            f"_Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
            "",
        ]
        
        # Major moves
        if major:
            report.append("## 🚨 MAJOR MOVEMENTS")
            for s in sorted(major, key=lambda x: x['value_usd'], reverse=True)[:5]:
                report.append(f"- **${s['value_usd']:,.0f}** {s['symbol']} | {s['from_label'] or s['from'][:12]}... → {s['to_label'] or s['to'][:12]}...")
            report.append("")
        
        # By token
        report.append("## 📊 BY TOKEN")
        for rank, symbol in sorted([(TOP_10_TOKENS[s]['rank'], s) for s in by_token.keys() if s in TOP_10_TOKENS]):
            token_signals = by_token[symbol]
            total = sum(s['value_usd'] for s in token_signals)
            report.append(f"\n### #{rank} {symbol} - ${total:,.0f}")
            
            for s in sorted(token_signals, key=lambda x: x['value_usd'], reverse=True)[:3]:
                emoji = {'BULLISH': '🟢', 'BEARISH': '🔴', 'MAJOR': '🚨', 'NEUTRAL': '⚪'}[s['signal']]
                report.append(f"- {emoji} ${s['value_usd']:,.0f} | {s['from_label'] or s['from'][:10]}... → {s['to_label'] or s['to'][:10]}...")
        
        # Summary
        report.append("\n## 📈 SUMMARY")
        report.append(f"- Total signals: {len(signals)}")
        report.append(f"- Bearish (to exchange): {len(bearish)}")
        report.append(f"- Bullish (from exchange): {len(bullish)}")
        report.append(f"- Major moves: {len(major)}")
        
        if bearish or bullish:
            inflow = sum(s['value_usd'] for s in bearish)
            outflow = sum(s['value_usd'] for s in bullish)
            net = outflow - inflow
            sentiment = "🟢 BULLISH" if net > 0 else "🔴 BEARISH" if net < 0 else "⚪ NEUTRAL"
            report.append(f"- Net flow: ${abs(net):,.0f} ({sentiment})")
        
        return "\n".join(report)
    
    def save_report(self, report: str, signals: List[Dict]):
        """Save reports"""
        report_dir = Path('/mnt/data/hermes/workspace/trading_system/whale_reports')
        report_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Markdown
        md_path = report_dir / f'top10_whale_{timestamp}.md'
        with open(md_path, 'w') as f:
            f.write(report)
        
        # JSON
        json_path = report_dir / f'top10_whale_{timestamp}.json'
        with open(json_path, 'w') as f:
            json.dump({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'signals': signals,
            }, f, indent=2, default=str)
        
        print(f"\n💾 Saved: {md_path.name}")


def main():
    print("="*80)
    print("TOP 10 WHALE TRACKER (Ex-Stablecoins)")
    print("="*80)
    
    tracker = Top10WhaleTracker()
    
    # Get prices
    print("\n📊 Fetching prices...")
    tracker.get_eth_price()
    print(f"   BTC: ${tracker.token_prices['BTC']:,.0f}")
    print(f"   ETH: ${tracker.eth_price:,.2f}")
    
    # Scan
    signals = tracker.scan_all_whales()
    
    # Report
    print("\n" + "="*80)
    report = tracker.generate_report(signals)
    print(report)
    
    # Save
    tracker.save_report(report, signals)
    print("="*80)
    
    return signals


if __name__ == '__main__':
    main()
