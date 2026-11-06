"""Pytest configuration for FinOps Sync Agent test suite.

Ensures fabric-integration/sync-agent and fabric-integration/lakehouse are in sys.path.
"""

import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent
LAKEHOUSE_DIR = AGENT_DIR.parent / "lakehouse"

for p in [AGENT_DIR, LAKEHOUSE_DIR]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
