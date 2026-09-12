"""Request state must survive fan-out without leaking across shared workers."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar

import pytest

from headroom.proxy.server import ProxyConfig, create_app
from headroom.transforms.compression_units import find_content_router
from headroom.transforms.content_router import ContentRouter, ContentRouterConfig


class Counter:
    def count_text(self, text):
        return max(1, len(text) // 4)


def rows(tag):
    return json.dumps([{"id": i, "value": f"{tag}-{i}", "status": "ok"} for i in range(100)])


def state(router):
    return (
        getattr(router, "_runtime_target_ratio", None),
        getattr(router, "_runtime_skip_kompress", False),
        getattr(router, "_runtime_compression_policy", None),
        dict(getattr(router, "_tool_call_args", {})),
        dict(getattr(router, "_tool_call_commands", {})),
        set(getattr(router, "_protect_read_tool_ids", set())),
        set(getattr(router, "_protect_read_msg_indices", set())),
        getattr(router, "_runtime_force_kompress", False),
        getattr(router, "_runtime_kompress_model", None),
    )


def test_reused_apply_worker_cleans_up_options_and_maps():
    router = ContentRouter(ContentRouterConfig(lossless=True, enable_kompress=False))
    messages = [
        {"role": "user", "content": "go"},
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t", "content": rows("one")}],
        },
    ]
    with ThreadPoolExecutor(max_workers=1) as pool:
        before = pool.submit(state, router).result()
        pool.submit(
            router.apply, messages, Counter(), target_ratio=0.2, skip_kompress=True
        ).result()
        assert pool.submit(state, router).result() == before


def test_nested_scope_and_exception_restore_caller_state():
    router = ContentRouter(ContentRouterConfig(lossless=True, enable_kompress=False))
    router._runtime_target_ratio = 0.4
    before = state(router)
    with pytest.raises(RuntimeError, match="audit"):
        with router.request_scope():
            assert router._runtime_target_ratio is None
            router._runtime_target_ratio = 0.8
            router._tool_call_args["parent"] = "kept"
            with router.request_scope():
                assert router._tool_call_args == {}
                router._tool_call_args["child"] = "temporary"
            assert router._tool_call_args == {"parent": "kept"}
            assert router._runtime_target_ratio == 0.8
            raise RuntimeError("audit")
    assert state(router) == before


def test_read_protection_and_tool_maps_cannot_be_overwritten(monkeypatch):
    monkeypatch.setenv("HEADROOM_PROTECT_READS", "1")
    router = ContentRouter(ContentRouterConfig(lossless=True, enable_kompress=False))
    entered = threading.Event()
    done = threading.Event()
    observed = {}
    original = router.compress

    def probe(*args, **kwargs):
        if threading.current_thread().name == "read-owner" and "before" not in observed:
            observed["before"] = state(router)
            entered.set()
            assert done.wait(10)
            observed["after"] = state(router)
        return original(*args, **kwargs)

    monkeypatch.setattr(router, "compress", probe)

    def messages(command, tag):
        return [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "shared",
                        "type": "function",
                        "function": {
                            "name": "exec_command",
                            "arguments": json.dumps({"cmd": command}),
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "shared",
                "content": "def example():\n    return 42\n",
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "data", "content": rows(tag)}],
            },
        ]

    def first():
        threading.current_thread().name = "read-owner"
        router.apply(messages("cat src/a.py", "a"), Counter())

    def second():
        assert entered.wait(10)
        try:
            router.apply(messages("printf data", "b"), Counter())
        finally:
            done.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(first), pool.submit(second)
        a.result(timeout=20)
        b.result(timeout=20)
    assert observed["before"][4]["shared"] == "cat src/a.py"
    assert observed["before"][5], "fixture must actually activate read protection"
    assert observed["after"] == observed["before"]


@pytest.mark.parametrize("small_batches", [False, True])
def test_responses_unit_and_batch_workers_inherit_context(monkeypatch, small_batches):
    from headroom.proxy.handlers import openai

    app = create_app(
        ProxyConfig(
            optimize=True,
            cache_enabled=False,
            rate_limit_enabled=False,
            cost_tracking_enabled=False,
        )
    )
    proxy = app.state.proxy
    router = find_content_router(proxy.openai_pipeline)
    assert router is not None
    router.config.lossless = True
    router.config.enable_kompress = False
    trace = ContextVar("audit_request", default=None)
    token = trace.set("this-request")
    seen = []
    lock = threading.Lock()
    parent = threading.get_ident()
    original = router.compress

    def probe(*args, **kwargs):
        with lock:
            seen.append((threading.get_ident(), trace.get(), state(router)))
        return original(*args, **kwargs)

    monkeypatch.setattr(router, "compress", probe)
    monkeypatch.setattr(openai, "_openai_responses_unit_parallelism", lambda: 2)
    count = 32 if small_batches else 2
    payload = {
        "model": "gpt-5-codex",
        "input": [
            {
                "type": "function_call_output",
                "call_id": f"call-{i}",
                "output": (f"item-{i}: " + "data " * 35) if small_batches else rows(f"large-{i}"),
            }
            for i in range(count)
        ],
    }
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            monkeypatch.setattr(openai, "_openai_responses_unit_executor", lambda: workers)
            proxy._compress_openai_responses_live_text_units_with_router(
                payload, model="gpt-5-codex", request_id="scope-audit"
            )
    finally:
        trace.reset(token)
    assert len(seen) >= 2, "fixture must enter the router multiple times"
    assert any(tid != parent for tid, _, _ in seen), "fixture must exercise worker submission"
    assert all(value == "this-request" for _, value, _ in seen)


def test_responses_entry_does_not_inherit_previous_apply_options(monkeypatch):
    app = create_app(
        ProxyConfig(
            optimize=True,
            cache_enabled=False,
            rate_limit_enabled=False,
            cost_tracking_enabled=False,
        )
    )
    proxy = app.state.proxy
    router = find_content_router(proxy.openai_pipeline)
    assert router is not None
    router.config.lossless = True
    router.config.enable_kompress = False
    router._runtime_skip_kompress = True
    router._tool_call_commands = {"unrelated": "cat foreign.py"}
    caller = state(router)
    seen = []
    original = router.compress

    def probe(*args, **kwargs):
        seen.append(state(router))
        return original(*args, **kwargs)

    monkeypatch.setattr(router, "compress", probe)
    payload = {
        "model": "gpt-5-codex",
        "input": [{"type": "function_call_output", "call_id": "x", "output": rows("fresh")}],
    }
    proxy._compress_openai_responses_live_text_units_with_router(
        payload, model="gpt-5-codex", request_id="fresh-request"
    )
    assert seen
    assert all(not snapshot[1] and snapshot[4] == {} for snapshot in seen)
    assert state(router) == caller


@pytest.mark.parametrize("task_count", [1, 3])
def test_watchdog_and_fanout_preserve_all_request_options(monkeypatch, task_count):
    from dataclasses import replace

    from headroom.transforms import content_router
    from headroom.transforms.compression_policy import policy_default_payg

    monkeypatch.setattr(content_router, "_compression_deadline_seconds", lambda: 5.0)
    monkeypatch.setenv("HEADROOM_COMPRESS_WORKERS", "3")
    router = ContentRouter(ContentRouterConfig(lossless=True, enable_kompress=False))
    policy = replace(policy_default_payg(), toin_read_only=True)
    seen = []
    lock = threading.Lock()
    original = router.compress
    parent = threading.get_ident()

    def probe(*args, **kwargs):
        with lock:
            seen.append((threading.get_ident(), state(router)))
        return original(*args, **kwargs)

    monkeypatch.setattr(router, "compress", probe)
    messages = [{"role": "user", "content": "go"}] + [
        {"role": "tool", "tool_call_id": str(i), "content": rows(f"watch-{i}")}
        for i in range(task_count)
    ]
    router.apply(
        messages,
        Counter(),
        target_ratio=0.25,
        force_kompress=True,
        skip_kompress=True,
        kompress_model="audit-model",
        compression_policy=policy,
    )
    assert seen and all(tid != parent for tid, _ in seen)
    for _, snapshot in seen:
        assert snapshot[0] == 0.25
        assert snapshot[1] is True
        assert snapshot[2] == policy
        assert snapshot[2].toin_read_only is True
        assert snapshot[7] is True
        assert snapshot[8] == "audit-model"
    assert router._runtime_compression_policy is None


def test_responses_preserves_unavailable_adapter_fallback(monkeypatch):
    import builtins

    from headroom.proxy.handlers.openai import OpenAIHandlerMixin

    original_import = builtins.__import__

    def unavailable(name, *args, **kwargs):
        if name == "headroom.transforms.compression_units":
            raise ImportError("audit adapter unavailable")
        return original_import(name, *args, **kwargs)

    class Proxy(OpenAIHandlerMixin):
        pass

    monkeypatch.setattr(builtins, "__import__", unavailable)
    payload = {"input": [{"type": "function_call_output", "call_id": "t", "output": "kept"}]}
    result = Proxy()._compress_openai_responses_live_text_units_with_router(
        payload, model="gpt-5-codex", request_id="fallback"
    )
    assert result == (payload, False, 0, [], {}, [], 0)
