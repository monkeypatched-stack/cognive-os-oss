"""BeliefState — the canonical cognitive data model.

Ported from monkeypatched's kernel/pipeline/belief_state.py (MonkeyBrain's
"light tier" — pure stdlib, no kernel/infra coupling). Unmodified except for
this header.

The BeliefState is the central data structure shared by every stage of the
cognitive lifecycle. It replaces loosely typed dictionaries with a well-defined
semantic model.

Stages communicate through BeliefState:
    Observe  → writes facts and observations from world
    Believe  → updates confidence, detects conflicts
    Plan     → reads facts + intent + goal, writes plan
    Execute  → reads plan, writes actions and observations
    Learn    → updates hypotheses, confidence, learned_updates
    Predict  → reads hypotheses + confidence, writes predictions
    Commit   → finalizes the cognitive state
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

# ════════════════════════════════════════════════════════════════════════════
# Supporting Types — frozen value objects (defined before BeliefState)
# ════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Intent:
    """Classified intent from the compiler."""
    type: str = ""
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Goal:
    """Resolved goal from the compiler."""
    name: str = ""
    description: str = ""
    success_criteria: tuple[str, ...] = ()
    optimization_objective: str = ""
    """'cost', 'speed', 'reliability', or '' for default balanced scoring."""


@dataclass(frozen=True)
class Observation:
    """A raw observation from the world."""
    entity: str = ""
    description: str = ""
    source: str = "world"
    confidence: float = 1.0
    observed_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class Fact:
    """A grounded fact about the world."""
    entity: str = ""
    attribute: str = ""
    value: Any = None
    confidence: float = 1.0
    source: str = "observation"
    observed_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class Hypothesis:
    """An inferred belief that may or may not be true."""
    claim: str = ""
    confidence: float = 0.5
    evidence: tuple[str, ...] = ()
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class Assumption:
    """Something taken for granted unless challenged."""
    statement: str = ""
    confidence: float = 0.8
    source: str = "default"
    created_at: float = field(default_factory=time.time)


@dataclass
class Uncertainty:
    """Quantified uncertainty about the belief state."""
    confidence: float = 0.5
    confidence_by_source: dict[str, float] = field(default_factory=dict)
    entropy: float = 0.0


@dataclass
class WorkingMemoryEntry:
    """A temporary entry in working memory."""
    key: str = ""
    value: Any = None
    expires_at: float = 0.0


@dataclass(frozen=True)
class LongTermMemoryEntry:
    """A retained entry across reasoning cycles."""
    key: str = ""
    value: Any = None
    confidence: float = 1.0
    stored_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class Plan:
    """A structured plan produced by the planning engine.

    Plans are semantic objects — they describe WHAT to do,
    not HOW to execute. Execution is a separate concern.
    """
    goal: str = ""
    """What the plan aims to achieve."""
    preconditions: tuple[str, ...] = ()
    """What must be true before execution."""
    steps: tuple[PlanStep, ...] = ()
    """Ordered plan steps."""
    expected_outcomes: tuple[str, ...] = ()
    """What we expect to happen after execution."""
    cost: float = 0.0
    """Estimated resource cost. [0.0, 1.0]"""
    confidence: float = 0.0
    """Plan confidence. [0.0, 1.0]"""
    risk: float = 0.0
    """Risk level. [0.0, 1.0]"""
    start_state: str = ""
    """Starting state."""
    goal_state: str = ""
    """Goal state."""
    planner: str = "default"
    """Which planning engine produced this plan."""
    metadata: dict[str, Any] = field(default_factory=dict)
    """Plan-specific metadata."""


@dataclass(frozen=True)
class PlanStep:
    """A single step in a plan."""
    action: str = ""
    """What to do (e.g. 'find_milk', 'add_to_cart')."""
    description: str = ""
    """Human-readable description."""
    preconditions: tuple[str, ...] = ()
    """What must be true before this step."""
    expected_outcome: str = ""
    """What this step is expected to achieve."""
    cost: float = 0.0
    """Estimated cost of this step. [0.0, 1.0]"""
    confidence: float = 0.0
    """Confidence in this step. [0.0, 1.0]"""


@dataclass(frozen=True)
class PlanEvaluation:
    """Result of evaluating a plan."""
    plan: Plan
    """The evaluated plan."""
    feasible: bool = True
    """Whether the plan can be executed."""
    goal_satisfied: bool = False
    """Whether the plan satisfies the goal."""
    violations: tuple[str, ...] = ()
    """Constraint violations found."""
    score: float = 0.0
    """Evaluation score. [0.0, 1.0]"""


@dataclass(frozen=True)
class Prediction:
    """A predicted future state."""
    description: str = ""
    confidence: float = 0.5
    based_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class LearnedUpdate:
    """Knowledge acquired during a reasoning cycle."""
    what: str = ""
    evidence: tuple[str, ...] = ()
    confidence: float = 0.5
    learned_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class BeliefSnapshot:
    """Immutable snapshot of a belief state at a point in time."""
    version: int = 0
    actor_id: str = ""
    tenant_id: str = ""
    intent_type: str = ""
    goal_name: str = ""
    facts_count: int = 0
    hypotheses_count: int = 0
    observations_count: int = 0
    confidence: float = 0.0
    plan_steps: int = 0
    predictions_count: int = 0
    learned_count: int = 0
    timestamp: float = field(default_factory=time.time)


# ════════════════════════════════════════════════════════════════════════════
# BeliefState — the canonical cognitive model
# ════════════════════════════════════════════════════════════════════════════


@dataclass
class BeliefState:
    """The actor's internal cognitive model.

    Represents what the actor currently believes about:
    - itself (identity)
    - the world (observations, facts)
    - its goals and intentions
    - uncertainty
    - learned knowledge
    - predictions
    - working memory

    Mutable within a single execution cycle.
    """

    # ── Identity ──────────────────────────────────────────────────────────

    actor_id: str = ""
    tenant_id: str = "default"

    # ── Intent & Goal ─────────────────────────────────────────────────────

    intent: Intent = field(default_factory=Intent)
    goal: Goal = field(default_factory=Goal)

    # ── World View (read-only reference) ──────────────────────────────────

    world_view: Any = None

    # ── Observations ──────────────────────────────────────────────────────

    observations: list[Observation] = field(default_factory=list)

    # ── Facts ─────────────────────────────────────────────────────────────

    facts: list[Fact] = field(default_factory=list)

    # ── Hypotheses ────────────────────────────────────────────────────────

    hypotheses: list[Hypothesis] = field(default_factory=list)

    # ── Assumptions ───────────────────────────────────────────────────────

    assumptions: list[Assumption] = field(default_factory=list)

    # ── Uncertainty ───────────────────────────────────────────────────────

    uncertainty: Uncertainty = field(default_factory=Uncertainty)

    # ── Memory ────────────────────────────────────────────────────────────

    working_memory: list[WorkingMemoryEntry] = field(default_factory=list)
    long_term_memory: list[LongTermMemoryEntry] = field(default_factory=list)

    # ── Plan ──────────────────────────────────────────────────────────────

    plan: Plan = field(default_factory=Plan)

    # ── Predictions ───────────────────────────────────────────────────────

    predictions: list[Prediction] = field(default_factory=list)

    # ── Learned Updates ───────────────────────────────────────────────────

    learned_updates: list[LearnedUpdate] = field(default_factory=list)

    # ── Metadata ──────────────────────────────────────────────────────────

    metadata: dict[str, Any] = field(default_factory=dict)

    # ── Versioning ────────────────────────────────────────────────────────

    version: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # ══════════════════════════════════════════════════════════════════════
    # Semantic API
    # ══════════════════════════════════════════════════════════════════════

    def add_observation(self, entity: str, description: str,
                        source: str = "world", confidence: float = 1.0) -> None:
        self.observations.append(Observation(
            entity=entity, description=description,
            source=source, confidence=confidence,
        ))
        self._touch()

    def add_fact(self, entity: str, attribute: str, value: Any,
                 confidence: float = 1.0, source: str = "observation") -> None:
        self.facts.append(Fact(
            entity=entity, attribute=attribute, value=value,
            confidence=confidence, source=source,
        ))
        self._touch()

    def add_hypothesis(self, claim: str, confidence: float = 0.5,
                       evidence: list[str] | None = None) -> None:
        self.hypotheses.append(Hypothesis(
            claim=claim, confidence=confidence, evidence=evidence or [],
        ))
        self._touch()

    def add_assumption(self, statement: str, confidence: float = 0.8,
                       source: str = "default") -> None:
        self.assumptions.append(Assumption(
            statement=statement, confidence=confidence, source=source,
        ))
        self._touch()

    def update_intent(self, intent_type: str, confidence: float = 1.0,
                      metadata: dict[str, Any] | None = None) -> None:
        self.intent = Intent(type=intent_type, confidence=confidence, metadata=metadata or {})
        self._touch()

    def update_goal(self, name: str, description: str = "",
                    success_criteria: list[str] | None = None,
                    optimization_objective: str = "") -> None:
        self.goal = Goal(name=name, description=description,
                         success_criteria=success_criteria or (),
                         optimization_objective=optimization_objective)
        self._touch()

    def update_plan(self, steps: list[str], start_state: str = "",
                    goal_state: str = "") -> None:
        self.plan = Plan(steps=tuple(steps), start_state=start_state, goal_state=goal_state)
        self._touch()

    def record_prediction(self, description: str, confidence: float = 0.5,
                          based_on: list[str] | None = None) -> None:
        self.predictions.append(Prediction(
            description=description, confidence=confidence, based_on=based_on or [],
        ))
        self._touch()

    def record_learning(self, what: str, evidence: list[str] | None = None,
                        confidence: float = 0.5) -> None:
        self.learned_updates.append(LearnedUpdate(
            what=what, evidence=evidence or [], confidence=confidence,
        ))
        self._touch()

    def add_to_working_memory(self, key: str, value: Any,
                               ttl_seconds: float = 300.0) -> None:
        self.working_memory.append(WorkingMemoryEntry(
            key=key, value=value, expires_at=time.time() + ttl_seconds,
        ))
        self._touch()

    # ══════════════════════════════════════════════════════════════════════
    # Maintenance
    # ══════════════════════════════════════════════════════════════════════

    def decay_and_prune(
        self,
        decay_rate: float = 0.05,
        hypothesis_prune_threshold: float = 0.2,
        fact_prune_threshold: float = 0.1,
        max_hypotheses: int = 50,
        fact_confidence_floor: float = 0.7,
    ) -> dict[str, int]:
        """Decay confidence on facts and prune stale hypotheses/facts.

        Called each tick to prevent unbounded accumulation and simulate
        real-world belief degradation (world changes → old beliefs fade).
        """
        now = time.time()
        pruned_hypotheses = 0
        pruned_facts = 0

        new_facts = []
        for fact in self.facts:
            age_ticks = max(1, (now - fact.observed_at) / 10.0)
            decayed = fact.confidence * ((1.0 - decay_rate) ** age_ticks)
            # fact_confidence_floor is a decay *floor* — it must never raise a
            # fact's confidence above what it started with. Clamping against
            # fact_confidence_floor directly (old behavior) inflated any fact
            # that decayed below the floor up to it, so e.g. a fact observed
            # at confidence 0.2 came out of a single decay_and_prune() call at
            # 0.7 — higher than it was before "decaying".
            clamped = max(decayed, min(fact_confidence_floor, fact.confidence))
            if decayed >= fact_prune_threshold:
                new_facts.append(Fact(
                    entity=fact.entity, attribute=fact.attribute,
                    value=fact.value, confidence=round(clamped, 4),
                    source=fact.source, observed_at=fact.observed_at,
                ))
            else:
                pruned_facts += 1
        self.facts = new_facts

        new_hypotheses = []
        for hyp in self.hypotheses:
            age_ticks = max(1, (now - hyp.created_at) / 10.0)
            decayed = hyp.confidence * ((1.0 - decay_rate) ** age_ticks)
            if decayed >= hypothesis_prune_threshold:
                new_hypotheses.append(Hypothesis(
                    claim=hyp.claim, confidence=round(decayed, 4),
                    evidence=hyp.evidence, created_at=hyp.created_at,
                ))
            else:
                pruned_hypotheses += 1
        self.hypotheses = new_hypotheses

        if len(self.hypotheses) > max_hypotheses:
            self.hypotheses.sort(key=lambda h: h.confidence, reverse=True)
            pruned_hypotheses += len(self.hypotheses) - max_hypotheses
            self.hypotheses = self.hypotheses[:max_hypotheses]

        self._touch()
        return {"pruned_facts": pruned_facts, "pruned_hypotheses": pruned_hypotheses}

    # ══════════════════════════════════════════════════════════════════════
    # Query API
    # ══════════════════════════════════════════════════════════════════════

    def recall(self, query: str) -> list[Fact]:
        q = query.lower()
        return [f for f in self.facts if q in str(f.value).lower() or q in f.entity.lower()]

    def confidence(self) -> float:
        return self.uncertainty.confidence

    def confidence_for(self, source: str) -> float:
        return self.uncertainty.confidence_by_source.get(source, self.uncertainty.confidence)

    # ══════════════════════════════════════════════════════════════════════
    # Snapshot & Serialization
    # ══════════════════════════════════════════════════════════════════════

    def snapshot(self) -> BeliefSnapshot:
        return BeliefSnapshot(
            version=self.version, actor_id=self.actor_id, tenant_id=self.tenant_id,
            intent_type=self.intent.type, goal_name=self.goal.name,
            facts_count=len(self.facts), hypotheses_count=len(self.hypotheses),
            observations_count=len(self.observations),
            confidence=self.uncertainty.confidence,
            plan_steps=len(self.plan.steps),
            predictions_count=len(self.predictions),
            learned_count=len(self.learned_updates),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version, "actor_id": self.actor_id, "tenant_id": self.tenant_id,
            "intent": asdict(self.intent), "goal": asdict(self.goal),
            "observations": [asdict(o) for o in self.observations],
            "facts": [asdict(f) for f in self.facts],
            "hypotheses": [asdict(h) for h in self.hypotheses],
            "assumptions": [asdict(a) for a in self.assumptions],
            "uncertainty": asdict(self.uncertainty),
            "plan": asdict(self.plan),
            "predictions": [asdict(p) for p in self.predictions],
            "learned_updates": [asdict(lu) for lu in self.learned_updates],
            "working_memory_count": len(self.working_memory),
            "long_term_memory_count": len(self.long_term_memory),
            "metadata": self.metadata,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }

    def summary(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id, "tenant_id": self.tenant_id,
            "intent": self.intent.type, "goal": self.goal.name,
            "observations": len(self.observations), "facts": len(self.facts),
            "hypotheses": len(self.hypotheses), "assumptions": len(self.assumptions),
            "confidence": round(self.uncertainty.confidence, 3),
            "plan_steps": len(self.plan.steps), "predictions": len(self.predictions),
            "learned": len(self.learned_updates),
            "working_memory": len(self.working_memory), "version": self.version,
        }

    def _touch(self) -> None:
        self.updated_at = time.time()
        self.version += 1
