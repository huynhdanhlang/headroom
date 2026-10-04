import http from "node:http";
import type { Context } from "@opencode/plugin/promise/plugin";
import type { SessionPrompt } from "@opencode/plugin/promise/session";
import type { Info, ToolContext, ToolEditor } from "@opencode/plugin/promise/tool";
import { describe, expect, it } from "vitest";
import { HeadroomV2Plugin } from "./plugin-v2.js";

async function receiver(status = 200) {
  const seen: { headers: http.IncomingHttpHeaders; body: string }[] = [];
  const server = http.createServer(async (req, res) => {
    const chunks: Buffer[] = [];
    for await (const chunk of req) chunks.push(Buffer.from(chunk));
    seen.push({ headers: req.headers, body: Buffer.concat(chunks).toString() });
    res.writeHead(status, { "content-type": "application/json" });
    res.end(JSON.stringify({ status: "saved", memory_id: "synthetic-id" }));
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  return { seen, url: `http://127.0.0.1:${(server.address() as { port: number }).port}`,
    close: () => new Promise<void>((resolve) => server.close(() => resolve())) };
}

function host(proxyUrl: string, project?: string) {
  const directories = new Map([["a", "/synthetic/tiếng Việt 100%"], ["b", "/synthetic/project-b"]]);
  const tools = new Map<string, Info>();
  const hooks = new Map<string, (event: unknown) => Promise<void>>();
  const ctx = {
    options: { proxyUrl, project }, location: { directory: "/wrong/plugin-location" },
    session: { get: async ({ sessionID }: { sessionID: string }) => ({ location: { directory: directories.get(sessionID) } }),
      hook: async (name: string, callback: (event: unknown) => Promise<void>) => {
        hooks.set(name, callback); return { dispose: async () => { hooks.delete(name); } };
      } },
    tool: { transform: async (callback: (editor: ToolEditor) => void) => {
      callback({ namespace: () => {}, add: (tool: Info) => { tools.set(`${tool.options?.namespace}_${tool.name}`, tool); } } as unknown as ToolEditor);
      return { dispose: async () => { tools.clear(); } };
    } },
  } as unknown as Context;
  const context = (sessionID: string, signal = new AbortController().signal) => ({ sessionID,
    messageID: "message1", id: "call1", agent: "build", signal, progress: async () => {} }) as unknown as ToolContext;
  return { ctx, directories, tools, hooks, context };
}

describe("native executable scoped memory", () => {
  it("discovers five tools and sends per-session trusted scope on real HTTP", async () => {
    const api = await receiver();
    const runtime = host(api.url);
    const cleanup = await HeadroomV2Plugin.setup(runtime.ctx);
    try {
      expect([...runtime.tools.keys()]).toEqual(["memory_search", "memory_list", "memory_save", "memory_update", "memory_delete"]);
      const save = runtime.tools.get("memory_save")!;
      const result = await save.execute({ content: "Đừng dùng dữ liệu giả." }, runtime.context("a"));
      expect(result.content).toContain('"status":"saved"');
      expect(api.seen[0].headers["x-headroom-cwd"]).toBe(encodeURIComponent(runtime.directories.get("a")!));
      expect(api.seen[0].headers["x-headroom-evidence-id"]).toBe("a:message1:call1");
      expect(JSON.parse(api.seen[0].body)).toEqual({ tool: "memory_save", arguments: { content: "Đừng dùng dữ liệu giả." } });
      runtime.directories.set("a", "/synthetic/moved");
      await runtime.tools.get("memory_list")!.execute({}, runtime.context("a"));
      await runtime.tools.get("memory_list")!.execute({}, runtime.context("b"));
      expect(api.seen[1].headers["x-headroom-cwd"]).toBe(encodeURIComponent("/synthetic/moved"));
      expect(api.seen[2].headers["x-headroom-cwd"]).toBe(encodeURIComponent("/synthetic/project-b"));
    } finally { await cleanup?.(); await api.close(); }
    expect(runtime.tools.size).toBe(0);
    expect(runtime.hooks.size).toBe(0);
  });

  it("captures only authored prompt text with stable replay identity, not attachments or compaction", async () => {
    const api = await receiver(); const runtime = host(api.url, "explicit-project");
    const cleanup = await HeadroomV2Plugin.setup(runtime.ctx);
    try {
      expect(runtime.hooks.has("prompt")).toBe(true);
      const event = { sessionID: "a", messageID: "prompt1", prompt: { text: "Nhớ quy tắc này: đừng dùng dữ liệu giả.",
        files: [{ uri: "file:///private/attached", description: "Never modify data." }] }, delivery: "steer" } as SessionPrompt;
      const original = JSON.stringify(event);
      await runtime.hooks.get("prompt")!(event);
      await runtime.hooks.get("prompt")!(event);
      expect(api.seen.map(r => r.headers["x-headroom-evidence-id"])).toEqual(["a:prompt1", "a:prompt1"]);
      expect(api.seen[0].headers["x-headroom-project-id"]).toBe("explicit-project");
      expect(api.seen[0].body).not.toContain("attached");
      expect(JSON.stringify(event)).toBe(original);
      expect(runtime.hooks.has("compaction")).toBe(false);
    } finally { await cleanup?.(); await api.close(); }
  });

  it("reports unavailable or unresolved writes without claiming remembered, and respects cancellation", async () => {
    const runtime = host("http://127.0.0.1:9");
    const cleanup = await HeadroomV2Plugin.setup(runtime.ctx);
    try {
      const save = runtime.tools.get("memory_save"); expect(save).toBeDefined();
      await expect(save!.execute({ content: "rule" }, runtime.context("a"))).rejects.toThrow(/Memory unavailable/);
      await expect(save!.execute({ content: "rule" }, runtime.context("unknown"))).rejects.toThrow(/scope/);
      const controller = new AbortController(); controller.abort();
      await expect(save!.execute({ content: "rule" }, runtime.context("a", controller.signal))).rejects.toThrow();
      await expect(save!.execute({ content: "rule", user_id: "bob" }, runtime.context("a"))).rejects.toThrow(/arguments/);
    } finally { await cleanup?.(); }
  });

  it("distinguishes stale-owner/version conflicts from unavailable memory without leaking server detail", async () => {
    const api = await receiver(409);
    const runtime = host(api.url);
    const cleanup = await HeadroomV2Plugin.setup(runtime.ctx);
    try {
      await expect(runtime.tools.get("memory_update")!.execute({ memory_id: "old-id", new_content: "rule",
        expected_content_hash: "old-hash", reason: "owner correction" }, runtime.context("a")))
        .rejects.toThrow(/owner\/version conflict.*reload/i);
    } finally { await cleanup?.(); await api.close(); }
  });
});
