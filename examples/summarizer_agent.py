"""A summarizer agent — fetches a real published post from
blog_platform_service and genuinely summarizes it with a local LLM
(Ollama, no API key/billing). Direct-call style, like
agent_capability.py's WikipediaAgent, not routed through n8n: a single
local HTTP call doesn't need a workflow engine in front of it.

Ties together the rest of examples/: publish a post with
n8n_publish_blog_agent.py, then summarize it here by title.

Requires: Ollama running locally (model gemma3, see n8n_blog_agent.py)
and blog_platform_service.py running on port 8835 with at least one
published post (run n8n_publish_blog_agent.py first if you haven't).

Run: pip install -e ".[examples]"; python examples/summarizer_agent.py
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from cognitiveos import Actor, CognitiveOS


class SummarizerAgent:
    """Real (non-mocked) agent: looks up a published post by title match,
    fetches its full content, and summarizes it with a local LLM.
    """

    agent_type = "process_summary"

    def __init__(
        self,
        blog_base_url: str = "http://127.0.0.1:8835",
        ollama_url: str = "http://127.0.0.1:11434/api/generate",
        model: str = "gemma3:latest",
        timeout: float = 60.0,
    ) -> None:
        self.blog_base_url = blog_base_url.rstrip("/")
        self.ollama_url = ollama_url
        self.model = model
        self.timeout = timeout

    async def handle(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        question = kwargs.get("question", "")

        match = re.search(r"summar\w*\s+(?:the\s+)?(?:blog\s+post\s+)?(?:about\s+)?(.+?)[\?\.]?$", question, re.IGNORECASE)
        if not match:
            return {"success": False, "error": "could_not_parse_target"}
        query = match.group(1).strip().lower()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                listing = await client.get(f"{self.blog_base_url}/posts")
            except httpx.HTTPError as exc:
                return {"success": False, "error": "blog_service_unreachable", "detail": str(exc)}

            if listing.status_code >= 400:
                return {"success": False, "error": f"blog_service_http_{listing.status_code}"}

            posts = listing.json().get("results", [])
            matched = next((p for p in posts if query in p["title"].lower()), None)
            if matched is None:
                return {"success": False, "error": f"no_post_matching: {query}"}

            post_response = await client.get(f"{self.blog_base_url}/posts/{matched['slug']}")
            if post_response.status_code >= 400:
                return {"success": False, "error": f"post_fetch_http_{post_response.status_code}"}
            post = post_response.json()

            prompt = f"Summarize the following blog post in 2-3 sentences:\n\n{post['content']}"
            try:
                gen_response = await client.post(
                    self.ollama_url,
                    json={"model": self.model, "prompt": prompt, "stream": False},
                )
            except httpx.HTTPError as exc:
                return {"success": False, "error": "ollama_unreachable", "detail": str(exc)}

            if gen_response.status_code >= 400:
                return {"success": False, "error": f"ollama_http_{gen_response.status_code}"}

            summary = gen_response.json().get("response", "").strip()
            if not summary:
                return {"success": False, "error": "empty_summary"}

        return {
            "success": True,
            "slug": matched["slug"],
            "title": post["title"],
            "summary": summary,
            "original_length": len(post["content"]),
            "summary_length": len(summary),
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
            "plan": {"steps": [{"name": self._agent_type, "type": "agent", "description": "summarize"}]},
        }


async def main() -> None:
    actor = Actor(entity_id="alice", actor_type_id="human", name="Alice", goals=["discovery"])

    os_ = CognitiveOS()
    os_.set_actor(actor)
    os_.register_agent(SummarizerAgent())
    os_.set_engine(SingleAgentStepEngine("process_summary"))

    result = await os_.run("Summarize the blog post about local-first software")

    print("Parsed intent:", result.intent)
    for sr in result.step_results:
        if sr.status == "success":
            print(f"  {sr.action:20s} -> success")
            print(f"    Title:   {sr.output['title']}")
            print(f"    Summary: {sr.output['summary']}")
            print(f"    {sr.output['original_length']} chars -> {sr.output['summary_length']} chars")
        else:
            print(f"  {sr.action:20s} -> {sr.status:8s} {sr.output}")
    print("\nOverall success:", result.success)


if __name__ == "__main__":
    asyncio.run(main())
