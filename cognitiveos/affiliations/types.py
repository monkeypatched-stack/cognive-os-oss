"""AffiliationType — semantic concept with metadata for each relationship type.

Instead of fixed enum values, each affiliation type is a rich object describing:
    - category (personal, organizational, etc.)
    - cardinality (how many-to-many)
    - bidirectionality (does the relationship exist in both directions?)
    - default permissions (what this relationship grants)
    - trust model (how trust propagates)
    - lifecycle (creation, maintenance, dissolution rules)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class Cardinality(str, Enum):
    ONE_TO_ONE = "one_to_one"       # marriage, guardianship
    ONE_TO_MANY = "one_to_many"     # employer→employees
    MANY_TO_ONE = "many_to_one"     # employee→employer
    MANY_TO_MANY = "many_to_many"   # friends, community members


@dataclass(frozen=True)
class TrustModel:
    """How trust behaves for this relationship type."""
    initial_trust: float = 0.5
    growth_rate: float = 0.05
    decay_rate: float = -0.08
    decay_on_breach: float = -0.15
    asymmetric: bool = True  # decay faster than growth


@dataclass(frozen=True)
class LifecycleRules:
    """How this relationship is created, maintained, and dissolved."""
    requires_mutual_consent: bool = False
    auto_expire: bool = False
    duration_limit_days: int | None = None  # None = indefinite
    dissolution_requires_action: bool = True


@dataclass(frozen=True)
class AffiliationType:
    """Semantic concept for a relationship type.

    Each type carries rich metadata that the runtime uses for:
    - relationship semantics (cardinality, bidirectionality)
    - trust propagation (growth/decay rates)
    - lifecycle management (creation, expiration, dissolution)
    - permission defaults (what this relationship grants)
    - governance rules (who can create/modify/dissolve)
    """
    id: str
    category: str
    cardinality: Cardinality = Cardinality.MANY_TO_ONE
    bidirectional: bool = True
    default_permissions: tuple[str, ...] = ()
    trust_model: TrustModel = field(default_factory=TrustModel)
    lifecycle: LifecycleRules = field(default_factory=LifecycleRules)
    description: str = ""


# ════════════════════════════════════════════════════════════════
# Personal
# ════════════════════════════════════════════════════════════════

FAMILY = AffiliationType(
    id="family", category="personal",
    cardinality=Cardinality.ONE_TO_MANY,
    bidirectional=True,
    default_permissions=("emotional_support", "financial_dependents", "caregiving"),
    trust_model=TrustModel(initial_trust=0.9, growth_rate=0.02, decay_rate=-0.10,
                           decay_on_breach=-0.20),
    lifecycle=LifecycleRules(requires_mutual_consent=False),
    description="Origin (parents, siblings) or Creation (children) family bonds",
)

FRIENDSHIP = AffiliationType(
    id="friendship", category="personal",
    cardinality=Cardinality.MANY_TO_MANY,
    bidirectional=True,
    default_permissions=("social", "emotional_support", "recommendation"),
    trust_model=TrustModel(initial_trust=0.6, growth_rate=0.05, decay_rate=-0.08),
    lifecycle=LifecycleRules(requires_mutual_consent=True),
    description="Social bond between individuals",
)

MARRIAGE = AffiliationType(
    id="marriage", category="personal",
    cardinality=Cardinality.ONE_TO_ONE,
    bidirectional=True,
    default_permissions=("financial", "legal", "medical", "emotional_support"),
    trust_model=TrustModel(initial_trust=1.0, growth_rate=0.02, decay_rate=-0.15,
                           decay_on_breach=-0.30),
    lifecycle=LifecycleRules(requires_mutual_consent=True, dissolution_requires_action=True),
    description="Legal and emotional partnership",
)

GUARDIANSHIP = AffiliationType(
    id="guardianship", category="personal",
    cardinality=Cardinality.ONE_TO_ONE,
    bidirectional=False,
    default_permissions=("caregiving", "legal", "financial_dependents", "education"),
    trust_model=TrustModel(initial_trust=0.95, growth_rate=0.02, decay_rate=-0.10,
                           decay_on_breach=-0.25),
    lifecycle=LifecycleRules(requires_mutual_consent=False, duration_limit_days=6570),
    description="Legal responsibility for a minor or incapacitated person",
)

# ════════════════════════════════════════════════════════════════
# Organizational
# ════════════════════════════════════════════════════════════════

EMPLOYMENT = AffiliationType(
    id="employment", category="organizational",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=True,
    default_permissions=("career_planning", "calendar", "work_scheduling", "compensation"),
    trust_model=TrustModel(initial_trust=0.7, growth_rate=0.03, decay_rate=-0.08,
                           decay_on_breach=-0.15),
    lifecycle=LifecycleRules(duration_limit_days=None),
    description="Formal employment relationship",
)

CONTRACTOR = AffiliationType(
    id="contractor", category="organizational",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=True,
    default_permissions=("project_access", "compensation", "work_scheduling"),
    trust_model=TrustModel(initial_trust=0.5, growth_rate=0.05, decay_rate=-0.10),
    lifecycle=LifecycleRules(auto_expire=True, duration_limit_days=365),
    description="Contract-based work relationship",
)

VOLUNTEER = AffiliationType(
    id="volunteer", category="organizational",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=True,
    default_permissions=("project_access", "community"),
    trust_model=TrustModel(initial_trust=0.6, growth_rate=0.05, decay_rate=-0.05),
    lifecycle=LifecycleRules(requires_mutual_consent=True),
    description="Voluntary service to an organization",
)

BOARD_MEMBER = AffiliationType(
    id="board_member", category="organizational",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=True,
    default_permissions=("governance", "strategy", "financial_oversight"),
    trust_model=TrustModel(initial_trust=0.8, growth_rate=0.03, decay_rate=-0.10,
                           decay_on_breach=-0.20),
    lifecycle=LifecycleRules(duration_limit_days=1825),
    description="Board of directors membership",
)

SHAREHOLDER = AffiliationType(
    id="shareholder", category="organizational",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=False,
    default_permissions=("financial_oversight", "voting"),
    trust_model=TrustModel(initial_trust=0.6, growth_rate=0.02, decay_rate=-0.05),
    description="Ownership stake in an organization",
)

# ════════════════════════════════════════════════════════════════
# Commercial
# ════════════════════════════════════════════════════════════════

CUSTOMER = AffiliationType(
    id="customer", category="commercial",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=True,
    default_permissions=("purchasing", "support"),
    trust_model=TrustModel(initial_trust=0.5, growth_rate=0.05, decay_rate=-0.10),
    description="Purchaser of goods or services",
)

SUPPLIER = AffiliationType(
    id="supplier", category="commercial",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=True,
    default_permissions=("procurement", "quality", "delivery"),
    trust_model=TrustModel(initial_trust=0.6, growth_rate=0.03, decay_rate=-0.12,
                           decay_on_breach=-0.18),
    description="Provider of goods or services",
)

PARTNER = AffiliationType(
    id="partner", category="commercial",
    cardinality=Cardinality.MANY_TO_MANY,
    bidirectional=True,
    default_permissions=("strategic", "joint_venture", "cross_promotion"),
    trust_model=TrustModel(initial_trust=0.7, growth_rate=0.05, decay_rate=-0.10),
    description="Strategic business partnership",
)

VENDOR = AffiliationType(
    id="vendor", category="commercial",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=True,
    default_permissions=("procurement", "delivery"),
    trust_model=TrustModel(initial_trust=0.5, growth_rate=0.03, decay_rate=-0.10),
    description="Regular supplier of specific goods or services",
)

FRANCHISE = AffiliationType(
    id="franchise", category="commercial",
    cardinality=Cardinality.ONE_TO_MANY,
    bidirectional=True,
    default_permissions=("brand_use", "operational_guidelines", "training"),
    trust_model=TrustModel(initial_trust=0.7, growth_rate=0.03, decay_rate=-0.08),
    lifecycle=LifecycleRules(duration_limit_days=1825),
    description="Franchise relationship between franchisor and franchisee",
)

# ════════════════════════════════════════════════════════════════
# Government
# ════════════════════════════════════════════════════════════════

CITIZEN = AffiliationType(
    id="citizen", category="government",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=True,
    default_permissions=("legal", "protection", "voting"),
    trust_model=TrustModel(initial_trust=0.5, growth_rate=0.02, decay_rate=-0.05),
    description="Legal membership in a nation-state",
)

RESIDENT = AffiliationType(
    id="resident", category="government",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=True,
    default_permissions=("local_services", "legal"),
    trust_model=TrustModel(initial_trust=0.5, growth_rate=0.02, decay_rate=-0.03),
    description="Residence in a jurisdiction",
)

TAXPAYER = AffiliationType(
    id="taxpayer", category="government",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=True,
    default_permissions=("fiscal", "representation"),
    trust_model=TrustModel(initial_trust=0.4, growth_rate=0.02, decay_rate=-0.05),
    description="Tax obligation to a government entity",
)

VOTER = AffiliationType(
    id="voter", category="government",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=True,
    default_permissions=("electoral", "participation"),
    trust_model=TrustModel(initial_trust=0.5, growth_rate=0.03, decay_rate=-0.05),
    description="Voting rights in a jurisdiction",
)

PUBLIC_OFFICIAL = AffiliationType(
    id="public_official", category="government",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=True,
    default_permissions=("governance", "policy", "public_service"),
    trust_model=TrustModel(initial_trust=0.5, growth_rate=0.03, decay_rate=-0.10,
                           decay_on_breach=-0.20),
    description="Elected or appointed government official",
)

# ════════════════════════════════════════════════════════════════
# Education
# ════════════════════════════════════════════════════════════════

STUDENT = AffiliationType(
    id="student", category="education",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=True,
    default_permissions=("learning", "facilities", "library"),
    trust_model=TrustModel(initial_trust=0.5, growth_rate=0.05, decay_rate=-0.05),
    lifecycle=LifecycleRules(duration_limit_days=1825),
    description="Enrolled learner at an institution",
)

TEACHER = AffiliationType(
    id="teacher", category="education",
    cardinality=Cardinality.ONE_TO_MANY,
    bidirectional=True,
    default_permissions=("teaching", "mentoring", "grading"),
    trust_model=TrustModel(initial_trust=0.7, growth_rate=0.03, decay_rate=-0.08),
    description="Educator at an institution",
)

ALUMNI = AffiliationType(
    id="alumni", category="education",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=True,
    default_permissions=("networking", "facilities"),
    trust_model=TrustModel(initial_trust=0.6, growth_rate=0.02, decay_rate=-0.03),
    description="Graduate of an institution",
)

RESEARCHER = AffiliationType(
    id="researcher", category="education",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=True,
    default_permissions=("research", "publications", "funding"),
    trust_model=TrustModel(initial_trust=0.7, growth_rate=0.03, decay_rate=-0.05),
    description="Research affiliate at an institution",
)

# ════════════════════════════════════════════════════════════════
# Healthcare
# ════════════════════════════════════════════════════════════════

PATIENT = AffiliationType(
    id="patient", category="healthcare",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=True,
    default_permissions=("medical", "emergency"),
    trust_model=TrustModel(initial_trust=0.7, growth_rate=0.02, decay_rate=-0.15,
                           decay_on_breach=-0.25),
    description="Person receiving healthcare services",
)

DOCTOR = AffiliationType(
    id="doctor", category="healthcare",
    cardinality=Cardinality.ONE_TO_MANY,
    bidirectional=True,
    default_permissions=("medical", "prescriptions", "diagnosis"),
    trust_model=TrustModel(initial_trust=0.8, growth_rate=0.02, decay_rate=-0.10,
                           decay_on_breach=-0.20),
    description="Healthcare provider",
)

CAREGIVER = AffiliationType(
    id="caregiver", category="healthcare",
    cardinality=Cardinality.ONE_TO_ONE,
    bidirectional=False,
    default_permissions=("caregiving", "medical_decisions", "emergency"),
    trust_model=TrustModel(initial_trust=0.9, growth_rate=0.03, decay_rate=-0.10,
                           decay_on_breach=-0.20),
    description="Person providing care to another",
)

INSURED = AffiliationType(
    id="insured", category="healthcare",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=True,
    default_permissions=("coverage", "claims"),
    trust_model=TrustModel(initial_trust=0.5, growth_rate=0.02, decay_rate=-0.08),
    description="Person covered by health insurance",
)

# ════════════════════════════════════════════════════════════════
# Digital
# ════════════════════════════════════════════════════════════════

AI_AGENT = AffiliationType(
    id="ai_agent", category="digital",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=True,
    default_permissions=("task_execution", "data_access", "messaging"),
    trust_model=TrustModel(initial_trust=0.5, growth_rate=0.05, decay_rate=-0.10),
    description="Autonomous AI agent",
)

ROBOT = AffiliationType(
    id="robot", category="digital",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=True,
    default_permissions=("physical_tasks", "sensor_data"),
    trust_model=TrustModel(initial_trust=0.5, growth_rate=0.03, decay_rate=-0.08),
    description="Physical robotic agent",
)

DEVICE = AffiliationType(
    id="device", category="digital",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=False,
    default_permissions=("telemetry", "control"),
    trust_model=TrustModel(initial_trust=0.4, growth_rate=0.02, decay_rate=-0.05),
    description="IoT or connected device",
)

SERVICE_ACCOUNT = AffiliationType(
    id="service_account", category="digital",
    cardinality=Cardinality.MANY_TO_ONE,
    bidirectional=False,
    default_permissions=("api_access", "data_read", "data_write"),
    trust_model=TrustModel(initial_trust=0.3, growth_rate=0.05, decay_rate=-0.15),
    description="Programmatic service account",
)


# ════════════════════════════════════════════════════════════════
# Registry — all types indexed by ID
# ════════════════════════════════════════════════════════════════

ALL_TYPES: dict[str, AffiliationType] = {
    t.id: t for t in [
        FAMILY, FRIENDSHIP, MARRIAGE, GUARDIANSHIP,
        EMPLOYMENT, CONTRACTOR, VOLUNTEER, BOARD_MEMBER, SHAREHOLDER,
        CUSTOMER, SUPPLIER, PARTNER, VENDOR, FRANCHISE,
        CITIZEN, RESIDENT, TAXPAYER, VOTER, PUBLIC_OFFICIAL,
        STUDENT, TEACHER, ALUMNI, RESEARCHER,
        PATIENT, DOCTOR, CAREGIVER, INSURED,
        AI_AGENT, ROBOT, DEVICE, SERVICE_ACCOUNT,
    ]
}

CATEGORIES: dict[str, list[str]] = {}
for _t in ALL_TYPES.values():
    CATEGORIES.setdefault(_t.category, []).append(_t.id)


def get_type(type_id: str) -> AffiliationType | None:
    """Look up an affiliation type by ID."""
    return ALL_TYPES.get(type_id)


def types_in_category(category: str) -> list[str]:
    """Get all type IDs for a category."""
    return CATEGORIES.get(category, [])
