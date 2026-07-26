"""Tests for CognitiveOS."""
import asyncio

import pytest

from cognitiveos import Actor, CognitiveOS


class TestOwnership:
    def test_one_to_one(self):
        os = CognitiveOS()
        a1 = Actor(entity_id="alice")
        os.set_actor(a1)
        assert os.actor is a1

    def test_reject_second(self):
        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice"))
        with pytest.raises(RuntimeError):
            os.set_actor(Actor(entity_id="bob"))


class TestTrustEnforcement:
    def test_send_message_blocked(self):
        os = CognitiveOS()
        a = Actor(entity_id="alice")
        os.set_actor(a)
        a.affiliations.add(type("Aff", (), {
            "affiliation_id": "f1", "affiliation_type": "family",
            "target_id": "enemy", "target_name": "Enemy",
            "trust_level": 0.1, "permissions": (), "policies": (),
            "priority": 0, "valid_from": "", "valid_until": "", "metadata": {},
        })())
        assert os.send_message("enemy", "test") is False

    def test_send_message_allowed(self):
        os = CognitiveOS()
        a = Actor(entity_id="alice")
        os.set_actor(a)
        a.affiliations.add(type("Aff", (), {
            "affiliation_id": "f1", "affiliation_type": "family",
            "target_id": "bob", "target_name": "Bob",
            "trust_level": 0.9, "permissions": (), "policies": (),
            "priority": 0, "valid_from": "", "valid_until": "", "metadata": {},
        })())
        assert os.send_message("bob", "test") is True


class TestReasoning:
    def test_evaluate_goals(self):
        os = CognitiveOS()
        a = Actor(entity_id="alice", actor_type_id="human",
                 goals=["wealth"], objective="cost")
        a.add_belief("observation", "market", confidence=0.7)
        a.add_capability("investment", proficiency=0.8)
        a.add_capability("accounting", proficiency=0.6)
        a.add_capability("analysis", proficiency=0.7)
        a.add_resource("money", quantity=5000)
        os.set_actor(a)
        evals = os.evaluate_goals()
        assert len(evals) >= 1
        assert evals[0].goal_type_id == "wealth"

    def test_synthesize(self):
        os = CognitiveOS()
        a = Actor(entity_id="alice", actor_type_id="human",
                 goals=["wealth"], objective="cost")
        a.add_belief("observation", "market", confidence=0.7)
        a.add_capability("investment", proficiency=0.8)
        a.add_capability("accounting", proficiency=0.6)
        a.add_capability("analysis", proficiency=0.7)
        a.add_resource("money", quantity=5000)
        os.set_actor(a)
        decision = os.synthesize()
        assert decision.selected_goal is not None
        assert decision.confidence > 0

    def test_tick_without_engine(self):
        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice"))
        import asyncio
        result = asyncio.run(os.tick())
        assert "error" in result
        assert "No engine" in result["error"]


class TestPluginArchitecture:
    def test_set_engine(self):
        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice"))
        assert os.has_engine() is False
        os.set_engine(object())
        assert os.has_engine() is True


class TestBeliefMaintenance:
    """Actor.decay_beliefs() previously had zero callers anywhere in the
    runtime — a long-running actor's subject-only beliefs (no attribute,
    see Actor.add_belief's revision semantics) would accumulate forever.
    run() and tick() now call it once per cognitive cycle.
    """

    def test_run_decays_actor_beliefs(self):
        os = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human")
        actor.add_belief("observation", "market", confidence=0.05)
        os.set_actor(actor)

        asyncio.run(os.run("Buy milk"))

        # confidence 0.05 - default decay_rate 0.05 <= 0.01 -> pruned
        assert actor.beliefs == []

    def test_tick_decays_actor_beliefs(self):
        class Engine:
            async def tick(self, actor):
                return {"plan": {"steps": []}}

        os = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human")
        actor.add_belief("observation", "market", confidence=0.05)
        os.set_actor(actor)
        os.set_engine(Engine())

        asyncio.run(os.tick())

        assert actor.beliefs == []

    def test_run_does_not_wipe_beliefs_used_within_the_same_cycle(self):
        """A single decay pass at default rate shouldn't destroy the
        reasonably-confident beliefs the same run() call needs to plan
        with — only near-zero-confidence beliefs are pruned."""
        os = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human", objective="cost")
        actor.add_belief("pricing", "store_a", attribute="price", value=5, confidence=0.9)
        os.set_actor(actor)

        result = asyncio.run(os.run("Buy milk"))

        assert any(s["name"] == "process_store_a" for s in result.steps)


class TestLocalMessageBusCap:
    """CognitiveOS._message_bus (used when no society_runtime is set) had
    no pruning mechanism at all — get_messages() only reads it, so it grew
    forever. Now capped at MAX_LOCAL_MESSAGE_BUS, oldest dropped first.
    """

    def test_message_bus_is_capped(self):
        from cognitiveos.os import MAX_LOCAL_MESSAGE_BUS

        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice"))
        for i in range(MAX_LOCAL_MESSAGE_BUS + 50):
            os.send_message("bob", "note", {"i": i})

        messages = os.get_messages()
        assert len(messages) == MAX_LOCAL_MESSAGE_BUS
        # oldest were dropped — the most recent messages survive
        assert messages[-1]["payload"]["i"] == MAX_LOCAL_MESSAGE_BUS + 49
        assert messages[0]["payload"]["i"] == 50


class TestTransition:
    """Regression: transition() used to call self._get_transition_model(),
    a method that was never defined anywhere in the class — every call
    raised AttributeError. Fixed to return the actual _transition_model
    attribute set in __init__.
    """

    def test_transition_returns_none_by_default(self):
        os = CognitiveOS()
        assert os.transition() is None

    def test_transition_does_not_raise(self):
        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice"))
        os.transition()  # would previously raise AttributeError


class TestTickWithRealEngine:
    def test_tick_returns_success_wrapper_around_engine_result(self):
        class Engine:
            async def tick(self, actor):
                return {"plan": {"steps": []}}

        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice"))
        os.set_engine(Engine())
        result = asyncio.run(os.tick())
        assert result["success"] is True
        assert result["result"] == {"plan": {"steps": []}}

    def test_tick_without_actor_returns_error(self):
        os = CognitiveOS()
        os.set_engine(object())
        result = asyncio.run(os.tick())
        assert result == {"error": "No actor bound to this CognitiveOS"}

    def test_tick_catches_engine_exception(self):
        class BrokenEngine:
            async def tick(self, actor):
                raise ValueError("planner exploded")

        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice"))
        os.set_engine(BrokenEngine())
        result = asyncio.run(os.tick())
        assert result["success"] is False
        assert "planner exploded" in result["error"]


class TestReasoningWithoutActor:
    def test_evaluate_goals_without_actor_returns_empty(self):
        os = CognitiveOS()
        assert os.evaluate_goals() == []

    def test_match_capabilities_without_actor_returns_empty(self):
        os = CognitiveOS()
        assert os.match_capabilities() == []

    def test_check_resources_without_actor_returns_empty(self):
        os = CognitiveOS()
        assert os.check_resources({"money": 10}) == []

    def test_synthesize_without_actor(self):
        os = CognitiveOS()
        decision = os.synthesize()
        assert decision.selected_goal is None
        assert decision.reasoning == "No actor bound"


class TestReasoningBranches:
    def test_no_beliefs_is_a_blocker(self):
        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human", goals=["wealth"]))
        evals = os.evaluate_goals()
        assert "no_beliefs" in evals[0].blockers
        assert evals[0].achievable is False

    def test_unavailable_capability_is_a_blocker(self):
        from cognitiveos.actor import CapabilityState

        os = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human", goals=["wealth"])
        actor.add_belief("observation", "market", confidence=0.7)
        actor._capabilities.append(
            CapabilityState(capability_type_id="investment", available=False)
        )
        os.set_actor(actor)
        evals = os.evaluate_goals()
        assert any(b.startswith("capability_unavailable:") for b in evals[0].blockers)
        assert evals[0].achievable is False

    def test_resource_with_positive_quantity_bumps_confidence(self):
        os = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human", goals=["wealth"])
        actor.add_belief("observation", "market", confidence=0.7)
        actor.add_resource("money", quantity=100)
        os.set_actor(actor)
        evals = os.evaluate_goals()
        assert evals[0].confidence >= 0.3

    def test_synthesize_no_achievable_goals(self):
        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human", goals=["wealth"]))
        decision = os.synthesize()
        assert decision.selected_goal is None
        assert decision.reasoning == "No achievable goals"
        assert decision.confidence == 0.0

    def test_synthesize_flags_low_trust_affiliations_for_trust_building(self):
        os = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human", goals=["wealth"])
        actor.add_belief("observation", "market", confidence=0.7)
        actor.add_capability("investment", proficiency=0.8)
        actor.add_capability("accounting", proficiency=0.6)
        actor.add_capability("analysis", proficiency=0.7)
        actor.add_resource("money", quantity=1000)
        actor.affiliations.add(type("Aff", (), {
            "affiliation_id": "f1", "affiliation_type": "community",
            "target_id": "stranger", "target_name": "Stranger",
            "trust_level": 0.2, "permissions": (), "policies": (),
            "priority": 0, "valid_from": "", "valid_until": "", "metadata": {},
        })())
        os.set_actor(actor)
        decision = os.synthesize()
        assert "build_trust:stranger" in decision.trust_actions


class TestRun:
    def test_parse_flight(self):
        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human"))
        result = asyncio.run(os.run("Book me a flight to Berlin next Friday"))
        assert result.intent.action == "book"
        assert result.intent.subject == "flight"
        assert result.intent.target == "berlin"
        assert "next" in result.intent.modifiers
        assert "friday" in result.intent.modifiers
        assert result.intent.goal_type_id == "travel"

    def test_parse_meeting(self):
        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human"))
        result = asyncio.run(os.run("Schedule a meeting with Bob tomorrow"))
        assert result.intent.action == "schedule"
        assert result.intent.subject == "meeting"
        assert "tomorrow" in result.intent.modifiers

    def test_parse_email(self):
        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human"))
        result = asyncio.run(os.run("Send an email to Carol about the project"))
        assert result.intent.action == "send"
        assert result.intent.subject == "email"

    def test_run_no_actor(self):
        os = CognitiveOS()
        result = asyncio.run(os.run("Book a flight"))
        assert result.reasoning == "No actor bound to this CognitiveOS"

    def test_run_no_engine(self):
        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice"))
        result = asyncio.run(os.run("Book a flight"))
        assert result.executed is True
        assert result.intent.action == "book"
        # Without a registered capability, the step fails for the expected
        # reason (dispatch found nothing) rather than crashing on a bad
        # CapabilityBus.execute() call signature.
        assert result.step_results[0].status == "failed"
        assert result.step_results[0].error == "capability_not_found"

    def test_run_with_engine(self):
        class MockEngine:
            async def tick(self, actor):
                return {"success": True, "plan": {"steps": [{"action": "book_flight"}]}, "goal_achieved": True}

        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human", goals=["travel"]))
        os.set_engine(MockEngine())
        result = asyncio.run(os.run("Book a flight to Berlin"))
        assert result.executed is True
        # Steps come from engine, but capabilities aren't registered so they fail
        assert len(result.step_results) > 0

    def test_run_uses_real_planner_by_default(self):
        """No engine injected: run() must fall back to the real
        DeterministicPlanner (cognitiveos.engine), not a hardcoded string —
        step names are planner-shaped ("process_<entity>", "achieve_goal"),
        grounded in the parsed intent's action/subject/target.
        """
        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human", goals=["travel"]))
        result = asyncio.run(os.run("Book me a flight to Berlin next Friday"))
        actions = {sr.action for sr in result.step_results}
        assert actions == {"process_book", "process_flight", "process_berlin", "achieve_goal"}

    def test_run_with_registered_capability_succeeds(self):
        class RealCapability:
            def __init__(self, name):
                self.name = name

            def fn(self, kwargs):
                return {"handled": self.name}

        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human", goals=["travel"]))
        # Register a handler for every step the real planner will produce for
        # this command (process_book, process_flight, process_berlin,
        # achieve_goal) so the whole run succeeds end to end — no mocked
        # pipeline, no stub steps.
        for name in ("process_book", "process_flight", "process_berlin", "achieve_goal"):
            os.register_capability(RealCapability(name))
        result = asyncio.run(os.run("Book me a flight to Berlin next Friday"))
        assert result.success is True
        assert all(sr.status == "success" for sr in result.step_results)
        assert {sr.output["handled"] for sr in result.step_results} == {
            "process_book", "process_flight", "process_berlin", "achieve_goal",
        }

    def test_run_sets_goal(self):
        class MockEngine:
            async def tick(self, actor):
                return {"success": True, "plan": {"steps": []}, "goal_achieved": False}

        os = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human")
        os.set_actor(actor)
        os.set_engine(MockEngine())
        asyncio.run(os.run("Book a flight to Berlin"))
        assert "travel" in actor._goals


class TestStepChaining:
    """plan['execution']: 'chain' (default) vs 'graph' (depends_on)."""

    def test_chain_step_reads_prior_step_output(self):
        class ProducerCapability:
            name = "produce"
            def fn(self, kwargs):
                return {"value": 42}

        class ConsumerCapability:
            name = "consume"
            def fn(self, kwargs):
                context = kwargs.get("context")
                return {"received": context.get_data("produce") if context else None}

        class TwoStepEngine:
            async def tick(self, actor):
                return {"plan": {"steps": [
                    {"name": "produce", "type": "capability"},
                    {"name": "consume", "type": "capability"},
                ]}}

        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human"))
        os.register_capability(ProducerCapability())
        os.register_capability(ConsumerCapability())
        os.set_engine(TwoStepEngine())

        result = asyncio.run(os.run("do the thing"))
        assert result.step_results[0].status == "success"
        assert result.step_results[1].status == "success"
        assert result.step_results[1].output["received"] == {"value": 42}

    def test_mixed_agent_and_capability_steps_execute_in_plan_order(self):
        order = []

        class OrderCapability:
            name = "cap_step"
            def fn(self, kwargs):
                order.append("cap_step")
                return {"ok": True}

        class OrderAgent:
            agent_type = "agent_step"
            async def handle(self, kwargs):
                order.append("agent_step")
                return {"ok": True}

        class MixedEngine:
            async def tick(self, actor):
                return {"plan": {"steps": [
                    {"name": "agent_step", "type": "agent"},
                    {"name": "cap_step", "type": "capability"},
                ]}}

        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human"))
        os.register_capability(OrderCapability())
        os.register_agent(OrderAgent())
        os.set_engine(MixedEngine())

        asyncio.run(os.run("do stuff"))
        assert order == ["agent_step", "cap_step"]

    def test_graph_step_waits_for_all_its_dependencies(self):
        class ProducerAgent:
            def __init__(self, agent_type, value):
                self.agent_type = agent_type
                self.value = value
            async def handle(self, kwargs):
                return {"value": self.value}

        class ConsumerAgent:
            agent_type = "consume"
            async def handle(self, kwargs):
                state = kwargs.get("state")
                return {"a": state.get_data("a"), "b": state.get_data("b")}

        class GraphEngine:
            async def tick(self, actor):
                return {"plan": {"execution": "graph", "steps": [
                    {"name": "a", "type": "agent"},
                    {"name": "b", "type": "agent"},
                    {"name": "consume", "type": "agent", "depends_on": ["a", "b"]},
                ]}}

        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human"))
        os.register_agent(ProducerAgent("a", 1))
        os.register_agent(ProducerAgent("b", 2))
        os.register_agent(ConsumerAgent())
        os.set_engine(GraphEngine())

        result = asyncio.run(os.run("do graph stuff"))
        by_name = {sr.action: sr for sr in result.step_results}
        assert by_name["a"].status == "success"
        assert by_name["b"].status == "success"
        assert by_name["consume"].output == {"a": {"value": 1}, "b": {"value": 2}}

    def test_graph_dependency_failure_blocks_dependent_without_running_it(self):
        ran = []

        class FailingAgent:
            agent_type = "will_fail"
            async def handle(self, kwargs):
                ran.append("will_fail")
                return {"success": False, "error": "boom"}

        class DependentAgent:
            agent_type = "dependent"
            async def handle(self, kwargs):
                ran.append("dependent")
                return {"success": True}

        class GraphEngine:
            async def tick(self, actor):
                return {"plan": {"execution": "graph", "steps": [
                    {"name": "will_fail", "type": "agent"},
                    {"name": "dependent", "type": "agent", "depends_on": ["will_fail"]},
                ]}}

        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human"))
        os.register_agent(FailingAgent())
        os.register_agent(DependentAgent())
        os.set_engine(GraphEngine())

        result = asyncio.run(os.run("do graph stuff"))
        by_name = {sr.action: sr for sr in result.step_results}
        assert by_name["will_fail"].status == "failed"
        assert by_name["dependent"].status == "failed"
        assert by_name["dependent"].error == "dependency_failed:will_fail"
        assert "dependent" not in ran

    def test_graph_cycle_fails_without_hanging(self):
        class NoopAgent:
            def __init__(self, agent_type):
                self.agent_type = agent_type
            async def handle(self, kwargs):
                return {"success": True}

        class CyclicEngine:
            async def tick(self, actor):
                return {"plan": {"execution": "graph", "steps": [
                    {"name": "a", "type": "agent", "depends_on": ["b"]},
                    {"name": "b", "type": "agent", "depends_on": ["a"]},
                ]}}

        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human"))
        os.register_agent(NoopAgent("a"))
        os.register_agent(NoopAgent("b"))
        os.set_engine(CyclicEngine())

        result = asyncio.run(os.run("do cyclic stuff"))
        assert all(sr.status == "failed" for sr in result.step_results)
        assert all(sr.error == "dependency_cycle" for sr in result.step_results)


class TestGoalIdentityAndPriority:
    """OSS-0202/OSS-0203: goal_type_id alone is a coarse ~24-entry ontology
    bucket that distinct requests can collapse into — label distinguishes
    them; priority is inferred from urgency language, not flat for everyone.
    """

    def test_distinct_requests_mapping_to_same_goal_type_both_tracked(self):
        os = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human")
        os.set_actor(actor)

        asyncio.run(os.run("Buy milk"))
        asyncio.run(os.run("Charge laptop"))  # same goal_type_id as "Buy milk"

        assert len(actor.goal_states) == 2
        labels = {g.label for g in actor.goal_states}
        assert labels == {"Buy milk", "Charge laptop"}

    def test_repeating_the_same_request_does_not_duplicate(self):
        os = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human")
        os.set_actor(actor)

        asyncio.run(os.run("Buy milk"))
        asyncio.run(os.run("Buy milk"))

        assert len(actor.goal_states) == 1

    def test_urgent_request_gets_higher_priority_and_wins_top_goal(self):
        os = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human")
        os.set_actor(actor)

        asyncio.run(os.run("Call ambulance"))
        asyncio.run(os.run("Buy groceries"))

        top = actor.top_goal()
        assert top.label == "Call ambulance"
        assert top.priority < actor.goal_states[1].priority

    def test_non_urgent_requests_get_default_priority(self):
        os = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human")
        os.set_actor(actor)
        asyncio.run(os.run("Buy groceries"))
        assert actor.goal_states[0].priority == 30


class TestResourcePreconditions:
    """OSS-0302/OSS-0704: a plan step can declare requires_resources — an
    unmet requirement fails the step without ever calling the capability/agent.
    """

    def test_missing_resource_fails_step_without_calling_capability(self):
        class TrackedCap:
            name = "make_tea"
            called = False
            def fn(self, kwargs):
                type(self).called = True
                return {"success": True}

        class Engine:
            async def tick(self, actor):
                return {"plan": {"steps": [
                    {"name": "make_tea", "type": "capability", "requires_resources": {"cup": 1}},
                ]}}

        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human"))
        cap = TrackedCap()
        os.register_capability(cap)
        os.set_engine(Engine())

        result = asyncio.run(os.run("Make tea"))

        assert result.step_results[0].status == "failed"
        assert "cup" in result.step_results[0].error
        assert TrackedCap.called is False

    def test_sufficient_resources_allow_step_to_run(self):
        class Cap:
            name = "make_tea"
            def fn(self, kwargs):
                return {"success": True}

        class Engine:
            async def tick(self, actor):
                return {"plan": {"steps": [
                    {"name": "make_tea", "type": "capability", "requires_resources": {"cup": 1}},
                ]}}

        os = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human")
        os.set_actor(actor)
        actor.add_resource("cup", quantity=1)
        os.register_capability(Cap())
        os.set_engine(Engine())

        result = asyncio.run(os.run("Make tea"))
        assert result.step_results[0].status == "success"

    def test_insufficient_agent_resource_reports_deficit(self):
        class VacuumAgent:
            agent_type = "vacuum_house"
            async def handle(self, kwargs):
                return {"success": True}

        class Engine:
            async def tick(self, actor):
                return {"plan": {"steps": [
                    {"name": "vacuum_house", "type": "agent", "requires_resources": {"battery": 30}},
                ]}}

        os = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human")
        os.set_actor(actor)
        actor.add_resource("battery", quantity=20, unit="percent")
        os.register_agent(VacuumAgent())
        os.set_engine(Engine())

        result = asyncio.run(os.run("Vacuum house"))
        assert result.step_results[0].status == "failed"
        assert "battery (have 20" in result.step_results[0].error


class TestFailFastAndRetry:
    """OSS-0402/OSS-0403: opt-in stop_on_failure and per-step retries."""

    def test_stop_on_failure_skips_remaining_steps_without_running_them(self):
        class OpenMissingFileCap:
            name = "open_missing_file"
            def fn(self, kwargs): return {"success": False, "error": "file_not_found"}

        class NeverReachedCap:
            name = "should_not_run"
            called = False
            def fn(self, kwargs):
                type(self).called = True
                return {"success": True}

        class Engine:
            async def tick(self, actor):
                return {"plan": {"stop_on_failure": True, "steps": [
                    {"name": "open_missing_file", "type": "capability"},
                    {"name": "should_not_run", "type": "capability"},
                ]}}

        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human"))
        os.register_capability(OpenMissingFileCap())
        os.register_capability(NeverReachedCap())
        os.set_engine(Engine())

        result = asyncio.run(os.run("Open a missing file"))

        assert result.step_results[0].status == "failed"
        assert result.step_results[1].status == "skipped"
        assert NeverReachedCap.called is False

    def test_default_chain_still_continues_past_failure(self):
        """stop_on_failure defaults to False — existing examples that
        deliberately show multiple partial-failure steps stay unaffected.
        """
        class FailCap:
            name = "will_fail"
            def fn(self, kwargs): return {"success": False, "error": "boom"}

        class ReachedCap:
            name = "still_runs"
            def fn(self, kwargs): return {"success": True}

        class Engine:
            async def tick(self, actor):
                return {"plan": {"steps": [
                    {"name": "will_fail", "type": "capability"},
                    {"name": "still_runs", "type": "capability"},
                ]}}

        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human"))
        os.register_capability(FailCap())
        os.register_capability(ReachedCap())
        os.set_engine(Engine())

        result = asyncio.run(os.run("Do stuff"))
        assert result.step_results[0].status == "failed"
        assert result.step_results[1].status == "success"

    def test_retries_succeed_on_a_later_attempt(self):
        class FlakyCap:
            name = "http_request"
            attempts = 0
            def fn(self, kwargs):
                type(self).attempts += 1
                if type(self).attempts == 1:
                    return {"success": False, "error": "connection_reset"}
                return {"success": True, "data": "ok"}

        class Engine:
            async def tick(self, actor):
                return {"plan": {"steps": [{"name": "http_request", "type": "capability", "retries": 2}]}}

        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human"))
        os.register_capability(FlakyCap())
        os.set_engine(Engine())

        result = asyncio.run(os.run("Make an HTTP request"))
        sr = result.step_results[0]
        assert sr.status == "success"
        assert sr.attempts == 2

    def test_no_retries_by_default_fails_after_one_attempt(self):
        class AlwaysFailsCap:
            name = "flaky"
            calls = 0
            def fn(self, kwargs):
                type(self).calls += 1
                return {"success": False, "error": "nope"}

        class Engine:
            async def tick(self, actor):
                return {"plan": {"steps": [{"name": "flaky", "type": "capability"}]}}

        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human"))
        os.register_capability(AlwaysFailsCap())
        os.set_engine(Engine())

        result = asyncio.run(os.run("Do it"))
        assert result.step_results[0].status == "failed"
        assert result.step_results[0].attempts == 1
        assert AlwaysFailsCap.calls == 1


class TestConditionalSteps:
    """OSS-0703: a real if/else, evaluated against the actor's beliefs."""

    class UmbrellaCap:
        name = "take_umbrella"
        def fn(self, kwargs): return {"success": True}

    class WalkCap:
        name = "walk"
        def fn(self, kwargs): return {"success": True}

    class WeatherEngine:
        async def tick(self, actor):
            return {"plan": {"steps": [
                {"name": "weather_decision", "type": "conditional",
                 "condition": {"subject": "weather", "attribute": "state", "equals": "raining"},
                 "if_true": "take_umbrella", "if_false": "walk"},
            ]}}

    def _os_with_capabilities(self):
        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human"))
        os.register_capability(self.UmbrellaCap())
        os.register_capability(self.WalkCap())
        os.set_engine(self.WeatherEngine())
        return os

    def test_true_branch_dispatched_when_condition_holds(self):
        os = self._os_with_capabilities()
        os.observe("Weather is raining")
        result = asyncio.run(os.run("Decide what to do"))
        assert result.step_results[0].action == "take_umbrella"
        assert result.step_results[0].status == "success"
        assert result.step_results[0].output["condition_result"] is True

    def test_false_branch_dispatched_when_condition_does_not_hold(self):
        os = self._os_with_capabilities()
        os.observe("Weather is sunny")
        result = asyncio.run(os.run("Decide what to do"))
        assert result.step_results[0].action == "walk"
        assert result.step_results[0].status == "success"
        assert result.step_results[0].output["condition_result"] is False

    def test_unknown_condition_treated_as_false_not_an_error(self):
        """No belief about the subject at all — honest 'we don't know
        that', not a crash."""
        os = self._os_with_capabilities()
        result = asyncio.run(os.run("Decide what to do"))
        assert result.step_results[0].action == "walk"
        assert result.step_results[0].output["condition_result"] is False

    def test_missing_branch_is_reported_skipped(self):
        class OneSidedEngine:
            async def tick(self, actor):
                return {"plan": {"steps": [
                    {"name": "weather_decision", "type": "conditional",
                     "condition": {"subject": "weather", "attribute": "state", "equals": "raining"},
                     "if_true": "take_umbrella"},  # no if_false
                ]}}

        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human"))
        os.register_capability(self.UmbrellaCap())
        os.set_engine(OneSidedEngine())
        os.observe("Weather is sunny")  # condition is False, no if_false branch

        result = asyncio.run(os.run("Decide what to do"))
        assert result.step_results[0].status == "skipped"


class TestInterruptResume:
    """OSS-0802/OSS-0803: interrupt() suspends an in-flight run() before its
    next step/wave and checkpoints the remainder; resume() continues from
    exactly that checkpoint rather than restarting the plan.
    """

    class RecordingCap:
        def __init__(self, name, log, os_ref=None, interrupt_after=False):
            self.name = name
            self._log = log
            self._os = os_ref
            self._interrupt_after = interrupt_after

        def fn(self, kwargs):
            self._log.append(self.name)
            if self._interrupt_after:
                self._os.interrupt("test_signal")
            return {"success": True}

    class ThreeStepChainEngine:
        async def tick(self, actor):
            return {"plan": {"execution": "chain", "steps": [
                {"name": "step_one", "type": "capability"},
                {"name": "step_two", "type": "capability"},
                {"name": "step_three", "type": "capability"},
            ]}}

    class GraphEngine:
        async def tick(self, actor):
            return {"plan": {"execution": "graph", "steps": [
                {"name": "wave_a", "type": "capability"},
                {"name": "wave_b", "type": "capability", "depends_on": ["wave_a"]},
            ]}}

    def _chain_os(self, log, interrupt_on):
        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human"))
        for name in ("step_one", "step_two", "step_three"):
            os.register_capability(self.RecordingCap(name, log, os_ref=os, interrupt_after=(name == interrupt_on)))
        os.set_engine(self.ThreeStepChainEngine())
        return os

    def test_interrupt_stops_before_next_step_and_checkpoints(self):
        log = []
        os = self._chain_os(log, interrupt_on="step_one")
        result = asyncio.run(os.run("Do the thing"))

        assert result.interrupted is True
        assert result.executed is True
        assert log == ["step_one"], "step_two must not run before resume()"
        assert os.has_suspended_plan() is True
        assert [sr.action for sr in result.step_results] == ["step_one"]

    def test_resume_continues_from_checkpoint_not_from_scratch(self):
        log = []
        os = self._chain_os(log, interrupt_on="step_one")
        first = asyncio.run(os.run("Do the thing"))
        assert first.interrupted is True

        resumed = asyncio.run(os.resume())

        assert resumed.interrupted is False
        assert resumed.success is True
        assert log == ["step_one", "step_two", "step_three"], "step_one re-ran on resume"
        assert [sr.action for sr in resumed.step_results] == ["step_one", "step_two", "step_three"]
        assert os.has_suspended_plan() is False

    def test_resumed_step_numbers_continue_not_restart(self):
        log = []
        os = self._chain_os(log, interrupt_on="step_one")
        asyncio.run(os.run("Do the thing"))
        resumed = asyncio.run(os.resume())

        numbers = [sr.step_number for sr in resumed.step_results]
        assert numbers == [1, 2, 3]

    def test_resume_with_nothing_suspended_is_honest_noop(self):
        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human"))

        result = asyncio.run(os.resume())

        assert result.executed is False
        assert result.interrupted is False
        assert "no suspended plan" in result.reasoning.lower()

    def test_interrupt_during_graph_mode_blocks_dependent_wave(self):
        log = []
        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human"))
        os.register_capability(self.RecordingCap("wave_a", log, os_ref=os, interrupt_after=True))
        os.register_capability(self.RecordingCap("wave_b", log))
        os.set_engine(self.GraphEngine())

        result = asyncio.run(os.run("Do the graph thing"))
        assert result.interrupted is True
        assert log == ["wave_a"], "dependent wave_b must not run before resume()"

        resumed = asyncio.run(os.resume())
        assert resumed.interrupted is False
        assert resumed.success is True
        assert log == ["wave_a", "wave_b"]
        assert {sr.action for sr in resumed.step_results} == {"wave_a", "wave_b"}
        assert log.count("wave_a") == 1, "prior wave must not re-run on resume"
