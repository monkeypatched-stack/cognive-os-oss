"""CognitiveOS — standalone cognitive runtime for autonomous actors.

Zero required dependencies. Optional pipeline via dependency injection.

Usage:
    from cognitiveos import Actor, CognitiveOS

    actor = Actor(entity_id="alice", actor_type_id="human")
    os = CognitiveOS()
    os.set_actor(actor)
    result = await os.run("Book me a flight to Berlin")
"""
from .version import __version__
from .actor import Actor, Identity, GoalState, BeliefState as ActorBelief, CapabilityState, ResourceState
from .os import CognitiveOS, GoalEvaluation, CapabilityMatch, ResourceCheck, DecisionSynthesis, ParsedIntent, RunResult, StepResult
from .interfaces import ICognitiveEngine, ITransitionModel, IMessageBus, IWorldProvider, ITrustProvider
from .exceptions import (
    CognitiveOSError, ActorNotBoundError, EngineNotInjectedError,
    TrustViolationError, InvalidActorError, DuplicateActorError,
)
from .protocol import ActorProtocol
from .agents import Agent, AgentResult, Provider, AgentRegistry
from .affiliations import AffiliationManager, TrustEngine, Affiliation
from .capability_bus import CapabilityBus
from .agent_bus import AgentBus

__all__ = [
    "__version__",
    "Actor", "Identity", "GoalState", "ActorBelief", "CapabilityState", "ResourceState",
    "CognitiveOS", "GoalEvaluation", "CapabilityMatch", "ResourceCheck", "DecisionSynthesis",
    "ParsedIntent", "RunResult", "StepResult",
    "ICognitiveEngine", "ITransitionModel", "IMessageBus", "IWorldProvider", "ITrustProvider",
    "CognitiveOSError", "ActorNotBoundError", "EngineNotInjectedError",
    "TrustViolationError", "InvalidActorError", "DuplicateActorError",
    "ActorProtocol",
    "Agent", "AgentResult", "Provider", "AgentRegistry",
    "AffiliationManager", "TrustEngine", "Affiliation",
    "CapabilityBus", "AgentBus",
]
