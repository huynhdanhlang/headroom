// src/proxy-url.ts
var proxyUrlCache = null;
function getDefaultProxyUrl() {
  return proxyUrlCache ?? process.env.HEADROOM_BASE_URL ?? "http://localhost:8787";
}
function resolveProxyUrl(options) {
  return (options?.proxyUrl ?? process.env.HEADROOM_PROXY_URL ?? process.env.HEADROOM_BASE_URL ?? getDefaultProxyUrl()).replace(/\/+$/, "");
}

// src/transport.ts
import { createRequire, syncBuiltinESMExports } from "module";
var nodeRequire = createRequire(import.meta.url);
var http = nodeRequire("node:http");
var https = nodeRequire("node:https");
var http2 = nodeRequire("node:http2");
var childProcess = nodeRequire("node:child_process");
var fs = nodeRequire("node:fs");
var BASE_URL_HEADER = "x-headroom-base-url";
var ORIGINAL_PATH_HEADER = "x-headroom-original-path";
var PROJECT_HEADER = "x-headroom-project";
var EXCLUDE_HOSTS_ENV = "HEADROOM_OPENCODE_EXCLUDE_HOSTS";
function normalizeProxyUrl(proxyUrl) {
  return new URL(proxyUrl);
}
function isLoopback(hostname) {
  const normalized = hostname.toLowerCase().replace(/^\[|\]$/g, "");
  return normalized === "localhost" || normalized === "127.0.0.1" || normalized === "::1";
}
function normalizeExcludeHosts(entries) {
  const hosts = /* @__PURE__ */ new Set();
  for (const entry of typeof entries === "string" ? entries.split(",") : entries) {
    const host = String(entry).trim().toLowerCase().replace(/^(\*\.|\.)/, "");
    if (host) {
      hosts.add(host);
    }
  }
  return [...hosts];
}
function isExcludedHost(hostname, excludeHosts) {
  const normalized = hostname.toLowerCase().replace(/^\[|\]$/g, "");
  return excludeHosts.some((host) => normalized === host || normalized.endsWith(`.${host}`));
}
function isLlmEndpointPath(pathname) {
  return pathname.endsWith("/chat/completions") || pathname.endsWith("/responses") || pathname.endsWith("/messages") || pathname.endsWith(":generateContent") || pathname.endsWith(":streamGenerateContent");
}
function isRoutableUpstream(url, proxy, excludeHosts) {
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return false;
  }
  if (isLoopback(url.hostname)) {
    return false;
  }
  if (url.origin === proxy.origin) {
    return false;
  }
  if (isExcludedHost(url.hostname, excludeHosts)) {
    return false;
  }
  return true;
}
function shouldRoute(url, proxy, excludeHosts) {
  return isRoutableUpstream(url, proxy, excludeHosts) && isLlmEndpointPath(url.pathname);
}
function routedUrl(upstream, proxy) {
  return new URL(`${upstream.pathname}${upstream.search}`, proxy.origin);
}
function normalizedOpenAiProxyPath(pathname) {
  if (pathname.endsWith("/chat/completions")) {
    return "/v1/chat/completions";
  }
  if (pathname.endsWith("/responses")) {
    return "/v1/responses";
  }
  return void 0;
}
function routedUrlForOpenCode(upstream, proxy) {
  const normalizedPath = normalizedOpenAiProxyPath(upstream.pathname);
  if (!normalizedPath) {
    return {
      url: routedUrl(upstream, proxy),
      originalPath: void 0
    };
  }
  return {
    url: new URL(`${normalizedPath}${upstream.search}`, proxy.origin),
    originalPath: upstream.pathname
  };
}
function requestUrl(input) {
  if (input instanceof Request) {
    return new URL(input.url);
  }
  if (input instanceof URL) {
    return input;
  }
  return new URL(String(input));
}
function mergeFetchHeaders(input, init, upstream, originalPath = void 0, project = void 0) {
  const headers = new Headers(input instanceof Request ? input.headers : void 0);
  if (init?.headers) {
    new Headers(init.headers).forEach((value, key) => headers.set(key, value));
  }
  if (upstream) {
    headers.set(BASE_URL_HEADER, upstream.origin);
    headers.delete("host");
  }
  if (originalPath) {
    headers.set(ORIGINAL_PATH_HEADER, originalPath);
  }
  if (project) {
    headers.set(PROJECT_HEADER, /[^\x00-\xff]/.test(project) ? encodeURIComponent(project) : project);
  }
  return headers;
}
function withRoutedFetchInput(input, init, proxy, project, excludeHosts) {
  const upstream = requestUrl(input);
  if (!shouldRoute(upstream, proxy, excludeHosts)) {
    return [input, init];
  }
  const { url: nextUrl, originalPath } = routedUrlForOpenCode(upstream, proxy);
  const nextInit = {
    ...init,
    headers: mergeFetchHeaders(input, init, upstream, originalPath, project)
  };
  if (input instanceof Request) {
    return [new Request(nextUrl, input), nextInit];
  }
  return [nextUrl, nextInit];
}
function routeHeadroomRequest(request, options) {
  const excludes = normalizeExcludeHosts(options.excludeHosts ?? process.env[EXCLUDE_HOSTS_ENV] ?? "");
  const proxy = normalizeProxyUrl(options.proxyUrl);
  const [input, init] = withRoutedFetchInput(
    request,
    void 0,
    proxy,
    options.project,
    excludes
  );
  const direct = new URL(request.url);
  const alreadyRouted = direct.origin === proxy.origin && isLlmEndpointPath(direct.pathname);
  if (input === request && init === void 0 && !alreadyRouted) return request;
  if (alreadyRouted && !options.clientMemoryTools && !options.memoryUnresolved && !options.cwd && !options.memoryProjectID) return request;
  const routed = new Request(input, init);
  if (options.clientMemoryTools || options.memoryUnresolved) {
    for (const key of ["x-headroom-cwd", "x-headroom-project-id", "x-headroom-memory-unresolved", "x-headroom-scope-encoding"]) routed.headers.delete(key);
  }
  if (options.cwd) routed.headers.set("x-headroom-cwd", encodeURIComponent(options.cwd));
  if (options.memoryProjectID) {
    routed.headers.set("x-headroom-project-id", encodeURIComponent(options.memoryProjectID));
    routed.headers.set("x-headroom-scope-encoding", "uri-component");
  }
  if (options.clientMemoryTools) routed.headers.set("x-headroom-memory-tools", "client");
  if (options.memoryUnresolved) routed.headers.set("x-headroom-memory-unresolved", "true");
  return routed;
}

// src/memory-v2.ts
var MemoryVersionConflict = class extends Error {
  constructor() {
    super("Memory owner/version conflict; reload the current scoped ID/hash before retrying.");
  }
};
async function resolveMemorySessionScope(ctx, sessionID, projectOverride) {
  const session = await ctx.session.get({ sessionID }, { signal: AbortSignal.timeout(3e3) });
  const cwd = session.location.directory;
  if (typeof cwd !== "string" || !cwd.trim()) throw new Error("Trusted memory scope unavailable");
  return { cwd, projectID: projectOverride };
}
var text = { type: "string", minLength: 1, maxLength: 16384 };
var limit = { type: "integer", minimum: 1, maximum: 100 };
var strings = { type: "array", maxItems: 32, items: text };
var definitions = [
  {
    name: "search",
    description: "Recall relevant scoped background, not action authority. Current project instructions take precedence.",
    required: ["query"],
    properties: { query: text, top_k: limit, entities: strings, include_related: { type: "boolean" } }
  },
  {
    name: "list",
    description: "Browse current scoped memories with exact IDs and hashes for guarded updates.",
    required: [],
    properties: { limit }
  },
  {
    name: "save",
    description: "Save explicitly useful background in this session's project. Report remembered only after durable success.",
    required: ["content"],
    properties: { content: text, facts: strings, entities: strings, importance: { type: "number", minimum: 0, maximum: 1 } }
  },
  {
    name: "update",
    description: "Replace a specific current memory after reading its exact ID/hash; preserve history. Never infer supersession from similarity.",
    required: ["memory_id", "new_content", "expected_content_hash", "reason"],
    properties: { memory_id: text, new_content: text, expected_content_hash: text, reason: text }
  },
  {
    name: "delete",
    description: "Only after an explicit user forget request, remove current recall by exact ID/hash. History is retained, not purged.",
    required: ["memory_id", "expected_content_hash", "reason"],
    properties: { memory_id: text, expected_content_hash: text, reason: text }
  }
];
async function registerMemoryV2(ctx, options) {
  const endpoint = new URL("/v1/memory/tools", resolveProxyUrl(options));
  if (!["127.0.0.1", "localhost", "[::1]"].includes(endpoint.hostname)) return async () => {
  };
  const lifetime = new AbortController();
  async function command(tool, input, sessionID, evidenceID, signal, source) {
    const scope = await resolveMemorySessionScope(ctx, sessionID, options.project);
    const body = JSON.stringify({ tool, arguments: input });
    if (Buffer.byteLength(body, "utf8") > 65536) throw new Error("Memory command arguments too large");
    const headers = {
      "content-type": "application/json",
      "x-headroom-cwd": encodeURIComponent(scope.cwd),
      "x-headroom-evidence-id": evidenceID,
      "x-headroom-memory-tools": "client"
    };
    if (scope.projectID) {
      headers["x-headroom-project-id"] = encodeURIComponent(scope.projectID);
      headers["x-headroom-scope-encoding"] = "uri-component";
    }
    if (source) headers["x-headroom-source"] = source;
    const signals = [lifetime.signal, AbortSignal.timeout(3e3), ...signal ? [signal] : []];
    try {
      const response = await fetch(endpoint, { method: "POST", headers, body, signal: AbortSignal.any(signals) });
      if (response.status === 409) throw new MemoryVersionConflict();
      if (!response.ok) throw new Error("Memory unavailable");
      const result = await response.json();
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
      const tool = {
        name: definition.name,
        description: definition.description,
        input: { type: "object", properties: definition.properties, required: definition.required, additionalProperties: false },
        options: { namespace: "memory", codemode: true },
        execute: async (input, context) => {
          if (!input || typeof input !== "object" || Array.isArray(input) || Object.keys(input).some((key) => !(key in definition.properties))) throw new Error("Invalid memory arguments");
          const result = await command(
            `memory_${definition.name}`,
            input,
            context.sessionID,
            `${context.sessionID}:${context.messageID}:${context.id}`,
            context.signal
          );
          return { content: JSON.stringify(result) };
        }
      };
      editor.add(tool);
    }
  });
  const prompt = await ctx.session.hook("prompt", async (event) => {
    if (!event.prompt.text || event.prompt.text.length > 16384) return;
    try {
      await command(
        "memory_feedback",
        { text: event.prompt.text },
        event.sessionID,
        `${event.sessionID}:${event.messageID}`,
        void 0,
        "opencode-prompt"
      );
    } catch {
      console.warn("Headroom memory feedback unavailable; not confirmed remembered.");
    }
  });
  return async () => {
    lifetime.abort();
    await prompt.dispose();
    await registration.dispose();
  };
}

// src/plugin-v2.ts
var HeadroomV2Plugin = {
  id: "headroom.opencode.v2",
  async setup(ctx) {
    const options = ctx.options;
    const proxyUrl = resolveProxyUrl(options);
    const proxy = new URL(proxyUrl);
    if (proxy.protocol !== "http:" && proxy.protocol !== "https:") {
      throw new Error("Headroom proxyUrl must use HTTP or HTTPS");
    }
    const project = options.project ?? ctx.location.project?.id ?? ctx.location.directory;
    const loopback = ["127.0.0.1", "localhost", "[::1]"].includes(proxy.hostname);
    const disposeMemory = await registerMemoryV2(ctx, options);
    const pending = /* @__PURE__ */ new Set();
    const key = (event) => JSON.stringify([event.sessionID, event.agent, event.model]);
    const registration = await ctx.session.hook("http.request", async (event) => {
      let scope;
      try {
        scope = await resolveMemorySessionScope(ctx, event.sessionID, options.project);
      } catch {
      }
      const routed = routeHeadroomRequest(event.request, {
        proxyUrl,
        project,
        excludeHosts: options.excludeHosts,
        cwd: scope?.cwd,
        memoryProjectID: scope?.projectID,
        clientMemoryTools: loopback,
        memoryUnresolved: !scope
      });
      pending.delete(key(event));
      if (loopback && routed !== event.request) {
        if (pending.size >= 256) pending.delete(pending.values().next().value);
        pending.add(key(event));
      }
      event.request = routed;
    });
    const response = await ctx.session.hook("http.response", (event) => {
      pending.delete(key(event));
    });
    const retry = await ctx.session.hook("retry", (event) => {
      if (pending.has(key(event)) && event.error.type === "provider.transport" && /^ConnectionRefused\b/.test(event.error.message)) event.decision = { retry: false };
    });
    return async () => {
      await registration.dispose();
      await response.dispose();
      await retry.dispose();
      await disposeMemory();
      pending.clear();
    };
  }
};
export {
  HeadroomV2Plugin as default
};
