"""Tests for AgentBus — routing, result normalisation, and error handling."""
import asyncio

from cognitiveos.agent_bus import AgentBus, AgentResult, get_agent_bus


class WorkingAgent:
    agent_type = "governance"

    async def handle(self, kwargs):
        return {"success": True, "answer": kwargs.get("question", "")}

    def feedback(self):
        return 0.9


class NoFeedbackAgent:
    agent_type = "planner"

    async def handle(self, kwargs):
        return {"ok": True}


class RaisingAgent:
    agent_type = "flaky"

    async def handle(self, kwargs):
        raise RuntimeError("backend unavailable")


class PayloadWrappingAgent:
    """Mimics BaseETASSAgent._result() returning a dict with a nested payload."""
    agent_type = "wrapper"

    async def handle(self, kwargs):
        return {"payload": {"answer": 42}, "reward": 0.75}


class TypedResultAgent:
    """Mimics a real AgentResult-like object (has .payload / .reward, not a dict)."""
    agent_type = "typed"

    class _Result:
        payload = {"value": "typed-answer"}
        reward = 0.8

    async def handle(self, kwargs):
        return self._Result()


class NonDictAgent:
    agent_type = "raw"

    async def handle(self, kwargs):
        return 12345


class NoneReturningAgent:
    agent_type = "silent"

    async def handle(self, kwargs):
        return None


class TestAgentBusRegistrationAndExecution:
    def test_register_and_execute_success(self):
        bus = AgentBus()
        bus.register(WorkingAgent())
        result = asyncio.run(bus.execute("governance", question="what?"))
        assert isinstance(result, AgentResult)
        assert result.success is True
        assert result.produced["answer"] == "what?"
        assert result.feedback == 0.9

    def test_execute_unregistered_agent_returns_not_found(self):
        bus = AgentBus()
        result = asyncio.run(bus.execute("nonexistent"))
        assert result.success is False
        assert result.produced["error"] == "agent_not_found"
        assert result.produced["agent_name"] == "nonexistent"

    def test_execute_never_raises_on_agent_exception(self):
        bus = AgentBus()
        bus.register(RaisingAgent())
        result = asyncio.run(bus.execute("flaky"))
        assert result.success is False
        assert "backend unavailable" in result.produced["error"]

    def test_default_feedback_when_agent_has_no_feedback_method(self):
        bus = AgentBus()
        bus.register(NoFeedbackAgent())
        result = asyncio.run(bus.execute("planner"))
        assert result.feedback == 0.5

    def test_summary_lists_local_agents(self):
        bus = AgentBus()
        bus.register(WorkingAgent())
        bus.register(NoFeedbackAgent())
        summary = bus.summary()
        assert summary["local_agent_count"] == 2
        assert set(summary["local_agents"]) == {"governance", "planner"}

    def test_get_agent_bus_factory_returns_fresh_instance(self):
        b1 = get_agent_bus()
        b2 = get_agent_bus()
        assert isinstance(b1, AgentBus)
        assert b1 is not b2


class TestNormaliseProduced:
    def test_none_becomes_empty_dict(self):
        bus = AgentBus()
        bus.register(NoneReturningAgent())
        result = asyncio.run(bus.execute("silent"))
        assert result.produced == {}
        assert result.success is True  # non-dict/None -> success defaults True

    def test_plain_dict_used_as_is(self):
        bus = AgentBus()
        bus.register(NoFeedbackAgent())
        result = asyncio.run(bus.execute("planner"))
        assert result.produced == {"ok": True}

    def test_nested_payload_dict_is_unwrapped_and_reward_becomes_feedback(self):
        bus = AgentBus()
        bus.register(PayloadWrappingAgent())
        result = asyncio.run(bus.execute("wrapper"))
        assert result.produced == {"answer": 42, "feedback": 0.75}

    def test_typed_result_with_dict_payload_attribute(self):
        bus = AgentBus()
        bus.register(TypedResultAgent())
        result = asyncio.run(bus.execute("typed"))
        assert result.produced["value"] == "typed-answer"
        assert result.produced["feedback"] == 0.8

    def test_non_dict_non_typed_result_wrapped_as_value(self):
        bus = AgentBus()
        bus.register(NonDictAgent())
        result = asyncio.run(bus.execute("raw"))
        assert result.produced == {"value": "12345"}
