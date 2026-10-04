"""Local native memory commands share inference's retained scoped backend."""
import asyncio
import json
from types import SimpleNamespace

import httpx
import numpy as np
import pytest

from headroom.memory import storage_router
from headroom.memory.adapters.fts5 import FTS5TextIndex
from headroom.memory.adapters.sqlite import SQLiteMemoryStore
from headroom.memory.adapters.sqlite_graph import SQLiteGraphStore
from headroom.memory.adapters.sqlite_vector import SQLiteVectorIndex
from headroom.memory.backends.local import LocalBackend
from headroom.memory.core import HierarchicalMemory
from headroom.proxy.memory_handler import MemoryConfig, MemoryHandler
from headroom.proxy.models import ProxyConfig
from headroom.proxy.server import create_app


class FixtureEmbedder:
    async def embed(self, text):
        return np.array([1.0, 0.0], dtype=np.float32)


class FixtureBackend(LocalBackend):
    async def _init_locked(self):
        path = self._config.db_path
        self._hierarchical_memory = HierarchicalMemory(
            SQLiteMemoryStore(path), SQLiteVectorIndex(dimension=2, db_path=str(path) + ".vector"),
            FTS5TextIndex(str(path) + ".text"), FixtureEmbedder())
        self._graph = SQLiteGraphStore(str(path) + ".graph")
        self._initialized = True


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HEADROOM_OFFLINE", "1")
    monkeypatch.setenv("HEADROOM_BEACON", "off")
    monkeypatch.setattr(storage_router, "LocalBackend", FixtureBackend)
    app = create_app(ProxyConfig(memory_enabled=False, offline=True))
    handler = MemoryHandler(MemoryConfig(enabled=True, storage_root=str(tmp_path),
                                         db_path=str(tmp_path / "global.db")), agent_type="opencode")
    handler._initialized = True
    handler._backend = FixtureBackend()
    handler._router = storage_router.BackendRouter(storage_router.BackendRouterConfig(
        mode=storage_router.MemoryStorageMode.PROJECT, root_dir=tmp_path,
        global_db_path=tmp_path / "global.db"))
    app.state.proxy.memory_handler = handler
    return app


def client(app, peer="127.0.0.1", headers=None):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=(peer, 1234), raise_app_exceptions=False),
        base_url="http://127.0.0.1", headers=headers or {"x-headroom-cwd": "/synthetic/project-a",
        "x-headroom-user-id": "alice", "x-headroom-evidence-id": "session:message:call1"})


async def command(client, tool, **arguments):
    return await client.post("/v1/memory/tools", json={"tool": tool, "arguments": arguments})


async def test_scoped_save_fresh_recall_guarded_update_and_isolation(app):
    async with client(app) as c:
        saved = await command(c, "memory_save", content="Đừng dùng dữ liệu giả.")
        assert saved.status_code == 200, saved.text
        row = saved.json()
        repeat = (await command(c, "memory_save", content="Đừng dùng dữ liệu giả.")).json()
        assert repeat["memory_id"] == row["memory_id"] and repeat["replayed"]
        listed = (await command(c, "memory_list")).json()["memories"]
        assert len(listed) == 1 and listed[0]["content_hash"] == row["content_hash"]
        updated = await command(c, "memory_update", memory_id=row["memory_id"],
            new_content="Chỉ dùng dữ liệu tổng hợp trong test.", expected_content_hash=row["content_hash"], reason="owner correction")
        assert updated.status_code == 200, updated.text
        assert (await command(c, "memory_update", memory_id=row["memory_id"], new_content="stale replacement",
            expected_content_hash=row["content_hash"], reason="stale")).status_code == 409
        results = (await command(c, "memory_search", query="test")).json()["memories"]
        assert [r["id"] for r in results] == [updated.json()["memory_id"]]
        c.headers["x-headroom-cwd"] = "/synthetic/project-b"
        assert (await command(c, "memory_list")).json()["memories"] == []
        assert (await command(c, "memory_delete", memory_id=updated.json()["memory_id"],
            expected_content_hash=updated.json()["content_hash"], reason="explicit owner forget")).status_code == 409


@pytest.mark.parametrize("tool,args", [
    ("unknown", {}), ("memory_list", {"limit": 101}), ("memory_search", {"query": "q", "top_k": True}),
    ("memory_save", {"content": "fact", "user_id": "bob"}),
    ("memory_save", {"content": "fact", "cwd": "/other"}),
    ("memory_save", {"content": "fact", "_evidence_key": "forged"}),
    ("memory_save", {"content": "fact", "importance": "high"}),
    ("memory_save", {"content": "fact", "facts": ["x"] * 33}),
    ("memory_save", {"content": "x" * 16385}),
    ("memory_update", {"memory_id": "id", "new_content": "fact"}),
    ("memory_delete", {"memory_id": "id", "expected_content_hash": "stale"}),
])
async def test_invalid_payloads_are_rejected_before_backend_initialization(app, tool, args):
    async with client(app) as c:
        response = await c.post("/v1/memory/tools", json={"tool": tool, "arguments": args})
    assert response.status_code == 400
    assert not app.state.proxy.memory_handler._router._backends


async def test_missing_scope_cannot_initialize_a_global_store(app):
    async with client(app, headers={"x-headroom-evidence-id": "event"}) as c:
        response = await command(c, "memory_save", content="fact")
    assert response.status_code == 400
    assert not app.state.proxy.memory_handler._router._backends


async def test_body_bound_and_malformed_json(app):
    async with client(app) as c:
        assert (await c.post("/v1/memory/tools", content=b"{" * 65537)).status_code == 413
        assert (await c.post("/v1/memory/tools", content=b"{oops")).status_code == 400


@pytest.mark.parametrize("peer,headers,status", [
    ("203.0.113.7", {}, 404), ("127.0.0.1", {"host": "attacker.example"}, 404),
    ("127.0.0.1", {"origin": "https://attacker.example"}, 403),
])
async def test_remote_rebinding_or_cross_origin_cannot_read_or_write(app, peer, headers, status):
    async with client(app, peer=peer, headers={"x-headroom-cwd": "/synthetic/project-a", **headers}) as c:
        response = await command(c, "memory_list")
    assert response.status_code == status


async def test_disabled_unavailable_and_private_errors_are_truthful(app, monkeypatch):
    async with client(app) as c:
        handler = app.state.proxy.memory_handler
        handler.config.enabled = False
        assert (await command(c, "memory_list")).status_code == 503
        handler.config.enabled = True
        async def broken(*args, **kwargs):
            raise RuntimeError("secret token /private/production/db")
        monkeypatch.setattr(handler, "execute_scoped_command", broken, raising=False)
        response = await command(c, "memory_list")
        assert response.status_code == 503
        assert "secret" not in response.text and "/private" not in response.text


async def test_feedback_only_explicit_authored_retention_is_saved_once(app):
    async with client(app) as c:
        c.headers["x-headroom-source"] = "opencode-prompt"
        advisory = await command(c, "memory_feedback", text="Đừng dùng dữ liệu giả.")
        assert advisory.status_code == 200 and advisory.json()["status"] == "advisory"
        for _ in range(2):
            response = await command(c, "memory_feedback", text="Nhớ quy tắc này: đừng dùng dữ liệu giả.")
            assert response.status_code == 200, response.text
        assert len((await command(c, "memory_list")).json()["memories"]) == 1


async def test_cancellation_is_not_reported_as_saved(app, monkeypatch):
    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError()
    monkeypatch.setattr(app.state.proxy.memory_handler, "execute_scoped_command", cancelled, raising=False)
    async with client(app) as c:
        response = await command(c, "memory_save", content="fact")
        # Starlette's existing BaseHTTPMiddleware wraps the cancelled child as
        # a failed response. The API must never turn it into durable success.
        assert response.status_code >= 400
        assert "saved" not in response.text
    assert not app.state.proxy.memory_handler._router._backends


@pytest.mark.parametrize("surface", ["responses", "chat/completions"])
async def test_native_client_tools_and_prefix_are_not_overridden_by_proxy(app, surface):
    proxy = app.state.proxy
    proxy.config.optimize = False
    proxy.config.cache_enabled = False
    proxy.cache = None
    proxy.config.rate_limit_enabled = False
    proxy.config.cost_tracking_enabled = False
    proxy.memory_handler.config.inject_context = False
    seen = []
    def upstream(request):
        seen.append(json.loads(request.content))
        if surface == "responses":
            result = {"id": "resp_native", "object": "response", "status": "completed", "output": [
                {"type": "function_call", "call_id": "call1", "name": "memory_save", "arguments": '{"content":"not proxy owned"}'}],
                "usage": {"input_tokens": 20, "output_tokens": 5}}
        else:
            result = {"id": "chat_native", "object": "chat.completion", "choices": [{"index": 0,
                "message": {"role": "assistant", "tool_calls": [{"id": "call1", "type": "function", "function": {
                    "name": "memory_save", "arguments": '{"content":"not proxy owned"}'}}]}, "finish_reason": "tool_calls"}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25}}
        if len(seen) == 1:
            if surface == "responses":
                result["output"] = []
            else:
                result["choices"][0]["message"] = {"role": "assistant", "content": "ok"}
                result["choices"][0]["finish_reason"] = "stop"
        return httpx.Response(200, json=result)
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as upstream_client:
        proxy.http_client = upstream_client
        async with client(app) as c:
            c.headers["authorization"] = "Bearer synthetic-api-key"
            c.headers["x-headroom-memory-tools"] = "client"
            prefix = [{"role": "system", "content": "Current project instructions are authoritative."},
                      {"role": "user", "content": "Historical context."},
                      {"role": "assistant", "content": "Historical answer."}]
            messages = prefix + [{"role": "user", "content": "Now recall."}]
            tool = {"name": "memory_save", "description": "client executor", "parameters": {"type": "object", "properties": {}}}
            body = {"model": "gpt-4o-mini", "stream": False, "service_tier": "priority"}
            if surface == "responses":
                body.update(input=messages, tools=[{"type": "function", **tool}], instructions="UNCHANGED authoritative prefix",
                            include=["reasoning.encrypted_content"])
            else:
                body.update(messages=messages, tools=[{"type": "function", "function": tool}])
            # Seed the same session's legacy sticky tool snapshot before the
            # native client takes ownership. Old proxy-only schemas cannot replay.
            c.headers.pop("x-headroom-memory-tools")
            assert (await c.post("/v1/" + surface, json=body)).status_code == 200
            c.headers["x-headroom-memory-tools"] = "client"
            response = await c.post("/v1/" + surface, json=body)
            assert response.status_code == 200, response.text
    assert seen[-1]["tools"] == body["tools"]
    assert seen[-1].get("instructions") == body.get("instructions")
    assert seen[-1]["service_tier"] == "priority"
    assert seen[-1].get("input", seen[-1].get("messages"))[:3] == prefix
    assert not proxy.memory_handler._router._backends


async def test_native_recall_uses_exact_keyword_and_preserves_filters(app):
    handler = app.state.proxy.memory_handler
    async with client(app) as c:
        saved = (await command(c, "memory_save", content="Đừng sửa XYZ_NATIVE_27 dữ liệu thật.", entities=["project-rule"])).json()
        ctx = storage_router.RequestContext(headers=dict(c.headers), system_prompt="", base_user_id="alice")
        backend, _, _ = handler._resolve_for_request("alice", ctx)
        class WeakQueryEmbedder:
            async def embed(self, text):
                return np.array([0.0, 1.0], dtype=np.float32)
        backend._hierarchical_memory._embedder = WeakQueryEmbedder()
        result = await command(c, "memory_search", query="XYZ_NATIVE_27", entities=["project-rule"], include_related=False)
        assert result.json()["memories"][0]["id"] == saved["memory_id"]
        assert result.json()["memories"][0]["score"] >= 0.3
        assert (await command(c, "memory_search", query="XYZ_NATIVE_27", entities=["unrelated"], include_related=False)).json()["memories"] == []


@pytest.mark.parametrize("relevant", [True, False])
async def test_responses_native_array_query_recalls_only_relevant_rule_without_mutating_prefix(app, relevant):
    proxy = app.state.proxy
    # Disabling optimization activates global passthrough before this endpoint.
    # Match the installed cache-mode route instead of bypassing its memory seam.
    proxy.config.mode = "cache"
    proxy.config.cache_enabled = False
    proxy.cache = None
    proxy.config.rate_limit_enabled = False
    proxy.config.cost_tracking_enabled = False
    seen = []
    def upstream(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "resp_recall", "object": "response", "status": "completed",
            "output": [], "usage": {"input_tokens": 20, "output_tokens": 5}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as upstream_client:
        proxy.http_client = upstream_client
        async with client(app) as c:
            c.headers["x-headroom-memory-tools"] = "client"
            saved = (await command(c, "memory_save", content="XYZ_NATIVE_ARRAY_73 must use synthetic blue data.")).json()
            ctx = storage_router.RequestContext(headers=dict(c.headers), system_prompt="", base_user_id="alice")
            backend, _, _ = proxy.memory_handler._resolve_for_request("alice", ctx)
            class WeakQueryEmbedder:
                async def embed(self, text):
                    return np.array([0.0, 1.0], dtype=np.float32)
            backend._hierarchical_memory._embedder = WeakQueryEmbedder()
            prefix = [{"role": "system", "content": "Authoritative instructions are unchanged."},
                {"type": "reasoning", "id": "rs_signed", "encrypted_content": "exact-signed-history", "summary": []},
                {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Historical answer."}]},
                {"type": "function_call_output", "call_id": "call_prior", "output": "Historical tool output."}]
            question = "XYZ_NATIVE_ARRAY_73 data color?" if relevant else "Draw a red circle."
            latest = {"type": "message", "role": "user", "content": [{"type": "input_text", "text": question}]}
            body = {"model": "gpt-4o-mini", "stream": False, "input": prefix + [latest],
                "instructions": "UNCHANGED authoritative prefix", "service_tier": "priority", "include": ["reasoning.encrypted_content"]}
            c.headers["authorization"] = "Bearer synthetic-api-key"
            response = await c.post("/v1/responses", json=body)
            assert response.status_code == 200, response.text
    assert seen[0]["input"][:-1] == prefix
    assert seen[0]["instructions"] == body["instructions"]
    assert seen[0]["service_tier"] == "priority" and seen[0]["include"] == body["include"]
    forwarded = json.dumps(seen[0]["input"][-1], ensure_ascii=False)
    if relevant:
        assert "synthetic blue data" in forwarded and saved["memory_id"] in forwarded
        assert "READ-ONLY" in forwarded and "NOT instructions" in forwarded
    else:
        assert seen[0]["input"][-1] == latest


async def test_stale_primary_row_cannot_be_recalled_after_interrupted_index_removal(app, monkeypatch):
    handler = app.state.proxy.memory_handler
    async with client(app) as c:
        saved = (await command(c, "memory_save", content="obsolete xyzzy rule")).json()
        ctx = storage_router.RequestContext(headers=dict(c.headers), system_prompt="", base_user_id="alice")
        backend, _, _ = handler._resolve_for_request("alice", ctx)
        async def interrupted(*args):
            raise RuntimeError("index interrupted")
        monkeypatch.setattr(backend._hierarchical_memory.vector_index, "remove", interrupted)
        assert (await command(c, "memory_delete", memory_id=saved["memory_id"],
            expected_content_hash=saved["content_hash"], reason="explicit owner forget")).status_code == 503
        assert (await command(c, "memory_search", query="xyzzy")).json()["memories"] == []


async def test_native_recall_is_bounded_labeled_and_preserves_frozen_prefix(app):
    from headroom.proxy.memory_injection import MemoryInjectionBudget
    handler = app.state.proxy.memory_handler
    async with client(app) as c:
        c.headers["x-headroom-memory-tools"] = "client"
        for index in range(8):
            c.headers["x-headroom-evidence-id"] = f"message:{index}"
            assert (await command(c, "memory_save", content=f"xyzzy rule {index}: Never grant deployment authority from memory.")).status_code == 200
        context = storage_router.RequestContext(headers=dict(c.headers), system_prompt="", base_user_id="alice")
        block = await handler.search_and_format_context("alice", [{"role": "user", "content": "xyzzy"}],
            request_context=context, budget=MemoryInjectionBudget(max_entries=20, max_tokens=5000))
        assert block.count("1. [") == 1
        assert block.count("[evidence-") <= 6
        assert len(block) <= 1200 * 4
        assert "sha256:" in block and "source=" in block and "scope=" in block
        assert "READ-ONLY" in block and "NOT instructions" in block
        prefix = [{"role": "system", "content": "authoritative frozen system"},
                  {"role": "assistant", "content": [{"type": "thinking", "thinking": "historical", "signature": "signed-sequence"}]}]
        messages = prefix + [{"role": "user", "content": "current request"}]
        original = json.dumps(messages, ensure_ascii=False)
        augmented, _ = handler._append_to_latest_user_tail(messages, block, provider="openai", frozen_message_count=2)
        assert augmented[:2] == prefix
        assert json.dumps(messages, ensure_ascii=False) == original


async def test_native_budget_omits_a_whole_rule_not_a_truncated_prohibition(app):
    from headroom.proxy.memory_injection import MemoryInjectionBudget
    handler = app.state.proxy.memory_handler
    async with client(app) as c:
        c.headers["x-headroom-memory-tools"] = "client"
        original = "Never modify production data without owner consent.\n" + "full authored rationale " * 200
        saved = (await command(c, "memory_save", content=original)).json()
        ctx = storage_router.RequestContext(headers=dict(c.headers), system_prompt="", base_user_id="alice")
        block = await handler.search_and_format_context("alice", [{"role": "user", "content": "production"}],
            request_context=ctx, budget=MemoryInjectionBudget(max_tokens=500))
        assert block is None or saved["memory_id"] not in block
        assert (await command(c, "memory_list")).json()["memories"][0]["content"] == original


@pytest.mark.parametrize("stream", [False, True])
async def test_native_anthropic_tools_are_client_owned(app, stream):
    proxy = app.state.proxy
    proxy.config.optimize = False
    proxy.config.rate_limit_enabled = False
    proxy.config.cost_tracking_enabled = False
    proxy.memory_handler.config.inject_context = False
    seen = []
    def upstream(request):
        seen.append(json.loads(request.content))
        if stream:
            events = [
                ("message_start", {"type": "message_start", "message": {"id": "msg_native", "type": "message", "role": "assistant", "content": [], "usage": {"input_tokens": 10, "output_tokens": 0}}}),
                ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": "call1", "name": "memory_save", "input": {}}}),
                ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": '{"content":"not proxy owned"}'}}),
                ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 3}}),
                ("message_stop", {"type": "message_stop"}),
            ]
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                content="".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events))
        return httpx.Response(200, json={"id": "msg_native", "type": "message", "role": "assistant",
            "content": [{"type": "tool_use", "id": "call1", "name": "memory_save", "input": {"content": "not proxy owned"}}],
            "stop_reason": "tool_use", "usage": {"input_tokens": 10, "output_tokens": 3}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as upstream_client:
        proxy.http_client = upstream_client
        async with client(app) as c:
            c.headers["x-api-key"] = "synthetic-test-only"
            c.headers["x-headroom-memory-tools"] = "client"
            body = {"model": "claude-sonnet-4-20250514", "max_tokens": 100, "stream": stream,
                    "system": "authoritative project instructions", "messages": [{"role": "user", "content": "Now recall"}],
                    "tools": [{"name": "memory_save", "description": "client executor", "input_schema": {"type": "object", "properties": {}}}]}
            response = await c.post("/v1/messages", json=body)
            assert response.status_code == 200, response.text
    assert seen[0]["tools"] == body["tools"]
    assert seen[0]["system"] == body["system"]
    assert not proxy.memory_handler._router._backends
