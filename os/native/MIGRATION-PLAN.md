# Native Canon Migration Plan — 1-file → 127-file decomposition

**Status**: DRAFT v1.1 (codex consult round-4 CHANGES-REQUIRED 2026-05-09 → 4 P1 + 3 P2 fixes applied; pending founder approval)
**Authored**: 2026-05-09
**Author**: claude-drafted via `core:incremental-architect` skill
**Owner**: CEO of Asawa (founder: sankalpasawa)
**Scope**: evolve `sutra/os/engines/NATIVE-ENGINE.md` from monolithic 1888-line canon doc → ~100-line INDEX + 127 per-part files under `sutra/os/native/**`
**Round-4 fixes** (codex session `019e0d0d`): (1) semantic-parity audit added §5; (2) feature-work forbidden during 14d window §3 Phase 13 + §9 MQ5 flipped; (3) decommission gate mechanically enforced §6; (4) R9 reader-resolution risk added §4; (5) Phase 7 sub-waves renumbered 7.1/7.2/7.3; (6) Phase 12 split into 12.1 shadow + 12.2 cutover; (7) cost projection revised w/ semantic-review + cross-link + template-iteration + fleet-validation line items.

---

## 1. Migration goal + constraints

**From-state**: Native canon = one monolithic engine doc (`NATIVE-ENGINE.md`, 1888 lines, RATIFIED v1 2026-05-09) covering §1-§9 runtime contract + §10-§14 strategic/PRD layers. ADRs already separate (`sutra/os/decisions/ADR-004..017`, 14 files). T4 fleet (~10-30 operators) currently reads engine doc as canonical truth via Sutra plugin v1.5.1 distribution.

**To-state**: Native canon = (a) `NATIVE-ENGINE.md` as ~100-line INDEX with cross-links, (b) 127 per-part files under `sutra/os/native/<bucket>/<part-id>.md` across 11 buckets, (c) existing ADRs unchanged (linked, not copied). Each part file has a category-specific industry-anchored template (L8 Feature Spec for blocks, L1 POV for pillars, L9 Tech Spec for events/primitives/surfaces, ADR-style for hardstops, research-log for open-Qs, L13 release-note for doc-layers, L12 roadmap for impl-phases, L11 OKR for N*).

**Why now**: founder direction 2026-05-09 — current monolithic doc cannot be reviewed per-part, cannot be linked-to by other surfaces (Sutra plugin, T4 fleet, codex reviews), cannot evolve per-section without touching the whole file. Decomposition enables (a) Step 4 DESIGN of 7-step product workflow done as artifacts not narrative, (b) per-part codex review per PROTO-019/D40 G2, (c) cleaner contracts for Step 6 BUILD (each block has spec, not "look at engine and guess").

**Constraints**:
- D54 (2026-05-07) currently restricts canon to NATIVE-ENGINE.md + ADRs. **Phase 0 amends D54** to permit `sutra/os/native/**`. Forbidden paths under `holding/**` stay forbidden — D54 anti-scatter intent preserved.
- Codex review per part file per D40 G2 (PROTO-019 gate). Budget: ~127 reviews × ~75s = ~159 min sequential; parallelize via subagents.
- Caveman default in prose (D51); normal in code/governance blocks.
- D52 autonomous push for routine commits on sutra+asawa during migration.
- No content loss: every fact in current engine doc must map to ≥1 part file. Parity audit script enforces.
- T4 fleet must keep reading a working canon throughout — engine doc stays live as INDEX + back-pointer during compat period.

---

## 2. Pattern selection

**Pattern**: **HYBRID — strangler fig + decompose-then-recompose**

| Pattern | Why this fits |
|---|---|
| **Strangler fig** | Engine doc stays live throughout; each bucket extracted into part files; engine sections replaced with link-blocks back to part files. Old path strangled one bucket at a time. |
| **Decompose-then-recompose** | Engine doc is monolithic by birth, not by accident. We decompose into 11 buckets within `sutra/os/native/` (decompose), then recompose via INDEX pointing back (`NATIVE-ENGINE.md` as ~100-line linker). |
| Why hybrid (not single) | Strangler alone leaves no recomposition rule — risk of 127 orphan files. Decompose alone leaves no live-fleet path during migration. Together: strangle each bucket section → recompose via INDEX. |

**Rejected**:
- Branch-by-abstraction — no abstraction layer to insert; readers consume markdown directly.
- Parallel-run — docs have no output to compare; parity must be done by structural audit instead.

**Anti-pattern guard**: each phase has explicit rollback (see Section 3). No phase ends with "fix forward" — every phase can revert to pre-phase state via single `git revert`.

---

## 3. Phase plan

**Smallest reversible step first**. 14 phases (0-13). Phase 0 = setup; Phases 2-11 = per-bucket extraction (sized smallest→largest by count); Phase 12 = engine INDEX rewrite; Phase 13 = decommission window + final-deletion gate.

### Phase 0 — Setup (D54 amendment + skill author)
- **Scope**: append D54 amendment to `holding/FOUNDER-DIRECTIONS.md`; author `native-author-part` skill at `sutra/marketplace/plugin/skills/native-author-part/SKILL.md`.
- **Build-Layer**: SOFT for FOUNDER-DIRECTIONS (LEGACY-HARD path; marker required); L0 for new skill (PLUGIN-RUNTIME).
- **Entry**: founder approval of this plan.
- **Exit**: D54 amendment committed; skill committed + listed in plugin marketplace.
- **Duration**: ~45 min.
- **Rollback**: `git revert` the 2 commits; D54 stays at v1; skill removed.
- **Observability**: D54 grep returns amendment text; skill listed in `claude /plugin list`.

### Phase 1 — Proof-of-concept (5 files, 1 per shape)
- **Scope**: 1 block (B9 closed-loop artifact, L8 template) + 1 pillar (P14 outcomes-drive-design, L1 POV template) + 1 event (`ExecutionStarted`, L9 Tech Spec template) + 1 primitive (Workflow, L9 Tech Spec template) + 1 hardstop (HS-1 audit-log-unwritable, ADR-style template). Each file authored via `native-author-part` skill. Codex consult on the 5-file shape sample.
- **Build-Layer**: L0 (new files under sutra/os/native/).
- **Entry**: Phase 0 complete.
- **Exit**: 5 files exist; codex verdict ≥ ADVISORY; founder approves template shapes.
- **Duration**: ~45 min.
- **Rollback**: delete 5 files; revert commit; engine doc unchanged.
- **Observability**: each file passes shape audit (header + definition + invariants + dependencies + references); back-links resolve.

### Phase 2 — Pillars (14 files)
- Scope: extract §10.2 (14 pillars) into `sutra/os/native/pillars/P1..P14.md`. Each file: L1 POV template — pillar statement + falsification test (from §10.3) + doctrine inheritance (from §10.4).
- Build-Layer: L0.
- Entry: Phase 1 complete + accepted.
- Exit: 14 files present; parity audit script confirms §10.2 + §10.3 + §10.4 content mapped; engine doc §10 replaced with link block.
- Duration: ~1h (14 × ~4 min).
- Rollback: delete 14 files; restore engine §10 from git.
- Observability: parity audit per bucket; cross-link audit (each pillar references its falsification test).

### Phase 3 — Surfaces (6 files)
- Scope: §14.7 (6 surfaces: ROUTE/RUN/GATE/EMERGE/AUDIT/TENANT) into `surfaces/<name>.md`. L9 Tech Spec template per surface — interface + invariants + integration points + emitted events + consumed events.
- Entry: Phase 2 complete.
- Exit: 6 files present; engine §14.7 → link block.
- Duration: ~30 min.
- Rollback: standard (delete + revert engine).
- Observability: each surface file declares its 26-event subset (link integrity).

### Phase 4 — Hardstops (8 files)
- Scope: §6.9 (HS-1..HS-8) into `hardstops/HS-<N>.md`. ADR-style template: status + context (trigger condition) + decision (fail-mode) + consequences (recovery path + downstream effects).
- Entry: Phase 3 complete.
- Exit: 8 files present; engine §6.9 → link block.
- Duration: ~40 min.
- Rollback: standard.

### Phase 5 — Primitives (10 files)
- Scope: §2 typed primitives (Domain/Charter/Workflow/Step/Trigger/ExecutionResult/EngineEvent/Tenant/DecisionProvenance/Approval) into `primitives/<name>.md`. L9 Tech Spec template — type signature + invariants + lifecycle + serialization + cross-primitive references.
- Entry: Phase 4 complete.
- Exit: 10 files present; engine §2 → link block.
- Duration: ~50 min.
- Rollback: standard.

### Phase 6 — Events (26 files)
- Scope: §3.2 EngineEvent type catalog (26 types) into `events/<type-slug>.md`. L9 Tech Spec template per event — schema (CloudEvents-style) + emitter + consumers + ordering invariants + replayability.
- Entry: Phase 5 complete (primitives exist for events to reference).
- Exit: 26 files present; engine §3.2 → link block.
- Duration: ~2h (26 × ~5 min — parallelizable via 4 subagents = ~30 min wall).
- Rollback: standard.

### Phase 7 — Blocks (24 files; sub-waved)

**Inventory recount (codex round-4 P2.1 stabilization)**:
- B-blocks: B1, B2, B3, B4, B5, B6, B7, B8, B9, B10, B11, B12, B13, B14, B15, B16, B17, B18 = **18**
- Sub-blocks: 7a, 7b, 7c, 7d, 7e = **5**
- Special: F1 = **1**
- **Total = 24**.
- PoC already authored in Phase 1: B9 (1 file).
- Top-5 v1 outcome blocks per §14.15.2: B9 (PoC), B7, 7d, B5, B18.

**Sub-wave plan** (renumbered 7.1/7.2/7.3 to avoid name-collision with sub-block labels 7a-7e):
- **Sub-wave 7.1**: top-5 v1 outcome blocks minus PoC = **4 files** (B7, 7d, B5, B18). Highest founder-value; built first.
- **Sub-wave 7.2**: remaining sub-blocks = **4 files** (7a, 7b, 7c, 7e — 7d already in 7.1) + F1 = **5 files total**.
- **Sub-wave 7.3**: remaining B-blocks = **14 files** (B1, B2, B3, B4, B6, B8, B10, B11, B12, B13, B14, B15, B16, B17).
- Arithmetic: 4 + 5 + 14 = 23 files in Phase 7; plus B9 from Phase 1 = **24 total**. ✓

- Scope: L8 Feature Spec template per block — name + 1-line summary + scope-in/out + UX flow + acceptance criteria + data model + edge cases + telemetry + dependencies on primitives/events/surfaces.
- Entry: Phase 6 complete (events available for block dependencies).
- Exit: 24 block files present; engine §14.16 + §16 references → link blocks.
- Duration: ~3h (24 × ~7 min — parallelizable).
- Rollback: per sub-wave (7.1 / 7.2 / 7.3 independently revertable via git revert of sub-wave commit).

### Phase 8 — Open Questions (11 files)
- Scope: §14.10 Q1-Q10 + §12.4 Q11 into `open-questions/Q<N>-<slug>.md`. Research-log template — question + default-if-unanswered + decision-needed-by + sources + ratification log.
- Entry: Phase 7 complete.
- Exit: 11 files present; engine §14.10 + §12.4 → link blocks. **Note**: all 11 Qs already ANSWERED 2026-05-09; files capture the ratified answers.
- Duration: ~30 min.
- Rollback: standard.

### Phase 9 — Doc layers (8 files)
- Scope: founder-owned doc layers (L1/L2/L3/L4/L6/L7/L11/L14) into `doc-layers/L<N>-<slug>.md`. L13 Release Note style — purpose + producer + consumer + cadence + ratification rules.
- Entry: Phase 8 complete.
- Exit: 8 files present; engine §10/§11/§12/§13/§14 section preambles → link blocks (L1=§10, L2=§11, L3=§12, L4=§13, L6=§14; L7/L11/L14 are STUBS pending authoring).
- Duration: ~40 min.
- Rollback: standard.

### Phase 10 — Impl phases (5 files)
- Scope: §14.15.1 Phase A-E into `impl-phases/phase-<A-E>-<slug>.md`. L12 Roadmap template — gate + duration + DRI + acceptance criteria + dependencies on other phases.
- Entry: Phase 9 complete.
- Exit: 5 files present; engine §14.15.1 → link block.
- Duration: ~25 min.
- Rollback: standard.

### Phase 11 — N* metric (1 file)
- Scope: §11.2 OHS/wk N* into `metrics/north-star-ohs-per-week.md`. L11 OKR template — definition + target + measurement + leading inputs + winning picture.
- Entry: Phase 10 complete.
- Exit: 1 file present; engine §11.2 → link block.
- Duration: ~10 min.
- Rollback: standard.

### Phase 12 — Engine doc → INDEX (split into 12.1 shadow + 12.2 cutover per codex round-4 P2.3)

#### Phase 12.1 — Shadow INDEX validation
- Scope: author SHADOW INDEX at `sutra/os/native/INDEX-shadow.md`. Same content as planned final INDEX (link table + reading order + governance rules) but at a separate path. NATIVE-ENGINE.md untouched.
- Validation:
  - Link-integrity check: every link in shadow INDEX resolves to an existing part file.
  - Bucket completeness check: 11 buckets present with expected file counts.
  - Reader-resolution test (R9 mitigation): 5 T4 fleet operators sample-read shadow INDEX; zero resolution failures gate cutover.
  - Semantic-parity sample: 3 random files per bucket reviewed against original engine doc section for content equivalence.
- Entry: Phases 0-11 complete (all 127 part files exist).
- Exit: shadow validates; reader test PASSES; semantic-parity sample PASSES.
- Duration: ~30 min author + ~1h reader test wall (async fleet).
- Rollback: delete shadow file; engine doc unchanged.

#### Phase 12.2 — Cutover (engine → INDEX)
- Scope: replace NATIVE-ENGINE.md content with shadow INDEX content. Move shadow to historical-archive `holding/research/_archive/native-v1.x/INDEX-shadow-pre-cutover.md` (per D54 historical-archive rule). Bump Sutra plugin version (mandates marketplace re-cache).
- Entry: Phase 12.1 PASS.
- Exit: NATIVE-ENGINE.md = ~100 lines; plugin version bumped; release notes published.
- Duration: ~15 min.
- Rollback: restore engine doc from git tag `pre-migration-v1` set at Phase 0; revert plugin version.

### Phase 13 — Decommission gate (14d observation + final-deletion)
- Scope: 14-day observation window. Founder + T4 fleet read new canon shape. Bug reports / drift signals collected. **NEW FEATURE WORK ON CANON FORBIDDEN during the 14d window** (codex round-4 P1.2 fix — preserves "single git revert per phase" rollback honesty; pre-existing in-flight non-canon work continues; canon edits queue for post-window). Then: final-deletion phase removes any duplicated content from engine doc that was kept temporarily for safety. Engine doc = pure INDEX permanently.
- **Critical-bug threshold** (codex round-4 P1.3 fix): 0 P1 bugs filed against decomp AND 0 T4 fleet critical-reader-failure reports during 14d. Any P1 → window restarts from day 0.
- Entry: Phase 12.2 complete.
- Exit: 14d clean; parity-audit final-PASS at `.enforcement/native-migration-audit.log` (final entry `verdict=PASS`); founder commits with header `DECOMMISSION-APPROVED: YYYY-MM-DD` (immutable approval record); tag `migration-v1-decommissioned` set.
- Duration: 14 calendar days + ~30 min finalization.
- Rollback: in the 14d window, founder can flag → revert to pre-Phase-12 state (full engine doc restored from git tag `pre-migration-v1`). After 14d + final-deletion, rollback requires re-recovery from git history (longer path).
- Observability: weekly parity-audit re-run during window; T4 fleet feedback channel monitored; CI hook `holding/hooks/native-migration-decommission-gate.sh` blocks final-deletion commit unless audit-PASS + window-elapsed + approval-header match.

---

## 4. Risk register

| # | Risk | Affects phase | Likelihood | Impact | Mitigation |
|---|---|---|---|---|---|
| R1 | Dual-source-of-truth — content lives in both engine doc + new file during migration; an edit lands in one but not other; readers see inconsistent canon | 2-11 | HIGH | HIGH | Per-bucket atomic move: extract bucket → write part files → replace engine section with link block in SAME commit. No bucket spans two commits. |
| R2 | T4 fleet sees partial state via plugin update mid-migration | 2-11 | MEDIUM | MEDIUM | Each per-bucket commit ships engine link-block + part files atomically. Plugin readers always see consistent shape. Coordinate plugin release tags with phase completion. |
| R3 | Link rot — a part file is renamed mid-migration; INDEX + cross-references become stale | 12 | MEDIUM | MEDIUM | Lock file naming convention in Phase 0 (slug = lowercase-kebab from canonical id; never rename post-creation). Link-integrity script run pre-commit per bucket. |
| R4 | Codex review queue overflow — 127 sequential reviews × ~75s = ~159 min wall (>15-min skill hard cap if not parallelized) | 1-11 | HIGH | MEDIUM | Parallelize via subagents (4-8 parallel codex consults via `gsd-execute-phase` style dispatch). Per-bucket batch review, not per-file. Cap each batch at <5 min per `[Chunk LLM work]`. |
| R5 | Drift between part file content + still-canon engine doc content during compat period | 2-11 | HIGH | HIGH | **R5 = R1 expanded**. Mitigation: parity-audit script runs per phase; engine doc bucket-section MUST be link-block-only after its phase (no residual content); CI hook flags engine doc edits in already-migrated buckets. |
| R6 | Hidden cross-references inside engine doc — §14.13 Foundation Index, §14.14 process, §14.15 kickoff frame cross-link multiple sections; decomp breaks these | 7-11 | MEDIUM | MEDIUM | Cross-reference audit before each phase: grep engine doc for "§N" references to the bucket being migrated; convert each to part-file link in same commit. |
| R7 | Schema evolution — 11 templates may need amendments mid-migration (a template proves wrong after a bucket is half-done) | 2-11 | LOW | HIGH | Phase 1 PoC validates template shapes BEFORE bulk authoring. If amendment needed post-Phase-1: pause migration, amend template, re-author files in already-completed buckets via skill. |
| R8 | Founder review fatigue — 127 codex verdicts × spot-review = high cognitive load | 1-11 | MEDIUM | LOW | Per-bucket batch review (founder sees verdict summary per bucket, not per file). Sample-review: founder spot-checks 1-2 files per bucket; codex full-review for the rest. |
| R9 | **Reader-resolution failure** (codex round-4 P1.4) — Sutra plugin / T4 fleet readers may fail to follow new path topology: hardcoded `engines/NATIVE-ENGINE.md` paths in skills/hooks, plugin marketplace cache lag, partial checkout, packaging-bundle skew, canonical-path differences across OS. | All | HIGH | HIGH | (a) Pre-Phase-0 audit: `grep -rE 'engines/NATIVE-ENGINE\.md\|os/engines/native' sutra/ holding/ .claude/` — fix every hardcoded reference. (b) Phase 12.1 shadow-INDEX validation tests 5 T4 fleet operators on new path resolution BEFORE Phase 12.2 cutover. (c) Plugin version bump at Phase 12.2 explicitly requires marketplace re-cache. (d) Migration tag `pre-migration-v1` restores monolith if reader failure surfaces in observation window. |

---

## 5. Parallel-run period + observability

**Duration**: Phases 2-11 = compat period (engine doc + part files BOTH exist). Phase 12 = transition (engine doc shrinks to INDEX). Phase 13 = 14d observation window after transition.

**Observability — required metrics** (codex round-4 P1.1 fix: structural checks alone do NOT prove "no content loss"; semantic parity must be checked too):

1. **Structural parity audit per phase**: shell script `holding/scripts/native-parity-audit-structural.sh` (to author in Phase 0):
   - For each canonical anchor in engine doc (P1-P14, B1-B18, HS-1..HS-8, etc.), assert ≥1 part file exists OR the anchor is in an unmigrated bucket.
   - For each part file, assert REFERENCES section contains ≥1 back-link to engine doc OR to another part file (no orphans).
2. **Semantic parity audit per bucket** (NEW per codex round-4 P1.1 — was missing in v1):
   - Before each per-bucket extraction commit: capture SHA256 of the canon-anchor section in engine doc (e.g., §10.2 pillar table). Store at `.enforcement/native-migration-source-checksums.jsonl` as `{anchor, sha256, ts, source_lines}`.
   - Each part file's header includes `parity-source: <anchor>` + `parity-source-sha256: <hash>` (matches the captured value).
   - **Semantic-equivalence check**: claude-or-codex reads original anchor section + reads new part file, returns PASS|WEAK|MISS verdict per content claim. Verdict written to `.enforcement/native-migration-semantic-audit.jsonl`. Per-bucket exit requires zero MISS + ≤2 WEAK per bucket; WEAK requires founder-readable summary noting what wording changed.
   - **Sample-review (sanity)**: 3 random files per bucket get full side-by-side review by founder during sample window (auto-selected via `shuf | head -3`).
3. **Cross-link integrity check**: every link in NATIVE-ENGINE.md INDEX (post-Phase-12) resolves to an existing file; every cross-bucket reference in part files resolves; no dangling `§N.M` ghost-anchors.
4. **Bucket completeness check**: each bucket has the expected file count (e.g., blocks/ has exactly 24 files matching B1-B18 + 7a-7e + F1; pillars/ has exactly 14 matching P1-P14).
5. **T4 fleet read-success**: weekly during 14d window, sample 3 T4 operators (per `holding/departments/analytics/fleet.sh`) and ask "did Native canon read correctly?". Baseline: zero failures.
6. **Reader-resolution audit** (R9 mitigation, codex round-4 P1.4): pre-Phase-0 grep for hardcoded `engines/NATIVE-ENGINE.md` references across `sutra/`, `holding/`, `.claude/`; fix all before migration starts; re-run grep at end of Phase 12.2 to confirm no skill/hook still hardcodes the old monolithic path.
7. **Codex review verdict roll-up**: `.enforcement/codex-reviews/gate-log.jsonl` filtered by `topic=native-decomp` — count PASS / ADVISORY / CHANGES-REQUIRED per bucket. ADVISORY-or-better gates phase exit.

---

## 6. Decommission gate (mechanically enforced — codex round-4 P1.3 fix)

```
+--- DECOMMISSION GATE (operational; CI-enforced) ---------+
| Named approver  : founder (sankalpasawa) only             |
| Evidence        : .enforcement/native-migration-audit.log |
|                   last entry verdict=PASS                 |
|                   .enforcement/native-migration-semantic- |
|                   audit.jsonl rolls up zero MISS          |
| Critical-bug    : 0 P1 bugs filed in 14d window           |
|   threshold       0 T4 fleet critical-reader-failures     |
|                   (any P1 → window restarts day 0)        |
| Observation     : 14 calendar days post-Phase-12.2 commit |
| Approval record : git commit on `main` w/ commit message  |
|                   header `DECOMMISSION-APPROVED:          |
|                   YYYY-MM-DD` from founder identity       |
|                   (sankalpasawa GPG-signed if available)  |
| Final-deletion  : Phase 13 final-deletion commit BLOCKED  |
|                   by CI hook holding/hooks/               |
|                   native-migration-decommission-gate.sh   |
|                   unless ALL above conditions PASS        |
| Tag             : migration-v1-decommissioned set ONLY    |
|                   after final-deletion lands              |
| Feature-work    : FORBIDDEN during 14d window (preserves  |
|   pause           single-git-revert rollback honesty)     |
+----------------------------------------------------------+
```

**Hook contract** (`holding/hooks/native-migration-decommission-gate.sh`, to author in Phase 0):
- Fires PreToolUse on Bash matching `git commit` AND staged files include NATIVE-ENGINE.md OR sutra/os/native/INDEX.md final-deletion shape.
- Checks 5 conditions: (1) audit-log last entry PASS, (2) semantic-audit zero MISS, (3) elapsed wall ≥ 14*86400 since Phase 12.2 commit, (4) commit message header `DECOMMISSION-APPROVED:` present, (5) `git config user.name` returns founder identity.
- Exit 0 if all pass; exit 2 with structured reason if any fails. Override `DECOMMISSION_ACK=1 reason="<why>"` logged immutably to `.enforcement/native-migration-decommission-overrides.log`.

Without all conditions satisfied, Phase 13 cannot complete. Migration stays in compat period indefinitely (acceptable failure mode — engine doc still works as canonical entry-point).

---

## 7. Cost projection

| Phase | Engineer-hours | Calendar | Codex tokens (est) | Founder review time |
|---|---:|---|---:|---:|
| 0 Setup | 0.75 | <1 day | ~5k | ~10 min |
| 1 PoC | 0.75 | <1 day | ~10k | ~15 min |
| 2 Pillars (14) | 1.0 | <1 day | ~28k | ~5 min batch |
| 3 Surfaces (6) | 0.5 | <1 day | ~12k | ~5 min batch |
| 4 Hardstops (8) | 0.7 | <1 day | ~16k | ~5 min batch |
| 5 Primitives (10) | 0.85 | <1 day | ~20k | ~5 min batch |
| 6 Events (26) | 2.0 (parallel: ~30min wall) | <1 day | ~52k | ~10 min batch |
| 7 Blocks (24) | 3.0 (parallel: ~45min wall) | 1-2 days | ~50k | ~15 min batch |
| 8 Open Qs (11) | 0.5 | <1 day | ~22k | ~5 min batch |
| 9 Doc layers (8) | 0.7 | <1 day | ~16k | ~5 min batch |
| 10 Impl phases (5) | 0.4 | <1 day | ~10k | ~5 min batch |
| 11 N* metric (1) | 0.2 | <1 day | ~2k | ~2 min |
| 12.1 Shadow INDEX | 0.5 + 1h reader test (async) | <1 day | ~3k | ~10 min |
| 12.2 Cutover | 0.25 | <1 day | ~2k | ~5 min |
| 13 Decommission | 0.5 (post-window) | **14 calendar days** | ~3k | ~10 min |
| **Subtotal (per-phase)** | **~12.85h focused** (parallel: ~8h wall) | | **~251k tokens** | **~115 min** |
| | | | | |
| **+ Codex round-4 buffer line items** (P2.4 fix) | | | | |
| Semantic-parity review per bucket | +2.0h | overlaps phases | +80k | +20 min review |
| Cross-link cleanup per bucket commit | +1.5h | overlaps phases | +0k (no codex) | +5 min |
| Template iteration (1-2 templates likely amend after PoC) | +1.0h | <1 day | +15k | +10 min |
| Live-fleet validation (R9 mitigation, Phase 12.1) | +1.0h (reader test wall) | overlaps Phase 12.1 | +0k (no codex) | +10 min |
| | | | | |
| **Revised total** | **~18.35h focused** (parallel: ~11.5h wall) | **~14 days + ~11.5h** | **~346k tokens (~$2-$4 codex)** | **~160 min** |

**Anchor check**: founder anchor was 8-11h; revised to ~11.5h wall (parallel) + ~18.35h sequential. Wall estimate still within anchor. Sequential exceeds anchor by ~50% — flagging honestly per codex round-4 P2.4. Decommission window adds 14 calendar days but no continuous engineering time.

---

## 8. Communication plan

| Audience | What they need to know | When | How |
|---|---|---|---|
| Founder | Phase 0 prereq (D54 amend OK); per-bucket verdicts; decommission gate decision | Per phase | In-session table + AskUserQuestion |
| T4 fleet operators | Native canon shape changing; readers should look at NATIVE-ENGINE.md INDEX or new `sutra/os/native/` files; nothing breaks for runtime | Pre-Phase-2 (heads-up via plugin release notes) + Post-Phase-12 (announcement) | Plugin release note + `holding/website/native/` page |
| Codex (review queue) | Migration context — review each batch as "Native canon decomp Phase N bucket X" | Per batch | Prompt prefix in `core:codex-sutra` consult mode |
| Sutra plugin marketplace | New skill `native-author-part` available; engine doc shape changing | Phase 0 (skill ship) + Phase 12 (engine shape) | Plugin version bumps + marketplace.json description |
| Future readers (claude/codex sessions, T4 fleet operators) | New canon shape, where to read what | Phase 12 onward | NATIVE-ENGINE.md INDEX header + this MIGRATION-PLAN.md retained as historical record |

---

## 9. Open questions + noted limitations

**Open questions** (for founder to decide before Phase 0 starts):

| # | Question | Default if unanswered |
|---|---|---|
| MQ1 | Codex review per-file OR per-bucket-batch? | per-bucket-batch (cheaper, faster; founder can spot-check per-file) |
| MQ2 | Subagent parallelism level — 4 or 8 concurrent? | 4 (safer; codex queue tolerance unknown for higher) |
| MQ3 | When part file mentions another part (cross-bucket link), use relative path or absolute `sutra/os/native/` path? | relative path (portable across worktrees) |
| MQ4 | Engine doc post-Phase-12 — strict INDEX (links only) OR INDEX + brief executive summary (1 para per bucket)? | INDEX + brief summary per bucket (~5 lines each = readable as standalone) |
| MQ5 | Should the 14d decommission window run in parallel with new feature work (Phase B Feature Specs continuing) OR pause feature work? | **FLIPPED per codex round-4 P1.2 fix**: PAUSE canon feature work during 14d window (preserves single-git-revert rollback honesty; non-canon work continues). Original default was parallel; codex flagged this breaks rollback contract. |

**Noted limitations**:

1. **Templates are v1 (DRAFT)** — Phase 1 PoC may reveal a template needs amendment. If so, pause migration, amend template, re-render any already-authored files via skill (re-run `native-author-part` with updated template).
2. **127 is a derivation, not a hard count** — if additional Native concepts are found mid-migration (e.g., a §3.3 sub-table not initially counted), they get appended to the appropriate bucket. Plan grows; doesn't break.
3. **D54 amendment is itself a major direction change** — must be reviewed by founder + codex consult before Phase 0 starts. This plan assumes D54 amendment is approved.
4. **Codex token budget (~251k) assumes ~2k tokens per part-file review** — if codex tends to verbose verdicts on complex specs (e.g., block L8 specs with edge-cases), budget could grow 2-3×. Mitigation: hard-cap codex `model_reasoning_effort=medium` for routine extractions; reserve `high` for ambiguous parts.
5. **Migration plan itself (this file) is a precedent for `sutra/os/native/` content** — keeping it after Phase 13 serves as historical-decomp-record. If founder wants to retire it after migration, archive to `holding/research/_archive/native-v1.x/INDEX.md` per D54 historical-archive rule.

---

## Appendix A — Phase dependency graph

```
Phase 0 (setup)
  |
  v
Phase 1 (PoC 5 files)  <-- founder gate on template shapes
  |
  v
Phase 2 (pillars 14)
  |
  v
Phase 3 (surfaces 6)
  |
  v
Phase 4 (hardstops 8)
  |
  v
Phase 5 (primitives 10)  <-- events depend on primitive types
  |
  v
Phase 6 (events 26)  <-- blocks depend on events for emission/consumption
  |
  v
Phase 7 (blocks 24)  <-- sub-waved 7a/7b/7c
  |
  v
Phase 8 (open-Qs 11)
  |
  v
Phase 9 (doc-layers 8)
  |
  v
Phase 10 (impl-phases 5)
  |
  v
Phase 11 (N* 1)
  |
  v
Phase 12 (engine -> INDEX rewrite)  <-- requires all 127 files exist
  |
  v
Phase 13 (14d observation + decommission gate)
  |
  v
[migration complete]
```

## Appendix B — Build-Layer per phase

| Phase | Path touched | Build-Layer | Marker required |
|---|---|---|---|
| 0 | holding/FOUNDER-DIRECTIONS.md | LEGACY-HARD | yes (D38) |
| 0 | sutra/marketplace/plugin/skills/native-author-part/ | PLUGIN-RUNTIME (L0) | yes (D38) |
| 1-11 | sutra/os/native/** | SOFT (advisory) | no |
| 12 | sutra/os/engines/NATIVE-ENGINE.md | SOFT | no |
| 13 | sutra/os/engines/NATIVE-ENGINE.md (final-deletion) | SOFT | no |

## Appendix C — Rollback tags

| Tag | Set at | Purpose |
|---|---|---|
| `pre-migration-v1` | Before Phase 0 | Full rollback to monolith canon |
| `post-phase-N-bucket-X` | After each per-bucket phase | Granular rollback to last good per-bucket state |
| `pre-engine-rewrite` | Before Phase 12 | Rollback to "all 127 files exist + engine doc still has content" state |
| `migration-v1-decommissioned` | After Phase 13 final-deletion | Migration complete; record point |

---

**End of MIGRATION-PLAN.md DRAFT v1.** Pending: (a) codex consult round-1 verdict, (b) founder approval, (c) MQ1-MQ5 answers, (d) Phase 0 execution.
