"""Tests for CognitiveOS Actor."""
import pytest
from cognitiveos.actor import Actor, Identity, GoalState, BeliefState, CapabilityState, ResourceState


class TestActorGoals:
    def test_add_goal(self):
        a = Actor(entity_id="a1", actor_type_id="human")
        g = a.add_goal("wealth", priority=30)
        assert g.goal_type_id == "wealth"
        assert g.priority == 30
        assert len(a.goal_states) == 1

    def test_remove_goal(self):
        a = Actor(entity_id="a1", actor_type_id="human")
        a.add_goal("wealth")
        a.add_goal("safety")
        assert a.remove_goal("wealth") is True
        assert len(a.goal_states) == 1

    def test_top_goal(self):
        a = Actor(entity_id="a1", actor_type_id="human")
        a.add_goal("wealth", priority=40)
        a.add_goal("safety", priority=5)
        top = a.top_goal()
        assert top.goal_type_id == "safety"

    def test_current_goal_from_constructor(self):
        a = Actor(entity_id="a1", actor_type_id="human", goals=["wealth", "safety"])
        assert a._current_goal == "wealth"

    def test_add_goal_with_label_distinguishes_same_type_goals(self):
        """goal_type_id is a coarse ontology bucket — two unrelated goals of
        the same type need label to stay distinguishable."""
        a = Actor(entity_id="a1", actor_type_id="human")
        a.add_goal("accomplishment", priority=30, label="Buy milk")
        a.add_goal("accomplishment", priority=30, label="Charge laptop")
        assert len(a.goal_states) == 2
        assert {g.label for g in a.goal_states} == {"Buy milk", "Charge laptop"}

    def test_update_goal_progress_preserves_label(self):
        a = Actor(entity_id="a1", actor_type_id="human")
        a.add_goal("wealth", priority=30, label="Buy milk")
        a.update_goal_progress("wealth", 0.5)
        assert a.goal_states[0].label == "Buy milk"
        assert a.goal_states[0].progress == 0.5


class TestActorBeliefs:
    def test_add_belief(self):
        a = Actor(entity_id="a1", actor_type_id="human")
        b = a.add_belief("observation", "store_a_stock", confidence=0.8)
        assert b.confidence == 0.8
        assert len(a.beliefs) == 1

    def test_highest_confidence(self):
        a = Actor(entity_id="a1", actor_type_id="human")
        a.add_belief("observation", "store_a", confidence=0.3)
        a.add_belief("observation", "store_a", confidence=0.9)
        best = a.highest_confidence("store_a")
        assert best.confidence == 0.9

    def test_decay_beliefs(self):
        a = Actor(entity_id="a1", actor_type_id="human")
        a.add_belief("observation", "store_a", confidence=0.3)
        a.add_belief("observation", "store_b", confidence=0.02)
        removed = a.decay_beliefs(decay_rate=0.05)
        assert removed == 1
        assert len(a.beliefs) == 1

    def test_attribute_belief_revises_in_place(self):
        """A belief with an attribute (subject.attribute=value) is a
        property with one current value — a later add_belief() for the
        same (subject, attribute) replaces it rather than accumulating.
        """
        a = Actor(entity_id="a1", actor_type_id="human")
        a.add_belief("observation", "door", attribute="state", value="closed")
        assert [(b.subject, b.attribute, b.value) for b in a.beliefs] == [("door", "state", "closed")]

        a.add_belief("observation", "door", attribute="state", value="open")
        assert [(b.subject, b.attribute, b.value) for b in a.beliefs] == [("door", "state", "open")]
        assert len(a.beliefs) == 1

    def test_beliefs_without_attribute_still_accumulate(self):
        """Backward compatible: the original belief_type_id+subject shape
        (no attribute) has no single "current value" to revise, so it
        stays append-only — matches test_highest_confidence's existing
        two-beliefs-about-the-same-subject usage.
        """
        a = Actor(entity_id="a1", actor_type_id="human")
        a.add_belief("observation", "store_a", confidence=0.3)
        a.add_belief("observation", "store_a", confidence=0.9)
        assert len(a.beliefs) == 2


class TestActorCapabilities:
    def test_has_capability(self):
        a = Actor(entity_id="a1", actor_type_id="ai_agent")
        a.add_capability("coding")
        assert a.has_capability("coding") is True
        assert a.has_capability("diagnosis") is False


class TestActorResources:
    def test_has_resource(self):
        a = Actor(entity_id="a1", actor_type_id="human")
        a.add_resource("money", quantity=1000)
        assert a.has_resource("money", min_quantity=500) is True
        assert a.has_resource("money", min_quantity=2000) is False

    def test_resource_quantity(self):
        a = Actor(entity_id="a1", actor_type_id="human")
        a.add_resource("money", quantity=500)
        a.add_resource("money", quantity=300)
        assert a.resource_quantity("money") == 800


class TestActorIntegration:
    def test_full_actor(self):
        a = Actor(entity_id="alice", actor_type_id="human", name="Alice",
                 goals=["wealth", "safety"], objective="cost")
        assert a.actor_type_id == "human"
        assert a.identity.name == "Alice"
        a.add_goal("mastery", priority=20)
        assert len(a.goal_states) == 3
        a.add_belief("observation", "market", confidence=0.8)
        a.add_capability("coding", proficiency=0.9)
        a.add_resource("money", quantity=5000)
        assert a.has_capability("coding")
        assert a.resource_quantity("money") == 5000
        assert len(a.affiliations.all()) == 0
