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
from . import extensions
from .base import OntologyType
from .core import (
    ALL_ACTOR,
    ALL_AFFILIATIONS,
    ALL_BELIEFS,
    ALL_CAPABILITIES,
    ALL_CORE,
    ALL_GOALS,
    ALL_WORLD,
    ActorConcept,
    AffiliationConcept,
    BeliefConcept,
    CapabilityConcept,
    GoalConcept,
    WorldConcept,
)

__all__ = [
    "ALL_ACTOR",
    "ALL_AFFILIATIONS",
    "ALL_BELIEFS",
    "ALL_CAPABILITIES",
    "ALL_CORE",
    "ALL_GOALS",
    "ALL_WORLD",
    "ActorConcept",
    "AffiliationConcept",
    "BeliefConcept",
    "CapabilityConcept",
    "GoalConcept",
    "OntologyType",
    "WorldConcept",
    "extensions",
]
