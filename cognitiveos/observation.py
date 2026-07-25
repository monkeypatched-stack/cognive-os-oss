"""Observation — turns a declarative sentence into structured facts.

This is the Observe stage's entity/attribute extractor: rule-based
(regex + small word lists), no LLM, matching the rest of the standalone
package's zero-dependency design. It is deliberately narrow — a handful
of common English sentence shapes, not a general NLU system:

    "There is a red ball on the table."       -> ball.color=red, ball.location=table
    "The blue box contains three batteries."  -> box.color=blue, battery.count=3,
                                                  battery.location=box

extract_facts() returns [] when no known pattern matches — an honest
empty result rather than a guess. Extend _PATTERNS-style functions below
to cover more sentence shapes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_COLORS = (
    "red", "blue", "green", "yellow", "black", "white",
    "orange", "purple", "pink", "brown", "gray", "grey",
)
_COLOR_PATTERN = "|".join(_COLORS)

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _parse_number(token: str) -> int | None:
    token = token.lower()
    if token.isdigit():
        return int(token)
    return _NUMBER_WORDS.get(token)


def _singularize(noun: str) -> str:
    """Rule-based, not a dictionary — has a known blind spot: nouns
    ending in consonant+o that pluralize with "-es" (mango -> mangoes,
    potato -> potatoes, hero -> heroes) come out wrong ("mangoe"), because
    the plural form is indistinguishable by suffix alone from nouns that
    already end in "-oe" and just add "-s" (shoe -> shoes, toe -> toes).
    Both end in "-oes"; telling them apart needs a dictionary, which this
    module deliberately doesn't have. Common case (batteries, boxes,
    apples, ...) is correct.
    """
    lower = noun.lower()
    if lower.endswith("ies") and len(lower) > 3:
        return lower[:-3] + "y"
    if lower.endswith(("ses", "xes", "ches", "shes")):
        return lower[:-2]
    if lower.endswith("s") and not lower.endswith("ss"):
        return lower[:-1]
    return lower


@dataclass(frozen=True)
class ObservedFact:
    """One extracted (entity, attribute, value) triple."""
    entity: str
    attribute: str
    value: Any
    confidence: float = 0.8  # matches BELIEF_OBSERVATION's ontology default


_EXISTENCE_LOCATION = re.compile(
    r"there\s+(?:is|are)\s+(?:a|an|the)?\s*"
    rf"(?:(?P<color>{_COLOR_PATTERN})\s+)?"
    r"(?P<entity>\w+)\s+(?:on|in|at|near|under|above)\s+(?:the\s+)?(?P<location>\w+)",
    re.IGNORECASE,
)

_CONTAINMENT_COUNT = re.compile(
    r"the\s+"
    rf"(?:(?P<container_color>{_COLOR_PATTERN})\s+)?"
    r"(?P<container>\w+)\s+(?:contains?|has|holds?)\s+"
    r"(?P<count>\w+)\s+(?P<items>\w+)",
    re.IGNORECASE,
)

# Copula/state pattern: "<Entity> is <predicate>." — anchored to the
# *whole* sentence (^...$, predicate is exactly one word) so it can't
# fire inside "There is a red ball on the table." (predicate there is
# "a red ball on the table", multiple words, doesn't match \w+$).
# Generic: any single-word predicate maps to attribute="state" — this
# doesn't try to special-case color words the way _EXISTENCE_LOCATION
# does, so "Ball is red" yields ball.state=red, not ball.color=red;
# these are two different sentence shapes with two different (honest,
# not-unified) interpretations.
_COPULA_STATE = re.compile(
    r"^\s*(?P<entity>\w+)\s+is\s+(?P<state>\w+)\s*\.?\s*$",
    re.IGNORECASE,
)


def extract_facts(sentence: str) -> list[ObservedFact]:
    """Extract (entity, attribute, value) facts from a declarative sentence."""
    facts: list[ObservedFact] = []

    m = _COPULA_STATE.match(sentence)
    if m:
        facts.append(ObservedFact(entity=m.group("entity").lower(), attribute="state", value=m.group("state").lower()))
        return facts

    m = _EXISTENCE_LOCATION.search(sentence)
    if m:
        entity = m.group("entity").lower()
        if m.group("color"):
            facts.append(ObservedFact(entity=entity, attribute="color", value=m.group("color").lower()))
        facts.append(ObservedFact(entity=entity, attribute="location", value=m.group("location").lower()))

    m = _CONTAINMENT_COUNT.search(sentence)
    if m:
        container = m.group("container").lower()
        if m.group("container_color"):
            facts.append(ObservedFact(entity=container, attribute="color", value=m.group("container_color").lower()))
        count = _parse_number(m.group("count"))
        if count is not None:
            item = _singularize(m.group("items"))
            facts.append(ObservedFact(entity=item, attribute="count", value=count))
            facts.append(ObservedFact(entity=item, attribute="location", value=container))

    return facts
