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
git diff --exit-code
git diff --cached --exit-code
docker build -f docker/Dockerfile.ai-motion \
  --build-arg FORK_COMMIT="$(git rev-parse HEAD)" \
  -t "headroom-amv:$(git rev-parse --short=12 HEAD)" .
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
