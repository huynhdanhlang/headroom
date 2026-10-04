"""Codex MCP exercises the canonical scoped HTTP/SQLite memory owner."""
import importlib.util
import json
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
import httpx
import pytest
from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams
from mcp.types import ListRootsResult, Root

from headroom.memory.proxy_mcp import create_proxy_memory_server
from tests.test_memory_commands import app as memory_app

app = memory_app  # shared real-store fixture without imported-name shadowing


@asynccontextmanager
async def memory_session(app, project="/synthetic/codex-a", roots=None):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1234)),
                                 base_url="http://127.0.0.1") as http:
        server = create_proxy_memory_server("http://127.0.0.1", project, http)
        async with create_client_server_memory_streams() as (client_streams, server_streams):
            async with anyio.create_task_group() as group:
                group.start_soon(server.run, *server_streams, server.create_initialization_options())
                async with ClientSession(*client_streams, list_roots_callback=roots) as session:
                    await session.initialize()
                    yield session
                group.cancel_scope.cancel()


async def call(session, name, **arguments):
    result = await session.call_tool(name, arguments)
    assert not result.isError, result
    return json.loads(result.content[0].text)


async def test_native_codex_save_fresh_search_update_forget_share_inference_store(app):
    async with memory_session(app) as session:
        assert {t.name for t in (await session.list_tools()).tools} == {
            "memory_save", "memory_search", "memory_list", "memory_update", "memory_delete"}
        saved = await call(session, "memory_save", content="Use synthetic fixtures in tests.")
        assert saved["status"] == "saved"
    # A new MCP session must read the same retained project backend, not its own DB.
    async with memory_session(app) as session:
        found = await call(session, "memory_search", query="synthetic fixtures")
        assert found["memories"][0]["id"] == saved["memory_id"]
        listed = await call(session, "memory_list")
        assert listed["memories"][0]["content_hash"] == saved["content_hash"]
        updated = await call(session, "memory_update", memory_id=saved["memory_id"],
            expected_content_hash=saved["content_hash"], new_content="Use synthetic fixtures, never production data.", reason="explicit correction")
        stale = await session.call_tool("memory_update", {"memory_id": saved["memory_id"],
            "expected_content_hash": saved["content_hash"], "new_content": "wrong", "reason": "stale"})
        assert stale.isError and "conflict" in stale.content[0].text.lower()
        forgotten = await call(session, "memory_delete", memory_id=updated["memory_id"],
            expected_content_hash=updated["content_hash"], reason="explicit owner forget")
        assert forgotten == {"status": "forgotten", "memory_id": updated["memory_id"], "history_retained": True}
        assert (await call(session, "memory_search", query="synthetic fixtures"))["memories"] == []


async def test_client_roots_follow_session_move_and_cannot_delete_other_project(app):
    location = "file:///synthetic/codex-a"

    async def roots(context):
        return ListRootsResult(roots=[Root(uri=location)])

    async with memory_session(app, roots=roots) as session:
        saved = await call(session, "memory_save", content="Project A convention.")
        location = "file:///synthetic/codex-b"
        assert (await call(session, "memory_list"))["memories"] == []
        result = await session.call_tool("memory_delete", {"memory_id": saved["memory_id"],
            "expected_content_hash": saved["content_hash"], "reason": "wrong project"})
        assert result.isError
        location = "file:///synthetic/codex-a"
        assert (await call(session, "memory_list"))["memories"][0]["id"] == saved["memory_id"]


async def test_invalid_arguments_and_ambiguous_roots_fail_before_store_creation(app):
    async with memory_session(app) as session:
        for arguments in ({"content": "fact", "user_id": "other"}, {"content": "fact", "cwd": "/other"},
                          {"content": "fact", "_evidence_key": "forged"}):
            assert (await session.call_tool("memory_save", arguments)).isError
    assert not app.state.proxy.memory_handler._router._backends

    async def roots(context):
        return ListRootsResult(roots=[Root(uri="file:///synthetic/a"), Root(uri="file:///synthetic/b")])

    async with memory_session(app, roots=roots) as session:
        assert (await session.call_tool("memory_save", {"content": "fact"})).isError
    assert not app.state.proxy.memory_handler._router._backends


async def test_disabled_backend_never_reports_durable_save(app):
    app.state.proxy.memory_handler.config.enabled = False
    async with memory_session(app) as session:
        result = await session.call_tool("memory_save", {"content": "fact"})
        assert result.isError and "not confirmed" in result.content[0].text


@pytest.mark.parametrize("url", ["https://remote.example", "http://127.0.0.1@remote.example", "http://localhost/?token=private"])
def test_proxy_adapter_refuses_remote_or_credential_urls(url):
    with pytest.raises(ValueError):
        create_proxy_memory_server(url, "/synthetic/project", None)


def test_normalized_filesystem_root_is_not_project_scope():
    with pytest.raises(ValueError):
        create_proxy_memory_server("http://127.0.0.1", "/tmp/..", None)


@pytest.mark.parametrize("response", [
    httpx.Response(503, text="secret /private/memory.db"),
    httpx.Response(200, json={"status": "error", "error": "secret /private/memory.db"}),
    httpx.Response(200, json={}),
    httpx.Response(200, content=b"x" * 262145),
])
async def test_invalid_http_results_do_not_become_success_or_expose_private_errors(response):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response)) as http:
        server = create_proxy_memory_server("http://127.0.0.1", "/synthetic/project", http)
        async with create_client_server_memory_streams() as (client_streams, server_streams):
            async with anyio.create_task_group() as group:
                group.start_soon(server.run, *server_streams, server.create_initialization_options())
                async with ClientSession(*client_streams) as session:
                    await session.initialize()
                    result = await session.call_tool("memory_save", {"content": "fact"})
                    assert result.isError
                    assert "secret" not in result.content[0].text and "/private" not in result.content[0].text
                group.cancel_scope.cancel()


def test_host_launcher_forwards_actual_session_cwd_without_project_or_secret_mounts(tmp_path):
    spec = importlib.util.spec_from_file_location("codex_memory_launcher",
        Path(__file__).resolve().parents[1] / "scripts/codex_memory_mcp.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    docker_command = module.docker_command
    command = docker_command("sha256:" + "a" * 64, "http://127.0.0.1:4444", tmp_path)
    assert command[-2:] == ["--project-root", str(tmp_path)]
    assert "--read-only" in command and "-i" in command and "-t" not in command
    # This process serves stdio, not the base image's proxy HTTP health endpoint.
    assert "--no-healthcheck" in command
    assert "--volume" not in command and "-v" not in command and "--mount" not in command
    assert command[command.index("--cap-drop") + 1] == "ALL"
    with pytest.raises(ValueError):
        docker_command("headroom:latest", "http://127.0.0.1:4444", tmp_path)
