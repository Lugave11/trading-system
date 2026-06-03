#!/usr/bin/env python3
"""
COMPLETE SYSTEM BACKTEST - 30 Days, 5-Minute Candles

Tests ENTIRE trading system with ALL components:
1. Data Worker - Whale watching, volume analysis, news sentiment
2. Orchestrator - Method scoring (momentum, mean reversion, breakout)
3. Method Bots - All three strategies with real execution
4. Position Management - Full lifecycle tracking
5. Performance Analytics - Comprehensive metrics

Usage:
    python3 backtest_complete_system.py --days 30 --timeframe 5m
"""

import sys
import json
import urllib.request
import urllib.error
import pandas as pd
import numpy as np
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import traceback

# Add paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'paper_trading_v4'))

# Import real strategies
try:
    from strategies.rsi_mean_reversion import RSIMeanReversion
    STRATEGY_AVAILABLE = True
except:
    STRATEGY_AVAILABLE = False
    print("⚠️  RSI Mean Reversion strategy not available - using simplified version")


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class BacktestConfig:
    coins: List[str] = None
    timeframe: str = '5m'
    days: int = 30
    initial_capital: float = 25.0
    max_position_size: float = 5.0
    max_concurrent_positions: int = 3
    
    # System timing
    data_worker_interval: int = 5  # minutes
    orchestrator_interval: int = 15  # minutes
    
    # Strategy parameters
    mean_reversion: Dict = None
    momentum: Dict = None
    breakout: Dict = None
    
    # Realistic simulation
    include_fees: bool = True
    fee_pct: float = 0.1
    slippage_pct: float = 0.05
    
    def __post_init__(self):
        if self.coins is None:
            self.coins = ['BTC', 'ETH', 'SOL']
        
        if self.mean_reversion is None:
            self.mean_reversion = {
                'rsi_period': 14,
                'oversold': 30,
                'overbought': 70,
                'stop_loss_pct': 3.0,
                'take_profit_pct': 6.0,
            }
        
        if self.momentum is None:
            self.momentum = {
                'rsi_period': 14,
                'trend_threshold': 60,
                'stop_loss_pct': 5.0,
                'take_profit_pct': 12.0,
            }
        
        if self.breakout is None:
            self.breakout = {
                'consolidation_periods': 8,
                'volume_spike': 2.0,
                'stop_loss_pct': 4.0,
                'take_profit_pct': 10.0,
            }


CONFIG = BacktestConfig()


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class Signal:
    direction: str  # LONG, SHORT, FLAT
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float
    metadata: Dict = None


@dataclass
class Position:
    symbol: str
    entry_time: datetime
    entry_price: float
    direction: str
    size_usd: float
    stop_loss: float
    take_profit: float
    method: str
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl_usd: Optional[float] = None
    pnl_pct: Optional[float] = None


@dataclass
class Trade:
    type: str  # ENTRY, EXIT
    symbol: str
    time: datetime
    price: float
    size_usd: Optional[float] = None
    pnl_usd: Optional[float] = None
    pnl_pct: Optional[float] = None
    method: Optional[str] = None
    exit_reason: Optional[str] = None
    fee: Optional[float] = None


@dataclass
class WhaleAlert:
    timestamp: datetime
    symbol: str
    type: str  # large_transfer, volume_spike, accumulation
    score: int
    details: Dict = None


@dataclass
class NewsItem:
    timestamp: datetime
    source: str
    title: str
    url: str
    sentiment: str  # bullish, bearish, neutral
    sentiment_score: float  # 0-100
    coins_mentioned: List[str] = None


# ============================================================================
# DATA FETCHING
# ============================================================================

class HistoricalDataManager:
    """Fetches and manages historical 5m data"""
    
    def __init__(self, coins: List[str], days: int, timeframe: str = '5m'):
        self.coins = coins
        self.days = days
        self.timeframe = timeframe
        self.data: Dict[str, pd.DataFrame] = {}
        self.news_data: List[NewsItem] = []
        
    def fetch_all(self) -> bool:
        """Fetch data for all coins"""
        print("\n" + "="*80)
        print("FETCHING HISTORICAL DATA")
        print("="*80)
        
        for symbol in self.coins:
            df = self._fetch_binance_us_data(f"{symbol}USDT", self.timeframe, self.days)
            if df is not None and len(df) > 0:
                self.data[symbol] = df
                print(f"  ✓ {symbol}: {len(df)} candles ({len(df) * 5 / 60 / 24:.1f} days)")
        
        # Fetch news history (simulated - RSS doesn't have historical API)
        self._generate_news_history()
        
        return len(self.data) > 0
    
    def _fetch_binance_us_data(self, symbol: str, timeframe: str, days: int) -> Optional[pd.DataFrame]:
        """Fetch from Binance.US with pagination"""
        print(f"\n  {symbol}...")
        
        all_candles = []
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = end_time - (days * 24 * 60 * 60 * 1000)
        
        # Binance.US returns max 1000 candles per request
        current_end = end_time
        page = 0
        max_pages = 50  # Up to 50,000 candles
        
        while current_end > start_time and page < max_pages:
            request_start = max(start_time, current_end - (1000 * 5 * 60 * 1000))
            
            url = f"https://api.binance.us/api/v3/klines?symbol={symbol}&interval={timeframe}&startTime={int(request_start)}&endTime={int(current_end)}&limit=1000"
            
            try:
                with urllib.request.urlopen(url, timeout=30) as response:
                    data = json.loads(response.read().decode())
                
                if not data:
                    break
                
                all_candles.extend(data)
                
                if len(data) < 1000:
                    break
                
                current_end = int(data[0][0]) - 1
                page += 1
                
            except Exception as e:
                print(f"    ✗ Page {page} error: {e}")
                break
        
        if not all_candles:
            print(f"    ✗ No data")
            return None
        
        # Convert to DataFrame
        df = pd.DataFrame(all_candles, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_volume',
            'taker_buy_quote_volume', 'ignore'
        ])
        
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        
        return df
    
    def _generate_news_history(self):
        """Generate simulated news history (RSS has no historical API)"""
        print(f"\n  Generating news history...")
        
        # Realistic news distribution
        news_templates = [
            ("CoinDesk", "Bitcoin Surges Past ${price} as Institutional Interest Grows", "bullish", 75),
            ("CoinDesk", "Ethereum Network Upgrade Shows Promise for Scalability", "bullish", 70),
            ("CoinDesk", "Regulatory Uncertainty Weighs on Crypto Markets", "bearish", 35),
            ("Cointelegraph", "Whale Alert: ${amount}M BTC Transferred to Exchange", "bearish", 30),
            ("Cointelegraph", "DeFi TVL Reaches New All-Time High", "bullish", 80),
            ("CryptoSlate", "Market Analysis: Consolidation Expected Near Current Levels", "neutral", 50),
            ("The Defiant", "New Protocol Launch Attracts $100M in First Day", "bullish", 65),
        ]
        
        # Generate ~3 news items per day
        num_news = self.days * 3
        start_time = datetime.now(timezone.utc) - timedelta(days=self.days)
        
        for i in range(num_news):
            timestamp = start_time + timedelta(
                days=np.random.randint(0, self.days),
                hours=np.random.randint(0, 24),
                minutes=np.random.randint(0, 60)
            )
            
            template = news_templates[i % len(news_templates)]
            source, title_template, sentiment, score = template
            
            # Customize title with current prices
            title = title_template.replace("${price}", "70000").replace("${amount}", str(np.random.randint(100, 500)))
            
            coins = []
            if 'Bitcoin' in title or 'BTC' in title:
                coins.append('BTC')
            if 'Ethereum' in title or 'ETH' in title:
                coins.append('ETH')
            if not coins:
                coins = ['BTC', 'ETH', 'SOL']
            
            self.news_data.append(NewsItem(
                timestamp=timestamp,
                source=source,
                title=title,
                url=f"https://example.com/news/{i}",
                sentiment=sentiment,
                sentiment_score=score,
                coins_mentioned=coins,
            ))
        
        # Sort by timestamp
        self.news_data.sort(key=lambda x: x.timestamp)
        
        print(f"    ✓ {len(self.news_data)} news items generated")


# ============================================================================
# DATA WORKER (WHALE WATCHING + NEWS)
# ============================================================================

class DataWorker:
    """Simulates Data Worker with whale watching and news analysis"""
    
    def __init__(self, config: BacktestConfig):
        self.config = config
    
    def run_cycle(self, timestamp: datetime, data_manager: HistoricalDataManager) -> Dict:
        """Run data collection cycle"""
        coin_data_list = []
        alerts = []
        
        for symbol in self.config.coins:
            if symbol not in data_manager.data:
                continue
            
            df = data_manager.data[symbol]
            mask = df.index <= timestamp
            
            if mask.sum() < 50:
                continue
            
            historical = df[mask].tail(100)
            
            # Calculate indicators
            indicators = self._calculate_indicators(historical)
            
            # Whale score calculation
            whale_score, whale_alerts = self._calculate_whale_score(
                symbol, timestamp, historical, indicators
            )
            
            alerts.extend(whale_alerts)
            
            # Get relevant news
            relevant_news = self._get_relevant_news(timestamp, symbol, data_manager.news_data)
            
            coin_data_list.append({
                'symbol': symbol,
                'timestamp': timestamp.isoformat(),
                'ohlcv': {
                    'success': True,
                    'indicators': indicators,
                    'candles': historical.tail(50).to_dict('records'),
                },
                'whale_score': whale_score,
                'whale_alerts': whale_alerts,
                'news': relevant_news,
                'market': {
                    'market_cap': indicators['current_price'] * 1e9,
                    'volume_24h': indicators['volume_24h'],
                }
            })
        
        return {
            'success': True,
            'coin_data': coin_data_list,
            'alerts': alerts,
            'timestamp': timestamp.isoformat(),
        }
    
    def _calculate_indicators(self, df: pd.DataFrame) -> Dict:
        """Calculate all technical indicators"""
        latest = df.iloc[-1]
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        # EMAs
        ema20 = df['close'].ewm(span=20).mean()
        ema50 = df['close'].ewm(span=50).mean()
        
        # MACD
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        macd = ema12 - ema26
        
        # Volume
        volume_avg = df['volume'].rolling(20).mean()
        volume_ratio = latest['volume'] / volume_avg.iloc[-1] if volume_avg.iloc[-1] > 0 else 1
        
        # 24h volume (288 x 5m candles)
        volume_24h = df['volume'].tail(288).sum()
        
        return {
            'current_price': latest['close'],
            'rsi': rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50,
            'ema20': ema20.iloc[-1],
            'ema50': ema50.iloc[-1],
            'macd': macd.iloc[-1] if not pd.isna(macd.iloc[-1]) else 0,
            'volume_ratio': volume_ratio,
            'volume_24h': volume_24h,
            'trend': 'bullish' if latest['close'] > ema20.iloc[-1] else 'bearish',
            'price_vs_ema20_pct': (latest['close'] - ema20.iloc[-1]) / ema20.iloc[-1] * 100,
        }
    
    def _calculate_whale_score(self, symbol: str, timestamp: datetime, 
                                df: pd.DataFrame, indicators: Dict) -> Tuple[int, List[WhaleAlert]]:
        """Calculate whale activity score"""
        score = 50  # Base neutral
        alerts = []
        
        # Volume anomaly
        vol_ratio = indicators['volume_ratio']
        if vol_ratio > 5:
            score += 30
            alerts.append(WhaleAlert(
                timestamp=timestamp,
                symbol=symbol,
                type='volume_spike',
                score=80,
                details={'volume_ratio': vol_ratio}
            ))
        elif vol_ratio > 3:
            score += 20
        elif vol_ratio > 2:
            score += 10
        
        # Price extension (whale accumulation/distribution proxy)
        price_vs_ema = abs(indicators['price_vs_ema20_pct'])
        if price_vs_ema > 10:
            score += 20
            alerts.append(WhaleAlert(
                timestamp=timestamp,
                symbol=symbol,
                type='large_move',
                score=70,
                details={'price_vs_ema': price_vs_ema}
            ))
        elif price_vs_ema > 5:
            score += 10
        
        return min(100, score), alerts
    
    def _get_relevant_news(self, timestamp: datetime, symbol: str, 
                           news_data: List[NewsItem]) -> Dict:
        """Get news from last 4 hours relevant to symbol"""
        cutoff = timestamp - timedelta(hours=4)
        
        relevant = [
            n for n in news_data 
            if cutoff <= n.timestamp <= timestamp and 
            (symbol in n.coins_mentioned or not n.coins_mentioned)
        ]
        
        # Calculate average sentiment
        if relevant:
            avg_score = sum(n.sentiment_score for n in relevant) / len(relevant)
            bullish_count = sum(1 for n in relevant if n.sentiment == 'bullish')
            bearish_count = sum(1 for n in relevant if n.sentiment == 'bearish')
            
            if avg_score > 60:
                sentiment = 'bullish'
            elif avg_score < 40:
                sentiment = 'bearish'
            else:
                sentiment = 'neutral'
        else:
            avg_score = 50
            sentiment = 'neutral'
            bullish_count = 0
            bearish_count = 0
        
        return {
            'articles': relevant[-5:],  # Last 5 articles
            'sentiment': sentiment,
            'average_sentiment_score': avg_score,
            'bullish_count': bullish_count,
            'bearish_count': bearish_count,
        }


# ============================================================================
# ORCHESTRATOR
# ============================================================================

class Orchestrator:
    """Evaluates coins and assigns to best-fit method"""
    
    def __init__(self, config: BacktestConfig):
        self.config = config
    
    def run_cycle(self, data_worker_output: Dict) -> Dict:
        """Run orchestration cycle"""
        decisions = []
        
        for coin_data in data_worker_output.get('coin_data', []):
            symbol = coin_data['symbol']
            indicators = coin_data['ohlcv']['indicators']
            whale_score = coin_data['whale_score']
            news = coin_data['news']
            
            # Calculate method scores
            mr_score = self._score_mean_reversion(indicators, whale_score, news)
            momentum_score = self._score_momentum(indicators, whale_score, news)
            breakout_score = self._score_breakout(indicators, whale_score, news)
            
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
            
            # Build reason
            reason = self._build_reason(best_method, indicators, news)
            
            decisions.append({
                'symbol': symbol,
                'assignment': assignment,
                'best_method': best_method,
                'best_score': round(best_score, 1),
                'all_scores': {k: round(v, 1) for k, v in methods.items()},
                'reason': reason,
                'current_price': indicators['current_price'],
            })
        
        return {
            'success': True,
            'decisions': decisions,
            'summary': {
                'coins_evaluated': len(decisions),
                'buy_signals': sum(1 for d in decisions if d['assignment'] == 'BUY'),
                'hold_signals': sum(1 for d in decisions if d['assignment'] == 'HOLD'),
            }
        }
    
    def _score_mean_reversion(self, indicators: Dict, whale_score: int, news: Dict) -> float:
        """Score mean reversion setup (0-100)"""
        rsi = indicators['rsi']
        price_vs_ema = abs(indicators['price_vs_ema20_pct'])
        vol_ratio = indicators['volume_ratio']
        
        score = 0
        
        # RSI in range (0-40 points)
        if 35 <= rsi <= 65:
            score += 40
        elif 30 <= rsi < 35 or 65 < rsi <= 70:
            score += 30
        elif rsi < 30 or rsi > 70:
            score += 35
        
        # Price extension (0-35 points)
        if price_vs_ema > 5:
            score += 35
        elif price_vs_ema > 2:
            score += 20
        else:
            score += 10
        
        # Volume (0-25 points)
        if 0.8 <= vol_ratio <= 1.5:
            score += 25
        else:
            score += 10
        
        return min(100, score)
    
    def _score_momentum(self, indicators: Dict, whale_score: int, news: Dict) -> float:
        """Score momentum setup (0-100)"""
        rsi = indicators['rsi']
        trend = indicators['trend']
        macd = indicators['macd']
        
        score = 0
        
        # RSI momentum (0-40 points)
        if trend == 'bullish' and 55 <= rsi <= 70:
            score += 40
        elif trend == 'bearish' and 30 <= rsi <= 45:
            score += 40
        elif 45 <= rsi <= 55:
            score += 20
        else:
            score += 10
        
        # Trend strength (0-35 points)
        if abs(indicators['price_vs_ema20_pct']) > 3:
            score += 35
        elif abs(indicators['price_vs_ema20_pct']) > 1:
            score += 20
        else:
            score += 10
        
        # MACD confirmation (0-25 points)
        if (trend == 'bullish' and macd > 0) or (trend == 'bearish' and macd < 0):
            score += 25
        else:
            score += 10
        
        return min(100, score)
    
    def _score_breakout(self, indicators: Dict, whale_score: int, news: Dict) -> float:
        """Score breakout setup (0-100)"""
        vol_ratio = indicators['volume_ratio']
        price_vs_ema = abs(indicators['price_vs_ema20_pct'])
        
        score = 0
        
        # Volume spike (0-50 points)
        if vol_ratio > 3:
            score += 50
        elif vol_ratio > 2:
            score += 35
        elif vol_ratio > 1.5:
            score += 20
        else:
            score += 10
        
        # Price breaking out (0-30 points)
        if price_vs_ema > 5:
            score += 30
        elif price_vs_ema > 2:
            score += 15
        else:
            score += 5
        
        # Whale activity (0-20 points)
        if whale_score > 70:
            score += 20
        elif whale_score > 60:
            score += 10
        else:
            score += 5
        
        return min(100, score)
    
    def _build_reason(self, method: str, indicators: Dict, news: Dict) -> str:
        """Build human-readable reason"""
        rsi = indicators['rsi']
        trend = indicators['trend']
        vol_ratio = indicators['volume_ratio']
        
        if method == 'mean_reversion':
            if rsi < 30:
                return f"RSI oversold ({rsi:.1f}) + price extension"
            elif rsi > 70:
                return f"RSI overbought ({rsi:.1f}) + mean reversion short"
            else:
                return f"RSI neutral ({rsi:.1f}) + range-bound"
        elif method == 'momentum':
            return f"{trend.title()} momentum (RSI {rsi:.1f}, vol {vol_ratio:.1f}x)"
        else:
            return f"Breakout setup (volume {vol_ratio:.1f}x)"


# ============================================================================
# METHOD BOTS
# ============================================================================

class MethodBots:
    """Executes trades for all three methods"""
    
    def __init__(self, config: BacktestConfig):
        self.config = config
        
        # Initialize strategies
        if STRATEGY_AVAILABLE:
            self.mr_strategy = RSIMeanReversion(config.mean_reversion)
        else:
            self.mr_strategy = None
    
    def execute(self, symbol: str, method: str, coin_data: Dict, 
                decision: Dict, df: pd.DataFrame) -> Optional[Signal]:
        """Execute trade based on method"""
        if method == 'mean_reversion':
            return self._execute_mean_reversion(symbol, coin_data, decision, df)
        elif method == 'momentum':
            return self._execute_momentum(symbol, coin_data, decision, df)
        elif method == 'breakout':
            return self._execute_breakout(symbol, coin_data, decision, df)
        return None
    
    def _execute_mean_reversion(self, symbol: str, coin_data: Dict, 
                                 decision: Dict, df: pd.DataFrame) -> Optional[Signal]:
        """Execute mean reversion trade"""
        if STRATEGY_AVAILABLE and self.mr_strategy:
            try:
                signal = self.mr_strategy.generate_signal(df)
                if signal.direction != 'FLAT':
                    return Signal(
                        direction=signal.direction,
                        entry_price=decision['current_price'],
                        stop_loss=signal.stop_loss,
                        take_profit=signal.take_profit,
                        confidence=decision['best_score'] / 100,
                        metadata={'rsi': signal.metadata.get('rsi'), 'method': 'mean_reversion'}
                    )
            except Exception as e:
                print(f"    MR strategy error: {e}")
        
        # Fallback simplified logic
        indicators = coin_data['ohlcv']['indicators']
        rsi = indicators['rsi']
        price = decision['current_price']
        
        if rsi < 30:
            direction = 'LONG'
            stop_loss = price * 0.97
            take_profit = price * 1.06
        elif rsi > 70:
            direction = 'SHORT'
            stop_loss = price * 1.03
            take_profit = price * 0.94
        else:
            return None
        
        return Signal(
            direction=direction,
            entry_price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=decision['best_score'] / 100,
            metadata={'rsi': rsi, 'method': 'mean_reversion'}
        )
    
    def _execute_momentum(self, symbol: str, coin_data: Dict, 
                          decision: Dict, df: pd.DataFrame) -> Optional[Signal]:
        """Execute momentum trade"""
        indicators = coin_data['ohlcv']['indicators']
        trend = indicators['trend']
        rsi = indicators['rsi']
        price = decision['current_price']
        
        if trend == 'bullish' and rsi > 55:
            direction = 'LONG'
            stop_loss = price * 0.95
            take_profit = price * 1.12
        elif trend == 'bearish' and rsi < 45:
            direction = 'SHORT'
            stop_loss = price * 1.05
            take_profit = price * 0.88
        else:
            return None
        
        return Signal(
            direction=direction,
            entry_price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=decision['best_score'] / 100,
            metadata={'rsi': rsi, 'trend': trend, 'method': 'momentum'}
        )
    
    def _execute_breakout(self, symbol: str, coin_data: Dict, 
                          decision: Dict, df: pd.DataFrame) -> Optional[Signal]:
        """Execute breakout trade"""
        indicators = coin_data['ohlcv']['indicators']
        vol_ratio = indicators['volume_ratio']
        trend = indicators['trend']
        price = decision['current_price']
        
        if vol_ratio > 2 and trend == 'bullish':
            direction = 'LONG'
            stop_loss = price * 0.96
            take_profit = price * 1.10
        elif vol_ratio > 2 and trend == 'bearish':
            direction = 'SHORT'
            stop_loss = price * 1.04
            take_profit = price * 0.90
        else:
            return None
        
        return Signal(
            direction=direction,
            entry_price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=decision['best_score'] / 100,
            metadata={'volume_ratio': vol_ratio, 'trend': trend, 'method': 'breakout'}
        )


# ============================================================================
# BACKTEST ENGINE
# ============================================================================

class CompleteSystemBacktester:
    """Runs complete system backtest"""
    
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.capital = config.initial_capital
        self.positions: List[Position] = []
        self.trades: List[Trade] = []
        self.equity_curve: List[Dict] = []
        self.decisions_log: List[Dict] = []
        self.whale_alerts: List[WhaleAlert] = []
        
        # Initialize components
        self.data_worker = DataWorker(config)
        self.orchestrator = Orchestrator(config)
        self.method_bots = MethodBots(config)
        
        # Stats
        self.stats = {
            'data_cycles': 0,
            'orchestrator_cycles': 0,
            'signals_generated': 0,
            'trades_executed': 0,
            'wins': 0,
            'losses': 0,
        }
    
    def run_backtest(self, data_manager: HistoricalDataManager) -> Dict:
        """Run complete system backtest"""
        print("\n" + "="*80)
        print("RUNNING COMPLETE SYSTEM BACKTEST")
        print("="*80)
        print(f"Period: {self.config.days} days @ {self.config.timeframe}")
        print(f"Coins: {', '.join(self.config.coins)}")
        print(f"Initial Capital: ${self.config.initial_capital}")
        print(f"Max Position: ${self.config.max_position_size}")
        print(f"Fees: {self.config.fee_pct}% | Slippage: {self.config.slippage_pct}%")
        print()
        
        # Get time range
        all_timestamps = []
        for symbol in self.config.coins:
            if symbol in data_manager.data:
                all_timestamps.extend(data_manager.data[symbol].index.tolist())
        
        if not all_timestamps:
            return {'error': 'No data available'}
        
        min_time = min(all_timestamps)
        max_time = max(all_timestamps)
        
        print(f"Data range: {min_time.strftime('%Y-%m-%d')} to {max_time.strftime('%Y-%m-%d')}")
        print(f"Starting simulation...")
        print()
        
        # Simulate time progression
        current_time = min_time
        data_cycle_counter = 0
        orchestrator_cycle_counter = 0
        last_data_output = None
        
        interval_minutes = int(self.config.timeframe.replace('m', ''))
        progress_interval = (max_time - min_time) / 20
        
        while current_time <= max_time:
            # Progress
            if current_time - min_time >= progress_interval * ((len(self.equity_curve) // 100) + 1):
                pct = (current_time - min_time) / (max_time - min_time) * 100
                print(f"  Progress: {pct:.0f}% ({current_time.strftime('%Y-%m-%d %H:%M')})")
            
            # Data Worker cycle
            data_cycle_counter += 1
            if data_cycle_counter >= self.config.data_worker_interval:
                last_data_output = self.data_worker.run_cycle(current_time, data_manager)
                self.whale_alerts.extend(last_data_output.get('alerts', []))
                self.stats['data_cycles'] += 1
                data_cycle_counter = 0
            
            # Orchestrator cycle
            orchestrator_cycle_counter += 1
            if orchestrator_cycle_counter >= self.config.orchestrator_interval and last_data_output:
                orch_output = self.orchestrator.run_cycle(last_data_output)
                
                # Execute BUY signals
                for decision in orch_output['decisions']:
                    if decision['assignment'] == 'BUY':
                        self._execute_signal(current_time, decision, data_manager)
                
                self.decisions_log.append({
                    'timestamp': current_time.isoformat(),
                    **orch_output,
                })
                self.stats['orchestrator_cycles'] += 1
                orchestrator_cycle_counter = 0
            
            # Check position exits
            self._check_position_exits(current_time, data_manager)
            
            # Record equity
            self._record_equity(current_time, data_manager)
            
            # Advance time
            current_time += timedelta(minutes=interval_minutes)
        
        print(f"\n  Progress: 100% - Complete!")
        print()
        
        return self._generate_report()
    
    def _execute_signal(self, timestamp: datetime, decision: Dict, 
                        data_manager: HistoricalDataManager):
        """Execute BUY signal"""
        symbol = decision['symbol']
        method = decision['best_method']
        
        # Check capacity
        if len(self.positions) >= self.config.max_concurrent_positions:
            return
        
        # Get historical data for strategy
        if symbol not in data_manager.data:
            return
        
        df = data_manager.data[symbol]
        mask = df.index <= timestamp
        historical = df[mask].tail(100)
        
        if len(historical) < 50:
            return
        
        # Get coin data from last data worker output
        coin_data = next(
            (c for c in self.decisions_log[-1].get('decisions', []) 
             if c.get('symbol') == symbol),
            None
        )
        
        # Execute via method bot
        signal = self.method_bots.execute(
            symbol, method, 
            {'ohlcv': {'indicators': {
                'rsi': historical['close'].iloc[-1],
                'current_price': historical['close'].iloc[-1],
                'trend': 'bullish' if historical['close'].iloc[-1] > historical['close'].ewm(span=20).mean().iloc[-1] else 'bearish',
                'volume_ratio': 1.0,
            }}},
            decision,
            historical
        )
        
        if signal:
            # Calculate fees and slippage
            fee = self.config.max_position_size * self.config.fee_pct / 100
            slippage = signal.entry_price * self.config.slippage_pct / 100
            
            entry_price = signal.entry_price + slippage if signal.direction == 'LONG' else signal.entry_price - slippage
            
            # Open position
            position = Position(
                symbol=symbol,
                entry_time=timestamp,
                entry_price=entry_price,
                direction=signal.direction,
                size_usd=self.config.max_position_size - fee,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                method=method,
            )
            
            self.positions.append(position)
            self.stats['trades_executed'] += 1
            
            self.trades.append(Trade(
                type='ENTRY',
                symbol=symbol,
                time=timestamp,
                price=entry_price,
                size_usd=self.config.max_position_size,
                method=method,
                fee=fee,
            ))
            
            self.stats['signals_generated'] += 1
    
    def _check_position_exits(self, timestamp: datetime, data_manager: HistoricalDataManager):
        """Check and execute position exits"""
        for position in self.positions[:]:
            if position.symbol not in data_manager.data:
                continue
            
            df = data_manager.data[position.symbol]
            mask = df.index <= timestamp
            
            if mask.sum() == 0:
                continue
            
            current_price = df[mask].iloc[-1]['close']
            
            # Calculate PnL
            if position.direction == 'LONG':
                pnl_pct = (current_price - position.entry_price) / position.entry_price * 100
            else:
                pnl_pct = (position.entry_price - current_price) / position.entry_price * 100
            
            # Check exit conditions
            exit_reason = None
            
            if position.direction == 'LONG':
                if current_price <= position.stop_loss:
                    exit_reason = 'Stop Loss'
                elif current_price >= position.take_profit:
                    exit_reason = 'Take Profit'
            else:
                if current_price >= position.stop_loss:
                    exit_reason = 'Stop Loss'
                elif current_price <= position.take_profit:
                    exit_reason = 'Take Profit'
            
            # Time-based exit (max 48 hours)
            if timestamp - position.entry_time > timedelta(hours=48):
                exit_reason = 'Time Exit'
            
            if exit_reason:
                # Calculate exit with fees
                fee = position.size_usd * self.config.fee_pct / 100
                pnl_usd = position.size_usd * pnl_pct / 100 - fee
                
                self.capital += pnl_usd
                
                if pnl_usd > 0:
                    self.stats['wins'] += 1
                else:
                    self.stats['losses'] += 1
                
                self.positions.remove(position)
                
                self.trades.append(Trade(
                    type='EXIT',
                    symbol=position.symbol,
                    time=timestamp,
                    price=current_price,
                    pnl_usd=pnl_usd,
                    pnl_pct=pnl_pct,
                    method=position.method,
                    exit_reason=exit_reason,
                    fee=fee,
                ))
    
    def _record_equity(self, timestamp: datetime, data_manager: HistoricalDataManager):
        """Record equity curve point"""
        unrealized_pnl = 0
        
        for position in self.positions:
            if position.symbol not in data_manager.data:
                continue
            
            df = data_manager.data[position.symbol]
            mask = df.index <= timestamp
            
            if mask.sum() == 0:
                continue
            
            current_price = df[mask].iloc[-1]['close']
            
            if position.direction == 'LONG':
                pnl_pct = (current_price - position.entry_price) / position.entry_price * 100
            else:
                pnl_pct = (position.entry_price - current_price) / position.entry_price * 100
            
            unrealized_pnl += position.size_usd * pnl_pct / 100
        
        self.equity_curve.append({
            'timestamp': timestamp,
            'capital': self.capital,
            'unrealized_pnl': unrealized_pnl,
            'total_equity': self.capital + unrealized_pnl,
            'open_positions': len(self.positions),
        })
    
    def _generate_report(self) -> Dict:
        """Generate comprehensive report"""
        trades_df = pd.DataFrame([asdict(t) for t in self.trades if t.type == 'EXIT'])
        equity_df = pd.DataFrame(self.equity_curve)
        
        # Metrics
        total_return = (self.capital - self.config.initial_capital) / self.config.initial_capital * 100
        
        if len(equity_df) > 1 and equity_df['total_equity'].std() > 0:
            equity_df['returns'] = equity_df['total_equity'].pct_change()
            sharpe = equity_df['returns'].mean() / equity_df['returns'].std() * np.sqrt(252 * 24 * 12)  # 5m data
        else:
            sharpe = 0
        
        if len(equity_df) > 0:
            max_equity = equity_df['total_equity'].cummax()
            drawdown = (equity_df['total_equity'] - max_equity) / max_equity * 100
            max_drawdown = drawdown.min()
            calmar = total_return / abs(max_drawdown) if max_drawdown != 0 else 0
        else:
            max_drawdown = 0
            calmar = 0
        
        win_rate = len(trades_df[trades_df['pnl_usd'] > 0]) / len(trades_df) * 100 if len(trades_df) > 0 else 0
        
        if len(trades_df) > 0:
            gross_profit = trades_df[trades_df['pnl_usd'] > 0]['pnl_usd'].sum()
            gross_loss = abs(trades_df[trades_df['pnl_usd'] < 0]['pnl_usd'].sum())
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
            avg_trade = trades_df['pnl_usd'].mean()
        else:
            profit_factor = 0
            avg_trade = 0
        
        # Method breakdown
        method_stats = {}
        for method in ['mean_reversion', 'momentum', 'breakout']:
            method_trades = trades_df[trades_df['method'] == method] if len(trades_df) > 0 else pd.DataFrame()
            if len(method_trades) > 0:
                method_stats[method] = {
                    'trades': len(method_trades),
                    'win_rate': len(method_trades[method_trades['pnl_usd'] > 0]) / len(method_trades) * 100,
                    'avg_pnl': method_trades['pnl_usd'].mean(),
                }
        
        return {
            'config': asdict(self.config),
            'summary': {
                'initial_capital': self.config.initial_capital,
                'final_capital': round(self.capital, 2),
                'total_return_pct': round(total_return, 2),
                'total_trades': len(trades_df),
                'win_rate_pct': round(win_rate, 2),
                'sharpe_ratio': round(sharpe, 2),
                'max_drawdown_pct': round(max_drawdown, 2),
                'calmar_ratio': round(calmar, 2),
                'profit_factor': round(profit_factor, 2) if profit_factor != float('inf') else 'inf',
                'avg_trade_pnl': round(avg_trade, 2),
            },
            'stats': self.stats,
            'method_breakdown': method_stats,
            'whale_alerts': len(self.whale_alerts),
            'trades': [asdict(t) for t in self.trades],
        }


# ============================================================================
# MAIN
# ============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Complete System Backtest')
    parser.add_argument('--days', type=int, default=30, help='Backtest duration')
    parser.add_argument('--timeframe', type=str, default='5m', help='Candle timeframe')
    parser.add_argument('--coins', type=str, default='BTC,ETH,SOL', help='Coins')
    parser.add_argument('--output', type=str, default='backtest_complete.json', help='Output file')
    
    args = parser.parse_args()
    
    config = BacktestConfig(
        coins=[c.strip() for c in args.coins.split(',')],
        timeframe=args.timeframe,
        days=args.days,
    )
    
    print("\n" + "="*80)
    print("COMPLETE TRADING SYSTEM BACKTEST")
    print("="*80)
    print("Components:")
    print("  ✓ Data Worker (whale watching, volume analysis, news sentiment)")
    print("  ✓ Orchestrator (method scoring: MR, Momentum, Breakout)")
    print("  ✓ Mean Reversion Bot (RSI strategy)")
    print("  ✓ Momentum Bot (trend following)")
    print("  ✓ Breakout Bot (consolidation + volume)")
    print("  ✓ Position Management (monitoring, exits)")
    print("  ✓ Realistic Simulation (fees, slippage)")
    print("="*80)
    
    backtester = CompleteSystemBacktester(config)
    
    # Load data
    data_manager = HistoricalDataManager(config.coins, config.days, config.timeframe)
    if not data_manager.fetch_all():
        print("\n✗ Failed to load data")
        sys.exit(1)
    
    # Run backtest
    report = backtester.run_backtest(data_manager)
    
    # Save report
    with open(args.output, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    # Print summary
    print("\n" + "="*80)
    print("BACKTEST RESULTS")
    print("="*80)
    
    summary = report['summary']
    stats = report['stats']
    method_breakdown = report.get('method_breakdown', {})
    
    print(f"\n📊 PERFORMANCE METRICS")
    print(f"  Initial Capital:    ${summary['initial_capital']:.2f}")
    print(f"  Final Capital:      ${summary['final_capital']:.2f}")
    print(f"  Total Return:       {summary['total_return_pct']:+.2f}%")
    print(f"  Sharpe Ratio:       {summary['sharpe_ratio']:.2f}")
    print(f"  Calmar Ratio:       {summary['calmar_ratio']:.2f}")
    print(f"  Max Drawdown:       {summary['max_drawdown_pct']:.2f}%")
    print(f"  Profit Factor:      {summary['profit_factor']}")
    print(f"  Win Rate:           {summary['win_rate_pct']:.1f}%")
    print(f"  Total Trades:       {summary['total_trades']}")
    print(f"  Avg Trade PnL:      ${summary['avg_trade_pnl']:.2f}")
    
    if method_breakdown:
        print(f"\n📈 METHOD BREAKDOWN")
        for method, mstats in method_breakdown.items():
            print(f"  {method.replace('_', ' ').title():20} {mstats['trades']:3} trades | "
                  f"Win: {mstats['win_rate']:5.1f}% | Avg: ${mstats['avg_pnl']:+.2f}")
    
    print(f"\n⚙️ SYSTEM STATISTICS")
    print(f"  Data Worker Cycles:  {stats['data_cycles']:,}")
    print(f"  Orchestrator Cycles: {stats['orchestrator_cycles']:,}")
    print(f"  Signals Generated:   {stats['signals_generated']}")
    print(f"  Trades Executed:     {stats['trades_executed']}")
    print(f"  Wins:                {stats['wins']}")
    print(f"  Losses:              {stats['losses']}")
    print(f"  Whale Alerts:        {report['whale_alerts']}")
    
    print(f"\n💾 Output saved to: {args.output}")
    print("="*80)


if __name__ == '__main__':
    main()
