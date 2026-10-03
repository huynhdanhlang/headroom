#!/usr/bin/env node
// Matched live Responses probes over synthetic data. No credentials or prompt
// contents are written to the report; subscription savings are never inferred.
import { spawnSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import { parseArgs } from "node:util";
import { randomUUID } from "node:crypto";

const { values } = parseArgs({ options: {
  "proxy-url": { type: "string", default: "http://127.0.0.1:4474" },
  model: { type: "string", default: "gpt-6.1-sol" },
  rounds: { type: "string", default: "3" },
  output: { type: "string" },
  opencode: { type: "string", default: "opencode" },
} });
const proxy = new URL(values["proxy-url"]);
const rounds = Number(values.rounds);
if (!values.output || !Number.isInteger(rounds) || rounds < 2 || rounds > 10 ||
    proxy.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]"].includes(proxy.hostname)) {
  throw new Error("Use --output, 2–10 rounds, and a dedicated loopback HTTP --proxy-url");
}
const exported = spawnSync(values.opencode, ["auth", "export"], { encoding: "utf8", maxBuffer: 1048576 });
if (exported.status !== 0) throw new Error("Cannot read OpenCode credentials through auth export");
const accounts = JSON.parse(exported.stdout).filter((entry) => entry.integrationID === "openai");
if (accounts.length !== 1) throw new Error("Need exactly one OpenAI connection; refusing an ambiguous account");
const credential = accounts[0].value;
const token = credential.type === "oauth" ? credential.access : credential.key;
if (typeof token !== "string" || !token) throw new Error("The configured OpenCode connection has no usable credential");

const failedIDs = [37, 281];
const rows = Array.from({ length: 320 }, (_, id) => ({
  job_id: id, component: "synthetic-build-worker", duration_ms: 12,
  status: failedIDs.includes(id) ? "failed" : "healthy",
  message: failedIDs.includes(id) ? "CRITICAL: dependency installation failed" : "Operation completed successfully; no action required",
}));
const logInput = [
  { role: "user", content: [{ type: "input_text", text: "Analyze this synthetic job-log fixture." }] },
  { type: "function_call", call_id: "synthetic-log-1", name: "shell", arguments: JSON.stringify({ command: "printf '%s\\n' 'synthetic job logs'" }) },
  { type: "function_call_output", call_id: "synthetic-log-1", output: JSON.stringify(rows) },
  { role: "user", content: [{ type: "input_text", text: 'Return exactly JSON {"failed_job_ids":[...]} listing every failed job ID, ascending. Do not call tools.' }] },
];
const cases = [
  { name: "short", input: [{ role: "user", content: [{ type: "input_text", text: "Reply with exactly OK." }] }],
    correct: (text) => text.trim() === "OK" },
  { name: "large-tool-log", input: logInput,
    tools: [{ type: "function", name: "shell", description: "Synthetic benchmark log producer", parameters: { type: "object", properties: { command: { type: "string" } }, required: ["command"] } }],
    correct: (text) => {
      try { return JSON.stringify(JSON.parse(text.trim()).failed_job_ids) === "[37,281]"; }
      catch { return false; }
    } },
];
const results = [];
async function probe(test, route, round, sessionID) {
  const body = { model: values.model, input: test.input, ...(test.tools ? { tools: test.tools } : {}),
    service_tier: "priority", reasoning: { effort: "low" }, store: false, stream: true };
  const headers = { authorization: "Bearer " + token, "content-type": "application/json",
    accept: "text/event-stream", "session-id": sessionID };
  if (route === "proxy") Object.assign(headers, {
    "x-headroom-base-url": "https://api.openai.com", "x-headroom-original-path": "/v1/responses",
    "x-headroom-project": "opencode-isolated-benchmark",
  });
  const start = performance.now();
  const response = await fetch(route === "proxy" ? new URL("/v1/responses", proxy) : "https://api.openai.com/v1/responses", {
    method: "POST", body: JSON.stringify(body), headers, signal: AbortSignal.timeout(120000),
  });
  const headerMs = performance.now() - start;
  if (!response.ok) throw new Error(`${test.name}/${route}: HTTP ${response.status}; ${String(await response.text()).slice(0,600)}`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "", text = "", firstTokenMs, completed;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      const lines = pending.split("\n"); pending = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data: ") || line === "data: [DONE]") continue;
        const event = JSON.parse(line.slice(6));
        if (event.type === "response.output_text.delta") {
          firstTokenMs ??= performance.now() - start;
          text += event.delta;
        }
        if (event.type === "response.completed") completed = event.response;
        if (event.type === "response.failed" || event.type === "error") throw new Error(`${test.name}/${route}: stream failed`);
      }
    }
  } finally { await reader.cancel().catch(() => {}); }
  if (!completed) throw new Error(`${test.name}/${route}: missing completed response`);
  const usage = completed.usage;
  return { case: test.name, route, round, correct: test.correct(text),
    model: completed.model, requestedTier: "priority", returnedTier: completed.service_tier,
    headerMs, firstTokenMs, totalMs: performance.now() - start,
    inputTokens: usage?.input_tokens, cachedTokens: usage?.input_tokens_details?.cached_tokens,
    cacheWriteTokens: usage?.input_tokens_details?.cache_write_tokens,
    outputTokens: usage?.output_tokens, reasoningTokens: usage?.output_tokens_details?.reasoning_tokens,
    headroomHeaders: Object.fromEntries([...response.headers].filter(([key]) => /^x-headroom-(tokens|compression|overhead|request-id|ccr)/.test(key))) };
}
const percentile = (array, p) => {
  const sorted = array.filter(Number.isFinite).sort((a,b) => a-b);
  return sorted[Math.max(0,Math.ceil(sorted.length*p)-1)];
};
for (const test of cases) {
  const sessions = { direct: randomUUID(), proxy: randomUUID() };
  for (let round = 0; round < rounds; round++) {
    // Alternate order, keep one session per arm for repeat-prefix measurements,
    // and use the same fetch client/keepalive behavior for both arms.
    for (const route of round % 2 ? ["proxy", "direct"] : ["direct", "proxy"]) {
      const result = await probe(test, route, round, sessions[route]); results.push(result);
      console.log(JSON.stringify({ ...result, headroomHeaders: undefined }));
    }
  }
}
const summaries = cases.flatMap((test) => ["direct", "proxy"].map((route) => {
  const rows = results.filter((r) => r.case === test.name && r.route === route);
  return { case: test.name, route, trials: rows.length, correct: rows.filter((r) => r.correct).length,
    medianFirstTokenMs: percentile(rows.map((r) => r.firstTokenMs),0.5), p95FirstTokenMs: percentile(rows.map((r) => r.firstTokenMs),0.95),
    medianTotalMs: percentile(rows.map((r) => r.totalMs),0.5), inputTokens: rows.map((r) => r.inputTokens),
    cachedTokens: rows.map((r) => r.cachedTokens), returnedTiers: [...new Set(rows.map((r) => r.returnedTier))] };
}));
const statsResponse = await fetch(new URL("/stats", proxy));
const stats = await statsResponse.json();
const report = { measuredAt: new Date().toISOString(), model: values.model, reasoning: "low", rounds,
  scope: "Synthetic transcript, real live Responses calls; repeated prefixes, not a complete creator or coding eval. Small sample; no quota/dollar savings or universal model speedup inferred.",
  proxyUrl: proxy.origin, summaries, results,
  proxyStats: Object.fromEntries(["requests","tokens","latency","overhead","ttfb","pipeline_timing","compression","prefix_cache"].map((key) => [key,stats[key]])) };
await mkdir(dirname(values.output), { recursive: true });
await writeFile(values.output, JSON.stringify(report,null,2)+"\n", { mode: 0o600 });
console.log(JSON.stringify({ report: values.output, summaries }));
if (results.some((r) => !r.correct)) process.exitCode = 1;
