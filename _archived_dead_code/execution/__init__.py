"""Execution middleware — copied from monkeypatched kernel.

Core components for agent execution:
- ICapability interface
- ExecutionState (accumulated state during execution)
- CapabilityBus (permission-gated capability execution)
- AgentBus (agent resolution and execution)
"""
from cognitiveos.capability_interface import ICapability, EntityResolutionCapability, KnowledgeRetrievalCapability, AnalysisCapability, AnswerGenerationCapability
from cognitiveos.execution_state import ExecutionState, CapabilityResult, ExecutionPhase
from cognitiveos.capability_bus import CapabilityBus
from cognitiveos.agent_bus import AgentBus, AgentResult
