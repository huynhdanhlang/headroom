// One lightweight URL owner for the library, V1 factory and native V2 adapter.
let proxyUrlCache: string | null = null;

export function setDefaultProxyUrl(url: string): void {
  proxyUrlCache = url;
}

export function getDefaultProxyUrl(): string {
  return proxyUrlCache ?? process.env.HEADROOM_BASE_URL ?? "http://localhost:8787";
}

export function resolveProxyUrl(options?: { proxyUrl?: string }): string {
  return (options?.proxyUrl ?? process.env.HEADROOM_PROXY_URL ?? process.env.HEADROOM_BASE_URL ?? getDefaultProxyUrl())
    .replace(/\/+$/, "");
}

export function resolveSessionToken(options?: { sessionToken?: string }): string | undefined {
  return options?.sessionToken ?? process.env.HEADROOM_OPENCODE_SESSION_TOKEN;
}
