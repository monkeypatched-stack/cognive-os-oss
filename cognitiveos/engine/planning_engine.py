"""Deterministic PlanningEngine — fact-based planning from beliefs and goals.

Ported from monkeypatched's kernel/pipeline/planning_engine.py, with the
import path adjusted to this package. Otherwise unmodified — this is the
real forward-chaining planner, not a simplified stand-in.

The default planning engine:
1. Analyzes the goal to determine required states
2. Searches belief facts for preconditions
3. Generates steps that achieve the goal from available facts
4. Estimates cost and confidence from fact coverage

This is a simple forward-chaining planner.
Real planners (GOAP, HTN, LLM) will replace this for production use.
"""
from __future__ import annotations

import logging
from typing import Any

from cognitiveos.engine.belief_state import (
    BeliefState,
    Fact,
    Goal,
    Plan,
    PlanStep,
)

logger = logging.getLogger("agentos.pipeline.planning_engine")


class DeterministicPlanner:
    """Default planning engine — fact-based forward chaining.

    Produces plans by:
    1. Analyzing goal requirements
    2. Matching against known facts
    3. Generating steps to fill gaps
    4. Estimating cost from plan length and fact coverage
    """

    def plan(
        self,
        belief: BeliefState,
        goal: Goal,
        context: Any = None,
    ) -> Plan:
        """Generate a plan from beliefs and goal.

        Args:
            belief: Current belief state with facts, hypotheses, confidence
            goal: What to achieve
            context: Optional runtime context

        Returns:
            Structured Plan with steps, preconditions, and estimates
        """
        if not goal.name:
            return Plan(
                goal="",
                confidence=0.0,
                planner="deterministic",
            )

        # Analyze what the goal requires
        required = self._analyze_goal(goal, belief)

        # Find relevant facts
        relevant_facts = self._find_relevant_facts(belief, required)

        # Get transition model from belief metadata if available
        transition_model = belief.metadata.get("transition_model") if hasattr(belief, "metadata") else None

        # Generate plan steps
        steps = self._generate_steps(goal, relevant_facts, required, transition_model)

        # Calculate metrics
        coverage = len(relevant_facts) / max(len(required), 1)
        cost = len(steps) / 10.0  # Simple cost model
        confidence = min(1.0, coverage * belief.confidence())
        risk = max(0.0, 1.0 - confidence)

        # Determine preconditions
        preconditions = self._determine_preconditions(relevant_facts, goal)

        # Determine expected outcomes
        outcomes = self._determine_outcomes(goal, steps)

        plan = Plan(
            goal=goal.name,
            preconditions=tuple(preconditions),
            steps=tuple(steps),
            expected_outcomes=tuple(outcomes),
            cost=min(1.0, cost),
            confidence=confidence,
            risk=risk,
            goal_state=goal.name,
            planner="deterministic",
        )

        logger.debug(
            "[planner] Generated plan: %d steps, confidence=%.2f, cost=%.2f",
            len(steps), confidence, cost,
        )

        return plan

    def _analyze_goal(self, goal: Goal, belief: BeliefState) -> list[str]:
        """Determine what states/conditions the goal requires."""
        required = []
        if goal.name:
            required.append(f"achieve:{goal.name}")
        for criterion in goal.success_criteria:
            required.append(f"criterion:{criterion}")
        if goal.description:
            required.append(f"context:{goal.description}")
        return required

    def _find_relevant_facts(
        self, belief: BeliefState, required: list[str],
    ) -> list[Fact]:
        """Find facts relevant to achieving the goal."""
        relevant = []
        goal_words = set()
        for req in required:
            goal_words.update(req.lower().split(":")[-1].split())

        for fact in belief.facts:
            fact_words = {fact.entity.lower(), fact.attribute.lower()}
            if fact_words & goal_words or fact.confidence >= 0.7:
                relevant.append(fact)

        # Also include high-confidence facts even if not directly matching
        for fact in belief.facts:
            if fact.confidence >= 0.8 and fact not in relevant:
                relevant.append(fact)

        return relevant

    def _generate_steps(
        self, goal: Goal, facts: list[Fact], required: list[str],
        transition_model: Any = None,
    ) -> list[PlanStep]:
        """Generate plan steps from facts and requirements.

        Uses the goal's optimization_objective to weight and sort steps.
        """
        steps = []
        objective = getattr(goal, 'optimization_objective', '') or ''

        # Group facts by entity
        by_entity: dict[str, list[Fact]] = {}
        for fact in facts:
            by_entity.setdefault(fact.entity, []).append(fact)

        for entity, entity_facts in by_entity.items():
            if entity == "world":
                continue

            # Skip entities with insufficient stock (need at least 3 units)
            stock_facts = [f for f in entity_facts if 'stock' in f.attribute.lower()]
            if stock_facts:
                stock_value = stock_facts[0].value
                if isinstance(stock_value, (int, float)) and stock_value < 3:
                    continue  # Out of stock — don't generate a plan step

            attrs = [f"{f.attribute}={f.value}" for f in entity_facts]
            action_key = f"process_{entity}"

            # Look up transition probability
            success_prob = 1.0
            if transition_model and hasattr(transition_model, "known_transitions"):
                transitions = transition_model.known_transitions.get(action_key, ())
                if transitions:
                    success_prob = transitions[0].probability

            # Compute objective-weighted score
            score = success_prob
            risk_note = ""
            if objective == 'cost':
                # Favor entities with low price
                for f in entity_facts:
                    if 'price' in f.attribute.lower() and isinstance(f.value, (int, float)):
                        score *= (1.0 / max(f.value, 0.5))
                        if f.value < 1.5:
                            risk_note = " [CHEAP]"
            elif objective == 'speed':
                # Favor entities with low distance/delivery time
                for f in entity_facts:
                    if 'distance' in f.attribute.lower() and isinstance(f.value, (int, float)):
                        score *= (1.0 / max(f.value, 0.5))
                        if f.value < 2.0:
                            risk_note = " [NEAR]"
                    if 'delivery' in f.attribute.lower() and isinstance(f.value, (int, float)):
                        score *= (1.0 / max(f.value, 1))
            elif objective == 'reliability':
                # Weighted reliability score: reliability*0.8 + (freshness/72)*0.2
                # Matches agent scoring formula exactly
                rel_score = 0.5  # base
                for f in entity_facts:
                    if 'reliability' in f.attribute.lower() and isinstance(f.value, (int, float)):
                        rel_score = f.value * 0.8
                        if f.value > 0.85:
                            risk_note = " [TRUSTED]"
                    if 'freshness' in f.attribute.lower() and isinstance(f.value, (int, float)):
                        rel_score += (f.value / 72.0) * 0.2
                score *= rel_score

            if success_prob < 0.5:
                risk_note = " [HIGH RISK]"
            elif success_prob < 0.7 and not risk_note:
                risk_note = " [MONITOR]"

            steps.append(PlanStep(
                action=action_key,
                description=f"Process {entity}: {', '.join(attrs[:3])}{risk_note}",
                preconditions=(f"observe:{entity}",),
                expected_outcome=f"{entity} processed (p={success_prob:.0%})",
                cost=0.1,
                confidence=min(1.0, max(0.0, score)),
            ))

        # Sort by objective-weighted confidence
        steps.sort(key=lambda s: s.confidence, reverse=True)

        # Add goal-achievement step
        if steps:
            overall_conf = min(s.confidence for s in steps) if steps else 0.5
            steps.append(PlanStep(
                action="achieve_goal",
                description=f"Achieve goal: {goal.name} ({objective or 'balanced'})",
                preconditions=tuple(s.action for s in steps),
                expected_outcome=goal.name,
                cost=0.2,
                confidence=overall_conf,
            ))

        return steps

    def _determine_preconditions(
        self, facts: list[Fact], goal: Goal,
    ) -> list[str]:
        """Determine what must be true before the plan can execute."""
        preconditions = []
        for fact in facts:
            if fact.confidence < 0.5:
                preconditions.append(f"verify:{fact.entity}.{fact.attribute}")
        if not preconditions:
            preconditions.append(f"goal_defined:{goal.name}")
        return preconditions

    def _determine_outcomes(self, goal: Goal, steps: list[PlanStep]) -> list[str]:
        """Determine expected outcomes of the plan."""
        outcomes = [f"goal_achieved:{goal.name}"]
        for step in steps:
            if step.expected_outcome:
                outcomes.append(step.expected_outcome)
        return outcomes
