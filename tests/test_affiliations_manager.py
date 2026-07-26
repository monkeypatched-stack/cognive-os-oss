"""Tests for AffiliationManager — coverage beyond tests/test_affiliations.py's
basics: update/serialization, coordination queries, and goal-based discovery.
"""
from cognitiveos.affiliations.affiliation import Affiliation
from cognitiveos.affiliations.education import EducationAffiliation
from cognitiveos.affiliations.employment import EmploymentAffiliation
from cognitiveos.affiliations.family import FamilyAffiliation
from cognitiveos.affiliations.manager import AffiliationManager


def _aff(aff_id, target_id, target_name, trust=0.5, aff_type="community", **kw):
    return Affiliation(
        affiliation_id=aff_id, affiliation_type=aff_type,
        target_id=target_id, target_name=target_name,
        trust_level=trust, metadata={}, **kw,
    )


class TestUpdate:
    def test_update_existing_field(self):
        mgr = AffiliationManager()
        mgr.add(_aff("a1", "t1", "Target", trust=0.5))
        updated = mgr.update("a1", target_name="New Name")
        assert updated.target_name == "New Name"
        assert mgr.get("a1").target_name == "New Name"

    def test_update_trust_level_syncs_trust_engine(self):
        mgr = AffiliationManager()
        mgr.add(_aff("a1", "t1", "Target", trust=0.5))
        mgr.update("a1", trust_level=0.9)
        assert mgr.get_trust("t1") == 0.9

    def test_update_missing_affiliation_returns_none(self):
        mgr = AffiliationManager()
        assert mgr.update("ghost", target_name="x") is None


class TestQueries:
    def test_by_type_and_by_subtype_are_equivalent(self):
        mgr = AffiliationManager()
        mgr.add(_aff("a1", "t1", "T1", aff_type="employment"))
        mgr.add(_aff("a2", "t2", "T2", aff_type="student"))
        assert [a.affiliation_id for a in mgr.by_type("employment")] == ["a1"]
        assert [a.affiliation_id for a in mgr.by_subtype("employment")] == ["a1"]

    def test_by_target(self):
        mgr = AffiliationManager()
        mgr.add(_aff("a1", "bob", "Bob"))
        mgr.add(_aff("a2", "carol", "Carol"))
        assert [a.affiliation_id for a in mgr.by_target("bob")] == ["a1"]

    def test_all_returns_every_affiliation(self):
        mgr = AffiliationManager()
        mgr.add(_aff("a1", "bob", "Bob"))
        mgr.add(_aff("a2", "carol", "Carol"))
        assert {a.affiliation_id for a in mgr.all()} == {"a1", "a2"}

    def test_by_permission_and_has_permission(self):
        mgr = AffiliationManager()
        mgr.add(_aff("a1", "bob", "Bob", permissions=("read", "write")))
        mgr.add(_aff("a2", "carol", "Carol", permissions=("read",)))

        assert [a.affiliation_id for a in mgr.by_permission("write")] == ["a1"]
        assert mgr.has_permission("bob", "write") is True
        assert mgr.has_permission("carol", "write") is False
        assert mgr.has_permission("ghost", "read") is False

    def test_active_excludes_expired(self):
        mgr = AffiliationManager()
        mgr.add(_aff("a1", "bob", "Bob", valid_until="2000-01-01"))
        mgr.add(_aff("a2", "carol", "Carol", valid_until="2999-01-01"))
        mgr.add(_aff("a3", "dave", "Dave", valid_until=""))

        active_ids = {a.affiliation_id for a in mgr.active()}
        assert active_ids == {"a2", "a3"}


class TestTrustDelegation:
    def test_get_set_trust_and_update_from_outcome(self):
        mgr = AffiliationManager()
        mgr.set_trust("bob", 0.6)
        assert mgr.get_trust("bob") == 0.6
        mgr.update_trust_from_outcome("bob", goal_achieved=True)
        assert mgr.get_trust("bob") > 0.6


class TestDiscoverParticipants:
    def test_keyword_match_filters_by_affiliation_type_and_trust(self):
        mgr = AffiliationManager()
        mgr.add(_aff("a1", "acme", "Acme Corp", trust=0.8, aff_type="employment"))
        mgr.add(_aff("a2", "bob", "Bob", trust=0.9, aff_type="family"))
        mgr.add(_aff("a3", "lowtrust_co", "LowTrust Co", trust=0.1, aff_type="employment"))

        results = mgr.discover_participants("I need help with my job search")
        ids = [a.affiliation_id for a in results]
        assert ids == ["a1"]  # employment matched, family excluded, low-trust excluded

    def test_results_sorted_by_trust_descending(self):
        mgr = AffiliationManager()
        mgr.add(_aff("a1", "c1", "Contractor1", trust=0.5, aff_type="contractor"))
        mgr.add(_aff("a2", "c2", "Contractor2", trust=0.9, aff_type="contractor"))

        results = mgr.discover_participants("looking for freelance work")
        assert [a.affiliation_id for a in results] == ["a2", "a1"]

    def test_no_keyword_match_falls_back_to_trusted_participants(self):
        mgr = AffiliationManager()
        mgr.add(_aff("a1", "t1", "T1", trust=0.6))
        mgr.add(_aff("a2", "t2", "T2", trust=0.2))

        results = mgr.discover_participants("xyzzy unrelated gibberish")
        assert [a.affiliation_id for a in results] == ["a1"]

    def test_participants_is_alias_for_discover_participants(self):
        mgr = AffiliationManager()
        mgr.add(_aff("a1", "acme", "Acme", trust=0.8, aff_type="employment"))
        assert mgr.participants("accept job") == mgr.discover_participants("accept job")


class TestSerialization:
    def test_roundtrip_generic_affiliation(self):
        mgr = AffiliationManager()
        mgr.add(_aff("a1", "t1", "Target", trust=0.7, permissions=("read",)))

        data = mgr.to_dict()
        restored = AffiliationManager.from_dict(data)

        assert restored.count() == 1
        restored_aff = restored.get("a1")
        assert restored_aff.target_name == "Target"
        assert restored_aff.permissions == ("read",)
        assert restored.get_trust("t1") == 0.7

    def test_roundtrip_preserves_subclass_types(self):
        mgr = AffiliationManager()
        mgr.add(FamilyAffiliation(
            affiliation_id="f1", affiliation_type="family",
            target_id="bob", target_name="Bob", trust_level=1.0,
            metadata={}, branch="creation", relation="spouse",
        ))
        mgr.add(EmploymentAffiliation(
            affiliation_id="e1", affiliation_type="employment",
            target_id="acme", target_name="Acme", trust_level=0.8,
            metadata={}, role="Engineer", start_date="2020-01-01",
            end_date="", status="active",
        ))
        mgr.add(EducationAffiliation(
            affiliation_id="ed1", affiliation_type="education",
            target_id="mit", target_name="MIT", trust_level=0.9,
            metadata={}, institution="MIT", program="CS",
            degree="BSc", status="enrolled",
        ))

        data = mgr.to_dict()
        restored = AffiliationManager.from_dict(data)

        assert isinstance(restored.get("f1"), FamilyAffiliation)
        assert restored.get("f1").relation == "spouse"
        assert isinstance(restored.get("e1"), EmploymentAffiliation)
        assert restored.get("e1").role == "Engineer"
        assert isinstance(restored.get("ed1"), EducationAffiliation)
        assert restored.get("ed1").institution == "MIT"

    def test_from_dict_with_empty_data_produces_empty_manager(self):
        restored = AffiliationManager.from_dict({})
        assert restored.count() == 0
