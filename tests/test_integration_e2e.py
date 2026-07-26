"""End-to-end integration tests — multiple real (unmocked) components wired
together through CognitiveOS.run()/send_message()/broadcast(), rather than
one module in isolation. Complements tests/test_os.py (which exercises each
plan-execution feature — chain, graph, retries, resources, conditionals —
one at a time) by combining several of them in a single run, and exercises
the society-runtime messaging path and AffiliationManager-driven delegation,
neither of which tests/test_os.py currently covers at all.
"""
import asyncio
from types import SimpleNamespace

from cognitiveos import Actor, CognitiveOS
from cognitiveos.affiliations.affiliation import Affiliation


class TestFullStackRealPlannerAndCapabilities:
    """No mocked engine, no mocked capability bus — the real
    DeterministicPlanner (via the default LightweightCognitiveEngine) plans
    from real actor beliefs, and real registered capabilities execute the
    resulting steps through the real CapabilityBus, chaining real state.
    """

    def test_cost_objective_plans_and_executes_cheaper_store_first(self):
        class RecordingCapability:
            def __init__(self, name):
                self.name = name

            def fn(self, kwargs):
                context = kwargs.get("context")
                return {"handled_by": self.name, "prior_seen": context.execution_stats.copy()}

        os_ = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human", objective="cost")
        actor.add_belief("pricing", "store_a", attribute="price", value=5, confidence=0.9)
        actor.add_belief("pricing", "store_b", attribute="price", value=3, confidence=0.9)
        os_.set_actor(actor)
        # The real planner also emits a step per fact from the parsed intent
        # itself (the action verb "buy" and the subject "milk" — see
        # LightweightCognitiveEngine._build_belief), not just one per
        # registered price belief — register a handler for every step it
        # will actually produce so the whole run succeeds end to end.
        for name in ("process_buy", "process_milk", "process_store_a", "process_store_b", "achieve_goal"):
            os_.register_capability(RecordingCapability(name))

        result = asyncio.run(os_.run("Buy milk"))

        assert result.success is True
        by_name = {sr.action: sr for sr in result.step_results}
        assert all(sr.status == "success" for sr in by_name.values())
        names_in_order = [sr.action for sr in result.step_results]
        assert names_in_order.index("process_store_b") < names_in_order.index("process_store_a")
        # achieve_goal ran last and had already seen both stores' outputs
        assert "process_store_a" in by_name["achieve_goal"].output["prior_seen"]
        assert "process_store_b" in by_name["achieve_goal"].output["prior_seen"]


class TestKitchenSinkGraphExecution:
    """One graph-mode run combining resource preconditions, retries, cross-
    step dependencies, and a conditional branch — features tests/test_os.py
    only ever exercises in isolation.
    """

    def test_combined_features_in_one_graph_run(self):
        class GatherCapability:
            name = "gather_ingredients"

            def fn(self, kwargs):
                return {"success": True, "cost": 15}

        class FlakyPaymentAgent:
            agent_type = "confirm_payment"
            attempts = 0

            async def handle(self, kwargs):
                type(self).attempts += 1
                state = kwargs.get("state")
                gathered = state.get_data("gather_ingredients")
                if type(self).attempts == 1:
                    return {"success": False, "error": "card_declined"}
                return {"success": True, "charged": gathered["cost"]}

        class SendReceiptCapability:
            name = "send_receipt"

            def fn(self, kwargs):
                return {"success": True, "sent": True}

        class LogFailureCapability:
            name = "log_failure"

            def fn(self, kwargs):
                return {"success": True, "logged": True}

        class KitchenSinkEngine:
            async def tick(self, actor):
                return {"plan": {"execution": "graph", "steps": [
                    {"name": "gather_ingredients", "type": "capability",
                     "requires_resources": {"budget": 20}},
                    {"name": "confirm_payment", "type": "agent", "retries": 2,
                     "depends_on": ["gather_ingredients"]},
                    {"name": "notify_decision", "type": "conditional",
                     "depends_on": ["confirm_payment"],
                     "condition": {"subject": "payment", "attribute": "status", "equals": "confirmed"},
                     "if_true": "send_receipt", "if_false": "log_failure"},
                ]}}

        os_ = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human")
        actor.add_resource("budget", quantity=50)
        actor.add_belief("payment", "payment", attribute="status", value="confirmed")
        os_.set_actor(actor)
        os_.register_capability(GatherCapability())
        os_.register_capability(SendReceiptCapability())
        os_.register_capability(LogFailureCapability())
        os_.register_agent(FlakyPaymentAgent())
        os_.set_engine(KitchenSinkEngine())

        result = asyncio.run(os_.run("Order groceries"))
        by_name = {sr.action: sr for sr in result.step_results}

        assert by_name["gather_ingredients"].status == "success"
        assert by_name["gather_ingredients"].output["cost"] == 15

        assert by_name["confirm_payment"].status == "success"
        assert by_name["confirm_payment"].attempts == 2
        assert by_name["confirm_payment"].output["charged"] == 15

        # The conditional step's StepResult.action reflects the branch that
        # was actually dispatched ("send_receipt"), not the conditional
        # step's own name ("notify_decision") — matching how
        # _dispatch_conditional recursively delegates to _dispatch_step.
        assert "notify_decision" not in by_name
        assert by_name["send_receipt"].status == "success"
        assert by_name["send_receipt"].output["condition_result"] is True

    def test_resource_gate_blocks_the_whole_dependent_chain(self):
        class GatherCapability:
            name = "gather_ingredients"
            called = False

            def fn(self, kwargs):
                type(self).called = True
                return {"success": True, "cost": 15}

        class PaymentAgent:
            agent_type = "confirm_payment"
            called = False

            async def handle(self, kwargs):
                type(self).called = True
                return {"success": True}

        class Engine:
            async def tick(self, actor):
                return {"plan": {"execution": "graph", "steps": [
                    {"name": "gather_ingredients", "type": "capability",
                     "requires_resources": {"budget": 20}},
                    {"name": "confirm_payment", "type": "agent",
                     "depends_on": ["gather_ingredients"]},
                ]}}

        os_ = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human")
        actor.add_resource("budget", quantity=5)  # insufficient
        os_.set_actor(actor)
        os_.register_capability(GatherCapability())
        os_.register_agent(PaymentAgent())
        os_.set_engine(Engine())

        result = asyncio.run(os_.run("Order groceries"))
        by_name = {sr.action: sr for sr in result.step_results}

        assert by_name["gather_ingredients"].status == "failed"
        assert "budget" in by_name["gather_ingredients"].error
        assert GatherCapability.called is False

        assert by_name["confirm_payment"].status == "failed"
        assert by_name["confirm_payment"].error == "dependency_failed:gather_ingredients"
        assert PaymentAgent.called is False


class _FakeSocietyRuntime:
    """Minimal duck-typed double for the society_runtime protocol CognitiveOS
    expects: active_actors(), send_message(from, to, type, payload),
    get_messages_for(actor_id). No real implementation ships in this
    package (SocietyRuntime is intentionally injected from outside), so
    this fake is what stands in for it in these tests.
    """

    def __init__(self):
        self._actors = []
        self.sent = []

    def register(self, actor_id):
        self._actors.append(SimpleNamespace(actor_id=actor_id))

    def active_actors(self):
        return list(self._actors)

    def send_message(self, from_id, to_id, msg_type, payload):
        self.sent.append({"from": from_id, "to": to_id, "type": msg_type, "payload": payload})

    def get_messages_for(self, actor_id):
        return [m for m in self.sent if m["to"] == actor_id]


class TestSocietyRuntimeMessaging:
    """send_message()/broadcast()/get_messages() wired to a real
    society_runtime double, exercising trust enforcement end to end across
    two independent CognitiveOS/Actor pairs sharing one runtime.
    """

    def _two_actors_sharing_runtime(self):
        runtime = _FakeSocietyRuntime()
        alice_os = CognitiveOS()
        bob_os = CognitiveOS()
        alice_os.set_actor(Actor(entity_id="alice", actor_type_id="human"))
        bob_os.set_actor(Actor(entity_id="bob", actor_type_id="human"))
        alice_os.set_society_runtime(runtime)
        bob_os.set_society_runtime(runtime)
        runtime.register("alice")
        runtime.register("bob")
        return runtime, alice_os, bob_os

    def test_send_message_routes_through_runtime_at_default_trust(self):
        runtime, alice_os, _bob_os = self._two_actors_sharing_runtime()
        # default trust (0.5) already clears TRUST_COMMUNICATION_THRESHOLD (0.3)
        sent = alice_os.send_message("bob", "greeting", {"text": "hi"})
        assert sent is True
        assert runtime.sent == [{"from": "alice", "to": "bob", "type": "greeting", "payload": {"text": "hi"}}]

    def test_send_message_blocked_below_trust_threshold(self):
        runtime, alice_os, _bob_os = self._two_actors_sharing_runtime()
        alice_os.actor.affiliations.set_trust("bob", 0.1)
        sent = alice_os.send_message("bob", "greeting", {"text": "hi"})
        assert sent is False
        assert runtime.sent == []

    def test_broadcast_reaches_only_trusted_peers(self):
        runtime, alice_os, _bob_os = self._two_actors_sharing_runtime()
        carol_os = CognitiveOS()
        carol_os.set_actor(Actor(entity_id="carol", actor_type_id="human"))
        carol_os.set_society_runtime(runtime)
        runtime.register("carol")

        alice_os.actor.affiliations.set_trust("carol", 0.1)  # untrusted
        # bob stays at default trust (0.5) — trusted

        sent_count = alice_os.broadcast("announcement", {"msg": "hello all"})

        assert sent_count == 1
        recipients = {m["to"] for m in runtime.sent}
        assert recipients == {"bob"}

    def test_get_messages_filters_by_sender_trust(self):
        runtime, alice_os, bob_os = self._two_actors_sharing_runtime()
        carol_os = CognitiveOS()
        carol_os.set_actor(Actor(entity_id="carol", actor_type_id="human"))
        carol_os.set_society_runtime(runtime)
        runtime.register("carol")

        bob_os.send_message("alice", "note", {"text": "from bob"})
        carol_os.send_message("alice", "note", {"text": "from carol"})
        alice_os.actor.affiliations.set_trust("carol", 0.1)

        received = alice_os.get_messages()
        assert len(received) == 1
        assert received[0]["from"] == "bob"

    def test_no_society_runtime_uses_local_message_bus(self):
        os_ = CognitiveOS()
        os_.set_actor(Actor(entity_id="alice", actor_type_id="human"))
        assert os_.send_message("bob", "hi") is True  # default trust, no runtime -> local bus
        assert os_.get_messages() == [{"from": "alice", "to": "bob", "type": "hi", "payload": {}}]


class TestAffiliationDrivenDelegation:
    """AffiliationManager.discover_participants() genuinely deciding which
    target a later plan step delegates to — not just a standalone query.
    """

    def test_trusted_recruiter_is_selected_and_contacted_over_low_trust_contact(self):
        actor = Actor(entity_id="alice", actor_type_id="human")
        actor.affiliations.add(Affiliation(
            affiliation_id="a1", affiliation_type="employment",
            target_id="acme_recruiter", target_name="Acme Recruiter",
            trust_level=0.9, metadata={},
        ))
        actor.affiliations.add(Affiliation(
            affiliation_id="a2", affiliation_type="employment",
            target_id="cold_contact", target_name="Cold Contact",
            trust_level=0.2, metadata={},
        ))

        contacted = []

        class SelectRecruiterCapability:
            name = "select_recruiter"

            def __init__(self, actor):
                self._actor = actor

            def fn(self, kwargs):
                candidates = self._actor.affiliations.participants("looking for a new job")
                return {"success": True, "target": candidates[0].target_id if candidates else None}

        class ContactRecruiterCapability:
            name = "contact_recruiter"

            def fn(self, kwargs):
                context = kwargs.get("context")
                target = context.get_data("select_recruiter")["target"]
                contacted.append(target)
                return {"success": True, "contacted": target}

        class Engine:
            async def tick(self, actor):
                return {"plan": {"steps": [
                    {"name": "select_recruiter", "type": "capability"},
                    {"name": "contact_recruiter", "type": "capability"},
                ]}}

        os_ = CognitiveOS()
        os_.set_actor(actor)
        os_.register_capability(SelectRecruiterCapability(actor))
        os_.register_capability(ContactRecruiterCapability())
        os_.set_engine(Engine())

        result = asyncio.run(os_.run("Find me a job"))

        assert result.success is True
        assert contacted == ["acme_recruiter"]


class TestAffiliationPersistenceRoundtrip:
    """Serializing/restoring AffiliationManager preserves both discovery
    ranking and trust-gated communication through a fresh CognitiveOS.
    """

    def test_restored_affiliations_still_gate_trust_after_roundtrip(self):
        actor = Actor(entity_id="alice", actor_type_id="human")
        actor.affiliations.add(Affiliation(
            affiliation_id="a1", affiliation_type="employment",
            target_id="bob", target_name="Bob", trust_level=0.9, metadata={},
        ))
        actor.affiliations.add(Affiliation(
            affiliation_id="a2", affiliation_type="employment",
            target_id="eve", target_name="Eve", trust_level=0.1, metadata={},
        ))

        before = [a.target_id for a in actor.affiliations.discover_participants("job search")]

        from cognitiveos.affiliations.manager import AffiliationManager
        restored = AffiliationManager.from_dict(actor.affiliations.to_dict())
        after = [a.target_id for a in restored.discover_participants("job search")]
        # eve's trust (0.1) is below discover_participants' 0.3 minimum-trust
        # filter, so only bob is discoverable, both before and after roundtrip.
        assert before == after == ["bob"]

        fresh_actor = Actor(entity_id="alice2", actor_type_id="human")
        fresh_actor._affiliations = restored
        runtime = _FakeSocietyRuntime()
        os_ = CognitiveOS()
        os_.set_actor(fresh_actor)
        os_.set_society_runtime(runtime)
        runtime.register("alice2")
        runtime.register("bob")
        runtime.register("eve")

        assert os_.send_message("bob", "hi") is True
        assert os_.send_message("eve", "hi") is False
