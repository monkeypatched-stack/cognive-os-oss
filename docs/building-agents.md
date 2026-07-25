# Building Agents

Agents are async units of work dispatched by the `AgentBus`. They handle higher-level reasoning, external system integration, or multi-step workflows.

## Agent Contract

An agent is any object with:

| Member | Type | Description |
|---|---|---|
| `agent_type` | `str` | The plan step name it handles (e.g. `"process_topic"`) |
| `async handle(kwargs)` | `async callable` | Receives `kwargs` including `"question"` and `"state"` |

## Minimal Example

```python
class EchoAgent:
    agent_type = "process_echo"

    async def handle(self, kwargs):
        question = kwargs.get("question", "")
        return {"success": True, "echo": question}
```

## Registration

```python
os = CognitiveOS()
os.register_agent(EchoAgent())
```

## How Dispatch Works

1. A custom `ICognitiveEngine` plans steps with `type: "agent"`
2. The `AgentBus` resolves the agent by `agent_type` name
3. The agent's `async handle(kwargs)` is called
4. The result is stored in `ExecutionState` for later steps to read

## Agent vs Capability

| | Capability | Agent |
|---|---|---|
| Execution | Sync (`.fn()`) | Async (`await .handle()`) |
| Bus | CapabilityBus | AgentBus |
| Step type | `"capability"` (default) | `"agent"` |
| Default planner | Produces these automatically | Never produces these |
| Use case | Local computation, API calls | LLM calls, external systems, workflows |

## Reading Context

```python
async def handle(self, kwargs):
    question = kwargs.get("question", "")    # raw command text
    state = kwargs.get("state")              # ExecutionState

    # Read data from a prior step
    prior = state.get_data("step_name") if state else None
```

## Returning Results

Return a dict. The bus treats `{"success": False, "error": "..."}` as a failure:

```python
async def handle(self, kwargs):
    if bad_condition:
        return {"success": False, "error": "could_not_parse"}
    return {"success": True, "data": "result"}
```

## Custom ICognitiveEngine

The default `DeterministicPlanner` never emits `type: "agent"` steps. To route to agents, provide a custom engine:

```python
class MyEngine:
    async def tick(self, actor):
        return {
            "plan": {
                "steps": [
                    {"name": "process_topic", "type": "agent", "description": "look up topic"},
                ],
            },
        }

os.set_engine(MyEngine())
```

## Chaining Agents

Chain multiple agents using step dependencies and `state.get_data()`:

```python
class MyEngine:
    async def tick(self, actor):
        return {
            "plan": {
                "steps": [
                    {"name": "generate", "type": "agent"},
                    {"name": "publish", "type": "agent", "depends_on": ["generate"]},
                ],
            },
        }
```

Step 2 reads step 1's output via `state.get_data("generate")`.

## AgentRegistry

For more complex setups, use `AgentRegistry` to register agents and providers:

```python
from cognitiveos.agents import Agent, Provider, AgentRegistry

registry = AgentRegistry()

# Register agents directly
agent = Agent(agent_id="writer", capabilities=["write_blog"])
registry.register_agent(agent)

# Register providers (OpenClaw, n8n, etc.)
provider = Provider(provider_id="openclaw", base_url="http://localhost:8080")
provider.register_agent(agent)
registry.register_provider(provider)

# Resolve and execute
result = registry.execute("write_blog", intent=None)
```

## Full Examples

- `examples/agent_capability.py` — Wikipedia agent
- `examples/openclaw_agent.py` — OpenClaw CLI agent
- `examples/n8n_blog_agent.py` — n8n webhook agent
- `examples/summarizer_agent.py` — blog post summarizer agent
- `examples/chained_blog_agents.py` — two-step chained agents
