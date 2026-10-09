# AI Motion Headroom maintenance fork

Integrated upstream source and native/dependency anchor: `01d9194854233ef6ed04005cf0a5b8c32bf65d6d` (0.40.0).

The native/dependency base is the upstream AMD64 image from matching CI run
37880479598's `digests-code-amd64` artifact (Docker and Rust run 37880479631 passed):
`ghcr.io/headroomlabs-ai/headroom:code-01d9194@sha256:9fcc722654c54feeb740fd677d19113cd9521baff178db33194db4007cb7545b`.
Pin this host's immutable platform digest rather than waiting for the multi-arch tag.

## Synchronization through 01d91948 (2026-10-09)

Integrated 34 upstream commits: mixed client-tool CCR recovery, malformed SSE
handling and failed-stream outcomes, cache-aware billing and savings attribution,
lazy startup imports, nested JSON preservation, Codex API-key forwarding,
registered-workspace ASTgrep verification, and security/dependency updates.
The fork's native-array/uncached accounting, request scope/restoration, shared
deadlines, frozen prefixes, exact reads/retrieval, and guarded memory remain.
The native OpenCode adapter and shipped child shim now forward the new registered
session token; two red transport regressions verify identity was missing before
adaptation. Shared URL/session-token resolution remains one config owner and
bundles are regenerated from source. Non-OpenAI custom upstreams retain their
bounded provider taxonomy, with the new explicit xAI bucket. The exact native
CI base supplies Rust/dependency changes. No model/context/worker/cache/security
deployment settings are changed; runtime receipts and latency claims are separate.

### Terminal-close streaming accounting repair

SSE usage and completion are parsed before forwarding the same chunk. A client
closing/cancelling immediately on the terminal frame no longer becomes a false
502 outcome or loses usage and next-turn prefix accounting. Direct Responses,
Chat Completions and Anthropic streaming, plus both backend streaming siblings,
share this ordering. Real error events, truncated streams and caught exceptions
remain failures. The repair adds no EOF wait, stream buffering, model change or
configuration change; synthetic lifecycle regressions and installed traffic
receipts qualify it separately from inference latency.
Known upstream-image limitation: the optional canary ASTgrep interceptor lacks
its PyPI launcher. It remains disabled in this installation; test-only launcher
restoration does not establish support in the release image.

## Synchronization through 3c418f6f (2026-10-08)

Integrated 32 upstream commits: bounded ML work, context/compaction guard,
cache-prefix lifetime and reply/read-maturation stability, exact recovery output,
native git-status preservation, OpenCode dual-loader routing, TLS configuration
and dependency security updates. Native changes use the matching immutable CI base.
The ML budget uses the existing fork request-scope owner, with shared locked
accounting across copied worker contexts and restoration on request exit.
The default OpenCode dual entry composes the fork native V2 adapter so guarded
memory/session HTTP hooks survive, retaining the exact 2.0.22 dependency pin.
Bundles are regenerated from source. Cached-prefix/source-read protections,
exact retrieval, client-owned memory and uncached continuation accounting remain.
Model/context/cache/worker settings are unchanged. Runtime receipts are separate;
no provider inference speedup or subscription-quota saving is implied.

## Synchronization through 855390d6 (0.40.0, 2026-10-06)

Integrated 18 commits, including per-turn Codex project context, credential/principal
cache partitioning, private state-file creation, offline egress checks, retrieval
wrapper exemptions, bounded upstream-error redaction, Gemini transforms and the
0.40.0 release. Native/dependency changes come from the exact upstream code image.
Resolved two conflicts by combining owner-only SQLite connections with guarded
memory conflicts and combining the scoped Codex learner gate with client-owned
memory exclusion at a single observation site. Three failing regressions exposed
the early unscoped/duplicate observation before this adaptation. The fork's
ContextVar scope, shared deadlines, cached-prefix/source-read protection, exact
retrieval, native OpenCode V2 and memory ownership remain. Existing model, context,
worker, cache and loopback deployment settings are not replaced. Activation and
qualification receipts are recorded separately; no inference speedup is implied.
Known upstream limitation: cold LiteLLM pricing imports can fetch the remote price
map with `HEADROOM_OFFLINE=1` before Headroom's guards. Two isolated socket-trap
checks reproduce this; default startup also imports pricing. This installation
does not enable `HEADROOM_OFFLINE`; cached-model offline loading is verified
separately and is not proof of whole-proxy air-gap operation.

## Synchronization through 26514897 (2026-10-06)

Integrated 24 commits, including Rust dependency updates, shared Responses
compression deadlines, latest-user preservation, SSE safeguards, same-origin
retrieval checks, authenticated rate identities, startup bind policy, pinned
ModernBERT loading and client/installer fixes. Rust/dependency changes come from
the exact matching upstream native image, not Python overlays. The optional
densify mode is included but not enabled for existing clients.
Resolved four overlaps by retaining the fork's ContextVar owner/restoration and
worker propagation, adapting only the shared-deadline entry point, keeping the
upstream plugin-root hook launcher, and updating the isolated accounting fixture
to the new shared rate-identity seam. Regression checks cover deadline expiry,
protected request state and caller restoration. Model, context, existing memory,
cache policy, read protection, worker limits and subscription tracking stay as
configured. Docker remains host-loopback-only; the upstream bind acknowledgement
is required for that already-existing container networking shape.
The installed CCR sidecar shares the proxy network namespace and uses
`http://127.0.0.1:8787`: the previous bridge peer/`Host: proxy` shape cannot
pass the existing strict retrieval loopback gate. Both published host ports
remain bound only to `127.0.0.1`; the retrieval gate is not weakened.
Deployment/qualification receipts are kept separately from source integration.

## Python-only synchronization through befdb52f (2026-10-05)

Integrated 17 upstream commits without merge conflicts. They reduce request-path
copying, preserve token-cache hits, offload bounded decompression, memoize image
analysis, retain cache-prefix lineage, scope proactive CCR expansion to markers
present in the requesting conversation, avoid caching error replies, and correct
gateway/Anthropic usage accounting. CLI/error/offline-tokenizer fixes are included.
No native or dependency input changes: every changed runtime file is explicitly
copied onto the existing immutable native base. The fork's request isolation,
cache-mode Responses prefix/source-read protection, bounded deadlines, OpenCode V2
and guarded shared-memory adapters remain. Model, context, tokenizer cache,
worker/security settings and existing memory stores are not replaced.
The conflict-free merge still overlapped streamed Anthropic continuation
accounting: the new uncached-input branch consumed the fork's whole-prompt
total. The existing two-round memory regression failed (135 versus 30 uncached
tokens); retaining raw provider input separately fixes it without changing
whole-prompt totals or the client stream. The affected checks passed after repair.
Qualification and actual activation receipts are recorded separately; source
integration alone does not establish live installation or faster model inference.

## Codex client-owned proxy memory (2026-10-05)

`headroom.memory.proxy_mcp` exposes search/list/save/update/delete over the running
proxy's existing local `/v1/memory/tools` command facade. It owns transport only:
no second SQLite store, embedder initialization, provider call or model change.
Exact IDs/hashes guard correction and retained forget; current instructions and
permissions take precedence over recalled background. Tool arguments cannot
select user/project identity. HTTP requests and results are bounded, and failed
or interrupted writes are never reported as confirmed remembered.

For this Docker installation, `scripts/codex_memory_mcp.py` launches the clean
release image by immutable image ID using host stdlib and inherited session cwd.
No project/secret mounts, Docker socket mount or explicit global MCP cwd are
needed. MCP roots, when supported, are consulted on each call so session moves
follow the current project; ambiguous/failed roots fail closed. Hosts without
roots retain their startup project until a fresh MCP session is created.
Register the launcher as `mcp_servers.headroom_memory` in Codex's config with
`command = "/usr/bin/python3"` and args `[absolute_launcher_path, "--image",
"sha256:<installed-clean-image-id>"]`; the local proxy defaults to port 4444.
The user-authorized memory server alone uses `default_tools_approval_mode =
"approve"` (Codex 0.160.0); `auto` still requires prompts on this host and
`approval_policy=never` then refuses the calls. Other MCP/shell approval policy
is unchanged. The stdio container disables the inherited proxy-only HTTP
healthcheck; its acceptance is the MCP handshake and real operation receipts.
Existing local-DB `headroom.memory.mcp_server` compatibility stays unchanged.
The proxy and CCR do not require a restart for this client-only adapter.
Installed acceptance passed save/list, fresh-session recall without the canary
in its prompt, other-project isolation, guarded update and retained forget,
plus a fresh Codex run using the actual global MCP config and installed launcher.
Receipts and pre-change config/instructions are preserved under the installation's
`backups/20261005-codex-memory.HrkAED/`. Recalled knowledge is scoped background,
not instruction authority; no guarantee of perfect recall or faster model inference.
Qualification: 183 focused checks passed. Full-suite collection encountered the
pre-existing dashboard Playwright `_open_dashboard` import failure; full suite
is not claimed green. Existing proxy/CCR runtime and worker/model/context/cache
settings are unchanged.

## Synchronization through 1cf49661 (2026-10-04)

### Qualified feedback-memory source — activation separately verified

The isolated `fix/feedback-memory` worktree repairs authored English/Vietnamese
feedback, exact owner/content-hash supersession and retained forget, durable
evidence-key replay, and a bounded local command adapter consumed by native
OpenCode V2 tools/prompt hooks. Current-session location supplies both tool and
inference scope; client-owned memory tools are not invisibly executed by the
proxy. Native recall verifies active primary rows, uses the existing hybrid
consumer and remains bounded read-only background below current project authority.

Authoring/QA was isolated and uncommitted; source integration and activation were
subsequently specifically authorized. The checks below remain source evidence,
not a substitute for release-image or actual resumed-traffic acceptance.
Disposable ASGI/SQLite/index/native-hook regressions use synthetic projects.
The final compiled V2 hooks also pass a real HTTP/canonical-handler journey with
the qualified ONNX model copied byte-for-byte from the existing cache, offline:
save/replay, fresh backend, relevant-only background, unchanged signed prefix,
guarded correction/conflict, session move, project isolation and forget. No model
was downloaded or substituted. This does not establish arbitrary cross-language
semantic quality. Actual installed-host acceptance subsequently passed: fresh
session automatic recall, compaction, native search/list/update/forget and
session moves on OpenCode 2.0.22 with the selected model. That acceptance exposed
native array-input recall gaps in HTTP/WS; read-only query projection and latest
user-tail injection fix them while keeping signed/cache prefixes unchanged.
The initial delivered runtime source was `c36d0f1a`, clean-built on the same pinned base;
both Headroom services are healthy with actual scope/ownership traffic verified.
The subsequent authorized follow-up closes the three baseline router-fixture
failures by injecting the existing deterministic token counter into their
external tokenizer seam; real context/fan-out assertions stay intact. All 54
previously HNSW-gated core cases now run against the installed SQLite-vector and
qualified offline ONNX adapters. Missing model assets fail fixture setup, never
silently skip. The exposed legacy missing-ID supersession message is restored
only for unguarded calls; partial guards still return uniform conflicts.
Default/access timestamps retain naive UTC without deprecated `utcnow`.
Final affected suites: 568 passed, zero skips; pinned runtime-source Ruff passed.
The follow-up runtime `d009303e` was then clean-built on the same pinned base,
with all 22 overlay hashes verified. Its compiled native hooks/real offline-model
journey and live synthetic native operations passed. Both Headroom services are
healthy; ordinary creator-session traffic resumed with the correct client-owned
scope. Consistent stopped-state rollback is preserved; model/Fast configuration,
top-k 3 and the video runtime remain unchanged. Exact release/live acceptance is
recorded separately in the Plan.
Exact per-slice evidence, review, source/bundle hashes and proposed activation
boundary are recorded in the approved `2026-10-04-feedback-memory` Plan and its
private worktree ledger. Those integration/build/activation actions were separately
authorized; verified stopped-service backups and original/intermediate rollback
images are preserved. No push, model/Fast configuration change or video-app
restart was performed. Live memory top-k remains 3.

Integrated five commits: streamed injected memory-tool execution, context injection
past trailing system messages, persisted escaped pattern-ID recognition, Hermes
documentation and npm maintenance. Upstream now supplies the equivalent learner
marker fix, so its overlay is removed without weakening managed-block protection.
Upstream continuation accounting undercounted Anthropic prompt tokens and hid
continuation input/cache usage from clients. A failing streamed two-round regression
reproduced this; the fork totals uncached plus cache input across rounds and emits
cumulative client usage without modifying ordinary single-round streams.
The twelve remaining overlays retain OpenCode V2, cache-mode Responses prefix/read
protection, request isolation, bounded deadlines and accounting. Live model,
context, persistent tokenizer cache and worker/security configuration remain unchanged.

## Synchronization through 2bc94194 (2026-10-03)

Integrated four commits: bounded relevance segments, quiet telemetry/nag defaults,
response-size logging and the dashboard CO2 estimate. The eleven runtime overlays
retain request isolation, cached-prefix/source-read protection, learner lifecycle,
deadlines and accounting. Context, model and live performance settings are unchanged.
CO2 is a modeled estimate, not measured energy or verified subscription savings.
Match the most specific model family first: the upstream insertion-order matcher
incorrectly treated GPT-4o and GPT-4o-mini as GPT-4. A failing regression covers
the declared factors, including dated and uppercase model names.
Includes the user-authorized OpenCode V2 native request-hook adapter, its directory
entry and rebuilt V1/V2 bundles. The plugin is typed against OpenCode 2.0.22; both
entries remain available. Bundle dependency changes are self-contained JS artifacts,
not a substitution of the pinned Python/native dependency base. Build in the clean
attached worktree and fast-forward the main checkout only after verifying the copied
OpenCode changes, preserving the user's exact development files.

## Synchronization through 9a72bc02 (2026-10-03)

Integrated 14 upstream commits without conflicts: proxy-token scrubbing, local
operator-only usage polling, OAuth minting only before upstream requests, Gemini
forwarded-prefix replay and media preservation, isolated timed-out image workers,
external-compressor fallback, stable learner items and savings audit output.
The exact matching image supplies upstream runtime; the six fork overlays keep
cache-mode Responses messages immutable, request isolation, bounded compression,
source-read protection and consistent accounting. Live model, context, persistent
tokenizer cache, parallelism and security settings are unchanged.
The upstream learner lifecycle regression reproduced expired categories surviving
in AGENTS.md: managed-block sanitization escaped pattern-ID comment endings. The
writer now recognizes the inert escaped marker without unescaping content or
weakening injection protection. Existing deletion/preservation regressions cover it.

## Synchronization through d5318ac2 (2026-10-02)

Integrated 28 upstream commits, including tenant-isolated TOIN learning, bounded
metrics and ONNX threads, chained-shell source-read protection, Codex dashboard
traffic, persistent learner evidence and safer public errors. Dependency changes
come from the exact matching native image; the five fork overlays remain.
Resolved the overlapping OpenAI provider fix and secure rate-key test by retaining
the fork's destination-aware provider check and opaque rate-key fixture. Preserve
context, cache prefixes, request isolation, deadlines and live configuration.
Usage reporting remains opt-in; do not enable it during installation.
Historical Responses message compression is retained for token mode only:
cache mode preserves messages byte-for-byte across turns. A two-turn regression
reproduced the new upstream prefix mutation before this guard was added.
This installation is single-user and has no tenant-ID gateway. Upstream explicit
tenant headers still strip/truncate IDs and can alias distinct namespaces; do not
enable shared-tenant routing without collision-resistant normalization and tests.

## Synchronization through 3080a9d4 (2026-10-02)

Integrated ten commits after c46, including the three original Python changes,
native SourceCode/PlainText live-zone dispatch, line/tabular integrity in Kompress,
CCR preservation wording, accurate runtime settings and the latest docs. Native
changes come from this exact base; only five fork runtime files are overlaid.
Model, reasoning, context retention and live configuration remain unchanged.

## Python-only synchronization through f0ec2bb3 (2026-10-02)

Integrated three commits for message/tool-call cache markers, fixed provider
telemetry labels and the Codex embedded-mode notice. No dependency/native files
changed. This slice was first verified as an additive Python overlay. The final
release uses the matching 3080 native image, which supplies those upstream files
itself; no source substitution or runtime deletion is permitted.

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

The runtime reports `0.40.0+amv.<commit>` and OCI labels identify the full fork commit.
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
