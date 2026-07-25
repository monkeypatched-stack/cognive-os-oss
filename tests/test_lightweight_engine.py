"""Tests for LightweightCognitiveEngine._build_belief() (OSS-0304).

Two related gaps, found and fixed together:
  1. Actor(objective=...) was never threaded into BeliefState.update_goal(),
     so DeterministicPlanner's objective-weighted scoring (cost/speed/
     reliability) was silently unreachable from the public Actor API.
  2. An attribute-bearing belief (actor.add_belief(..., attribute="price",
     value=5)) had its real attribute/value discarded in favor of
     attribute=belief_type_id, value=confidence — so belief data could
     never surface as a planner fact under its real name.
"""
import asyncio

from cognitiveos import Actor, CognitiveOS


class TestObjectiveWiring:
    def test_actor_objective_reaches_planner_goal(self):
        from cognitiveos.engine.lightweight_engine import LightweightCognitiveEngine

        actor = Actor(entity_id="alice", actor_type_id="human", objective="cost")
        engine = LightweightCognitiveEngine()
        belief = engine._build_belief(actor)
        assert belief.goal.optimization_objective == "cost"

    def test_no_objective_defaults_to_empty(self):
        from cognitiveos.engine.lightweight_engine import LightweightCognitiveEngine

        actor = Actor(entity_id="alice", actor_type_id="human")
        engine = LightweightCognitiveEngine()
        belief = engine._build_belief(actor)
        assert belief.goal.optimization_objective == ""


class TestBeliefAttributePassthrough:
    def test_attribute_bearing_belief_surfaces_real_attribute_and_value(self):
        from cognitiveos.engine.lightweight_engine import LightweightCognitiveEngine

        actor = Actor(entity_id="alice", actor_type_id="human")
        actor.add_belief("pricing", "store_a", attribute="price", value=5, confidence=0.9)
        engine = LightweightCognitiveEngine()
        belief = engine._build_belief(actor)

        price_facts = [f for f in belief.facts if f.entity == "store_a"]
        assert len(price_facts) == 1
        assert price_facts[0].attribute == "price"
        assert price_facts[0].value == 5

    def test_legacy_subject_only_belief_still_uses_belief_type_id_and_confidence(self):
        """No attribute set — falls back to the original behavior (there's
        no real attribute/value to preserve, just a type + confidence)."""
        from cognitiveos.engine.lightweight_engine import LightweightCognitiveEngine

        actor = Actor(entity_id="alice", actor_type_id="human")
        actor.add_belief("observation", "market", confidence=0.7)
        engine = LightweightCognitiveEngine()
        belief = engine._build_belief(actor)

        market_facts = [f for f in belief.facts if f.entity == "market"]
        assert len(market_facts) == 1
        assert market_facts[0].attribute == "observation"
        assert market_facts[0].value == 0.7


class TestCostOptimizationEndToEnd:
    """OSS-0304: given real price beliefs and objective='cost', the
    cheaper option is genuinely favored by the real (unmocked) planner
    end to end through os.run() — no hardcoded store names or outcomes."""

    def test_cheaper_store_ranked_first_in_plan(self):
        os_ = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human", objective="cost")
        actor.add_belief("pricing", "store_a", attribute="price", value=5, confidence=0.9)
        actor.add_belief("pricing", "store_b", attribute="price", value=3, confidence=0.9)
        os_.set_actor(actor)

        result = asyncio.run(os_.run("Buy milk"))
        names = [s["name"] for s in result.steps]

        assert "process_store_a" in names and "process_store_b" in names
        assert names.index("process_store_b") < names.index("process_store_a")

    def test_without_cost_objective_price_does_not_drive_order(self):
        """Sanity check the fix is genuinely objective-gated, not just
        always sorting by price regardless of actor.objective."""
        os_ = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human")  # no objective
        actor.add_belief("pricing", "store_a", attribute="price", value=5, confidence=0.9)
        actor.add_belief("pricing", "store_b", attribute="price", value=3, confidence=0.9)
        os_.set_actor(actor)

        result = asyncio.run(os_.run("Buy milk"))
        names = [s["name"] for s in result.steps]
        # Both stores are still planned for (facts are always relevant at
        # confidence >= 0.7) — same insertion order in, same order out,
        # since no objective weighting applies without objective="cost".
        assert names.index("process_store_a") < names.index("process_store_b")
