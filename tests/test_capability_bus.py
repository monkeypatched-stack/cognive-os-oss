"""Tests for CapabilityBus multi-provider support (OSS-0503)."""
import asyncio

from cognitiveos.capability_bus import CapabilityBus


class FastCalculator:
    name = "calculator"
    proficiency = 0.6

    def fn(self, kwargs):
        return {"success": True, "provider": "fast"}


class AccurateCalculator:
    name = "calculator"
    proficiency = 0.95

    def fn(self, kwargs):
        return {"success": True, "provider": "accurate"}


class NoProficiencyCap:
    name = "calculator"

    def fn(self, kwargs):
        return {"success": True, "provider": "default_proficiency"}


class TestMultiProviderCapabilityBus:
    def test_second_registration_does_not_overwrite_first(self):
        bus = CapabilityBus()
        bus.register_capability(FastCalculator())
        bus.register_capability(AccurateCalculator())
        assert len(bus.list_providers("calculator")) == 2

    def test_execute_selects_highest_proficiency_provider(self):
        bus = CapabilityBus()
        bus.register_capability(FastCalculator())
        bus.register_capability(AccurateCalculator())

        result = asyncio.run(bus.execute("calculator"))
        assert result.produced["provider"] == "accurate"

    def test_tie_breaks_by_registration_order(self):
        bus = CapabilityBus()
        bus.register_capability(NoProficiencyCap())  # proficiency defaults to 0.5
        bus.register_capability(FastCalculator())     # 0.6, strictly higher — should win
        result = asyncio.run(bus.execute("calculator"))
        assert result.produced["provider"] == "fast"

    def test_single_provider_still_works_as_before(self):
        bus = CapabilityBus()
        bus.register_capability(AccurateCalculator())
        result = asyncio.run(bus.execute("calculator"))
        assert result.produced["provider"] == "accurate"


class TestFuzzyCapabilityResolution:
    """OSS-0501/OSS-0603: a planner-generated step name ('process_weather')
    doesn't exact-match a registered capability ('weather_api') — real
    keyword-overlap fallback, not a hardcoded synonym table.
    """

    def test_falls_back_to_shared_keyword_when_no_exact_match(self):
        class WeatherAPI:
            name = "weather_api"
            def fn(self, kwargs): return {"success": True, "via": "weather_api"}

        bus = CapabilityBus()
        bus.register_capability(WeatherAPI())
        result = asyncio.run(bus.execute("process_weather"))
        assert result.produced["via"] == "weather_api"

    def test_prefers_more_relevant_capability_over_less_relevant_one(self):
        class Browser:
            name = "browser"
            def fn(self, kwargs): return {"success": True, "via": "browser"}
        class WeatherAPI:
            name = "weather_api"
            def fn(self, kwargs): return {"success": True, "via": "weather_api"}

        bus = CapabilityBus()
        bus.register_capability(Browser())
        bus.register_capability(WeatherAPI())
        result = asyncio.run(bus.execute("process_weather"))
        assert result.produced["via"] == "weather_api"

    def test_no_shared_keyword_still_reports_not_found(self):
        """Doesn't fuzzy-match into a false positive when nothing is
        genuinely relevant."""
        class Browser:
            name = "browser"
            def fn(self, kwargs): return {"success": True}

        bus = CapabilityBus()
        bus.register_capability(Browser())
        result = asyncio.run(bus.execute("generate_image"))
        assert result.success is False
        assert result.produced["error"] == "capability_not_found"

    def test_structural_words_are_not_meaningful_signal(self):
        """'achieve_goal' shouldn't fuzzy-match a capability just because
        it happens to contain the word 'goal'."""
        class GoalTracker:
            name = "goal_tracker"
            def fn(self, kwargs): return {"success": True}

        bus = CapabilityBus()
        bus.register_capability(GoalTracker())
        result = asyncio.run(bus.execute("achieve_goal"))
        assert result.success is False
        assert result.produced["error"] == "capability_not_found"
