"""LLMPlannerEngine — a real ICognitiveEngine backed by an actual LLM,
instead of DeterministicPlanner's fact-based forward chaining.

DeterministicPlanner (planning_engine.py) has no procedural/world
knowledge — it groups whatever facts it has by entity and emits one
process_<entity> step per entity. It cannot decompose a goal like "Make
tea" into "boil_water -> add_tea -> pour -> serve"; there is no recipe
knowledge anywhere in a fact-based planner. planner.py's own docstring
already names this: "GOAP/HTN/LLM planners will replace this for
production use." This is that LLM planner, for real.

This is a genuinely different engine, not a patch on the default: it
requires an LLM to be reachable (Ollama by default) and returns an
honest error if one isn't — it does not silently fall back to
DeterministicPlanner. Swap it in per-instance via
CognitiveOS.set_engine(LLMPlannerEngine()); the package-level default
(CognitiveOS()'s built-in _lightweight_engine) is untouched and stays
zero-dependency — set_engine() takes priority over it (see os.py's
run(): `engine = self._engine or self._lightweight_engine`), so once
set, DeterministicPlanner is fully out of the decision path for that
instance.

Uses only the stdlib (urllib.request, json) for the HTTP call — no new
dependency is added to cognitiveos's dependencies=[] to support this.
Ollama itself is an optional *runtime* requirement (like Gateway/service
dependencies in examples/), not a package dependency.
"""
from __future__ import annotations

import asyncio
import json
import re
import urllib.error
import urllib.request
from typing import Any


class LLMPlannerEngine:
    """Asks a local LLM for an ordered plan instead of computing one from
    facts. Implements ICognitiveEngine: async def tick(self, actor) -> dict
    shaped {"plan": {"steps": [...]}}, same contract as
    LightweightCognitiveEngine.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "gemma3:latest",
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def tick(self, actor: Any) -> dict:
        intent = getattr(actor, "_current_intent", None)
        goal_text = (
            getattr(intent, "raw", None)
            or getattr(actor, "_current_goal", None)
            or ""
        )
        if not goal_text:
            return {"success": False, "error": "no_goal_or_command_to_plan_for"}

        prompt = (
            "You are a task planner. Given a goal, output ONLY a JSON array of short "
            "snake_case step names (lowercase, underscores, at most 4 words each) "
            "representing an ordered sequence of concrete actions needed to achieve it. "
            "No explanation, no markdown formatting — just the JSON array.\n\n"
            f"Goal: {goal_text}\n\nOutput:"
        )

        try:
            step_names = await self._generate_plan(prompt)
        except Exception as e:
            return {"success": False, "error": f"llm_planner_failed: {e}"}

        return {
            "success": True,
            "plan": {
                "steps": [
                    {"name": name, "type": "capability", "description": name.replace("_", " ")}
                    for name in step_names
                ],
            },
        }

    async def _generate_plan(self, prompt: str) -> list[str]:
        # urllib is synchronous/blocking; run it off the event loop thread
        # rather than blocking every other coroutine on the LLM's latency.
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._generate_plan_sync, prompt)

    def _generate_plan_sync(self, prompt: str) -> list[str]:
        body = json.dumps({"model": self.model, "prompt": prompt, "stream": False}).encode()
        request = urllib.request.Request(
            f"{self.base_url}/api/generate", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode())
        except urllib.error.URLError as e:
            raise RuntimeError(f"could not reach LLM at {self.base_url}: {e}") from e

        text = data.get("response", "").strip()
        return self._parse_steps(text)

    @staticmethod
    def _parse_steps(text: str) -> list[str]:
        """LLM output is free text, not a guaranteed-valid API response —
        parse defensively rather than assume a clean JSON array.
        """
        fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
        candidate = fenced.group(1) if fenced else text
        if not candidate.strip().startswith("["):
            bracketed = re.search(r"\[.*\]", candidate, re.DOTALL)
            candidate = bracketed.group(0) if bracketed else candidate

        parsed = json.loads(candidate)
        if not isinstance(parsed, list):
            raise ValueError(f"expected a JSON array of step names, model returned: {parsed!r}")

        return [
            re.sub(r"[^a-z0-9_]", "", str(item).strip().lower().replace(" ", "_"))
            for item in parsed
        ]
