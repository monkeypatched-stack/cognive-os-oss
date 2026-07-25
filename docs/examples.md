# Examples

All examples are in the `examples/` directory. Run with:

```bash
pip install -e ".[examples]"
python examples/<example>.py
```

## Standalone

**`examples/standalone.py`** — Zero-dependency demo. Creates an actor, adds capabilities/resources, synthesizes a decision, and runs the full `os.run()` pipeline with the built-in DeterministicPlanner.

```bash
python examples/standalone.py
```

## API Capability

**`examples/api_capability.py`** — Register a capability backed by a real external API (Open-Meteo weather). Shows the minimal capability pattern: object with `.name` and `.fn(kwargs)`.

```bash
python examples/api_capability.py
```

## Agent Capability

**`examples/agent_capability.py`** — Register an agent backed by Wikipedia's API. Shows the difference between capabilities (sync, CapabilityBus) and agents (async, AgentBus), and how to write a custom `ICognitiveEngine` to route agent-type steps.

```bash
python examples/agent_capability.py
```

## Grocery Capability

**`examples/grocery_capability.py`** — Real capability backed by a local HTTP grocery service with authentication. Demonstrates parsing quantities from commands and making authenticated API calls.

```bash
python examples/grocery_capability.py
```

## Grocery Graph Pipeline

**`examples/grocery_graph_pipeline.py`** — Dependency graph execution. Four steps with real HTTP calls running concurrently where possible (check_wallet + check_product → place_order → assign_rider). Shows the `graph` execution mode with `depends_on`.

```bash
python -m examples.grocery_graph_pipeline
```

## OpenClaw Agent

**`examples/openclaw_agent.py`** — Agent backed by the OpenClaw CLI (local agent gateway). Shells out to `openclaw agent --json` to get LLM responses through the running Gateway.

```bash
python examples/openclaw_agent.py
```

## n8n Blog Agent

**`examples/n8n_blog_agent.py`** — Agent backed by an n8n webhook workflow. Calls a real WriterAgent workflow that generates blog content via a local LLM (Ollama).

```bash
python examples/n8n_blog_agent.py
```

## Chained Blog Agents

**`examples/chained_blog_agents.py`** — Two-step chain: write a blog post (via n8n WriterAgent), then publish it (via n8n PublishingAgent). Shows how `state.get_data("process_blog")` passes data between chained steps.

```bash
python -m examples.chained_blog_agents
```

## Summarizer Agent

**`examples/summarizer_agent.py`** — Agent that fetches a published blog post and summarizes it with a local LLM. Demonstrates reading from an external service and calling Ollama directly.

```bash
python examples/summarizer_agent.py
```
