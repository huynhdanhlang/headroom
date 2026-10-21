# Native TLS security update implementation plan
> **For agentic workers:** Use superpowers:executing-plans inline; review the whole branch once.
**Goal:** Integrate upstream 4c7acba5, patch audited dependencies, rebuild native base and install a verified image without changing optimization settings.
**Architecture:** Cargo/uv locks own dependency resolution; the existing Dockerfile builds native artifacts. The maintenance build guard verifies the rebuilt local base's exact image ID before applying revision-stamped overlays.
**Tech Stack:** Rust 1.95.0, Python 3.13, uv 0.11.18, Docker, pytest, cargo-audit.
**Spec:** User approval on 2026-10-22 and FORK.md; external diagnostic receipt checkpoint.json records the starting evidence.

## Global constraints
- Preserve frozen prefixes/read protection, scoped memory/exact retrieval, raw billing, shared deadlines, terminal cleanup and H2-to-H1 cooldown/no replay.
- No model/context/cache/memory/worker/global Codex setting changes.
- rustls-webpki >=0.103.16,<0.104; webpki-roots 1.x >=1.0.10. Keep 0.26.11 compatibility wrapper only if its parent is fixed.
- certifi >=2026.10.19; Pillow >=13.0.0 in resolved optional dependency locks.
- No third-party publication or new permanent registry; local rebuilt base is explicitly checked by immutable image ID.
- Release builds from clean commits, isolated tests/state/ports, stopped-service state backup and verified old image before live cutover.

## Review focus
- Terminal delivered versus withheld by memory filter: existing and new terminal-close regressions.
- Prefix tracker restoration versus source-read protection: restart/read-protection suites and actual restart receipts.
- Dependency wrapper re-export semantics: lock-contract tests plus cargo-audit.
- Local base tag accidentally retargeted: guard rejects unexpected image ID.
- Candidate/liveness health versus real model completion: actual Codex Responses terminal probe, memory and exact-retrieval smoke.

### Task 1: Security dependency lock contract
Files: tests/test_security_dependency_contract.py; Cargo.lock; pyproject.toml; uv.lock.
Interfaces: produces a clean security source commit and auditable fixed lockfiles consumed by the native build.
- [ ] Write tests checking all selected Cargo versions and resolved Python lock versions meet the fixed floors.
- [ ] Run tests against existing locks; expect assertion failures naming the vulnerable versions.
- [ ] Run precise Cargo updates for rustls-webpki and webpki-roots 1.x; add Python constraints and update only certifi/Pillow with uv.
- [ ] Run contract tests and cargo-audit; expect zero relevant findings. Run source router/Responses/protection/accounting/restart suites.
- [ ] Commit merged upstream and dependency fixes after tests pass.

### Task 2: Rebuilt native base, immutable guard and qualification
Files: tests/test_ai_motion_build_guard.py; scripts/build_ai_motion.py; docker/Dockerfile.ai-motion; FORK.md.
Interfaces: consumes Task 1 clean commit; produces a base image built by Dockerfile --target runtime, plus a revision-stamped qualified release image.
- [ ] Add guard regression: exact local image ID passes and a mismatched ID raises before build. Watch it fail first.
- [ ] Implement verified local base support without weakening runtime coverage/native-change checks; pin native source commit and image ID.
- [ ] Build native base with existing Dockerfile; preserve native source/lock hashes and image receipt. No runtime dependency deletion or additive substitution.
- [ ] Commit release pins; run check-only from clean commit; build release overlay.
- [ ] Audit installed distributions, run installed relevant suites and attempt full pytest collection/run with named optional-environment failures reported rather than hidden.
- [ ] Review complete branch read-only; fix blockers with RED/GREEN proof.
- [ ] Candidate actual Codex/SSE/memory/exact retrieval/offline ONNX and restart-prefix behavior must pass.
- [ ] Fast-forward/push main; install with stopped-state backup and rollback; verify hashes/settings and resumed real traffic.
- [ ] Remove only this task's test containers/state and obsolete third rollback, retaining two verified prior backups/images.
