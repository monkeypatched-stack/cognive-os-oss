"""PipelineActor — identity-only entity for the cognitive engine.

Ported from monkeypatched's kernel/pipeline/actor.py. Renamed Actor ->
PipelineActor (module and class) to avoid colliding with cognitiveos.Actor,
which is a different, richer object (owns goals/beliefs/capabilities). This
one is intentionally minimal — the engine's own bookkeeping of reasoning
cycles per cognitiveos actor, not a replacement for it.

An Actor encapsulates identity and lifecycle. It does NOT own BeliefState,
policy, or memory — those belong to the engine/runtime.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineActor:
    """Identity-only entity. Does NOT own cognition.

    Owns:
    - identity (actor_id, tenant_id)
    - lifecycle state
    - trust score
    - metadata

    Does NOT own:
    - BeliefState (that's the engine's per-tick construction)
    - Policy / learning
    - Memory
    """

    actor_id: str = ""
    tenant_id: str = "default"
    trust_score: float = 0.5
    status: str = "idle"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_reasoned_at: float = 0.0
    cycle_count: int = 0

    def start_reasoning(self) -> None:
        self.status = "reasoning"

    def finish_reasoning(self) -> None:
        self.status = "idle"
        self.last_reasoned_at = time.time()
        self.cycle_count += 1

    def block(self, reason: str = "") -> None:
        self.status = f"blocked:{reason}"

    def terminate(self) -> None:
        self.status = "terminated"

    def is_active(self) -> bool:
        return self.status == "idle"

    def snapshot(self) -> PipelineActorSnapshot:
        return PipelineActorSnapshot(
            actor_id=self.actor_id,
            tenant_id=self.tenant_id,
            trust_score=self.trust_score,
            status=self.status,
            cycle_count=self.cycle_count,
        )

    def summary(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "tenant_id": self.tenant_id,
            "status": self.status,
            "trust_score": round(self.trust_score, 3),
            "cycle_count": self.cycle_count,
        }


@dataclass(frozen=True)
class PipelineActorSnapshot:
    """Immutable snapshot of a pipeline actor's identity at a point in time."""
    actor_id: str = ""
    tenant_id: str = ""
    trust_score: float = 0.0
    status: str = ""
    cycle_count: int = 0
