"""ActionExecutor — default execution through the CapabilityBus.

Ported from monkeypatched's kernel/pipeline/action_executor.py and adapted to
cognitiveos's actual CapabilityBus contract. The original called a fictional
`capability_bus.discover(name)` -> object exposing `.handle(dict)`, which
doesn't exist anywhere in cognitiveos — the real cognitiveos.CapabilityBus
(cognitiveos/capability_bus.py) is async and exposes
`execute(name, *, context=None, **kwargs) -> CapabilityResult`. This version
calls that instead, and `execute()`/`_execute_action()` are now async to
match it (the original was sync).

Plan steps → Actions → CapabilityBus → ActionOutcomes

The executor:
1. Converts plan steps to typed Actions
2. Invokes each capability through the CapabilityBus
3. Collects ActionOutcomes
4. Produces an ExecutionResult

If no CapabilityBus is available, actions are simulated (pass-through).
"""
from __future__ import annotations

import logging
import time
from typing import Any

from cognitiveos.engine.execution import (
    Action, ActionOutcome, ExecutionResult,
)

logger = logging.getLogger("agentos.pipeline.action_executor")


class ActionExecutor:
    """Default execution engine — invokes capabilities through the CapabilityBus.

    The engine depends only on the ExecutionEngine protocol.
    This is the default implementation that discovers and invokes capabilities.
    """

    def __init__(self, capability_bus: Any = None, failure_rate: float = 0.0) -> None:
        self._capability_bus = capability_bus
        self._failure_rate = failure_rate

    async def execute(
        self,
        actions: tuple[Action, ...],
        context: Any = None,
    ) -> ExecutionResult:
        """Execute a sequence of actions.

        Args:
            actions: The actions to execute
            context: Optional runtime context, forwarded to the CapabilityBus

        Returns:
            ExecutionResult with outcomes for each action
        """
        if not actions:
            return ExecutionResult(goal_achieved=True)

        outcomes = []
        start_time = time.time()

        for action in actions:
            outcome = await self._execute_action(action, context)
            outcomes.append(outcome)

        total_ms = (time.time() - start_time) * 1000
        success_count = sum(1 for o in outcomes if o.success)
        failure_count = sum(1 for o in outcomes if not o.success)

        # Goal is achieved if all actions succeeded
        goal_achieved = failure_count == 0

        return ExecutionResult(
            actions=tuple(outcomes),
            success_count=success_count,
            failure_count=failure_count,
            total_latency_ms=round(total_ms, 2),
            goal_achieved=goal_achieved,
        )

    async def _execute_action(self, action: Action, context: Any = None) -> ActionOutcome:
        """Execute a single action through the capability bus."""
        import random
        start_time = time.time()

        try:
            # Stochastic failure — simulates real-world unreliability. Off by
            # default (failure_rate=0.0); opt in for chaos testing.
            if self._failure_rate > 0 and random.random() < self._failure_rate:
                latency = (time.time() - start_time) * 1000
                error_msgs = [
                    f"Transient failure: {action.capability} — retry needed",
                    f"Resource contention: {action.capability} — capacity exceeded",
                    f"Timeout: {action.capability} — exceeded deadline",
                    f"Dependency unavailable: {action.capability} — upstream delayed",
                    f"State conflict: {action.capability} — concurrent modification",
                ]
                return ActionOutcome(
                    action_id=action.action_id,
                    success=False,
                    result={"simulated": True, "stochastic_failure": True, "capability": action.capability},
                    error=random.choice(error_msgs),
                    latency_ms=round(latency, 2),
                )

            if self._capability_bus is None:
                # No capability bus — simulate success
                logger.debug("[executor] No capability bus, simulating: %s", action.capability)
                return ActionOutcome(
                    action_id=action.action_id,
                    success=True,
                    result={"simulated": True, "capability": action.capability},
                    latency_ms=0.0,
                )

            # Invoke the capability through cognitiveos's real CapabilityBus
            cap_result = await self._capability_bus.execute(
                action.capability, context=context, **action.parameters,
            )

            latency = (time.time() - start_time) * 1000

            return ActionOutcome(
                action_id=action.action_id,
                success=cap_result.success,
                result=cap_result.produced,
                error=cap_result.produced.get("error", "") if not cap_result.success else "",
                latency_ms=round(latency, 2),
            )

        except Exception as e:
            latency = (time.time() - start_time) * 1000
            logger.error("[executor] Action %s failed: %s", action.action_id, e)
            return ActionOutcome(
                action_id=action.action_id,
                success=False,
                error=str(e),
                latency_ms=round(latency, 2),
            )
