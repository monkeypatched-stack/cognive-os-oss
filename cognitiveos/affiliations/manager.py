from __future__ import annotations

import logging
from typing import Any, ClassVar

from .affiliation import Affiliation
from .trust import TrustEngine

logger = logging.getLogger("agentos.affiliations")


class AffiliationManager:
    """Manages an actor's affiliations and trust relationships.

    Three explicit responsibilities:

    Relationship Management
        add(), update(), remove(), get(), count()

    Trust Interface
        get_trust(), update_trust_from_outcome(), trusted_participants()

    Coordination
        discover_participants() / participants(), by_permission(),
        has_permission(), active()

    set_trust() is intentionally restricted:
        Used only for initial affiliation creation, migration,
        testing, and administrative override. Trust should evolve
        through update_trust_from_outcome(), not manual assignment.

    Discovery evolution:
        V1: Goal → keyword matching (current)
        V2: Goal → Planner Intent IR
        V3: Goal → Semantic World Model
        V4: Goal → Trust Graph traversal
        The public API never changes. Only the implementation evolves.
    """

    def __init__(self, trust_engine: TrustEngine | None = None):
        self._affiliations: dict[str, Affiliation] = {}
        self.trust_engine = trust_engine or TrustEngine()

    # ──────────────────────────────────────────────────────────
    # Relationship Management
    # ──────────────────────────────────────────────────────────

    def add(self, affiliation: Affiliation) -> None:
        """Add an affiliation. Syncs initial trust to TrustEngine."""
        self._affiliations[affiliation.affiliation_id] = affiliation
        self.trust_engine.set_trust(
            "self", affiliation.target_id, affiliation.trust_level,
        )
        logger.debug("Added %s -> %s (%s, trust=%.2f)",
                     "self", affiliation.target_name,
                     affiliation.affiliation_type, affiliation.trust_level)

    def update(self, affiliation_id: str, **kwargs: Any) -> Affiliation | None:
        """Update fields on an existing affiliation. Returns updated affiliation."""
        old = self._affiliations.get(affiliation_id)
        if old is None:
            return None
        from dataclasses import replace
        updated = replace(old, **kwargs)
        self._affiliations[affiliation_id] = updated
        if "trust_level" in kwargs:
            self.trust_engine.set_trust("self", updated.target_id, updated.trust_level)
        return updated

    def remove(self, affiliation_id: str) -> bool:
        """Remove an affiliation by ID."""
        return self._affiliations.pop(affiliation_id, None) is not None

    def get(self, affiliation_id: str) -> Affiliation | None:
        """Get an affiliation by ID."""
        return self._affiliations.get(affiliation_id)

    def count(self) -> int:
        """Number of affiliations."""
        return len(self._affiliations)

    def all(self) -> list[Affiliation]:
        """All affiliations."""
        return list(self._affiliations.values())

    def by_type(self, affiliation_type: str) -> list[Affiliation]:
        """Filter by affiliation type (family, employment, education, etc.)."""
        return [a for a in self._affiliations.values()
                if a.affiliation_type == affiliation_type]

    def by_target(self, target_id: str) -> list[Affiliation]:
        """Filter by target entity ID."""
        return [a for a in self._affiliations.values()
                if a.target_id == target_id]

    def by_category(self, category: str) -> list[Affiliation]:
        """Filter by category (personal, organizational, commercial, etc.)."""
        return [a for a in self._affiliations.values()
                if a.category == category]

    def by_subtype(self, subtype: str) -> list[Affiliation]:
        """Filter by type ID (family, employment, student, ai_agent, etc.)."""
        return [a for a in self._affiliations.values()
                if a.affiliation_type == subtype]

    # ──────────────────────────────────────────────────────────
    # Trust Interface
    # ──────────────────────────────────────────────────────────

    def get_trust(self, target_id: str) -> float:
        """Current trust level for a target entity."""
        return self.trust_engine.get_trust("self", target_id)

    def set_trust(self, target_id: str, level: float) -> None:
        """Set trust directly.

        RESTRICTED — use only for:
            - Initial affiliation creation
            - Migration
            - Testing
            - Administrative override

        Trust should evolve through update_trust_from_outcome(),
        not manual assignment.
        """
        self.trust_engine.set_trust("self", target_id, level)

    def update_trust_from_outcome(self, target_id: str, goal_achieved: bool,
                                  recommendation_valid: bool | None = None,
                                  obligation_met: bool | None = None) -> None:
        """Update trust based on a goal outcome. Primary trust evolution mechanism."""
        self.trust_engine.update_from_outcome(
            "self", target_id,
            goal_achieved=goal_achieved,
            recommendation_valid=recommendation_valid,
            obligation_met=obligation_met,
        )

    def trusted_participants(self, min_trust: float = 0.5) -> list[Affiliation]:
        """Affiliations with trust at or above min_trust."""
        return [
            a for a in self._affiliations.values()
            if self.trust_engine.get_trust("self", a.target_id) >= min_trust
        ]

    # ──────────────────────────────────────────────────────────
    # Coordination
    # ──────────────────────────────────────────────────────────

    def by_permission(self, permission: str) -> list[Affiliation]:
        """Affiliations that grant a specific permission."""
        return [a for a in self._affiliations.values()
                if permission in a.permissions]

    def has_permission(self, target_id: str, permission: str) -> bool:
        """Check if any affiliation with this target grants the permission."""
        return any(
            permission in a.permissions
            for a in self._affiliations.values()
            if a.target_id == target_id
        )

    def active(self) -> list[Affiliation]:
        """Affiliations that are not expired."""
        import datetime
        # UTC, not a naive local date — valid_until comparisons shouldn't
        # depend on the server's local timezone.
        now = datetime.datetime.now(tz=datetime.UTC).date().isoformat()
        return [a for a in self._affiliations.values()
                if not a.valid_until or a.valid_until >= now]

    # ──────────────────────────────────────────────────────────
    # Discovery
    # ──────────────────────────────────────────────────────────

    _GOAL_AFFILIATION_MAP: ClassVar[dict[str, list[str]]] = {
        # Organizational
        "job":       ["employment", "contractor"],
        "work":      ["employment", "contractor"],
        "hire":      ["employment"],
        "career":    ["employment"],
        "salary":    ["employment"],
        "contract":  ["contractor"],
        "freelance": ["contractor"],
        "board":     ["board_member"],
        "invest":    ["shareholder"],
        "stock":     ["shareholder"],
        # Education
        "school":    ["student", "teacher"],
        "university":["student", "teacher", "researcher"],
        "degree":    ["student"],
        "course":    ["student"],
        "teach":     ["teacher"],
        "research":  ["researcher"],
        "alumni":    ["alumni"],
        # Personal
        "family":    ["family"],
        "spouse":    ["marriage", "family"],
        "child":     ["family", "guardianship"],
        "parent":    ["family", "guardianship"],
        "wedding":   ["marriage"],
        "friend":    ["friendship"],
        # Healthcare
        "medical":   ["patient", "doctor"],
        "hospital":  ["patient", "doctor", "caregiver"],
        "doctor":    ["doctor"],
        "patient":   ["patient"],
        "insurance": ["insured", "patient"],
        "care":      ["caregiver"],
        # Commercial
        "buy":       ["customer"],
        "sell":      ["supplier", "vendor"],
        "supply":    ["supplier"],
        "partner":   ["partner"],
        "franchise": ["franchise"],
        "vendor":    ["vendor"],
        # Government
        "government":["citizen", "resident", "taxpayer"],
        "vote":      ["voter"],
        "tax":       ["taxpayer"],
        "official":  ["public_official"],
        "citizen":   ["citizen"],
        "resident":  ["resident"],
        # Digital
        "agent":     ["ai_agent"],
        "robot":     ["robot"],
        "device":    ["device"],
        "api":       ["service_account"],
        "service":   ["service_account"],
    }

    def discover_participants(self, goal: str) -> list[Affiliation]:
        """Discover relevant participants for a goal.

        V1 (current): Goal → keyword matching → affiliation types
        V2: Goal → Planner Intent IR
        V3: Goal → Semantic World Model
        V4: Goal → Trust Graph traversal

        The public API never changes. Only the implementation evolves.

        Returns affiliations sorted by trust (highest first),
        filtered by minimum trust threshold (0.3).
        """
        goal_lower = goal.lower()
        matched_types: set[str] = set()
        for keyword, types in self._GOAL_AFFILIATION_MAP.items():
            if keyword in goal_lower:
                matched_types.update(types)

        if matched_types:
            candidates = [
                a for a in self._affiliations.values()
                if a.affiliation_type in matched_types
                and self.trust_engine.get_trust("self", a.target_id) >= 0.3
            ]
        else:
            candidates = self.trusted_participants(min_trust=0.3)

        return sorted(
            candidates,
            key=lambda a: self.trust_engine.get_trust("self", a.target_id),
            reverse=True,
        )

    def participants(self, goal: str) -> list[Affiliation]:
        """Convenience alias for discover_participants().

        Usage:
            participants = actor.affiliations.participants("accept_job")
        """
        return self.discover_participants(goal)

    # ──────────────────────────────────────────────────────────
    # Serialization
    # ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dict. Enables persistence, cloud sync,
        REST, GraphQL, and checkpointing."""
        from .education import EducationAffiliation
        from .employment import EmploymentAffiliation
        from .family import FamilyAffiliation

        affiliations_data = []
        for a in self._affiliations.values():
            d: dict[str, Any] = {
                "affiliation_id": a.affiliation_id,
                "affiliation_type": a.affiliation_type,
                "target_id": a.target_id,
                "target_name": a.target_name,
                "trust_level": a.trust_level,
                "permissions": list(a.permissions),
                "policies": list(a.policies),
                "priority": a.priority,
                "valid_from": a.valid_from,
                "valid_until": a.valid_until,
                "metadata": a.metadata,
            }
            if isinstance(a, FamilyAffiliation):
                d["branch"] = a.branch
                d["relation"] = a.relation
            elif isinstance(a, EmploymentAffiliation):
                d["role"] = a.role
                d["start_date"] = a.start_date
                d["end_date"] = a.end_date
                d["status"] = a.status
            elif isinstance(a, EducationAffiliation):
                d["institution"] = a.institution
                d["program"] = a.program
                d["degree"] = a.degree
                d["status"] = a.status
            affiliations_data.append(d)

        return {
            "affiliations": affiliations_data,
            "trust": self.trust_engine.all_trust("self"),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any],
                  trust_engine: TrustEngine | None = None) -> AffiliationManager:
        """Deserialize from dict, preserving subclass types."""
        from .education import EducationAffiliation
        from .employment import EmploymentAffiliation
        from .family import FamilyAffiliation

        _SUBCLASS_MAP: dict[str, type] = {
            "family": FamilyAffiliation,
            "employment": EmploymentAffiliation,
            "education": EducationAffiliation,
        }

        mgr = cls(trust_engine=trust_engine)
        for ad in data.get("affiliations", []):
            aff_type = ad.get("affiliation_type", "")
            subclass = _SUBCLASS_MAP.get(aff_type, Affiliation)

            base_fields = {
                "affiliation_id": ad["affiliation_id"],
                "affiliation_type": aff_type,
                "target_id": ad["target_id"],
                "target_name": ad["target_name"],
                "trust_level": ad.get("trust_level", 0.5),
                "permissions": tuple(ad.get("permissions", [])),
                "policies": tuple(ad.get("policies", [])),
                "priority": ad.get("priority", 0),
                "valid_from": ad.get("valid_from", ""),
                "valid_until": ad.get("valid_until", ""),
                "metadata": ad.get("metadata", {}),
            }

            if subclass is FamilyAffiliation:
                aff = FamilyAffiliation(
                    **base_fields,
                    branch=ad.get("branch", ad.get("metadata", {}).get("branch", "")),
                    relation=ad.get("relation", ad.get("metadata", {}).get("relation", "")),
                )
            elif subclass is EmploymentAffiliation:
                aff = EmploymentAffiliation(
                    **base_fields,
                    role=ad.get("role", ad.get("metadata", {}).get("role", "")),
                    start_date=ad.get("start_date", ad.get("metadata", {}).get("start_date", "")),
                    end_date=ad.get("end_date", ad.get("metadata", {}).get("end_date", "")),
                    status=ad.get("status", ad.get("metadata", {}).get("status", "active")),
                )
            elif subclass is EducationAffiliation:
                aff = EducationAffiliation(
                    **base_fields,
                    institution=ad.get("institution", ad.get("metadata", {}).get("institution", "")),
                    program=ad.get("program", ad.get("metadata", {}).get("program", "")),
                    degree=ad.get("degree", ad.get("metadata", {}).get("degree", "")),
                    status=ad.get("status", ad.get("metadata", {}).get("status", "enrolled")),
                )
            else:
                aff = Affiliation(**base_fields)

            mgr.add(aff)
        for target, level in data.get("trust", {}).items():
            mgr.trust_engine.set_trust("self", target, level)
        return mgr
