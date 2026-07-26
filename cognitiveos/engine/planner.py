"""Planner — the abstraction for goal-directed planning.

Ported from monkeypatched's kernel/pipeline/planner.py, with the import path
adjusted to this package. Otherwise unmodified.

The planner consumes BeliefState and Goal, and produces a Plan.
The engine depends only on this interface.

Different planners can be swapped in:
- DeterministicPlanner (default: fact-based planning)
- GraphPlanner (world graph traversal)
- GOAP (Goal-Oriented Action Planning)
- HTN (Hierarchical Task Network)
- LLMPlanner (LLM-assisted planning)
- SATPlanner (constraint satisfaction)
- RLPlanner (reinforcement learning)

The engine never knows which planner is active.
"""
from __future__ import annotations

from typing import Any, Protocol

from cognitiveos.engine.belief_state import BeliefState, Goal, Plan


class PlanningEngine(Protocol):
    """Protocol for anything that produces plans.

    The engine depends only on this interface.
    Implementations can be deterministic, probabilistic, or LLM-based.
    """

    def plan(
        self,
        belief: BeliefState,
        goal: Goal,
        context: Any = None,
    ) -> Plan:
        """Generate a plan from the current belief state and goal.

        Args:
            belief: The actor's current belief state (facts, hypotheses, confidence)
            goal: What the actor wants to achieve
            context: Optional runtime context (services, constraints)

        Returns:
            A structured Plan describing what to do
        """
        ...
