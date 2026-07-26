# Building Capabilities

Capabilities are synchronous units of work dispatched by the `CapabilityBus`. They handle plan steps that the planner produces.

## Capability Contract

A capability is any object with:

| Member | Type | Description |
|---|---|---|
| `name` | `str` | The plan step name it handles (e.g. `"process_weather"`) |
| `fn(kwargs)` | `callable` | Receives `kwargs` including `kwargs["context"]` (an `ExecutionState`) |

## Minimal Example

```python
class WeatherCapability:
    name = "process_weather"

    def fn(self, kwargs):
        context = kwargs.get("context")
        question = context.question if context is not None else ""
        return {"success": True, "city": "Berlin", "temperature_c": 22}
```

## Registration

```python
os = CognitiveOS()
os.register_capability(WeatherCapability())
```

## How Dispatch Works

1. The planner produces steps with names like `"process_weather"`, `"process_booking"`, etc.
2. The `CapabilityBus` matches step names to registered capabilities by exact name, then falls back to fuzzy word-overlap matching
3. The capability's `.fn()` is called with the execution context
4. The result is stored in `ExecutionState` for later steps to read

## Reading Context

The `context` argument gives access to the full `ExecutionState`:

```python
def fn(self, kwargs):
    context = kwargs["context"]

    # The raw command text
    command = context.question

    # Data from a prior step
    prior_output = context.get_data("step_name")

    # Current execution phase
    phase = context.phase
```

## Returning Results

Return a dict. The bus treats `{"success": False, "error": "..."}` as a failure:

```python
def fn(self, kwargs):
    if bad_condition:
        return {"success": False, "error": "missing_input"}
    return {"success": True, "result": "some output"}
```

## Multiple Providers

Multiple capabilities can register under the same name. The bus selects by highest `.proficiency`:

```python
os.register_capability(WeatherCapability())  # default proficiency 0.5

class BetterWeather:
    name = "process_weather"
    proficiency = 0.8  # this one wins

    def fn(self, kwargs):
        return {"success": True, "source": "premium_api"}

os.register_capability(BetterWeather())
```

## Authorization

Capabilities can declare required permissions:

```python
class AdminCapability:
    name = "delete_user"
    required_permissions = {"admin", "user_management"}

    def fn(self, kwargs):
        return {"success": True}
```

If the execution context doesn't include the required permissions, the bus returns a denied result without calling `.fn()`.

## Full Example

See `examples/api_capability.py` for a real HTTP-backed capability (Open-Meteo weather API).
