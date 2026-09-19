# Upstream `bc21c937` Integration Design

## Objective

Integrate the 24 commits between the maintenance fork's pinned upstream base
`63c5df8a39c4c515a0b9b714050e530df8efeb7a` and
`bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9`, while preserving the fork's
request isolation and accounting guarantees. The result should improve the
Codex/Responses workload's usable token savings, compression latency, runtime
performance, and context stability without sacrificing exact retrieval,
protected source reads, prefix-cache continuity, or recoverability.

## User Priorities

The maintenance fork is optimized for local Codex and Claude-style coding
traffic. In priority order, the integrated runtime must:

1. Preserve exact and recoverable source context. Protected file reads, cached
   prefixes, tool-call identity, signed thinking blocks, and retrieval markers
   must not be damaged or moved incorrectly.
2. Reduce tokens forwarded to the model when content can be compressed safely.
   Savings accounting must use coherent denominators and remain bounded without
   percentage clipping.
3. Avoid latency and concurrency regressions. Compression work must not leak
   request state, block unrelated requests, or add unnecessary model warm-up to
   the first qualifying request.
4. Avoid context churn. A nominal token reduction is not useful if the agent
   must repeat searches, re-read files, or loses usable cache prefixes.
5. Keep deployment reproducible. Native and dependency changes must come from
   an exact upstream image, and the overlay must contain every fork-only runtime
   change.

## Upstream Audit Decision

All 24 upstream commits are accepted, with one adapted overlap:

- Storage, loop-learning, Codex Live, tool-search history, route advice,
  LiteLLM reasoning fidelity, MCP reconciliation, grep-context detection,
  Anthropic project-root handling, rootless Podman ownership, runtime-env body
  limits, Kompress serialization, SmartCrusher strict-lossless behavior,
  system-block relocation, Responses gateway support, and dependency security
  updates are adopted.
- The gateway-turn subsystem is adopted as upstream code. Its routes inherit
  the existing `/v1/compress` exposure policy and remain disableable through
  upstream's `HEADROOM_GATEWAY_CONTRACT=0` path.
- Upstream #3556 is not allowed to replace the fork's broader request-state
  isolation. Its tests and compatible behavior are adopted, while the fork's
  scoping of runtime options, tool maps, read-protection sets, worker contexts,
  exception cleanup, and reused workers remains authoritative.

The final source tree is therefore based on the exact upstream commit, plus a
small, reviewable maintenance delta. It is not a blind conflict resolution and
does not cherry-pick partial dependency/native changes onto an older binary.

## Integration Strategy

Merge `upstream/main` at `bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9`
into the fork branch. A merge is preferred over rebasing because the public
fork already contains merge commits and must not rewrite published `main`
history.

The merge has three textual conflicts:

- `headroom/transforms/content_router.py`
- `tests/test_content_router_concurrency.py`
- `tests/test_transforms_content_router.py`

`headroom/proxy/handlers/openai.py` and `headroom/proxy/server.py` merge
textually but still require semantic review because they contain the fork's
accounting changes and upstream's gateway/security additions.

The resolution uses upstream as the structural baseline, then reapplies the
fork's stronger request-scope design. New upstream behavior—including
Responses `custom_tool_call` parsing, read protection, session mode, gateway
hooks, background Kompress warm-up, and runtime-env limits—must remain present.

## Fork-Specific Optimization

Upstream recognizes a simple `rtk cat` wrapper, but the actual local workflow
uses compound commands such as `rtk proxy sed -n ...`, `rtk proxy nl ...`, and
`rtk proxy cat ...`. The current parser stops at `proxy`, so those exact source
reads can be misclassified as compressible even after upstream #3621.

The integration adds a regression-first change that treats `rtk proxy` as one
compound wrapper without treating every executable named `proxy` as a generic
shell wrapper. The tests cover:

- `rtk proxy sed -n`, `rtk proxy nl`, and `rtk proxy cat` as protected reads;
- `rtk proxy rg` as searchable, losslessly foldable output;
- `rtk proxy pytest` as ordinary compressible command output;
- write redirections and lockfile reads remaining unprotected as before.

This optimization targets context quality rather than raw compression ratio:
exact source reads should prevent compensating re-reads, while derived search
and test output remains eligible for compression.

## Image and Build Contract

The old overlay is based on `code-63c5df8`, but the accepted upstream range
changes Rust sources, `Cargo.lock`, `pyproject.toml`, and `uv.lock`. The new
overlay must therefore use the upstream image built from the new native and
dependency state:

`ghcr.io/headroomlabs-ai/headroom:code-bc21c93@sha256:cc517ad22cc1a0c4618cc1bdea612b345f9c0928c13958dae86c9f1d481c380d`

The image has successful upstream multi-architecture build, native import
smoke tests, manifest assembly, and signing for amd64 and arm64. The build guard
will be repinned to the full upstream commit and exact image digest. It will
continue to reject dirty builds, omitted runtime files, runtime deletions, and
future native/dependency changes that are not present in a new pinned base.

The overlay copies only files that differ from `bc21c937`; upstream files come
from the immutable base image. The runtime version remains
`0.37.0+amv.<fork-commit>` unless the integrated upstream source declares a new
package version.

## Accounting and Context Invariants

The following fork invariants are non-negotiable:

- Native Responses array messages, `function_call_output`, and
  `custom_tool_call_output` contribute to the original HTTP token denominator.
- `original_tokens - optimized_tokens == tokens_saved` for successful
  compression outcomes.
- Agent Usage rows, totals, saved-token shares, and savings percentages use the
  same bounded request-log window whenever request logs exist. Global counters
  are only the fallback when the log window is empty.
- Request-local runtime options, tool maps, and read-protection sets cannot leak
  across concurrent requests or reused workers.
- Context copied into watchdog, batch, and fan-out workers observes the owning
  request's state.
- Request exit and exceptions restore caller state.
- Protected source reads stay byte-exact; search/test/log output remains
  compressible when the applicable compressor is reversible or recoverable.
- Cached prefixes and session identity are not rewritten solely to improve a
  reported compression ratio.

## Verification Design

Verification proceeds from narrow regressions to the complete maintained build
contract:

1. Run the upstream conflict-area tests and the fork's request-scope tests.
2. Run Responses accounting, read protection, provider Responses, output
   shaper, request outcome, dashboard Agent Usage, conversation savings,
   token-scale, additional-tools, and retrieval suites.
3. Run the upstream gateway, signed-thinking, grep-context, strict-lossless,
   runtime-env, Codex Live, and dependency-adjacent regression suites affected
   by the 24 commits.
4. Run pinned Ruff checks on every changed Python file and `git diff --check`.
5. From a clean commit, run `scripts/build_ai_motion.py --check-only`, build the
   image, and smoke-test both `headroom proxy` and `headroom mcp serve` entry
   paths.
6. Exercise the candidate on isolated ports and temporary state. Verify exact
   MCP retrieval, frozen-prefix preservation, a real Responses request, native
   array tool outputs, dashboard rows, and bounded percentages.
7. Run matched synthetic router benchmarks on the old and new revisions using
   the same fixtures, concurrency, and isolated stores. Report tokens before
   and after, compression overhead, median and tail latency, and any repeated
   reads separately.

Synthetic benchmarks are evidence about the router implementation only. They
must not be described as proof of provider inference speed, model quality,
subscription quota reduction, or production cost savings.

## Acceptance Criteria

The branch is ready for review when:

- all 24 upstream commits are reachable from the branch;
- the three merge conflicts are resolved without dropping either upstream
  features or fork invariants;
- the exact upstream base image and full upstream commit are pinned together;
- all required targeted suites pass, with any unrelated baseline failure
  documented rather than hidden;
- exact retrieval, protected reads, prefix behavior, accounting equations, and
  bounded Agent Usage percentages pass their regressions;
- matched benchmarks show no unexplained compression-overhead or tail-latency
  regression, and token changes are explained by protection/recoverability
  policy rather than presented as an isolated percentage;
- the build guard passes from a clean commit and the candidate image starts
  both supported manager subcommands;
- no live service is updated without separate user authorization, a stopped
  service/config/state backup, a verified previous image, and post-cutover
  traffic verification.

## Alternatives Rejected

Selective cherry-picking would avoid the gateway subsystem but leave the fork
behind on dependency/native security fixes and make the next synchronization
more conflict-prone. Replacing the fork with upstream and recreating only the
accounting patch would lose tested request-state and build protections. A blind
merge would preserve history but risks silently accepting the narrower #3556
implementation. The exact-base merge plus curated fork delta is the smallest
approach that satisfies correctness, performance, and maintainability.
