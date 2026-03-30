"""
Agent package — lazy exports so `import agents.evaluator` does not load tools/executor.
"""
from __future__ import annotations

__all__ = [
    "ReasoningAgent",
    "PlanningAgent",
    "ExecutionAgent",
    "EvaluatorAgent",
    "MemoryAgent",
]


def __getattr__(name: str):
    if name == "ReasoningAgent":
        from agents.reasoning import ReasoningAgent

        return ReasoningAgent
    if name == "PlanningAgent":
        from agents.planner import PlanningAgent

        return PlanningAgent
    if name == "ExecutionAgent":
        from agents.executor import ExecutionAgent

        return ExecutionAgent
    if name == "EvaluatorAgent":
        from agents.evaluator import EvaluatorAgent

        return EvaluatorAgent
    if name == "MemoryAgent":
        from agents.memory_agent import MemoryAgent

        return MemoryAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(__all__)
