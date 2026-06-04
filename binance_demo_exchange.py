#!/usr/bin/env python3
"""
Binance Demo Exchange Adapter - Unified Demo (demo.binance.com)

Supports:
- Spot Trading (BUY/SELL)
- Futures Trading (LONG/SHORT with leverage)
- Market Data (prices, OHLCV, account info)

API Docs: https://demo.binance.com/en/api-docs

Usage:
    exchange = BinanceDemoExchange(api_key, api_secret)
    
    # Spot
    balance = exchange.get_balance('USDT')
    order = exchange.place_spot_order('BTCUSDT', 'BUY', 'MARKET', quantity=0.001)
    
    # Futures
    leverage = exchange.set_leverage('BTCUSDT', 2)
    order = exchange.place_futures_order('BTCUSDT', 'BUY', 'MARKET', quantity=0.001)
"""

import hmac
import hashlib
import time
import requests
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode


class BinanceDemoExchange:
    """Binance Demo Exchange Client (demo.binance.com)"""
    
    # Unified Demo API Base URL
    BASE_URL = "https://demo.binance.com"
    
    def __init__(self, api_key: str, api_secret: str):
        """
        Initialize Binance Demo client
        
        Args:
            api_key: API Key from demo.binance.com
            api_secret: Secret Key from demo.binance.com
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = requests.Session()
        self.recv_window = 5000  # 5 seconds
        
    def _generate_signature(self, params: Dict) -> str:
        """Generate HMAC SHA256 signature"""
        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _request(self, method: str, endpoint: str, params: Dict = None, signed: bool = False) -> Dict:
        """
        Make API request to Binance Demo
        
        Args:
            method: HTTP method (GET, POST, DELETE)
            endpoint: API endpoint (e.g., '/api/v3/account')
            params: Query/body parameters
            signed: Whether to sign the request (required for trading)
        """
        url = f"{self.BASE_URL}{endpoint}"
        
        headers = {
            'X-MBX-APIKEY': self.api_key,
            'Content-Type': 'application/json'
        }
        
        if params is None:
            params = {}
        
        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['recvWindow'] = self.recv_window
            signature = self._generate_signature(params)
            params['signature'] = signature
        
        try:
            if method == 'GET':
                response = self.session.get(url, headers=headers, params=params, timeout=30)
            elif method == 'POST':
                response = self.session.post(url, headers=headers, data=params, timeout=30)
            elif method == 'DELETE':
                response = self.session.delete(url, headers=headers, params=params, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            data = response.json()
            
            # Check for errors
            if response.status_code != 200:
                raise Exception(f"Binance Demo API error {response.status_code}: {data}")
            
            if 'code' in data and isinstance(data['code'], int) and data['code'] < 0:
                error_msg = data.get('msg', 'Unknown error')
                raise Exception(f"Binance Demo error {data['code']}: {error_msg}")
            
            return data
            
        except requests.RequestException as e:
            raise Exception(f"Connection error: {e}")
    
    # ========================================================================
    # MARKET DATA
    # ========================================================================
    
    def get_price(self, symbol: str) -> float:
        """
        Get current price for a symbol
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
        
        Returns:
            Current price as float
        """
        endpoint = "/api/v3/ticker/price"
        params = {'symbol': symbol.upper()}
        data = self._request('GET', endpoint, params)
        return float(data['price'])
    
    def get_ticker_24h(self, symbol: str) -> Dict:
        """Get 24h ticker statistics"""
        endpoint = "/api/v3/ticker/24hr"
        params = {'symbol': symbol.upper()}
        return self._request('GET', endpoint, params)
    
    def get_klines(self, symbol: str, interval: str = '1h', limit: int = 100) -> list:
        """
        Get OHLCV candlestick data
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            interval: Kline interval (1m, 5m, 15m, 1h, 4h, 1d, etc.)
            limit: Number of candles (max 1000)
        
        Returns:
            List of candles: [open_time, open, high, low, close, volume, ...]
        """
        endpoint = "/api/v3/klines"
        params = {
            'symbol': symbol.upper(),
            'interval': interval,
            'limit': limit
        }
        return self._request('GET', endpoint, params)
    
    # ========================================================================
    # ACCOUNT INFO
    # ========================================================================
    
    def get_account_spot(self) -> Dict:
        """Get spot account info and balances"""
        endpoint = "/api/v3/account"
        return self._request('GET', endpoint, signed=True)
    
    def get_balance_spot(self, asset: str = 'USDT') -> float:
        """
        Get available balance for an asset (spot)
        
        Args:
            asset: Asset symbol (e.g., 'USDT', 'BTC')
        
        Returns:
            Available balance as float
        """
        account = self.get_account_spot()
        for balance in account.get('balances', []):
            if balance['asset'] == asset:
                return float(balance['free'])
        return 0.0
    
    def get_account_futures(self) -> Dict:
        """Get futures account info"""
        endpoint = "/fapi/v2/account"
        return self._request('GET', endpoint, signed=True)
    
    def get_balance_futures(self, asset: str = 'USDT') -> float:
        """
        Get available balance for an asset (futures)
        
        Args:
            asset: Asset symbol (e.g., 'USDT')
        
        Returns:
            Available balance as float
        """
        account = self.get_account_futures()
        for asset_info in account.get('assets', []):
            if asset_info['asset'] == asset:
                return float(asset_info['available'])
        return 0.0
    
    # ========================================================================
    # SPOT TRADING
    # ========================================================================
    
    def place_spot_order(self, symbol: str, side: str, order_type: str, 
                         quantity: float = None, quote_order_qty: float = None) -> Dict:
        """
        Place a spot order
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            side: 'BUY' or 'SELL'
            order_type: 'MARKET', 'LIMIT', etc.
            quantity: Order quantity in base asset (for LIMIT orders)
            quote_order_qty: Order quantity in quote asset (for MARKET buy)
        
        Returns:
            Order response with orderId, status, fills, etc.
        """
        endpoint = "/api/v3/order"
        params = {
            'symbol': symbol.upper(),
            'side': side.upper(),
            'type': order_type.upper(),
        }
        
        if quantity:
            params['quantity'] = quantity
        if quote_order_qty:
            params['quoteOrderQty'] = quote_order_qty
        if order_type.upper() == 'LIMIT':
            params['timeInForce'] = 'GTC'
        
        return self._request('POST', endpoint, params, signed=True)
    
    def cancel_spot_order(self, symbol: str, order_id: int) -> Dict:
        """Cancel a spot order"""
        endpoint = "/api/v3/order"
        params = {
            'symbol': symbol.upper(),
            'orderId': order_id
        }
        return self._request('DELETE', endpoint, params, signed=True)
    
    def get_spot_order_status(self, symbol: str, order_id: int) -> Dict:
        """Get spot order status"""
        endpoint = "/api/v3/order"
        params = {
            'symbol': symbol.upper(),
            'orderId': order_id
        }
        return self._request('GET', endpoint, params, signed=True)
    
    # ========================================================================
    # FUTURES TRADING
    # ========================================================================
    
    def set_leverage(self, symbol: str, leverage: int) -> Dict:
        """
        Set leverage for a futures symbol
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            leverage: Leverage (1-125)
        
        Returns:
            Response with new leverage
        """
        endpoint = "/fapi/v1/leverage"
        params = {
            'symbol': symbol.upper(),
            'leverage': leverage
        }
        return self._request('POST', endpoint, params, signed=True)
    
    def place_futures_order(self, symbol: str, side: str, order_type: str,
                            quantity: float, position_side: str = 'BOTH') -> Dict:
        """
        Place a futures order
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            side: 'BUY' (LONG) or 'SELL' (SHORT)
            order_type: 'MARKET', 'LIMIT', etc.
            quantity: Order quantity in base asset
            position_side: 'BOTH' (one-way), 'LONG', or 'SHORT' (hedge mode)
        
        Returns:
            Order response with orderId, status, fills, etc.
        """
        endpoint = "/fapi/v1/order"
        params = {
            'symbol': symbol.upper(),
            'side': side.upper(),
            'positionSide': position_side,
            'type': order_type.upper(),
            'quantity': quantity,
        }
        
        if order_type.upper() == 'LIMIT':
            params['timeInForce'] = 'GTC'
        
        return self._request('POST', endpoint, params, signed=True)
    
    def cancel_futures_order(self, symbol: str, order_id: int) -> Dict:
        """Cancel a futures order"""
        endpoint = "/fapi/v1/order"
        params = {
            'symbol': symbol.upper(),
            'orderId': order_id
        }
        return self._request('DELETE', endpoint, params, signed=True)
    
    def get_futures_order_status(self, symbol: str, order_id: int) -> Dict:
        """Get futures order status"""
        endpoint = "/fapi/v1/order"
        params = {
            'symbol': symbol.upper(),
            'orderId': order_id
        }
        return self._request('GET', endpoint, params, signed=True)
    
    def get_futures_positions(self) -> list:
        """Get all open futures positions"""
        endpoint = "/fapi/v2/positionRisk"
        return self._request('GET', endpoint, signed=True)
    
    def close_futures_position(self, symbol: str, quantity: float, side: str = None) -> Dict:
        """
        Close a futures position (market order)
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            quantity: Position size to close
            side: 'SELL' to close LONG, 'BUY' to close SHORT (auto-detected if None)
        
        Returns:
            Order response
        """
        # Auto-detect side if not provided
        if side is None:
            positions = self.get_futures_positions()
            for pos in positions:
                if pos['symbol'] == symbol.upper() and float(pos['positionAmt']) != 0:
                    # If position is positive (LONG), close with SELL
                    # If position is negative (SHORT), close with BUY
                    side = 'SELL' if float(pos['positionAmt']) > 0 else 'BUY'
                    break
        
        if side is None:
            raise Exception(f"No open position for {symbol}")
        
        return self.place_futures_order(symbol, side, 'MARKET', quantity)


# ============================================================================
# TEST / DEMO
# ============================================================================

if __name__ == '__main__':
    import os
    from pathlib import Path
    
    # Load credentials from .env.demo
    env_path = Path(__file__).parent / '.env.demo'
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                if line.startswith('BINANCE_DEMO_API_KEY='):
                    api_key = line.split('=')[1].strip()
                elif line.startswith('BINANCE_DEMO_SECRET='):
                    api_secret = line.split('=')[1].strip()
    else:
        print("❌ .env.demo not found")
        exit(1)
    
    # Initialize client
    print("="*80)
    print("BINANCE DEMO EXCHANGE - TEST")
    print("="*80)
    
    exchange = BinanceDemoExchange(api_key, api_secret)
    
    # Test 1: Get prices
    print("\n📊 Test 1: Get Prices")
    for symbol in ['BTCUSDT', 'ETHUSDT', 'BCHUSDT', 'MATICUSDT']:
        try:
            price = exchange.get_price(symbol)
            print(f"  {symbol}: ${price:,.2f}")
        except Exception as e:
            print(f"  {symbol}: ERROR - {e}")
    
    # Test 2: Get spot balance
    print("\n💰 Test 2: Spot Account Balance")
    try:
        account = exchange.get_account_spot()
        usdt_balance = exchange.get_balance_spot('USDT')
        print(f"  USDT Available: ${usdt_balance:,.2f}")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    # Test 3: Get futures balance
    print("\n💰 Test 3: Futures Account Balance")
    try:
        account = exchange.get_account_futures()
        usdt_balance = exchange.get_balance_futures('USDT')
        print(f"  USDT Available: ${usdt_balance:,.2f}")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    # Test 4: Get open futures positions
    print("\n📈 Test 4: Open Futures Positions")
    try:
        positions = exchange.get_futures_positions()
        open_positions = [p for p in positions if float(p.get('positionAmt', 0)) != 0]
        if open_positions:
            for pos in open_positions:
                print(f"  {pos['symbol']}: {pos['positionAmt']} @ ${float(pos['entryPrice']):,.2f}")
        else:
            print("  No open positions")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    print("\n" + "="*80)
    print("✅ Connection test complete!")
    print("="*80)
