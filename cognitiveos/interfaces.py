"""Public interfaces for CognitiveOS plugin architecture.

All external dependencies are injected through these interfaces.
The runtime depends only on interfaces, never on concrete implementations.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ICognitiveEngine(Protocol):
    """Interface for cognitive pipeline engines.

    Implement this to integrate BeliefFormation, CognitiveRuntime, etc.
    """
    async def tick(self, actor: Any) -> Any:
        """Run one cognitive cycle for the given actor."""
        ...


@runtime_checkable
class ITransitionModel(Protocol):
    """Interface for transition models.

    Implement this to provide world dynamics prediction.
    """
    def predict(self, state: Any, action: Any) -> Any:
        """Predict the next state given current state and action."""
        ...


@runtime_checkable
class IMessageBus(Protocol):
    """Interface for message buses.

    Implement this to provide inter-actor messaging.
    """
    def send(self, from_id: str, to_id: str, msg_type: str, payload: dict) -> bool:
        """Send a message. Returns True if sent."""
        ...

    def broadcast(self, from_id: str, msg_type: str, payload: dict) -> int:
        """Broadcast to all peers. Returns count sent."""
        ...

    def receive(self, actor_id: str) -> list[dict]:
        """Receive pending messages for an actor."""
        ...


@runtime_checkable
class IWorldProvider(Protocol):
    """Interface for world access.

    Implement this to provide shared world observation.
    """
    def observe(self) -> Any:
        """Return the current world state."""
        ...


@runtime_checkable
class ITrustProvider(Protocol):
    """Interface for trust management.

    Implement this to provide trust calculation.
    """
    def check_trust(self, source: str, target: str) -> float:
        """Get trust level from source to target."""
        ...

    def update_trust(self, source: str, target: str, outcome: bool) -> None:
        """Update trust based on an outcome."""
        ...
