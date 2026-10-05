"""Shared Responses deadlines must not replace protected request state."""

import headroom.transforms.content_router as routing


def test_joined_deadline_preserves_request_options_and_restores_caller(monkeypatch):
    monkeypatch.setattr(routing, "_compression_deadline_seconds", lambda: 1.0)
    monkeypatch.setattr(routing.time, "perf_counter", lambda: 100.0)
    router = routing.ContentRouter()
    router._runtime_target_ratio = 0.8
    router._runtime_kompress_deadline_started_at = 90.0
    with router.request_scope():
        router._runtime_target_ratio = 0.25
        router._protect_read_tool_ids = {"read-1"}
        router._tool_call_commands = {"read-1": "read_file"}
        assert router.share_request_deadline(99.5) is True
        assert router._runtime_kompress_deadline_started_at == 99.5
        assert router._runtime_target_ratio == 0.25
        assert router._protect_read_tool_ids == {"read-1"}
        assert router._tool_call_commands == {"read-1": "read_file"}
    assert router._runtime_target_ratio == 0.8
    assert router._runtime_kompress_deadline_started_at == 90.0


def test_expired_shared_deadline_does_not_rebind_request_state(monkeypatch):
    monkeypatch.setattr(routing, "_compression_deadline_seconds", lambda: 1.0)
    monkeypatch.setattr(routing.time, "perf_counter", lambda: 100.0)
    router = routing.ContentRouter()
    router._runtime_kompress_deadline_started_at = 99.5
    router._protect_read_tool_ids = {"read-1"}
    assert router.share_request_deadline(98.0) is False
    assert router._runtime_kompress_deadline_started_at == 99.5
    assert router._protect_read_tool_ids == {"read-1"}
