"""Tests for LLMPlannerEngine. Hermetic — the HTTP call is monkeypatched
so this suite never needs Ollama (or any LLM) actually running; that
matches the rest of tests/ staying zero-dependency. Live verification
against a real running Ollama is done separately, not in this suite.
"""
import asyncio

import pytest

from cognitiveos import Actor
from cognitiveos.engine.llm_planner import LLMPlannerEngine


class TestParseSteps:
    def test_clean_json_array(self):
        assert LLMPlannerEngine._parse_steps('["boil_water", "add_tea", "pour", "serve"]') == [
            "boil_water", "add_tea", "pour", "serve",
        ]

    def test_markdown_fenced_json(self):
        text = '```json\n["boil_water", "add_tea"]\n```'
        assert LLMPlannerEngine._parse_steps(text) == ["boil_water", "add_tea"]

    def test_json_with_leading_prose(self):
        text = 'Here is the plan:\n["boil_water", "add_tea"]'
        assert LLMPlannerEngine._parse_steps(text) == ["boil_water", "add_tea"]

    def test_normalizes_spaces_and_case(self):
        assert LLMPlannerEngine._parse_steps('["Boil Water", "ADD TEA"]') == ["boil_water", "add_tea"]

    def test_non_list_json_raises(self):
        with pytest.raises(ValueError):
            LLMPlannerEngine._parse_steps('{"not": "a list"}')


class TestLLMPlannerEngineTick:
    def test_tick_returns_plan_from_generated_steps(self, monkeypatch):
        engine = LLMPlannerEngine()

        async def fake_generate_plan(prompt):
            assert "Make tea" in prompt
            return ["boil_water", "add_tea", "pour", "serve"]

        monkeypatch.setattr(engine, "_generate_plan", fake_generate_plan)

        actor = Actor(entity_id="alice", actor_type_id="human")

        class FakeIntent:
            raw = "Make tea"

        actor._current_intent = FakeIntent()

        result = asyncio.run(engine.tick(actor))

        assert result["success"] is True
        assert [s["name"] for s in result["plan"]["steps"]] == ["boil_water", "add_tea", "pour", "serve"]
        assert all(s["type"] == "capability" for s in result["plan"]["steps"])

    def test_tick_with_no_goal_returns_honest_error_without_calling_llm(self, monkeypatch):
        engine = LLMPlannerEngine()
        called = False

        async def fake_generate_plan(prompt):
            nonlocal called
            called = True
            return []

        monkeypatch.setattr(engine, "_generate_plan", fake_generate_plan)

        actor = Actor(entity_id="alice", actor_type_id="human")
        result = asyncio.run(engine.tick(actor))

        assert result["success"] is False
        assert "error" in result
        assert called is False

    def test_tick_propagates_llm_failure_honestly(self, monkeypatch):
        engine = LLMPlannerEngine()

        async def failing_generate_plan(prompt):
            raise RuntimeError("could not reach LLM at http://127.0.0.1:11434")

        monkeypatch.setattr(engine, "_generate_plan", failing_generate_plan)

        actor = Actor(entity_id="alice", actor_type_id="human")

        class FakeIntent:
            raw = "Make tea"

        actor._current_intent = FakeIntent()

        result = asyncio.run(engine.tick(actor))
        assert result["success"] is False
        assert "could not reach LLM" in result["error"]
