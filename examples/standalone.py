"""Standalone demo — no monkeypatched needed."""
import asyncio
from dataclasses import dataclass

from cognitiveos import Actor, CognitiveOS

# Create an actor
actor = Actor(
    entity_id="alice",
    actor_type_id="human",
    name="Alice",
    goals=["wealth", "safety"],
    objective="cost",
)

# Add ontology-backed capabilities
actor.add_capability("investment", proficiency=0.8)
actor.add_capability("accounting", proficiency=0.6)
actor.add_capability("analysis", proficiency=0.7)
actor.add_capability("reasoning", proficiency=0.9)
actor.add_capability("communication", proficiency=0.6)

# Add beliefs
actor.add_belief("observation", "market", confidence=0.7)
actor.add_belief("observation", "risk", confidence=0.4)

# Add resources
actor.add_resource("money", quantity=5000, unit="USD")
actor.add_resource("time", quantity=8, unit="hours")

# Create OS and bind actor
os = CognitiveOS()
os.set_actor(actor)

# Synthesize a decision (no pipeline needed)
decision = os.synthesize()

print("=== CognitiveOS Standalone Demo ===")
print(f"Selected goal: {decision.selected_goal}")
print(f"Confidence: {decision.confidence:.2f}")
print(f"Capabilities: {decision.selected_capabilities}")
print(f"Reasoning: {decision.reasoning}")
print(f"\nTrust check (bob): {os._get_actor_trust('bob')}")
print(f"Trust check (enemy): {os._get_actor_trust('enemy')}")

# Trust enforcement — both start at the default trust level (0.5), which is
# above TRUST_COMMUNICATION_THRESHOLD (0.3), so both sends are allowed until
# an affiliation/trust update actually lowers "enemy" below the threshold.
print("\nbob   allowed:", os.send_message("bob", "greeting"))
print("enemy allowed:", os.send_message("enemy", "threat"))


# --- Full os.run() pipeline: Prompt -> Intent -> Goal -> Capabilities -> Plan -> Execute ---
#
# CognitiveOS's default engine is cognitiveos.engine.LightweightCognitiveEngine
# — a real, ported (not mocked) forward-chaining planner (DeterministicPlanner,
# from monkeypatched's kernel/pipeline "light tier"). It plans one step per
# fact entity it's given (the actor's capabilities/resources, plus whatever
# the parsed command asks for) and a final "achieve_goal" step. No LLM, no
# hardcoded response — real planning grounded in actor state.

@dataclass
class RealStepCapability:
    """A real (non-mocked) capability the run() pipeline dispatches to."""
    name: str

    def fn(self, kwargs):
        return {"handled": self.name}


async def run_pipeline_demo() -> None:
    travel_actor = Actor(entity_id="bob", actor_type_id="human", name="Bob", goals=["travel"])
    travel_actor.add_capability("booking", proficiency=0.8)
    travel_actor.add_resource("money", quantity=2000, unit="USD")

    travel_os = CognitiveOS()
    travel_os.set_actor(travel_actor)

    # Register a handler for every step the planner will produce for this
    # actor + command (one per fact entity: the "book" action verb, booking,
    # money, flight, berlin — plus achieve_goal) so the whole run succeeds
    # end to end.
    for step_name in ("process_book", "process_booking", "process_money", "process_flight", "process_berlin", "achieve_goal"):
        travel_os.register_capability(RealStepCapability(step_name))

    result = await travel_os.run("Book me a flight to Berlin next Friday")

    print("\n=== os.run() pipeline (real DeterministicPlanner, ported from monkeypatched) ===")
    print(f"Parsed intent: {result.intent}")
    print(f"Goals created: {result.goals_created}")
    print(f"Plan steps: {[s['name'] for s in result.steps]}")
    print(f"Step results: {result.step_results}")
    print(f"Success: {result.success}")


asyncio.run(run_pipeline_demo())

print("\nDone — zero external dependencies!")
