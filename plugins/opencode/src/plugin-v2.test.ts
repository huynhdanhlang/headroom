import fs from "node:fs";
import http from "node:http";
import { fileURLToPath } from "node:url";
import type { Context, Plugin } from "@opencode/plugin/promise/plugin";
import type { SessionHttpRequest, SessionRetry, SessionHttpResponse } from "@opencode/plugin/promise/session";
import { describe, expect, it } from "vitest";

async function loadV2(): Promise<Plugin | undefined> {
  const entry = new URL("./entry.opencode.v2.ts", import.meta.url);
  if (!fs.existsSync(fileURLToPath(entry))) return undefined;
  return (await import(entry.href)).default;
}

// The host owns hook dispatch. This harness captures its real callback boundary;
// requests, streams, AbortSignals and the receiving HTTP server are real.
function host(options: Record<string, unknown>, directory = "/workspace/one") {
  const hooks = new Map<string, (event: SessionHttpRequest) => Promise<void> | void>();
  const ctx = {
    options,
    location: { directory },
    session: {
      get: async () => ({ location: { directory } }),
      hook: async (name: string, callback: (event: SessionHttpRequest) => Promise<void> | void) => {
        hooks.set(name, callback);
        return { dispose: async () => { hooks.delete(name); } };
      },
    },
    tool: { transform: async () => ({ dispose: async () => {} }) },
  } as unknown as Context;
  return {
    ctx,
    async retry(type: string, message: string) {
      const event = { sessionID: "session-test", agent: "build",
        model: { providerID: "openai", id: "gpt-6.1-sol-fast" }, error: { type, message },
        attempt: 1, decision: { retry: true, delay: 1000 } } as SessionRetry;
      await (hooks.get("retry") as unknown as ((event: SessionRetry) => Promise<void> | void))?.(event);
      return event.decision;
    },
    async respond(request: Request) {
      const event = { sessionID: "session-test", agent: "build",
        model: { providerID: "openai", id: "gpt-6.1-sol-fast" }, kind: "primary", request,
        response: new Response("", { status: 429 }) } as SessionHttpResponse;
      await (hooks.get("http.response") as unknown as ((event: SessionHttpResponse) => Promise<void> | void))?.(event);
    },
    async dispatch(request: Request) {
      const event = {
        sessionID: "session-test", agent: "build", model: { providerID: "openai", id: "gpt-6.1-sol-fast" },
        kind: "primary", request,
      } as SessionHttpRequest;
      await hooks.get("http.request")?.(event);
      return event.request;
    },
  };
}

async function receiver() {
  const seen: Array<{ url: string; headers: http.IncomingHttpHeaders; body: string }> = [];
  const server = http.createServer(async (request, response) => {
    const chunks: Buffer[] = [];
    for await (const chunk of request) chunks.push(Buffer.from(chunk));
    seen.push({ url: request.url!, headers: request.headers, body: Buffer.concat(chunks).toString() });
    response.writeHead(200, { "content-type": "text/event-stream" });
    response.end('data: {"type":"response.completed"}\n\n');
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address() as { port: number };
  return {
    url: `http://127.0.0.1:${address.port}`, seen,
    close: () => new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve())),
  };
}

describe("Headroom native OpenCode V2 request routing", () => {
  it("fails promptly only when the routed loopback proxy refuses a connection", async () => {
    const plugin = await loadV2();
    const runtime = host({ proxyUrl: "http://127.0.0.1:9", excludeHosts: ["other.example"] });
    const cleanup = await plugin!.setup(runtime.ctx);
    try {
      const request = await runtime.dispatch(new Request("https://api.openai.com/v1/responses"));
      expect(await runtime.retry("provider.transport", "ConnectionRefused: Unable to connect.")).toEqual({ retry: false });
      expect(await runtime.retry("provider.transport", "Timeout: Unable to connect.")).toEqual({ retry: true, delay: 1000 });
      expect(await runtime.retry("provider.api", "Rate limit")).toEqual({ retry: true, delay: 1000 });
      await runtime.respond(request);
      expect(await runtime.retry("provider.transport", "ConnectionRefused: Unable to connect.")).toEqual({ retry: true, delay: 1000 });
      await runtime.dispatch(new Request("https://other.example/v1/responses"));
      expect(await runtime.retry("provider.transport", "ConnectionRefused: Unable to connect.")).toEqual({ retry: true, delay: 1000 });
    } finally { await cleanup?.(); }
  });
  it("routes real HTTP Responses bytes without changing model, Fast tier, auth, tools or signed reasoning", async () => {
    const plugin = await loadV2();
    expect(plugin?.setup, "OpenCode V2 requires an id/setup plugin, not the V1 factory").toBeTypeOf("function");
    if (!plugin) return;
    const proxy = await receiver();
    const runtime = host({ proxyUrl: proxy.url + "/v1" });
    const body = JSON.stringify({ model: "gpt-6.1-sol", service_tier: "priority", store: false, stream: true,
      input: [{ type: "reasoning", encrypted_content: "signed-byte-sequence" },
        { type: "function_call", call_id: "call-1", name: "shell", arguments: '{"command":"npm ls --json"}' },
        { type: "function_call_output", call_id: "call-1", output: '{"typescript":"6.0.3"}' }],
      tools: [{ type: "function", name: "shell", parameters: { type: "object", properties: {} } }] });
    const cleanup = await plugin.setup(runtime.ctx);
    try {
      const request = await runtime.dispatch(new Request("https://api.openai.com/v1/responses?check=1", {
        method: "POST", body,
        headers: { authorization: "Bearer test-only", "content-type": "application/json", host: "api.openai.com",
          "x-headroom-base-url": "https://wrong.example", "x-headroom-original-path": "/wrong" },
      }));
      const response = await fetch(request);
      expect(await response.text()).toBe('data: {"type":"response.completed"}\n\n');
      expect(proxy.seen[0].url).toBe("/v1/responses?check=1");
      expect(proxy.seen[0].body).toBe(body);
      expect(proxy.seen[0].headers.authorization).toBe("Bearer test-only");
      expect(proxy.seen[0].headers["x-headroom-base-url"]).toBe("https://api.openai.com");
      expect(proxy.seen[0].headers["x-headroom-original-path"]).toBe("/v1/responses");
      expect(proxy.seen[0].headers["x-headroom-project"]).toBe("/workspace/one");
      expect(proxy.seen[0].headers.host).toBe(new URL(proxy.url).host);
    } finally {
      await cleanup?.();
      await proxy.close();
    }
  });

  it("decorates already-routed inference but leaves documentation, excluded hosts and MCP untouched", async () => {
    const plugin = await loadV2();
    expect(plugin?.setup).toBeTypeOf("function");
    if (!plugin) return;
    const runtime = host({ proxyUrl: "http://127.0.0.1:8787", excludeHosts: ["*.example.com"] });
    const cleanup = await plugin.setup(runtime.ctx);
    try {
      for (const url of ["https://api.openai.com/v1/models", "https://sub.example.com/v1/responses",
        "http://127.0.0.1:4445/mcp", "http://127.0.0.1:8787/v1/responses"]) {
        const original = new Request(url);
        const routed = await runtime.dispatch(original);
        if (url === "http://127.0.0.1:8787/v1/responses") {
          expect(routed.url).toBe(original.url);
          expect(routed.headers.get("x-headroom-cwd")).toBe(encodeURIComponent("/workspace/one"));
          expect(routed.headers.get("x-headroom-memory-tools")).toBe("client");
        } else expect(routed).toBe(original);
      }
    } finally { await cleanup?.(); }
  });

  it("preserves cancellation and isolated project routing, and removes the hook on unload", async () => {
    const plugin = await loadV2();
    expect(plugin?.setup).toBeTypeOf("function");
    if (!plugin) return;
    const first = host({ proxyUrl: "http://127.0.0.1:8787" }, "/workspace/one");
    const second = host({ proxyUrl: "http://127.0.0.1:8788" }, "/workspace/two");
    const disposeFirst = await plugin.setup(first.ctx);
    const disposeSecond = await plugin.setup(second.ctx);
    try {
      const controller = new AbortController();
      const request = new Request("https://api.openai.com/v1/responses", { signal: controller.signal });
      const one = await first.dispatch(request);
      const two = await second.dispatch(new Request("https://api.openai.com/v1/responses"));
      expect(one.url).toBe("http://127.0.0.1:8787/v1/responses");
      expect(two.url).toBe("http://127.0.0.1:8788/v1/responses");
      expect(one.headers.get("x-headroom-project")).toBe("/workspace/one");
      expect(two.headers.get("x-headroom-project")).toBe("/workspace/two");
      controller.abort();
      expect(one.signal.aborted).toBe(true);
      await disposeFirst?.();
      const direct = new Request("https://api.openai.com/v1/responses");
      expect(await first.dispatch(direct)).toBe(direct);
    } finally { await disposeSecond?.(); }
  });

  it("uses each current session directory rather than the plugin location", async () => {
    const plugin = await loadV2();
    const runtime = host({ proxyUrl: "http://127.0.0.1:8787" });
    let directory = "/workspace/tiếng Việt 100%";
    runtime.ctx.session.get = async () => ({ location: { directory } }) as never;
    const cleanup = await plugin!.setup(runtime.ctx);
    try {
      const first = await runtime.dispatch(new Request("https://api.openai.com/v1/responses"));
      expect(first.headers.get("x-headroom-cwd")).toBe(encodeURIComponent(directory));
      expect(first.headers.get("x-headroom-memory-tools")).toBe("client");
      directory = "/workspace/moved";
      const moved = await runtime.dispatch(new Request("https://api.openai.com/v1/responses"));
      expect(moved.headers.get("x-headroom-cwd")).toBe(encodeURIComponent(directory));
    } finally { await cleanup?.(); }
  });

  it("cannot reuse a stale scope when session lookup fails", async () => {
    const plugin = await loadV2();
    const runtime = host({ proxyUrl: "http://127.0.0.1:8787" });
    runtime.ctx.session.get = async () => { throw new Error("unknown session"); };
    const cleanup = await plugin!.setup(runtime.ctx);
    try {
      const request = await runtime.dispatch(new Request("https://api.openai.com/v1/responses", {
        headers: { "x-headroom-cwd": "/forged", "x-headroom-project-id": "stale" },
      }));
      expect(request.url).toBe("http://127.0.0.1:8787/v1/responses");
      expect(request.headers.get("x-headroom-cwd")).toBeNull();
      expect(request.headers.get("x-headroom-project-id")).toBeNull();
      expect(request.headers.get("x-headroom-memory-unresolved")).toBe("true");
    } finally { await cleanup?.(); }
  });
});
