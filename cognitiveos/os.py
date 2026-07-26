"""
CognitiveOS — The operating system for a single autonomous cognitive actor.

Each actor has exactly one CognitiveOS instance. The OS provides the
complete cognitive infrastructure: world, messaging, planning, execution,
learning, transition models, and objective scoring.

Architecture:
    Actor ←→ CognitiveOS (one-to-one)
    Actor API: self.os.world(), self.os.send_message(), self.os.transition()

Five explicit responsibilities:

Actor Ownership
    actor          — the single owned actor (read-only)
    set_actor()    — bind actor to this OS (once)

Infrastructure Services
    world()        — read-only shared world
    send_message() — inter-agent messaging (trust-enforced)
    broadcast()    — broadcast to society peers (trust-enforced)
    get_messages() — pending messages (trust-filtered)
    transition()   — learned transition model

Trust Enforcement
    _check_trust()     — is communication allowed?
    _get_actor_trust() — current trust level
    _update_trust()    — evolve trust from outcomes

Reasoning
    evaluate_goals()   — which goals are achievable?
    match_capabilities() — which capabilities can achieve goals?
    check_resources()  — does actor have required resources?
    synthesize()       — combine ontology types into decisions

Cognitive Pipeline (delegated, not owned)
    BeliefFormation — Observe → Believe → Plan → Execute → Learn
    TransitionModel — learned world dynamics across ticks

Trust enforcement:
    Low-trust actors cannot communicate. Messages are filtered by trust
    threshold at send, broadcast, and receive time.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, ClassVar

from cognitiveos.agent_bus import AgentBus
from cognitiveos.capability_bus import CapabilityBus
from cognitiveos.engine.action_executor import ActionExecutor
from cognitiveos.engine.lightweight_engine import LightweightCognitiveEngine

logger = logging.getLogger("agentos.cognitive_os")

TRUST_COMMUNICATION_THRESHOLD = 0.3

# Cap on the local (no society_runtime) message bus — without a bound, a
# long-running actor sending many messages would grow this list forever,
# since get_messages() only reads it and never removes entries. Oldest
# messages are dropped first once the cap is hit.
MAX_LOCAL_MESSAGE_BUS = 1000


@dataclass
class GoalEvaluation:
    """Result of evaluating a goal against current beliefs and capabilities."""
    goal_type_id: str
    achievable: bool
    blockers: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    required_resources: tuple[str, ...] = ()
    confidence: float = 0.0  # how confident we are this goal can be achieved


@dataclass
class CapabilityMatch:
    """Result of matching a capability to a goal."""
    capability_type_id: str
    goal_type_id: str
    proficiency: float = 0.0
    available: bool = True
    blockers: tuple[str, ...] = ()


@dataclass
class ResourceCheck:
    """Result of checking if a resource is available."""
    resource_type_id: str
    available: bool
    quantity: float = 0.0
    required: float = 0.0
    deficit: float = 0.0


@dataclass
class DecisionSynthesis:
    """Result of synthesizing ontology types into a decision."""
    selected_goal: str | None = None
    selected_capabilities: tuple[str, ...] = ()
    required_resources: tuple[str, ...] = ()
    trust_actions: tuple[str, ...] = ()  # trust updates needed
    confidence: float = 0.0
    reasoning: str = ""


@dataclass
class ParsedIntent:
    """Result of parsing a natural language command."""
    raw: str
    action: str = ""          # e.g., "book", "schedule", "send", "find"
    subject: str = ""         # e.g., "flight", "meeting", "email"
    target: str = ""          # e.g., "Berlin", "tomorrow", "alice"
    modifiers: tuple[str, ...] = ()  # e.g., ("next Friday", "economy")
    goal_type_id: str = ""    # mapped to ontology goal
    confidence: float = 0.0


@dataclass
class StepResult:
    """Result of executing a single step."""
    step_number: int
    action: str
    status: str = "pending"  # "pending" | "success" | "failed" | "skipped"
    output: Any = None
    error: str = ""
    duration_ms: float = 0.0
    attempts: int = 1  # >1 means it failed and was retried (see step["retries"])


@dataclass
class RunResult:
    """Result of os.run() — executed plan."""
    intent: ParsedIntent
    goals_created: tuple[str, ...] = ()
    capabilities_needed: tuple[str, ...] = ()
    resources_needed: tuple[str, ...] = ()
    steps: tuple[dict, ...] = ()
    step_results: tuple[StepResult, ...] = ()
    confidence: float = 0.0
    reasoning: str = ""
    ready: bool = False
    executed: bool = False
    success: bool = False
    total_duration_ms: float = 0.0
    interrupted: bool = False  # True if interrupt() fired mid-run; see CognitiveOS.resume()


class _PlanInterrupted(Exception):
    """Internal control-flow signal — interrupt() fired between steps
    (chain) or waves (graph). Caught in run()/resume(); never escapes them.
    """


class CognitiveOS:
    """The operating system for a single actor.

    One-to-one: each actor has exactly one CognitiveOS.

    Five explicit responsibilities:

    Actor Ownership
        actor          — the single owned actor (read-only)
        set_actor()    — bind actor to this OS (once)

    Infrastructure Services
        world()        — read-only shared world
        send_message() — inter-agent messaging (trust-enforced)
        broadcast()    — broadcast to society peers (trust-enforced)
        get_messages() — pending messages (trust-filtered)
        transition()   — learned transition model

    Trust Enforcement
        _check_trust()     — is communication allowed?
        _get_actor_trust() — current trust level
        _update_trust()    — evolve trust from outcomes

    Reasoning
        evaluate_goals()    — which goals are achievable?
        match_capabilities() — which capabilities can achieve goals?
        check_resources()   — does actor have required resources?
        synthesize()        — combine ontology types into decisions

    Cognitive Pipeline
        BeliefFormation — Observe → Believe → Plan → Execute → Learn
        TransitionModel — learned world dynamics across ticks
    """

    def __init__(self, world: Any = None):
        self._world = world
        self._actor: Any = None
        self._engine = None
        self._transition_model = None
        self._message_bus: list[dict] = []
        self._society_runtime: Any = None
        self._capability_bus = CapabilityBus()
        self._agent_bus = AgentBus()
        self._lightweight_engine = LightweightCognitiveEngine()
        self._action_executor = ActionExecutor(capability_bus=self._capability_bus)
        self._interrupt_requested = False
        self._interrupt_reason = ""
        self._suspended_plan: dict[str, Any] | None = None

    def interrupt(self, reason: str = "") -> None:
        """Request that the in-flight run()/resume() stop before its next
        step (chain) or wave (graph) and checkpoint the remaining plan so
        resume() can continue it later. Not instantaneous mid-step
        preemption — checked between steps, same granularity everything
        else in run() operates at.
        """
        self._interrupt_requested = True
        self._interrupt_reason = reason

    def has_suspended_plan(self) -> bool:
        return self._suspended_plan is not None

    # ── Actor Ownership ──────────────────────────────────────

    @property
    def actor(self) -> Any:
        return self._actor

    def set_actor(self, actor: Any) -> None:
        if self._actor is not None:
            raise RuntimeError(
                f"CognitiveOS already owns actor '{self._actor.entity_id}'. "
                f"One OS, one actor. Create a new CognitiveOS for a new actor."
            )
        self._actor = actor
        actor.os = self
        actor.set_world(self._world)
        logger.info("CognitiveOS: bound to actor %s", getattr(actor, 'entity_id', '?'))

    def register_capability(self, capability: Any) -> None:
        """Register a capability (object exposing `.name` and `.fn`) for run() to dispatch to."""
        self._capability_bus.register_capability(capability)

    def register_agent(self, agent: Any) -> None:
        """Register a Broca-style agent for run() to route "agent" steps to."""
        self._agent_bus.register(agent)

    def set_society_runtime(self, runtime: Any) -> None:
        self._society_runtime = runtime

    # ── Infrastructure Services ──────────────────────────────

    def world(self) -> Any:
        return self._world

    # ── Trust Enforcement ────────────────────────────────────

    def _check_trust(self, target_actor_id: str) -> bool:
        if self._actor is None:
            return False
        affiliations = getattr(self._actor, '_affiliations', None)
        if affiliations is None:
            return True
        trust = affiliations.get_trust(target_actor_id)
        return trust >= TRUST_COMMUNICATION_THRESHOLD

    def _get_actor_trust(self, target_actor_id: str) -> float:
        if self._actor is None:
            return 0.0
        affiliations = getattr(self._actor, '_affiliations', None)
        if affiliations is None:
            return 0.5
        return affiliations.get_trust(target_actor_id)

    def _update_trust(self, target_actor_id: str, goal_achieved: bool) -> None:
        if self._actor is None:
            return
        affiliations = getattr(self._actor, '_affiliations', None)
        if affiliations is not None:
            affiliations.update_trust_from_outcome(
                target_actor_id, goal_achieved=goal_achieved,
            )

    # ── Messaging (trust-enforced) ───────────────────────────

    def send_message(self, to_actor: str, msg_type: str,
                     payload: dict | None = None) -> bool:
        if not self._check_trust(to_actor):
            logger.warning(
                "Message BLOCKED: %s → %s (trust=%.2f < %.2f)",
                self._actor.entity_id if self._actor else "?",
                to_actor,
                self._get_actor_trust(to_actor),
                TRUST_COMMUNICATION_THRESHOLD,
            )
            return False

        if self._society_runtime is None:
            self._message_bus.append({
                "from": self._actor.entity_id if self._actor else "?",
                "to": to_actor, "type": msg_type, "payload": payload or {},
            })
            if len(self._message_bus) > MAX_LOCAL_MESSAGE_BUS:
                del self._message_bus[:-MAX_LOCAL_MESSAGE_BUS]
            return True

        self._society_runtime.send_message(
            self._actor.entity_id, to_actor, msg_type, payload,
        )
        return True

    def broadcast(self, msg_type: str, payload: dict | None = None) -> int:
        if self._society_runtime is None:
            return 0

        sent = 0
        for target in self._society_runtime.active_actors():
            if target.actor_id != (self._actor.entity_id if self._actor else "?"):
                if self._check_trust(target.actor_id):
                    self._society_runtime.send_message(
                        self._actor.entity_id, target.actor_id, msg_type, payload,
                    )
                    sent += 1
                else:
                    logger.debug(
                        "Broadcast BLOCKED to %s (trust=%.2f)",
                        target.actor_id, self._get_actor_trust(target.actor_id),
                    )
        return sent

    def get_messages(self) -> list[dict]:
        if self._society_runtime is None:
            return list(self._message_bus)

        all_msgs = self._society_runtime.get_messages_for(
            self._actor.entity_id,
        )

        filtered = []
        for msg in all_msgs:
            sender = msg.get("from", "")
            if self._check_trust(sender):
                filtered.append(msg)
            else:
                logger.debug(
                    "Message FILTERED from %s (trust=%.2f)",
                    sender, self._get_actor_trust(sender),
                )
        return filtered

    def transition(self) -> Any:
        return self._transition_model

    # ── Reasoning ────────────────────────────────────────────

    def evaluate_goals(self) -> list[GoalEvaluation]:
        """Evaluate which goals are achievable given current beliefs and capabilities.

        For each active goal:
        - Check if required beliefs exist with sufficient confidence
        - Check if required capabilities are available
        - Check if required resources are available
        - Calculate overall confidence
        """
        if self._actor is None:
            return []

        results = []
        goal_states = getattr(self._actor, 'goal_states', [])
        beliefs = getattr(self._actor, 'beliefs', [])
        capabilities = getattr(self._actor, 'capabilities', [])
        resources = getattr(self._actor, 'resources', [])

        for goal in goal_states:
            if not goal.active:
                continue

            blockers = []
            req_caps = []
            req_resources = []
            confidence = 0.5

            cap_matches = self._match_for_goal(goal.goal_type_id, capabilities)
            for match in cap_matches:
                req_caps.append(match.capability_type_id)
                if not match.available:
                    blockers.append(f"capability_unavailable:{match.capability_type_id}")
                else:
                    confidence = max(confidence, match.proficiency)

            for res in resources:
                if res.quantity > 0:
                    confidence = max(confidence, 0.3)

            if not beliefs:
                blockers.append("no_beliefs")

            results.append(GoalEvaluation(
                goal_type_id=goal.goal_type_id,
                achievable=len(blockers) == 0,
                blockers=tuple(blockers),
                required_capabilities=tuple(req_caps),
                required_resources=tuple(req_resources),
                confidence=confidence,
            ))

        return results

    def _match_for_goal(self, goal_type_id: str, capabilities: list) -> list[CapabilityMatch]:
        """Match capabilities to a goal type."""
        _GOAL_CAPABILITY_MAP = {
            "wealth": ["investment", "accounting", "analysis"],
            "safety": ["reasoning", "planning", "communication"],
            "health": ["caregiving", "diagnosis", "treatment"],
            "mastery": ["teaching", "research", "analysis"],
            "accomplishment": ["planning", "coding", "automation"],
            "expression": ["writing", "design", "communication"],
            "discovery": ["research", "analysis", "data_processing"],
            "order": ["leadership", "coordination", "negotiation"],
            "legacy": ["leadership", "teaching", "innovation"],
        }

        required = _GOAL_CAPABILITY_MAP.get(goal_type_id, [])
        matches = []
        for cap_type in required:
            available = any(c.capability_type_id == cap_type and c.available
                           for c in capabilities)
            proficiency = max((c.proficiency for c in capabilities
                             if c.capability_type_id == cap_type), default=0.0)
            matches.append(CapabilityMatch(
                capability_type_id=cap_type,
                goal_type_id=goal_type_id,
                proficiency=proficiency,
                available=available,
            ))
        return matches

    def match_capabilities(self) -> list[CapabilityMatch]:
        """Match all capabilities to all active goals."""
        if self._actor is None:
            return []

        goals = getattr(self._actor, 'goal_states', [])
        capabilities = getattr(self._actor, 'capabilities', [])

        matches = []
        for goal in goals:
            if goal.active:
                matches.extend(self._match_for_goal(goal.goal_type_id, capabilities))
        return matches

    def check_resources(self, required: dict[str, float] | None = None) -> list[ResourceCheck]:
        """Check if the actor has required resources."""
        if self._actor is None:
            return []

        if required is None:
            required = {}

        resources = getattr(self._actor, 'resources', [])
        results = []

        for res_type, req_qty in required.items():
            available = sum(r.quantity for r in resources if r.resource_type_id == res_type)
            deficit = max(0.0, req_qty - available)
            results.append(ResourceCheck(
                resource_type_id=res_type,
                available=available >= req_qty,
                quantity=available,
                required=req_qty,
                deficit=deficit,
            ))

        return results

    def synthesize(self) -> DecisionSynthesis:
        """Synthesize all ontology types into a coherent decision.

        Combines:
        - Goal evaluation (which goals are achievable)
        - Capability matching (which capabilities can help)
        - Resource checking (what resources are needed)
        - Trust assessment (who to communicate with)
        """
        if self._actor is None:
            return DecisionSynthesis(reasoning="No actor bound")

        goal_evals = self.evaluate_goals()
        cap_matches = self.match_capabilities()

        achievable = [g for g in goal_evals if g.achievable]
        if not achievable:
            return DecisionSynthesis(
                reasoning="No achievable goals",
                confidence=0.0,
            )

        best_goal = min(achievable, key=lambda g: (
            -g.confidence,
            getattr(self._actor, '_goal_states', [])[0].priority
            if getattr(self._actor, '_goal_states', []) else 50,
        ))

        needed_caps = [m.capability_type_id for m in cap_matches
                       if m.goal_type_id == best_goal.goal_type_id and m.available]

        trust_actions = []
        affiliations = getattr(self._actor, '_affiliations', [])
        if affiliations:
            for aff in getattr(affiliations, '_affiliations', {}).values():
                trust = affiliations.get_trust(aff.target_id)
                if trust < 0.5:
                    trust_actions.append(f"build_trust:{aff.target_id}")

        return DecisionSynthesis(
            selected_goal=best_goal.goal_type_id,
            selected_capabilities=tuple(needed_caps),
            trust_actions=tuple(trust_actions),
            confidence=best_goal.confidence,
            reasoning=f"Selected {best_goal.goal_type_id} (confidence={best_goal.confidence:.2f})",
        )

    # ── Natural Language Task Execution ──────────────────────

    _INTENT_ACTION_MAP: ClassVar[dict[str, str]] = {
        "book": "travel",
        "buy": "acquisition",
        "purchase": "acquisition",
        "send": "communication",
        "write": "communication",
        "schedule": "planning",
        "create": "creation",
        "find": "discovery",
        "search": "discovery",
        "add": "modification",
        "update": "modification",
        "delete": "modification",
        "remove": "modification",
        "call": "communication",
        "meet": "social",
        "invite": "social",
        "share": "communication",
        "pay": "financial",
        "transfer": "financial",
    }

    _SUBJECT_GOAL_MAP: ClassVar[dict[str, str]] = {
        "flight": "travel",
        "hotel": "travel",
        "reservation": "travel",
        "meeting": "social",
        "appointment": "social",
        "event": "social",
        "email": "communication",
        "message": "communication",
        "document": "creation",
        "report": "creation",
        "file": "creation",
        "task": "accomplishment",
        "project": "accomplishment",
        "calendar": "planning",
        "reminder": "planning",
        "alarm": "planning",
        "food": "health",
        "groceries": "acquisition",
        "medicine": "health",
        "money": "financial",
        "payment": "financial",
    }

    # Rule-based urgency signal — no LLM required for the default path.
    # Real but narrow: a keyword hit, not genuine risk assessment.
    _URGENT_KEYWORDS = (
        "emergency", "urgent", "critical", "asap", "immediately",
        "ambulance", "fire", "911", "danger", "dying", "bleeding", "help",
    )
    _URGENT_PRIORITY = 5
    _DEFAULT_PRIORITY = 30

    def _infer_priority(self, text: str) -> int:
        """Lower number = higher priority (matches top_goal()'s min-priority
        convention). Flat default for everything else — this is a real,
        if narrow, urgency signal, not a substitute for genuine risk
        assessment.
        """
        lower = text.lower()
        if any(word in lower for word in self._URGENT_KEYWORDS):
            return self._URGENT_PRIORITY
        return self._DEFAULT_PRIORITY

    def _parse_intent(self, command: str) -> ParsedIntent:
        """Parse a natural language command into structured intent.

        Uses keyword matching (V1). Future versions will use NLU.
        """
        words = command.lower().split()
        action = ""
        subject = ""
        target = ""
        modifiers = []

        # Words to skip (pronouns, prepositions, articles)
        _SKIP = {"me", "my", "a", "an", "the", "to", "at", "on", "for",
                 "with", "from", "it", "that", "this", "and", "or", "of"}

        for word in words:
            clean = word.strip(".,!?;:")
            if clean in _SKIP:
                continue
            if clean in self._INTENT_ACTION_MAP and not action:
                action = clean
            elif clean in self._SUBJECT_GOAL_MAP and not subject:
                subject = clean
            elif any(c.isdigit() for c in clean) or clean in (
                "next", "tomorrow", "today", "monday", "tuesday", "wednesday",
                "thursday", "friday", "saturday", "sunday", "this",
                "economy", "business", "first", "class", "urgent", "asap",
            ):
                modifiers = (*modifiers, clean)
            elif not action:
                action = clean
            elif not subject and action:
                subject = clean
            elif not target and subject:
                target = clean

        if action and subject:
            goal_type_id = self._SUBJECT_GOAL_MAP.get(subject, "accomplishment")
        elif action:
            goal_type_id = self._INTENT_ACTION_MAP.get(action, "accomplishment")
        else:
            goal_type_id = "accomplishment"
            action = words[0] if words else "execute"

        confidence = 0.7 if action and subject else 0.4 if action else 0.2

        return ParsedIntent(
            raw=command,
            action=action,
            subject=subject,
            target=target,
            modifiers=tuple(modifiers),
            goal_type_id=goal_type_id,
            confidence=confidence,
        )

    def observe(self, sentence: str) -> list:
        """Observe stage — extract structured facts from a declarative
        sentence (cognitiveos.observation) and record them onto the
        bound actor as beliefs (belief_type_id="observation").

        Distinct from run(): run() parses *imperative* commands ("Book a
        flight") into an intent and executes a plan. observe() is for
        *declarative* statements ("There is a red ball on the table")
        that describe world state — nothing to plan or execute, just
        something to believe. Returns the list of BeliefState objects
        created (empty if no known sentence pattern matched, or if no
        actor is bound).
        """
        from cognitiveos.observation import extract_facts

        if self._actor is None:
            return []

        created = []
        for fact in extract_facts(sentence):
            belief = self._actor.add_belief(
                belief_type_id="observation",
                subject=fact.entity,
                attribute=fact.attribute,
                value=fact.value,
                confidence=fact.confidence,
                evidence=(sentence,),
            )
            created.append(belief)
        return created

    async def run(self, command: str) -> RunResult:
        """Parse a natural language command and execute through the cognitive runtime.

        Flow:
            1. Parse intent from natural language
            2. Set goal on actor
            3. Engine produces a plan with steps
            4. ExecutionMiddleware executes each step, accumulating knowledge
            5. Return structured results

        The engine decides what steps to take.
        The middleware handles execution and knowledge acquisition.
        """
        import time as _time

        intent = self._parse_intent(command)

        if self._actor is None:
            return RunResult(
                intent=intent,
                reasoning="No actor bound to this CognitiveOS",
            )

        start = _time.time()

        # 1. Set goal (and the parsed intent, for the engine's Observe stage) on actor.
        #    goal_type_id alone is not a unique goal identity — it's a small,
        #    coarse ontology bucket (~24 entries) that unrelated requests
        #    routinely collapse into ("buy milk" and "charge laptop" both ->
        #    "accomplishment"). Track distinctness by (goal_type_id, label)
        #    instead, so a second distinct request isn't silently dropped
        #    just because its type coincides with an earlier one's.
        self._actor._current_intent = intent
        if intent.goal_type_id:
            self._actor._current_goal = intent.goal_type_id
            if hasattr(self._actor, '_goals') and intent.goal_type_id not in self._actor._goals:
                self._actor._goals.append(intent.goal_type_id)

            already_tracked = any(
                g.goal_type_id == intent.goal_type_id and getattr(g, 'label', '') == intent.raw
                for g in getattr(self._actor, 'goal_states', [])
            )
            if not already_tracked and hasattr(self._actor, 'add_goal'):
                self._actor.add_goal(
                    intent.goal_type_id,
                    priority=self._infer_priority(intent.raw),
                    label=intent.raw,
                )

        # Beliefs added without an attribute accumulate indefinitely (see
        # Actor.add_belief's revision semantics) — decay once per cognitive
        # cycle so a long-running actor's belief list doesn't grow forever.
        # Uses decay_beliefs()'s own default rate; low-confidence beliefs
        # used within this same run() call are unaffected (they'd need to
        # already be near-zero confidence to be pruned by one pass).
        if hasattr(self._actor, 'decay_beliefs'):
            self._actor.decay_beliefs()

        # 2. Evaluate
        cap_matches = self.match_capabilities()
        needed_caps = tuple(m.capability_type_id for m in cap_matches if m.available)

        # 3. Get plan from the injected engine, falling back to the built-in
        #    DeterministicPlanner (cognitiveos.engine) — real forward-chaining
        #    planning either way, never a hardcoded fake step.
        steps = []
        plan: dict[str, Any] = {}
        engine = self._engine or self._lightweight_engine
        try:
            engine_result = await engine.tick(self._actor)
            if isinstance(engine_result, dict):
                plan = engine_result.get("plan", {}) or {}
                if isinstance(plan, dict):
                    steps = plan.get("steps", [])
                else:
                    plan = {}
        except Exception as e:
            logger.warning("Engine tick failed: %s", e)

        # 4. Execute through the OS's persistent CapabilityBus + AgentBus.
        #    plan["execution"] picks the dispatch strategy:
        #      "chain" (default) — steps run strictly in plan order; each
        #        step's output is recorded via state.set_data(name, output)
        #        so every later step can read it via context.get_data(name).
        #      "graph" — each step may declare depends_on: [names]; steps
        #        run in topological waves, everything within a wave
        #        concurrently (asyncio.gather), and a failed dependency
        #        blocks its dependents without running them.
        from cognitiveos.execution_state import ExecutionState as ExecState

        state = ExecState(question=command)
        execution_mode = plan.get("execution", "chain")

        interrupted = False
        interrupt_reason = ""
        try:
            if execution_mode == "graph":
                step_results = await self._run_graph(steps, command, state)
            else:
                step_results = await self._run_chain(
                    steps, command, state, stop_on_failure=bool(plan.get("stop_on_failure")),
                )
        except _PlanInterrupted as exc:
            interrupted = True
            interrupt_reason = str(exc)
            step_results = self._suspended_plan["completed_results"]

        return self._build_run_result(
            intent, needed_caps, steps, step_results, start,
            interrupted=interrupted, interrupt_reason=interrupt_reason,
        )

    def _build_run_result(
        self, intent: ParsedIntent, needed_caps: tuple, steps: list[dict],
        step_results: list[StepResult], start: float,
        interrupted: bool = False, interrupt_reason: str = "",
    ) -> RunResult:
        import time as _time

        duration = (_time.time() - start) * 1000
        success = (not interrupted) and all(sr.status == "success" for sr in step_results) if step_results else False

        if interrupted:
            reasoning = (
                f"Interrupted ({interrupt_reason or 'no reason given'}) after "
                f"{len(step_results)} step(s) — {(self.has_suspended_plan() and 'checkpointed') or 'lost checkpoint'}; "
                f"call resume() to continue."
            )
        else:
            reasoning = (
                f"Parsed: {intent.action} {intent.subject} → {intent.goal_type_id} "
                f"| {len(step_results)} steps, {sum(1 for s in step_results if s.status == 'success')} succeeded"
            )

        return RunResult(
            intent=intent,
            goals_created=(intent.goal_type_id,) if intent.goal_type_id else (),
            capabilities_needed=needed_caps,
            steps=tuple(steps),
            step_results=tuple(step_results),
            confidence=intent.confidence,
            reasoning=reasoning,
            ready=len(step_results) > 0,
            executed=True,
            success=success,
            total_duration_ms=duration,
            interrupted=interrupted,
        )

    async def resume(self) -> RunResult:
        """Continue a plan suspended by interrupt(). Picks up exactly where
        _run_chain/_run_graph checkpointed — prior step_results are kept,
        only the not-yet-dispatched remainder is re-run. If interrupt()
        fires again during resume, the plan is re-checkpointed and this
        returns another interrupted=True RunResult, resumable again.

        Calling resume() with nothing suspended is not an error — it's an
        honest no-op RunResult (executed=False), not a raised exception.
        """
        import time as _time

        if self._suspended_plan is None:
            return RunResult(
                intent=ParsedIntent(raw=""),
                reasoning="No suspended plan to resume — call interrupt() during a run() first.",
            )

        checkpoint = self._suspended_plan
        self._suspended_plan = None
        start = _time.time()

        intent = self._parse_intent(checkpoint["command"])
        cap_matches = self.match_capabilities()
        needed_caps = tuple(m.capability_type_id for m in cap_matches if m.available)

        interrupted = False
        interrupt_reason = ""
        try:
            if checkpoint["execution"] == "graph":
                step_results = await self._run_graph(
                    checkpoint["steps"], checkpoint["command"], checkpoint["state"],
                    prior_results=checkpoint["completed_results"],
                )
            else:
                step_results = await self._run_chain(
                    checkpoint["steps"], checkpoint["command"], checkpoint["state"],
                    stop_on_failure=bool(checkpoint.get("stop_on_failure")),
                    prior_results=checkpoint["completed_results"],
                )
        except _PlanInterrupted as exc:
            interrupted = True
            interrupt_reason = str(exc)
            step_results = self._suspended_plan["completed_results"]

        return self._build_run_result(
            intent, needed_caps, checkpoint["steps"], step_results, start,
            interrupted=interrupted, interrupt_reason=interrupt_reason,
        )

    async def _dispatch_step(self, i: int, step: dict, command: str, state: Any) -> StepResult:
        """Execute exactly one plan step (agent or capability) and record
        its output into state on success, so later steps can read it via
        state.get_data(name).

        A step may declare `requires_resources: {resource_type_id: quantity}`
        — checked via check_resources() *before* dispatch; if unmet, the
        step fails with a clear reason and the capability/agent is never
        called (not retried — a missing resource won't appear between
        immediate retries). This is a real precondition gate, not just
        check_resources() existing for callers to use manually.

        A step may also declare `retries: N` — on failure, the dispatch
        (not the precondition check) is retried up to N additional times
        before giving up; StepResult.attempts records how many it took.

        A step with type "conditional" ({"condition": {...}, "if_true": ...,
        "if_false": ...}) evaluates its condition against the actor's
        beliefs (see cognitiveos.observation / CognitiveOS.observe()) and
        recursively dispatches whichever branch applies — a real if/else,
        not a fixed linear sequence.
        """
        from cognitiveos.engine.execution import Action

        name = step.get("name", step.get("action", "unknown"))
        step_type = step.get("type", "capability")

        if step_type == "conditional":
            return await self._dispatch_conditional(i, step, command, state)

        requires_resources = step.get("requires_resources")
        if requires_resources:
            checks = self.check_resources(requires_resources)
            missing = [c for c in checks if not c.available]
            if missing:
                reasons = ", ".join(f"{c.resource_type_id} (have {c.quantity}, need {c.required})" for c in missing)
                return StepResult(
                    step_number=i, action=name, status="failed",
                    error=f"missing_resources: {reasons}",
                )

        max_attempts = 1 + max(0, int(step.get("retries", 0) or 0))
        step_result = StepResult(step_number=i, action=name, status="failed")

        for attempt in range(1, max_attempts + 1):
            try:
                if step_type == "agent":
                    result = await self._agent_bus.execute(name, question=command, state=state)
                    success = result.success
                    output = result.produced if hasattr(result, 'produced') else {}
                    error = output.get("error", "") if not success else ""
                else:
                    action = Action(action_id=str(i), capability=name, source_step=name)
                    exec_result = await self._action_executor.execute((action,), context=state)
                    outcome = exec_result.actions[0] if exec_result.actions else None
                    success = outcome.success if outcome is not None else False
                    output = outcome.result if outcome is not None and isinstance(outcome.result, dict) else {}
                    error = outcome.error if outcome is not None else "no_outcome"

                step_result = StepResult(
                    step_number=i, action=name,
                    status="success" if success else "failed",
                    output=output, error=error, attempts=attempt,
                )
            except Exception as e:
                step_result = StepResult(
                    step_number=i, action=name, status="failed", error=str(e), attempts=attempt,
                )

            if step_result.status == "success":
                break

        if step_result.status == "success":
            state.set_data(name, step_result.output)
        return step_result

    async def _dispatch_conditional(self, i: int, step: dict, command: str, state: Any) -> StepResult:
        """Evaluate step["condition"] and recursively dispatch step["if_true"]
        or step["if_false"] (each may be a step name — dispatched as a
        capability — or a full step dict for e.g. an agent branch).
        Neither branch is a plan step in its own right; only the chosen
        one ever actually runs.
        """
        condition_result = self._evaluate_condition(step.get("condition") or {})
        branch = step.get("if_true") if condition_result else step.get("if_false")

        if branch is None:
            return StepResult(
                step_number=i, action=step.get("name", "conditional"), status="skipped",
                output={"condition_result": condition_result},
            )

        branch_step = branch if isinstance(branch, dict) else {"name": branch, "type": "capability"}
        result = await self._dispatch_step(i, branch_step, command, state)
        result.output = {**(result.output or {}), "condition_result": condition_result}
        return result

    def _evaluate_condition(self, condition: dict) -> bool:
        """condition: {"subject": ..., "attribute": "", "equals": ...} —
        checked against the bound actor's beliefs (the same subject/
        attribute/value model cognitiveos.observation populates via
        CognitiveOS.observe()). No matching belief is treated as an
        honest "we don't believe that" (False), not an error.
        """
        subject = condition.get("subject")
        if subject is None or self._actor is None:
            return False
        attribute = condition.get("attribute", "")
        expected = condition.get("equals")
        for belief in getattr(self._actor, "beliefs", []):
            if belief.subject == subject and belief.attribute == attribute:
                return belief.value == expected
        return False

    async def _run_chain(
        self, steps: list[dict], command: str, state: Any, stop_on_failure: bool = False,
        prior_results: list[StepResult] | None = None,
    ) -> list[StepResult]:
        """Default execution strategy — steps run strictly in plan order.
        A capability step and an agent step can be adjacent in a real
        plan, so both go through the same loop rather than one type
        being batched separately (which would both reorder execution
        and make cross-step chaining impossible).

        stop_on_failure (plan["stop_on_failure"]) is opt-in — the default
        (False) preserves existing behavior (every step is attempted
        regardless of earlier failures, which several examples rely on to
        show exactly which capabilities are missing). When True, dispatch
        stops at the first failed step; remaining steps are reported
        "skipped", never executed.

        prior_results seeds already-completed steps when resuming after
        an interrupt() — step_number continues from there rather than
        restarting at 1, so a resumed step still reports its real
        position in the original plan. Before dispatching each step,
        checks interrupt_requested(): if set, checkpoints `steps` (from
        this point on) + `state` into self._suspended_plan and raises
        _PlanInterrupted for run()/resume() to catch.
        """
        results = list(prior_results) if prior_results else []
        start_index = len(results)

        for offset, step in enumerate(steps):
            i = start_index + offset + 1

            if self._interrupt_requested:
                reason = self._interrupt_reason
                self._interrupt_requested = False
                self._interrupt_reason = ""
                self._suspended_plan = {
                    "execution": "chain",
                    "steps": steps[offset:],
                    "command": command,
                    "state": state,
                    "stop_on_failure": stop_on_failure,
                    "completed_results": results,
                }
                raise _PlanInterrupted(reason)

            results.append(await self._dispatch_step(i, step, command, state))
            if stop_on_failure and results[-1].status != "success":
                for j, remaining in enumerate(steps[offset + 1:], start=i + 1):
                    name = remaining.get("name", remaining.get("action", "unknown"))
                    results.append(StepResult(step_number=j, action=name, status="skipped"))
                break
        return results

    async def _run_graph(
        self, steps: list[dict], command: str, state: Any,
        prior_results: list[StepResult] | None = None,
    ) -> list[StepResult]:
        """Dependency-graph execution strategy — each step may declare
        `depends_on: [names]`. Steps run in topological waves; everything
        within a wave (no unmet dependencies) is scheduled concurrently
        via asyncio.gather. A step whose dependency failed, is unresolvable
        (unknown name), or is part of a cycle is marked failed without
        being executed — it never runs against missing/broken input.

        Wall-clock parallelism within a wave is real for agent steps
        (AgentBus.execute() is async all the way down — see
        examples/agent_capability.py). Capability steps go through
        CapabilityBus, whose `fn(kwargs)` contract is synchronous
        (see capability_bus.py) — asyncio.gather still schedules them
        together, but a capability that blocks (e.g. requests.get(),
        time.sleep()) blocks the event loop for its own duration same as
        it would sequentially. Dependency ordering and cross-step data
        flow (state.get_data()) are correct either way; only the
        concurrency speedup depends on the step being genuinely async.

        prior_results seeds already-completed steps when resuming after
        an interrupt() — their names count as satisfied dependencies even
        though their step dicts aren't in `steps` anymore (only the
        not-yet-dispatched remainder is, after a checkpoint). Checked
        before each wave: if interrupted, checkpoints the undispatched
        steps and raises _PlanInterrupted.
        """
        indexed: dict[str, tuple[int, dict]] = {}
        for i, step in enumerate(steps, 1):
            name = step.get("name", step.get("action", "unknown"))
            indexed[name] = (i, step)

        depends_on = {name: tuple(step.get("depends_on") or ()) for name, (_, step) in indexed.items()}

        results_by_name: dict[str, StepResult] = {}
        step_results: list[StepResult] = []
        if prior_results:
            for sr in prior_results:
                results_by_name[sr.action] = sr
                step_results.append(sr)

        remaining = set(indexed.keys())

        while remaining:
            if self._interrupt_requested:
                reason = self._interrupt_reason
                self._interrupt_requested = False
                self._interrupt_reason = ""
                self._suspended_plan = {
                    "execution": "graph",
                    "steps": [indexed[n][1] for n in remaining],
                    "command": command,
                    "state": state,
                    "completed_results": list(step_results),
                }
                raise _PlanInterrupted(reason)

            ready = []
            for name in list(remaining):
                unknown = [d for d in depends_on[name] if d not in indexed and d not in results_by_name]
                if unknown:
                    i, _ = indexed[name]
                    sr = StepResult(step_number=i, action=name, status="failed",
                                    error=f"unknown_dependency:{unknown[0]}")
                    results_by_name[name] = sr
                    step_results.append(sr)
                    remaining.discard(name)
                    continue
                if all(d in results_by_name for d in depends_on[name]):
                    ready.append(name)

            if not ready:
                # Every remaining step is blocked on another remaining step —
                # a dependency cycle. Fail them all rather than hang.
                for name in remaining:
                    i, _ = indexed[name]
                    step_results.append(StepResult(
                        step_number=i, action=name, status="failed",
                        error="dependency_cycle",
                    ))
                break

            to_run = []
            for name in ready:
                failed_dep = next(
                    (d for d in depends_on[name] if results_by_name[d].status != "success"), None,
                )
                if failed_dep:
                    i, _ = indexed[name]
                    sr = StepResult(step_number=i, action=name, status="failed",
                                    error=f"dependency_failed:{failed_dep}")
                    results_by_name[name] = sr
                    step_results.append(sr)
                    remaining.discard(name)
                else:
                    to_run.append(name)

            if to_run:
                wave = await asyncio.gather(*(
                    self._dispatch_step(indexed[n][0], indexed[n][1], command, state) for n in to_run
                ))
                for name, sr in zip(to_run, wave, strict=True):
                    results_by_name[name] = sr
                    step_results.append(sr)
                    remaining.discard(name)

        step_results.sort(key=lambda sr: sr.step_number)
        return step_results

    # ── Cognitive Pipeline (injectable) ──────────────────────

    def set_engine(self, engine: Any) -> None:
        """Inject a BeliefFormation-compatible engine.

        Optional — without this, tick() returns an error.
        With it, tick() runs the full cognitive pipeline.
        """
        self._engine = engine

    def has_engine(self) -> bool:
        return self._engine is not None

    async def tick(self) -> dict:
        """Run one cognitive cycle.

        Requires an engine to be set via set_engine().
        Without an engine, returns an error indicating
        the pipeline is not available.
        """
        actor = self._actor
        if actor is None:
            return {"error": "No actor bound to this CognitiveOS"}

        if self._engine is None:
            return {"error": "No engine injected. Call set_engine() with an ICognitiveEngine implementation."}

        if hasattr(actor, 'decay_beliefs'):
            actor.decay_beliefs()

        try:
            result = await self._engine.tick(actor)
            return {
                "success": True,
                "result": result,
            }
        except Exception as e:
            return {"error": str(e), "success": False}
