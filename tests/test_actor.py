"""Tests for CognitiveOS Actor."""
from cognitiveos.actor import Actor


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

    def test_best_capability_picks_highest_proficiency(self):
        a = Actor(entity_id="a1", actor_type_id="ai_agent")
        a.add_capability("coding", proficiency=0.4)
        a.add_capability("coding", proficiency=0.9)
        best = a.best_capability("coding")
        assert best.proficiency == 0.9

    def test_best_capability_returns_none_when_no_match(self):
        a = Actor(entity_id="a1", actor_type_id="ai_agent")
        assert a.best_capability("coding") is None


class TestActorBeliefsByType:
    def test_beliefs_by_type(self):
        a = Actor(entity_id="a1", actor_type_id="human")
        a.add_belief("observation", "market", confidence=0.7)
        a.add_belief("trust_belief", "bob", confidence=0.5)
        obs = a.beliefs_by_type("observation")
        assert len(obs) == 1
        assert obs[0].subject == "market"


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


class TestActorWithoutBoundOS:
    """Actor delegates cognition to self.os — before an OS is bound, these
    methods must fail honestly rather than raise."""

    def test_tick_without_os_returns_error_dict(self):
        import asyncio
        a = Actor(entity_id="a1", actor_type_id="human")
        result = asyncio.run(a.tick())
        assert result == {"error": "No CognitiveOS bound to this actor"}

    def test_observe_without_os_returns_none(self):
        a = Actor(entity_id="a1", actor_type_id="human")
        assert a.observe() is None

    def test_send_message_without_os_returns_false(self):
        a = Actor(entity_id="a1", actor_type_id="human")
        assert a.send_message("bob", "hi") is False

    def test_broadcast_without_os_returns_zero(self):
        a = Actor(entity_id="a1", actor_type_id="human")
        assert a.broadcast("hi") == 0

    def test_set_goal(self):
        a = Actor(entity_id="a1", actor_type_id="human")
        a.set_goal("wealth")
        assert a._current_goal == "wealth"
        a.set_goal(None)
        assert a._current_goal is None


class TestActorWithBoundOS:
    """Once bound, Actor's cognition proxies genuinely delegate to
    self.os rather than short-circuiting."""

    def test_tick_delegates_to_os(self):
        import asyncio

        from cognitiveos import CognitiveOS

        os_ = CognitiveOS()
        a = Actor(entity_id="a1", actor_type_id="human")
        os_.set_actor(a)

        class Engine:
            async def tick(self, actor):
                return {"delegated": True}

        os_.set_engine(Engine())
        result = asyncio.run(a.tick())
        assert result == {"success": True, "result": {"delegated": True}}

    def test_observe_delegates_to_os_world(self):
        from cognitiveos import CognitiveOS

        world = object()
        os_ = CognitiveOS(world=world)
        a = Actor(entity_id="a1", actor_type_id="human")
        os_.set_actor(a)
        assert a.observe() is world

    def test_send_message_delegates_to_os(self):
        from cognitiveos import CognitiveOS

        os_ = CognitiveOS()
        a = Actor(entity_id="a1", actor_type_id="human")
        os_.set_actor(a)
        assert a.send_message("bob", "hi") is True

    def test_broadcast_delegates_to_os(self):
        from cognitiveos import CognitiveOS

        os_ = CognitiveOS()
        a = Actor(entity_id="a1", actor_type_id="human")
        os_.set_actor(a)
        assert a.broadcast("hi") == 0  # no society_runtime set -> 0 sent, but delegated


class TestActorEqualityAndHash:
    def test_equal_by_entity_id(self):
        a1 = Actor(entity_id="alice", actor_type_id="human")
        a2 = Actor(entity_id="alice", actor_type_id="ai_agent")  # different type, same id
        assert a1 == a2
        assert hash(a1) == hash(a2)

    def test_not_equal_different_entity_id(self):
        a1 = Actor(entity_id="alice", actor_type_id="human")
        a2 = Actor(entity_id="bob", actor_type_id="human")
        assert a1 != a2

    def test_not_equal_to_non_actor(self):
        a1 = Actor(entity_id="alice", actor_type_id="human")
        assert (a1 == "alice") is False

    def test_usable_as_set_member(self):
        a1 = Actor(entity_id="alice", actor_type_id="human")
        a2 = Actor(entity_id="alice", actor_type_id="human")
        assert len({a1, a2}) == 1


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
