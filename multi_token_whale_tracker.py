#!/usr/bin/env python3
"""
Multi-Token Whale Tracker - Etherscan V2 API

Tracks whale movements across ETH + major ERC-20 tokens:
- USDT, USDC (stablecoins - exchange flows)
- WBTC (wrapped Bitcoin)
- LINK, UNI, and other major DeFi tokens

Generates alerts for movements >$1M threshold.
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

# Token contracts to monitor
TOKENS = {
    'USDT': {
        'contract': '0xdac17f958d2ee523a2206206994597c13d831ec7',
        'decimals': 6,
        'name': 'Tether USD',
        'price_source': 'usd',  # Stablecoin
    },
    'USDC': {
        'contract': '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',
        'decimals': 6,
        'name': 'USD Coin',
        'price_source': 'usd',
    },
    'WBTC': {
        'contract': '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599',
        'decimals': 8,
        'name': 'Wrapped BTC',
        'price_source': 'btc',
    },
    'LINK': {
        'contract': '0x514910771af9ca656af840dff83e8264ecf986ca',
        'decimals': 18,
        'name': 'Chainlink',
        'price_source': 'link',
    },
    'UNI': {
        'contract': '0x1f9840a85d5af5bf1d1762f925bdaddc4201f984',
        'decimals': 18,
        'name': 'Uniswap',
        'price_source': 'uni',
    },
    'PEPE': {
        'contract': '0x6982508145454ce325ddbe47a25d4ec3d2311933',
        'decimals': 18,
        'name': 'Pepe',
        'price_source': 'pepe',
    },
    'SHIB': {
        'contract': '0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce',
        'decimals': 18,
        'name': 'Shiba Inu',
        'price_source': 'shib',
    },
}

# Known whale wallets (exchanges, institutions, individuals)
WHALE_WALLETS = {
    # Binance (largest exchange)
    "0xF977814e90dA44bFA03b6295A0616a897441aceC": "Binance 8 (Top Whale)",
    "0x47ac0Fb4F2D84898e4D9E7b4DaB3C24507a6D503": "Binance Cold Wallet",
    "0x28C6c06298d514Db089934071355E5743bf21d60": "Binance 14",
    "0x21a31Ee1afC51d94C2eFcCAa2092aD1028285549": "Binance 15",
    "0xDFd5293D8e347dFe59E90eFd55b2956a1343963d": "Binance 16",
    "0x56Eddb7aa87536c09CCc2793473599fD21A8b17F": "Binance 17",
    "0x9696f59E4d72E237BE84fFD425DCaD154Bf96976": "Binance 18",
    "0x4D9A95c7Ca9088665D22DD5a55a7A38a1C7f4055": "Binance 19",
    "0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8": "Binance 7",
    
    # Coinbase
    "0xA9D1e08C7793af67e9d92fe308d5697FB81d3E43": "Coinbase 1",
    "0x503828976D22510aad0201ac7EC88293211D23Da": "Coinbase 2",
    "0xa910f92ACdAf488fa6eF02174fb86208Ad7722ba": "Coinbase 3",
    
    # Kraken
    "0x2910543Af39abA0Cd09dBb2D50200b3E800A63D2": "Kraken 1",
    "0x5A52E96BAcdaBb82fd05763E25335261B270Efcb": "Kraken 2",
    
    # Bitfinex
    "0x742d35Cc6634C0532925a3b844Bc454e4438f44e": "Bitfinex",
    
    # Bridges
    "0x0716a17FBAeE714f1E6aB0f9d59edbC5f09815C0": "Arbitrum Bridge",
    "0x8315177aB297bA92A06054cE80a67Ed4DBd7ed3a": "Optimism Bridge",
    "0x40ec5B33f54e0E8A33A975908C5BA1c14e5BbbDf": "Polygon Bridge",
    
    # Vitalik
    "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045": "Vitalik Buterin",
}

# Approximate token prices (USD) - would fetch from API in production
TOKEN_PRICES = {
    'BTC': 67000,
    'ETH': 1830,
    'LINK': 10,
    'UNI': 6,
    'PEPE': 0.000008,
    'SHIB': 0.000012,
}


class MultiTokenWhaleTracker:
    """Track whale movements across ETH + ERC-20 tokens"""
    
    def __init__(self, api_key: str = API_KEY):
        self.api_key = api_key
        self.session = requests.Session()
        self.base_url = BASE_URL
        self.eth_price = 0
        self.token_prices = TOKEN_PRICES.copy()
    
    def _request(self, module: str, action: str, max_retries: int = 3, **params) -> Optional[Dict]:
        """Make request with rate limiting and retry logic"""
        params['chainid'] = 1
        params['apikey'] = self.api_key
        params['module'] = module
        params['action'] = action
        
        for attempt in range(max_retries):
            try:
                time.sleep(0.25)  # Rate limit: 5 calls/sec
                response = self.session.get(self.base_url, params=params, timeout=15)
                data = response.json()
                
                if data.get('status') == '1':
                    return data.get('result')
                elif data.get('status') == '0':
                    error_msg = data.get('message', '')
                    if 'rate limit' in error_msg.lower() or 'NOTOK' in error_msg:
                        if attempt < max_retries - 1:
                            wait_time = 2 ** (attempt + 1)
                            print(f"   ⏳ Rate limited - waiting {wait_time}s...")
                            time.sleep(wait_time)
                            continue
                        return None
                    return None
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                print(f"   ❌ Error: {e}")
                return None
        
        return None
    
    def get_eth_price(self) -> float:
        """Get current ETH price"""
        result = self._request('stats', 'ethprice')
        if result:
            self.eth_price = float(result.get('ethusd', 0))
            # Also get BTC price
            btc_price = float(result.get('btcusd', 0))
            self.token_prices['BTC'] = btc_price
            return self.eth_price
        return self.eth_price
    
    def get_eth_transfers(self, address: str, limit: int = 5) -> List[Dict]:
        """Get ETH transfers for an address"""
        return self._request('account', 'txlist', address=address, startblock=0, 
                            endblock=99999999, page=1, offset=limit, sort='desc') or []
    
    def get_token_transfers(self, address: str, contract: str = None, limit: int = 5) -> List[Dict]:
        """Get ERC-20 token transfers for an address"""
        params = {
            'address': address,
            'page': 1,
            'offset': limit,
            'sort': 'desc',
        }
        if contract:
            params['contractaddress'] = contract
        
        return self._request('account', 'tokentx', **params) or []
    
    def calculate_usd_value(self, symbol: str, amount: float) -> float:
        """Calculate USD value for a token amount"""
        if symbol in ['USDT', 'USDC']:
            return amount
        elif symbol == 'WBTC':
            return amount * self.token_prices.get('BTC', 67000)
        elif symbol == 'ETH':
            return amount * self.eth_price
        else:
            return amount * self.token_prices.get(symbol.upper(), 1)
    
    def analyze_transfer(self, transfer: Dict, symbol: str = 'ETH') -> Dict:
        """Analyze a single transfer for whale signals"""
        # Get token info
        if symbol == 'ETH':
            decimals = 18
        else:
            decimals = TOKENS.get(symbol, {}).get('decimals', 18)
        
        # Parse transfer data
        value_raw = int(transfer.get('value', 0))
        value_token = value_raw / (10 ** decimals)
        value_usd = self.calculate_usd_value(symbol, value_token)
        
        from_addr = transfer.get('from', '')
        to_addr = transfer.get('to', '')
        
        # Get labels
        from_label = WHALE_WALLETS.get(from_addr, None)
        to_label = WHALE_WALLETS.get(to_addr, None)
        
        # Determine if exchange-related
        exchange_keywords = ['binance', 'coinbase', 'kraken', 'bitfinex', 'exchange']
        from_exchange = any(k in (from_label or '').lower() for k in exchange_keywords)
        to_exchange = any(k in (to_label or '').lower() for k in exchange_keywords)
        
        # Determine signal
        signal = 'NEUTRAL'
        if to_exchange and value_usd > WHALE_THRESHOLD_USD:
            signal = 'BEARISH'  # To exchange = potential sell
        elif from_exchange and value_usd > WHALE_THRESHOLD_USD:
            signal = 'BULLISH'  # From exchange = accumulation
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
        """Scan a single wallet for ETH + token transfers"""
        signals = []
        
        # Get ETH transfers
        eth_transfers = self.get_eth_transfers(address, limit=2)
        for tx in eth_transfers[:1]:
            if int(tx.get('value', 0)) > 0:
                analysis = self.analyze_transfer(tx, 'ETH')
                if analysis['value_usd'] > WHALE_THRESHOLD_USD:
                    signals.append(analysis)
        
        # Get token transfers (all tokens at once - no contract filter)
        token_transfers = self.get_token_transfers(address, limit=10)
        
        for tx in token_transfers[:5]:
            symbol = tx.get('tokenSymbol', 'UNKNOWN')
            if symbol in TOKENS or symbol == 'ETH':
                analysis = self.analyze_transfer(tx, symbol)
                if analysis['value_usd'] > WHALE_THRESHOLD_USD:
                    signals.append(analysis)
        
        return signals
    
    def scan_all_whales(self) -> List[Dict]:
        """Scan all whale wallets"""
        print(f"\n🔍 Scanning {len(WHALE_WALLETS)} whale wallets...")
        print(f"   Threshold: ${WHALE_THRESHOLD_USD:,}+")
        print(f"   ETH Price: ${self.eth_price:,.2f}")
        print(f"   BTC Price: ${self.token_prices.get('BTC', 67000):,}")
        print()
        
        all_signals = []
        
        for i, (address, label) in enumerate(WHALE_WALLETS.items(), 1):
            print(f"[{i:2d}/{len(WHALE_WALLETS)}] {label[:40]:40s}", end=" ")
            
            signals = self.scan_wallet(address, label)
            
            if signals:
                # Show largest signal
                largest = max(signals, key=lambda x: x['value_usd'])
                print(f"→ {largest['symbol']} ${largest['value_usd']:,.0f} ({largest['signal']})")
                all_signals.extend(signals)
            else:
                print("✓")
        
        return all_signals
    
    def generate_report(self, signals: List[Dict]) -> str:
        """Generate comprehensive whale tracking report"""
        if not signals:
            return "🐋 **MULTI-TOKEN WHALE REPORT**\n\nNo significant movements detected."
        
        # Group by signal type
        bearish = [s for s in signals if s['signal'] == 'BEARISH']
        bullish = [s for s in signals if s['signal'] == 'BULLISH']
        major = [s for s in signals if s['signal'] == 'MAJOR']
        
        # Group by token
        by_token = {}
        for s in signals:
            symbol = s['symbol']
            if symbol not in by_token:
                by_token[symbol] = []
            by_token[symbol].append(s)
        
        report = [
            "🐋 **MULTI-TOKEN WHALE REPORT**",
            f"_Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
            "",
        ]
        
        # Major moves first
        if major:
            report.append("## 🚨 MAJOR MOVEMENTS (>$5M)")
            for s in sorted(major, key=lambda x: x['value_usd'], reverse=True)[:5]:
                from_name = s['from_label'] or s['from'][:12]
                to_name = s['to_label'] or s['to'][:12]
                report.append(f"- **${s['value_usd']:,.0f}** {s['symbol']} | {from_name}... → {to_name}...")
            report.append("")
        
        # By token
        report.append("## 📊 BY TOKEN")
        for symbol in sorted(by_token.keys()):
            token_signals = by_token[symbol]
            total_value = sum(s['value_usd'] for s in token_signals)
            report.append(f"\n### {symbol}")
            report.append(f"**Total Volume:** ${total_value:,.0f} | **Transactions:** {len(token_signals)}")
            
            for s in sorted(token_signals, key=lambda x: x['value_usd'], reverse=True)[:3]:
                signal_emoji = {'BULLISH': '🟢', 'BEARISH': '🔴', 'MAJOR': '🚨', 'NEUTRAL': '⚪'}[s['signal']]
                from_name = s['from_label'] or s['from'][:10]
                to_name = s['to_label'] or s['to'][:10]
                report.append(f"- {signal_emoji} ${s['value_usd']:,.0f} | {from_name}... → {to_name}...")
        
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
            report.append(f"- Net exchange flow: ${abs(net):,.0f} ({sentiment})")
        
        return "\n".join(report)
    
    def save_report(self, report: str, signals: List[Dict]):
        """Save report to file"""
        report_dir = Path('/mnt/data/hermes/workspace/trading_system/whale_reports')
        report_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save markdown report
        md_path = report_dir / f'whale_report_{timestamp}.md'
        with open(md_path, 'w') as f:
            f.write(report)
        
        # Save JSON data
        json_path = report_dir / f'whale_data_{timestamp}.json'
        with open(json_path, 'w') as f:
            json.dump({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'eth_price': self.eth_price,
                'signals': signals,
            }, f, indent=2, default=str)
        
        print(f"\n💾 Reports saved:")
        print(f"   {md_path}")
        print(f"   {json_path}")


def main():
    """Run multi-token whale scan"""
    print("="*80)
    print("MULTI-TOKEN WHALE TRACKER - LIVE SCAN")
    print("="*80)
    
    tracker = MultiTokenWhaleTracker()
    
    # Get prices
    print("\n📊 Fetching prices...")
    eth_price = tracker.get_eth_price()
    print(f"   ETH: ${tracker.eth_price:,.2f}")
    print(f"   BTC: ${tracker.token_prices['BTC']:,.2f}")
    
    # Scan all whales
    signals = tracker.scan_all_whales()
    
    # Filter to significant signals only
    significant = [s for s in signals if s['value_usd'] > WHALE_THRESHOLD_USD]
    
    # Generate report
    print("\n" + "="*80)
    report = tracker.generate_report(significant)
    print(report)
    
    # Save
    tracker.save_report(report, significant)
    
    print("="*80)
    
    return significant


if __name__ == '__main__':
    signals = main()
    print(f"\n🎯 Total significant movements: {len(signals)}")
