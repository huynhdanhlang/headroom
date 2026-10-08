# headroom-opencode

OpenCode integration helpers for Headroom. The package supports two integration paths:

1. Provider config helpers used by `headroom wrap opencode` and persistent installs.
2. Native OpenCode plugins: the V1 transport factory and the V2 request-hook adapter.

## Install

```bash
npm install headroom-opencode
```

## Provider Config Helpers

Use these helpers when you need to generate OpenCode config that routes a `headroom` provider through a running Headroom proxy.

```ts
import {
  buildOpencodeConfigContent,
  createHeadroomProvider,
} from "headroom-opencode";

const provider = createHeadroomProvider({ proxyPort: 8787 });
const config = buildOpencodeConfigContent({
  proxyPort: 8787,
  defaultModel: "claude-sonnet-4-6",
});

console.log(provider.provider.headroom.npm);
console.log(config.model);
```

The generated provider uses `@ai-sdk/openai-compatible` and points model requests at `http://127.0.0.1:<port>/v1`.

## Native OpenCode Plugin

The package's default export is an OpenCode plugin that loads on both OpenCode 1.x and 2.x. Register it in `opencode.json`:

```json
{
  "plugin": [
    ["headroom-opencode", { "proxyUrl": "http://127.0.0.1:8787" }]
  ]
}
```

OpenCode 2.x migrates the 1.x `plugin` key automatically. To configure it the 2.x way, use `"plugins": [{ "package": "headroom-opencode", "options": { ... } }]`.

The default export is `{ id: "headroom", server, setup }`. OpenCode 1.x calls `server` (`HeadroomPlugin`) and 2.x calls `setup` (`headroomSetup`); each ignores the other's field. Both entry points:

- install Headroom transport interception for OpenCode provider traffic.
- expose the `headroom_retrieve` tool (a direct tool on 2.x, not only through code mode).
- add `HEADROOM_ACTIVE`, `HEADROOM_PROXY_URL`, `HEADROOM_PROJECT` (and `HEADROOM_BACKEND` when set) to shell command environments.
- default to `HEADROOM_PROXY_URL`, then `http://127.0.0.1:8787`, when no `proxyUrl` option is supplied.
- skip routing for hosts listed in `excludeHosts` (or `HEADROOM_OPENCODE_EXCLUDE_HOSTS`); those requests go straight upstream with no compression or telemetry.

On 2.x, setup returns a cleanup that releases the transport, so hot reloads do not stack interceptors.

OpenCode 2.x keeps its own reference to `fetch` from before plugins load, so patching `fetch` alone does not catch its model traffic. On 2.x the plugin also rewrites each remote model that uses the OpenAI chat-completions or responses format so that it points at the proxy. Headers name the real upstream, as the transport does. Models on other formats (Anthropic messages, Google) are left alone. `headroom wrap opencode` routes native Anthropic and OpenAI through the proxy separately, via their `baseURL`.

To keep a provider off the proxy, list its host. An entry matches the host and all of its subdomains, and `.example.com` / `*.example.com` are accepted as spellings of `example.com`:

```jsonc
// opencode.json
{
  "plugin": [["/path/to/headroom/providers/opencode/_dist", { "excludeHosts": ["opencode.ai"] }]]
}
```

or, for `headroom wrap opencode` and spawned Node child processes, set the environment variable before launching:

```bash
HEADROOM_OPENCODE_EXCLUDE_HOSTS="opencode.ai,.corp.internal" headroom wrap opencode
```

## Native OpenCode V2

OpenCode V2 requires an `id/setup` object; the V1 factory entry is not compatible.
Build with `npm run build:standalone` and use the absolute directory path
`headroom/providers/opencode/_dist/v2` as `plugins[].package`. OpenCode 2.0.22
requires a directory, not a file. Both builds generate the `v2` package directory;
copy `dist-standalone/entry.opencode.v2.js` and `dist-standalone/v2/` together into
the wheel's `_dist/` when updating it. CI verifies all three artifacts. Its entry delegates to the single self-contained
`entry.opencode.v2.js` bundle next to it.
Pass `options.proxyUrl` for the existing local proxy; the default is port 8787.
The same `project` and `excludeHosts` options apply.

The adapter uses V2's `http.request` hook and the existing endpoint/header router.
It preserves model IDs, Fast parameters, auth, signed reasoning, tool schemas,
request bytes, cancellation and project isolation. It does not patch global fetch,
spawn Node shims, change credentials or substitute provider/model configuration.
This entry covers HTTP model requests, including title/compaction calls; it is not
a WebSocket interceptor. The tested ChatGPT token-sharing integration uses HTTP.
Connection-refused failures for a routed loopback proxy stop promptly; other
failures use OpenCode's ordinary recovery, without silently going direct.

Keep the Headroom MCP connection for compression, retrieval and stats. Existing
client-side tool-result compression can coexist: the client stores its compressed
result once, while the proxy's cache mode preserves the repeated request prefix.
Do not rewrite historical cached messages or source reads to inflate token savings.

For isolated live measurements, run `npm run benchmark:proxy -- --proxy-url
http://127.0.0.1:4474 --rounds 3 --output /tmp/opencode-headroom-benchmark.json`
against a dedicated Headroom instance with isolated stores. The benchmark uses the
single configured OpenCode OpenAI connection, synthetic transcripts and identical
model/reasoning/request tiers on both arms. It alternates direct/proxy order and
reports response correctness, first-token/total latency, provider token counts and
cache receipts. It refuses ambiguous accounts and never writes credentials or
prompt contents. Small samples and API-equivalent counters do not establish general
coding speed, commercial quality or subscription-quota savings.

## Retrieve Tool

```ts
import { createHeadroomRetrieveTool } from "headroom-opencode";

const retrieve = createHeadroomRetrieveTool({
  proxyBaseUrl: "http://127.0.0.1:8787",
});

const result = await retrieve.execute({
  hash: "0123456789abcdef01234567",
});
```

The tool calls `/v1/retrieve/<hash>` on the Headroom proxy.

## Compression Helper

```ts
import { compressWithHeadroom } from "headroom-opencode";

const result = await compressWithHeadroom(
  [{ role: "user", content: "Summarize this file" }],
  { model: "gpt-4o", proxyUrl: "http://127.0.0.1:8787" },
);

console.log(`Saved ${result.tokensSaved} tokens`);
```

## Models

| Model | Context | Output |
|---|---:|---:|
| `claude-sonnet-4-6` | 200K | 16K |
| `claude-opus-4-6` | 200K | 16K |
| `claude-haiku-4-5-20251001` | 200K | 8K |
| `gpt-4o` | 128K | 16K |
| `gpt-4.1` | 1M | 32K |

The provider config exposes these as `headroom/<model>` and defaults to `headroom/claude-sonnet-4-6`.

## Environment

| Variable | Used by | Description |
|---|---|---|
| `HEADROOM_PROXY_URL` | Native plugin | Proxy URL used by `HeadroomPlugin` |
| `HEADROOM_OPENCODE_EXCLUDE_HOSTS` | Native plugin | Comma-separated hosts (and their subdomains) that bypass the proxy; the `excludeHosts` plugin option takes precedence |
| `OPENCODE_CONFIG_CONTENT` | OpenCode wrapper | Generated OpenCode provider, model, and MCP config |

## License

Apache-2.0
