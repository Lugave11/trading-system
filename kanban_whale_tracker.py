#!/usr/bin/env python3
"""
Kanban-Integrated Whale Tracker

Tracks whale movements for:
1. TOP 10 tokens by market cap (ex-stablecoins)
2. Portfolio coins from coin_universe.json

Creates Kanban tasks automatically for:
- MAJOR moves (>$5M)
- BEARISH signals (large exchange inflows)
- BULLISH signals (large exchange outflows)

Usage:
  python3 kanban_whale_tracker.py
"""

import os
import sys
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

# Add trading_system to path
sys.path.insert(0, '/mnt/data/hermes/workspace/trading_system')

# Import base tracker
from top10_whale_tracker import Top10WhaleTracker, TOP_10_TOKENS, WHALE_WALLETS, TOKEN_PRICES

# ===== CONFIGURATION =====

# Load portfolio coins
def load_portfolio() -> List[str]:
    """Load coins from coin_universe.json"""
    config_path = Path('/mnt/data/hermes/workspace/trading_system/state/coin_universe.json')
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config.get('coins', [])
    return []

# ERC-20 contracts for portfolio coins (if they exist on Ethereum)
PORTFOLIO_CONTRACTS = {
    'BTC': '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599',  # WBTC
    'ETH': None,  # Native ETH
    'SOL': None,  # No major ERC-20 (Solana is separate chain)
    'BNB': '0xB8c77482e45F1F44dE1745F52C74426C631bDD52',
    'XRP': None,  # No major ERC-20
    'ADA': '0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47',
    'AVAX': '0x85f138bfEE4ef8e540890CFb48F620571d67Eda3',
    'MATIC': '0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0',
    'DOT': '0x7083609fCE4d1d8Dc0C979AAb8c869Ea2C873402',
    'LINK': '0x514910771af9ca656af840dff83e8264ecf986ca',
    'UNI': '0x1f9840a85d5af5bf1d1762f925bdaddc4201f984',
    'ATOM': None,  # Cosmos native
    'DOGE': None,  # No major ERC-20
    'LTC': '0x6c6EE5e31d828De241282B9606C8e98Ea48526E2',
    'BCH': None,  # No major ERC-20
}

# Kanban thresholds
KANBAN_THRESHOLDS = {
    'MAJOR': 5_000_000,      # >$5M always creates task
    'BEARISH': 2_000_000,    # >$2M exchange inflow
    'BULLISH': 2_000_000,    # >$2M exchange outflow
    'PORTFOLIO': 1_000_000,  # >$1M for portfolio coins (lower threshold)
}


class KanbanWhaleTracker(Top10WhaleTracker):
    """Extended tracker with Kanban integration"""
    
    def __init__(self, api_key: str = None):
        super().__init__(api_key)
        self.portfolio_coins = load_portfolio()
        print(f"📋 Portfolio coins: {', '.join(self.portfolio_coins)}")
    
    def scan_portfolio_wallets(self) -> List[Dict]:
        """
        Scan additional wallets specific to portfolio coins.
        For now, uses same whale wallets but filters by portfolio coins.
        In future, can add coin-specific whale addresses.
        """
        print(f"\n🔍 Scanning for PORTFOLIO COIN movements...")
        print(f"   Coins: {', '.join(self.portfolio_coins)}")
        print()
        
        portfolio_signals = []
        
        for address, label in WHALE_WALLETS.items():
            # Get all token transfers
            token_txs = self.get_token_transfers(address, limit=20)
            
            for tx in token_txs[:10]:
                symbol = tx.get('tokenSymbol', '')
                
                # Only track if in portfolio
                if symbol in self.portfolio_coins or symbol == 'ETH':
                    analysis = self.analyze_transfer(tx, symbol)
                    if analysis:
                        # Lower threshold for portfolio coins
                        if analysis['value_usd'] > KANBAN_THRESHOLDS['PORTFOLIO']:
                            analysis['is_portfolio'] = True
                            portfolio_signals.append(analysis)
            
            # Rate limit
            time.sleep(0.3)
        
        return portfolio_signals
    
    def create_kanban_task(self, signal: Dict) -> Optional[str]:
        """
        Create a Kanban task for a significant whale movement.
        Returns task ID if created, None if skipped.
        """
        symbol = signal['symbol']
        value_usd = signal['value_usd']
        signal_type = signal['signal']
        
        # Determine task priority and type
        if signal_type == 'MAJOR' or value_usd > KANBAN_THRESHOLDS['MAJOR']:
            priority = '🔴 HIGH'
            task_type = 'MAJOR_WHALE_MOVE'
        elif signal_type == 'BEARISH':
            priority = '🟠 MEDIUM'
            task_type = 'BEARISH_SIGNAL'
        elif signal_type == 'BULLISH':
            priority = '🟢 LOW'
            task_type = 'BULLISH_SIGNAL'
        else:
            return None  # Skip neutral signals
        
        # Build task title
        from_name = signal['from_label'] or 'Unknown Whale'
        to_name = signal['to_label'] or 'Unknown Wallet'
        
        title = f"🐋 {signal_type}: ${value_usd:,.0f} {symbol} - {from_name[:20]}... → {to_name[:20]}..."
        
        # Build task body
        body = f"""
## 🚨 WHALE ALERT - {signal_type}

**Token:** {symbol}
**Value:** ${value_usd:,.2f} USD
**Timestamp:** {datetime.fromtimestamp(signal['timestamp'], tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}

### Movement Details
- **From:** `{signal['from']}` ({from_name})
- **To:** `{signal['to']}` ({to_name})
- **Transaction:** [`{signal['tx_hash'][:10]}...`](https://etherscan.io/tx/{signal['tx_hash']})
- **Block:** {signal['block']}

### Signal Analysis
- **Type:** {signal_type}
- **From Exchange:** {'Yes' if signal['from_exchange'] else 'No'}
- **To Exchange:** {'Yes' if signal['to_exchange'] else 'No'}
- **Portfolio Coin:** {'Yes' if signal.get('is_portfolio') else 'No'}

### Recommended Action
"""
        
        if signal_type == 'BEARISH':
            body += """
**⚠️ POTENTIAL SELLING PRESSURE**

1. Monitor price action for next 1-4 hours
2. Check if this is part of a series of inflows
3. Consider reducing exposure if multiple bearish signals
4. Set tighter stop-losses on {symbol} positions
""".format(symbol=symbol)
        elif signal_type == 'BULLISH':
            body += """
**✅ ACCUMULATION SIGNAL**

1. Monitor for follow-up buying
2. Check if exchange reserves are decreasing
3. Consider this a confirmation for long positions
4. Watch for breakout above key resistance
""".format(symbol=symbol)
        else:  # MAJOR
            body += """
**🔍 SIGNIFICANT MOVEMENT - INVESTIGATE**

1. Determine if this is exchange internal transfer or external
2. Check news/catalysts for {symbol}
3. Monitor for follow-up transactions
4. Assess impact on market sentiment
""".format(symbol=symbol)
        
        # Create task via Hermes CLI
        try:
            cmd = [
                '/mnt/data/hermes/workspace/.local/bin/hermes',
                'kanban', 'create',
                title,
                '--body', body,
                '--assignee', 'trading-data',
                '--metadata', json.dumps({
                    'task_type': task_type,
                    'signal': signal,
                    'symbol': symbol,
                    'value_usd': value_usd,
                    'tx_hash': signal['tx_hash'],
                })
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                # Extract task ID from output
                output = result.stdout.strip()
                if 'Created' in output:
                    task_id = output.split()[-1]
                    print(f"   ✅ Created Kanban task: {task_id}")
                    return task_id
            
            print(f"   ⚠️  Task creation failed: {result.stderr[:100] if result.stderr else 'Unknown error'}")
            return None
            
        except Exception as e:
            print(f"   ❌ Error creating task: {e}")
            return None
    
    def scan_and_create_tasks(self) -> Dict:
        """
        Full scan + Kanban task creation.
        Returns summary of actions taken.
        """
        print("="*80)
        print("KANBAN WHALE TRACKER - FULL SCAN")
        print("="*80)
        
        # Get prices
        print("\n📊 Fetching prices...")
        self.get_eth_price()
        print(f"   BTC: ${self.token_prices['BTC']:,.0f}")
        print(f"   ETH: ${self.eth_price:,.2f}")
        
        # Scan TOP 10
        print("\n" + "-"*80)
        top10_signals = self.scan_all_whales()
        
        # Scan portfolio-specific
        print("\n" + "-"*80)
        portfolio_signals = self.scan_portfolio_wallets()
        
        # Combine and deduplicate
        all_signals = top10_signals + portfolio_signals
        
        # Remove duplicates (same tx_hash)
        seen_hashes = set()
        unique_signals = []
        for s in all_signals:
            if s['tx_hash'] not in seen_hashes:
                seen_hashes.add(s['tx_hash'])
                unique_signals.append(s)
        
        print(f"\n{'='*80}")
        print(f"SCAN SUMMARY")
        print(f"{'='*80}")
        print(f"Total signals found: {len(unique_signals)}")
        
        # Create Kanban tasks for significant signals
        tasks_created = []
        
        print(f"\n📋 Creating Kanban tasks for significant movements...")
        
        for signal in sorted(unique_signals, key=lambda x: x['value_usd'], reverse=True):
            # Check if should create task
            should_create = False
            reason = ""
            
            if signal['signal'] == 'MAJOR' or signal['value_usd'] > KANBAN_THRESHOLDS['MAJOR']:
                should_create = True
                reason = "MAJOR move (>$5M)"
            elif signal['signal'] == 'BEARISH' and signal['value_usd'] > KANBAN_THRESHOLDS['BEARISH']:
                should_create = True
                reason = "Bearish signal (>$2M)"
            elif signal['signal'] == 'BULLISH' and signal['value_usd'] > KANBAN_THRESHOLDS['BULLISH']:
                should_create = True
                reason = "Bullish signal (>$2M)"
            elif signal.get('is_portfolio') and signal['value_usd'] > KANBAN_THRESHOLDS['PORTFOLIO']:
                should_create = True
                reason = "Portfolio coin (>$1M)"
            
            if should_create:
                print(f"\n   Creating task for: {reason}")
                print(f"   • {signal['symbol']} ${signal['value_usd']:,.0f} - {signal['signal']}")
                
                task_id = self.create_kanban_task(signal)
                if task_id:
                    tasks_created.append({
                        'task_id': task_id,
                        'signal': signal,
                        'reason': reason,
                    })
        
        # Summary
        print(f"\n{'='*80}")
        print(f"FINAL SUMMARY")
        print(f"{'='*80}")
        print(f"Signals scanned: {len(unique_signals)}")
        print(f"Kanban tasks created: {len(tasks_created)}")
        
        if tasks_created:
            print(f"\n📋 TASKS CREATED:")
            for task in tasks_created:
                signal = task['signal']
                print(f"  • {task['task_id']} | {signal['symbol']} ${signal['value_usd']:,.0f} | {task['reason']}")
        
        # Save report
        self.save_kanban_report(unique_signals, tasks_created)
        
        print(f"\n{'='*80}")
        
        return {
            'signals': unique_signals,
            'tasks_created': tasks_created,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
    
    def save_kanban_report(self, signals: List[Dict], tasks: List[Dict]):
        """Save comprehensive report with task links"""
        report_dir = Path('/mnt/data/hermes/workspace/trading_system/whale_reports')
        report_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Generate markdown report
        report_lines = [
            "🐋 **KANBAN WHALE TRACKER REPORT**",
            f"_Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
            "",
            f"## 📊 SCAN SUMMARY",
            f"- Total signals: {len(signals)}",
            f"- Kanban tasks created: {len(tasks)}",
            "",
        ]
        
        # List tasks
        if tasks:
            report_lines.append("## 📋 KANBAN TASKS CREATED")
            report_lines.append("")
            for task in tasks:
                signal = task['signal']
                report_lines.append(f"### {task['task_id']} - {signal['symbol']} ${signal['value_usd']:,.0f}")
                report_lines.append(f"- **Type:** {task['reason']}")
                report_lines.append(f"- **Signal:** {signal['signal']}")
                report_lines.append(f"- **From:** {signal['from_label'] or signal['from'][:20]}")
                report_lines.append(f"- **To:** {signal['to_label'] or signal['to'][:20]}")
                report_lines.append(f"- **TX:** [{signal['tx_hash'][:10]}...](https://etherscan.io/tx/{signal['tx_hash']})")
                report_lines.append("")
        
        # Save
        md_path = report_dir / f'kanban_whale_{timestamp}.md'
        with open(md_path, 'w') as f:
            f.write('\n'.join(report_lines))
        
        # Save JSON
        json_path = report_dir / f'kanban_whale_{timestamp}.json'
        with open(json_path, 'w') as f:
            json.dump({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'signals': signals,
                'tasks_created': tasks,
            }, f, indent=2, default=str)
        
        print(f"💾 Report saved: {md_path.name}")


def main():
    """Main entry point"""
    tracker = KanbanWhaleTracker()
    result = tracker.scan_and_create_tasks()
    return result


if __name__ == '__main__':
    result = main()
    
    # Exit with status
    if result['tasks_created']:
        print(f"\n✅ Scan complete - {len(result['tasks_created'])} Kanban tasks created")
        sys.exit(0)
    else:
        print(f"\n✅ Scan complete - No significant movements requiring Kanban tasks")
        sys.exit(0)
