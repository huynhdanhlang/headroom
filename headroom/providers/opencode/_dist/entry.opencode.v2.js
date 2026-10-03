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
function shouldRoute(url, proxy, excludeHosts) {
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
  return isLlmEndpointPath(url.pathname);
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
    headers.set(PROJECT_HEADER, project);
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
  const [input, init] = withRoutedFetchInput(
    request,
    void 0,
    normalizeProxyUrl(options.proxyUrl),
    options.project,
    excludes
  );
  return input === request && init === void 0 ? request : new Request(input, init);
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
    const pending = /* @__PURE__ */ new Set();
    const key = (event) => JSON.stringify([event.sessionID, event.agent, event.model]);
    const registration = await ctx.session.hook("http.request", (event) => {
      const routed = routeHeadroomRequest(event.request, {
        proxyUrl,
        project,
        excludeHosts: options.excludeHosts
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
      pending.clear();
    };
  }
};
export {
  HeadroomV2Plugin as default
};
