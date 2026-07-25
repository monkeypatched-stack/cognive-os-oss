# OpenClaw Integration

OpenClaw is a general-purpose local agent gateway. CognitiveOS integrates with it as an agent provider — the agent shells out to the `openclaw` CLI, which talks to a running OpenClaw Gateway.

## Prerequisites

1. Install the `openclaw` CLI
2. Start the Gateway: `openclaw onboard` (first time) then `openclaw status` (verify)
3. Ensure a model is bound: `openclaw agent --agent main --message "hello"` should respond

## Agent Implementation

```python
import asyncio
import json
import re
import shutil
from typing import Any

class OpenClawAgent:
    agent_type = "process_ask"

    def __init__(self, agent_id: str = "main", timeout: float = 120.0):
        self.agent_id = agent_id
        self.timeout = timeout

    async def handle(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        question = kwargs.get("question", "")

        # Parse the message from the command
        match = re.search(r"ask\s+(?:openclaw|the assistant)?\s*(.+?)[\?\.]?$", question, re.IGNORECASE)
        message = (match.group(1).strip() if match else question).strip()
        if not message:
            return {"success": False, "error": "could_not_parse_message"}

        if not shutil.which("openclaw"):
            return {"success": False, "error": "openclaw_cli_not_found"}

        # Shell out to openclaw CLI
        proc = await asyncio.create_subprocess_exec(
            "openclaw", "agent",
            "--agent", self.agent_id,
            "--message", message,
            "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)

        if proc.returncode != 0:
            return {"success": False, "error": "openclaw_cli_error",
                    "detail": stderr.decode("utf-8", errors="replace").strip()}

        result = json.loads(stdout.decode("utf-8", errors="replace"))
        payloads = result.get("result", {}).get("payloads", [])
        reply = payloads[0].get("text", "") if payloads else ""

        return {
            "success": bool(reply),
            "message": message,
            "reply": reply,
            "provider": result.get("result", {}).get("meta", {}).get("agentMeta", {}).get("provider"),
            "model": result.get("result", {}).get("meta", {}).get("agentMeta", {}).get("model"),
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
                {"name": self._agent_type, "type": "agent", "description": "ask openclaw"}
            ]},
        }

actor = Actor(entity_id="alice", actor_type_id="human", goals=["discovery"])

os_ = CognitiveOS()
os_.set_actor(actor)
os_.register_agent(OpenClawAgent())
os_.set_engine(SingleAgentStepEngine("process_ask"))

result = await os_.run("Ask what is the capital of France")
```

## Key Points

- The default planner (`DeterministicPlanner`) never emits `type: "agent"` steps — you need a custom `ICognitiveEngine` to route to agents
- OpenClaw agents are async (`async def handle`), unlike capabilities which are sync (`.fn()`)
- The agent reads `kwargs["question"]` (the raw command) and `kwargs["state"]` (ExecutionState)
- System events can be sent via `openclaw system event --text "..." --mode now`

## Full Example

See `examples/openclaw_agent.py` for a complete working integration.
