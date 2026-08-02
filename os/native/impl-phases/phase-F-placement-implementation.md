---
part-id: phase-F
bucket: impl-phases
template: L12-roadmap-entry
parity-source: net-new (ADR-028); post-cutover canon
status: ACTIVE
authored: 2026-07-27
---

# Phase F: Mandatory Work Placement — Implementation

## Gate (entry criteria)

ADR-028 authored and canon landed: `placement.md`, `B19`, `B20`, `B21`, `B22`, `placement_assigned`, `domain_minted`, plus edits to `charter.md`, `domain.md`, `workflow.md`, `B3`. deepseek peer review folded (CHANGES-REQUIRED → all 7 findings addressed). Codex review pending lane availability 2026-08-19 — **not a blocker for W1-W3**, is a blocker for W7 fleet ship.

## Scope (what gets done)

Ship the Placement feature set in two runtimes: **Sutra plugin** (the per-turn block + hooks the founder uses daily, L0 fleet-wide) and **Native engine** (the registry, resolver, and events). Sutra ships first because it is where the dogfooding happens; Native follows with the durable engine.

## Duration (target wall-clock)

W1-W3 in the first working session block. W4-W6 across the following days. W7 gated on codex availability. Not a calendar commitment — a dependency ordering.

## DRI

Claude implements; founder reviews at each workstream boundary.

## Acceptance (exit criteria)

Every task below closed, plus: the PLACEMENT block prints on every turn in this repo; `.sutra-native/user-kit/placements/` holds rows for real work; B22 has run once against this repo and produced a coverage report; MECE report runs and returns a violation count.

---

## W1 — Sutra plugin: the printed block (11 tasks)

| # | Task | Verify |
|---|---|---|
| F1.1 | Add PLACEMENT to `sutra-defaults.json` `.per_turn_blocks` schema | `jq '.per_turn_blocks.placement'` returns object |
| F1.2 | Write the block spec into plugin CLAUDE.md GOVBLOCK template | `bash -n` on start.sh; apostrophe count even |
| F1.3 | Implement expanded render (full ancestor chain + `[NEW]` markers) | render fixture matches golden file |
| F1.4 | Implement compact render (one line, matched case) | render fixture matches golden |
| F1.5 | Render selector: expanded iff `created` non-empty | unit test both branches |
| F1.6 | ASCII-only assertion per D-UX-1 | grep for unicode box chars returns nothing |
| F1.7 | Charter line shows `title` + purpose first line, never bare `C-hash` | fixture assertion |
| F1.8 | Collapse to summary line when >20 units placed in one turn | fixture with 500 units |
| F1.9 | `.claude/placement-registered` marker written by the block | marker exists after turn |
| F1.10 | Bump plugin version (marketplace cache keys on version) | `jq .version` incremented |
| F1.11 | CHANGELOG entry ≤5 lines | file diff |

## W2 — Sutra plugin: the hook floor (9 + 5 tasks)

> **Peer-review fold (deepseek consult 2026-07-29, CHANGES-REQUIRED).** Three P1s
> changed this workstream before any code landed:
>
> | # | Finding | Fold |
> |---|---|---|
> | P1 | A new HARD gate shipped fleet-wide deadlocks on day zero — the model has never been required to emit this block, so the first miss blocks the next Edit with an opaque exit-2 | **Warn-first ladder** (F2.10-F2.12). `required: true` from day one, but enforcement starts at WARN and only flips to HARD once a repo clears a compliance threshold. On by default; punishing later |
> | P1 | Six mandatory blocks, one rendering a tree, pushes all-present compliance toward 70% — ~30% of turns would false-positive block | **COMPACT is the mandatory shape** (F1.4 is now the required render; F1.3 EXPANDED fires only when something was minted). No tree walk on the common path |
> | P1 | "Bash-mutation" is undefined — the gate needs a command classifier or it is either too broad or too narrow | **Explicit classifier** (F2.13), specified before the gate exists |
>
> Two P2s also folded: repo-local kill-switch (F2.14) rather than the global
> `~/.placement-disabled`, and no content parsing in the gate — presence only,
> with validity handled by a separate lint pass.
>
> Rejected from the review: deepseek claimed no-tool-turn enforcement is impossible
> because "a hook can't block 'no tool'". False — Claude Code Stop hooks do exactly
> that; `flow-stop-check.sh` and `h-sutra-enforce.sh` ship today and both blocked
> this very build session. F2.4 stands as written.

| # | Task | Verify |
|---|---|---|
| F2.1 | `placement-gate.sh` PreToolUse on Edit/Write/Bash-mutation | hook fires on test Edit |
| F2.2 | Gate blocks on missing **declaration**, never on missing domain | test: empty tree still passes |
| F2.3 | Registry-unwritable → HS-4 path, the only true halt | chmod test dir 000, assert halt |
| F2.4 | `placement-stop-check.sh` for no-tool turns | no-tool turn without block is caught |
| F2.5 | Kill-switch: `~/.placement-disabled` + `PLACEMENT_ACK=1` | both paths bypass cleanly |
| F2.6 | Per-turn marker reset wired into `reset-turn-markers.sh` | marker absent at turn start |
| F2.7 | Bootstrap-safe: hook must not self-gate its own install | fresh-repo install test |
| F2.8 | **Concurrent-session safe**: markers namespaced per session id | two sessions, no clobber |
| F2.9 | Log rows to `.enforcement/placement/gate-log.jsonl` | rows append, valid JSON |
| F2.10 | **Warn-first ladder**: gate reads `.claude/placement-mode` (`warn` \| `hard`); default `warn` | no marker + warn mode → exit 0 with stderr notice |
| F2.11 | Compliance counter: each turn that emits the block increments a per-repo count | counter file increments; survives restart |
| F2.12 | Auto-promote warn→hard once the repo clears the threshold (default 50 compliant turns, operator-overridable) | at threshold-1 exit 0; at threshold exit 2 |
| F2.13 | **Bash-mutation classifier**: explicit allow/deny lists. Read-only verbs (`ls cat grep find git status git log git diff wc head tail jq stat` …) never gate. Mutating verbs (`rm mv cp mkdir touch tee sed -i git commit git push git checkout` …) do. Redirection (`>`, `>>`) into a tracked path counts as mutation | fixture of 30 commands classifies correctly, 0 misses |
| F2.14 | **Repo-local kill-switch** `.claude/placement-disabled` takes precedence; global `~/.placement-disabled` retained but documented as fleet-wide | repo-local disables one repo only |

> F2.8 is not optional. This build was blocked twice by two sessions fighting over per-repo markers. Shipping a new per-turn gate with the same defect would multiply the problem fleet-wide.

## W3 — Classifier (12 tasks)

| # | Task | Verify |
|---|---|---|
| F3.1 | Evidence gatherer: utterance terms | unit test |
| F3.2 | Evidence gatherer: target file paths | unit test |
| F3.3 | Evidence gatherer: artifacts referenced | unit test |
| F3.4 | Evidence gatherer: adjacent existing Placements | unit test |
| F3.5 | Deepest-matching-ancestor search over the Domain registry | golden-tree fixture |
| F3.6 | Confidence scoring, 0.0-1.0, deterministic for identical input | same input → same score, 10 runs |
| F3.7 | Confidence floor constant + config override | below floor → floor-hold |
| F3.8 | Floor-hold path: place at ancestor, emit low-confidence event, **do not mint** | assert zero mints below floor |
| F3.9 | Mint path: child of deepest matching ancestor only (I-P4) | assert never a sibling overlap |
| F3.10 | Never mint a catch-all/misc node (P5) | name-blocklist test |
| F3.11 | Charter stub minter: title/purpose/scope inferred, `obligations: []` + reason | assert I-2 satisfied, zero fabricated obligations |
| F3.12 | Classifier eval pack: 50 labelled work units, measure precision | precision baseline recorded |

## W4 — Native registry + primitives (13 tasks)

| # | Task | Verify |
|---|---|---|
| F4.1 | `placements/` registry dir + `PL-<hash>.json` writer | file written, hash matches |
| F4.2 | Canonical form excludes `domain_path`/`domain_depth` (I-P8) | two rows differing only in path → same id |
| F4.3 | `CURRENT.jsonl` single-current pointer per `work_ref` (I-P5) | exactly one current after 3 supersessions |
| F4.4 | `supersedes` chain reconstructible | walk chain to origin |
| F4.5 | Domain: add stable `ref`, keep positional `id` derived | re-parent test: `ref` unchanged |
| F4.6 | Domain: `origin`, `touched_by_operator`, `mint_evidence` | fields persisted |
| F4.7 | **Atomic check-then-insert** on Domain mint (I-D2/I-P10) | 20 concurrent minters → exactly 1 node |
| F4.8 | Race loser adopts winner's `ref`, emits `race_adopted: true` | concurrency test asserts event |
| F4.9 | Charter: add `title` (≤60, non-empty) + `domain_ref` | mint rejects empty title |
| F4.10 | Workflow: add `domain_ref`; wire B3's MECE check to the now-real field | registration rejects bad ref |
| F4.11 | `placement_assigned` emitter | event shape matches spec |
| F4.12 | `domain_minted` emitter incl. `obligations_empty_reason` for charters | required-field assertion |
| F4.13 | Tenant scoping on every read/write; HS-3 on cross-tenant | cross-tenant attempt blocked |

## W5 — B20 restructure + consolidation (10 tasks)

| # | Task | Verify |
|---|---|---|
| F5.1 | RENAME — display only, zero re-placement | assert 0 rows minted |
| F5.2 | MOVE — subtree paths change, **zero re-placement** (the P1 fix) | assert 0 rows minted on 1000-row subtree |
| F5.3 | MERGE — re-point rows on absorbed node only | count matches absorbed-node rows |
| F5.4 | SPLIT — reclassify members; ambiguous rows surface | ambiguous list non-empty on fixture |
| F5.5 | DELETE — re-point to parent; root delete forbidden | root delete rejected |
| F5.6 | MECE re-validation; P5 violation rejects operation whole | violating merge leaves tree unchanged |
| F5.7 | Consolidation AUTO tier: system-minted + untouched + high similarity | auto-merges, no prompt |
| F5.8 | Consolidation PROPOSE tier: anything operator-touched | never auto-merges |
| F5.9 | MECE report: sibling overlap + unaddressed-unit count | deterministic across 2 runs |
| F5.10 | Blast-radius preview before apply | preview matches actual |

## W6 — Legacy: B21 + B22 (9 tasks)

| # | Task | Verify |
|---|---|---|
| F6.1 | B21 detect unaddressed target on touch | fires only when no current Placement |
| F6.2 | B21 stamp `origin=backfilled`, never delay work | timing assertion |
| F6.3 | B21 skip already-addressed targets | zero duplicate rows |
| F6.4 | B21 bulk-touch collapses to summary render | 500-file edit test |
| F6.5 | B22 corpus enumerator (paths, classes, history) | count matches `find` |
| F6.6 | B22 level-by-level derivation, stop below floor | flat corpus → depth 1, no invented depth |
| F6.7 | B22 idempotent on rerun | second run mints 0 |
| F6.8 | B22 resumable after interrupt | kill mid-run, rerun completes |
| F6.9 | B22 coverage report incl. MECE violations | report renders all fields |

## W7 — Ship + verify (8 tasks)

| # | Task | Verify |
|---|---|---|
| F7.1 | Codex review once lane returns (2026-08-19) | gate-log PASS entry |
| F7.2 | Reconcile codex vs deepseek findings; document divergence | divergence table in ADR-028 |
| F7.3 | Run B22 against this repo | coverage report exists |
| F7.4 | Dogfood: PLACEMENT block on every turn for 24h | no missing-block turns in log |
| F7.5 | Measure mint rate over the dogfood window | rate recorded; decaying or explained |
| F7.6 | Tune floor + AUTO threshold from real data (OQ-028-1, OQ-028-2) | values set with evidence, not guessed |
| F7.7 | T2 cohort rollout | fleet.sh shows adoption |
| F7.8 | Update `MEMORY.md` + `SYSTEM-MAP.md` | entries present |

---

## Dependencies (on other phases / blocks)

- W3 depends on W4's registry for the Domain search (dev against a fixture registry until F4.5 lands).
- W5 depends on F4.2 + F4.5 — the whole point of MOVE being cheap is the stable-ref split.
- W6 depends on W3 (shared classifier) and W4 (shared registry).
- W7.1 blocks fleet ship, not local dogfooding.

## Known risks

| Risk | Mitigation | Owner |
|---|---|---|
| Classifier precision too low → noisy tree | F3.12 eval pack sets a baseline before ship; F3.7 floor prevents the worst | W3 |
| AUTO consolidation merges things it shouldn't | Only ever touches system-minted, never-touched nodes; operator edit is a permanent latch | W5 |
| Per-turn block adds token cost every turn | Compact render is one line; expanded only when minting | W1 |
| Concurrent-session marker clobber (observed twice during this build) | F2.8 namespaces markers per session | W2 |
| Codex lane unavailable until 2026-08-19 | deepseek review folded now; codex is a confirmatory second pass, not the only gate | W7 |

## Task count

**72 tasks** across 7 workstreams.

## References

- [ADR-028](../../decisions/ADR-028-mandatory-work-placement.md) — the decision record.
- [placement.md](../primitives/placement.md) · [B19](../blocks/B19-work-placement.md) · [B20](../blocks/B20-domain-restructure.md) · [B21](../blocks/B21-backfill-on-touch.md) · [B22](../blocks/B22-domain-discovery-scan.md).
- deepseek consult 2026-07-27 — `.enforcement/deepseek-reviews/gate-log.jsonl`.
