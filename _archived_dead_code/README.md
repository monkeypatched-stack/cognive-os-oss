# Archived dead code

These modules were copied into the standalone cognitiveos package during
extraction but are never imported by cognitiveos/__init__.py, os.py, actor.py,
protocol.py, or any test. They belong to a separate "adapter SDK" subsystem
(different exception hierarchy rooted at AdapterError, ILifecycleManager /
IEventBus / ITelemetryManager interfaces, contracts/interfaces.py references
`..events.bus` and `..telemetry.manager` modules that don't exist in this
package) — not the 5-layer CognitiveOS architecture (Ontology -> Actor ->
CognitiveOS -> Society -> Trust Network).

Verified orphaned via import-graph grep on 2026-07-25 before archiving:
contracts/, lifecycle/, registries/capability_registry.py,
execution/__init__.py (the package, not execution_state.py), provider_registry.py,
scheduler.py, config.py.

Kept here instead of deleted since nothing referenced them; safe to delete
entirely once confirmed unneeded.
