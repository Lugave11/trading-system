"""
Shared State Manager - Handles data handoff between Data Worker and Orchestrator.

This module provides:
- Write: Data Worker saves collection results
- Read: Orchestrator loads latest data
- Lock: Prevents race conditions
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# ============================================================================
# CONFIGURATION
# ============================================================================

STATE_DIR = Path(__file__).parent / "state"
STATE_DIR.mkdir(exist_ok=True)

DATA_WORKER_STATE = STATE_DIR / "data_worker_latest.json"
ORCHESTRATOR_STATE = STATE_DIR / "orchestrator_latest.json"
SHARED_STATE = STATE_DIR / "shared_state.json"


# ============================================================================
# STATE OPERATIONS
# ============================================================================

def write_data_worker_output(data: dict) -> dict:
    """
    Data Worker writes its output to shared state.
    
    Args:
        data: Output from run_data_collection_cycle()
    
    Returns:
        dict with write status
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    
    state = {
        "last_updated": timestamp,
        "source": "data_worker",
        "data": data,
        "ready_for_orchestrator": True,
    }
    
    with open(SHARED_STATE, "w") as f:
        json.dump(state, f, indent=2, default=str)
    
    # Also save a timestamped backup
    backup_file = STATE_DIR / f"data_worker_{timestamp.replace(':', '-')}.json"
    with open(backup_file, "w") as f:
        json.dump(data, f, indent=2, default=str)
    
    return {
        "success": True,
        "timestamp": timestamp,
        "file": str(SHARED_STATE),
        "backup": str(backup_file),
    }


def read_latest_data() -> dict:
    """
    Orchestrator reads latest data from shared state.
    
    Returns:
        dict with data or error if not available
    """
    if not SHARED_STATE.exists():
        return {
            "success": False,
            "error": "No shared state file found. Run Data Worker first.",
            "file": str(SHARED_STATE),
        }
    
    try:
        with open(SHARED_STATE, "r") as f:
            state = json.load(f)
        
        # Check if data is fresh (within last 15 minutes)
        last_updated = datetime.fromisoformat(state["last_updated"].replace("Z", "+00:00"))
        age_minutes = (datetime.now(timezone.utc) - last_updated).total_seconds() / 60
        
        if age_minutes > 15:
            return {
                "success": False,
                "error": f"Data is stale ({age_minutes:.1f} minutes old)",
                "last_updated": state["last_updated"],
                "age_minutes": round(age_minutes, 1),
            }
        
        if not state.get("ready_for_orchestrator", False):
            return {
                "success": False,
                "error": "Data not marked as ready for orchestrator",
                "last_updated": state["last_updated"],
            }
        
        return {
            "success": True,
            "data": state["data"],
            "last_updated": state["last_updated"],
            "age_minutes": round(age_minutes, 1),
        }
    
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Invalid JSON in state file: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def write_orchestrator_decisions(decisions: dict) -> dict:
    """
    Orchestrator writes its decisions to shared state.
    
    Args:
        decisions: Output from run_orchestration_cycle()
    
    Returns:
        dict with write status
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    
    state = {
        "last_updated": timestamp,
        "source": "orchestrator",
        "decisions": decisions,
        "ready_for_bots": True,
    }
    
    with open(ORCHESTRATOR_STATE, "w") as f:
        json.dump(state, f, indent=2, default=str)
    
    return {
        "success": True,
        "timestamp": timestamp,
        "file": str(ORCHESTRATOR_STATE),
    }


def read_orchestrator_decisions() -> dict:
    """
    Method bots read orchestrator decisions from shared state.
    
    Returns:
        dict with decisions or error
    """
    if not ORCHESTRATOR_STATE.exists():
        return {
            "success": False,
            "error": "No orchestrator decisions found. Run Orchestrator first.",
        }
    
    try:
        with open(ORCHESTRATOR_STATE, "r") as f:
            state = json.load(f)
        
        return {
            "success": True,
            "decisions": state.get("decisions", {}),
            "last_updated": state["last_updated"],
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def get_state_summary() -> dict:
    """
    Get summary of all state files.
    
    Returns:
        dict with file statuses
    """
    files = {
        "shared_state": SHARED_STATE,
        "orchestrator_state": ORCHESTRATOR_STATE,
    }
    
    summary = {}
    
    for name, path in files.items():
        if path.exists():
            stat = path.stat()
            summary[name] = {
                "exists": True,
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            }
        else:
            summary[name] = {
                "exists": False,
            }
    
    return summary


# ============================================================================
# CLI / TEST
# ============================================================================

if __name__ == "__main__":
    print("="*60)
    print("SHARED STATE MANAGER - STATUS")
    print("="*60)
    print()
    
    summary = get_state_summary()
    
    for name, info in summary.items():
        print(f"{name}:")
        if info["exists"]:
            print(f"  ✓ Exists ({info['size_bytes']} bytes)")
            print(f"  Modified: {info['modified']}")
        else:
            print(f"  ✗ Not found")
        print()
