"""Publish a blog post — chains two real n8n agents behind one cognitiveos
agent, and lands the result in a real, independently-verifiable service.

Same starting point as n8n_blog_agent.py: "MonkeyBrain — PublishingAgent"
was a stub (its Code node just echoed back whatever `message` you sent
it). Fixed via the n8n API the same way — Webhook -> Code -> Respond
stays the shape, but the Code node now calls a real local blog platform
(examples/blog_platform_service.py, FastAPI + MongoDB, needs to be
running: `uvicorn examples.blog_platform_service:app --port 8835`) that
actually persists the post and hands back a real slug/URL.

Why one agent calls two n8n webhooks instead of two plan steps: cognitiveos's
run() dispatches each plan step independently — there's currently no
mechanism for one step's output to flow into the next step's input (see
os.py's run(): every agent/capability step gets the same static
ExecutionState, nothing writes generated content into it for a later step
to read). So "publish a blog about X" is modeled as what it actually is
end-to-end — one real pipeline (write, then publish) — rather than two
disconnected steps that would need something to manually wire together.
If you want write and publish as visibly separate steps, that's a real
gap in run()'s step-chaining to close, not something to fake here.

Requires: n8n running (WriterAgent + PublishingAgent workflows active),
Ollama running (see n8n_blog_agent.py), and blog_platform_service.py
running on port 8835.

Run: pip install -e ".[examples]"; python examples/n8n_publish_blog_agent.py
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from cognitiveos import Actor, CognitiveOS


class PublishBlogAgent:
    """Real (non-mocked) agent: writes a post via n8n's WriterAgent
    webhook, then publishes it via n8n's PublishingAgent webhook.
    """

    agent_type = "process_publish_blog"

    def __init__(
        self,
        writer_webhook: str = "http://localhost:5678/webhook/writeragent",
        publisher_webhook: str = "http://localhost:5678/webhook/publishingagent",
        author: str = "alice",
        timeout: float = 60.0,
    ) -> None:
        self.writer_webhook = writer_webhook
        self.publisher_webhook = publisher_webhook
        self.author = author
        self.timeout = timeout

    async def handle(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        question = kwargs.get("question", "")

        match = re.search(r"blog\s+(?:post\s+)?(?:about|on)\s+(.+?)[\?\.]?$", question, re.IGNORECASE)
        if not match:
            return {"success": False, "error": "could_not_parse_topic"}
        topic = match.group(1).strip()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                write_response = await client.post(self.writer_webhook, json={"topic": topic})
            except httpx.HTTPError as exc:
                return {"success": False, "error": "writer_unreachable", "detail": str(exc)}

            if write_response.status_code >= 400:
                return {"success": False, "error": f"writer_http_{write_response.status_code}"}
            written = write_response.json()
            if not written.get("success"):
                return {"success": False, "error": written.get("error", "write_failed")}

            try:
                publish_response = await client.post(
                    self.publisher_webhook,
                    json={"title": written["title"], "content": written["content"], "author": self.author},
                )
            except httpx.HTTPError as exc:
                return {"success": False, "error": "publisher_unreachable", "detail": str(exc)}

            if publish_response.status_code >= 400:
                return {"success": False, "error": f"publisher_http_{publish_response.status_code}"}
            published = publish_response.json()
            if not published.get("success"):
                return {"success": False, "error": published.get("error", "publish_failed")}

        return {
            "success": True,
            "topic": topic,
            "title": written["title"],
            "content": written["content"],
            "slug": published["slug"],
            "url": published["url"],
            "published_at": published["published_at"],
        }


class SingleAgentStepEngine:
    """Minimal ICognitiveEngine that plans exactly one agent-type step —
    same helper as examples/agent_capability.py; see that file for why
    the default planner never emits agent steps on its own.
    """

    def __init__(self, agent_type: str) -> None:
        self._agent_type = agent_type

    async def tick(self, actor: Any) -> dict:
        return {
            "plan": {"steps": [{"name": self._agent_type, "type": "agent", "description": "write and publish blog post"}]},
        }


async def main() -> None:
    actor = Actor(entity_id="alice", actor_type_id="human", name="Alice", goals=["expression"])

    os_ = CognitiveOS()
    os_.set_actor(actor)
    os_.register_agent(PublishBlogAgent())
    os_.set_engine(SingleAgentStepEngine("process_publish_blog"))

    result = await os_.run("Publish a blog post about the future of local-first software")

    print("Parsed intent:", result.intent)
    for sr in result.step_results:
        if sr.status == "success":
            print(f"  {sr.action:20s} -> success")
            print(f"    Title:     {sr.output['title']}")
            print(f"    Published: {sr.output['url']}")
            print(f"    At:        {sr.output['published_at']}")
        else:
            print(f"  {sr.action:20s} -> {sr.status:8s} {sr.output}")
    print("\nOverall success:", result.success)


if __name__ == "__main__":
    asyncio.run(main())
