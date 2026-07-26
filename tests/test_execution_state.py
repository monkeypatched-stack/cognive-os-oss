"""Tests for cognitiveos.execution_state — ExecutionState and CapabilityResult.

Note: this ExecutionState is distinct from the ExecutionState used by
cognitiveos.os.run() at runtime (same class, imported directly there);
CapabilityResult here is a different type from
cognitiveos.capability_bus.CapabilityResult (same name, different shape —
this one wraps an updated_state, the bus one wraps `produced`/`success`).
"""
from cognitiveos.execution_state import CapabilityResult, ExecutionPhase, ExecutionState


class TestExecutionStateBasics:
    def test_defaults(self):
        state = ExecutionState()
        assert state.question == ""
        assert state.phase == ExecutionPhase.INITIALIZED
        assert state.entities == []
        assert state.has_errors() is False
        assert state.is_complete() is False

    def test_add_entity_tracks_both_list_and_resolved_map(self):
        state = ExecutionState()
        state.add_entity("person", {"name": "Alice"})
        assert state.entities == [{"name": "Alice"}]
        assert state.get_entity("person") == {"name": "Alice"}
        assert state.get_entity("missing") is None

    def test_add_hierarchy_merges_dict(self):
        state = ExecutionState()
        state.add_hierarchy({"a": 1})
        state.add_hierarchy({"b": 2})
        assert state.hierarchy == {"a": 1, "b": 2}

    def test_add_relationship_appends(self):
        state = ExecutionState()
        state.add_relationship({"from": "a", "to": "b"})
        assert state.relationships == [{"from": "a", "to": "b"}]

    def test_add_graph_entities_documents_web_results_extend_lists(self):
        state = ExecutionState()
        state.add_graph_entities([{"id": 1}])
        state.add_graph_entities([{"id": 2}])
        state.add_documents([{"doc": "x"}])
        state.add_web_results([{"url": "y"}])
        assert state.graph_entities == [{"id": 1}, {"id": 2}]
        assert state.documents == [{"doc": "x"}]
        assert state.web_results == [{"url": "y"}]

    def test_record_capability_execution_updates_history_and_trace(self):
        state = ExecutionState()
        state.record_capability_execution("resolver", {"timestamp": "t1", "ok": True})
        assert state.capability_history == ["resolver"]
        assert state.execution_trace == [{
            "capability": "resolver",
            "result": {"timestamp": "t1", "ok": True},
            "timestamp": "t1",
        }]

    def test_observations_and_policy_updates(self):
        state = ExecutionState()
        state.add_observation({"obs": 1})
        state.add_policy_update({"policy": "x"})
        assert state.observations == [{"obs": 1}]
        assert state.policy_updates == [{"policy": "x"}]

    def test_set_answer(self):
        state = ExecutionState()
        state.set_answer("42", quality=0.9, confidence=0.8)
        assert state.current_answer == "42"
        assert state.answer_quality == 0.9
        assert state.confidence == 0.8

    def test_errors_and_warnings(self):
        state = ExecutionState()
        assert state.has_errors() is False
        state.add_error("boom")
        state.add_warning("careful")
        assert state.has_errors() is True
        assert state.errors == ["boom"]
        assert state.warnings == ["careful"]

    def test_is_complete_for_completed_and_failed_phases(self):
        state = ExecutionState(phase=ExecutionPhase.COMPLETED)
        assert state.is_complete() is True
        state2 = ExecutionState(phase=ExecutionPhase.FAILED)
        assert state2.is_complete() is True
        state3 = ExecutionState(phase=ExecutionPhase.ANALYSIS)
        assert state3.is_complete() is False

    def test_data_accessors(self):
        state = ExecutionState()
        assert state.has_data("k") is False
        assert state.get_data("k") is None
        state.set_data("k", {"v": 1})
        assert state.has_data("k") is True
        assert state.get_data("k") == {"v": 1}


class TestExecutionStateSerialization:
    def test_to_dict_and_from_dict_roundtrip(self):
        state = ExecutionState(question="q", intent="i", phase=ExecutionPhase.ANALYSIS)
        state.add_entity("person", {"name": "Alice"})
        state.set_data("step1", {"out": 1})
        state.add_error("oops")

        data = state.to_dict()
        restored = ExecutionState.from_dict(data)

        assert restored.question == "q"
        assert restored.intent == "i"
        assert restored.phase == ExecutionPhase.ANALYSIS
        assert restored.entities == [{"name": "Alice"}]
        assert restored.resolved_entities == {"person": {"name": "Alice"}}
        assert restored.execution_stats == {"step1": {"out": 1}}
        assert restored.errors == ["oops"]

    def test_from_dict_defaults_when_data_missing(self):
        restored = ExecutionState.from_dict({})
        assert restored.question == ""
        assert restored.phase == ExecutionPhase.INITIALIZED
        assert restored.entities == []


class TestCapabilityResult:
    def test_to_dict_includes_nested_state(self):
        state = ExecutionState(question="q")
        result = CapabilityResult(updated_state=state, capability_name="cap1", success=True)
        d = result.to_dict()
        assert d["capability_name"] == "cap1"
        assert d["success"] is True
        assert d["updated_state"]["question"] == "q"

    def test_from_dict_roundtrip(self):
        state = ExecutionState(question="q")
        result = CapabilityResult(
            updated_state=state, capability_name="cap1", success=False,
            latency=12.5, observations=[{"o": 1}], transition_reward=0.5,
        )
        restored = CapabilityResult.from_dict(result.to_dict())
        assert restored.capability_name == "cap1"
        assert restored.success is False
        assert restored.latency == 12.5
        assert restored.observations == [{"o": 1}]
        assert restored.updated_state.question == "q"

    def test_defaults(self):
        state = ExecutionState()
        result = CapabilityResult(updated_state=state)
        assert result.success is True
        assert result.capability_name == ""
        assert result.observations == []
