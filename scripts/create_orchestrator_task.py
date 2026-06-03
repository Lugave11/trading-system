#!/usr/bin/env python3
"""
Cron Job: Create Orchestrator Kanban Task

Runs every 15 minutes, creates a Kanban task for trading-orchestrator profile.
"""

from kanban import kanban_create, kanban_list

def main():
    # Find latest completed Data Collection task
    tasks = kanban_list(assignee='trading-data', status='completed', limit=1)
    
    if not tasks:
        print("No completed Data Collection tasks found")
        return
    
    latest_data_task = tasks[0]
    print(f"Found latest data task: {latest_data_task['id']}")
    
    # Create Orchestrator task
    task = kanban_create(
        title='Make Trading Decisions',
        assignee='trading-orchestrator',
        parent=latest_data_task['id'],
        body='''Run the Orchestrator to make trading decisions based on latest market data.

Read the parent task's output (Data Collection) and execute the orchestrator.

Report decisions via kanban_complete() and create execution tasks for any BUY signals.
''',
    )
    
    print(f"Created Orchestrator task: {task['task_id']}")

if __name__ == '__main__':
    main()
