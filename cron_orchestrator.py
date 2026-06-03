#!/usr/bin/env python3
"""
Orchestrator Cron Job - Creates Kanban Task

This script is called by Cron every 15 minutes.
Instead of running the orchestration directly, it creates a Kanban task
that will be executed by the trading-orchestrator profile.

Flow:
1. Cron triggers this script
2. Creates Kanban task: "Orchestrator Cycle"
3. Assigns to trading-orchestrator profile
4. Profile's SOUL.md instructs it to:
   - Create child task for Data Worker discovery
   - Wait for completion
   - Evaluate coins
   - Create Method Bot child tasks
   - Complete silently (or 2-hr summary)
"""

import json
from datetime import datetime, timezone
from pathlib import Path
import sys

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent))

def create_orchestrator_task():
    """Create Kanban task for Orchestrator cycle"""
    
    try:
        from kanban import kanban_create
        
        print("\n📋 Creating Orchestrator Kanban task...")
        
        task = kanban_create(
            title=f"Orchestrator Cycle - {datetime.now(timezone.utc).strftime('%H:%M UTC')}",
            description="""
ORCHESTRATOR CYCLE

You are the brain of the trading system. Execute the full orchestration flow:

## Step 1: Request Coin Discovery
Create a child Kanban task for the Data Worker to discover coins:
- Assignee: trading-data
- Instruction: "Scan 15 candidates, rank by opportunity score, select top 3-5"
- Wait for task completion (poll every 5s, timeout 120s)
- Read discovery report from task output

## Step 2: Evaluate Discovered Coins
For each coin in the discovery report:
- Calculate Mean Reversion score (RSI-based)
- Calculate Momentum score (trend-based)
- Calculate Breakout score (volume-based)
- Select best method
- If best score >= 60: Create Method Bot child task

## Step 3: Create Method Bot Tasks
For each BUY signal (score >= 60):
- Create child task assigned to trading-{method} profile
- Include metadata: symbol, entry, stop_loss, take_profit
- Method Bot will execute and report to Gateway

## Step 4: Complete Cycle
- If this is a 2-hour update cycle: Send summary to Gateway
- Otherwise: Complete silently (no Telegram message)
- Save results to reports/orchestration_{timestamp}.json

## Discovery Criteria (for reference)
- Volume (40%): $5M = 40 pts, $50M+ = 100 pts
- Volatility (30%): 5% move = 100 pts
- Whale (20%): Volume >$50M = +20, Move >5% = +15
- News (10%): Neutral = 50 pts
- Minimum score: 50
- Max coins to select: 5

## Method Scoring Thresholds
- BUY signal: best method score >= 60
- HOLD: best method score < 60

Complete with: kanban_complete(output=results, silent=True)
            """,
            assignee='trading-orchestrator',
            metadata={
                'task_type': 'orchestrator_cycle',
                'trigger': 'cron_15min',
                'created_at': datetime.now(timezone.utc).isoformat(),
            }
        )
        
        print(f"✓ Orchestrator task created: {task['id']}")
        print(f"  Assignee: {task.get('assignee', 'N/A')}")
        print(f"  Status: {task.get('status', 'N/A')}")
        
        return task
    
    except ImportError as e:
        print(f"✗ Kanban module not available: {e}")
        print("  Running in standalone mode (direct execution)")
        return run_standalone_orchestration()
    
    except Exception as e:
        print(f"✗ Error creating task: {e}")
        return None


def run_standalone_orchestration():
    """Fallback: run orchestration directly if Kanban not available"""
    
    print("\n⚠ Running standalone orchestration (no Kanban)")
    
    # Import and run orchestrator
    from orchestrator_kanban import KanbanOrchestrator, complete_orchestrator_task
    
    orchestrator = KanbanOrchestrator()
    results = orchestrator.run_orchestration_cycle()
    complete_orchestrator_task(results)
    
    return results


if __name__ == '__main__':
    print("\n" + "="*70)
    print("ORCHESTRATOR CRON JOB")
    print("="*70)
    print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    task = create_orchestrator_task()
    
    if task:
        print("\n✅ Orchestrator cycle initiated")
        print("   Next: Data Worker will discover coins (child task)")
    else:
        print("\n✗ Failed to initiate orchestrator cycle")
    
    print("="*70)
