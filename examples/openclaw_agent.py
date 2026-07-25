"""Register an agent backed by OpenClaw — a different integration style
from the rest of examples/: not an HTTP call, a real subprocess CLI
invocation (`openclaw agent ... --json`), same as monkeypatched's own
integration (packages/cerebellum/cerebellum/capabilities/agent/agents.py
:: OpenClawCapability, CLI mode) — cognitiveos/agents/__init__.py's
docstring already names OpenClaw as a provider alongside n8n and NANDA;
this is that, for real.

OpenClaw is a general-purpose local agent gateway (openclaw.ai) — this
machine already has it running as a LaunchAgent (`openclaw status` shows
Gateway reachable, agent "main" bound to the local Ollama gemma3 model).
The CLI shells out to that running Gateway; nothing here talks to an LLM
API directly.

Requires: the `openclaw` CLI installed and its Gateway running
(`openclaw status` to check; `openclaw onboard` if it isn't set up yet).

Run: pip install -e ".[examples]"; python examples/openclaw_agent.py
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
from typing import Any

from cognitiveos import Actor, CognitiveOS


class OpenClawAgent:
    """Real (non-mocked) agent: shells out to the openclaw CLI, which
    talks to the already-running OpenClaw Gateway.
    """

    agent_type = "process_ask"

    def __init__(self, agent_id: str = "main", timeout: float = 120.0) -> None:
        self.agent_id = agent_id
        self.timeout = timeout

    async def handle(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        question = kwargs.get("question", "")

        match = re.search(r"ask\s+(?:openclaw|the assistant)?\s*(.+?)[\?\.]?$", question, re.IGNORECASE)
        message = (match.group(1).strip() if match else question).strip()
        if not message:
            return {"success": False, "error": "could_not_parse_message"}

        if not shutil.which("openclaw"):
            return {"success": False, "error": "openclaw_cli_not_found"}

        try:
            proc = await asyncio.create_subprocess_exec(
                "openclaw", "agent",
                "--agent", self.agent_id,
                "--message", message,
                "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return {"success": False, "error": "openclaw_timeout", "detail": f"no reply within {self.timeout}s"}
        except Exception as exc:
            return {"success": False, "error": "openclaw_subprocess_failed", "detail": str(exc)}

        if proc.returncode != 0:
            return {
                "success": False,
                "error": "openclaw_cli_error",
                "detail": stderr.decode("utf-8", errors="replace").strip(),
            }

        try:
            result = json.loads(stdout.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return {"success": False, "error": "openclaw_bad_json", "detail": stdout.decode()[:300]}

        payloads = result.get("result", {}).get("payloads", [])
        reply = payloads[0].get("text", "") if payloads else ""
        if not reply:
            return {"success": False, "error": "openclaw_empty_reply", "detail": json.dumps(result)[:300]}

        meta = result.get("result", {}).get("meta", {}).get("agentMeta", {})
        return {
            "success": True,
            "message": message,
            "reply": reply,
            "provider": meta.get("provider"),
            "model": meta.get("model"),
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
            "plan": {"steps": [{"name": self._agent_type, "type": "agent", "description": "ask openclaw"}]},
        }


async def main() -> None:
    actor = Actor(entity_id="alice", actor_type_id="human", name="Alice", goals=["discovery"])

    os_ = CognitiveOS()
    os_.set_actor(actor)
    os_.register_agent(OpenClawAgent())
    os_.set_engine(SingleAgentStepEngine("process_ask"))

    result = await os_.run("Ask what is the capital of France")

    print("Parsed intent:", result.intent)
    for sr in result.step_results:
        if sr.status == "success":
            print(f"  {sr.action:20s} -> success")
            print(f"    Message: {sr.output['message']}")
            print(f"    Reply:   {sr.output['reply']}")
            print(f"    Model:   {sr.output['provider']}/{sr.output['model']}")
        else:
            print(f"  {sr.action:20s} -> {sr.status:8s} {sr.output}")
    print("\nOverall success:", result.success)


if __name__ == "__main__":
    asyncio.run(main())
