"""Tests for cognitiveos.engine.belief_state.BeliefState."""
import time

from cognitiveos.engine.belief_state import BeliefState, Fact, Hypothesis


class TestSemanticAPI:
    def test_add_observation_bumps_version(self):
        belief = BeliefState()
        v0 = belief.version
        belief.add_observation("store", "has milk")
        assert belief.version == v0 + 1
        assert belief.observations[0].entity == "store"

    def test_add_fact(self):
        belief = BeliefState()
        belief.add_fact("store_a", "price", 5.0, confidence=0.9)
        assert belief.facts[0].value == 5.0

    def test_add_hypothesis_and_assumption(self):
        belief = BeliefState()
        belief.add_hypothesis("milk is fresh", confidence=0.6, evidence=["e1"])
        belief.add_assumption("store is open", confidence=0.9)
        assert belief.hypotheses[0].claim == "milk is fresh"
        assert belief.assumptions[0].statement == "store is open"

    def test_update_intent_and_goal(self):
        belief = BeliefState()
        belief.update_intent("purchase", confidence=0.8, metadata={"k": "v"})
        belief.update_goal("buy_milk", description="get milk", success_criteria=["has_milk"])
        assert belief.intent.type == "purchase"
        assert belief.goal.name == "buy_milk"
        # update_goal() passes success_criteria straight through when truthy
        # (only defaults to () when falsy) — it doesn't cast list -> tuple.
        assert list(belief.goal.success_criteria) == ["has_milk"]

    def test_update_plan(self):
        belief = BeliefState()
        belief.update_plan(["step1", "step2"], start_state="s0", goal_state="s1")
        assert belief.plan.steps == ("step1", "step2")
        assert belief.plan.start_state == "s0"

    def test_record_prediction_and_learning(self):
        belief = BeliefState()
        belief.record_prediction("it will rain", confidence=0.4, based_on=["forecast"])
        belief.record_learning("rain matters", evidence=["obs1"], confidence=0.7)
        assert belief.predictions[0].description == "it will rain"
        assert belief.learned_updates[0].what == "rain matters"

    def test_add_to_working_memory(self):
        belief = BeliefState()
        belief.add_to_working_memory("k", "v", ttl_seconds=60)
        assert belief.working_memory[0].key == "k"
        assert belief.working_memory[0].expires_at > time.time()


class TestQueryAPI:
    def test_recall_matches_value_or_entity(self):
        belief = BeliefState()
        belief.add_fact("store_a", "price", "cheap")
        belief.add_fact("store_b", "price", "expensive")
        results = belief.recall("cheap")
        assert len(results) == 1
        assert results[0].entity == "store_a"

    def test_confidence_and_confidence_for(self):
        belief = BeliefState()
        belief.uncertainty.confidence = 0.7
        belief.uncertainty.confidence_by_source["sensor"] = 0.9
        assert belief.confidence() == 0.7
        assert belief.confidence_for("sensor") == 0.9
        assert belief.confidence_for("unknown_source") == 0.7


class TestSnapshotAndSerialization:
    def test_snapshot_counts(self):
        belief = BeliefState(actor_id="alice")
        belief.add_fact("a", "b", "c")
        belief.add_hypothesis("h")
        snap = belief.snapshot()
        assert snap.actor_id == "alice"
        assert snap.facts_count == 1
        assert snap.hypotheses_count == 1

    def test_to_dict_contains_expected_keys(self):
        belief = BeliefState(actor_id="alice")
        belief.add_fact("a", "b", "c")
        d = belief.to_dict()
        assert d["actor_id"] == "alice"
        assert len(d["facts"]) == 1

    def test_summary(self):
        belief = BeliefState(actor_id="alice")
        belief.add_fact("a", "b", "c")
        summary = belief.summary()
        assert summary["actor_id"] == "alice"
        assert summary["facts"] == 1


class TestDecayAndPrune:
    def test_returns_pruned_counts(self):
        belief = BeliefState()
        belief.facts.append(Fact(entity="e", attribute="a", value=1, confidence=0.05,
                                  observed_at=time.time() - 1000))
        result = belief.decay_and_prune()
        assert result["pruned_facts"] == 1
        assert belief.facts == []

    def test_decay_never_raises_confidence_above_original(self):
        """Regression: decay_and_prune previously clamped a retained fact's
        confidence up to fact_confidence_floor (default 0.7) unconditionally,
        so a fact observed at confidence 0.2 came out at 0.7 — higher than
        before "decaying". A floor must never exceed the fact's own starting
        confidence.
        """
        belief = BeliefState()
        belief.facts.append(Fact(entity="e", attribute="a", value=1, confidence=0.2,
                                  observed_at=time.time()))
        belief.decay_and_prune(fact_prune_threshold=0.0)
        assert len(belief.facts) == 1
        assert belief.facts[0].confidence <= 0.2

    def test_decay_reduces_confidence_over_time(self):
        belief = BeliefState()
        old_time = time.time() - 1000  # far enough in the past to decay meaningfully
        belief.facts.append(Fact(entity="e", attribute="a", value=1, confidence=0.9,
                                  observed_at=old_time))
        belief.decay_and_prune(fact_prune_threshold=0.0, fact_confidence_floor=0.0)
        assert belief.facts[0].confidence < 0.9

    def test_high_confidence_fact_can_still_use_floor_as_a_true_floor(self):
        """A fact that started above the floor and decays down to just below
        it is still floored at the (lower) floor value, not pushed below it —
        this is the one case where floor semantics legitimately apply."""
        belief = BeliefState()
        belief.facts.append(Fact(entity="e", attribute="a", value=1, confidence=0.9,
                                  observed_at=time.time() - 1000))
        belief.decay_and_prune(fact_prune_threshold=0.0, fact_confidence_floor=0.5, decay_rate=0.5)
        assert belief.facts[0].confidence >= 0.5

    def test_hypothesis_pruning_below_threshold(self):
        belief = BeliefState()
        belief.hypotheses.append(Hypothesis(claim="h", confidence=0.01,
                                             created_at=time.time() - 1000))
        result = belief.decay_and_prune()
        assert result["pruned_hypotheses"] == 1
        assert belief.hypotheses == []

    def test_max_hypotheses_trims_lowest_confidence(self):
        belief = BeliefState()
        for i in range(5):
            belief.hypotheses.append(Hypothesis(claim=f"h{i}", confidence=0.9 - i * 0.05))
        result = belief.decay_and_prune(max_hypotheses=3, hypothesis_prune_threshold=0.0)
        assert len(belief.hypotheses) == 3
        assert result["pruned_hypotheses"] == 2
        # kept the highest-confidence ones
        assert {h.claim for h in belief.hypotheses} == {"h0", "h1", "h2"}
