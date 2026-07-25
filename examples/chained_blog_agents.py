"""Write and publish a blog post as two genuinely separate, chained plan
steps — the real version of what n8n_publish_blog_agent.py's docstring
said wasn't possible yet:

    "cognitiveos's run() dispatches each plan step independently — there's
    currently no mechanism for one step's output to flow into the next
    step's input... modeling 'publish a blog about X' as one real
    pipeline is honest about that gap rather than papering over it."

That gap is closed now (see os.py's run(): state.set_data()/get_data()).
PublishOnlyAgent below doesn't call the WriterAgent webhook at all — it
reads the writer step's title/content straight out of state, which
run()'s "chain" execution mode (the default) populated after step 1
finished. Two real n8n calls, two real plan steps, real data flowing
between them through cognitiveos's own core, not through one agent
internally doing both.

Requires the same services as n8n_publish_blog_agent.py: n8n (WriterAgent
+ PublishingAgent workflows active), Ollama, and blog_platform_service.py
running on port 8835.

Run: pip install -e ".[examples]"; python -m examples.chained_blog_agents

(module invocation, not `python examples/chained_blog_agents.py` — this
file cross-imports another examples/ module via an absolute
`examples.n8n_blog_agent` import, which only resolves when `examples` is
on sys.path as a package, i.e. run from the repo root as `-m`.)
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from cognitiveos import Actor, CognitiveOS
from examples.n8n_blog_agent import BlogWriterAgent


class PublishOnlyAgent:
    """Real (non-mocked) agent: publishes whatever the *prior* plan step
    (process_blog) produced — reads it from state, never generates its
    own content.
    """

    agent_type = "process_publish"

    def __init__(
        self,
        publisher_webhook: str = "http://localhost:5678/webhook/publishingagent",
        author: str = "alice",
        timeout: float = 30.0,
    ) -> None:
        self.publisher_webhook = publisher_webhook
        self.author = author
        self.timeout = timeout

    async def handle(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        state = kwargs.get("state")
        written = state.get_data("process_blog") if state is not None else None
        if not written or not written.get("success", True) or "title" not in written:
            return {"success": False, "error": "no_prior_blog_step_output"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.publisher_webhook,
                    json={"title": written["title"], "content": written["content"], "author": self.author},
                )
        except httpx.HTTPError as exc:
            return {"success": False, "error": "publisher_unreachable", "detail": str(exc)}

        if response.status_code >= 400:
            return {"success": False, "error": f"publisher_http_{response.status_code}"}

        published = response.json()
        if not published.get("success"):
            return {"success": False, "error": published.get("error", "publish_failed")}

        return {
            "success": True,
            "title": written["title"],
            "slug": published["slug"],
            "url": published["url"],
            "published_at": published["published_at"],
        }


class TwoStepChainEngine:
    """Plans process_blog then process_publish, in that order — plan
    execution defaults to "chain" (sequential, in order), which is
    exactly what makes step 2 able to read step 1's output.
    """

    async def tick(self, actor: Any) -> dict:
        return {
            "plan": {
                "steps": [
                    {"name": "process_blog", "type": "agent", "description": "write blog post"},
                    {"name": "process_publish", "type": "agent", "description": "publish it"},
                ],
            },
        }


async def main() -> None:
    actor = Actor(entity_id="alice", actor_type_id="human", name="Alice", goals=["expression"])

    os_ = CognitiveOS()
    os_.set_actor(actor)
    os_.register_agent(BlogWriterAgent())
    os_.register_agent(PublishOnlyAgent())
    os_.set_engine(TwoStepChainEngine())

    result = await os_.run("Write a blog post about the future of local-first software")

    print("Parsed intent:", result.intent)
    for sr in result.step_results:
        if sr.status == "success":
            print(f"  {sr.action:20s} -> success")
            if sr.action == "process_blog":
                print(f"    Title:   {sr.output['title']}")
            else:
                print(f"    Published: {sr.output['url']}")
        else:
            print(f"  {sr.action:20s} -> {sr.status:8s} {sr.output}")
    print("\nOverall success:", result.success)


if __name__ == "__main__":
    asyncio.run(main())
