"""Tests for cognitiveos.engine.action_executor.ActionExecutor."""
import asyncio

from cognitiveos.engine.action_executor import ActionExecutor
from cognitiveos.engine.execution import Action


class FakeCapabilityResult:
    def __init__(self, success, produced):
        self.success = success
        self.produced = produced


class FakeCapabilityBus:
    def __init__(self, response=None, raise_exc=None):
        self._response = response
        self._raise_exc = raise_exc
        self.calls = []

    async def execute(self, capability, *, context=None, **kwargs):
        self.calls.append((capability, context, kwargs))
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._response


class TestActionExecutorNoCapabilityBus:
    def test_empty_actions_short_circuits(self):
        executor = ActionExecutor()
        result = asyncio.run(executor.execute(()))
        assert result.goal_achieved is True
        assert result.actions == ()

    def test_no_capability_bus_simulates_success(self):
        executor = ActionExecutor()
        action = Action(action_id="a1", capability="find_item")
        result = asyncio.run(executor.execute((action,)))
        assert result.success_count == 1
        assert result.failure_count == 0
        assert result.goal_achieved is True
        assert result.actions[0].result == {"simulated": True, "capability": "find_item"}


class TestActionExecutorWithCapabilityBus:
    def test_successful_capability_call(self):
        bus = FakeCapabilityBus(response=FakeCapabilityResult(True, {"found": True}))
        executor = ActionExecutor(capability_bus=bus)
        action = Action(action_id="a1", capability="find_item", parameters={"q": "milk"})

        result = asyncio.run(executor.execute((action,), context="ctx"))

        assert result.success_count == 1
        assert result.actions[0].result == {"found": True}
        assert bus.calls == [("find_item", "ctx", {"q": "milk"})]

    def test_failed_capability_call_reports_error_from_produced(self):
        bus = FakeCapabilityBus(response=FakeCapabilityResult(False, {"error": "not found"}))
        executor = ActionExecutor(capability_bus=bus)
        action = Action(action_id="a1", capability="find_item")

        result = asyncio.run(executor.execute((action,)))

        assert result.failure_count == 1
        assert result.goal_achieved is False
        assert result.actions[0].error == "not found"

    def test_capability_bus_exception_is_caught(self):
        bus = FakeCapabilityBus(raise_exc=RuntimeError("boom"))
        executor = ActionExecutor(capability_bus=bus)
        action = Action(action_id="a1", capability="find_item")

        result = asyncio.run(executor.execute((action,)))

        assert result.failure_count == 1
        assert "boom" in result.actions[0].error

    def test_multiple_actions_aggregate_counts(self):
        bus = FakeCapabilityBus(response=FakeCapabilityResult(True, {}))
        executor = ActionExecutor(capability_bus=bus)
        actions = (
            Action(action_id="a1", capability="find_item"),
            Action(action_id="a2", capability="add_to_cart"),
        )
        result = asyncio.run(executor.execute(actions))
        assert result.success_count == 2
        assert len(result.actions) == 2


class TestStochasticFailure:
    def test_failure_rate_one_always_fails(self):
        executor = ActionExecutor(failure_rate=1.0)
        action = Action(action_id="a1", capability="find_item")
        result = asyncio.run(executor.execute((action,)))
        assert result.failure_count == 1
        assert result.actions[0].result["stochastic_failure"] is True
        assert result.actions[0].error != ""

    def test_failure_rate_zero_never_triggers_stochastic_path(self):
        executor = ActionExecutor(failure_rate=0.0)
        action = Action(action_id="a1", capability="find_item")
        result = asyncio.run(executor.execute((action,)))
        assert result.success_count == 1
