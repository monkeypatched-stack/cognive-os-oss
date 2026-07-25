# n8n Integration

CognitiveOS integrates with n8n as an agent provider — an agent calls an n8n webhook, which can orchestrate LLM calls, data transformations, or any n8n workflow.

## Prerequisites

1. n8n running locally (default: `http://localhost:5678`)
2. A workflow with a Webhook trigger node
3. Optionally, a local LLM (e.g. Ollama) behind the workflow

## Agent Implementation

```python
import asyncio
import re
from typing import Any
import httpx

class BlogWriterAgent:
    agent_type = "process_blog"

    def __init__(self, webhook_url: str = "http://localhost:5678/webhook/writeragent",
                 timeout: float = 60.0):
        self.webhook_url = webhook_url
        self.timeout = timeout

    async def handle(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        question = kwargs.get("question", "")

        match = re.search(r"blog\s+(?:post\s+)?(?:about|on)\s+(.+?)[\?\.]?$", question, re.IGNORECASE)
        if not match:
            return {"success": False, "error": "could_not_parse_topic"}
        topic = match.group(1).strip()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.webhook_url, json={"topic": topic})

        if response.status_code >= 400:
            return {"success": False, "error": f"n8n_http_{response.status_code}"}

        data = response.json()
        return {
            "success": data.get("success", False),
            "topic": data.get("topic"),
            "title": data.get("title"),
            "content": data.get("content"),
            "generated_by": data.get("model"),
        }
```

## Wiring into CognitiveOS

```python
from cognitiveos import Actor, CognitiveOS

class SingleAgentStepEngine:
    def __init__(self, agent_type: str):
        self._agent_type = agent_type

    async def tick(self, actor):
        return {
            "plan": {"steps": [
                {"name": self._agent_type, "type": "agent", "description": "write blog post"}
            ]},
        }

actor = Actor(entity_id="alice", actor_type_id="human", goals=["expression"])

os_ = CognitiveOS()
os_.set_actor(actor)
os_.register_agent(BlogWriterAgent())
os_.set_engine(SingleAgentStepEngine("process_blog"))

result = await os_.run("Write a blog post about the future of local-first software")
```

## Chaining n8n Steps

Chain multiple n8n-backed agents using CognitiveOS's step chaining. Step 2 reads step 1's output via `state.get_data("process_blog")`:

```python
class PublishOnlyAgent:
    agent_type = "process_publish"

    async def handle(self, kwargs):
        state = kwargs.get("state")
        written = state.get_data("process_blog")  # reads prior step's output

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "http://localhost:5678/webhook/publishingagent",
                json={"title": written["title"], "content": written["content"]},
            )

        return {"success": True, "slug": response.json()["slug"]}
```

Then register both agents and use a multi-step engine:

```python
class TwoStepChainEngine:
    async def tick(self, actor):
        return {
            "plan": {
                "steps": [
                    {"name": "process_blog", "type": "agent", "description": "write"},
                    {"name": "process_publish", "type": "agent", "description": "publish"},
                ],
            },
        }
```

## Key Points

- n8n agents are async — they call webhooks over HTTP
- The agent reads `kwargs["question"]` for the raw command text
- Step chaining uses `state.get_data(step_name)` to pass data between steps
- The n8n workflow handles the actual LLM call, data processing, or orchestration

## Full Examples

- `examples/n8n_blog_agent.py` — single n8n agent (write blog post)
- `examples/n8n_publish_blog_agent.py` — single n8n agent (publish post)
- `examples/chained_blog_agents.py` — write then publish, chained through state
