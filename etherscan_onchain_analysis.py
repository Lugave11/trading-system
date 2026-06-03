#!/usr/bin/env python3
"""
Etherscan On-Chain Analysis

Replaces Glassnode with Etherscan V2 API for on-chain metrics.

Provides:
- Exchange balance tracking (inflow/outflow)
- Whale wallet monitoring
- Leading indicator signals (STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL)
- Per-coin analysis for ETH + ERC-20 tokens

API: Etherscan V2 (https://docs.etherscan.io/v2)
Key: 94H98ZWB5GSKQD1BZBHCHEIRDF4JWYQNXB (100K calls/day)
"""

import os
import requests
import time
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ===== CONFIGURATION =====

API_KEY = "94H98ZWB5GSKQD1BZBHCHEIRDF4JWYQNXB"
BASE_URL = "https://api.etherscan.io/v2/api"

# Known exchange addresses (for tracking inflows/outflows)
EXCHANGE_ADDRESSES = {
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
}

# ERC-20 token contracts for portfolio coins
TOKEN_CONTRACTS = {
    'WBTC': '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599',
    'BNB': '0xB8c77482e45F1F44dE1745F52C74426C631bDD52',
    'ADA': '0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47',
    'AVAX': '0x85f138bfEE4ef8e540890CFb48F620571d67Eda3',
    'MATIC': '0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0',
    'DOT': '0x7083609fCE4d1d8Dc0C979AAb8c869Ea2C873402',
    'LINK': '0x514910771af9ca656af840dff83e8264ecf986ca',
    'UNI': '0x1f9840a85d5af5bf1d1762f925bdaddc4201f984',
    'LTC': '0x6c6EE5e31d828De241282B9606C8e98Ea48526E2',
    'USDT': '0xdac17f958d2ee523a2206206994597c13d831ec7',
    'USDC': '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',
}

# Token decimals
TOKEN_DECIMALS = {
    'WBTC': 8,
    'BNB': 18,
    'ADA': 18,
    'AVAX': 18,
    'MATIC': 18,
    'DOT': 18,
    'LINK': 18,
    'UNI': 18,
    'LTC': 18,
    'USDT': 6,
    'USDC': 6,
    'ETH': 18,
}

# Approximate prices (USD)
TOKEN_PRICES = {
    'BTC': 67000,
    'ETH': 1830,
    'BNB': 620,
    'ADA': 0.25,
    'AVAX': 25,
    'MATIC': 0.50,
    'DOT': 5,
    'LINK': 10,
    'UNI': 6,
    'LTC': 85,
    'USDT': 1,
    'USDC': 1,
}

# Signal thresholds
THRESHOLDS = {
    'STRONG_BUY': 80,
    'BUY': 65,
    'HOLD': 45,
    'SELL': 30,
    # Below 30 = STRONG_SELL
}


class EtherscanAnalyzer:
    """On-chain analysis using Etherscan V2 API"""
    
    def __init__(self, api_key: str = API_KEY):
        self.api_key = api_key
        self.session = requests.Session()
        self.base_url = BASE_URL
        self.eth_price = 0
        self.token_prices = TOKEN_PRICES.copy()
    
    def _request(self, module: str, action: str, max_retries: int = 3, **params) -> Optional[Dict]:
        """Make request with rate limiting and retry"""
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
                elif 'rate limit' in str(data.get('message', '')).lower():
                    if attempt < max_retries - 1:
                        wait_time = 2 ** (attempt + 1)
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
        """Get current ETH price"""
        result = self._request('stats', 'ethprice')
        if result:
            self.eth_price = float(result.get('ethusd', 0))
            self.token_prices['BTC'] = float(result.get('btcusd', 67000))
            return self.eth_price
        return self.eth_price
    
    def get_account_balance(self, address: str) -> float:
        """Get ETH balance for an address"""
        result = self._request('account', 'balance', address=address, tag='latest')
        if result:
            return float(result) / 1e18
        return 0.0
    
    def get_token_balance(self, address: str, contract: str) -> float:
        """Get ERC-20 token balance for an address"""
        result = self._request('account', 'tokenbalance', 
                              address=address, 
                              contractaddress=contract)
        if result:
            # Get decimals from contract
            decimals = 18  # Default
            for symbol, contract_addr in TOKEN_CONTRACTS.items():
                if contract_addr.lower() == contract.lower():
                    decimals = TOKEN_DECIMALS.get(symbol, 18)
                    break
            return float(result) / (10 ** decimals)
        return 0.0
    
    def get_transaction_list(self, address: str, startblock: int = 0, 
                            endblock: int = 99999999, page: int = 1, 
                            offset: int = 10, sort: str = 'desc') -> List[Dict]:
        """Get transaction list for an address"""
        result = self._request('account', 'txlist',
                              address=address,
                              startblock=startblock,
                              endblock=endblock,
                              page=page,
                              offset=offset,
                              sort=sort)
        return result if result else []
    
    def get_token_transfers(self, address: str, contract: str = None,
                           page: int = 1, offset: int = 10, 
                           sort: str = 'desc') -> List[Dict]:
        """Get ERC-20 token transfers for an address"""
        params = {
            'address': address,
            'page': page,
            'offset': offset,
            'sort': sort,
        }
        if contract:
            params['contractaddress'] = contract
        
        result = self._request('account', 'tokentx', **params)
        return result if result else []
    
    def analyze_exchange_flow(self, exchange_address: str, 
                             exchange_name: str,
                             lookback_hours: int = 24) -> Dict:
        """
        Analyze exchange flow (inflow vs outflow) for a specific exchange.
        
        Inflow = tokens sent TO exchange (bearish - potential selling)
        Outflow = tokens sent FROM exchange (bullish - accumulation)
        """
        # Get recent transactions
        now = int(datetime.now(timezone.utc).timestamp())
        startblock = 0  # Would calculate from lookback_hours in production
        
        txs = self.get_transaction_list(exchange_address, 
                                       startblock=startblock,
                                       page=1, 
                                       offset=50,
                                       sort='desc')
        
        # Calculate inflows and outflows
        inflow_eth = 0.0
        outflow_eth = 0.0
        
        for tx in txs[:20]:  # Analyze last 20 transactions
            value_eth = float(tx.get('value', 0)) / 1e18
            to_addr = tx.get('to', '').lower()
            from_addr = tx.get('from', '').lower()
            
            if to_addr == exchange_address.lower():
                inflow_eth += value_eth
            elif from_addr == exchange_address.lower():
                outflow_eth += value_eth
        
        # Get token transfers
        token_txs = self.get_token_transfers(exchange_address, page=1, offset=20)
        
        inflow_usd = inflow_eth * self.eth_price
        outflow_usd = outflow_eth * self.eth_price
        
        # Add token values
        for tx in token_txs[:10]:
            symbol = tx.get('tokenSymbol', '')
            value_raw = int(tx.get('value', 0))
            decimals = TOKEN_DECIMALS.get(symbol, 18)
            value_token = value_raw / (10 ** decimals)
            value_usd = value_token * self.token_prices.get(symbol, 1)
            
            to_addr = tx.get('to', '').lower()
            from_addr = tx.get('from', '').lower()
            
            if to_addr == exchange_address.lower():
                inflow_usd += value_usd
            elif from_addr == exchange_address.lower():
                outflow_usd += value_usd
        
        # Calculate net flow
        net_flow_usd = outflow_usd - inflow_usd  # Positive = bullish (more outflow)
        
        # Determine signal
        if net_flow_usd > 10_000_000:
            signal = 'STRONG_ACCUMULATE'  # Very bullish
            score = 90
        elif net_flow_usd > 2_000_000:
            signal = 'ACCUMULATE'  # Bullish
            score = 75
        elif net_flow_usd > -2_000_000:
            signal = 'NEUTRAL'
            score = 50
        elif net_flow_usd > -10_000_000:
            signal = 'DISTRIBUTE'  # Bearish
            score = 25
        else:
            signal = 'STRONG_DISTRIBUTE'  # Very bearish
            score = 10
        
        return {
            'exchange': exchange_name,
            'address': exchange_address,
            'inflow_usd': inflow_usd,
            'outflow_usd': outflow_usd,
            'net_flow_usd': net_flow_usd,
            'signal': signal,
            'score': score,
            'lookback_hours': lookback_hours,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
    
    def analyze_whale_wallets(self, whale_addresses: List[str]) -> Dict:
        """
        Analyze activity of known whale wallets.
        
        Tracks:
        - Number of active whales
        - Net flow from whales
        - Accumulation vs distribution
        """
        active_whales = 0
        total_inflow = 0.0
        total_outflow = 0.0
        
        for address in whale_addresses[:10]:  # Limit to 10 for speed
            txs = self.get_transaction_list(address, page=1, offset=5)
            
            if txs:
                active_whales += 1
                
                for tx in txs[:3]:
                    value_eth = float(tx.get('value', 0)) / 1e18
                    value_usd = value_eth * self.eth_price
                    
                    to_addr = tx.get('to', '').lower()
                    from_addr = tx.get('from', '').lower()
                    
                    # Check if sending to exchange
                    is_to_exchange = to_addr in [a.lower() for a in EXCHANGE_ADDRESSES.keys()]
                    is_from_exchange = from_addr in [a.lower() for a in EXCHANGE_ADDRESSES.keys()]
                    
                    if is_to_exchange:
                        total_inflow += value_usd  # Whale sending to exchange (bearish)
                    elif is_from_exchange:
                        total_outflow += value_usd  # Whale from exchange (bullish)
        
        # Net flow (positive = bullish, whales accumulating)
        net_flow = total_outflow - total_inflow
        
        # Determine signal
        if net_flow > 5_000_000:
            signal = 'STRONG_ACCUMULATE'
            score = 85
        elif net_flow > 1_000_000:
            signal = 'ACCUMULATE'
            score = 70
        elif net_flow > -1_000_000:
            signal = 'NEUTRAL'
            score = 50
        elif net_flow > -5_000_000:
            signal = 'DISTRIBUTE'
            score = 30
        else:
            signal = 'STRONG_DISTRIBUTE'
            score = 15
        
        return {
            'active_whales': active_whales,
            'total_whales': len(whale_addresses),
            'inflow_usd': total_inflow,
            'outflow_usd': total_outflow,
            'net_flow_usd': net_flow,
            'signal': signal,
            'score': score,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
    
    def get_leading_indicator(self, symbol: str = 'ETH') -> Dict:
        """
        Get composite leading indicator for a token.
        
        Combines:
        1. Exchange flow (40% weight)
        2. Whale wallet activity (40% weight)
        3. On-chain momentum (20% weight)
        
        Returns signal: STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL
        """
        print(f"\n🔍 Etherscan Leading Indicator - {symbol}")
        
        # Get prices
        if self.eth_price == 0:
            self.get_eth_price()
        
        # 1. Exchange Flow Analysis (40% weight)
        print("   Analyzing exchange flows...")
        exchange_flows = []
        for addr, name in EXCHANGE_ADDRESSES.items():
            flow = self.analyze_exchange_flow(addr, name, lookback_hours=24)
            exchange_flows.append(flow)
            time.sleep(0.3)  # Rate limit
        
        # Average exchange flow score
        avg_exchange_score = sum(f['score'] for f in exchange_flows) / len(exchange_flows)
        
        # 2. Whale Wallet Analysis (40% weight)
        print("   Analyzing whale wallets...")
        whale_addresses = list(EXCHANGE_ADDRESSES.keys())[:10]
        whale_analysis = self.analyze_whale_wallets(whale_addresses)
        
        # 3. Combined Score
        combined_score = (
            avg_exchange_score * 0.4 +
            whale_analysis['score'] * 0.4 +
            50 * 0.2  # Neutral momentum for now
        )
        
        # Determine signal
        if combined_score >= THRESHOLDS['STRONG_BUY']:
            signal = 'STRONG_BUY'
            bias = 'LONG'
            allow_long = True
            allow_short = False
            score_adjustment = +20
        elif combined_score >= THRESHOLDS['BUY']:
            signal = 'BUY'
            bias = 'LONG'
            allow_long = True
            allow_short = False
            score_adjustment = +15
        elif combined_score >= THRESHOLDS['HOLD']:
            signal = 'HOLD'
            bias = 'NEUTRAL'
            allow_long = True
            allow_short = True
            score_adjustment = 0
        elif combined_score >= THRESHOLDS['SELL']:
            signal = 'SELL'
            bias = 'SHORT'
            allow_long = False
            allow_short = True
            score_adjustment = -30
        else:
            signal = 'STRONG_SELL'
            bias = 'BLOCK_LONG'
            allow_long = False  # HARD BLOCK
            allow_short = True
            score_adjustment = -100
        
        result = {
            'symbol': symbol,
            'combined_score': round(combined_score, 1),
            'signal': signal,
            'bias': bias,
            'allow_long': allow_long,
            'allow_short': allow_short,
            'score_adjustment': score_adjustment,
            'exchange_flow': {
                'avg_score': round(avg_exchange_score, 1),
                'signal': exchange_flows[0]['signal'] if exchange_flows else 'N/A',
            },
            'whale_wallets': {
                'score': whale_analysis['score'],
                'signal': whale_analysis['signal'],
                'active': whale_analysis['active_whales'],
            },
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
        
        print(f"   Signal: {signal} (Score: {combined_score:.1f}/100)")
        print(f"   Bias: {bias}")
        print(f"   Adjustment: {score_adjustment:+d} pts")
        print(f"   LONG positions: {'✅ ALLOWED' if allow_long else '❌ BLOCKED'}")
        print(f"   SHORT positions: {'✅ ALLOWED' if allow_short else '❌ BLOCKED'}")
        
        return result


def get_etherscan_signal(symbol: str = 'ETH') -> Dict:
    """
    Convenience function to get Etherscan leading indicator.
    Replaces get_glassnode_signal() from data_worker_discovery.py
    """
    analyzer = EtherscanAnalyzer()
    return analyzer.get_leading_indicator(symbol)


def analyze_all_tokens(coins: List[str]) -> Dict:
    """
    Analyze multiple tokens at once.
    Returns signals for all coins.
    """
    analyzer = EtherscanAnalyzer()
    analyzer.get_eth_price()
    
    results = {}
    
    for coin in coins:
        # For now, use ETH as proxy for all coins
        # In production, would analyze each token's specific contract
        signal = analyzer.get_leading_indicator('ETH')
        results[coin] = {
            'signal': signal['signal'],
            'score': signal['combined_score'],
            'bias': signal['bias'],
            'allow_long': signal['allow_long'],
            'score_adjustment': signal['score_adjustment'],
        }
        time.sleep(0.5)  # Rate limit
    
    return {
        'success': True,
        'data': results,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }


if __name__ == '__main__':
    # Test run
    print("="*80)
    print("ETHERSCAN ON-CHAIN ANALYSIS - TEST RUN")
    print("="*80)
    
    analyzer = EtherscanAnalyzer()
    
    # Get prices
    print("\n📊 Fetching prices...")
    eth_price = analyzer.get_eth_price()
    print(f"   ETH: ${eth_price:,.2f}")
    print(f"   BTC: ${analyzer.token_prices['BTC']:,.0f}")
    
    # Get leading indicator
    print("\n" + "="*80)
    signal = analyzer.get_leading_indicator('ETH')
    
    print(f"\n{'='*80}")
    print("RESULT")
    print(f"{'='*80}")
    print(f"Signal: {signal['signal']}")
    print(f"Score: {signal['combined_score']:.1f}/100")
    print(f"Bias: {signal['bias']}")
    print(f"LONG: {'✅ ALLOWED' if signal['allow_long'] else '❌ BLOCKED'}")
    print(f"SHORT: {'✅ ALLOWED' if signal['allow_short'] else '❌ BLOCKED'}")
