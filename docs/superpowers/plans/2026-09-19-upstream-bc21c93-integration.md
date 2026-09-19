# Upstream `bc21c937` Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the 24 accepted upstream commits through `bc21c937`, preserve the maintenance fork's stronger accounting and request-scope guarantees, and add RTK-aware source-read protection for the local Codex workflow.

**Architecture:** Use the exact upstream commit and its signed `code-bc21c93` multi-architecture image as the structural/native base. Keep the fork as a small Python/frontend overlay: combine upstream's new router/Responses/gateway behavior with the fork's per-option `ContextVar` request scope, then verify savings, latency, context stability, and build reproducibility independently.

**Tech Stack:** Python 3.13, FastAPI, pytest, `contextvars`, Docker Buildx, upstream Rust/PyO3 image, Ruff 0.16.7, Git merge workflow.

**Spec:** `docs/superpowers/specs/2026-09-19-upstream-bc21c93-integration-design.md`

## Global Constraints

- Merge exactly `bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9`; do not merge a moving `upstream/main` ref.
- Pin `ghcr.io/headroomlabs-ai/headroom:code-bc21c93@sha256:cc517ad22cc1a0c4618cc1bdea612b345f9c0928c13958dae86c9f1d481c380d` as the native/dependency base.
- Keep protected file reads, cached prefixes, signed thinking blocks, retrieval markers, and session identity exact and recoverable.
- Keep `original_tokens - optimized_tokens == tokens_saved` for successful compression outcomes.
- When request logs exist, Agent Usage rows and totals use the same bounded request-log window; global counters are only the empty-log fallback.
- Request options, tool maps, read-protection sets, watchdogs, Responses workers, fan-out workers, nested scopes, exceptions, and reused workers must remain request-local.
- Use Ruff 0.16.7, the version pinned by the integrated upstream source.
- Build only from a clean commit; do not deploy or alter a live service in this plan.
- Benchmark results describe the synthetic router workload only, not model inference speed, subscription quota, or production cost savings.

## Review Focus

- A Responses `custom_tool_call` script with several `exec_command` calls, including one `rtk proxy` source read, must protect its single output byte-for-byte; pinned in Task 2's end-to-end test.
- Nested scopes, exceptions, reused executor threads, watchdog threads, Responses workers, and multi-task fan-out must restore or inherit the correct request state; pinned in Task 1's combined router-scope suites.
- Request-log rows must not use deduplicated global savings as their denominator, including when global savings are zero or much larger than the log window; pinned by `test_agent_shares_and_totals_use_the_same_logged_request_scope` in Task 1.
- A tag/digest mismatch or a future native/dependency delta against the pinned base must fail before Docker build; pinned by Task 3's exact-base and native-input tests.
- Oversized chunked runtime-env input and a disabled gateway contract must retain their security/feature-gate behavior after the merge; pinned by Task 4's runtime-env and gateway suites.

---

### Task 1: Merge the exact upstream commit and preserve fork invariants

**Files:**

- Merge: the 96 files changed by `63c5df8a..bc21c937`
- Resolve: `headroom/transforms/content_router.py`
- Resolve: `tests/test_content_router_concurrency.py`
- Resolve: `tests/test_transforms_content_router.py`
- Audit: `headroom/proxy/handlers/openai.py`
- Audit: `headroom/proxy/server.py`
- Test: `tests/test_ai_motion_router_scope.py`
- Test: `tests/test_responses_savings_denominator.py`
- Test: `tests/test_dashboard_agent_usage.py`
- Test: `tests/test_openai_responses_read_protection.py`

**Interfaces:**

- Consumes: `ContentRouter.apply(...)`, `ContentRouter.compress(...)`, Responses compression workers, and the upstream gateway/Responses additions at `bc21c937`.
- Produces: `ContentRouter.request_scope() -> Iterator[None]`; request-local descriptor-backed fields `_runtime_target_ratio`, `_runtime_force_kompress`, `_runtime_skip_kompress`, `_runtime_kompress_model`, `_runtime_compression_policy`, `_tool_call_args`, `_tool_call_commands`, `_protect_read_tool_ids`, and `_protect_read_msg_indices`.

- [ ] **Step 1: Verify the integration branch and immutable merge target**

Run:

```bash
git status --short --branch
git rev-parse HEAD
git rev-parse upstream/main
git cat-file -t bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9
```

Expected: branch `codex/sync-upstream-bc21c93`, a clean worktree, `upstream/main` and the named commit both resolve to `bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9`, and `git cat-file` prints `commit`.

- [ ] **Step 2: Run the fork's pre-merge invariant baseline**

Run:

```bash
python -m pytest -q \
  tests/test_ai_motion_router_scope.py \
  tests/test_content_router_concurrency.py \
  tests/test_transforms_content_router.py \
  tests/test_compression_policy_toin_gate.py \
  tests/test_responses_savings_denominator.py \
  tests/test_dashboard_agent_usage.py
```

Expected: PASS. A failure is a baseline stop condition and must be diagnosed before merging.

- [ ] **Step 3: Start the non-rewriting merge**

Run:

```bash
git merge --no-ff --no-commit bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9
```

Expected: Git stops with conflicts only in `headroom/transforms/content_router.py`, `tests/test_content_router_concurrency.py`, and `tests/test_transforms_content_router.py`; `headroom/proxy/handlers/openai.py` and `headroom/proxy/server.py` auto-merge.

- [ ] **Step 4: Resolve `ContentRouter` around the fork's scoped descriptors**

Keep upstream's imports, content-detection additions, custom-tool parsing, replay/session behavior, and other non-conflicting code. Replace upstream's single mutable `_PerRequestRuntimeState` object with the fork's per-option descriptors and resettable scope:

```python
_PER_REQUEST_DEFAULTS = {
    "_runtime_target_ratio": None,
    "_runtime_force_kompress": False,
    "_runtime_skip_kompress": False,
    "_runtime_kompress_model": None,
    "_runtime_compression_policy": None,
}
_PER_REQUEST_FACTORIES = {
    "_tool_call_args": dict,
    "_tool_call_commands": dict,
    "_protect_read_tool_ids": set,
    "_protect_read_msg_indices": set,
}
_REQUEST_UNSET = object()


class _PerRequestOption:
    __slots__ = ("_name",)

    def __set_name__(self, owner: type, name: str) -> None:
        self._name = name

    def _var(self, obj: "ContentRouter") -> ContextVar[Any]:
        return obj.__dict__["_per_request_vars"][self._name]

    def __get__(self, obj: "ContentRouter | None", objtype: type | None = None) -> Any:
        if obj is None:
            return self
        variable = self._var(obj)
        value = variable.get()
        if value is _REQUEST_UNSET:
            value = _request_default(self._name)
            variable.set(value)
        return value

    def __set__(self, obj: "ContentRouter", value: Any) -> None:
        self._var(obj).set(value)
```

Retain `_scoped_router_request`, decorate every top-level request entry used by the fork, eagerly create each router's `_per_request_vars` in `__init__`, and keep `request_scope()` resetting tokens in reverse order in `finally`. Do not keep upstream's `self._runtime_state_var.set(_PerRequestRuntimeState())` at the top of `apply()` because it neither restores caller state nor protects direct Responses entry points.

- [ ] **Step 5: Preserve worker-context propagation and upstream behavior**

The single-task watchdog must run `copy_context().run(_run)`, every fan-out task must use a fresh `copy_context()` instance, and Responses batch/unit submissions in `headroom/proxy/handlers/openai.py` must remain `executor.submit(copy_context().run, ...)`. Keep upstream's `custom_tool_call` parsing and session/replay additions unchanged.

Expected source shapes:

```python
worker = threading.Thread(
    target=copy_context().run,
    args=(_run,),
    name="headroom-single-compress-watchdog",
    daemon=True,
)
```

```python
futures.append(
    executor.submit(
        copy_context().run,
        self._timed_compress,
        task_content,
        task_ctx,
        task_bias,
        task_detection,
    )
)
```

- [ ] **Step 6: Combine both sides of the conflicted tests**

Keep all five upstream concurrency tests in `tests/test_content_router_concurrency.py`:

```text
test_concurrent_apply_calls_leak_compression_policy_across_requests
test_parallel_fanout_workers_lose_this_requests_runtime_state
test_single_pending_task_watchdog_thread_loses_this_requests_runtime_state
test_concurrent_apply_calls_leak_read_protection_state_across_requests
test_concurrent_apply_calls_with_internal_fanout_do_not_cross_contaminate
```

Also keep the fork's broader cases in `tests/test_ai_motion_router_scope.py` and the local concurrency/fan-out cases at the end of `tests/test_transforms_content_router.py`. Keep upstream's opening-task and replay-guarantee tests added to that same file.

- [ ] **Step 7: Audit the two auto-merged semantic hotspots**

Confirm in `headroom/proxy/handlers/openai.py` that native Responses array items are included in the HTTP savings denominator and that upstream gateway/custom-tool changes remain. Confirm in `headroom/proxy/server.py` that Agent Usage uses the request-log denominator when logs exist while retaining upstream's gateway install, Kompress background warm-up, and 64 KiB runtime-env body limit.

Run:

```bash
python -m pytest -q \
  tests/test_responses_savings_denominator.py \
  tests/test_dashboard_agent_usage.py \
  tests/test_openai_responses_read_protection.py \
  tests/test_ai_motion_router_scope.py \
  tests/test_content_router_concurrency.py \
  tests/test_transforms_content_router.py \
  tests/test_compression_policy_toin_gate.py
```

Expected: PASS, including `test_array_input_is_included_in_http_savings_denominator`, `test_agent_shares_and_totals_use_the_same_logged_request_scope`, all upstream #3556 cases, and all fork scope/restoration cases.

- [ ] **Step 8: Check the resolution and commit the merge**

Run:

```bash
git diff --check
rg -n '^(<<<<<<<|=======|>>>>>>>)' headroom tests
git status --short
git add headroom/transforms/content_router.py tests/test_content_router_concurrency.py tests/test_transforms_content_router.py
git commit -m "merge: sync upstream main at bc21c937"
```

Expected: no conflict markers, all merge paths resolved, and a two-parent merge commit.

### Task 2: Protect `rtk proxy` source reads without suppressing useful compression

**Files:**

- Modify: `headroom/transforms/content_router.py` near `_bash_program`
- Test: `tests/test_transforms_content_router.py`
- Test: `tests/test_openai_responses_read_protection.py`

**Interfaces:**

- Consumes: `_bash_program(command: str) -> tuple[str, list[str]]`, `_is_read_command(command: str) -> bool`, `_bash_command_is_search(command: str, search_commands: frozenset[str]) -> bool`, and upstream `_custom_tool_call_commands(raw: Any) -> list[str]`.
- Produces: the same signatures, with the token sequence `rtk proxy` treated as one compound wrapper while a standalone executable named `proxy` remains the real program.

- [ ] **Step 1: Add failing parser and classification regressions**

Add to `tests/test_transforms_content_router.py`:

```python
@pytest.mark.parametrize(
    "command",
    [
        "rtk proxy sed -n '1,120p' src/app.py",
        "rtk proxy nl -ba src/app.py",
        "rtk proxy cat src/app.py",
    ],
)
def test_rtk_proxy_compound_wrapper_preserves_source_read_classification(command):
    from headroom.transforms.content_router import _is_read_command

    assert _is_read_command(command) is True


def test_rtk_proxy_compound_wrapper_keeps_derived_output_compressible():
    from headroom.transforms.content_router import (
        _bash_command_is_search,
        _bash_program,
        _is_read_command,
    )

    assert _bash_program("rtk proxy rg -n request_scope headroom") == (
        "rg",
        ["-n", "request_scope", "headroom"],
    )
    assert _bash_command_is_search(
        "rtk proxy rg -n request_scope headroom", frozenset({"rg"})
    )
    assert not _is_read_command("rtk proxy pytest -q tests/test_router.py")
    assert not _is_read_command("rtk proxy cat Cargo.lock")
    assert not _is_read_command("rtk proxy cat src/app.py > /tmp/app-copy.py")
    assert _bash_program("proxy cat src/app.py")[0] == "proxy"
    assert _bash_program("rtk proxy") == ("", [])
```

- [ ] **Step 2: Add the end-to-end Responses regression**

Add to `tests/test_openai_responses_read_protection.py`, using the upstream `_codex_exec_call` and `_codex_exec_output` fixtures:

```python
def test_responses_codex_rtk_proxy_read_stays_verbatim(monkeypatch):
    monkeypatch.setenv("HEADROOM_PROTECT_READS", "1")
    handler = _handler_with_router(_lossy_router())
    output = _codex_exec_output("call_rtk", _NL_OUTPUT)
    payload = {
        "model": "gpt-5",
        "input": [
            _codex_exec_call("call_rtk", "rtk proxy sed -n '20,115p' src/app.py"),
            output,
        ],
    }

    new_payload, _modified, _s, _t, _u, _c, _a = _run(handler, payload)

    assert new_payload["input"][1] == output
```

- [ ] **Step 3: Run the regressions and verify they fail for the intended reason**

Run:

```bash
python -m pytest -q \
  tests/test_transforms_content_router.py::test_rtk_proxy_compound_wrapper_preserves_source_read_classification \
  tests/test_transforms_content_router.py::test_rtk_proxy_compound_wrapper_keeps_derived_output_compressible \
  tests/test_openai_responses_read_protection.py::test_responses_codex_rtk_proxy_read_stays_verbatim
```

Expected: the read/parser assertions fail because `_bash_program` currently returns `("proxy", ...)`; the standalone `proxy` assertion continues to pass.

- [ ] **Step 4: Implement the minimal compound-wrapper parser**

Special-case `rtk` before the generic `_SHELL_WRAPPERS` branch:

```python
        if base == "rtk":
            i += 1
            while i < len(toks) and toks[i].startswith("-"):
                i += 1
            if i < len(toks) and toks[i].rsplit("/", 1)[-1].lower() == "proxy":
                i += 1
            continue
        if base in _SHELL_WRAPPERS:
            i += 1
            while i < len(toks) and (
                toks[i].startswith("-") or toks[i].replace(".", "", 1).isdigit()
            ):
                i += 1
            continue
```

Leave `proxy` out of `_SHELL_WRAPPERS`; this prevents unrelated `proxy` executables from being peeled.

- [ ] **Step 5: Run the focused and neighboring tests**

Run:

```bash
python -m pytest -q \
  tests/test_transforms_content_router.py::test_rtk_proxy_compound_wrapper_preserves_source_read_classification \
  tests/test_transforms_content_router.py::test_rtk_proxy_compound_wrapper_keeps_derived_output_compressible \
  tests/test_openai_responses_read_protection.py \
  tests/test_bash_search_lossless_fold.py
```

Expected: PASS. Source reads remain byte-exact; RTK-wrapped `rg` and pytest output remain eligible for their existing compression paths.

- [ ] **Step 6: Commit the RTK optimization**

Run:

```bash
git add headroom/transforms/content_router.py tests/test_transforms_content_router.py tests/test_openai_responses_read_protection.py
git commit -m "fix(router): classify rtk proxy source reads"
```

### Task 3: Repin the maintained image and build guard

**Files:**

- Modify: `scripts/build_ai_motion.py`
- Modify: `docker/Dockerfile.ai-motion`
- Modify: `tests/test_ai_motion_build_guard.py`
- Modify: `FORK.md`

**Interfaces:**

- Consumes: `validate_overlay(changes, copied)`, `copied_sources(recipe)`, the upstream image's Python 3.13 site-packages layout, and the exact upstream commit.
- Produces: `UPSTREAM_BASE == "bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9"` and `BASE_IMAGE == "ghcr.io/headroomlabs-ai/headroom:code-bc21c93@sha256:cc517ad22cc1a0c4618cc1bdea612b345f9c0928c13958dae86c9f1d481c380d"`.

- [ ] **Step 1: Add a failing exact-base regression**

Add to `tests/test_ai_motion_build_guard.py`:

```python
def test_guard_pins_integrated_upstream_source_and_native_image():
    module = guard()
    assert module.UPSTREAM_BASE == "bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9"
    assert module.BASE_IMAGE == (
        "ghcr.io/headroomlabs-ai/headroom:code-bc21c93@"
        "sha256:cc517ad22cc1a0c4618cc1bdea612b345f9c0928c13958dae86c9f1d481c380d"
    )
    assert module.SITE_PACKAGES == "/usr/local/lib/python3.13/site-packages/"
```

- [ ] **Step 2: Run the test and verify the old base fails**

Run:

```bash
python -m pytest -q tests/test_ai_motion_build_guard.py::test_guard_pins_integrated_upstream_source_and_native_image
```

Expected: FAIL showing the old `63c5df8a` source/image values.

- [ ] **Step 3: Update the exact source/image constants and Docker base**

Set in `scripts/build_ai_motion.py`:

```python
UPSTREAM_BASE = "bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9"
BASE_IMAGE = "ghcr.io/headroomlabs-ai/headroom:code-bc21c93@sha256:cc517ad22cc1a0c4618cc1bdea612b345f9c0928c13958dae86c9f1d481c380d"
SITE_PACKAGES = "/usr/local/lib/python3.13/site-packages/"
```

Use the identical `BASE_IMAGE` string in the single `FROM` instruction in `docker/Dockerfile.ai-motion`. Keep explicit single-file `COPY` instructions for every runtime file changed relative to `UPSTREAM_BASE`; do not copy upstream-only files already present in the pinned image.

- [ ] **Step 4: Update the fork contract**

In `FORK.md`, change the upstream base to `bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9`, record the accepted 24-commit range, document that #3556's tests were adopted while the broader fork isolation remains, and record the pinned `code-bc21c93` digest. Preserve the existing warnings about synthetic benchmarks and live rollout.

- [ ] **Step 5: Run build-guard tests**

Run:

```bash
python -m pytest -q tests/test_ai_motion_build_guard.py tests/test_ai_motion_benchmark_isolation.py
```

Expected: PASS, including exact base/digest enforcement, native/dependency rejection, explicit copy coverage, and isolated benchmark state.

- [ ] **Step 6: Commit the new build base**

Run:

```bash
git add scripts/build_ai_motion.py docker/Dockerfile.ai-motion tests/test_ai_motion_build_guard.py FORK.md
git commit -m "build: repin maintenance overlay to bc21c937"
```

### Task 4: Run the integrated regression and quality matrix

**Files:**

- Verify: fork and upstream tests listed below
- Verify: every Python file changed relative to `bc21c937`

**Interfaces:**

- Consumes: Tasks 1-3's integrated source and exact build base.
- Produces: evidence that accounting, Responses, routing, security, gateway, native-lossless, and install behavior coexist without regression.

- [ ] **Step 1: Run the maintained fork suites**

Run:

```bash
python -m pytest -q \
  tests/test_ai_motion_router_scope.py \
  tests/test_content_router_concurrency.py \
  tests/test_transforms_content_router.py \
  tests/test_compression_policy_toin_gate.py \
  tests/test_responses_savings_denominator.py \
  tests/test_dashboard_agent_usage.py \
  tests/test_request_outcome.py \
  tests/test_outcome_token_scale.py \
  tests/test_provider_openai_responses.py \
  tests/test_provider_codex_responses.py \
  tests/test_openai_responses_additional_tools.py \
  tests/test_openai_responses_output_shaper.py \
  tests/test_output_shaper_responses.py \
  tests/test_conversation_savings.py
```

Expected: PASS.

- [ ] **Step 2: Run upstream regressions introduced by the accepted commits**

Run:

```bash
python -m pytest -q \
  tests/test_codex_live.py \
  tests/test_issue_746_tool_search.py \
  tests/test_litellm_openai_passthrough.py \
  tests/test_litellm_thinking_fidelity.py \
  tests/test_route_advice_native_providers.py \
  tests/test_openai_responses_read_protection.py \
  tests/test_mixed_content_sections.py \
  tests/test_transforms_content_detection.py \
  tests/test_runtime_env.py \
  tests/test_kompress_mps_serialization.py \
  tests/test_proxy_handler_helpers.py \
  tests/test_transforms/test_smart_crusher_bugs.py \
  tests/test_cli/test_mcp_reconcile.py \
  tests/test_mcp_registry/test_claude_registrar.py \
  tests/test_install/test_runtime.py
```

Expected: PASS.

- [ ] **Step 3: Run the gateway and compress-turn contract suites**

Run:

```bash
python -m pytest -q \
  tests/gateway \
  tests/test_gateway_turn_unit.py \
  tests/test_turn_hook_seams.py \
  tests/test_compress_session_mode.py
```

Expected: PASS, including the disabled-gateway path, response-shape parity, usage relay, deferral, redrive, and cache-breakpoint behavior.

- [ ] **Step 4: Run exact retrieval, prefix, and Responses integration suites**

Run:

```bash
python -m pytest -q \
  tests/test_ccr_retrieve_history_repair.py \
  tests/test_plugins_hermes_retrieve.py \
  tests/test_transforms/test_content_router_ccr_retrieve_exemption.py \
  tests/test_proxy/test_openai_responses_ccr.py \
  tests/test_proxy_openai_responses_integration.py \
  tests/test_responses_cross_turn_dedup.py \
  tests/test_openai_responses_t3_replay_regression.py \
  tests/test_codex_responses_passthrough_bytes.py
```

Expected: PASS.

- [ ] **Step 5: Run the pinned formatter/linter and repository checks**

Run:

```bash
python scripts/verify-ruff-version.py
uvx ruff@0.16.7 check \
  headroom/proxy/handlers/openai.py \
  headroom/proxy/server.py \
  headroom/transforms/content_router.py \
  scripts/build_ai_motion.py \
  tests/test_ai_motion_build_guard.py \
  tests/test_ai_motion_router_scope.py \
  tests/test_content_router_concurrency.py \
  tests/test_openai_responses_read_protection.py \
  tests/test_transforms_content_router.py
uvx ruff@0.16.7 format --check \
  headroom/proxy/handlers/openai.py \
  headroom/proxy/server.py \
  headroom/transforms/content_router.py \
  scripts/build_ai_motion.py \
  tests/test_ai_motion_build_guard.py \
  tests/test_ai_motion_router_scope.py \
  tests/test_content_router_concurrency.py \
  tests/test_openai_responses_read_protection.py \
  tests/test_transforms_content_router.py
git diff --check bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9..HEAD
```

Expected: all commands exit zero. Any failure is diagnosed with `superpowers:systematic-debugging`; a behavioral fix receives a failing regression before implementation and a focused commit before this matrix is rerun.

### Task 5: Measure matched token, latency, and throughput behavior

**Files:**

- Verify: `scripts/benchmark_ai_motion.py`
- Test: `tests/test_ai_motion_benchmark_isolation.py`

**Interfaces:**

- Consumes: the unchanged synthetic JSON fixture, `workers=[1, 12]`, `requests=48`, fresh child processes, isolated local state, and in-memory CCR.
- Produces: directly comparable `estimated_tokens_before`, `estimated_tokens_after`, `median_ms`, `p95_ms`, `requests_per_second`, and `output_digest` for the old and new source revisions.

- [ ] **Step 1: Prove benchmark isolation**

Run:

```bash
python -m pytest -q tests/test_ai_motion_benchmark_isolation.py
```

Expected: PASS; no live Headroom or CCR settings reach child cases.

- [ ] **Step 2: Run the old fork baseline from the original checkout**

Run from `/home/huynhdanhlang/Documents/Projects/headroom`:

```bash
python scripts/benchmark_ai_motion.py --workers 1 12 --requests 48
```

Expected: JSON with `kind: synthetic_router_only`, four result rows, and `ccr_backend: isolated-memory`. Preserve the terminal output in the task record.

- [ ] **Step 3: Run the integrated candidate with the identical fixture**

Run from `/home/huynhdanhlang/.codex/worktrees/sync-upstream-bc21c93/headroom`:

```bash
python scripts/benchmark_ai_motion.py --workers 1 12 --requests 48
```

Expected: the same schema, worker counts, request counts, cached/non-cached cases, and `estimated_tokens_before` totals as the baseline.

- [ ] **Step 4: Evaluate the matched results**

For each of the four matching rows, report candidate-versus-baseline deltas for `estimated_tokens_after`, `median_ms`, `p95_ms`, and `requests_per_second`. Explain output-digest or token changes through upstream routing/protection behavior. Do not accept an unexplained latency regression or claim provider/model speedup from this local benchmark.

Expected: no context-correctness regression, no unexplained median/tail-latency regression, and any token increase is attributable to deliberate protection/recoverability behavior rather than accidental loss of compression.

### Task 6: Validate the clean maintained image and hand off the branch

**Files:**

- Verify: `docker/Dockerfile.ai-motion`
- Verify: `scripts/build_ai_motion.py`
- Verify: final Git history and worktree state

**Interfaces:**

- Consumes: a clean committed branch, exact base image digest, and explicit overlay copy set.
- Produces: a locally tagged candidate image whose revision label and runtime build version identify the exact fork commit.

- [ ] **Step 1: Verify reachability and clean source state**

Run:

```bash
git merge-base --is-ancestor bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9 HEAD
git rev-list --left-right --count HEAD...upstream/main
git status --short
```

Expected: ancestor check exits zero, the branch is zero commits behind this upstream head, and the worktree is clean.

- [ ] **Step 2: Run the clean build guard**

Run:

```bash
python scripts/build_ai_motion.py --check-only
```

Expected: JSON naming the exact HEAD commit, the candidate image tag, and hashes for every overlay source; no native/dependency or missing-copy error.

- [ ] **Step 3: Build the candidate image**

Run:

```bash
FORK_REV=$(git rev-parse --short=12 HEAD)
python scripts/build_ai_motion.py --tag "headroom-amv:${FORK_REV}"
```

Expected: Docker build exits zero using only the pinned `code-bc21c93` base plus the explicit overlay.

- [ ] **Step 4: Smoke-test build identity and both manager subcommands**

Run:

```bash
FORK_REV=$(git rev-parse --short=12 HEAD)
docker run --rm --entrypoint python3 "headroom-amv:${FORK_REV}" -c 'from headroom._build_info import BUILD_VERSION; from headroom._core import SmartCrusher; print(BUILD_VERSION, SmartCrusher.__name__)'
docker run --rm "headroom-amv:${FORK_REV}" proxy --help
docker run --rm "headroom-amv:${FORK_REV}" mcp serve --help
docker image inspect "headroom-amv:${FORK_REV}" --format '{{json .Config.Labels}}'
```

Expected: version `0.37.0+amv.<12-char-HEAD>`, native `SmartCrusher` import succeeds, both help commands exit zero, and OCI revision/source labels identify the fork commit/repository.

- [ ] **Step 5: Start an isolated health-check container**

Run:

```bash
FORK_REV=$(git rev-parse --short=12 HEAD)
CANDIDATE_STATE=$(mktemp -d)
docker run -d --rm \
  --name headroom-bc21c93-smoke \
  --read-only \
  --cap-drop ALL \
  --tmpfs /tmp \
  -p 127.0.0.1:18787:8787 \
  -v "${CANDIDATE_STATE}:/data" \
  -e HEADROOM_WORKSPACE_DIR=/data/state \
  -e HEADROOM_CONFIG_DIR=/data/config \
  -e HEADROOM_BEACON=off \
  "headroom-amv:${FORK_REV}" proxy --host 0.0.0.0 --port 8787
curl --fail --silent --show-error http://127.0.0.1:18787/health
docker logs headroom-bc21c93-smoke
docker stop headroom-bc21c93-smoke
```

Expected: health returns success, logs show normal startup with no import/native error, and the test container stops. The temporary state directory may be retained until final review, then moved to trash; no live proxy or persistent configuration is touched.

- [ ] **Step 6: Perform final branch review**

Invoke `superpowers:requesting-code-review`, then run:

```bash
git log --oneline --decorate --graph --max-count=20
git diff --stat bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9..HEAD
git status --short --branch
```

Expected: review finds no unresolved correctness issue; the diff against upstream contains only the fork's accounting, request-scope, RTK classification, maintained build, documentation, and test changes. Do not merge, push, deploy, or update the live service without a separate user request.
