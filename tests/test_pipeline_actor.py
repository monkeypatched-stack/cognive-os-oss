"""Tests for cognitiveos.engine.pipeline_actor.PipelineActor — the engine's
own identity/lifecycle bookkeeping (distinct from cognitiveos.Actor)."""
from cognitiveos.engine.pipeline_actor import PipelineActor


class TestLifecycle:
    def test_starts_idle_and_is_active(self):
        actor = PipelineActor(actor_id="a1")
        assert actor.status == "idle"
        assert actor.is_active() is True

    def test_start_and_finish_reasoning_tracks_cycle_count(self):
        actor = PipelineActor(actor_id="a1")
        actor.start_reasoning()
        assert actor.status == "reasoning"
        assert actor.is_active() is False

        actor.finish_reasoning()
        assert actor.status == "idle"
        assert actor.cycle_count == 1
        assert actor.last_reasoned_at > 0

    def test_multiple_cycles_increment_count(self):
        actor = PipelineActor(actor_id="a1")
        for _ in range(3):
            actor.start_reasoning()
            actor.finish_reasoning()
        assert actor.cycle_count == 3

    def test_block_sets_status_with_reason(self):
        actor = PipelineActor(actor_id="a1")
        actor.block("waiting_on_resource")
        assert actor.status == "blocked:waiting_on_resource"
        assert actor.is_active() is False

    def test_terminate(self):
        actor = PipelineActor(actor_id="a1")
        actor.terminate()
        assert actor.status == "terminated"
        assert actor.is_active() is False


class TestSnapshotAndSummary:
    def test_snapshot_captures_identity_and_state(self):
        actor = PipelineActor(actor_id="a1", tenant_id="t1", trust_score=0.8)
        actor.start_reasoning()
        actor.finish_reasoning()
        snap = actor.snapshot()
        assert snap.actor_id == "a1"
        assert snap.tenant_id == "t1"
        assert snap.trust_score == 0.8
        assert snap.status == "idle"
        assert snap.cycle_count == 1

    def test_summary_rounds_trust_score(self):
        actor = PipelineActor(actor_id="a1", trust_score=0.123456)
        summary = actor.summary()
        assert summary["trust_score"] == 0.123
        assert summary["actor_id"] == "a1"
        assert summary["cycle_count"] == 0
