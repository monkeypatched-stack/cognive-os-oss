# Monkeypatched - CognitiveOS 

> **The cognitive runtime for autonomous software.**

CognitiveOS is the cognitive runtime that lets your existing capabilities, OpenClaw agents, and n8n workflows reason, plan, and execute together.

CognitiveOS gives software the ability to **observe**, **reason**, **plan**, and **execute**.

Unlike workflow engines and agent orchestrators, CognitiveOS doesn't tell your software **how** to execute—it decides **what should happen next**.

Use it to orchestrate:

- 🐍 Native Python capabilities
- 🤖 OpenClaw agents
- 🔄 n8n workflows
- 🌐 REST APIs
- 🦾 Robots
- 📦 Local tools and services

No distributed runtime.

No databases.

No message brokers.

No vendor lock-in.

Just cognition.

---

# Why CognitiveOS?

Modern software already has tools.

You have:

- APIs
- Python libraries
- OpenClaw agents
- n8n workflows
- robots
- automation services

The missing piece isn't another workflow engine.

The missing piece is **decision making**.

CognitiveOS acts as the cognitive layer above your existing ecosystem.

```
                          CognitiveOS
                               │
                 Observe → Believe → Plan
                               │
                     Capability Selection
                               │
      ┌─────────────┬─────────────┬─────────────┬─────────────┐
      ▼             ▼             ▼             ▼
   Python       OpenClaw         n8n         REST APIs
```

Your tools already know **how** to perform work.

CognitiveOS decides **which tool should execute next.**

---

# The Cognitive Loop

Every execution follows the same reasoning pipeline.

```
Observe
    │
    ▼
Believe
    │
    ▼
Goal
    │
    ▼
Plan
    │
    ▼
Capability Selection
    │
    ▼
Execute
```

Everything happens locally.

No cloud services.

No shared memory.

No distributed runtime.

---

# Quick Example

```python
from cognitiveos import Actor, CognitiveOS

actor = Actor("alice")

os = CognitiveOS()
os.set_actor(actor)

await os.run(
    "Book me a flight to Berlin next Friday"
)
```

That's it.

---

# One Runtime. Unlimited Capabilities.

Register anything as a capability.

```python
os.register_capability(SQLCapability())

os.register_capability(GitHubCapability())

os.register_capability(EmailCapability())

os.register_capability(RobotCapability())

os.register_capability(OpenClawCapability())

os.register_capability(N8NCapability())
```

The planner decides which capability should execute.

Your application never needs to hardcode execution order.

---

# OpenClaw Integration

Already using OpenClaw?

Register existing OpenClaw agents directly.

```python
os.register_agent(
    OpenClawAgent(...)
)
```

CognitiveOS treats OpenClaw agents as cognitive capabilities.

---

# n8n Integration

Already have automation workflows?

Reuse them.

```python
os.register_agent(
    N8NWorkflow(...)
)
```

CognitiveOS decides **when** a workflow should run.

n8n executes it.

---

# Native Python

Not everything needs another framework.

Your existing Python code is a capability.

```python
class WeatherCapability(Capability):

    async def execute(self, request):
        ...
```

Register it.

```python
os.register_capability(
    WeatherCapability()
)
```

Done.

---

# Real Planning

CognitiveOS doesn't execute static workflows.

It builds plans.

```
User Goal

      │

      ▼

Planner

      │

      ▼

Capability Selection

      │

      ▼

Execution
```

Planning is deterministic by default.

Need procedural knowledge?

Swap in an LLM planner.

```python
os.set_engine(
    LLMPlannerEngine(...)
)
```

LLMs are optional—not required.

---

# Architecture

```
                    CognitiveOS

Observe
      │
      ▼
Believe
      │
      ▼
Goals
      │
      ▼
Planner
      │
      ▼
Capability Bus
      │
      ├────────────► Python
      ├────────────► OpenClaw
      ├────────────► n8n
      ├────────────► REST APIs
      ├────────────► Robots
      └────────────► Local Tools
```

One runtime.

One actor.

One execution context.

---

# Features

| Feature | Included |
|----------|-----------|
| Observe | ✅ |
| Belief Management | ✅ |
| Goal Management | ✅ |
| Planning Engine | ✅ |
| Deterministic Planning | ✅ |
| Optional LLM Planning | ✅ |
| Capability Bus | ✅ |
| Agent Bus | ✅ |
| OpenClaw Integration | ✅ |
| n8n Integration | ✅ |
| Native Python Capabilities | ✅ |
| REST API Integration | ✅ |
| Interrupt / Resume | ✅ |
| Multi-step Planning | ✅ |
| Multiple Independent Actors | ✅ |
| Zero Dependencies | ✅ |

---

# Simple by Design

CognitiveOS intentionally focuses on **local cognition**.

It does **not** include platform concerns.

- No authentication
- No authorization
- No policy engine
- No distributed runtime
- No shared world model
- No distributed memory
- No databases
- No message brokers
- No infrastructure requirements

Bring your own infrastructure.

Bring your own tools.

Bring your own capabilities.

CognitiveOS supplies the cognition.

---

# Multiple Actors

Every runtime owns exactly one actor.

```python
alice = CognitiveOS()

bob = CognitiveOS()

warehouse = CognitiveOS()
```

Actors never share memory.

Applications coordinate them if desired.

---

# Perfect For

- Autonomous applications
- Robotics
- AI assistants
- Workflow automation
- Local AI agents
- Edge computing
- Simulations
- CLI tools
- Game AI
- Research

---

# Philosophy

Most AI frameworks help you build workflows.

CognitiveOS helps software make decisions.

Instead of building another orchestration platform, CognitiveOS focuses on a single question:

> **Given everything I know right now, what should happen next?**

Once that decision is made, execution is delegated to the most appropriate capability—whether that's a Python function, an OpenClaw agent, an n8n workflow, a robot, or an external API.

CognitiveOS doesn't replace your tools.

**It gives them cognition.**

---

# Installation

```bash
pip install cognitiveos
```

---

# Documentation

- [Getting Started](docs/getting-started.md) — install, quick start, first steps
- [Architecture Guide](docs/architecture.md) — design principles, components, execution modes
- [Examples](docs/examples.md) — runnable examples for every integration pattern
- [API Reference](docs/api-reference.md) — types, interfaces, exceptions
- [Building Capabilities](docs/building-capabilities.md) — add custom capabilities
- [Building Agents](docs/building-agents.md) — add custom agents
- [OpenClaw Integration](docs/openclaw-integration.md) — agent backed by OpenClaw CLI
- [n8n Integration](docs/n8n-integration.md) — agent backed by n8n workflows
- [Contributing](docs/contributing.md) — development setup, code style, submitting changes

# Note: This is the opensource version 

---

# License

Apache License 2.0
