"""AgentBus — routes workload steps to Broca agents.

Execution flow:
    AgentBus.execute(agent_name, **context)
      → BrocaAgentRegistry.discover(agent_name)   # local registry, then NANDA fallback
      → agent.handle(context)                      # Broca agent does the work
      → Cerebellum capabilities (inside the agent)
      → AgentResult

AgentResult mirrors CapabilityResult so callers can swap buses without changing their
result-handling code: both expose .success, .produced, .events_emitted, .latency_ms.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("agentos.agent_bus")


@dataclass
class AgentResult:
    """Standardised result envelope from agent execution.

    Field names mirror CapabilityResult for uniform handling.
    """

    agent_name: str
    success: bool
    produced: dict[str, Any] = field(default_factory=dict)
    events_emitted: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    feedback: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentBus:
    """Routes workload steps to registered Broca agents.

    Usage:
        bus = AgentBus()
        result = await bus.execute("governance", question="...", mongo_client=...)
        if result.success and result.produced:
            accumulated.update(result.produced)

    Registration priority:
        1. Manually registered agents (via bus.register())
        2. BrocaAgentRegistry (auto-registered subclasses + NANDA fallback)
    """

    def __init__(self) -> None:
        self._agents: dict[str, Any] = {}

    def register(self, agent: Any) -> None:
        """Manually register a Broca agent instance."""
        agent_type = getattr(agent, "agent_type", None) or str(agent)
        self._agents[agent_type] = agent
        logger.info("[agent_bus] registered agent: %s", agent_type)

    async def execute(self, agent_name: str, **kwargs: Any) -> AgentResult:
        """Execute the named agent with the given context kwargs.

        Returns AgentResult. Never raises — errors surface as success=False.
        """
        t0 = time.monotonic()
        agent = self._resolve(agent_name)

        if agent is None:
            logger.warning("[agent_bus] no agent found for %r", agent_name)
            return AgentResult(
                agent_name=agent_name,
                success=False,
                produced={"error": "agent_not_found", "agent_name": agent_name},
                latency_ms=0.0,
            )

        try:
            raw = await agent.handle(kwargs)
            elapsed = (time.monotonic() - t0) * 1000
            feedback = agent.feedback() if callable(getattr(agent, "feedback", None)) else 0.5
            produced = self._normalise_produced(raw)
            return AgentResult(
                agent_name=agent_name,
                success=produced.get("success", True) if isinstance(produced, dict) else True,
                produced=produced,
                latency_ms=elapsed,
                feedback=feedback,
            )
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            logger.error("[agent_bus] agent %r raised: %s", agent_name, exc)
            return AgentResult(
                agent_name=agent_name,
                success=False,
                produced={"error": str(exc), "agent_name": agent_name},
                latency_ms=elapsed,
            )

    def _resolve(self, agent_name: str) -> Any | None:
        """Local registry → BrocaAgentRegistry (includes NANDA fallback)."""
        agent = self._agents.get(agent_name)
        if agent is not None:
            return agent
        try:
            from broca.registry import get_registry
            return get_registry().discover(agent_name)
        except Exception as exc:
            logger.debug("[agent_bus] BrocaAgentRegistry lookup failed for %r: %s", agent_name, exc)
            return None

    @staticmethod
    def _normalise_produced(raw: Any) -> dict[str, Any]:
        """Coerce agent.handle() output to a plain dict for .produced.

        BrocaAgent.handle() may return:
          - AgentResult (execution_outcome)  → use .payload
          - plain dict                        → use as-is
          - anything else                     → wrap in {"value": raw}
        """
        if raw is None:
            return {}
        if isinstance(raw, dict):
            # BaseETASSAgent._result() returns a plain dict when AgentResult unavailable;
            # if it contains a nested "payload" key, unwrap it.
            if "payload" in raw and isinstance(raw["payload"], dict):
                merged = {**raw["payload"]}
                if "reward" in raw:
                    merged.setdefault("feedback", raw["reward"])
                return merged
            return raw
        # Typed AgentResult from execution_outcome
        payload = getattr(raw, "payload", None)
        if isinstance(payload, dict):
            result: dict[str, Any] = dict(payload)
            result.setdefault("feedback", getattr(raw, "reward", 0.5))
            return result
        return {"value": str(raw)}

    def summary(self) -> dict[str, Any]:
        return {
            "local_agents": list(self._agents.keys()),
            "local_agent_count": len(self._agents),
        }


def get_agent_bus() -> AgentBus:
    return AgentBus()


__all__ = ["AgentBus", "AgentResult", "get_agent_bus"]
