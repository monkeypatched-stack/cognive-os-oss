"""LightweightCognitiveEngine — the real default ICognitiveEngine.

Not ported from anywhere — this is the bridge between cognitiveos.Actor
(cognitiveos/actor.py) and the ported planning stack (belief_state.py,
planning_engine.py). It implements the ICognitiveEngine protocol
(cognitiveos/interfaces.py: `async def tick(self, actor) -> Any`) so it can
be passed to `CognitiveOS.set_engine()`, and CognitiveOS.run() also falls
back to it automatically when no engine has been injected.

Scope: Observe -> Believe -> Plan only. Execution stays CognitiveOS's job
(CapabilityBus/AgentBus, or engine/action_executor.py's ActionExecutor) —
matching CognitiveOS.run()'s existing design: "The engine decides what steps
to take. The middleware handles execution."
"""
from __future__ import annotations

from typing import Any

from cognitiveos.engine.belief_state import BeliefState
from cognitiveos.engine.pipeline_actor import PipelineActor
from cognitiveos.engine.planning_engine import DeterministicPlanner


class LightweightCognitiveEngine:
    """Real forward-chaining planning engine — no ML, no infra, no LLM.

    Builds a BeliefState from the actor's ontology-backed capabilities,
    resources, beliefs, and the currently parsed intent (if any), then runs
    the ported DeterministicPlanner over it. Tracks reasoning cycles per
    actor via PipelineActor, mirroring the real kernel's actor bookkeeping.
    """

    def __init__(self) -> None:
        self._planner = DeterministicPlanner()
        self._pipeline_actors: dict[str, PipelineActor] = {}

    async def tick(self, actor: Any) -> dict:
        actor_id = getattr(actor, "entity_id", "") or ""
        pipeline_actor = self._pipeline_actors.setdefault(
            actor_id, PipelineActor(actor_id=actor_id),
        )
        pipeline_actor.start_reasoning()

        belief = self._build_belief(actor)
        plan = self._planner.plan(belief, belief.goal)

        pipeline_actor.finish_reasoning()

        return {
            "success": True,
            "goal_achieved": False,
            "plan": {
                "steps": [
                    {"name": step.action, "type": "capability", "description": step.description}
                    for step in plan.steps
                ],
            },
            "plan_confidence": plan.confidence,
            "plan_risk": plan.risk,
            "cycle_count": pipeline_actor.cycle_count,
        }

    def _build_belief(self, actor: Any) -> BeliefState:
        """Observe stage: turn actor state + current intent into Facts."""
        belief = BeliefState(actor_id=getattr(actor, "entity_id", "") or "")

        goal_id = getattr(actor, "_current_goal", None) or ""
        intent = getattr(actor, "_current_intent", None)
        description_parts = [
            str(p) for p in (
                getattr(intent, "action", None) if intent else None,
                getattr(intent, "subject", None) if intent else None,
                getattr(intent, "target", None) if intent else None,
            ) if p
        ]
        belief.update_goal(
            name=goal_id,
            description=" ".join(description_parts) if description_parts else goal_id,
            # actor.py stores the constructor's objective= as _objective (no
            # public accessor) — without threading it through here,
            # Actor(objective="cost") never reaches DeterministicPlanner's
            # objective-weighted scoring at all, silently planning as if no
            # objective had been set.
            optimization_objective=getattr(actor, "_objective", "") or "",
        )

        for cap in getattr(actor, "capabilities", []):
            belief.add_fact(
                entity=cap.capability_type_id, attribute="proficiency",
                value=cap.proficiency,
                confidence=1.0 if cap.available else 0.3,
                source="actor_capability",
            )

        for res in getattr(actor, "resources", []):
            belief.add_fact(
                entity=res.resource_type_id, attribute="quantity",
                value=res.quantity, confidence=1.0, source="actor_resource",
            )

        for bel in getattr(actor, "beliefs", []):
            # A belief with a real attribute ("store_a".price = 5, see
            # actor.py's revision semantics) carries actual domain data the
            # planner can reason over — e.g. DeterministicPlanner's cost
            # objective looks for a fact whose attribute contains "price".
            # Surfacing it as attribute=belief_type_id/value=confidence
            # (the old behavior, still correct for legacy subject-only
            # beliefs with no attribute) would discard that data and make
            # it structurally unreachable from the public Actor API.
            if bel.attribute:
                belief.add_fact(
                    entity=bel.subject, attribute=bel.attribute,
                    value=bel.value, confidence=bel.confidence,
                    source="actor_belief",
                )
            else:
                belief.add_fact(
                    entity=bel.subject, attribute=bel.belief_type_id,
                    value=bel.confidence, confidence=bel.confidence,
                    source="actor_belief",
                )

        if intent is not None:
            action = getattr(intent, "action", "") or ""
            subject = getattr(intent, "subject", "") or ""
            target = getattr(intent, "target", "") or ""
            confidence = getattr(intent, "confidence", 1.0) or 1.0
            # The action verb itself is a fact too, not just what it acts on —
            # otherwise a command like "Translate text" never produces a
            # "translate" entity at all (only "text", via subject), so a
            # registered "translate" capability could never be found by name
            # even though it's exactly what the command asked for.
            if action:
                belief.add_fact(
                    entity=action, attribute="requested_action", value=True,
                    confidence=confidence, source="intent",
                )
            if subject:
                belief.add_fact(
                    entity=subject, attribute="requested", value=True,
                    confidence=confidence, source="intent",
                )
            if target:
                belief.add_fact(
                    entity=target, attribute="destination", value=True,
                    confidence=confidence, source="intent",
                )

        return belief
