# Getting Started

## Installation

```bash
pip install -e .
```

Zero required dependencies. Python >= 3.12.

## Quick Start

```python
import asyncio
from cognitiveos import Actor, CognitiveOS

# 1. Create an actor
actor = Actor(
    entity_id="alice",
    actor_type_id="human",
    name="Alice",
    goals=["wealth", "safety"],
)

# 2. Add capabilities and resources
actor.add_capability("investment", proficiency=0.8)
actor.add_capability("analysis", proficiency=0.7)
actor.add_resource("money", quantity=5000, unit="USD")

# 3. Create the runtime and bind the actor
os = CognitiveOS()
os.set_actor(actor)

# 4. Synthesize a decision
decision = os.synthesize()
print(decision.selected_goal)  # e.g. "wealth"
print(decision.confidence)     # e.g. 0.8
```

## Running a Command

Use `os.run()` to parse a natural language command and execute it through the cognitive pipeline:

```python
async def main():
    result = await os.run("Book me a flight to Berlin")
    print(result.intent.action)      # "book"
    print(result.intent.subject)     # "flight"
    print(result.success)            # True/False
    print(result.step_results)       # per-step outcomes

asyncio.run(main())
```

## What Happens Under the Hood

1. **Parse Intent** — the command is parsed into a `ParsedIntent` (action, subject, target)
2. **Set Goal** — a goal is created on the actor
3. **Plan** — the engine produces execution steps
4. **Execute** — each step is dispatched to a registered capability or agent
5. **Return** — a structured `RunResult` with per-step outcomes

## Observing the World

Use `os.observe()` for declarative statements (not commands):

```python
beliefs = os.observe("There is a red ball on the table")
# beliefs: [BeliefState(subject="ball", attribute="color", value="red"),
#           BeliefState(subject="ball", attribute="location", value="table")]
```

## Next Steps

- [Architecture Guide](architecture.md) — how CognitiveOS is structured
- [Building Capabilities](building-capabilities.md) — add custom capabilities
- [Building Agents](building-agents.md) — add custom agents
- [Examples](examples.md) — runnable examples for every integration pattern
