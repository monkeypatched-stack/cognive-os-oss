"""How to register a capability backed by a real external API.

This is the minimal pattern — no credentials, no local services, nothing
to set up. Compare to examples/grocery_capability.py (a full real service
with auth/payment/shipping) and examples/instacart_capability.py (a real
partner API that needs credentials this repo doesn't have) for more
involved cases; this file is the "start here" version of the same pattern.

The pattern, in three parts:

1. A capability is any object with:
     .name          -> str, the plan-step name it handles
     .fn(kwargs)     -> dict, with kwargs["context"] giving access to the
                        ExecutionState (kwargs["context"].question is the
                        raw command text)

2. Register it on a CognitiveOS instance:
     os.register_capability(MyCapability())

3. cognitiveos's real planner (cognitiveos.engine.DeterministicPlanner)
   decides WHEN to call it — it plans a step named after whatever entity
   it reasoned about (see os.py's run() docstring: "the engine decides
   what steps to take, the middleware executes them"). Your capability
   just needs to be registered under the name the planner will produce.
   Run examples/standalone.py first if you haven't already — it shows
   what those step names look like for a given actor + command.

Run: pip install -e ".[examples]"; python examples/api_capability.py
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from cognitiveos import Actor, CognitiveOS


class WeatherCapability:
    """Real (non-mocked) capability: looks up a city's live weather via
    Open-Meteo (https://open-meteo.com — free, no API key required).

    Two real HTTP calls: geocode the city name to lat/lon, then fetch the
    current weather for those coordinates. Either can genuinely fail (city
    not found, service unreachable) — those failures are reported
    honestly, not swallowed into a fake success.
    """

    name = "process_weather"  # must match the plan step this should handle

    def fn(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        context = kwargs.get("context")
        question = context.question if context is not None else ""

        match = re.search(r"weather\s+(?:in|for)\s+(\w+)", question, re.IGNORECASE)
        if not match:
            return {"success": False, "error": "could_not_parse_city"}
        city = match.group(1)

        try:
            geo = httpx.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": 1}, timeout=5.0,
            ).json()
        except httpx.HTTPError as exc:
            return {"success": False, "error": "geocoding_unreachable", "detail": str(exc)}

        results = geo.get("results") or []
        if not results:
            return {"success": False, "error": f"city_not_found: {city}"}
        lat, lon = results[0]["latitude"], results[0]["longitude"]

        try:
            forecast = httpx.get(
                "https://api.open-meteo.com/v1/forecast",
                params={"latitude": lat, "longitude": lon, "current_weather": "true"},
                timeout=5.0,
            ).json()
        except httpx.HTTPError as exc:
            return {"success": False, "error": "forecast_unreachable", "detail": str(exc)}

        current = forecast.get("current_weather")
        if not current:
            return {"success": False, "error": "no_current_weather_in_response"}

        return {
            "success": True,
            "city": results[0]["name"],
            "temperature_c": current["temperature"],
            "windspeed_kmh": current["windspeed"],
        }


async def main() -> None:
    actor = Actor(entity_id="alice", actor_type_id="human", name="Alice", goals=["discovery"])

    os_ = CognitiveOS()
    os_.set_actor(actor)
    os_.register_capability(WeatherCapability())

    result = await os_.run("What's the weather in Berlin?")

    print("Parsed intent:", result.intent)
    print("Plan steps:   ", [s["name"] for s in result.steps])
    for sr in result.step_results:
        print(f"  {sr.action:20s} -> {sr.status:8s} {sr.output}")
    print("\nOverall success:", result.success)


if __name__ == "__main__":
    asyncio.run(main())
