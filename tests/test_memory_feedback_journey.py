"""Disposable authored prompt → scoped durable recall → guarded lifecycle."""
import json

import pytest

from tests.test_memory_commands import app, client, command  # noqa: F401
from headroom.memory.storage_router import BackendRouter, RequestContext
from headroom.proxy.memory_injection import MemoryInjectionBudget


async def test_authored_feedback_fresh_session_restart_compaction_and_forget(app, monkeypatch):
    handler = app.state.proxy.memory_handler
    original = "Nhớ quy tắc này: đừng dùng dữ liệu giả. Không được tự phê duyệt."
    async with client(app) as first:
        first.headers["x-headroom-source"] = "opencode-prompt"
        for _ in range(2):
            response = await command(first, "memory_feedback", text=original)
            assert response.status_code == 200
        rows = (await command(first, "memory_list")).json()["memories"]
        assert {r["content"] for r in rows} == {"Nhớ quy tắc này: đừng dùng dữ liệu giả.", "Không được tự phê duyệt."}
    async with client(app) as fresh:
        fresh.headers["x-headroom-evidence-id"] = "new-session:new-message"
        fresh.headers["x-headroom-memory-tools"] = "client"
        rows = (await command(fresh, "memory_search", query="dữ liệu giả")).json()["memories"]
        old = next(r for r in rows if "dữ liệu giả" in r["content"])
        updated = (await command(fresh, "memory_update", memory_id=old["id"],
            expected_content_hash=old["content_hash"], new_content="Chỉ dùng dữ liệu tổng hợp trong kiểm tra cô lập.",
            reason="owner narrows the rule to isolated tests")).json()
        assert updated["status"] == "updated"
        # Restart the scoped backend/router, retaining only its disposable disk.
        config = handler._router._config
        for backend in handler._router._backends.values():
            await backend.close()
        handler._router = BackendRouter(config)
        # A compacted summary isn't another authored feedback event. Search uses
        # retained SQLite evidence, not learning from this compacted context.
        context = RequestContext(headers=dict(fresh.headers), system_prompt="", base_user_id="alice")
        block = await handler.search_and_format_context("alice", [{"role": "user", "content": "kiểm tra cô lập"}],
            request_context=context, budget=MemoryInjectionBudget())
        assert "Chỉ dùng dữ liệu tổng hợp" in block and old["id"] not in block
        assert (await command(fresh, "memory_update", memory_id=old["id"],
            expected_content_hash=old["content_hash"], new_content="stale correction", reason="stale")).status_code == 409
        # Replaying the original prompt cannot reactivate the superseded rule.
        fresh.headers["x-headroom-source"] = "opencode-prompt"
        fresh.headers["x-headroom-evidence-id"] = "session:message:call1"
        assert (await command(fresh, "memory_feedback", text=original)).status_code == 200
        current = (await command(fresh, "memory_list")).json()["memories"]
        assert old["id"] not in {r["id"] for r in current} and len(current) == 2
        assert (await command(fresh, "memory_delete", memory_id=updated["memory_id"],
            expected_content_hash=updated["content_hash"], reason="explicit owner forget request")).json()["status"] == "forgotten"
        # Independent project never inherits either rule or history authority.
        fresh.headers["x-headroom-cwd"] = "/synthetic/project-b"
        assert (await command(fresh, "memory_search", query="dữ liệu")).json()["memories"] == []


async def test_interrupted_native_save_retry_recovers_exact_active_evidence(app, monkeypatch):
    handler = app.state.proxy.memory_handler
    async with client(app) as c:
        context = RequestContext(headers=dict(c.headers), system_prompt="", base_user_id="alice")
        backend, _, _ = handler._resolve_for_request("alice", context)
        await backend._ensure_initialized()
        index = backend._hierarchical_memory.text_index
        original_index = index.index_memory
        async def interrupted(*args):
            raise RuntimeError("index write interrupted")
        monkeypatch.setattr(index, "index_memory", interrupted)
        assert (await command(c, "memory_save", content="Never mutate production data.")).status_code == 503
        monkeypatch.setattr(index, "index_memory", original_index)
        saved = (await command(c, "memory_save", content="Never mutate production data.")).json()
        assert saved["status"] == "saved" and saved["replayed"] is True
        rows = (await command(c, "memory_search", query="production data")).json()["memories"]
        assert len(rows) == 1 and rows[0]["id"] == saved["memory_id"]
        assert rows[0]["content"] == "Never mutate production data."
