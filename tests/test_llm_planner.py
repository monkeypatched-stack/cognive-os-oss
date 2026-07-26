"""Tests for LLMPlannerEngine. Hermetic — the HTTP call is monkeypatched
so this suite never needs Ollama (or any LLM) actually running; that
matches the rest of tests/ staying zero-dependency. Live verification
against a real running Ollama is done separately, not in this suite.
"""
import asyncio
import json
import urllib.error
import urllib.request

import pytest

from cognitiveos import Actor
from cognitiveos.engine.llm_planner import LLMPlannerEngine


class _FakeHTTPResponse:
    """Minimal stand-in for the object urllib.request.urlopen()'s context
    manager yields — just enough to satisfy `.read().decode()`."""

    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


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
        with pytest.raises(TypeError):
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


class TestGeneratePlanSync:
    """Covers the real HTTP path (_generate_plan_sync / _generate_plan),
    hermetically — urllib.request.urlopen is monkeypatched so no live
    Ollama is contacted, but the actual request-building and
    response-parsing code runs for real.
    """

    def test_generate_plan_sync_parses_ollama_style_response(self, monkeypatch):
        engine = LLMPlannerEngine()

        def fake_urlopen(request, timeout=None):
            assert request.full_url == "http://127.0.0.1:11434/api/generate"
            body = json.loads(request.data.decode())
            assert body["model"] == "gemma3:latest"
            return _FakeHTTPResponse({"response": '["boil_water", "add_tea"]'})

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        steps = engine._generate_plan_sync("Make tea")
        assert steps == ["boil_water", "add_tea"]

    def test_generate_plan_sync_wraps_url_error(self, monkeypatch):
        engine = LLMPlannerEngine()

        def fake_urlopen(request, timeout=None):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        with pytest.raises(RuntimeError, match="could not reach LLM"):
            engine._generate_plan_sync("Make tea")

    def test_generate_plan_runs_sync_call_off_the_event_loop(self, monkeypatch):
        """_generate_plan (async) delegates to _generate_plan_sync via
        run_in_executor — exercise the real async wrapper, not just the
        sync half."""
        engine = LLMPlannerEngine()

        def fake_urlopen(request, timeout=None):
            return _FakeHTTPResponse({"response": '["step_one"]'})

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        steps = asyncio.run(engine._generate_plan("Do a thing"))
        assert steps == ["step_one"]

    def test_tick_end_to_end_through_real_http_path(self, monkeypatch):
        """Full tick() -> _generate_plan -> _generate_plan_sync -> urlopen
        chain, only urlopen itself faked."""
        engine = LLMPlannerEngine()

        def fake_urlopen(request, timeout=None):
            return _FakeHTTPResponse({"response": '["boil_water", "serve"]'})

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        actor = Actor(entity_id="alice", actor_type_id="human")

        class FakeIntent:
            raw = "Make tea"

        actor._current_intent = FakeIntent()

        result = asyncio.run(engine.tick(actor))
        assert result["success"] is True
        assert [s["name"] for s in result["plan"]["steps"]] == ["boil_water", "serve"]
