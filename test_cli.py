#!/usr/bin/env python3
"""
test_cli.py — Run the full Pantheon COO agent loop from the terminal.

Usage:
  python3 test_cli.py "your command here"          # dry run (plan only)
  python3 test_cli.py "your command here" --run    # full execution
  python3 test_cli.py "your command here" --debug  # verbose agent output

Examples:
  python3 test_cli.py "Create a Python script that generates a Fibonacci sequence"
  python3 test_cli.py "List all files in the workspace" --run
  python3 test_cli.py "Write a markdown report on AI trends" --run
"""
import asyncio
import json
import sys
import uuid
from datetime import datetime


async def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("--"):
        print("Usage: python3 test_cli.py 'your command' [--run] [--debug]")
        sys.exit(1)

    command = args[0]
    do_run = "--run" in args
    debug  = "--debug" in args

    print(f"\n{'━'*60}")
    print(f"  Pantheon COO OS v2 — CLI")
    print(f"{'━'*60}")
    print(f"  Command : {command}")
    print(f"  Mode    : {'EXECUTE' if do_run else 'DRY RUN (plan only)'}")
    print(f"{'━'*60}\n")

    # Bootstrap
    import pathlib
    pathlib.Path("/tmp/pantheon_v2").mkdir(parents=True, exist_ok=True)

    import memory.store as store
    await store.init()

    task_id = str(uuid.uuid4())
    await store.create_task(task_id, command, source="cli")

    print(f"  Task ID : {task_id[:8]}...\n")

    # ── Reasoning ────────────────────────────────────────────────────
    print("▶ Reasoning Agent thinking...")
    from agents.memory_agent import recall_relevant
    from agents.reasoning import ReasoningAgent
    from models import ReasoningInput

    snippets = await recall_relevant("general", limit=3)
    reasoning = await ReasoningAgent().run(
        ReasoningInput(raw_goal=command, memory_snippets=snippets)
    )

    print(f"  Goal     : {reasoning.understood_goal}")
    print(f"  Type     : {reasoning.goal_type}  |  Complexity: {reasoning.complexity}")
    if reasoning.risks:
        print(f"  Risks    : {', '.join(reasoning.risks[:2])}")
    print(f"  Criteria : {len(reasoning.success_criteria)} defined")

    if reasoning.clarifications_needed:
        print(f"\n  ⚠ Clarifications needed: {reasoning.clarifications_needed}")

    # ── Planning ─────────────────────────────────────────────────────
    print("\n▶ Planning Agent generating steps...")
    from agents.planner import PlanningAgent
    from models import PlanningInput

    plan_snippets = await recall_relevant(reasoning.goal_type, limit=3)
    plan = await PlanningAgent().run(PlanningInput(reasoning=reasoning, memory_snippets=plan_snippets))

    print(f"  {len(plan.steps)} steps planned — {plan.goal_summary}")
    if plan.notes:
        print(f"  Notes: {plan.notes}")

    print()
    for s in plan.steps:
        dep = f"  [after {s.depends_on}]" if s.depends_on else ""
        print(f"  Step {s.step_id:2}  [{s.tool.value}] {s.action}{dep}")
        print(f"          {s.description}")
        if debug:
            print(f"          params: {json.dumps(s.params)}")

    if not do_run:
        print(f"\n  DRY RUN complete. Use --run to execute.\n{'━'*60}\n")
        return

    # ── Execution ────────────────────────────────────────────────────
    print("\n▶ Execution Agent running steps...")
    from agents.executor import ExecutionAgent
    from models import ExecutionInput

    execution = await ExecutionAgent().run(ExecutionInput(task_id=task_id, plan=plan))

    for r in execution.results:
        icon = "✅" if r.status.value == "success" else ("⏭" if r.status.value == "skipped" else "❌")
        print(f"  {icon} Step {r.step_id}: {r.status.value}")
        if r.result and debug:
            print(f"     → {json.dumps(r.result, default=str)[:200]}")
        if r.error:
            print(f"     ✗ {r.error}")

    # ── Evaluation ───────────────────────────────────────────────────
    print("\n▶ Evaluator Agent scoring...")
    from agents.evaluator import EvaluatorAgent
    from models import EvaluatorInput

    evaluation = await EvaluatorAgent().run(
        EvaluatorInput(
            goal=reasoning.understood_goal,
            success_criteria=reasoning.success_criteria,
            plan=plan,
            execution=execution,
        )
    )

    bar = "█" * int(evaluation.score * 20) + "░" * (20 - int(evaluation.score * 20))
    print(f"  Score  : [{bar}] {evaluation.score:.2f}")
    print(f"  Verdict: {'✅ GOAL MET' if evaluation.goal_met else '⚠  GOAL NOT FULLY MET'}")
    print(f"  Summary: {evaluation.summary}")

    if evaluation.what_failed:
        print(f"  Failed : {evaluation.what_failed}")
    if evaluation.improvement_hints:
        print(f"  Hints  : {evaluation.improvement_hints[0]}")

    # ── Memory ───────────────────────────────────────────────────────
    print("\n▶ Memory Agent storing learning...")
    from agents.memory_agent import MemoryAgent
    from models import MemoryInput

    mem_out = await MemoryAgent().run(MemoryInput(
        task_id=task_id, goal=reasoning.understood_goal,
        goal_type=reasoning.goal_type, plan=plan,
        execution=execution, evaluation=evaluation,
    ))
    print(f"  Stored : {mem_out.learning[:100]}...")

    # ── Final status ─────────────────────────────────────────────────
    final = "DONE" if evaluation.goal_met else "NEEDS RETRY"
    await store.update_status(
        task_id,
        from_str("done" if evaluation.goal_met else "failed"),
        summary=evaluation.summary,
        eval_score=evaluation.score,
        iterations=1,
        results_json=json.dumps([r.model_dump() for r in execution.results], default=str),
    )

    print(f"\n{'━'*60}")
    print(f"  Result  : {final}")
    print(f"  Task ID : {task_id[:8]}")
    print(f"{'━'*60}\n")


def from_str(s):
    from models import TaskStatus
    return TaskStatus(s)


if __name__ == "__main__":
    asyncio.run(main())
