"""
pattern_detector.py
────────────────────
Phase 3 — Pattern Detector

Runs after every task completion and asks:
  "Have we done this sequence of steps 3+ times? Should we build a tool for it?"

How it works:
  1. After execution, extract the step sequence (tool+action pairs) from the plan
  2. Normalize and fingerprint the sequence
  3. Store in task_patterns table
  4. Query for sequences repeated >= PATTERN_THRESHOLD times
  5. If a new repeated pattern is found, signal the Tool Builder Agent

The detector uses structural pattern matching — it ignores specific param values
and looks at the *shape* of what was done: [filesystem.write_file, terminal.run_command, ...]
"""
from __future__ import annotations
import json
import hashlib
from typing import Optional

from models import PlanningOutput
import memory.store as store

PATTERN_THRESHOLD = 3   # min times a sequence must repeat to trigger tool building


def _fingerprint(plan: PlanningOutput) -> str:
    """
    Create a normalized fingerprint of a step sequence.
    Ignores params (specific values), focuses on tool+action shape.
    """
    steps = [(s.tool.value, s.action) for s in plan.steps]
    raw = json.dumps(steps)
    return hashlib.md5(raw.encode()).hexdigest()[:12] + "::" + raw


async def record_and_detect(
    task_id: str,
    goal_type: str,
    plan: PlanningOutput,
) -> Optional[str]:
    """
    Record the plan's step pattern, then check if it's repeated enough
    to warrant tool building.

    Returns the repeated step_sequence string if a new pattern threshold
    is crossed, otherwise None.
    """
    if not plan.steps:
        return None

    fingerprint = _fingerprint(plan)
    await store.record_pattern(task_id, goal_type, fingerprint)

    # Check for newly-crossed threshold
    patterns = await store.get_repeated_patterns(min_occurrences=PATTERN_THRESHOLD)

    for p in patterns:
        if p["step_sequence"] == fingerprint:
            # Only trigger once — check if we already have a tool for this pattern
            existing = await store.get_custom_tools()
            already_built = any(t["trigger_pattern"] == fingerprint for t in existing)
            if not already_built:
                return fingerprint  # Signal: build a tool for this

    return None


def describe_pattern(fingerprint: str) -> str:
    """Extract a human-readable description of a pattern from its fingerprint."""
    try:
        raw = fingerprint.split("::", 1)[1]
        steps = json.loads(raw)
        return " → ".join(f"{tool}.{action}" for tool, action in steps)
    except Exception:
        return fingerprint[:60]
