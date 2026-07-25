"""n8n_blog_agent.py's main(), wrapped as an HTTP endpoint instead of a
hardcoded script — same setup (register BlogWriterAgent, force the
agent-type step via SingleAgentStepEngine), just with the prompt coming
from the request body instead of being hardcoded.

Run:
    pip install -e ".[examples]"
    uvicorn examples.blog_agent_api:app --port 8836

    curl -X POST http://127.0.0.1:8836/prompt \\
      -H "Content-Type: application/json" \\
      -d '{"prompt": "Write a blog post about the future of local-first software"}'
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from cognitiveos import Actor, CognitiveOS
from examples.n8n_blog_agent import BlogWriterAgent, SingleAgentStepEngine

app = FastAPI(title="cognitiveos blog agent")


class PromptRequest(BaseModel):
    prompt: str


@app.post("/prompt")
async def run_prompt(req: PromptRequest) -> dict:
    actor = Actor(entity_id="alice", actor_type_id="human", name="Alice", goals=["expression"])

    os_ = CognitiveOS()
    os_.set_actor(actor)
    os_.register_agent(BlogWriterAgent())
    os_.set_engine(SingleAgentStepEngine("process_blog"))

    result = await os_.run(req.prompt)

    sr = result.step_results[0] if result.step_results else None
    if sr is not None and sr.status == "success":
        return {
            "success": True,
            "title": sr.output["title"],
            "content": sr.output["content"],
            "generated_by": sr.output["generated_by"],
        }
    return {
        "success": False,
        "error": sr.output if sr is not None else "no_steps_produced",
    }
