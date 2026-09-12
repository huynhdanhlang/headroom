# AI Motion Headroom maintenance fork

Upstream base: `63c5df8a39c4c515a0b9b714050e530df8efeb7a` (package version 0.37.0).

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

The runtime reports `0.37.0+amv.<commit>` and OCI labels identify the full fork commit.
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
| #3556 | Regression test adopted; alternative implementation excluded | It overlapped #3487 and omitted watchdog/fan-out context propagation. |
| #3562 | Deferred | Its bare retrieval tool can reach unsupported Codex subscription streams and changes cached tool schemas. |
| #3256 | Deferred pending a cache-specific benchmark | Our base already has deadline-based SQLite expiry purging; the older PR also changes eviction/backing-store lifecycle. |
| #3385 | Deferred | Automatic repricing can mix message and schema savings and rewrite historical totals inconsistently. |
| #3373 | Deferred as low priority for this local workload | Current low key cardinality does not exercise its over-capacity cleanup bottleneck. |

The adaptation scopes all request options, tool-call maps and read-protection sets; copied worker contexts preserve
those values, and request exit restores the caller's state. Both `apply()` and the native Responses unit path
are covered, including exceptions, reused workers, batches, watchdogs and read/TOIN protection.

The build guard requires a clean commit, one immutable base stage, correct destinations for every changed runtime
file, and a base rebuild for native/dependency changes or runtime deletions. This prevents a future cherry-pick
from passing source tests while silently remaining absent from the deployed image.

## Performance and context maintenance

Use `scripts/benchmark_ai_motion.py` in a source-configured development environment with the matching native
extension. Each case runs in a fresh child process with temporary local Headroom state and an in-memory CCR store;
it never uses the live proxy or inherited remote CCR configuration. Compare the same fixtures and concurrency on
both revisions. It is a synthetic router benchmark, not an LLM latency or subscription-quota benchmark.

Keep cache mode/coding profile until a matched workload demonstrates a reason to change them. Report provider
connection/inference time separately from compression overhead. Cached tokens still occupy model context;
narrow code reads, compact command results and deliberate task handoffs remain useful. Treat dollar counters
as API-equivalent estimates, not subscription savings. Preserve meaningful source-read content and recoverability.

Use RTK for compact command output and Codegraph for indexed symbol/call-path lookup. Keep Codegraph's database
local; use exact unfiltered output when a test failure or content hash needs it.
