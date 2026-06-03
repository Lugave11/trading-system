#!/usr/bin/env python3
"""
Full System Backtest - Tests entire trading system on historical data

Simulates:
1. Data Worker collecting historical data
2. Orchestrator making decisions every 15 minutes
3. Method Bots executing trades
4. Position monitoring and exits
5. Performance aggregation

Usage:
    python3 backtest_full_system.py --days 30 --coins BTC,ETH,SOL
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import pandas as pd
import numpy as np

# Add paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'paper_trading_v4'))

from strategies.rsi_mean_reversion import RSIMeanReversion
from core.data_manager import DataManager
from exchanges.mexc import MEXC
from backtesting.metrics import calculate_metrics

# ============================================================================
# BACKTEST CONFIGURATION
# ============================================================================

BACKTEST_CONFIG = {
    'days': 30,
    'coins': ['BTC', 'ETH', 'SOL'],
    'timeframe': '15m',
    'initial_capital': 25.0,
    'max_position_size': 5.0,
    'data_worker_interval_minutes': 5,
    'orchestrator_interval_minutes': 15,
    
    # Strategy parameters
    'mean_reversion': {
        'rsi_period': 14,
        'oversold': 30,
        'overbought': 70,
        'stop_loss_pct': 3.0,
        'take_profit_pct': 6.0,
    },
    'momentum': {
        'rsi_period': 14,
        'trend_threshold': 60,
        'stop_loss_pct': 5.0,
        'take_profit_pct': 12.0,
    },
    'breakout': {
        'consolidation_periods': 8,
        'volume_spike_threshold': 2.0,
        'stop_loss_pct': 4.0,
        'take_profit_pct': 10.0,
    },
}


# ============================================================================
# SIMULATED COMPONENTS
# ============================================================================

class SimulatedDataWorker:
    """Simulates Data Worker on historical data"""
    
    def __init__(self, data: Dict[str, pd.DataFrame], config: dict):
        self.data = data
        self.config = config
        
    def run_cycle(self, timestamp: datetime, coins: List[str]) -> dict:
        """Run data collection cycle at given timestamp"""
        coin_data = []
        
        for symbol in coins:
            if symbol not in self.data:
                continue
            
            df = self.data[symbol]
            # Get candles up to timestamp
            mask = df['timestamp'] <= timestamp
            historical_df = df[mask].tail(100)
            
            if len(historical_df) < 50:
                continue
            
            # Calculate indicators (simplified)
            latest = historical_df.iloc[-1]
            
            # RSI
            delta = latest['close'] - historical_df['close'].shift(1)
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = -delta.where(delta < 0, 0).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            # EMAs
            ema20 = historical_df['close'].ewm(span=20).mean().iloc[-1]
            ema50 = historical_df['close'].ewm(span=50).mean().iloc[-1]
            
            # MACD
            ema12 = historical_df['close'].ewm(span=12).mean().iloc[-1]
            ema26 = historical_df['close'].ewm(span=26).mean().iloc[-1]
            macd = ema12 - ema26
            
            # Volume ratio
            avg_volume = historical_df['volume'].rolling(20).mean().iloc[-1]
            volume_ratio = latest['volume'] / avg_volume if avg_volume > 0 else 1.0
            
            coin_data.append({
                'symbol': symbol,
                'timestamp': timestamp.isoformat(),
                'ohlcv': {
                    'success': True,
                    'candles': historical_df.to_dict('records'),
                    'indicators': {
                        'current_price': latest['close'],
                        'rsi': rsi.iloc[-1] if hasattr(rsi, 'iloc') else rsi,
                        'macd': macd,
                        'ema20': ema20,
                        'ema50': ema50,
                        'volume_ratio': volume_ratio,
                        'trend': 'bullish' if latest['close'] > ema20 else 'bearish',
                    }
                },
                'whale_score': 50 + np.random.randint(-10, 10),  # Simulated
                'market': {
                    'market_cap': latest['close'] * 1e9,  # Placeholder
                    'volume_24h': latest['volume'] * 24 * 4,
                },
                'news': {
                    'news_sentiment': 'neutral',
                    'average_sentiment_score': 50,
                }
            })
        
        return {
            'success': True,
            'summary': {
                'coins_processed': len(coin_data),
                'alerts_triggered': 0,
                'average_whale_score': np.mean([c['whale_score'] for c in coin_data]) if coin_data else 50,
            },
            'coin_data': coin_data,
            'alerts': [],
        }


class SimulatedOrchestrator:
    """Simulates Orchestrator decision-making"""
    
    def __init__(self, config: dict):
        self.config = config
        
    def calculate_mean_reversion_score(self, coin_data: dict) -> float:
        """Calculate mean reversion fit score"""
        indicators = coin_data.get('ohlcv', {}).get('indicators', {})
        rsi = indicators.get('rsi', 50)
        price_vs_ema = (indicators.get('current_price', 0) - indicators.get('ema20', 0)) / indicators.get('ema20', 1) * 100
        
        score = 0
        
        # RSI in range (0-40 points)
        if 35 <= rsi <= 65:
            score += 40
        elif 30 <= rsi < 35 or 65 < rsi <= 70:
            score += 25
        elif rsi < 30:
            score += 35  # Oversold = good for mean reversion long
        else:
            score += 5
        
        # Price position (0-35 points)
        if abs(price_vs_ema) > 5:
            score += 35
        elif abs(price_vs_ema) > 2:
            score += 20
        else:
            score += 10
        
        # Volatility (0-25 points)
        vol_ratio = indicators.get('volume_ratio', 1)
        if 0.8 <= vol_ratio <= 1.5:
            score += 25
        else:
            score += 10
        
        return min(100, score)
    
    def run_cycle(self, data_worker_output: dict) -> dict:
        """Run orchestration cycle"""
        decisions = []
        
        for coin_data in data_worker.get('coin_data', []):
            symbol = coin_data['symbol']
            
            # Calculate scores for each method
            mr_score = self.calculate_mean_reversion_score(coin_data)
            
            # Simplified momentum and breakout scores
            indicators = coin_data.get('ohlcv', {}).get('indicators', {})
            momentum_score = 50 + (indicators.get('rsi', 50) - 50) * 0.5
            breakout_score = 50 + (indicators.get('volume_ratio', 1) - 1) * 20
            
            # Find best method
            methods = {
                'mean_reversion': mr_score,
                'momentum': momentum_score,
                'breakout': breakout_score,
            }
            
            best_method = max(methods, key=methods.get)
            best_score = methods[best_method]
            
            # Decide
            if best_score >= 60:
                assignment = 'BUY'
            elif best_score >= 45:
                assignment = 'HOLD'
            else:
                assignment = 'HOLD'
            
            decisions.append({
                'symbol': symbol,
                'assignment': assignment,
                'best_method': best_method,
                'best_score': round(best_score, 1),
                'all_scores': {k: round(v, 1) for k, v in methods.items()},
                'current_price': indicators.get('current_price', 0),
            })
        
        return {
            'success': True,
            'decisions': decisions,
            'summary': {
                'coins_evaluated': len(decisions),
                'buy_signals': sum(1 for d in decisions if d['assignment'] == 'BUY'),
                'hold_signals': sum(1 for d in decisions if d['assignment'] == 'HOLD'),
                'switch_signals': 0,
            }
        }


class SimulatedMeanReversionBot:
    """Simulates mean reversion execution"""
    
    def __init__(self, config: dict):
        self.config = config
        self.strategy = RSIMeanReversion(config)
        
    def execute(self, symbol: str, coin_data: dict, decision: dict) -> dict:
        """Execute mean reversion trade"""
        candles = coin_data.get('ohlcv', {}).get('candles', [])
        
        if len(candles) < 50:
            return {'success': False, 'error': 'Insufficient data'}
        
        # Convert to DataFrame
        df = pd.DataFrame(candles)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        
        # Generate signal
        signal = self.strategy.generate_signal(df)
        
        if signal.direction == 'FLAT':
            return {
                'success': True,
                'action': 'NO_TRADE',
                'symbol': symbol,
                'reason': 'Strategy says FLAT',
            }
        
        current_price = decision.get('current_price', candles[-1]['close'])
        
        return {
            'success': True,
            'action': 'OPEN_POSITION',
            'symbol': symbol,
            'direction': signal.direction,
            'entry_price': current_price,
            'position_size_usd': min(5.0, BACKTEST_CONFIG['max_position_size']),
            'stop_loss': signal.stop_loss,
            'take_profit': signal.take_profit,
            'rsi': signal.metadata.get('rsi'),
        }


# ============================================================================
# MAIN BACKTEST ENGINE
# ============================================================================

class FullSystemBacktester:
    """Runs full system backtest"""
    
    def __init__(self, config: dict):
        self.config = config
        self.initial_capital = config['initial_capital']
        self.capital = self.initial_capital
        self.positions = []
        self.trades = []
        self.equity_curve = []
        
    def load_data(self, coins: List[str], days: int, timeframe: str = '15m') -> Dict[str, pd.DataFrame]:
        """Load historical data for all coins"""
        print(f"Loading {days} days of {timeframe} data for {', '.join(coins)}...")
        
        data = {}
        for symbol in coins:
            try:
                # Try to load from paper_trading_v4 data
                data_path = Path(f'/mnt/data/hermes/workspace/paper_trading_v4/data/{symbol}_USDT_{timeframe}.csv')
                if data_path.exists():
                    df = pd.read_csv(data_path)
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    df.set_index('timestamp', inplace=True)
                    
                    # Filter to last N days
                    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
                    df = df[df['timestamp'] >= cutoff]
                    
                    data[symbol] = df
                    print(f"  ✓ {symbol}: {len(df)} candles")
                else:
                    print(f"  ✗ {symbol}: No data file found")
            except Exception as e:
                print(f"  ✗ {symbol}: Error - {e}")
        
        return data
    
    def run_backtest(self, data: Dict[str, pd.DataFrame]) -> dict:
        """Run full system backtest"""
        print(f"\nStarting backtest...")
        print(f"Initial capital: ${self.initial_capital}")
        print(f"Max position size: ${self.config['max_position_size']}")
        print()
        
        # Initialize components
        data_worker = SimulatedDataWorker(data, self.config)
        orchestrator = SimulatedOrchestrator(self.config)
        mr_bot = SimulatedMeanReversionBot(self.config['mean_reversion'])
        
        # Get time range
        all_timestamps = []
        for df in data.values():
            all_timestamps.extend(df.index.tolist())
        
        if not all_timestamps:
            return {'error': 'No data available'}
        
        min_time = min(all_timestamps)
        max_time = max(all_timestamps)
        
        print(f"Backtest period: {min_time} to {max_time}")
        print(f"Running simulation...")
        
        # Simulate time progression
        current_time = min_time
        data_cycle_counter = 0
        orchestrator_cycle_counter = 0
        
        while current_time <= max_time:
            # Data Worker cycle (every 5 min)
            data_cycle_counter += 1
            if data_cycle_counter >= self.config['data_worker_interval_minutes']:
                data_worker_output = data_worker.run_cycle(current_time, self.config['coins'])
                data_cycle_counter = 0
            
            # Orchestrator cycle (every 15 min)
            orchestrator_cycle_counter += 1
            if orchestrator_cycle_counter >= self.config['orchestrator_interval_minutes']:
                orchestrator_output = orchestrator.run_cycle(data_worker_output)
                
                # Execute BUY signals
                for decision in orchestrator_output['decisions']:
                    if decision['assignment'] == 'BUY' and decision['best_method'] == 'mean_reversion':
                        coin_data = next((c for c in data_worker_output['coin_data'] if c['symbol'] == decision['symbol']), None)
                        if coin_data:
                            execution = mr_bot.execute(decision['symbol'], coin_data, decision)
                            
                            if execution.get('action') == 'OPEN_POSITION':
                                # Open position
                                self.positions.append({
                                    'symbol': execution['symbol'],
                                    'entry_price': execution['entry_price'],
                                    'entry_time': current_time,
                                    'size_usd': execution['position_size_usd'],
                                    'stop_loss': execution['stop_loss'],
                                    'take_profit': execution['take_profit'],
                                    'method': 'mean_reversion',
                                })
                                
                                self.trades.append({
                                    'type': 'ENTRY',
                                    'symbol': execution['symbol'],
                                    'price': execution['entry_price'],
                                    'time': current_time,
                                    'size_usd': execution['position_size_usd'],
                                })
                
                orchestrator_cycle_counter = 0
            
            # Check position exits
            for position in self.positions[:]:
                # Get current price
                symbol = position['symbol']
                if symbol not in data:
                    continue
                
                df = data[symbol]
                mask = df.index <= current_time
                if mask.sum() == 0:
                    continue
                
                current_price = df[mask].iloc[-1]['close']
                
                # Check exit conditions
                pnl_pct = (current_price - position['entry_price']) / position['entry_price'] * 100
                if position['direction'] == 'SHORT':
                    pnl_pct = -pnl_pct
                
                exit_reason = None
                if current_price <= position['stop_loss'] or current_price >= position['take_profit']:
                    exit_reason = 'SL/TP'
                elif pnl_pct <= -self.config['mean_reversion']['stop_loss_pct']:
                    exit_reason = 'Stop Loss'
                elif pnl_pct >= self.config['mean_reversion']['take_profit_pct']:
                    exit_reason = 'Take Profit'
                
                if exit_reason:
                    # Close position
                    pnl_usd = position['size_usd'] * pnl_pct / 100
                    self.capital += pnl_usd
                    
                    self.positions.remove(position)
                    self.trades.append({
                        'type': 'EXIT',
                        'symbol': symbol,
                        'price': current_price,
                        'time': current_time,
                        'pnl_usd': pnl_usd,
                        'pnl_pct': pnl_pct,
                        'exit_reason': exit_reason,
                    })
            
            # Record equity
            unrealized_pnl = sum(
                (data[p['symbol']][data[p['symbol']].index <= current_time].iloc[-1]['close'] - p['entry_price']) / p['entry_price'] * p['size_usd']
                for p in self.positions if p['symbol'] in data
            )
            total_equity = self.capital + unrealized_pnl
            
            self.equity_curve.append({
                'timestamp': current_time,
                'capital': self.capital,
                'unrealized_pnl': unrealized_pnl,
                'total_equity': total_equity,
                'open_positions': len(self.positions),
            })
            
            # Advance time (15 min steps)
            current_time += timedelta(minutes=15)
        
        print(f"\nBacktest complete!")
        print(f"Final capital: ${self.capital:.2f}")
        print(f"Total trades: {len([t for t in self.trades if t['type'] == 'EXIT'])}")
        
        return self.generate_report()
    
    def generate_report(self) -> dict:
        """Generate backtest report"""
        if not self.equity_curve:
            return {'error': 'No equity curve data'}
        
        equity_df = pd.DataFrame(self.equity_curve)
        trades_df = pd.DataFrame([t for t in self.trades if t['type'] == 'EXIT'])
        
        # Calculate metrics
        total_return = (self.capital - self.initial_capital) / self.initial_capital * 100
        
        if len(equity_df) > 1:
            equity_df['returns'] = equity_df['total_equity'].pct_change()
            sharpe = equity_df['returns'].mean() / equity_df['returns'].std() * np.sqrt(252 * 24 * 4) if equity_df['returns'].std() > 0 else 0
        else:
            sharpe = 0
        
        max_equity = equity_df['total_equity'].cummax()
        drawdown = (equity_df['total_equity'] - max_equity) / max_equity * 100
        max_drawdown = drawdown.min()
        
        win_trades = trades_df[trades_df['pnl_usd'] > 0] if not trades_df.empty else pd.DataFrame()
        win_rate = len(win_trades) / len(trades_df) * 100 if len(trades_df) > 0 else 0
        
        report = {
            'summary': {
                'initial_capital': self.initial_capital,
                'final_capital': self.capital,
                'total_return_pct': round(total_return, 2),
                'total_trades': len(trades_df),
                'win_rate_pct': round(win_rate, 2),
                'sharpe_ratio': round(sharpe, 2),
                'max_drawdown_pct': round(max_drawdown, 2),
                'avg_trade_pnl': round(trades_df['pnl_usd'].mean(), 2) if not trades_df.empty else 0,
            },
            'trades': trades_df.to_dict('records') if not trades_df.empty else [],
            'equity_curve': equity_df.to_dict('records'),
        }
        
        return report


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Full System Backtest')
    parser.add_argument('--days', type=int, default=30, help='Backtest duration in days')
    parser.add_argument('--coins', type=str, default='BTC,ETH,SOL', help='Comma-separated coin list')
    parser.add_argument('--output', type=str, default='backtest_report.json', help='Output file')
    
    args = parser.parse_args()
    
    config = BACKTEST_CONFIG.copy()
    config['days'] = args.days
    config['coins'] = [c.strip() for c in args.coins.split(',')]
    
    print("="*60)
    print("FULL SYSTEM BACKTEST")
    print("="*60)
    print()
    
    backtester = FullSystemBacktester(config)
    
    # Load data
    data = backtester.load_data(config['coins'], config['days'])
    
    if not data:
        print("\n✗ No data available. Run data collection first.")
        sys.exit(1)
    
    # Run backtest
    report = backtester.run_backtest(data)
    
    # Save report
    with open(args.output, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\nReport saved to: {args.output}")
    
    # Print summary
    print("\n" + "="*60)
    print("BACKTEST SUMMARY")
    print("="*60)
    summary = report.get('summary', {})
    for key, value in summary.items():
        print(f"{key.replace('_', ' ').title()}: {value}")
    
    print("\n" + "="*60)


if __name__ == '__main__':
    main()
