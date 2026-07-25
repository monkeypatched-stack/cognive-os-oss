"""How to register an *agent* — a different integration point from
examples/api_capability.py's capability, worth understanding as distinct:

    CapabilityBus (register_capability)      AgentBus (register_agent)
    ------------------------------------     ------------------------------
    object needs: .name, .fn(kwargs)         object needs: .agent_type,
                  (sync)                                   async .handle(kwargs)
    dispatched when a plan step has          dispatched when a plan step has
    type == "capability" (the default)       type == "agent"
    driven by cognitiveos.engine's real      NEVER produced by the default
    DeterministicPlanner out of the box      planner — DeterministicPlanner
                                              only ever emits "capability"
                                              steps (see planning_engine.py's
                                              _generate_steps). Something has
                                              to explicitly ask for an agent
                                              step: either your own
                                              ICognitiveEngine (via
                                              os.set_engine()), or a future
                                              planner that reasons about
                                              capability vs. agent per step.

So to show register_agent() actually dispatching through the real
os.run() pipeline, this file also defines a tiny custom ICognitiveEngine
that plans a single agent-type step — just enough to demonstrate the
path, not a real planner. In your own code you'd only need this if you're
writing your own engine; if you're just adding a capability, see
api_capability.py instead.

Run: pip install -e ".[examples]"; python examples/agent_capability.py
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from cognitiveos import Actor, CognitiveOS


class WikipediaAgent:
    """Real (non-mocked) agent: fetches a live Wikipedia summary.

    Agents are async (unlike capabilities' sync .fn) and receive whatever
    kwargs CognitiveOS.run() passes for agent-type steps — here,
    `question` (the raw command) and `state` (the ExecutionState).
    """

    agent_type = "process_topic"  # AgentBus registers agents under this key

    async def handle(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        question = kwargs.get("question", "")

        match = re.search(r"about\s+(?:the\s+)?(.+?)[\?\.]?$", question, re.IGNORECASE)
        if not match:
            return {"success": False, "error": "could_not_parse_topic"}
        topic = match.group(1).strip().replace(" ", "_")

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"https://en.wikipedia.org/api/rest_v1/page/summary/{topic}",
                    # Wikimedia's API rejects requests without a descriptive
                    # User-Agent (https://w.wiki/4wJS) — httpx's default gets a 403.
                    headers={"User-Agent": "cognitiveos-example/0.1 (https://github.com/)"},
                )
        except httpx.HTTPError as exc:
            return {"success": False, "error": "wikipedia_unreachable", "detail": str(exc)}

        if response.status_code == 404:
            return {"success": False, "error": f"topic_not_found: {topic}"}
        if response.status_code >= 400:
            return {"success": False, "error": f"wikipedia_http_{response.status_code}"}

        data = response.json()
        return {
            "success": True,
            "title": data.get("title"),
            "extract": data.get("extract"),
            "url": data.get("content_urls", {}).get("desktop", {}).get("page"),
        }


class SingleAgentStepEngine:
    """Minimal ICognitiveEngine that plans exactly one agent-type step.

    Not a real planner — cognitiveos.engine.DeterministicPlanner (the
    default) never emits agent steps on its own. This exists purely to
    exercise the AgentBus dispatch path in os.run() for this example.
    """

    def __init__(self, agent_type: str) -> None:
        self._agent_type = agent_type

    async def tick(self, actor: Any) -> dict:
        return {
            "plan": {
                "steps": [
                    {"name": self._agent_type, "type": "agent", "description": "look up topic"},
                ],
            },
        }


async def main() -> None:
    actor = Actor(entity_id="alice", actor_type_id="human", name="Alice", goals=["discovery"])

    os_ = CognitiveOS()
    os_.set_actor(actor)
    os_.register_agent(WikipediaAgent())
    os_.set_engine(SingleAgentStepEngine("process_topic"))

    result = await os_.run("Tell me about the Eiffel Tower")

    print("Parsed intent:", result.intent)
    print("Plan steps:   ", [s["name"] for s in result.steps])
    for sr in result.step_results:
        print(f"  {sr.action:20s} -> {sr.status:8s} {sr.output}")
    print("\nOverall success:", result.success)


if __name__ == "__main__":
    asyncio.run(main())
