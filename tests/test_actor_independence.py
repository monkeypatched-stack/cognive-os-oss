"""Multi-actor independence — the local-runtime invariant.

Every CognitiveOS instance owns its own beliefs, goals, planner,
capabilities, and execution engine. Nothing is shared, no synchronization,
no distributed state, no world model, no continuous learning — unless a
caller explicitly injects a shared `world` or `society_runtime` (both
default to None/unset).
"""
import asyncio

from cognitiveos import Actor, CognitiveOS


class _Capability:
    def __init__(self, name):
        self.name = name

    def fn(self, kwargs):
        return {"by": self.name}


class TestActorIndependence:
    def _three_actors(self):
        alice = CognitiveOS()
        bob = CognitiveOS()
        warehouse = CognitiveOS()
        alice.set_actor(Actor(entity_id="alice", actor_type_id="human", goals=["wealth"]))
        bob.set_actor(Actor(entity_id="bob", actor_type_id="human", goals=["safety"]))
        warehouse.set_actor(Actor(entity_id="warehouse", actor_type_id="enterprise", goals=["accomplishment"]))
        return alice, bob, warehouse

    def test_each_actor_owns_its_own_bus_and_engine_instances(self):
        alice, bob, warehouse = self._three_actors()
        assert alice._capability_bus is not bob._capability_bus
        assert bob._capability_bus is not warehouse._capability_bus
        assert alice._agent_bus is not bob._agent_bus
        assert alice._lightweight_engine is not bob._lightweight_engine
        assert alice._action_executor is not bob._action_executor

    def test_capability_registration_does_not_leak_between_actors(self):
        alice, bob, warehouse = self._three_actors()
        alice.register_capability(_Capability("only_alice"))
        assert "only_alice" in alice._capability_bus._capabilities
        assert "only_alice" not in bob._capability_bus._capabilities
        assert "only_alice" not in warehouse._capability_bus._capabilities

    def test_no_shared_world_by_default(self):
        alice, bob, warehouse = self._three_actors()
        assert alice.world() is None
        assert bob.world() is None
        assert warehouse.world() is None

    def test_concurrent_runs_do_not_cross_contaminate_intent_or_goal(self):
        alice, bob, warehouse = self._three_actors()

        async def run_all():
            return await asyncio.gather(
                alice.run("Book me a flight to Berlin next Friday"),
                bob.run("Schedule a meeting with Bob tomorrow"),
            )

        r1, r2 = asyncio.run(run_all())

        assert alice.actor._current_goal == "travel"
        assert bob.actor._current_goal != "travel"
        assert alice.actor._current_intent.subject == "flight"
        assert bob.actor._current_intent.subject != "flight"
        assert getattr(warehouse.actor, "_current_intent", None) is None

        assert r1.intent.subject == "flight"
        assert r2.intent.subject == "meeting"
        assert r1.steps != r2.steps
