# API Reference

## Core Types

### `Actor`

```python
Actor(
    entity_id: str,
    actor_type_id: str = "human",
    name: str = "",
    goals: list[str] | None = None,
    objective: str = "",
)
```

The autonomous entity. Owns identity, goals, beliefs, capabilities, and resources.

**Properties:**
- `entity_id` → `str` — unique identifier
- `identity` → `Identity` — who the actor is
- `actor_type_id` → `str` — type reference (e.g. "human", "ai_agent")
- `os` → `CognitiveOS | None` — bound runtime
- `affiliations` → `AffiliationManager` — trust and relationships
- `goal_states` → `list[GoalState]` — current goals
- `beliefs` → `list[BeliefState]` — what the actor knows
- `capabilities` → `list[CapabilityState]` — what the actor can do
- `resources` → `list[ResourceState]` — what the actor has

**Methods:**
- `add_goal(goal_type_id, priority=50, label="")` → `GoalState`
- `remove_goal(goal_type_id)` → `bool`
- `active_goals()` → `list[GoalState]`
- `top_goal()` → `GoalState | None`
- `update_goal_progress(goal_type_id, progress)` → `None`
- `add_belief(belief_type_id, subject, attribute="", value=None, confidence=0.5, evidence=())` → `BeliefState`
- `beliefs_about(subject)` → `list[BeliefState]`
- `beliefs_by_type(belief_type_id)` → `list[BeliefState]`
- `highest_confidence(subject)` → `BeliefState | None`
- `decay_beliefs(decay_rate=0.05)` → `int` — count of removed beliefs
- `add_capability(capability_type_id, proficiency=0.5)` → `CapabilityState`
- `has_capability(capability_type_id)` → `bool`
- `add_resource(resource_type_id, quantity, unit="")` → `ResourceState`
- `has_resource(resource_type_id, min_quantity=1.0)` → `bool`
- `resource_quantity(resource_type_id)` → `float`
- `send_message(to, msg_type, payload=None)` → `bool`
- `broadcast(msg_type, payload=None)` → `int`

---

### `CognitiveOS`

```python
CognitiveOS(world: Any = None)
```

The runtime. One-to-one with an Actor.

**Methods:**
- `set_actor(actor)` → `None` — bind actor (once)
- `register_capability(capability)` → `None`
- `register_agent(agent)` → `None`
- `set_engine(engine)` → `None` — inject custom `ICognitiveEngine`
- `set_society_runtime(runtime)` → `None`
- `observe(sentence)` → `list[BeliefState]` — extract facts from declarative text
- `run(command)` → `RunResult` — parse and execute a natural language command
- `resume()` → `RunResult` — continue an interrupted plan
- `interrupt(reason="")` → `None` — request checkpoint before next step
- `has_suspended_plan()` → `bool`
- `tick()` → `dict` — run one cognitive cycle (requires engine)
- `evaluate_goals()` → `list[GoalEvaluation]`
- `match_capabilities()` → `list[CapabilityMatch]`
- `check_resources(required=None)` → `list[ResourceCheck]`
- `synthesize()` → `DecisionSynthesis`
- `send_message(to_actor, msg_type, payload=None)` → `bool`
- `broadcast(msg_type, payload=None)` → `int`
- `get_messages()` → `list[dict]`

---

## Data Classes

### `ParsedIntent`

```python
@dataclass
class ParsedIntent:
    raw: str
    action: str = ""          # e.g. "book", "schedule"
    subject: str = ""         # e.g. "flight", "meeting"
    target: str = ""          # e.g. "Berlin", "tomorrow"
    modifiers: tuple[str, ...] = ()
    goal_type_id: str = ""
    confidence: float = 0.0
```

### `RunResult`

```python
@dataclass
class RunResult:
    intent: ParsedIntent
    goals_created: tuple[str, ...] = ()
    capabilities_needed: tuple[str, ...] = ()
    steps: tuple[dict, ...] = ()
    step_results: tuple[StepResult, ...] = ()
    confidence: float = 0.0
    reasoning: str = ""
    ready: bool = False
    executed: bool = False
    success: bool = False
    total_duration_ms: float = 0.0
    interrupted: bool = False
```

### `StepResult`

```python
@dataclass
class StepResult:
    step_number: int
    action: str
    status: str = "pending"  # "pending" | "success" | "failed" | "skipped"
    output: Any = None
    error: str = ""
    duration_ms: float = 0.0
    attempts: int = 1
```

### `GoalEvaluation`

```python
@dataclass
class GoalEvaluation:
    goal_type_id: str
    achievable: bool
    blockers: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    required_resources: tuple[str, ...] = ()
    confidence: float = 0.0
```

### `DecisionSynthesis`

```python
@dataclass
class DecisionSynthesis:
    selected_goal: str | None = None
    selected_capabilities: tuple[str, ...] = ()
    required_resources: tuple[str, ...] = ()
    trust_actions: tuple[str, ...] = ()
    confidence: float = 0.0
    reasoning: str = ""
```

---

## State Types

### `Identity`

```python
@dataclass(frozen=True)
class Identity:
    actor_type_id: str
    name: str
    description: str = ""
```

### `GoalState`

```python
@dataclass(frozen=True)
class GoalState:
    goal_type_id: str
    priority: int = 50       # lower = higher priority
    progress: float = 0.0    # 0.0 to 1.0
    active: bool = True
    label: str = ""
```

### `BeliefState`

```python
@dataclass(frozen=True)
class BeliefState:
    belief_type_id: str
    subject: str
    attribute: str = ""
    value: Any = None
    confidence: float = 0.5
    evidence: tuple[str, ...] = ()
    age_days: int = 0
```

### `CapabilityState`

```python
@dataclass(frozen=True)
class CapabilityState:
    capability_type_id: str
    proficiency: float = 0.5  # 0.0 to 1.0
    available: bool = True
```

### `ResourceState`

```python
@dataclass(frozen=True)
class ResourceState:
    resource_type_id: str
    quantity: float = 0.0
    unit: str = ""
```

---

## Execution Types

### `CapabilityBus`

```python
class CapabilityBus:
    register_capability(capability) -> None
    execute(capability_name, *, context=None, **kwargs) -> CapabilityResult
    list_providers(capability_name) -> list[Any]
    summary() -> dict
```

### `CapabilityResult`

```python
@dataclass
class CapabilityResult:
    name: str
    success: bool
    produced: dict[str, Any]
    events_emitted: list[str]
    latency_ms: float
```

### `AgentBus`

```python
class AgentBus:
    register(agent) -> None
    execute(agent_name, **kwargs) -> AgentResult
    summary() -> dict
```

### `AgentResult`

```python
@dataclass
class AgentResult:
    agent_name: str
    success: bool
    produced: dict[str, Any]
    events_emitted: list[str]
    latency_ms: float
    feedback: float
    metadata: dict[str, Any]
```

### `ExecutionState`

```python
@dataclass
class ExecutionState:
    question: str
    intent: str
    phase: ExecutionPhase
    # ... entity, hierarchy, knowledge, and answer fields
    set_data(key, value) -> None
    get_data(key) -> Any
    has_data(key) -> bool
    to_dict() -> dict
    from_dict(data) -> ExecutionState  # classmethod
```

---

## Interfaces

### `ICognitiveEngine`

```python
class ICognitiveEngine(Protocol):
    async def tick(self, actor: Any) -> Any: ...
```

### `ITransitionModel`

```python
class ITransitionModel(Protocol):
    def predict(self, state: Any, action: Any) -> Any: ...
```

### `IMessageBus`

```python
class IMessageBus(Protocol):
    def send(self, from_id, to_id, msg_type, payload) -> bool: ...
    def broadcast(self, from_id, msg_type, payload) -> int: ...
    def receive(self, actor_id) -> list[dict]: ...
```

### `IWorldProvider`

```python
class IWorldProvider(Protocol):
    def observe(self) -> Any: ...
```

### `ITrustProvider`

```python
class ITrustProvider(Protocol):
    def check_trust(self, source, target) -> float: ...
    def update_trust(self, source, target, outcome) -> None: ...
```

### `ICapability`

```python
class ICapability(ABC):
    capability_name: str          # abstract property
    capability_type: str          # abstract property
    async execute(state, **kwargs) -> CapabilityResult  # abstract
    can_execute(state) -> bool    # abstract
    estimate_reward(state) -> float  # abstract
    estimate_cost(state) -> float    # abstract
    compute_confidence(state) -> float  # default 0.5
```

### `ActorProtocol`

```python
class ActorProtocol(Protocol):
    entity_id: str
    async def tick(self) -> Any: ...
    def set_world(self, world: Any) -> None: ...
```

---

## Exceptions

| Exception | Raised when |
|---|---|
| `CognitiveOSError` | Base exception |
| `ActorNotBoundError` | No actor bound to CognitiveOS |
| `EngineNotInjectedError` | `tick()` called without engine |
| `TrustViolationError` | Trust-enforced operation blocked |
| `InvalidActorError` | Invalid actor provided |
| `DuplicateActorError` | Second actor bound to same OS |
