# Feedback memory that survives sessions without changing authority

## Intent and approval boundary

The owner requests better memory for Headroom, OpenCode and AI Motion Video: remember Vietnamese/English feedback, replace outdated rules, avoid repeating mistakes and remind the owner only when a real decision is missing. On 2026-10-04 the owner approved the combined approach: authoritative current project instructions plus scoped persistent recall and a pre-action check.

This is the written architectural design for review, not an approved implementation plan or a production-update authorization. No commit, model/provider change, service restart, live creator-project write or product-stage advancement follows from this document. AI Motion Video retains its existing PDR, Roadmap and Active Plan as its only delivery authorities; this specification governs the Headroom integration, not the video product.

## Verified starting point

Read-only investigation against source HEAD `520ff80992362163ee91da3295ff4a52bcd921c0`:

- `TrafficLearner._find_correction` reproduced `Don't use fake data.` → `use fake data` and `Never modify production data.` → `modify production data`. The capture loses the prohibition. Equivalent Vietnamese prohibitions returned no capture. This probe executed the actual AST-selected detector methods, not a replacement implementation.
- The current detector examines at most the first 500 characters, captures one correction, uses English-only trigger sequences and normally waits for repeated evidence before persistence. It is not a reliable complete feedback recorder.
- OpenCode's native V2 adapter routes through `routeHeadroomRequest`, which sets `x-headroom-project` for attribution. `ProjectResolver.resolve` instead consumes `x-headroom-project-id` or `x-headroom-cwd` for memory partitioning. The attribution header does not select a memory partition.
- The running proxy command has `--memory-storage project --memory-project-root /home/huynhdanhlang/AI-Motion-Video/app --memory-top-k 3`. The old root takes precedence over system-prompt cwd when a canonical scope header is absent. The actual source location is `/home/huynhdanhlang/Documents/Projects/ai-motion-video`.
- The mounted global `state/memory.db` and sole project database `state/memories/projects/app-08de8b34eba962de/memory.db` each contain zero memory rows. This is a bounded observation of those stores, not proof that no memory exists anywhere else.
- OpenCode registers the compression MCP at `http://127.0.0.1:4445/mcp`, not a memory tool adapter. `memory_search` failed as unavailable in this session; Code Mode discovery also found no memory tools.
- `MemoryHandler` already provides scoped save/search/list/update/delete dispatch and bounded context injection. `LocalBackend`, hierarchical memory, SQLite history/supersession and indexes are the retained storage owners. The separate memory stdio MCP currently exposes search/save only; it must not create a different DB for this integration.
- AI Motion Video's Active Plan top mixes current checkpoint material with many superseded checkpoints and next actions. Its Roadmap remains the sole next-action authority. History is evidence, not a new current instruction.

The unavailable local `rtk` executable is a tooling limitation; no installation is required for this work. Native tools and exact, scoped shell probes are the fallback.

## Architecture: keep the owners, repair the seams

### 1. Current rules and recalled facts are different

- Explicit project instructions and current user steering determine permissions and required behavior. Retrieved memory never grants execution, Rights, release or live-data authority.
- Durable memory stores preferences, corrections and verified lessons with provenance. An AI deduction is an advisory candidate, not an owner-approved rule.
- Each saved correction preserves the original authored wording and negation. A concise interpretation may accompany it but never replaces the source text.
- Use the existing memory metadata for kind, source, scope, evidence identity, source reference/hash and optional rule key. Extend existing owners where necessary; do not add a second store, registry, generated rule inventory or autonomous task queue.
- Product feedback is written into the appropriate existing project owner. A memory entry is a retrieval aid linking to that owner, not a duplicate authority. Generalize a rule's scope only when the owner states that scope; do not generalize an example's data or consent.

### 2. One canonical project identity through every entry point

- Retain `x-headroom-project` for existing attribution consumers. Add the canonical memory scope signal to the native V2 routing adapter rather than interpreting the attribution label as a filesystem path.
- For ordinary sessions, derive `x-headroom-cwd` from the actual session's current directory, correctly percent-encoded. Never use one plugin instance's loading directory for every session it can observe. Intentional project-ID overrides use `x-headroom-project-id` consistently across inference and memory operations.
- Memory tools derive scope from the trusted session context. Model arguments cannot select another user's identity, another project's DB or a storage mode.
- Missing project identity fails closed with an explicit unavailable result; it must not fall back to the obsolete root or a global pool. Remove the stale live root override only through an authorized, backed-up configuration update.
- Preserve existing partition keys and data. Any legacy-to-current migration requires an exact verified mapping and a reversible backup; do not merge project stores by fuzzy name or wipe an empty-looking store.

### 3. Real memory tools visible to OpenCode

- Register native V2 memory tools so the harness and Code Mode both know their executable schemas. Do not rely on definitions inserted only into upstream model traffic.
- Add a thin, allowlisted local command adapter at `POST /v1/memory/tools` on the existing Headroom proxy. It delegates to `MemoryHandler` and its resolved backend; it does not start another memory service or open a second unrelated store.
- Initial operations are search, chronological list, explicit save and guarded update. Forget/delete is available only after the same identity, scope and ownership checks are implemented. Existing compression tools remain unchanged.
- Reuse the existing local-access/origin security boundary. Validate payload type, operation allowlist, sizes, limits and scope before initialization or execution. Return structured missing/unavailable/denied/conflict/error results without credentials, raw transport internals or saved content in general logs.
- Updates resolve the exact memory ID in the caller's scope, verify ownership and expected content/version, then use the existing immutable history/supersession owner. No delete-then-save fallback or semantic-search-by-ID as identity proof. Unsupported backends return an explicit unsupported result instead of silently weakening this contract.
- Saves return the durable ID and scope only after persistence. Replayed save requests with the same scoped evidence identity are idempotent. Do not claim an asynchronous save succeeded merely because it was queued.

### 4. Feedback learning without learning the wrong thing

- Repair the retained detector to preserve prohibitions, support explicit Vietnamese/English corrections and process bounded complete clauses rather than silently discarding everything after character 500.
- Explicit durable intent such as “remember this rule” can be persisted on its first occurrence with authored provenance. Ordinary task commands, copied examples, tool output, harness reminders and retrieved memory are not automatically promoted into rules.
- Repeated-evidence thresholds remain appropriate for inferred environment/recovery lessons. Re-sending the same user turn on every model request does not count as new independent evidence. A successful unrelated command is not proof of recovery.
- Preserve all meaning-bearing clauses in a supported correction. When extraction cannot confidently establish the boundary, retain the source as an advisory candidate instead of truncating it into a misleading rule.
- Do not auto-rewrite AGENTS or product decisions from inferred traffic. Owner-explicit instruction repairs stay in their existing file owners; learned advisory entries stay in memory. Native-file writing, if retained for other users, remains explicit and configurable.
- Rule replacement requires an explicit rule key/old memory ID or a verified source-owner revision. Similarity alone never establishes contradiction, identity or supersession. History remains available; superseded entries are excluded from active retrieval.

### 5. Recall and pre-action checks

- Keep critical instructions in their existing instruction owners, already loaded by the harness. Do not depend on cosine similarity to retrieve permissions or mandatory rules.
- Retrieve a small set of task-relevant, active memories with source/version labels. Keep injection in the existing live-zone tail and preserve cached system/history bytes and source-read protection. Start with a bounded six-entry/1,200-token candidate budget, then retain it only if focused evidence supports it.
- Before a consequential edit, reconcile the current objective, applicable source rule, relevant feedback, actual current artifact and permitted action. This is a brief internal check, not another planning ritual or status turn.
- If a source owner changed, its current text wins over a stale memory summary. Recovery reads the exact owner; it does not invent an approval or replay a recalled task.
- If memory is unavailable, say so once and continue from current repository authorities where permitted. Do not claim “saved” or repeatedly ask an already answered question.
- Remind the owner only about an actual unresolved conflict, missing fact, required approval or explicitly requested reminder. No background scheduler, notifications or external messages are introduced.

### 6. Compact the existing project checkpoint

- Back up the dirty AI Motion Video Active Plan preimage and verified restore manifest before changing it. Preserve concurrent user/agent edits and stop on drift.
- Keep one concise current checkpoint: outcome, selected artifact/current heads, current system-wide feedback, verified evidence/limits, blocker and one Roadmap-aligned next action.
- Separate genuinely useful prior evidence inside the same existing Plan with an explicit historical heading. Remove duplicate superseded status prose, not source evidence or authority. Do not create another spec, roadmap, checklist or receipt owner in AI Motion Video.
- Preserve the existing product stage, fresh-design approval gate, all16/all7/three-journey outcome, Rights/consent and runtime boundaries. This memory repair grants no UI implementation or product acceptance.

## Error handling and observability

Record scope-resolution result, operation, durable ID, source hash, dedup outcome and reason for skipped injection using bounded structured diagnostics. Do not log secrets or full private feedback. Lookup timeout does not corrupt history or bypass Headroom. Write failure reports unsaved; version conflict preserves both existing memory and the new correction input. Restart/retry must not duplicate a correction or resurrect a superseded rule.

## Decisive acceptance

The implementation is accepted only when the actual path works, not merely when storage tables or tool schemas exist:

1. Vietnamese and English positive/negative feedback retains its original meaning, including multiple clauses and a correction beyond character 500. Quoted examples, reminders and ordinary one-time requests do not become mandatory rules.
2. An explicit correction saves once, returns its ID and survives a new session, compaction and backend restart in isolated test state. Replaying the same authored evidence does not duplicate it or inflate confidence.
3. Two projects, two session directories and a session move resolve consistently across inference, save, search and update. Missing scope fails closed; another user's/project's ID cannot be read or changed.
4. A changed rule replaces its exact predecessor with recoverable history. A stale expected version returns conflict. Similar-sounding independent rules remain independent; old or unverified summaries do not override current source instructions.
5. Native OpenCode tool discovery exposes real executable memory tools. The actual save → new session → search → guarded update → reread path succeeds through the registered adapter, using disposable synthetic feedback rather than creator-project mutations.
6. Relevant recall remains bounded and does not alter cached prefixes, signed reasoning, source reads, existing compression retrieval or accounting. Run focused memory, V2 routing, Responses and protection regressions selected by changed risk; no synthetic result is claimed as quota savings or model quality.
7. The existing AI Motion Video checkpoint identifies one current next action and preserves product authority. A fresh-context read finds the current system-wide correction without treating old approvals or next actions as live.

## Delivery order and rollback

First repair the proven extraction/identity defects with failing regressions. Then expose the guarded existing memory owner to OpenCode, prove the disposable end-to-end path and reconcile the existing project checkpoint. Only then consider live activation.

Source changes are reversible and remain uncommitted unless specifically authorized. A live update needs explicit authorization for the exact Headroom configuration/image/plugin change, a coherent DB/config backup, prior image digest, rollback instructions and actual resumed-traffic evidence. Do not build a release image from a dirty source commit. Do not restart the video app, install a new embedding/model dependency, switch provider or weaken the cache/source safeguards as a shortcut.

## Design review state

- [x] Understand the approved combined approach and existing owners.
- [x] Reproduce the concrete detector defect and inspect actual deployed scope/tool configuration.
- [x] Write and self-review this design for scope, authority, failure handling and real acceptance.
- [x] Owner reviews this written design — approved by “Ok go build” on 2026-10-04.
- [ ] Create and review the detailed implementation plan, then choose execution method.
- [ ] Implement, verify the complete memory path and obtain separate live-update authority if needed.

Self-review: no placeholders; source repair, source authority and live activation are distinct. Memory does not become a task/permission source. Existing data/owners and all unrelated work are preserved. Deployment and fresh-session evidence are not claimed as already achieved.
