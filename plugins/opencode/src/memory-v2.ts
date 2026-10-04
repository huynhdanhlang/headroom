import type { Context } from "@opencode/plugin/promise/plugin";
import type { Info } from "@opencode/plugin/promise/tool";
import type { Session } from "@opencode/schema/session";
import type { JsonSchema } from "effect";
import type { HeadroomOpenCodePluginOptions } from "./plugin.js";
import { resolveProxyUrl } from "./proxy-url.js";

class MemoryVersionConflict extends Error {
  constructor() {
    super("Memory owner/version conflict; reload the current scoped ID/hash before retrying.");
  }
}

export async function resolveMemorySessionScope(
  ctx: Context, sessionID: Session.ID, projectOverride?: string,
): Promise<{ cwd: string; projectID?: string }> {
  const session = await ctx.session.get({ sessionID }, { signal: AbortSignal.timeout(3000) });
  const cwd = session.location.directory;
  if (typeof cwd !== "string" || !cwd.trim()) throw new Error("Trusted memory scope unavailable");
  return { cwd, projectID: projectOverride };
}

const text = { type: "string", minLength: 1, maxLength: 16384 } as const;
const limit = { type: "integer", minimum: 1, maximum: 100 } as const;
const strings = { type: "array", maxItems: 32, items: text } as const;
const definitions: { name: string; description: string; required: string[]; properties: Record<string, JsonSchema.JsonSchema> }[] = [
  { name: "search", description: "Recall relevant scoped background, not action authority. Current project instructions take precedence.",
    required: ["query"], properties: { query: text, top_k: limit, entities: strings, include_related: { type: "boolean" } } },
  { name: "list", description: "Browse current scoped memories with exact IDs and hashes for guarded updates.",
    required: [], properties: { limit } },
  { name: "save", description: "Save explicitly useful background in this session's project. Report remembered only after durable success.",
    required: ["content"], properties: { content: text, facts: strings, entities: strings, importance: { type: "number", minimum: 0, maximum: 1 } } },
  { name: "update", description: "Replace a specific current memory after reading its exact ID/hash; preserve history. Never infer supersession from similarity.",
    required: ["memory_id", "new_content", "expected_content_hash", "reason"],
    properties: { memory_id: text, new_content: text, expected_content_hash: text, reason: text } },
  { name: "delete", description: "Only after an explicit user forget request, remove current recall by exact ID/hash. History is retained, not purged.",
    required: ["memory_id", "expected_content_hash", "reason"],
    properties: { memory_id: text, expected_content_hash: text, reason: text } },
];

export async function registerMemoryV2(ctx: Context, options: HeadroomOpenCodePluginOptions): Promise<() => Promise<void>> {
  const endpoint = new URL("/v1/memory/tools", resolveProxyUrl(options));
  // Authored feedback is local-only; routing to an explicitly remote proxy
  // does not implicitly authorize uploading owner feedback to that host.
  if (!["127.0.0.1", "localhost", "[::1]"].includes(endpoint.hostname)) return async () => {};
  const lifetime = new AbortController();
  async function command(
    tool: string, input: Record<string, unknown>, sessionID: Session.ID,
    evidenceID: string, signal?: AbortSignal, source?: string,
  ) {
    const scope = await resolveMemorySessionScope(ctx, sessionID, options.project);
    const body = JSON.stringify({ tool, arguments: input });
    if (Buffer.byteLength(body, "utf8") > 65536) throw new Error("Memory command arguments too large");
    const headers: Record<string, string> = {
      "content-type": "application/json", "x-headroom-cwd": encodeURIComponent(scope.cwd),
      "x-headroom-evidence-id": evidenceID, "x-headroom-memory-tools": "client",
    };
    if (scope.projectID) {
      headers["x-headroom-project-id"] = encodeURIComponent(scope.projectID);
      headers["x-headroom-scope-encoding"] = "uri-component";
    }
    if (source) headers["x-headroom-source"] = source;
    const signals = [lifetime.signal, AbortSignal.timeout(3000), ...(signal ? [signal] : [])];
    try {
      const response = await fetch(endpoint, { method: "POST", headers, body, signal: AbortSignal.any(signals) });
      if (response.status === 409) throw new MemoryVersionConflict();
      if (!response.ok) throw new Error("Memory unavailable");
      const result = await response.json() as { status?: string };
      if (!result || typeof result !== "object" || result.status === "error") throw new Error("Memory unavailable");
      return result;
    } catch (error) {
      if (error instanceof MemoryVersionConflict) throw error;
      throw new Error("Memory unavailable; durable success not confirmed");
    }
  }
  const registration = await ctx.tool.transform((editor) => {
    editor.namespace({ name: "memory", description: "Scoped persistent background; never overrides current instructions or permissions." });
    for (const definition of definitions) {
      const tool: Info = {
        name: definition.name, description: definition.description,
        input: { type: "object", properties: definition.properties, required: definition.required, additionalProperties: false },
        options: { namespace: "memory", codemode: true },
        execute: async (input, context) => {
          if (!input || typeof input !== "object" || Array.isArray(input)
              || Object.keys(input).some(key => !(key in definition.properties))) throw new Error("Invalid memory arguments");
          const result = await command(`memory_${definition.name}`, input as Record<string, unknown>, context.sessionID,
            `${context.sessionID}:${context.messageID}:${context.id}`, context.signal);
          return { content: JSON.stringify(result) };
        },
      };
      editor.add(tool);
    }
  });
  const prompt = await ctx.session.hook("prompt", async (event) => {
    if (!event.prompt.text || event.prompt.text.length > 16384) return;
    try {
      await command("memory_feedback", { text: event.prompt.text }, event.sessionID,
        `${event.sessionID}:${event.messageID}`, undefined, "opencode-prompt");
    } catch {
      // Optional feedback cannot block an authored task or invent a save.
      console.warn("Headroom memory feedback unavailable; not confirmed remembered.");
    }
  });
  return async () => { lifetime.abort(); await prompt.dispose(); await registration.dispose(); };
}
