# AI Motion Headroom maintenance fork

Integrated upstream source: `f0ec2bb37697b1addccb416bd626e7bf3c5ea835` (0.39.1 plus latest upstream main fixes).
Native/dependency source anchor: `c46e7cc6514ec49a039537c9f0e984f2c9e6327a`.

The native/dependency base is the signed multi-architecture image
`ghcr.io/headroomlabs-ai/headroom:code-c46e7cc@sha256:2ef8487524dddaabba3abd36f830bef3649a99a6f090a51facb783ae8e9fa0f3`.

## Python-only synchronization through f0ec2bb3 (2026-10-02)

Integrated three commits for message/tool-call cache markers, fixed provider
telemetry labels and the Codex embedded-mode notice. No dependency/native files
changed. While the exact upstream image is unpublished, the build-guard-checked
additive overlay supplies all eight changed runtime files on the unchanged c46
native base; no source substitution or runtime deletion is permitted.

The fork corrects the telemetry fallback to check a client custom-base header or
a changed resolved destination, not a merely nonempty upstream URL. A failing HTTP-route regression reproduced
default OpenAI traffic being logged as `custom`; keep that traffic in `openai`.

## Synchronization through c46e7cc6 (2026-10-02)

Integrated the upstream HTTP TCP-keepalive fix (#3907). Both HTTP clients probe
idle upstream links after 30 seconds, with six 10-second probes, before the
existing retry policy reconnects. A healthy model thinking silently is not cut
off. Keepalive wraps the network backend before SSRF pinning and preserves
HTTP/2, environment proxies and connection reuse. Context, cached prefixes,
source-read protection, deadlines, accounting and tokenizer cache are unchanged.

## Synchronization through f824a270 (2026-10-01)

Integrated 28 commits after 0a2c80d: dependency security patches, protected JSON
record spans, memory SQLite connection cleanup, bounded HNSW eviction,
corrupt-row handling and credential-safe shared-proxy routing. The merge is
conflict-free; all five fork runtime overlays and persistent tokenizer cache
remain. Per-message diagnostics and keep-last-turns are opt-in: do not enable
history trimming globally or weaken cached-prefix/source-read protections.

## 2026-10-01 upstream sync

Integrated 22 commits after ffc6edb, including memoized OpenAI token counting,
code UTF-8 mapping performance, Codex exec-envelope/source-read protection,
coding-profile protection and token-correct compression fallback accounting.
Preserved all fork request isolation, bounded deadlines, exact retrieval and
Responses/dashboard accounting. Combined both sides of the read-protection test
conflict so neither upstream nor fork regression coverage is lost.

The local manager keeps `TIKTOKEN_CACHE_DIR=/headroom/cache/tiktoken` on its
persistent cache volume. Prewarm and verify all four tokenizer encodings offline
before cutover: ephemeral `/tmp` vocab downloads exceeded the bounded loader's
timeout in the test candidate. This changes no counting/compression thresholds.

## 2026-09-30 upstream sync

Integrated the 33 commits after 7968122, including native/dependency updates,
CCR retrieval/cache ordering, unmarked HTML protection and security gates.
Preserved the fork's ContextVar request isolation and shared compression deadline,
source-read protection, bounded accounting, parallelism and deployment configuration.
The only merge conflict was adjacent router documentation; both behaviors remain.

This fork keeps the upstream compression/cache policy. Its maintenance changes are:

- Count native Responses array text and tool outputs in the HTTP token denominator,
  without changing forwarded request content or session identity.
- Calculate the Agent Usage panel's rows, totals and savings shares from the same
  bounded request-log window. These per-request savings are distinct from global
  conversation-deduplicated savings; global counters remain the fallback when no logs exist.

The first issue was reproduced on both stable and upstream main. Valid tool-output
requests could report only three original tokens and thousands of saved tokens.
The second issue could report shares above 100 percent by mixing per-request
numerators with a deduplicated global denominator. Tests cover these inputs;
no percentage clipping is used to hide a mismatched count.

## Build

Use a clean checkout. The overlay copies only the changed Python/frontend files onto
an immutable upstream image, preserving its native extension and dependencies.
Changing Rust or dependencies requires rebuilding the base rather than this overlay.

```bash
python scripts/build_ai_motion.py --check-only
python scripts/build_ai_motion.py
```

The runtime reports `0.39.1+amv.<commit>` and OCI labels identify the full fork commit.
The image preserves the AI Motion manager entrypoint (`headroom`) so one image can run
both `proxy` and `mcp serve`. Direct use must include the subcommand, for example
`docker run --rm IMAGE proxy --port 8787`; upstream examples that append only `--port`
do not apply to this wrapper. The manager runs both services as its explicit unprivileged
UID/GID with a read-only filesystem and dropped capabilities.
Do not deploy an image built from uncommitted changes under a committed revision label.

## Verify before deployment

Run the native Responses savings-denominator, dashboard agent-usage, request-outcome,
token-scale, provider Responses, tokenizer offload, waste-signals, conversation-savings,
additional-tools and output-shaper regression suites. Check the changed Python files
with the repository's pinned Ruff version.

Use isolated state and ports for the candidate. Verify exact MCP retrieval, frozen-prefix
preservation, a real Responses request, dashboard rows and bounded percentages. Then
verify resumed desktop traffic, including native array tool outputs, after cutover.
Keep the stable image and a stopped-service backup of configuration, state and cache.
Preserve valid internal model-cache symlinks in both backup and restore.


## Curated upstream changes

Pending PRs are reviewed by exact head/commit and tested against this fork; they are not merged in bulk.

| Upstream PR | Decision for this runtime | Reason |
| --- | --- | --- |
| #3487 | Integrated its two implementation/test commits, then adapted | Context-local options alone did not scope tool maps, read protection, reused workers, or Responses worker contexts. |
| #3556 | Integrated, then adapted | Its tests and upstream behavior are retained; the fork keeps broader scoping, caller restoration, reused-worker cleanup, and Responses/watchdog/fan-out context propagation. |
| #3562 | Deferred | Its bare retrieval tool can reach unsupported Codex subscription streams and changes cached tool schemas. |
| #3256 | Integrated with upstream 0.39.0 | The upstream TTL sweep change is in the pinned native base; do not cherry-pick it again. |
| #3385 | Deferred | Automatic repricing can mix message and schema savings and rewrite historical totals inconsistently. |
| #3373 | Integrated with upstream 0.39.0 | The constant-time rate-limiter bucket check is in the pinned native base. |

The adaptation scopes all request options, tool-call maps and read-protection sets; copied worker contexts preserve
those values, and request exit restores the caller's state. Both `apply()` and the native Responses unit path
are covered, including exceptions, reused workers, batches, watchdogs and read/TOIN protection.

The build guard requires a clean commit, one immutable base stage, correct destinations for every changed runtime
file, and a base rebuild for native/dependency changes or runtime deletions. This prevents a future cherry-pick
from passing source tests while silently remaining absent from the deployed image.

## Upstream synchronization through `bc21c937`

The 24 commits after the former `63c5df8a` base were reviewed by exact commit and integrated. They include
Codex Live HTTP creation, Responses `custom_tool_call` read protection, signed-thinking/tool-search fidelity,
gateway-turn and Responses gateway contracts, grep-context classification, strict-lossless SmartCrusher fixes,
runtime-env request-size protection, rootless Podman ownership, project-root handling, Kompress serialization,
Python 3.14 packaging, and the rustls/anyio security updates.

The upstream range changes Rust sources and dependency lockfiles, so it is supplied by the exact native base
image above rather than copied through the Python overlay. The fork overlay contains only the accounting,
request-scope, RTK-aware source-read protection, gateway Responses tool-identity protection, dashboard and
build-contract differences from `bc21c937`.

## Upstream synchronization through `1cb779e1`

The 22 commits after `bc21c937` are integrated on the 0.38.0 native base. They add bounded
request logging, budget enforcement on OpenAI/Gemini routes, safer dense-line and tabular
handling, SmartCrusher JSON-field preservation, cache-aware pricing, and updated savings
history/metrics. The Responses budget check runs before the fork's native-array token
accounting; request scoping, exact read protection, gateway tool identity, and Agent Usage
log-window accounting remain fork changes. The overlay is compared against `1cb779e1`.

## Upstream synchronization through `66f42617` (0.39.0)

The 0.39.0 native/dependency base includes upstream cache-prefix, stream,
security, request-budget, tool-search, and Kompress deadline fixes. The fork
keeps request-scope restoration across reused workers, exact source-read
protection, Responses accounting, dashboard log-window accounting, and its
bounded large-frame deadline. The Codex JavaScript command parser adopts
upstream's whole-literal fail-closed checks; uncertain commands still protect
their output. Request-scoped Kompress timing uses the fork's existing ContextVar
scope rather than a second state mechanism. Native and dependency changes come
from the pinned 0.39.0 base, not the overlay.

## Post-release synchronization through `79681226`

The single post-0.39.0 upstream commit fixes TPM rate-limit accounting for
requests larger than one minute of configured capacity, so a large-context
request cannot leave its bucket refusing traffic forever. It changes Python
code and tests only; the pinned `code-7968122` image supplies that exact
upstream runtime while the fork overlay remains limited to its five changed
Python/frontend files. Keep this hotfix with the existing Responses and
request-scope protections; verify large-context admission and retry behavior
before updating the live proxy.

## Performance and context maintenance

Use `scripts/benchmark_ai_motion.py` in a source-configured development environment with the matching native
extension. Each case runs in a fresh child process with temporary local Headroom state and an in-memory CCR store;
it never uses the live proxy or inherited remote CCR configuration. Compare the same fixtures and concurrency on
both revisions. It is a synthetic router benchmark, not an LLM latency or subscription-quota benchmark.

Keep cache mode/coding profile until a matched workload demonstrates a reason to change them. Report provider
connection/inference time separately from compression overhead. Cached tokens still occupy model context;
narrow code reads, compact command results and deliberate task handoffs remain useful. Treat dollar counters
as API-equivalent estimates, not subscription savings. Preserve meaningful source-read content and recoverability.

Codex WebSocket frames below 4 MiB retain the 5-second compression deadline. Larger frames have a bounded
7.5-second deadline: on this local workload, cold 5.6 MB frames finished 1–2.4 seconds after the old deadline,
which otherwise forwarded the entire uncompressed context and briefly quarantined compression. The local
manager may run eight tool-output workers; a synthetic 1,200-output fixture produced identical bytes and
savings at four and eight workers, with lower compression time at eight. Neither setting proves provider
latency or subscription-quota improvement.

Use RTK for compact command output and Codegraph for indexed symbol/call-path lookup. Keep Codegraph's database
local; use exact unfiltered output when a test failure or content hash needs it.
