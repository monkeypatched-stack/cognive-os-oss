"""Tests for cognitiveos.agents — Agent, Provider, AgentRegistry."""
from cognitiveos.agents import Agent, AgentRegistry, AgentResult, Provider


class FakeBackend:
    def __init__(self, output=None):
        self.output = output or {}
        self.calls = []

    def execute(self, action, intent, actor=None, world=None):
        self.calls.append((action, intent, actor, world))
        return AgentResult(success=True, action=action, output=self.output)


class TestAgent:
    def test_can_handle_known_action(self):
        agent = Agent(agent_id="a1", capabilities=["book_flight"])
        assert agent.can_handle("book_flight") is True
        assert agent.can_handle("cook_dinner") is False

    def test_execute_without_backend_returns_failure(self):
        agent = Agent(agent_id="a1", capabilities=["book_flight"])
        result = agent.execute("book_flight", intent=None)
        assert result.success is False
        assert result.agent_id == "a1"
        assert "No backend configured" in result.error

    def test_execute_with_backend_delegates(self):
        agent = Agent(agent_id="a1", capabilities=["book_flight"])
        backend = FakeBackend(output={"confirmation": "XYZ"})
        agent.set_backend(backend)

        result = agent.execute("book_flight", intent="intent-obj", actor="actor-obj", world="world-obj")

        assert result.success is True
        assert result.output == {"confirmation": "XYZ"}
        assert backend.calls == [("book_flight", "intent-obj", "actor-obj", "world-obj")]

    def test_default_capabilities_is_empty_list_not_shared(self):
        a1 = Agent(agent_id="a1")
        a2 = Agent(agent_id="a2")
        a1.capabilities.append("x")
        assert a2.capabilities == []


class TestProvider:
    def test_register_agent_sets_provider_id(self):
        provider = Provider(provider_id="openclaw")
        agent = Agent(agent_id="a1", capabilities=["book_flight"], provider="local")
        provider.register_agent(agent)
        assert agent.provider == "openclaw"
        assert provider.get_agent("a1") is agent

    def test_get_agent_missing_returns_none(self):
        provider = Provider(provider_id="openclaw")
        assert provider.get_agent("ghost") is None

    def test_execute_dispatches_to_matching_agent(self):
        provider = Provider(provider_id="openclaw")
        backend = FakeBackend(output={"ok": True})
        agent = Agent(agent_id="a1", capabilities=["book_flight"])
        agent.set_backend(backend)
        provider.register_agent(agent)

        result = provider.execute("book_flight", intent=None)
        assert result.success is True
        assert result.output == {"ok": True}

    def test_execute_no_matching_agent_returns_error(self):
        provider = Provider(provider_id="openclaw")
        result = provider.execute("unknown_action", intent=None)
        assert result.success is False
        assert result.provider == "openclaw"
        assert "No agent for action" in result.error


class TestAgentRegistry:
    def test_resolve_finds_directly_registered_agent(self):
        registry = AgentRegistry()
        agent = Agent(agent_id="a1", capabilities=["book_flight"])
        registry.register_agent(agent)
        assert registry.resolve("book_flight") is agent

    def test_resolve_falls_back_to_provider_agents(self):
        registry = AgentRegistry()
        provider = Provider(provider_id="openclaw")
        agent = Agent(agent_id="a1", capabilities=["book_flight"])
        provider.register_agent(agent)
        registry.register_provider(provider)

        assert registry.resolve("book_flight") is agent

    def test_resolve_returns_none_when_nothing_matches(self):
        registry = AgentRegistry()
        assert registry.resolve("anything") is None

    def test_execute_no_agent_found_returns_error_result(self):
        registry = AgentRegistry()
        result = registry.execute("unknown_action", intent=None)
        assert result.success is False
        assert "No agent found for action" in result.error

    def test_execute_delegates_to_resolved_agent(self):
        registry = AgentRegistry()
        backend = FakeBackend(output={"done": True})
        agent = Agent(agent_id="a1", capabilities=["book_flight"])
        agent.set_backend(backend)
        registry.register_agent(agent)

        result = registry.execute("book_flight", intent=None)
        assert result.success is True
        assert result.output == {"done": True}

    def test_list_agents_and_providers(self):
        registry = AgentRegistry()
        registry.register_agent(Agent(agent_id="a1"))
        registry.register_agent(Agent(agent_id="a2"))
        registry.register_provider(Provider(provider_id="p1"))

        assert set(registry.list_agents()) == {"a1", "a2"}
        assert registry.list_providers() == ["p1"]

    def test_directly_registered_agent_takes_priority_over_provider(self):
        registry = AgentRegistry()

        direct_backend = FakeBackend(output={"source": "direct"})
        direct_agent = Agent(agent_id="dup", capabilities=["act"])
        direct_agent.set_backend(direct_backend)
        registry.register_agent(direct_agent)

        provider_backend = FakeBackend(output={"source": "provider"})
        provider_agent = Agent(agent_id="dup2", capabilities=["act"])
        provider_agent.set_backend(provider_backend)
        provider = Provider(provider_id="p1")
        provider.register_agent(provider_agent)
        registry.register_provider(provider)

        result = registry.execute("act", intent=None)
        assert result.output == {"source": "direct"}
