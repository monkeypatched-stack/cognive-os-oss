"""CognitiveOS exceptions."""


class CognitiveOSError(Exception):
    """Base exception for CognitiveOS."""


class ActorNotBoundError(CognitiveOSError):
    """Raised when no actor is bound to the CognitiveOS."""


class EngineNotInjectedError(CognitiveOSError):
    """Raised when tick() is called without an injected engine."""


class TrustViolationError(CognitiveOSError):
    """Raised when a trust-enforced operation is blocked."""


class InvalidActorError(CognitiveOSError):
    """Raised when an invalid actor is provided."""


class DuplicateActorError(CognitiveOSError):
    """Raised when trying to bind a second actor to the same OS."""
