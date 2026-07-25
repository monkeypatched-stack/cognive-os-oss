# Architecture Guide

## Overview

CognitiveOS is a standalone cognitive runtime for a single autonomous actor. Its core loop:

```
Observe → Believe → Plan → Execute
```

No shared state. No infrastructure requirements. No LLM dependency.

## Design Principles

| Principle | Meaning |
|---|---|
| **Single Actor** | One CognitiveOS owns exactly one Actor. Multiple actors = multiple runtimes. |
| **Zero Dependencies** | `dependencies = []`. Everything beyond the stdlib is optional. |
| **Local Cognition** | Every decision is made locally. No distributed execution. |
| **Real Execution** | No canned responses. Every planner performs actual reasoning. |
| **Extensible** | Planners, capabilities, agents — all injected through interfaces. |

## Component Map

```
Application (CLI / SDK / Library)
        │
        ▼
   CognitiveOS
        │
   ┌────┴────────────────┐
   │                     │
CapabilityBus         AgentBus
   │                     │
   ▼                     ▼
Capabilities           Agents
```

### Actor

The autonomous entity. Owns identity, goals, beliefs, capabilities, and resources. Contains no execution logic — delegates everything to CognitiveOS.

### CognitiveOS

The runtime. Responsibilities:

- **Actor Ownership** — one-to-one binding via `set_actor()`
- **Goal Management** — parse commands into goals, evaluate achievability
- **Planning** — produces execution steps from beliefs + capabilities
- **Execution** — dispatches steps to CapabilityBus or AgentBus
- **Interrupt/Resume** — checkpoint and continue plans mid-flight

### CapabilityBus

Dispatches synchronous capability calls. Capabilities are objects with `.name` and `.fn(kwargs)`. Multiple providers can register under the same name — the bus selects by highest proficiency.

### AgentBus

Dispatches async agent calls. Agents expose `.agent_type` and `async .handle(kwargs)`. Used for higher-level reasoning or external system integration (OpenClaw, n8n, etc.).

## Execution Modes

### Chain (default)

Steps run strictly in order. Each step's output is stored in `ExecutionState` so later steps can read it via `state.get_data(name)`.

```python
{"execution": "chain", "steps": [{"name": "step1"}, {"name": "step2"}]}
```

### Graph

Steps declare `depends_on: [names]`. Steps run in topological waves — independent steps within a wave run concurrently via `asyncio.gather`.

```python
{
    "execution": "graph",
    "steps": [
        {"name": "check_wallet", "type": "agent"},
        {"name": "check_product", "type": "agent"},
        {"name": "place_order", "type": "agent", "depends_on": ["check_wallet", "check_product"]},
    ]
}
```

## Cognitive Pipeline

```
Command → Parse Intent → Set Goal → Engine.tick() → Plan → Execute → Result
```

The engine (default: `LightweightCognitiveEngine`) builds a `BeliefState` from actor state and runs `DeterministicPlanner` to produce steps. Applications can swap in `LLMPlannerEngine` or a custom `ICognitiveEngine`.

## Package Layout

```
cognitiveos/
├── actor.py              # Actor, Identity, GoalState, BeliefState
├── os.py                 # CognitiveOS runtime
├── interfaces.py         # ICognitiveEngine, ITransitionModel, etc.
├── protocol.py           # ActorProtocol
├── capability_bus.py     # CapabilityBus + CapabilityResult
├── agent_bus.py          # AgentBus + AgentResult
├── execution_state.py    # ExecutionState
├── observation.py        # Rule-based fact extraction
├── exceptions.py         # Exception hierarchy
├── capability_interface.py  # ICapability ABC
├── engine/
│   ├── lightweight_engine.py  # Default ICognitiveEngine
│   ├── llm_planner.py        # LLM-backed ICognitiveEngine
│   ├── planner.py            # PlanningEngine protocol
│   ├── planning_engine.py    # DeterministicPlanner
│   ├── belief_state.py       # BeliefState + Goal + Plan
│   ├── execution.py          # Action, ActionOutcome, ExecutionResult
│   ├── action_executor.py    # ActionExecutor
│   └── pipeline_actor.py     # PipelineActor bookkeeping
├── agents/               # Agent, Provider, AgentRegistry
├── affiliations/         # AffiliationManager, TrustEngine
└── ontology/             # Ontology types and extensions
```

## Architectural Invariants

- One CognitiveOS owns exactly one Actor
- Every actor executes independently
- All cognition is local
- No infrastructure is required
- No global mutable state exists
- All integrations occur through interfaces
- Domain knowledge lives in capabilities, not in the runtime
