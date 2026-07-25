"""Core Ontologies — the foundational semantic concepts.

Architecture:
    Ontology defines what exists (semantic concepts).
    Actors embody those concepts and make decisions.
    CognitiveOS performs reasoning for each actor.
    Society provides shared infrastructure and governance.
    Trust Network governs interactions between autonomous actors.

Core (~133 concepts): Stable, versioned, backward compatible.
Domain Extensions: Healthcare, manufacturing, finance, etc. (extend core).
"""
from .base import OntologyType
from .core import (
    ALL_CORE,
    ALL_WORLD, ALL_ACTOR, ALL_GOALS, ALL_BELIEFS,
    ALL_AFFILIATIONS, ALL_CAPABILITIES,
    WorldConcept, ActorConcept, GoalConcept, BeliefConcept,
    AffiliationConcept, CapabilityConcept,
)
from . import extensions

__all__ = [
    "OntologyType",
    "ALL_CORE",
    "ALL_WORLD", "ALL_ACTOR", "ALL_GOALS", "ALL_BELIEFS",
    "ALL_AFFILIATIONS", "ALL_CAPABILITIES",
    "WorldConcept", "ActorConcept", "GoalConcept", "BeliefConcept",
    "AffiliationConcept", "CapabilityConcept",
    "extensions",
]
