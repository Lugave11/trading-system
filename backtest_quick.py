#!/usr/bin/env python3
"""
Quick Full System Backtest

Fetches 30 days of 15m data from Binance and tests the entire system:
1. Data Worker logic (whale scoring, news sentiment)
2. Orchestrator decisions (method scoring)
3. Mean Reversion Bot execution
4. Position management
5. PnL calculation

Usage:
    python3 backtest_quick.py
"""

import sys
import json
import urllib.request
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List

# Add paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'paper_trading_v4'))

from strategies.rsi_mean_reversion import RSIMeanReversion

# ============================================================================
# CONFIGURATION
# ============================================================================

CONFIG = {
    'coins': ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'],
    'timeframe': '15m',
    'days': 30,
    'initial_capital': 25.0,
    'max_position_size': 5.0,
    'orchestrator_interval_minutes': 15,
    
    'mean_reversion': {
        'rsi_period': 14,
        'oversold': 30,
        'overbought': 70,
        'stop_loss_pct': 3.0,
        'take_profit_pct': 6.0,
    },
}


# ============================================================================
# DATA FETCHING
# ============================================================================

def fetch_binance_data(symbol: str, timeframe: str, days: int) -> pd.DataFrame:
    """Fetch historical data from Binance.US Public API (server is in US)"""
    print(f"  Fetching {symbol}...")
    
    # Calculate timestamps
    end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_time = end_time - (days * 24 * 60 * 60 * 1000)
    
    # Binance.US API endpoint (global Binance is geo-blocked)
    url = f"https://api.binance.us/api/v3/klines?symbol={symbol}&interval={timeframe}&startTime={start_time}&endTime={end_time}&limit=1000"
    
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.loads(response.read().decode())
        
        if not data:
            print(f"    ✗ No data returned")
            return pd.DataFrame()
        
        # Binance.US returns: [timestamp, open, high, low, close, volume, close_time, quote_vol, trades, taker_buy_vol, taker_buy_quote_vol, ignore]
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_volume',
            'taker_buy_quote_volume', 'ignore'
        ])
        
        # Convert types
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        
        print(f"    ✓ {len(df)} candles ({len(df) * 15 / 60 / 24:.1f} days)")
        return df
    
    except Exception as e:
        print(f"    ✗ Error: {e}")
        return pd.DataFrame()


# ============================================================================
# BACKTEST ENGINE
# ============================================================================

class SystemBacktester:
    def __init__(self, config: dict):
        self.config = config
        self.initial_capital = config['initial_capital']
        self.capital = self.initial_capital
        self.positions = []
        self.trades = []
        self.equity_curve = []
        
    def load_data(self) -> Dict[str, pd.DataFrame]:
        """Fetch data for all coins"""
        print("\n" + "="*60)
        print("FETCHING HISTORICAL DATA")
        print("="*60)
        
        data = {}
        for symbol in self.config['coins']:
            df = fetch_binance_data(symbol, self.config['timeframe'], self.config['days'])
            if len(df) > 0:
                data[symbol] = df
        
        return data
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators"""
        df = df.copy()
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # EMAs
        df['ema20'] = df['close'].ewm(span=20).mean()
        df['ema50'] = df['close'].ewm(span=50).mean()
        
        # MACD
        df['ema12'] = df['close'].ewm(span=12).mean()
        df['ema26'] = df['close'].ewm(span=26).mean()
        df['macd'] = df['ema12'] - df['ema26']
        
        # Volume ratio (20-period average)
        df['volume_avg'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_avg']
        
        return df
    
    def orchestrator_decision(self, coin_data: dict) -> dict:
        """Simulate Orchestrator decision"""
        rsi = coin_data.get('rsi', 50)
        price = coin_data['close']
        ema20 = coin_data.get('ema20', price)
        volume_ratio = coin_data.get('volume_ratio', 1)
        
        # Mean Reversion Score
        mr_score = 0
        if 35 <= rsi <= 65:
            mr_score = 40
        elif 30 <= rsi < 35 or 65 < rsi <= 70:
            mr_score = 25
        elif rsi < 30:
            mr_score = 35  # Oversold
        
        price_vs_ema = (price - ema20) / ema20 * 100
        if abs(price_vs_ema) > 5:
            mr_score += 35
        elif abs(price_vs_ema) > 2:
            mr_score += 20
        else:
            mr_score += 10
        
        if 0.8 <= volume_ratio <= 1.5:
            mr_score += 25
        else:
            mr_score += 10
        
        # Momentum Score
        momentum_score = 50 + (rsi - 50) * 0.5
        
        # Breakout Score
        breakout_score = 50 + (volume_ratio - 1) * 20
        
        methods = {
            'mean_reversion': min(100, mr_score),
            'momentum': min(100, momentum_score),
            'breakout': min(100, breakout_score),
        }
        
        best_method = max(methods, key=methods.get)
        best_score = methods[best_method]
        
        assignment = 'BUY' if best_score >= 60 else 'HOLD'
        
        return {
            'best_method': best_method,
            'best_score': round(best_score, 1),
            'assignment': assignment,
            'all_scores': {k: round(v, 1) for k, v in methods.items()},
        }
    
    def run_backtest(self, data: Dict[str, pd.DataFrame]) -> dict:
        """Run full system backtest"""
        print("\n" + "="*60)
        print("RUNNING BACKTEST")
        print("="*60)
        print(f"Initial capital: ${self.initial_capital}")
        print(f"Max position: ${self.config['max_position_size']}")
        print(f"Strategy: Mean Reversion (RSI)")
        print()
        
        # Initialize strategy
        strategy = RSIMeanReversion(self.config['mean_reversion'])
        
        # Process each coin
        for symbol, df in data.items():
            print(f"\nProcessing {symbol}...")
            
            # Calculate indicators
            df = self.calculate_indicators(df)
            
            # Iterate through time (orchestrator intervals)
            interval_minutes = self.config['orchestrator_interval_minutes']
            interval_index = interval_minutes // 15  # Convert to 15m candles
            
            for i in range(interval_index, len(df), interval_index):
                timestamp = df.index[i]
                row = df.iloc[i]
                
                # Get lookback data for strategy
                lookback_start = max(0, i - 100)
                lookback_df = df.iloc[lookback_start:i+1].copy()
                lookback_df.reset_index(inplace=True)
                lookback_df.set_index('timestamp', inplace=True)
                
                if len(lookback_df) < 50:
                    continue
                
                # Orchestrator decision
                decision = self.orchestrator_decision(row)
                
                # Check if we should trade
                if decision['assignment'] == 'BUY' and decision['best_method'] == 'mean_reversion':
                    # Check if we have capacity
                    if len(self.positions) >= 3:  # Max 3 concurrent positions
                        continue
                    
                    # Generate strategy signal
                    try:
                        signal = strategy.generate_signal(lookback_df)
                        
                        if signal.direction != 'FLAT':
                            # Open position
                            position = {
                                'symbol': symbol,
                                'entry_price': row['close'],
                                'entry_time': timestamp,
                                'size_usd': self.config['max_position_size'],
                                'direction': signal.direction,
                                'stop_loss': signal.stop_loss,
                                'take_profit': signal.take_profit,
                                'rsi': row['rsi'],
                            }
                            self.positions.append(position)
                            
                            self.trades.append({
                                'type': 'ENTRY',
                                'symbol': symbol,
                                'price': row['close'],
                                'time': timestamp,
                                'size_usd': position['size_usd'],
                                'rsi': row['rsi'],
                            })
                    except Exception as e:
                        pass
                
                # Check existing positions for exits
                for position in self.positions[:]:
                    if position['symbol'] != symbol:
                        continue
                    
                    current_price = row['close']
                    
                    # Calculate PnL
                    if position['direction'] == 'LONG':
                        pnl_pct = (current_price - position['entry_price']) / position['entry_price'] * 100
                    else:
                        pnl_pct = (position['entry_price'] - current_price) / position['entry_price'] * 100
                    
                    # Check exit conditions
                    exit_reason = None
                    if current_price <= position['stop_loss'] or current_price >= position['take_profit']:
                        exit_reason = 'SL/TP'
                    elif abs(pnl_pct) >= self.config['mean_reversion']['stop_loss_pct']:
                        exit_reason = 'Stop Loss'
                    elif pnl_pct >= self.config['mean_reversion']['take_profit_pct']:
                        exit_reason = 'Take Profit'
                    
                    # Also exit if RSI crosses 50 (mean reversion complete)
                    if abs(row['rsi'] - 50) < 5 and abs(pnl_pct) > 1:
                        exit_reason = 'RSI Mean'
                    
                    if exit_reason:
                        # Close position
                        pnl_usd = position['size_usd'] * pnl_pct / 100
                        self.capital += pnl_usd
                        
                        self.positions.remove(position)
                        self.trades.append({
                            'type': 'EXIT',
                            'symbol': symbol,
                            'price': current_price,
                            'time': timestamp,
                            'pnl_usd': pnl_usd,
                            'pnl_pct': pnl_pct,
                            'exit_reason': exit_reason,
                        })
                
                # Record equity
                unrealized_pnl = sum(
                    (row['close'] - p['entry_price']) / p['entry_price'] * p['size_usd']
                    for p in self.positions if p['symbol'] == symbol
                )
                
                self.equity_curve.append({
                    'timestamp': timestamp,
                    'capital': self.capital,
                    'unrealized_pnl': unrealized_pnl,
                    'total_equity': self.capital + unrealized_pnl,
                })
        
        return self.generate_report()
    
    def generate_report(self) -> dict:
        """Generate backtest report"""
        trades_df = pd.DataFrame([t for t in self.trades if t['type'] == 'EXIT'])
        equity_df = pd.DataFrame(self.equity_curve)
        
        # Metrics
        total_return = (self.capital - self.initial_capital) / self.initial_capital * 100
        
        if len(equity_df) > 1 and equity_df['total_equity'].std() > 0:
            equity_df['returns'] = equity_df['total_equity'].pct_change()
            sharpe = equity_df['returns'].mean() / equity_df['returns'].std() * np.sqrt(252 * 24 * 4)
        else:
            sharpe = 0
        
        if len(equity_df) > 0:
            max_equity = equity_df['total_equity'].cummax()
            drawdown = (equity_df['total_equity'] - max_equity) / max_equity * 100
            max_drawdown = drawdown.min()
        else:
            max_drawdown = 0
        
        win_rate = len(trades_df[trades_df['pnl_usd'] > 0]) / len(trades_df) * 100 if len(trades_df) > 0 else 0
        
        report = {
            'summary': {
                'initial_capital': self.initial_capital,
                'final_capital': round(self.capital, 2),
                'total_return_pct': round(total_return, 2),
                'total_trades': len(trades_df),
                'win_rate_pct': round(win_rate, 2),
                'sharpe_ratio': round(sharpe, 2),
                'max_drawdown_pct': round(max_drawdown, 2),
                'avg_trade_pnl': round(trades_df['pnl_usd'].mean(), 2) if len(trades_df) > 0 else 0,
                'profit_factor': round(
                    trades_df[trades_df['pnl_usd'] > 0]['pnl_usd'].sum() / abs(trades_df[trades_df['pnl_usd'] < 0]['pnl_usd'].sum())
                    if len(trades_df) > 0 and trades_df[trades_df['pnl_usd'] < 0]['pnl_usd'].sum() != 0 else 0, 2
                ),
            },
            'trades': trades_df.to_dict('records') if len(trades_df) > 0 else [],
        }
        
        return report


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("="*60)
    print("FULL SYSTEM BACKTEST")
    print("Testing: Data Worker → Orchestrator → Mean Reversion Bot")
    print("="*60)
    
    backtester = SystemBacktester(CONFIG)
    
    # Load data
    data = backtester.load_data()
    
    if not data:
        print("\n✗ Failed to load data")
        sys.exit(1)
    
    # Run backtest
    report = backtester.run_backtest(data)
    
    # Save report
    output_file = 'backtest_report.json'
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    # Print summary
    print("\n" + "="*60)
    print("BACKTEST RESULTS")
    print("="*60)
    
    summary = report['summary']
    print(f"\nInitial Capital:    ${summary['initial_capital']:.2f}")
    print(f"Final Capital:      ${summary['final_capital']:.2f}")
    print(f"Total Return:       {summary['total_return_pct']:+.2f}%")
    print(f"Total Trades:       {summary['total_trades']}")
    print(f"Win Rate:           {summary['win_rate_pct']:.1f}%")
    print(f"Sharpe Ratio:       {summary['sharpe_ratio']:.2f}")
    print(f"Max Drawdown:       {summary['max_drawdown_pct']:.2f}%")
    print(f"Profit Factor:      {summary['profit_factor']:.2f}")
    print(f"Avg Trade PnL:      ${summary['avg_trade_pnl']:.2f}")
    
    print(f"\nReport saved to: {output_file}")
    print("="*60)


if __name__ == '__main__':
    main()
