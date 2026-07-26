"""CognitiveOS — standalone cognitive runtime for autonomous actors.

Zero required dependencies. Optional pipeline via dependency injection.

Usage:
    from cognitiveos import Actor, CognitiveOS

    actor = Actor(entity_id="alice", actor_type_id="human")
    os = CognitiveOS()
    os.set_actor(actor)
    result = await os.run("Book me a flight to Berlin")
"""
from .actor import Actor, CapabilityState, GoalState, Identity, ResourceState
from .actor import BeliefState as ActorBelief
from .affiliations import Affiliation, AffiliationManager, TrustEngine
from .agent_bus import AgentBus
from .agents import Agent, AgentRegistry, AgentResult, Provider
from .capability_bus import CapabilityBus
from .exceptions import (
    ActorNotBoundError,
    CognitiveOSError,
    DuplicateActorError,
    EngineNotInjectedError,
    InvalidActorError,
    TrustViolationError,
)
from .interfaces import ICognitiveEngine, IMessageBus, ITransitionModel, ITrustProvider, IWorldProvider
from .os import (
    CapabilityMatch,
    CognitiveOS,
    DecisionSynthesis,
    GoalEvaluation,
    ParsedIntent,
    ResourceCheck,
    RunResult,
    StepResult,
)
from .protocol import ActorProtocol
from .version import __version__

__all__ = [
    "Actor",
    "ActorBelief",
    "ActorNotBoundError",
    "ActorProtocol",
    "Affiliation",
    "AffiliationManager",
    "Agent",
    "AgentBus",
    "AgentRegistry",
    "AgentResult",
    "CapabilityBus",
    "CapabilityMatch",
    "CapabilityState",
    "CognitiveOS",
    "CognitiveOSError",
    "DecisionSynthesis",
    "DuplicateActorError",
    "EngineNotInjectedError",
    "GoalEvaluation",
    "GoalState",
    "ICognitiveEngine",
    "IMessageBus",
    "ITransitionModel",
    "ITrustProvider",
    "IWorldProvider",
    "Identity",
    "InvalidActorError",
    "ParsedIntent",
    "Provider",
    "ResourceCheck",
    "ResourceState",
    "RunResult",
    "StepResult",
    "TrustEngine",
    "TrustViolationError",
    "__version__",
]
