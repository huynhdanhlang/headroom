# Reliable Feedback Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Repository authority requires the main agent to remain the sole writer; conditional read-only review is not implementation delegation.

**Goal:** Preserve the meaning of owner feedback and make scoped, versioned memory usable across OpenCode sessions without replacing current project authority.

**Architecture:** Repair the existing TrafficLearner, SQLite/HierarchicalMemory/LocalBackend lifecycle and native OpenCode V2 adapter. A bounded local command adapter connects native tools and authored prompt feedback to the same MemoryHandler and project store used by inference. Existing project instructions remain authoritative; recalled entries are background, not execution grants.

**Tech Stack:** Python/FastAPI/SQLite with the existing native Headroom base; TypeScript/OpenCode plugin API 2.0.22; pytest and Vitest; existing Docker runtime, not a new app topology.

**Spec:** `docs/superpowers/specs/2026-10-04-feedback-memory-design.md` — owner approved 2026-10-04.

## Global Constraints

- Baseline source HEAD: `520ff80992362163ee91da3295ff4a52bcd921c0`; only our untracked specification existed at planning time. Check freshness before edits; preserve all later unrelated work.
- Native/dependency anchor remains upstream `1cf496612e781ef8d67ff87ee4f78037492f0bc7`, as owned by `FORK.md`. No new runtime/model/embedding dependency or provider substitution.
- Source work is uncommitted. No commit/push/merge, release-image build from dirty source, service/config activation, video-app restart or creator-project write without the required specific authority.
- Use a disposable QA image/state for Python verification. Never mount `/home/huynhdanhlang/Headroom/state` or Engine data into tests. No real upstream inference or telemetry in focused regressions.
- Preserve cache-hot prefixes, signed reasoning, model/Fast parameters, exact source reads, CCR retrieval, request isolation and accounting.
- Missing trusted project identity fails closed. Model arguments never select user identity, cwd, project ID or database path.
- Retrieved memory never changes permissions, product stage, Rights/consent, human approval or release authority. Similarity is not rule identity or supersession evidence.
- Feedback/body limits: 16,384 Unicode characters per text; 65,536 bytes per command body; at most 32 facts, 100 search/list results. Reject overflow, do not silently truncate meaning.
- Candidate injection budget: at most six entries and 1,200 heuristic tokens, only after focused evidence. Do not change live top-k/settings during source work.
- AI Motion Video keeps its PDR, Roadmap and Active Plan; no new product design/status authority. Back up dirty instruction/checkpoint preimages with SHA256 and restore manifest before editing.

## Review Focus

1. A prohibition or Vietnamese multi-clause correction must never become a positive instruction; Task 1 pins full wording and clause coverage.
2. A session moved between directories must use its current location for both inference and tools; Task 5 tests moves and concurrent sessions.
3. A repeated prompt, interrupted save or retry must not duplicate a memory or inflate evidence; Tasks 1 and 3 test replay/restart and partial-index recovery.
4. A foreign/stale memory ID or simultaneous update must not alter another owner or fork the active chain; Task 2 tests ownership and atomic conflict.
5. Quoted instructions, harness text, unavailable memory and old project evidence must not grant action authority; Tasks 1, 4, 6 and 7 pin refusal/fallback and current-source precedence.

## Verification setup and file responsibilities

Retain `traffic_learner.py` as the authored-feedback detector; no competing classifier. Retain `adapters/sqlite.py` as the transactional memory owner and `core.py` as its indexing/history consumer. Keep HTTP input/access validation in new `proxy/memory_commands.py`, called by one route registration in `server.py`. Keep V2 scope resolution and native tool/prompt hooks in new `plugins/opencode/src/memory-v2.ts`, invoked by the existing V2 plugin; transport continues to own HTTP routing. These two new adapters have demonstrated consumers and introduce no storage owner.

Host Python and the live image do not have pytest; the live image does have the native Headroom extension. Do not install into the live container. At execution, create a **non-release QA image** under `/tmp/opencode`: base it on the exact local image ID returned by `docker inspect ai-motion-headroom-proxy-1 --format '{{.Image}}'`; add only pytest/pytest-asyncio and their dev dependencies at versions read from the checked-in `uv.lock`. Overlay only the explicit changed Python files into the installed package, preserving its native extension. Before the fix, use no source overlays so the regression exercises the baseline. Rebuild that QA image after each changed Python batch; it must never be promoted to production.

Define the following execution helpers, with `ROOT` set to the isolated checkout and `QA_IMAGE` to the current disposable candidate:

```bash
pytests() {
  docker run --rm --network none --cpus=2 --entrypoint python \
    -v "$ROOT/tests:/work/tests:ro" -v "$ROOT/pyproject.toml:/work/pyproject.toml:ro" \
    -w /work "$QA_IMAGE" -m pytest -p no:cacheprovider "$@"
}
```

Node tests use the installed host fnm Node/pnpm and existing locked plugin dependencies: `pnpm --dir plugins/opencode exec vitest run <files>`. If isolation/setup fails twice, stop expanding the harness and use a smaller owner-level check, reporting the unverified integration limit. No standalone production server is needed for ordinary ASGI/native-hook regressions.

### Task 1: Preserve authored feedback and independent evidence

**Files:** Modify `headroom/memory/traffic_learner.py` (`_extract_preferences`, `_find_correction`, `on_messages`, `_accumulate`, native-file flush); extend `tests/test_memory/test_traffic_learner.py` and `tests/test_openai_responses_traffic_learner.py`.

**Interfaces:** Retain `_find_correction(text: str) -> str | None` for compatibility, returning the first complete authored correction. Add `_find_corrections(text: str) -> list[str]` for all supported clauses. `_extract_preferences` returns existing `ExtractedPattern` objects with full source text, `explicit_retention: bool` and advisory/explicit provenance metadata. Extend `on_messages(..., *, evidence_id: str | None = None)` so a trusted authored event can distinguish new evidence from replay.

- [ ] Write regressions asserting original wording for `Don't use fake data.`, `Never modify production data.`, `Đừng dùng dữ liệu giả.`, and `Không được sửa dữ liệu production.`; two complete clauses survive, as does a correction after character 500.
- [ ] Add negative cases: quoted/example-only prohibition, `<system-reminder>`, appended recalled memories, a one-time “fix this file” request and ordinary “không có API” observation. None is a mandatory learned rule. Without durable intent, a genuine correction remains advisory.
- [ ] Add replay assertions: the same evidence ID does not increment confidence; independent IDs may increment; explicit “remember this rule” needs one durable occurrence. Anonymous replay is not new independent evidence. Disable native-file promotion for this integration without breaking explicit opt-in native writing.
- [ ] Run `pytests tests/test_memory/test_traffic_learner.py tests/test_openai_responses_traffic_learner.py`; confirm the newly added behavior fails on the baseline.
- [ ] Implement Unicode-aware bounded clause scanning that retains triggers/negation, removes the 500-character blind spot and filters unauthored context. Persist original wording, not the stripped tail or an invented summary. Integrate independent evidence into the existing accumulator; do not infer recovery from an unrelated successful tool call.
- [ ] Rebuild QA overlays, rerun these two files and inspect the scoped diff. Leave uncommitted.

### Task 2: Guard immutable update and forget at the actual owner

**Files:** Modify `headroom/memory/models.py`, `headroom/memory/ports.py`, `headroom/memory/adapters/sqlite.py`, `headroom/memory/core.py`, `headroom/memory/backends/local.py`; extend `tests/test_memory/test_core_operations.py`, `tests/test_memory/test_supersession_repair.py`, `tests/test_memory_handler_native_ops.py`.

**Interfaces:** Add `Memory.content_hash: str` (`sha256:` plus SHA256 of exact UTF-8 content) and `MemoryConflictError(ValueError)`. Extend `SQLiteMemoryStore.supersede(old_memory_id, new_memory, supersede_time=None, *, expected_content_hash: str | None = None, expected_user_id: str | None = None) -> Memory`; pass the same guards through `HierarchicalMemory.supersede`, which also accepts optional `metadata_updates: dict | None` for audit reason. Extend `LocalBackend.update_memory(memory_id, new_content, reason=None, user_id=None, *, expected_content_hash: str | None = None) -> Memory`, forwarding `user_id` as the expected owner. The native-command path always supplies owner and hash; legacy unguarded interfaces remain compatible. Add `SQLiteMemoryStore.forget(memory_id: str, *, user_id: str, expected_content_hash: str, reason: str) -> bool`, `HierarchicalMemory.forget` with the same signature, and `LocalBackend.delete_memory_guarded(memory_id: str, user_id: str, expected_content_hash: str, reason: str) -> bool` as its public-backend wrapper. Forget ends validity and marks the existing row forgotten; it is not an unrequested history/backup purge.

- [ ] Add tests for foreign ownership, nonexistent ID, stale hash, already-superseded ID, two competing successors, and rollback between old-row update/new-row insert. Assert one active successor, unchanged losing input/old content, complete history and preserved audit reason.
- [ ] Run `pytests tests/test_memory/test_core_operations.py tests/test_memory/test_supersession_repair.py tests/test_memory_handler_native_ops.py`; confirm new guard tests fail.
- [ ] Move guarded current-row lookup and CAS into the existing SQLite transaction (`BEGIN IMMEDIATE`); check exact ID, owner, content hash and active state before changing either row. Core embeds before the transaction and only changes indexes/cache after the committed result. Reject a foreign ID before embedding or writes.
- [ ] Make LocalBackend use `user_id` and `reason` instead of ignoring them. Pass optional guards through `MemoryStore`/core without forcing unrelated backend implementations to claim support. Unsupported guarded operations return unsupported, never delete-then-save.
- [ ] Make guarded forget check the exact owner/head in the same transaction that ends its validity and writes `forgotten_at`/audit reason into the existing row metadata; then remove it from existing active indexes/cache. Keep the evidence identity so an old prompt replay cannot recreate a forgotten rule. Expose it only for an explicit owner forget request, truthfully describing retained history; no automated cleanup or backup purge is part of this task.
- [ ] Rebuild QA overlays, rerun the three files and verify current search excludes superseded rows while historical queries retain the old version. Leave uncommitted.

### Task 3: Idempotent durable saves and post-crash index recovery

**Files:** Modify the retained SQLite store/core/LocalBackend from Task 2 and `headroom/proxy/memory_handler.py`; extend `tests/test_memory/test_core_operations.py` and `tests/test_memory_handler_native_ops.py`.

**Interfaces:** Add `SQLiteMemoryStore.save_if_absent(memory: Memory) -> tuple[Memory, bool]`. Add optional `evidence_key: str | None` to `HierarchicalMemory.add` and `LocalBackend.save_memory`. With a key, derive a stable opaque ID from user plus scoped evidence identity; no key preserves current behavior. The store returns an existing identical row or raises conflict for changed content under the same identity. Save results include `memory_id`, `content_hash`, scope and `replayed: bool`.

- [ ] Write tests for two identical concurrent saves, same key/different content conflict, distinct users/projects, independent similar facts and a durable row whose index step failed before retry. Assert one primary row, no similarity-based replacement and successful active-index recovery without changed evidence count. Replay after supersession or forget must not revive or re-index the old rule, and must return an explicit superseded/forgotten outcome instead of claiming a new save.
- [ ] Run `pytests tests/test_memory/test_core_operations.py tests/test_memory_handler_native_ops.py`; verify new idempotency/recovery cases fail.
- [ ] Implement transactional insert-if-absent at SQLite, preserving existing save semantics outside the evidence path. On replay, verify the existing content/provenance; repair indexes/cache only for an active durable row. A superseded/forgotten row remains inactive and is never recreated. Do not manufacture a second row or claim a queued write succeeded.
- [ ] Extend handler saves with validated provenance/evidence fields, and return the committed ID/hash/scope. Facts use distinct clause identities beneath the same authored event, not one key shared by every fact.
- [ ] Rebuild QA overlays and rerun the focused files. Leave uncommitted.

### Task 4: Bounded local memory command adapter

**Files:** Create `headroom/proxy/memory_commands.py` and `tests/test_memory_commands.py`; modify `headroom/proxy/server.py`, `headroom/proxy/memory_handler.py`, `docker/Dockerfile.ai-motion` (additive source copies only).

**Interfaces:** `register_memory_commands(app: FastAPI, proxy: HeadroomProxy) -> None` installs `POST /v1/memory/tools` before provider passthrough. Request body is `{tool: str, arguments: dict}`. Public allowlist: `memory_search`, `memory_list`, `memory_save`, `memory_update`, guarded `memory_delete`. An internal `memory_feedback` operation accepts original authored text and stable event identity from the native prompt adapter, feeds Task 1 and saves explicit-retention results through Task 3; it is not a model-visible tool. Add `MemoryHandler.execute_scoped_command(tool_name: str, input_data: dict, user_id: str, request_context: RequestContext) -> dict` as the validated facade over existing dispatch.

- [ ] Write ASGI tests for body overflow, malformed JSON, invalid operation/types/limits, untrusted origin/remote peer, absent scope, identity override attempts, disabled/unavailable backend, ID ownership, conflict, safe error text and request cancellation. Missing scope must not create a global store.
- [ ] Write the bounded same-owner integration test: save → list/search → update with exact returned hash → old-hash conflict → reread current version; API and inference resolve the same partition. Internal feedback with no durable intent returns ignored/advisory without a rule write.
- [ ] Run `pytests tests/test_memory_commands.py`; confirm the endpoint is missing or new assertions fail.
- [ ] Implement validation before initialization, reuse existing local/container-gateway and same-origin access guards, resolve user/project from trusted request headers, and delegate to the canonical handler. Do not accept scope selectors in model arguments. Return explicit error statuses with no private transport details. Unsupported guard capabilities fail closed.
- [ ] Register the adapter once, add each new/modified Python runtime file to the existing additive Docker recipe, and verify no native/dependency input changed. Do not run the clean-release build gate on the dirty checkout.
- [ ] Rebuild QA overlays; run `pytests tests/test_memory_commands.py tests/test_memory_handler_project_isolation.py tests/test_memory_handler_native_ops.py`. Leave uncommitted.

### Task 5: Native OpenCode memory tools, authored capture and matching scope

**Files:** Create `plugins/opencode/src/memory-v2.ts` and `plugins/opencode/src/memory-v2.test.ts`; modify `plugin-v2.ts`, `plugin-v2.test.ts`, `transport.ts` and its existing transport tests. Preserve V1 entries.

**Interfaces:** `resolveMemorySessionScope(ctx: Context, sessionID: Session.ID, projectOverride?: string) -> Promise<{cwd: string; projectID?: string}>` reads `ctx.session.get({sessionID})` and the actual session location; no instance-directory fallback for unknown sessions. `registerMemoryV2(ctx: Context, options: HeadroomOpenCodePluginOptions) -> Promise<Cleanup>` registers tools/prompt hooks and returns cleanup. Extend the routing options with `cwd?: string` and `memoryProjectID?: string`; retain `project` for attribution.

- [ ] Extend the native-hook test host with real session lookup and tool-transform capture. Add cases for two sessions observed by one plugin, a moved session, Unicode/space/percent paths, explicit project-ID override, missing lookup and preserved body/auth/model/Fast/signed-reasoning/AbortSignal bytes.
- [ ] Add a real receiving local HTTP server test for native tool discovery/execution, authored prompt events, evidence-ID replay, unavailable API and cleanup. Assert model arguments cannot replace scope/user and a failed save is not reported as remembered. A session move must also change memory-tool scope. Client-owned native tools must not be duplicated by invisible proxy-only tool definitions.
- [ ] Run `pnpm --dir plugins/opencode exec vitest run src/plugin-v2.test.ts src/memory-v2.test.ts`; observe the new scope/tools cases fail.
- [ ] Implement per-session scope lookup and correct percent-encoded `x-headroom-cwd`/optional `x-headroom-project-id`. Keep `x-headroom-project` attribution intact. Signal client-owned memory tools with `x-headroom-memory-tools: client`, handled per request in Task 6 rather than by mutating shared configuration. Native HTTP routing remains byte-preserving and never bypasses the proxy on failure.
- [ ] Register namespace `memory` with search/save/list/update/delete executable schemas (`codemode: true`), mapping effective operations to Task 4. Updates/deletes require exact ID/hash; delete description requires an explicit user forget request. Derive replay identity from trusted session/message/call context, not model-supplied scope fields. Use bounded timeout and the runtime cancellation signal.
- [ ] On the V2 `prompt` hook, send only the actual authored prompt and its stable session/message evidence ID to internal feedback capture. Do not capture title/generate/compaction, synthetic reminders, attached file content or recalled context as owner feedback. No automatic AGENTS edits and no paid model call.
- [ ] Rerun the focused V2 and existing transport tests. Inspect references with TypeScript tools and run the pinned compiler for these changes without upgrading dependencies. Build existing standalone/V2 entries and copy only their existing generated bundle owners; leave uncommitted and unactivated.

### Task 6: Bounded truthful recall and instruction precedence

**Files:** Modify `headroom/proxy/memory_handler.py`, `headroom/memory/backends/local.py` only where its existing hybrid consumer needs repair, `headroom/memory/tools.py`, and exact surviving memory-instruction consumers in `headroom/proxy/handlers/openai.py`; extend `tests/test_memory_injection_budget.py`, `tests/test_memory_auto_tail.py`, `tests/test_memory_tool_mode.py`, `tests/test_memory_handler_project_isolation.py` and `tests/test_memory/test_local_backend_search.py`.

**Interfaces:** Retain `search_and_format_context` and `MemoryInjectionBudget`; add ID/hash/source/scope/currentness fields to the existing tool result projection. Reuse `LocalBackend.hybrid_search(query, user_id, top_k, vector_weight=0.5, text_weight=0.5, min_similarity=0.0)` for native local recall candidates, preserving existing requested entity/related filters and validating active rows at the primary store. Other backend types retain their supported search contract. Existing recall blocks remain read-only background. Memory instructions reference current project/user authority rather than making memory the first source of truth. No new retrieval engine, permission or task state machine.

- [ ] Add tests for active-versus-stale rows after update/index failure, explicit source labels, six-entry/1,200-token cap, full original text retrieval, unavailable-memory fallback and malicious imperative entries that must remain read-only. Budget truncation must not report an omitted row as recalled. Pin an exact Vietnamese/identifier keyword match that weak vector similarity would miss; existing scoped FTS5/hybrid retrieval must return it without a new embedder, duplicate result or lost entity filter.
- [ ] Add byte-equality tests that the preexisting system/history/cache prefix and signed reasoning are unchanged; the only recall addition is bounded live-zone-tail context.
- [ ] Run the five focused files above and confirm new projection/precedence/lexical cases fail. Extend the existing source-protection/Responses regression only for the changed consumer; do not launch every suite.
- [ ] Implement active-row verification at the retained store, provenance labels and the bounded candidate budget. Native requests declaring `x-headroom-memory-tools: client` retain recall but skip proxy-only memory tool/instruction injection; other clients preserve their configured behavior. Replace contradictory memory-first-authority prose in its actual owners, preserving stable session tool/instruction behavior and current configured modes. Do not overwrite original text with a summary or current documents with learned traffic.
- [ ] Rebuild QA overlays and rerun the focused regressions plus the exact affected Responses/protection/accounting tests identified by source references. Record what is synthetic versus actual integration evidence. Leave live settings unchanged.

### Task 7: Repair current instructions and the existing video-project checkpoint

**Files:** Modify existing `/home/huynhdanhlang/.config/opencode/AGENTS.md` only where feedback capture/source precedence needs clarification; modify only the current checkpoint/history organization of `/home/huynhdanhlang/Documents/Projects/ai-motion-video/docs/superpowers/plans/2026-09-21-architecture-a-plan-workspace.md`. Preserve Roadmap/PDR unless a contradictory source repair is actually required.

**Interfaces:** Existing instruction file carries a short feedback rule: update the canonical owner, save scoped recall when available, verify durable success, and fall back once without claiming a save. The Active Plan carries exactly one current Roadmap-aligned next action; superseded checkpoints are explicitly historical.

- [ ] Read fresh affected sections/head and identify actual competing changes. Save dirty preimages, SHA256 and verifiable restore manifest in the private Engine backup area before edits; stop on drift.
- [ ] Reconcile the existing current checkpoint with the current Roadmap and latest source-supported artifact. Preserve system-wide feedback, all16/all7/three journeys, fresh design approval, Rights/consent, evidence limits and runtime safety. Move useful prior evidence under a historical heading within the same Plan; do not invent acceptance or delete unrelated source evidence.
- [ ] Replace, rather than stack, any obsolete instruction sentence. Keep this rule brief; do not add another rule database/inventory/receipt owner or automatically migrate historical approvals into memory.
- [ ] Verify restored preimage hashes and review the narrow diff. Perform a fresh-context read of the current checkpoint + Roadmap + applicable instructions: one current next action, no old approval treated as current, memory unavailable still permits authorized read-only work. Leave unrelated dirty work untouched.

### Task 8: Disposable end-to-end acceptance and exact activation boundary

**Files:** Create `tests/test_memory_feedback_journey.py` using the existing SQLite/index owners and disposable test fixtures; update this Headroom plan with current evidence/limits and `FORK.md` with the actual bounded source change, not a release claim.

**Interfaces:** Consume Tasks 1–6 through the real ASGI command route/native tool-hook boundary. Test sessions have distinct synthetic project roots and never point at live creator projects or production memory stores.

- [ ] Write a failing journey assertion: authored Vietnamese rule saved once → tools visible/executable → new session recalls it → exact guarded correction replaces it → compaction/restarted backend retains only active recall → old hash conflicts → second project sees nothing. Inject one interrupted index write and verify replay recovery.
- [ ] Run `pytests tests/test_memory_feedback_journey.py` and the focused native V2 journey; implement only the missing retained-owner seam revealed by the failure.
- [ ] Prove this path with the installed qualified embedder in isolated state as well as deterministic regression fixtures. If that embedder/model is unavailable, report the blocker; do not download a new model or silently substitute one. Green fake-embedding tests are not semantic-quality acceptance.
- [ ] Run only previously unresolved affected regressions, review the final scoped diff/source references and record exact tested source hashes, QA image identity, candidate bundle hashes and limits. No passing-suite repetition without a new change/failure.
- [ ] Prepare, but do not apply, the exact activation diff: remove the stale root override, activate the tested V2 bundle/API image and retain safe memory bounds. Backups must cover config/DB/previous image. A clean committed release build and service update need separate specific authorization; do not promote the dirty QA image or restart the app.
- [ ] After such authorization, verify actual resumed inference scope, native tools and save → fresh session → guarded update using disposable feedback in an isolated registered project. If live activation is not authorized, hand off verified source/candidate evidence with runtime acceptance explicitly pending.

## Self-review and execution handoff

Spec coverage: Tasks 1/3 implement authored capture and replay; Task 2 history/ownership/CAS; Tasks 4/5 the actual owner-to-harness connection; Task 6 recall, cache safety and precedence; Task 7 existing instruction/checkpoint owners; Task 8 new-session/restart/compaction evidence and rollback. All five Review Focus conditions have named owning tests.

New interfaces are defined before their consumers. No task installs a product model, changes runtime permissions or creates another state owner. A successful source regression does not establish live activation, creator acceptance, model quality or quota savings. Review each independently testable task via its scoped diff; commits remain prohibited absent specific authority.

- [x] Written specification approved by the owner.
- [x] Implementation plan written and self-reviewed against the spec/current source.
- [x] Owner reviews this written plan — “Ok duyệt” on 2026-10-04. Execution is native/main-agent.
- [x] Load `executing-plans`, establish workspace isolation at `/tmp/opencode/headroom-feedback-worktree` (branch `fix/feedback-memory`, BASE520ff809), and execute Task 1 onward in dependency order. Private task evidence/rulings are in that worktree's `.superpowers/sdd/2026-10-04-feedback-memory/progress.md`.
- [ ] Actual memory-path evidence complete; unresolved runtime/activation limits explicitly reported.

## Execution checkpoint — 2026-10-04, source only

Implementation was qualified in `/tmp/opencode/headroom-feedback-worktree` on
`fix/feedback-memory`, BASE`520ff80992362163ee91da3295ff4a52bcd921c0`.
Tasks1–6 and the six Important review fixes have bounded source regression evidence; Task7's instruction/checkpoint
repair is backed up and preserves previous video-project evidence as history.
The two disposable ASGI journeys pass save/replay→fresh recall→guarded update→
fresh backend/compacted query→inactive replay→forget/isolation. Full native plugin
suite:41passed; Python497passed/54external-fixture-skipped; pinned compiler,
runtime-source Ruff0.16.8 and standalone bundle build verified. The final compiled
V2 hook→real HTTP→canonical handler/SQLite path also passes with the qualified
ONNX model copied exactly from the existing cache, offline, including fresh
backend, relevant-only Vietnamese reminder, unchanged signed prefix, guarded
correction/conflict, session move/isolation and forget. QA container removed.
This is actual adapter-boundary evidence with synthetic projects, not installed
OpenCode-host discovery, universal cross-language semantic quality or creator acceptance.

Limits: no new download or model substitution; arbitrary cross-language paraphrases
remain unqualified (weak English-query/Vietnamese-rule similarity was observed).
Three router fixture checks fail identically on untouched baseline
(`test_responses_unit_and_batch_workers_inherit_context[False/True]` and
`test_responses_entry_does_not_inherit_previous_apply_options`). Independent
whole-change review returned six Important findings, all verified RED→GREEN in
one main-agent fix pass. No clean release or live acceptance claimed.
The unexpected pnpm auto-install touched only ignored main-checkout dependencies;
tracked source was preserved, and candidate verification uses isolated npm-ci
from the unchanged lockfile. Do not describe that dependency cache as untouched.

Exact logs, decisions, verified restore manifest, source/bundle hashes and proposed
activation diff are in this Plan's private worktree ledger
`.superpowers/sdd/2026-10-04-feedback-memory/`. Keep that workspace because commits
are prohibited and it is the recovery evidence, not a new product authority.
Owner subsequently explicitly selected **Cho phép** for commit/integration,
clean pinned release build, backup, Headroom update/restart and necessary OpenCode
plugin reload, followed by actual traffic/native-tool verification. No push,
model/Fast change, video-app restart or creator-project write authorized.
Integration/activation is now in progress; no live acceptance claimed until those
checks finish. Preserve the exact prior image/config/state/cache for rollback.
