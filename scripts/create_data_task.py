#!/usr/bin/env python3
"""
Cron Job: Create Data Collection Kanban Task

Runs every 5 minutes, creates a Kanban task for trading-data profile.
"""

from kanban import kanban_create

def main():
    task = kanban_create(
        title='Data Collection - BTC/ETH/SOL',
        assignee='trading-data',
        body='''Run the Data Worker to collect market data for BTC, ETH, SOL.

Working directory: /mnt/data/hermes/workspace/trading_system

Execute:
```python
from data_worker import run_data_collection_cycle
from kanban import kanban_complete

result = run_data_collection_cycle(['BTC', 'ETH', 'SOL'])

# Report to Kanban
kanban_complete(
    summary=f"Data collected: {result['summary']['coins_processed']} coins, {result['summary']['alerts_triggered']} alerts",
    output={
        'task': 'data_collection',
        'success': result['success'],
        'summary': result['summary'],
        'coin_data': result['coin_data'],
        'alerts': result['alerts']
    }
)

# Alert user if needed
if result['alerts']:
    from telegram import send_message
    alert_text = "\\n".join([f"{a['symbol']}: {a['reason']}" for a in result['alerts']])
    send_message(f"🚨 Trading Alert:\\n{alert_text}")
```
''',
    )
    
    print(f"Created Kanban task: {task['task_id']}")

if __name__ == '__main__':
    main()
