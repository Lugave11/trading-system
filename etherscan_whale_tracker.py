#!/usr/bin/env python3
"""
Etherscan V2 API - Whale Tracking Module

Tracks whale wallets, large transactions, and exchange flows.
Uses authenticated API key from .env

Docs: https://docs.etherscan.io/introduction
"""

import os
import requests
import time
from datetime import datetime, timezone
from typing import List, Dict, Optional
from pathlib import Path

# Load API key from .env
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

# Known whale wallets to monitor (mix of institutions, funds, individuals)
WHALE_WALLETS = {
    "0x47ac0Fb4F2D84898e4D9E7b4DaB3C24507a6D503": "Binance Cold Wallet",
    "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045": "Vitalik Buterin",
    "0x28C6c06298d514Db089934071355E5743bf21d60": "Binance 14",
    "0x21a31Ee1afC51d94C2eFcCAa2092aD1028285549": "Binance 15",
    "0xDFd5293D8e347dFe59E90eFd55b2956a1343963d": "Binance 16",
    "0x56Eddb7aa87536c09CCc2793473599fD21A8b17F": "Binance 17",
    "0x9696f59E4d72E237BE84fFD425DCaD154Bf96976": "Binance 18",
    "0x4D9A95c7Ca9088665D22DD5a55a7A38a1C7f4055": "Binance 19",
    "0x2910543Af39abA0Cd09dBb2D50200b3E800A63D2": "Kraken 1",
    "0x5A52E96BAcdaBb82fd05763E25335261B270Efcb": "Kraken 2",
    "0x0716a17FBAeE714f1E6aB0f9d59edbC5f09815C0": "Arbitrum Bridge",
    "0x8315177aB297bA92A06054cE80a67Ed4DBd7ed3a": "Bridge: Optimism",
    "0x40ec5B33f54e0E8A33A975908C5BA1c14e5BbbDf": "Polygon Bridge",
    "0x8EB8a3b98659Cce290402893d0123abb75E3ab28": "Avalanche Bridge",
    "0xA9D1e08C7793af67e9d92fe308d5697FB81d3E43": "Coinbase 1",
    "0x503828976D22510aad0201ac7EC88293211D23Da": "Coinbase 2",
    "0xa910f92ACdAf488fa6eF02174fb86208Ad7722ba": "Coinbase 3",
    "0x742d35Cc6634C0532925a3b844Bc454e4438f44e": "Bitfinex",
    "0xF977814e90dA44bFA03b6295A0616a897441aceC": "Binance 8 (Top Whale)",
    "0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8": "Binance 7",
}

# USDT contract (for stablecoin whale tracking)
USDT_CONTRACT = "0xdac17f958d2ee523a2206206994597c13d831ec7"
USDC_CONTRACT = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"

# Whale threshold (in USD)
WHALE_THRESHOLD_USD = 1_000_000  # $1M+


class EtherscanWhaleTracker:
    """Track whale movements using Etherscan V2 API"""
    
    def __init__(self, api_key: str = API_KEY):
        self.api_key = api_key
        self.session = requests.Session()
        self.base_url = BASE_URL
        self.eth_price_usd = 0.0
    
    def _request(self, module: str, action: str, max_retries: int = 3, **params) -> Optional[Dict]:
        """Make authenticated request to Etherscan V2 API with rate limiting"""
        params['chainid'] = 1  # Ethereum mainnet
        params['apikey'] = self.api_key
        params['module'] = module
        params['action'] = action
        
        for attempt in range(max_retries):
            try:
                # Enforce rate limit: 5 calls/sec = 200ms between calls
                time.sleep(0.25)
                
                response = self.session.get(self.base_url, params=params, timeout=15)
                data = response.json()
                
                if data.get('status') == '1':
                    return data.get('result')
                elif data.get('status') == '0':
                    error_msg = data.get('message', 'Unknown')
                    
                    if 'rate limit' in error_msg.lower() or 'NOTOK' in error_msg:
                        if attempt < max_retries - 1:
                            wait_time = 2 ** (attempt + 1)  # Exponential backoff
                            print(f"   ⚠️  Rate limited - waiting {wait_time}s...")
                            time.sleep(wait_time)
                            continue
                        else:
                            print(f"   ❌ Rate limit exceeded after {max_retries} attempts")
                            return None
                    else:
                        # Other errors (invalid address, etc.)
                        return None
                else:
                    return None
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                print(f"   ❌ Request failed: {e}")
                return None
        
        return None
    
    def get_eth_price(self) -> float:
        """Get current ETH price in USD"""
        result = self._request('stats', 'ethprice')
        if result:
            price = float(result.get('ethusd', 0))
            self.eth_price_usd = price
            return price
        return self.eth_price_usd
    
    def get_balance(self, address: str) -> float:
        """Get ETH balance for an address (in ETH)"""
        result = self._request('account', 'balance', address=address, tag='latest')
        if result and result.isdigit():
            return int(result) / 1e18
        return 0.0
    
    def get_transactions(self, address: str, limit: int = 10) -> List[Dict]:
        """Get recent transactions for an address"""
        result = self._request(
            'account', 'txlist',
            address=address,
            startblock=0,
            endblock=99999999,
            page=1,
            offset=limit,
            sort='desc'
        )
        return result if result else []
    
    def get_token_transfers(self, address: str, contract: str = USDT_CONTRACT, limit: int = 10) -> List[Dict]:
        """Get ERC-20 token transfers for an address"""
        result = self._request(
            'account', 'tokentx',
            contractaddress=contract,
            address=address,
            page=1,
            offset=limit,
            sort='desc'
        )
        return result if result else []
    
    def get_internal_transactions(self, address: str, limit: int = 10) -> List[Dict]:
        """Get internal transactions (contract calls)"""
        result = self._request(
            'account', 'txlistinternal',
            address=address,
            startblock=0,
            endblock=99999999,
            page=1,
            offset=limit,
            sort='desc'
        )
        return result if result else []
    
    def is_exchange_address(self, address: str) -> Optional[str]:
        """Check if address belongs to a known exchange"""
        # Check against our known whale list
        if address in WHALE_WALLETS:
            label = WHALE_WALLETS[address]
            if 'Binance' in label or 'Coinbase' in label or 'Kraken' in label or 'Bitfinex' in label:
                return label
        return None
    
    def analyze_transaction(self, tx: Dict) -> Dict:
        """Analyze a single transaction for whale signals"""
        value_eth = int(tx.get('value', 0)) / 1e18
        value_usd = value_eth * self.eth_price_usd
        
        from_addr = tx.get('from', '')
        to_addr = tx.get('to', '')
        
        from_label = WHALE_WALLETS.get(from_addr, self.is_exchange_address(from_addr))
        to_label = WHALE_WALLETS.get(to_addr, self.is_exchange_address(to_addr))
        
        # Determine transaction type
        tx_type = "transfer"
        if from_label and to_label:
            tx_type = "whale_to_whale"
        elif from_label and not to_label:
            tx_type = "whale_outflow"
        elif to_label and not from_label:
            tx_type = "whale_inflow"
        
        # Check if exchange-related
        from_exchange = 'exchange' in from_label.lower() if from_label else False
        to_exchange = 'exchange' in to_label.lower() if to_label else False
        
        # Signal interpretation
        signal = "NEUTRAL"
        if to_exchange and value_usd > WHALE_THRESHOLD_USD:
            signal = "BEARISH"  # Large deposit to exchange (potential sell)
        elif from_exchange and value_usd > WHALE_THRESHOLD_USD:
            signal = "BULLISH"  # Large withdrawal from exchange (accumulation)
        elif value_usd > WHALE_THRESHOLD_USD * 5:
            signal = "MAJOR_MOVE"  # Very large transfer
        
        return {
            'hash': tx.get('hash', ''),
            'timestamp': datetime.fromtimestamp(int(tx.get('timeStamp', 0)), tz=timezone.utc),
            'from': from_addr,
            'from_label': from_label,
            'to': to_addr,
            'to_label': to_label,
            'value_eth': value_eth,
            'value_usd': value_usd,
            'type': tx_type,
            'signal': signal,
            'is_exchange_inflow': to_exchange,
            'is_exchange_outflow': from_exchange,
            'block': tx.get('blockNumber', ''),
        }
    
    def scan_whales(self, whale_addresses: Optional[List[str]] = None) -> List[Dict]:
        """Scan multiple whale wallets for recent activity"""
        if whale_addresses is None:
            whale_addresses = list(WHALE_WALLETS.keys())[:10]  # Top 10 by default
        
        print(f"\n🔍 Scanning {len(whale_addresses)} whale wallets...")
        print(f"   Threshold: ${WHALE_THRESHOLD_USD:,}+")
        print(f"   ETH Price: ${self.eth_price_usd:,.2f}")
        print()
        
        all_signals = []
        
        for i, address in enumerate(whale_addresses, 1):
            label = WHALE_WALLETS.get(address, "Unknown")
            print(f"[{i}/{len(whale_addresses)}] {label[:30]:30s} ({address[:8]}...)", end=" ")
            
            # Get recent transactions
            txs = self.get_transactions(address, limit=5)
            
            if not txs:
                print("No recent txs")
                continue
            
            # Analyze each transaction
            for tx in txs:
                analysis = self.analyze_transaction(tx)
                
                # Only keep significant movements
                if analysis['value_usd'] > WHALE_THRESHOLD_USD or analysis['signal'] != 'NEUTRAL':
                    all_signals.append(analysis)
                    print(f"→ {analysis['signal']} ${analysis['value_usd']:,.0f}")
                    break  # Only report most recent significant tx
            else:
                print("✓")
            
            # Rate limit: 5 calls/sec max
            time.sleep(0.2)
        
        return all_signals
    
    def generate_report(self, signals: List[Dict]) -> str:
        """Generate a human-readable whale tracking report"""
        if not signals:
            return "🐋 **WHALE TRACKING REPORT**\n\nNo significant whale movements detected in the last scan."
        
        report = ["🐋 **WHALE TRACKING REPORT**", f"_Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_", ""]
        
        # Group by signal type
        bearish = [s for s in signals if s['signal'] == 'BEARISH']
        bullish = [s for s in signals if s['signal'] == 'BULLISH']
        major = [s for s in signals if s['signal'] == 'MAJOR_MOVE']
        
        if major:
            report.append("## 🚨 MAJOR MOVEMENTS")
            for s in major:
                report.append(f"- **${s['value_usd']:,.0f}** | {s['from_label'] or s['from'][:10]}... → {s['to_label'] or s['to'][:10]}...")
                report.append(f"  • TX: `{s['hash'][:10]}...` | {s['timestamp'].strftime('%H:%M UTC')}")
            report.append("")
        
        if bearish:
            report.append("## 🔴 BEARISH SIGNALS (Exchange Inflows)")
            for s in bearish:
                report.append(f"- **${s['value_usd']:,.0f}** → {s['to_label'] or 'Exchange'}")
                report.append(f"  • From: {s['from_label'] or s['from'][:10]}...")
                report.append(f"  • Potential selling pressure")
            report.append("")
        
        if bullish:
            report.append("## 🟢 BULLISH SIGNALS (Exchange Outflows)")
            for s in bullish:
                report.append(f"- **${s['value_usd']:,.0f}** ← {s['from_label'] or 'Exchange'}")
                report.append(f"  • To: {s['to_label'] or s['to'][:10]}...")
                report.append(f"  • Accumulation / Cold storage")
            report.append("")
        
        # Summary
        report.append("## 📊 SUMMARY")
        report.append(f"- Total signals: {len(signals)}")
        report.append(f"- Bearish (inflows): {len(bearish)}")
        report.append(f"- Bullish (outflows): {len(bullish)}")
        report.append(f"- Major moves: {len(major)}")
        
        if bearish or bullish:
            net_flow = sum(s['value_usd'] for s in bullish) - sum(s['value_usd'] for s in bearish)
            sentiment = "🟢 BULLISH" if net_flow > 0 else "🔴 BEARISH" if net_flow < 0 else "⚪ NEUTRAL"
            report.append(f"- Net flow: ${abs(net_flow):,.0f} ({sentiment})")
        
        return "\n".join(report)


def main():
    """Run whale tracking scan"""
    print("="*80)
    print("ETHERSCAN WHALE TRACKER - LIVE SCAN")
    print("="*80)
    
    tracker = EtherscanWhaleTracker()
    
    # Get ETH price first
    print("\n📊 Fetching ETH price...")
    eth_price = tracker.get_eth_price()
    if eth_price:
        print(f"   ✅ ETH: ${eth_price:,.2f}")
    else:
        print("   ❌ Failed to get ETH price")
        return
    
    # Scan top 10 whale wallets
    top_whales = list(WHALE_WALLETS.keys())[:10]
    signals = tracker.scan_whales(top_whales)
    
    # Generate report
    print("\n" + "="*80)
    report = tracker.generate_report(signals)
    print(report)
    
    # Save report to file
    report_path = Path('/mnt/data/hermes/workspace/trading_system/whale_reports')
    report_path.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file = report_path / f'whale_report_{timestamp}.md'
    
    with open(report_file, 'w') as f:
        f.write(report)
    
    print(f"\n💾 Report saved to: {report_file}")
    print("="*80)
    
    # Return signals for Kanban integration
    return signals


if __name__ == '__main__':
    signals = main()
    
    if signals:
        print(f"\n🎯 Found {len(signals)} significant whale movements")
        
        # Example: Print the most bearish signal
        bearish = [s for s in signals if s['signal'] == 'BEARISH']
        if bearish:
            worst = max(bearish, key=lambda x: x['value_usd'])
            print(f"\n⚠️  MOST BEARISH: ${worst['value_usd']:,.0f} inflow to {worst['to_label']}")
            print(f"   This could indicate impending selling pressure!")
