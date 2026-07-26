"""Action Execution — plans become real actions through the Capability Bus.

Ported from monkeypatched's kernel/pipeline/execution.py, unmodified except
for this header.

Plan → Action → ExecutionEngine → CapabilityBus → Outcome

The runtime coordinates execution. It does not implement capabilities.
The ExecutionEngine discovers and invokes capabilities via the CapabilityBus.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Action:
    """A single executable action produced from a plan step.

    Actions are immutable — they describe WHAT to do, not the result.
    """
    action_id: str = ""
    """Unique identifier for this action."""
    capability: str = ""
    """Which capability to invoke (e.g. 'find_item', 'add_to_cart')."""
    parameters: dict[str, Any] = field(default_factory=dict)
    """Parameters for the capability."""
    preconditions: tuple[str, ...] = ()
    """What must be true before execution."""
    expected_outcome: str = ""
    """What this action is expected to achieve."""
    confidence: float = 0.0
    """Confidence in this action. [0.0, 1.0]"""
    source_step: str = ""
    """Which plan step this action came from."""


@dataclass(frozen=True)
class ActionOutcome:
    """The result of executing a single action.

    Immutable — captures what happened, not what should happen.
    """
    action_id: str = ""
    """Which action produced this outcome."""
    success: bool = False
    """Whether the action completed successfully."""
    result: Any = None
    """The raw result from the capability."""
    error: str = ""
    """Error message if the action failed."""
    latency_ms: float = 0.0
    """How long the action took."""
    side_effects: tuple[str, ...] = ()
    """What changed in the world as a result."""
    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional outcome metadata."""


@dataclass(frozen=True)
class ExecutionResult:
    """Aggregated result of executing all actions in a plan."""
    actions: tuple[ActionOutcome, ...] = ()
    """Outcomes for each action executed."""
    success_count: int = 0
    """Number of successful actions."""
    failure_count: int = 0
    """Number of failed actions."""
    total_latency_ms: float = 0.0
    """Total execution time."""
    goal_achieved: bool = False
    """Whether the overall goal was achieved."""

    @property
    def is_success(self) -> bool:
        return self.failure_count == 0 and self.goal_achieved

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / max(total, 1)


class ExecutionEngine(Protocol):
    """Protocol for executing actions through capabilities.

    The runtime depends only on this interface.
    Implementations discover and invoke capabilities via the CapabilityBus.
    """

    async def execute(
        self,
        actions: tuple[Action, ...],
        context: Any = None,
    ) -> ExecutionResult:
        """Execute a sequence of actions.

        Args:
            actions: The actions to execute (from a validated plan)
            context: Optional runtime context

        Returns:
            ExecutionResult with outcomes for each action
        """
        ...
