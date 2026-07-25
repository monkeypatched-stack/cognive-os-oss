"""Actors Layer — embodies ontology concepts and makes decisions.

The Actor is the center of its own world. It owns:
    Identity    — who am I (ActorType, name, description)
    Goals       — what do I want (GoalType hierarchy)
    Beliefs     — what do I know (BeliefType, confidence, evidence)
    Capabilities — what can I do (CapabilityType)
    Affiliations — who do I know and trust (AffiliationType)
    Resources   — what do I have (ResourceType)

The Actor delegates ALL infrastructure to CognitiveOS (self.os).
The Actor NEVER instantiates runtime components directly.

Decision flow:
    Observe  → World → Beliefs (BeliefType + ConfidenceModel)
    Evaluate → Goals (GoalType + priority + constraints)
    Plan     → Capabilities (CapabilityType + prerequisites)
    Execute  → World mutation
    Learn    → Update beliefs (BeliefType confidence evolution)
    Trust    → Update affiliations (AffiliationType trust model)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("agentos.actor")


@dataclass(frozen=True)
class Identity:
    """Who the actor IS — references ActorType ontology."""
    actor_type_id: str  # e.g., "human", "ai_agent", "enterprise"
    name: str
    description: str = ""


@dataclass(frozen=True)
class GoalState:
    """A goal the actor is pursuing — references GoalType ontology."""
    goal_type_id: str    # e.g., "wealth", "safety", "mastery"
    priority: int = 50
    progress: float = 0.0  # 0.0 to 1.0
    active: bool = True
    label: str = ""       # the specific request, e.g. "buy milk" — goal_type_id
                           # is a small, coarse ontology bucket (~24 entries); two
                           # unrelated requests routinely collapse into the same
                           # one ("buy milk" and "charge laptop" both -> "accomplishment"),
                           # so label is what actually distinguishes them as goals


@dataclass(frozen=True)
class BeliefState:
    """What the actor knows — references BeliefType ontology."""
    belief_type_id: str  # e.g., "observation", "trust_belief"
    subject: str         # what the belief is about, e.g. "ball"
    attribute: str = ""  # which aspect of the subject, e.g. "color"
    value: Any = None    # the believed value, e.g. "red"
    confidence: float = 0.5
    evidence: tuple[str, ...] = ()
    age_days: int = 0


@dataclass(frozen=True)
class CapabilityState:
    """What the actor can do — references CapabilityType ontology."""
    capability_type_id: str  # e.g., "coding", "diagnosis"
    proficiency: float = 0.5  # 0.0 to 1.0
    available: bool = True


@dataclass(frozen=True)
class ResourceState:
    """What the actor has — references ResourceType ontology."""
    resource_type_id: str  # e.g., "money", "data", "time"
    quantity: float = 0.0
    unit: str = ""


class Actor:
    """The center of its own world. Embodies ontology concepts and makes decisions.

    Three explicit responsibilities:

    Identity & Domain
        identity     — who am I (ActorType reference)
        goals        — what do I want (GoalType references)
        capabilities — what can I do (CapabilityType references)
        resources    — what do I have (ResourceType references)
        affiliations — who do I know (AffiliationManager)

    Cognition
        beliefs      — what do I know (BeliefType + confidence)
        observe()    — observe the world
        evaluate()   — evaluate goals against beliefs
        plan()       — plan actions using capabilities
        execute()    — execute plan against world
        learn()      — update beliefs from outcomes

    Decision Flow
        observe → evaluate → plan → execute → learn → trust

    The actor delegates ALL infrastructure to CognitiveOS (self.os):
        self.os.world()           → read-only world access
        self.os.send_message()    → inter-agent messaging
        self.os.broadcast()       → broadcast to peers
        self.os.transition()      → learned transition model
        self.os.tick()            → run cognitive cycle

    ARCHITECTURAL INVARIANT:
        Actor depends ONLY on CognitiveOS API.
        Actor NEVER knows about SocietyRuntime or PlanetaryRuntime.
    """

    def __init__(self, entity_id: str, actor_type_id: str = "human",
                 name: str = "", goals: list[str] | None = None,
                 objective: str = ""):
        self._entity_id = entity_id
        self._os: Any = None  # set by CognitiveOS.set_actor()

        # ── Identity ────────────────────────────────────────
        self._identity = Identity(actor_type_id=actor_type_id, name=name or entity_id)

        # ── Goals ───────────────────────────────────────────
        self._goal_states: list[GoalState] = [
            GoalState(goal_type_id=g) for g in (goals or [])
        ]
        self._current_goal: str | None = goals[0] if goals else None
        self._objective: str = objective
        self._goals: list[str] = goals or []

        # ── Beliefs ─────────────────────────────────────────
        self._beliefs: list[BeliefState] = []

        # ── Capabilities ────────────────────────────────────
        self._capabilities: list[CapabilityState] = []

        # ── Resources ───────────────────────────────────────
        self._resources: list[ResourceState] = []

        # ── Affiliations (owned by actor) ───────────────────
        from cognitiveos.affiliations.manager import AffiliationManager
        self._affiliations = AffiliationManager()

    # ── Identity & Domain ───────────────────────────────────

    @property
    def entity_id(self) -> str:
        return self._entity_id

    @property
    def identity(self) -> Identity:
        return self._identity

    @property
    def actor_type_id(self) -> str:
        return self._identity.actor_type_id

    @property
    def os(self) -> Any:
        return self._os

    @os.setter
    def os(self, value: Any) -> None:
        self._os = value

    @property
    def affiliations(self):
        return self._affiliations

    # ── Goals ───────────────────────────────────────────────

    @property
    def goal_states(self) -> list[GoalState]:
        return list(self._goal_states)

    def add_goal(self, goal_type_id: str, priority: int = 50, label: str = "") -> GoalState:
        goal = GoalState(goal_type_id=goal_type_id, priority=priority, label=label)
        self._goal_states.append(goal)
        self._goals.append(goal_type_id)
        if self._current_goal is None:
            self._current_goal = goal_type_id
        return goal

    def remove_goal(self, goal_type_id: str) -> bool:
        before = len(self._goal_states)
        self._goal_states = [g for g in self._goal_states if g.goal_type_id != goal_type_id]
        self._goals = [g for g in self._goals if g != goal_type_id]
        if self._current_goal == goal_type_id:
            self._current_goal = self._goals[0] if self._goals else None
        return len(self._goal_states) < before

    def active_goals(self) -> list[GoalState]:
        return [g for g in self._goal_states if g.active]

    def top_goal(self) -> GoalState | None:
        active = self.active_goals()
        return min(active, key=lambda g: g.priority) if active else None

    def update_goal_progress(self, goal_type_id: str, progress: float) -> None:
        for g in self._goal_states:
            if g.goal_type_id == goal_type_id:
                new_progress = max(0.0, min(1.0, progress))
                self._goal_states = [
                    GoalState(
                        goal_type_id=g.goal_type_id, priority=g.priority,
                        progress=new_progress, active=g.active, label=g.label,
                    )
                    if g.goal_type_id == goal_type_id else g
                    for g in self._goal_states
                ]
                break

    # ── Beliefs ─────────────────────────────────────────────

    @property
    def beliefs(self) -> list[BeliefState]:
        return list(self._beliefs)

    def add_belief(self, belief_type_id: str, subject: str,
                   attribute: str = "", value: Any = None,
                   confidence: float = 0.5, evidence: tuple[str, ...] = ()) -> BeliefState:
        if attribute:
            # An attribute belief is a property with one current value
            # ("door.state") — a new observation revises it rather than
            # sitting alongside a now-contradicted old one. Beliefs with
            # no attribute (the original belief_type_id+subject shape)
            # stay append-only — there's no single "current value" to
            # revise for those.
            self._beliefs = [
                b for b in self._beliefs
                if not (b.subject == subject and b.attribute == attribute)
            ]
        belief = BeliefState(
            belief_type_id=belief_type_id, subject=subject,
            attribute=attribute, value=value,
            confidence=max(0.0, min(1.0, confidence)), evidence=evidence,
        )
        self._beliefs.append(belief)
        return belief

    def beliefs_about(self, subject: str) -> list[BeliefState]:
        return [b for b in self._beliefs if b.subject == subject]

    def beliefs_by_type(self, belief_type_id: str) -> list[BeliefState]:
        return [b for b in self._beliefs if b.belief_type_id == belief_type_id]

    def highest_confidence(self, subject: str) -> BeliefState | None:
        matches = self.beliefs_about(subject)
        return max(matches, key=lambda b: b.confidence) if matches else None

    def decay_beliefs(self, decay_rate: float = 0.05) -> int:
        """Decay confidence of all beliefs. Returns count of beliefs removed."""
        original = len(self._beliefs)
        self._beliefs = [
            BeliefState(
                belief_type_id=b.belief_type_id, subject=b.subject,
                attribute=b.attribute, value=b.value,
                confidence=max(0.0, b.confidence - decay_rate),
                evidence=b.evidence, age_days=b.age_days + 1,
            )
            for b in self._beliefs
            if b.confidence - decay_rate > 0.01
        ]
        return original - len(self._beliefs)

    # ── Capabilities ────────────────────────────────────────

    @property
    def capabilities(self) -> list[CapabilityState]:
        return list(self._capabilities)

    def add_capability(self, capability_type_id: str, proficiency: float = 0.5) -> CapabilityState:
        cap = CapabilityState(capability_type_id=capability_type_id,
                             proficiency=max(0.0, min(1.0, proficiency)))
        self._capabilities.append(cap)
        return cap

    def has_capability(self, capability_type_id: str) -> bool:
        return any(c.capability_type_id == capability_type_id and c.available
                   for c in self._capabilities)

    def best_capability(self, capability_type_id: str) -> CapabilityState | None:
        matches = [c for c in self._capabilities
                   if c.capability_type_id == capability_type_id and c.available]
        return max(matches, key=lambda c: c.proficiency) if matches else None

    # ── Resources ───────────────────────────────────────────

    @property
    def resources(self) -> list[ResourceState]:
        return list(self._resources)

    def add_resource(self, resource_type_id: str, quantity: float, unit: str = "") -> ResourceState:
        res = ResourceState(resource_type_id=resource_type_id, quantity=quantity, unit=unit)
        self._resources.append(res)
        return res

    def has_resource(self, resource_type_id: str, min_quantity: float = 1.0) -> bool:
        return any(r.resource_type_id == resource_type_id and r.quantity >= min_quantity
                   for r in self._resources)

    def resource_quantity(self, resource_type_id: str) -> float:
        return sum(r.quantity for r in self._resources
                   if r.resource_type_id == resource_type_id)

    # ── Cognition (delegated to self.os) ────────────────────

    async def tick(self) -> dict:
        """Run one cognitive cycle. Delegates to CognitiveOS."""
        if self._os is None:
            return {"error": "No CognitiveOS bound to this actor"}
        return await self._os.tick()

    def observe(self) -> Any:
        """Observe the world through the OS."""
        if self._os is None:
            return None
        return self._os.world()

    def send_message(self, to: str, msg_type: str, payload: dict = None) -> bool:
        """Send a message to another actor. Trust-enforced by OS."""
        if self._os is None:
            return False
        return self._os.send_message(to, msg_type, payload)

    def broadcast(self, msg_type: str, payload: dict = None) -> int:
        """Broadcast to all peers. Trust-enforced by OS."""
        if self._os is None:
            return 0
        return self._os.broadcast(msg_type, payload)

    def set_world(self, world: Any) -> None:
        """Inject world reference (called by CognitiveOS)."""
        if self._os is not None:
            self._os._world = world

    def set_goal(self, goal: str | None) -> None:
        self._current_goal = goal

    def __hash__(self) -> int:
        return hash(self._entity_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Actor):
            return NotImplemented
        return self._entity_id == other._entity_id
