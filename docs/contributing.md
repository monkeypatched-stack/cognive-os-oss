# Contributing

## Development Setup

```bash
git clone <repo-url>
cd cognitive-os-oss
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,examples]"
```

## Running Tests

```bash
pytest
```

## Linting

```bash
ruff check cognitiveos/
```

## Project Structure

```
cognitiveos/          # main package
├── os.py             # CognitiveOS runtime
├── actor.py          # Actor
├── engine/           # planners and execution
├── agents/           # agent system
├── affiliations/     # trust management
├── ontology/         # type system
tests/                # test suite
examples/             # runnable examples
docs/                 # documentation
```

## Code Style

- Zero required dependencies
- Python >= 3.12
- Type hints on all public APIs
- Docstrings on all public classes and methods
- No comments unless explaining non-obvious behavior

## Adding a Capability

1. Create a class with `.name` and `.fn(kwargs)` — see [Building Capabilities](building-capabilities.md)
2. Add an example in `examples/`
3. Add tests in `tests/`

## Adding an Agent

1. Create a class with `.agent_type` and `async .handle(kwargs)` — see [Building Agents](building-agents.md)
2. Add an example in `examples/`
3. Add tests in `tests/`

## Adding an Engine

1. Implement `ICognitiveEngine` (async `tick(actor) -> dict`)
2. Return `{"plan": {"steps": [...]}}` from `tick()`
3. Register via `os.set_engine(MyEngine())`
4. Add tests

## Testing Conventions

- Tests are in `tests/` as `test_*.py`
- Use `pytest` and `asyncio`
- Tests are named after what they verify (e.g. `test_actor.py`, `test_os.py`)

## Architecture Invariants

These must always hold:

- One CognitiveOS owns exactly one Actor
- All cognition is local
- No required dependencies
- All integrations through interfaces
- Domain knowledge in capabilities, not the runtime

## Submitting Changes

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure `pytest` passes
5. Ensure `ruff check` passes
6. Submit a pull request
