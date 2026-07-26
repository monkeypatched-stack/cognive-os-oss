"""Core Ontology — the stable, versioned foundation.

~160 concepts organized into categories:
    World    — what exists (16 types)
    Actor    — what actors are (17 types)
    Cognition — goals (24 types) + beliefs (14 types)
    Social   — affiliations/relationships (21 types)
    Capability — what actors can do (21 types)

Domain extensions (healthcare, manufacturing, etc.) extend this
core without modifying it.
"""
from typing import Any

from .actor import ALL_ACTOR, ActorConcept, ActorLifecycle, ActorTrustModel
from .capability import ALL_CAPABILITIES, CapabilityConcept, PrerequisiteModel
from .cognition import (
    ALL_BELIEFS,
    ALL_GOALS,
    BeliefConcept,
    ConfidenceModel,
    GoalConcept,
    GoalConstraints,
)
from .social import ALL_AFFILIATIONS, AffiliationConcept, SocialLifecycle, SocialTrustModel
from .world import ALL_WORLD, WorldConcept

ALL_CORE: dict[str, Any] = {}
ALL_CORE.update(ALL_WORLD)
ALL_CORE.update(ALL_ACTOR)
ALL_CORE.update(ALL_GOALS)
ALL_CORE.update(ALL_BELIEFS)
ALL_CORE.update(ALL_AFFILIATIONS)
ALL_CORE.update(ALL_CAPABILITIES)

__all__ = [
    "ALL_ACTOR",
    "ALL_AFFILIATIONS",
    "ALL_BELIEFS",
    "ALL_CAPABILITIES",
    "ALL_CORE",
    "ALL_GOALS",
    "ALL_WORLD",
    "ActorConcept",
    "ActorLifecycle",
    "ActorTrustModel",
    "AffiliationConcept",
    "BeliefConcept",
    "CapabilityConcept",
    "ConfidenceModel",
    "GoalConcept",
    "GoalConstraints",
    "PrerequisiteModel",
    "SocialLifecycle",
    "SocialTrustModel",
    "WorldConcept",
]
