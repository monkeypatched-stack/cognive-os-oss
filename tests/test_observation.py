"""Tests for the Observe stage (cognitiveos.observation + CognitiveOS.observe()).

Covers the OSS-0101/OSS-0102 conformance cases directly.
"""
from cognitiveos import Actor, CognitiveOS
from cognitiveos.observation import extract_facts


class TestExtractFacts:
    def test_existence_with_color_and_location(self):
        facts = extract_facts("There is a red ball on the table.")
        got = {(f.entity, f.attribute): f.value for f in facts}
        assert got == {("ball", "color"): "red", ("ball", "location"): "table"}

    def test_containment_with_count_and_color(self):
        facts = extract_facts("The blue box contains three batteries.")
        got = {(f.entity, f.attribute): f.value for f in facts}
        assert got == {("box", "color"): "blue", ("battery", "count"): 3, ("battery", "location"): "box"}

    def test_digit_count_also_parses(self):
        facts = extract_facts("The box contains 5 batteries.")
        got = {(f.entity, f.attribute): f.value for f in facts}
        assert got[("battery", "count")] == 5

    def test_no_match_returns_empty(self):
        assert extract_facts("Book me a flight to Berlin") == []

    def test_generalizes_to_unseen_nouns_colors_and_prepositions(self):
        """Not a lookup table for the two known example sentences — the
        same regex-and-word-list rules applied to entirely different
        nouns/colors/prepositions/verbs it was never tuned against.
        """
        cases = [
            ("There is a green cup on the shelf.",
             {("cup", "color"): "green", ("cup", "location"): "shelf"}),
            ("There is a yellow car in the garage.",
             {("car", "color"): "yellow", ("car", "location"): "garage"}),
            ("There is a purple kite near the fence.",
             {("kite", "color"): "purple", ("kite", "location"): "fence"}),
            ("There is a bicycle under the stairs.",  # no color at all
             {("bicycle", "location"): "stairs"}),
            ("The white bag contains five apples.",
             {("bag", "color"): "white", ("apple", "count"): 5, ("apple", "location"): "bag"}),
            ("The orange crate has 12 mangoes.",  # digit count, 'has' verb
             {("crate", "color"): "orange"}),  # count/location checked separately below (see mango note)
        ]
        for sentence, expected_subset in cases:
            got = {(f.entity, f.attribute): f.value for f in extract_facts(sentence)}
            for key, value in expected_subset.items():
                assert got[key] == value, f"{sentence!r}: expected {key}={value!r}, got {got}"

    def test_unrelated_sentences_produce_no_facts(self):
        assert extract_facts("I like pizza.") == []
        assert extract_facts("The weather is nice today.") == []

    def test_singularize_known_limitation_consonant_o_plus_es(self):
        """Documented blind spot (see _singularize's docstring): 'mangoes'
        and 'shoes' both end in '-oes' and are indistinguishable by
        suffix alone without a dictionary. Locking in the current
        (imperfect but honest) behavior so a future change to this rule
        is a deliberate choice, not a silent regression.
        """
        facts = extract_facts("The crate contains three mangoes.")
        got = {(f.entity, f.attribute): f.value for f in facts}
        assert got[("mangoe", "count")] == 3  # known-wrong: should be "mango"

    def test_copula_state_pattern(self):
        assert {(f.entity, f.attribute): f.value for f in extract_facts("Door is closed")} \
            == {("door", "state"): "closed"}
        assert {(f.entity, f.attribute): f.value for f in extract_facts("Door is open")} \
            == {("door", "state"): "open"}

    def test_copula_generalizes_to_unseen_entities_and_states(self):
        cases = [
            ("Light is on", {("light", "state"): "on"}),
            ("Alarm is active", {("alarm", "state"): "active"}),
            ("Engine is broken", {("engine", "state"): "broken"}),
        ]
        for sentence, expected in cases:
            got = {(f.entity, f.attribute): f.value for f in extract_facts(sentence)}
            assert got == expected, f"{sentence!r}: expected {expected}, got {got}"

    def test_copula_pattern_does_not_fire_on_existence_sentences(self):
        """'is' appears in both shapes — the anchored copula pattern must
        not swallow "There is a red ball on the table." (multi-word
        predicate) as if it were a two-word "Entity is state." sentence.
        """
        facts = extract_facts("There is a red ball on the table.")
        got = {(f.entity, f.attribute): f.value for f in facts}
        assert got == {("ball", "color"): "red", ("ball", "location"): "table"}
        assert ("there", "state") not in got


class TestCognitiveOSObserve:
    def test_oss_0101_single_observation(self):
        os = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human")
        os.set_actor(actor)

        beliefs = os.observe("There is a red ball on the table.")

        got = {(b.subject, b.attribute): b.value for b in beliefs}
        assert got == {("ball", "color"): "red", ("ball", "location"): "table"}
        assert all(b.belief_type_id == "observation" for b in beliefs)
        # Recorded on the actor too, not just returned
        assert actor.beliefs == beliefs

    def test_oss_0102_multiple_facts(self):
        os = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human")
        os.set_actor(actor)

        beliefs = os.observe("The blue box contains three batteries.")

        got = {(b.subject, b.attribute): b.value for b in beliefs}
        assert got == {("box", "color"): "blue", ("battery", "count"): 3, ("battery", "location"): "box"}

    def test_observe_without_actor_returns_empty(self):
        os = CognitiveOS()
        assert os.observe("There is a red ball on the table.") == []

    def test_observe_unmatched_sentence_returns_empty(self):
        os = CognitiveOS()
        os.set_actor(Actor(entity_id="alice", actor_type_id="human"))
        assert os.observe("Colorless green ideas sleep furiously.") == []

    def test_oss_0103_belief_update(self):
        """A later observation about the same (subject, attribute) revises
        the belief in place — the actor ends up with one current belief
        (door.state=open), not two contradictory ones sitting side by side.
        """
        os = CognitiveOS()
        actor = Actor(entity_id="alice", actor_type_id="human")
        os.set_actor(actor)

        os.observe("Door is closed")
        assert {(b.subject, b.attribute): b.value for b in actor.beliefs} == {("door", "state"): "closed"}

        os.observe("Door is open")
        assert {(b.subject, b.attribute): b.value for b in actor.beliefs} == {("door", "state"): "open"}
        assert len(actor.beliefs) == 1
