"""Actor-Centric Affiliation Architecture.

TrustEngine is the single trust abstraction used by both
SocietyRuntime (actor-to-actor) and AffiliationManager (affiliation trust).

Each affiliation type is a semantic concept with metadata:
    - category (personal, organizational, etc.)
    - cardinality (how many-to-many)
    - bidirectionality
    - default permissions
    - trust model (growth/decay rates)
    - lifecycle rules (creation, expiration, dissolution)
"""
from .affiliation import Affiliation
from .education import EducationAffiliation
from .employment import EmploymentAffiliation
from .family import FamilyAffiliation
from .manager import AffiliationManager
from .trust import TrustEngine
from .types import (
    ALL_TYPES,
    CATEGORIES,
    AffiliationType,
    Cardinality,
    LifecycleRules,
    TrustModel,
    get_type,
    types_in_category,
)

__all__ = [
    "ALL_TYPES",
    "CATEGORIES",
    "Affiliation",
    "AffiliationManager",
    "AffiliationType",
    "Cardinality",
    "EducationAffiliation",
    "EmploymentAffiliation",
    "FamilyAffiliation",
    "LifecycleRules",
    "TrustEngine",
    "TrustModel",
    "get_type",
    "types_in_category",
]
