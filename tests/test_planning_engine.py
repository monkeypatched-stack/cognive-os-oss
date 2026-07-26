"""Tests for cognitiveos.engine.planning_engine.DeterministicPlanner."""
from cognitiveos.engine.belief_state import BeliefState, Goal
from cognitiveos.engine.planning_engine import DeterministicPlanner


class TestEmptyGoal:
    def test_empty_goal_name_returns_empty_plan(self):
        planner = DeterministicPlanner()
        belief = BeliefState()
        plan = planner.plan(belief, Goal(name=""))
        assert plan.goal == ""
        assert plan.confidence == 0.0
        assert plan.steps == ()


class TestBasicPlanning:
    def test_no_facts_produces_no_steps(self):
        planner = DeterministicPlanner()
        belief = BeliefState()
        belief.update_goal(name="buy_milk")
        plan = planner.plan(belief, belief.goal)
        assert plan.steps == ()
        assert plan.preconditions == ("goal_defined:buy_milk",)

    def test_facts_produce_process_steps_and_final_achieve_goal_step(self):
        planner = DeterministicPlanner()
        belief = BeliefState()
        belief.update_goal(name="buy_milk")
        belief.add_fact(entity="store_a", attribute="stock", value=10, confidence=0.9)
        plan = planner.plan(belief, belief.goal)

        step_actions = [s.action for s in plan.steps]
        assert "process_store_a" in step_actions
        assert step_actions[-1] == "achieve_goal"

    def test_world_entity_is_skipped(self):
        planner = DeterministicPlanner()
        belief = BeliefState()
        belief.update_goal(name="g")
        belief.add_fact(entity="world", attribute="time", value="noon", confidence=0.9)
        plan = planner.plan(belief, belief.goal)
        assert plan.steps == ()

    def test_low_stock_entity_is_skipped(self):
        planner = DeterministicPlanner()
        belief = BeliefState()
        belief.update_goal(name="g")
        belief.add_fact(entity="store_a", attribute="stock", value=1, confidence=0.9)
        plan = planner.plan(belief, belief.goal)
        assert plan.steps == ()

    def test_sufficient_stock_entity_is_included(self):
        planner = DeterministicPlanner()
        belief = BeliefState()
        belief.update_goal(name="g")
        belief.add_fact(entity="store_a", attribute="stock", value=3, confidence=0.9)
        plan = planner.plan(belief, belief.goal)
        assert any(s.action == "process_store_a" for s in plan.steps)

    def test_low_confidence_fact_adds_verify_precondition(self):
        from cognitiveos.engine.belief_state import Fact

        planner = DeterministicPlanner()
        fact = Fact(entity="store_a", attribute="price", value=5, confidence=0.3)
        preconditions = planner._determine_preconditions([fact], Goal(name="g"))
        assert preconditions == ["verify:store_a.price"]

    def test_low_confidence_fact_reaches_preconditions_through_full_plan_when_relevant(self):
        """End-to-end: a low-confidence fact only becomes 'relevant' (and thus
        reaches _determine_preconditions) if it shares a word with the goal,
        since _find_relevant_facts only includes low-confidence facts on a
        keyword match (confidence >= 0.7 is the other, unconditional path)."""
        planner = DeterministicPlanner()
        belief = BeliefState()
        belief.update_goal(name="store_a")
        belief.add_fact(entity="store_a", attribute="price", value=5, confidence=0.3)
        plan = planner.plan(belief, belief.goal)
        assert "verify:store_a.price" in plan.preconditions


class TestObjectiveWeighting:
    def test_cost_objective_favors_cheaper_entity(self):
        planner = DeterministicPlanner()
        belief = BeliefState()
        belief.update_goal(name="buy_milk", optimization_objective="cost")
        belief.add_fact(entity="store_a", attribute="price", value=5.0, confidence=0.9)
        belief.add_fact(entity="store_b", attribute="price", value=2.0, confidence=0.9)

        plan = planner.plan(belief, belief.goal)
        process_steps = [s.action for s in plan.steps if s.action.startswith("process_")]
        assert process_steps.index("process_store_b") < process_steps.index("process_store_a")

    def test_speed_objective_favors_shorter_distance(self):
        planner = DeterministicPlanner()
        belief = BeliefState()
        belief.update_goal(name="deliver", optimization_objective="speed")
        belief.add_fact(entity="warehouse_far", attribute="distance", value=10.0, confidence=0.9)
        belief.add_fact(entity="warehouse_near", attribute="distance", value=1.0, confidence=0.9)

        plan = planner.plan(belief, belief.goal)
        process_steps = [s.action for s in plan.steps if s.action.startswith("process_")]
        assert process_steps.index("process_warehouse_near") < process_steps.index("process_warehouse_far")

    def test_reliability_objective_favors_higher_reliability_and_marks_trusted(self):
        planner = DeterministicPlanner()
        belief = BeliefState()
        belief.update_goal(name="pick_supplier", optimization_objective="reliability")
        belief.add_fact(entity="supplier_a", attribute="reliability", value=0.95, confidence=0.9)
        belief.add_fact(entity="supplier_b", attribute="reliability", value=0.5, confidence=0.9)

        plan = planner.plan(belief, belief.goal)
        process_steps = {s.action: s for s in plan.steps if s.action.startswith("process_")}
        assert list(process_steps.keys()).index("process_supplier_a") < list(process_steps.keys()).index("process_supplier_b")
        assert "[TRUSTED]" in process_steps["process_supplier_a"].description

    def test_no_objective_does_not_reorder_by_price(self):
        planner = DeterministicPlanner()
        belief = BeliefState()
        belief.update_goal(name="buy_milk")  # no optimization_objective
        belief.add_fact(entity="store_a", attribute="price", value=5.0, confidence=0.9)
        belief.add_fact(entity="store_b", attribute="price", value=2.0, confidence=0.9)

        plan = planner.plan(belief, belief.goal)
        process_steps = [s.action for s in plan.steps if s.action.startswith("process_")]
        # same confidence (1.0 success_prob for both, no objective weighting) ->
        # stable sort keeps insertion (entity dict) order: store_a before store_b
        assert process_steps.index("process_store_a") < process_steps.index("process_store_b")


class TestTransitionModel:
    class _Transition:
        def __init__(self, probability):
            self.probability = probability

    class _TransitionModel:
        def __init__(self, mapping):
            self.known_transitions = mapping

    def test_low_success_probability_marks_high_risk(self):
        planner = DeterministicPlanner()
        belief = BeliefState()
        belief.update_goal(name="g")
        belief.metadata["transition_model"] = self._TransitionModel(
            {"process_store_a": (self._Transition(0.3),)}
        )
        belief.add_fact(entity="store_a", attribute="stock", value=10, confidence=0.9)

        plan = planner.plan(belief, belief.goal)
        step = next(s for s in plan.steps if s.action == "process_store_a")
        assert "[HIGH RISK]" in step.description

    def test_medium_success_probability_marks_monitor(self):
        planner = DeterministicPlanner()
        belief = BeliefState()
        belief.update_goal(name="g")
        belief.metadata["transition_model"] = self._TransitionModel(
            {"process_store_a": (self._Transition(0.6),)}
        )
        belief.add_fact(entity="store_a", attribute="stock", value=10, confidence=0.9)

        plan = planner.plan(belief, belief.goal)
        step = next(s for s in plan.steps if s.action == "process_store_a")
        assert "[MONITOR]" in step.description

    def test_high_success_probability_no_risk_note(self):
        planner = DeterministicPlanner()
        belief = BeliefState()
        belief.update_goal(name="g")
        belief.metadata["transition_model"] = self._TransitionModel(
            {"process_store_a": (self._Transition(0.95),)}
        )
        belief.add_fact(entity="store_a", attribute="stock", value=10, confidence=0.9)

        plan = planner.plan(belief, belief.goal)
        step = next(s for s in plan.steps if s.action == "process_store_a")
        assert "RISK" not in step.description and "MONITOR" not in step.description


class TestGoalAnalysis:
    def test_success_criteria_and_description_become_required_conditions(self):
        planner = DeterministicPlanner()
        goal = Goal(name="g", description="a nice description",
                    success_criteria=("has_milk", "has_eggs"))
        required = planner._analyze_goal(goal, BeliefState())
        assert "achieve:g" in required
        assert "criterion:has_milk" in required
        assert "criterion:has_eggs" in required
        assert "context:a nice description" in required


class TestSpeedObjectiveDelivery:
    def test_delivery_attribute_also_weighted_for_speed(self):
        planner = DeterministicPlanner()
        belief = BeliefState()
        belief.update_goal(name="deliver", optimization_objective="speed")
        belief.add_fact(entity="slow_supplier", attribute="delivery", value=10.0, confidence=0.9)
        belief.add_fact(entity="fast_supplier", attribute="delivery", value=1.0, confidence=0.9)

        plan = planner.plan(belief, belief.goal)
        process_steps = [s.action for s in plan.steps if s.action.startswith("process_")]
        assert process_steps.index("process_fast_supplier") < process_steps.index("process_slow_supplier")


class TestReliabilityFreshness:
    def test_freshness_contributes_to_reliability_score(self):
        planner = DeterministicPlanner()
        belief = BeliefState()
        belief.update_goal(name="pick_supplier", optimization_objective="reliability")
        belief.add_fact(entity="fresh_supplier", attribute="reliability", value=0.7, confidence=0.9)
        belief.add_fact(entity="fresh_supplier", attribute="freshness", value=72.0, confidence=0.9)
        belief.add_fact(entity="stale_supplier", attribute="reliability", value=0.7, confidence=0.9)
        belief.add_fact(entity="stale_supplier", attribute="freshness", value=1.0, confidence=0.9)

        plan = planner.plan(belief, belief.goal)
        process_steps = [s.action for s in plan.steps if s.action.startswith("process_")]
        assert process_steps.index("process_fresh_supplier") < process_steps.index("process_stale_supplier")


class TestOutcomes:
    def test_outcomes_include_goal_and_step_outcomes(self):
        planner = DeterministicPlanner()
        belief = BeliefState()
        belief.update_goal(name="buy_milk")
        belief.add_fact(entity="store_a", attribute="stock", value=10, confidence=0.9)
        plan = planner.plan(belief, belief.goal)
        assert plan.expected_outcomes[0] == "goal_achieved:buy_milk"
        assert any("store_a" in o for o in plan.expected_outcomes)
