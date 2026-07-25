"""Tests for CognitiveOS affiliations and trust."""
import pytest
from cognitiveos.affiliations.trust import TrustEngine
from cognitiveos.affiliations.affiliation import Affiliation
from cognitiveos.affiliations.family import FamilyAffiliation
from cognitiveos.affiliations.employment import EmploymentAffiliation
from cognitiveos.affiliations.manager import AffiliationManager


class TestTrustEngine:
    def test_default_trust(self):
        te = TrustEngine()
        assert te.get_trust("alice", "bob") == 0.5

    def test_set_trust(self):
        te = TrustEngine()
        te.set_trust("alice", "bob", 0.9)
        assert te.get_trust("alice", "bob") == 0.9

    def test_clamp_trust_bounds(self):
        te = TrustEngine()
        te.set_trust("alice", "bob", 1.5)
        assert te.get_trust("alice", "bob") == 1.0
        te.set_trust("alice", "bob", -0.5)
        assert te.get_trust("alice", "bob") == 0.0

    def test_update_good_recommendation(self):
        te = TrustEngine()
        te.set_trust("alice", "bob", 0.7)
        te.update_from_outcome("alice", "bob", goal_achieved=True, recommendation_valid=True)
        assert te.get_trust("alice", "bob") > 0.7

    def test_decay_faster_than_growth(self):
        te = TrustEngine()
        te.set_trust("alice", "bob", 0.5)
        te.update_from_outcome("alice", "bob", goal_achieved=True)
        after_good = te.get_trust("alice", "bob")
        te.set_trust("alice", "bob", 0.5)
        te.update_from_outcome("alice", "bob", goal_achieved=False)
        after_bad = te.get_trust("alice", "bob")
        assert (0.5 - after_bad) > (after_good - 0.5)


class TestAffiliationManager:
    def test_add_and_get(self):
        mgr = AffiliationManager()
        a = Affiliation(
            affiliation_id="a1", affiliation_type="community",
            target_id="c1", target_name="Tech Club",
            trust_level=0.6, metadata={},
        )
        mgr.add(a)
        assert mgr.get("a1") == a
        assert mgr.count() == 1

    def test_remove(self):
        mgr = AffiliationManager()
        mgr.add(Affiliation(
            affiliation_id="a1", affiliation_type="community",
            target_id="c1", target_name="Club",
            trust_level=0.6, metadata={},
        ))
        assert mgr.remove("a1") is True
        assert mgr.get("a1") is None

    def test_by_category(self):
        mgr = AffiliationManager()
        mgr.add(FamilyAffiliation(
            affiliation_id="f1", affiliation_type="family",
            target_id="bob", target_name="Bob",
            trust_level=1.0, metadata={}, branch="creation", relation="spouse",
        ))
        mgr.add(EmploymentAffiliation(
            affiliation_id="e1", affiliation_type="employment",
            target_id="openai", target_name="OpenAI",
            trust_level=0.8, metadata={}, role="Engineer",
            start_date="", end_date="", status="active",
        ))
        personal = mgr.by_category("personal")
        assert len(personal) == 1
        assert personal[0].target_name == "Bob"

    def test_trusted_participants(self):
        mgr = AffiliationManager()
        mgr.add(Affiliation(
            affiliation_id="a1", affiliation_type="community",
            target_id="t1", target_name="Trusted",
            trust_level=0.8, metadata={},
        ))
        mgr.add(Affiliation(
            affiliation_id="a2", affiliation_type="community",
            target_id="t2", target_name="Untrusted",
            trust_level=0.3, metadata={},
        ))
        trusted = mgr.trusted_participants(min_trust=0.5)
        assert len(trusted) == 1
        assert trusted[0].target_name == "Trusted"
