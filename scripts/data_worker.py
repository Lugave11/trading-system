#!/usr/bin/env python3
"""
Data Worker - Standalone Script for Cron Job

Runs every 5 minutes, outputs JSON for Kanban handoff.
"""

import sys
import json
from datetime import datetime, timezone
from pathlib import Path

# Add trading_system to path
sys.path.insert(0, str(Path(__file__).parent))

from data_worker import run_data_collection_cycle

def main():
    """Run data collection and output JSON."""
    result = run_data_collection_cycle(['BTC', 'ETH', 'SOL'])
    
    # Output JSON for cron job to capture
    output = {
        'task': 'data_collection',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'success': result['success'],
        'summary': result['summary'],
        'coin_data': result['coin_data'],
        'alerts': result['alerts'],
    }
    
    print(json.dumps(output, indent=2, default=str))
    
    # Return exit code based on success
    return 0 if result['success'] else 1

if __name__ == '__main__':
    sys.exit(main())
