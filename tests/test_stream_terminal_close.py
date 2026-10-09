"""Clients may close on the terminal SSE frame, before transport EOF."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from headroom.backends.base import StreamEvent
from headroom.proxy.server import HeadroomProxy


@pytest.fixture
def stream_proxy():
    proxy = object.__new__(HeadroomProxy)
    proxy.http_client = MagicMock(spec=httpx.AsyncClient)
    proxy.config = MagicMock()
    proxy.config.memory_enabled = False
    proxy.config.ccr_inject_tool = False
    proxy.config.retry_max_attempts = 1
    proxy.config.retry_base_delay_ms = 0
    proxy.config.retry_max_delay_ms = 0
    proxy.memory_handler = None
    # Observe the actual generator's accounting boundary, not a copied loop.
    proxy._finalize_stream_response = AsyncMock()
    return proxy


async def open_stream(proxy, chunks, provider, endpoint, *, headers=None, session_key=None):
    upstream = AsyncMock()
    upstream.headers = httpx.Headers({"content-type": "text/event-stream"})
    upstream.status_code = 200

    async def source():
        for chunk in chunks:
            yield chunk

    upstream.aiter_bytes = source
    proxy.http_client.build_request.return_value = MagicMock()
    proxy.http_client.send = AsyncMock(return_value=upstream)
    response = await proxy._stream_response(
        url="https://example.test/v1/" + endpoint,
        headers=headers or {},
        body={"model": "test", "stream": True, "messages": []},
        provider=provider,
        model="test",
        request_id="terminal-close-test",
        original_tokens=12,
        optimized_tokens=10,
        tokens_saved=2,
        transforms_applied=[],
        tags={},
        optimization_latency=0.0,
        session_key=session_key,
    )
    return response.body_iterator, upstream


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True], ids=["close", "cancel"])
@pytest.mark.parametrize(
    "provider,endpoint,wire",
    [
        (
            "openai",
            "responses",
            b'event: response.completed\ndata: {"type":"response.completed","response":{"usage":{"input_tokens":10,"output_tokens":1}}}\n\n',
        ),
        (
            "openai",
            "responses",
            b'event: response.incomplete\ndata: {"type":"response.incomplete","response":{"usage":{"input_tokens":10,"output_tokens":1}}}\n\n',
        ),
        (
            "openai",
            "chat/completions",
            b'data: {"usage":{"prompt_tokens":10,"completion_tokens":1}}\n\ndata: [DONE]\n\n',
        ),
        (
            "anthropic",
            "messages",
            b'event: message_start\ndata: {"type":"message_start","message":{"usage":{"input_tokens":10}}}\n\nevent: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":1}}\n\nevent: message_stop\ndata: {"type":"message_stop"}\n\n',
        ),
    ],
    ids=["responses-completed", "responses-incomplete", "chat-done", "anthropic-stop"],
)
async def test_terminal_close_keeps_success_and_authoritative_usage(
    stream_proxy,
    provider,
    endpoint,
    wire,
    cancel,
):
    iterator, upstream = await open_stream(stream_proxy, [wire], provider, endpoint)
    assert await anext(iterator) == wire
    if cancel:
        with pytest.raises(asyncio.CancelledError):
            await iterator.athrow(asyncio.CancelledError())
    else:
        await iterator.aclose()
    recorded = stream_proxy._finalize_stream_response.await_args.kwargs
    assert recorded["status_code"] == 200
    assert recorded["stream_state"]["input_tokens"] == 10
    assert recorded["stream_state"]["output_tokens"] == 1
    upstream.aclose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "wire",
    [
        b'event: response.output_text.delta\ndata: {"type":"response.output_text.delta","delta":"partial"}\n\n',
        b'event: response.failed\ndata: {"type":"response.failed","response":{"error":{"code":"server_error"}}}\n\n',
        b'event: response.completed\ndata: {"type":"response.completed"}',
        b'event: error\ndata: {"type":"error"}\n\nevent: response.completed\ndata: {"type":"response.completed"}\n\n',
    ],
    ids=["before-terminal", "provider-error", "partial-terminal", "error-then-terminal"],
)
async def test_non_successful_close_remains_failed(stream_proxy, wire):
    iterator, upstream = await open_stream(stream_proxy, [wire], "openai", "responses")
    assert await anext(iterator) == wire
    await iterator.aclose()
    assert stream_proxy._finalize_stream_response.await_args.kwargs["status_code"] == 502
    upstream.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_terminal_close_does_not_yield_pending_messages_during_cleanup(stream_proxy):
    session = "terminal-close-with-pending"
    wire = b'event: message_stop\ndata: {"type":"message_stop"}\n\n'
    iterator, upstream = await open_stream(
        stream_proxy,
        [wire],
        "anthropic",
        "messages",
        headers={"user-agent": "claude-code/1.2.3", "x-headroom-session-id": session},
        session_key=session,
    )
    stream_proxy._queue_mid_turn_message(
        session, {"messages": [{"role": "user", "content": "queued"}]}
    )
    assert await anext(iterator) == wire
    await iterator.aclose()
    assert session not in stream_proxy._active_streams
    assert session not in stream_proxy._mid_turn_queues
    assert stream_proxy._finalize_stream_response.await_args.kwargs["status_code"] == 200
    upstream.aclose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("dialect", ["openai", "anthropic"])
@pytest.mark.parametrize("successful", [False, True])
async def test_backend_terminal_close_preserves_accounting_and_prefix(
    stream_proxy,
    dialect,
    successful,
):
    backend = MagicMock()
    backend.name = "test-backend"
    stream_proxy.config.log_full_messages = False
    stream_proxy._record_request_outcome = AsyncMock()
    tracker = MagicMock()
    tracker.classify_cache_miss.return_value.is_miss = False
    arguments = {
        "body": {"messages": []},
        "headers": {},
        "model": "test",
        "request_id": "backend-close",
        "original_tokens": 12,
        "optimized_tokens": 10,
        "tokens_saved": 2,
        "transforms_applied": [],
        "tags": {},
        "optimization_latency": 0.0,
        "prefix_tracker": tracker,
        "backend": backend,
    }
    if dialect == "openai":
        chunk = b'data: {"usage":{"prompt_tokens":10,"completion_tokens":1,"prompt_tokens_details":{"cached_tokens":6}}}\n\n'
        chunk += (
            b"data: [DONE]\n\n" if successful else b'data: {"error":{"type":"server_error"}}\n\n'
        )

        async def source(body, headers):
            yield chunk

        backend.stream_openai_message = source
        result = await stream_proxy._stream_openai_via_backend(
            **arguments,
            start_time=time.time(),
        )
    else:

        async def source(body, headers):
            yield StreamEvent(
                event_type="message_start",
                data={
                    "type": "message_start",
                    "message": {"usage": {"input_tokens": 10, "cache_read_input_tokens": 6}},
                },
            )
            yield StreamEvent(
                event_type="message_delta",
                data={
                    "type": "message_delta",
                    "usage": {"output_tokens": 1},
                },
            )
            yield StreamEvent(
                event_type="message_stop" if successful else "error",
                data={
                    "type": "message_stop" if successful else "error",
                },
            )

        backend.stream_message = source
        result = await stream_proxy._stream_response_bedrock(**arguments, provider="anthropic")
    iterator = result.body_iterator
    if dialect == "anthropic":
        for _ in range(3):  # ping, message_start, message_delta
            await anext(iterator)
    await anext(iterator)
    await iterator.aclose()
    outcome = stream_proxy._record_request_outcome.await_args.args[0]
    assert outcome.status_code == (200 if successful else 502)
    assert outcome.output_tokens == 1
    assert outcome.cache_read_tokens == 6
    if successful:
        assert tracker.update_from_response.call_count == 1
    else:
        tracker.update_from_response.assert_not_called()
