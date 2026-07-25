"""Agent system — cognitive workers that execute tasks through providers.

Architecture:
    Provider (OpenClaw, n8n, NANDA) → hosts Agents
    Agent → executes tasks, uses provider infrastructure
    CognitiveOS → resolves agents, routes tasks

Agents are NOT stubs. They resolve to real providers or run locally.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("agentos.agents")


@dataclass
class AgentResult:
    """Result from an agent execution."""
    agent_id: str = ""
    provider: str = ""
    success: bool = True
    action: str = ""
    output: dict = field(default_factory=dict)
    error: str = ""
    latency_ms: float = 0.0


class Agent:
    """A cognitive worker that executes tasks.

    Agents resolve to a provider (OpenClaw, n8n, etc.) or run locally.
    Each agent handles specific intents and delegates to a backend.
    """

    def __init__(self, agent_id: str, capabilities: list[str] = None,
                 provider: str = "local"):
        self.agent_id = agent_id
        self.capabilities = capabilities or []
        self.provider = provider
        self._backend: Any = None

    def can_handle(self, action: str, intent: Any = None) -> bool:
        """Check if this agent can handle the given action."""
        return action in self.capabilities

    def set_backend(self, backend: Any) -> None:
        """Set the execution backend (provider connection)."""
        self._backend = backend

    def execute(self, action: str, intent: Any, actor: Any = None,
                world: Any = None) -> AgentResult:
        """Execute a task. Routes to backend if available."""
        if self._backend is not None:
            return self._backend.execute(action, intent, actor, world)

        return AgentResult(
            agent_id=self.agent_id,
            provider=self.provider,
            success=False,
            action=action,
            error=f"No backend configured for agent {self.agent_id}",
        )


class Provider:
    """External service platform that hosts agents.

    Examples: OpenClaw, n8n, NANDA
    """

    def __init__(self, provider_id: str, base_url: str = ""):
        self.provider_id = provider_id
        self.base_url = base_url
        self._agents: dict[str, Agent] = {}

    def register_agent(self, agent: Agent) -> None:
        agent.provider = self.provider_id
        self._agents[agent.agent_id] = agent

    def get_agent(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def execute(self, action: str, intent: Any, actor: Any = None,
                world: Any = None) -> AgentResult:
        """Execute through this provider's best matching agent."""
        for agent in self._agents.values():
            if agent.can_handle(action, intent):
                return agent.execute(action, intent, actor, world)
        return AgentResult(
            provider=self.provider_id, success=False,
            action=action, error=f"No agent for action: {action}",
        )


class AgentRegistry:
    """Registry of all agents and providers."""

    def __init__(self):
        self._agents: dict[str, Agent] = {}
        self._providers: dict[str, Provider] = {}

    def register_agent(self, agent: Agent) -> None:
        self._agents[agent.agent_id] = agent

    def register_provider(self, provider: Provider) -> None:
        self._providers[provider.provider_id] = provider

    def resolve(self, action: str, intent: Any = None) -> Agent | None:
        """Find the best agent for an action."""
        for agent in self._agents.values():
            if agent.can_handle(action, intent):
                return agent
        for provider in self._providers.values():
            for agent in provider._agents.values():
                if agent.can_handle(action, intent):
                    return agent
        return None

    def execute(self, action: str, intent: Any, actor: Any = None,
                world: Any = None) -> AgentResult:
        """Resolve and execute through the best agent."""
        agent = self.resolve(action, intent)
        if agent is None:
            return AgentResult(
                success=False, action=action,
                error=f"No agent found for action: {action}",
            )
        return agent.execute(action, intent, actor, world)

    def list_agents(self) -> list[str]:
        return list(self._agents.keys())

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())
