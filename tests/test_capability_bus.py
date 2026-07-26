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


class TestPermissions:
    class _Guarded:
        name = "guarded"
        required_permissions = {"admin"}

        def fn(self, kwargs):
            return {"success": True}

    class _Context:
        def __init__(self, permissions):
            self.permissions = permissions

    def test_get_permissions_for_unknown_capability_is_empty(self):
        bus = CapabilityBus()
        assert bus.get_permissions("ghost") == set()

    def test_get_permissions_returns_declared_set(self):
        bus = CapabilityBus()
        bus.register_capability(self._Guarded())
        assert bus.get_permissions("guarded") == {"admin"}

    def test_check_authorization_allows_when_no_permissions_required(self):
        bus = CapabilityBus()
        allowed, reason = bus.check_authorization("anything", set())
        assert allowed is True
        assert reason == ""

    def test_check_authorization_denies_when_missing(self):
        bus = CapabilityBus()
        bus.register_capability(self._Guarded())
        allowed, reason = bus.check_authorization("guarded", set())
        assert allowed is False
        assert "admin" in reason

    def test_execute_denies_without_context(self):
        """No context means no granted permissions at all — authorization
        fails closed, not open."""
        bus = CapabilityBus()
        bus.register_capability(self._Guarded())
        result = asyncio.run(bus.execute("guarded"))
        assert result.success is False
        assert result.produced["error"] == "authorization_denied"

    def test_execute_allows_with_sufficient_context_permissions(self):
        bus = CapabilityBus()
        bus.register_capability(self._Guarded())
        result = asyncio.run(bus.execute("guarded", context=self._Context({"admin"})))
        assert result.success is True

    def test_execute_denies_with_insufficient_context_permissions(self):
        bus = CapabilityBus()
        bus.register_capability(self._Guarded())
        result = asyncio.run(bus.execute("guarded", context=self._Context({"read"})))
        assert result.success is False
        assert "admin" in result.produced["detail"]


class TestExecuteEdgeCases:
    def test_capability_with_no_fn_and_not_callable_reports_no_callable(self):
        class Inert:
            name = "inert"

        bus = CapabilityBus()
        bus.register_capability(Inert())
        result = asyncio.run(bus.execute("inert"))
        assert result.success is True  # no "error"/"success" key -> defaults True
        assert result.produced == {"error": "no_callable"}

    def test_callable_capability_without_fn_attribute_is_invoked_directly(self):
        class CallableCap:
            name = "callable_cap"
            def __call__(self, kwargs):
                return {"success": True, "via": "call"}

        bus = CapabilityBus()
        bus.register_capability(CallableCap())
        result = asyncio.run(bus.execute("callable_cap"))
        assert result.produced == {"success": True, "via": "call"}

    def test_exception_inside_fn_is_caught_and_reported(self):
        class Explodes:
            name = "explodes"
            def fn(self, kwargs):
                raise ValueError("kaboom")

        bus = CapabilityBus()
        bus.register_capability(Explodes())
        result = asyncio.run(bus.execute("explodes"))
        assert result.success is False
        assert "kaboom" in result.produced["error"]

    def test_non_dict_result_wrapped_under_result_key(self):
        class ReturnsString:
            name = "returns_string"
            def fn(self, kwargs):
                return "just a string"

        bus = CapabilityBus()
        bus.register_capability(ReturnsString())
        result = asyncio.run(bus.execute("returns_string"))
        assert result.success is True
        assert result.produced == {"result": "just a string"}


class TestSummary:
    def test_summary_reports_capability_and_provider_counts(self):
        bus = CapabilityBus()
        bus.register_capability(TestPermissions._Guarded())

        class SecondGuarded(TestPermissions._Guarded):
            pass

        bus.register_capability(SecondGuarded())
        summary = bus.summary()
        assert summary["capabilities_registered"] == 1
        assert summary["providers_registered"] == 2
        assert summary["mesh_attached"] is False

    def test_set_mesh_reflected_in_summary(self):
        bus = CapabilityBus()
        bus.set_mesh(object())
        assert bus.summary()["mesh_attached"] is True
