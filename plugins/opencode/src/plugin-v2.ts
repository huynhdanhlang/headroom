import type { Plugin } from "@opencode/plugin/promise/plugin";
import type { HeadroomOpenCodePluginOptions } from "./plugin.js";
import { resolveProxyUrl } from "./proxy-url.js";
import { routeHeadroomRequest } from "./transport.js";
import { registerMemoryV2, resolveMemorySessionScope } from "./memory-v2.js";

/** Native V2 adapter. V1 factories and child-process transport remain unchanged. */
export const HeadroomV2Plugin: Plugin = {
  id: "headroom.opencode.v2",
  async setup(ctx) {
    const options = ctx.options as HeadroomOpenCodePluginOptions;
    const proxyUrl = resolveProxyUrl(options);
    const proxy = new URL(proxyUrl);
    if (proxy.protocol !== "http:" && proxy.protocol !== "https:") {
      throw new Error("Headroom proxyUrl must use HTTP or HTTPS");
    }
    const project = options.project ?? ctx.location.project?.id ?? ctx.location.directory;
    const loopback = ["127.0.0.1", "localhost", "[::1]"].includes(proxy.hostname);
    const disposeMemory = await registerMemoryV2(ctx, options);
    // Bounded pending transports scoped to this host; HTTP responses clear
    // ownership so upstream rate limits/errors keep OpenCode's normal retries.
    const pending = new Set<string>();
    const key = (event: { sessionID: string; agent: string; model: unknown }) =>
      JSON.stringify([event.sessionID, event.agent, event.model]);
    const registration = await ctx.session.hook("http.request", async (event) => {
      let scope: { cwd: string; projectID?: string } | undefined;
      try { scope = await resolveMemorySessionScope(ctx, event.sessionID, options.project); } catch { /* Fail closed for memory, not inference. */ }
      const routed = routeHeadroomRequest(event.request, {
        proxyUrl, project, excludeHosts: options.excludeHosts,
        cwd: scope?.cwd, memoryProjectID: scope?.projectID,
        clientMemoryTools: loopback, memoryUnresolved: !scope,
      });
      pending.delete(key(event));
      if (loopback && routed !== event.request) {
        if (pending.size >= 256) pending.delete(pending.values().next().value!);
        pending.add(key(event));
      }
      event.request = routed;
    });
    const response = await ctx.session.hook("http.response", (event) => {
      pending.delete(key(event));
    });
    const retry = await ctx.session.hook("retry", (event) => {
      if (pending.has(key(event)) && event.error.type === "provider.transport" &&
          /^ConnectionRefused\b/.test(event.error.message)) event.decision = { retry: false };
    });
    // Other failures keep OpenCode recovery. No failure bypasses the proxy.
    return async () => {
      await registration.dispose();
      await response.dispose();
      await retry.dispose();
      await disposeMemory();
      pending.clear();
    };
  },
};
