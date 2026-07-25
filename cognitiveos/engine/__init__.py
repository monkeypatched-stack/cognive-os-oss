"""cognitiveos.engine — real (non-mocked) cognitive engines.

Ported from monkeypatched's kernel/pipeline "light tier": pure stdlib
belief/plan/execution data model and a genuine forward-chaining planner
(DeterministicPlanner), as opposed to the kernel's heavy BeliefFormation ->
ComparisonIntegratedPolicy machinery (prediction/comparison/learning stages),
which requires a fully booted Kernel and external persistence and was not
ported — it would defeat this package's zero-dependency, in-memory design.

LightweightCognitiveEngine (DeterministicPlanner-backed) is
CognitiveOS()'s built-in default — always available, no setup. It has no
procedural/world knowledge, though: it can't decompose "make tea" into
"boil_water -> add_tea -> pour -> serve", only reason about facts it's
been given. LLMPlannerEngine is the alternative for that: a real,
optional engine backed by an actual LLM (Ollama by default), swapped in
per-instance via CognitiveOS.set_engine() — it requires an LLM
reachable at runtime, but adds no package dependency (stdlib
urllib.request only) and the zero-dependency default is untouched
unless you explicitly opt into it.
"""
from cognitiveos.engine.belief_state import BeliefState, Goal, Fact, Plan, PlanStep
from cognitiveos.engine.pipeline_actor import PipelineActor
from cognitiveos.engine.execution import Action, ActionOutcome, ExecutionResult
from cognitiveos.engine.planner import PlanningEngine
from cognitiveos.engine.planning_engine import DeterministicPlanner
from cognitiveos.engine.action_executor import ActionExecutor
from cognitiveos.engine.lightweight_engine import LightweightCognitiveEngine
from cognitiveos.engine.llm_planner import LLMPlannerEngine

__all__ = [
    "BeliefState", "Goal", "Fact", "Plan", "PlanStep",
    "PipelineActor",
    "Action", "ActionOutcome", "ExecutionResult",
    "PlanningEngine", "DeterministicPlanner",
    "ActionExecutor",
    "LightweightCognitiveEngine",
    "LLMPlannerEngine",
]
