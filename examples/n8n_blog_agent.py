"""Register an agent backed by a real n8n workflow — n8n as the "provider"
cognitiveos/agents/__init__.py's docstring already names (OpenClaw, n8n,
NANDA), demonstrated for real this time.

The "MonkeyBrain — WriterAgent" n8n workflow (webhook path /writeragent)
was, like the email-notifications workflow before it, a stub: its Code
node just did `value * 2` — no actual writing. Fixed via the n8n API the
same way: Webhook -> Code -> Respond stays the shape, but the Code node
now calls a real local LLM (Ollama, http://127.0.0.1:11434, model
gemma3:latest — already pulled on this machine, no API key/billing
needed, unlike the Anthropic key in monkeypatched's .env which is real
but out of credits) and returns real generated content, not a placeholder.

This mirrors examples/agent_capability.py's shape (an agent wraps an
external system's async call), swapping "call Wikipedia directly" for
"call an n8n webhook, which itself calls an LLM" — the same AgentBus
contract either way: .agent_type + async .handle(kwargs).

Requires n8n running locally (the "MonkeyBrain — WriterAgent" workflow
active, webhook at http://localhost:5678/webhook/writeragent) and Ollama
running locally with a pulled model (`ollama pull gemma3` if needed).

Run: pip install -e ".[examples]"; python examples/n8n_blog_agent.py
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from cognitiveos import Actor, CognitiveOS


class BlogWriterAgent:
    """Real (non-mocked) agent: generates a blog post via the n8n
    WriterAgent webhook, which itself calls a local LLM.
    """

    agent_type = "process_blog"  # AgentBus registers agents under this key

    def __init__(self, webhook_url: str = "http://localhost:5678/webhook/writeragent", timeout: float = 60.0) -> None:
        self.webhook_url = webhook_url
        self.timeout = timeout

    async def handle(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        question = kwargs.get("question", "")

        match = re.search(r"blog\s+(?:post\s+)?(?:about|on)\s+(.+?)[\?\.]?$", question, re.IGNORECASE)
        if not match:
            return {"success": False, "error": "could_not_parse_topic"}
        topic = match.group(1).strip()

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.webhook_url, json={"topic": topic})
        except httpx.HTTPError as exc:
            return {"success": False, "error": "n8n_unreachable", "detail": str(exc)}

        if response.status_code >= 400:
            return {"success": False, "error": f"n8n_http_{response.status_code}", "detail": response.text}

        data = response.json()
        if not data.get("success"):
            return {"success": False, "error": data.get("error", "generation_failed")}

        return {
            "success": True,
            "topic": data["topic"],
            "title": data["title"],
            "content": data["content"],
            "generated_by": data.get("model"),
        }


class SingleAgentStepEngine:
    """Minimal ICognitiveEngine that plans exactly one agent-type step —
    same helper as examples/agent_capability.py, see that file's docstring
    for why the default planner never emits agent steps on its own.
    """

    def __init__(self, agent_type: str) -> None:
        self._agent_type = agent_type

    async def tick(self, actor: Any) -> dict:
        return {
            "plan": {"steps": [{"name": self._agent_type, "type": "agent", "description": "write blog post"}]},
        }


async def main() -> None:
    actor = Actor(entity_id="alice", actor_type_id="human", name="Alice", goals=["expression"])

    os_ = CognitiveOS()
    os_.set_actor(actor)
    os_.register_agent(BlogWriterAgent())
    os_.set_engine(SingleAgentStepEngine("process_blog"))

    result = await os_.run("Write a blog post about the future of local-first software")

    print("Parsed intent:", result.intent)
    print("Plan steps:   ", [s["name"] for s in result.steps])
    for sr in result.step_results:
        if sr.status == "success":
            print(f"  {sr.action:20s} -> success")
            print(f"    Title:   {sr.output['title']}")
            print(f"    Content: {sr.output['content'][:200]}...")
            print(f"    Model:   {sr.output['generated_by']}")
        else:
            print(f"  {sr.action:20s} -> {sr.status:8s} {sr.output}")
    print("\nOverall success:", result.success)


if __name__ == "__main__":
    asyncio.run(main())
