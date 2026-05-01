# Sutra — Current Version

## v2.15.0 (2026-05-01) — governance-parity bump: 4 Asawa-side disciplines ship to T4 fleet

**What this is**: founder direction 2026-05-01 in this session — "ship everything to clients" — closes 4 of the v2.14.1 audit gaps. Three of them ship as expanded per-turn-discipline-prompt.sh stderr emissions; the fourth (subagent dispatch briefing) was already shipping in v2.14.1 via `subagent-dispatch-brief.sh` PreToolUse:Task hook and is verified here.

**The 4 disciplines now reaching T4 fleet**:

| # | Discipline | Mechanism | Status before v2.15.0 |
|---|---|---|---|
| 1 | **Skill-explain card** (D40 G3 — 4-line SKILL/WHAT/WHY/EXPECT/ASKS before invoking any skill) | `per-turn-discipline-prompt.sh` reads `.skill_explanation.template_lines` from sutra-defaults.json and emits a reminder line on every UserPromptSubmit | schema present in sutra-defaults.json since v2.9.0; **no hook reminder** — pure convention on Asawa side via [Explain skills on first use] memory |
| 2 | **Subagent dispatch briefing** (5-block + 4-line footer when invoking Task tool) | `subagent-dispatch-brief.sh` PreToolUse:Task hook (already shipping v2.14.1) — **verified** emitting `§Sutra discipline (mandatory)` prefix + 5 numbered blocks + 4-line footer reminder | shipped in v2.14.1; "T4 visibility unverified" note in v2.14.1 audit was overcautious |
| 3 | **Readability gate** (tables>prose, numbers>adjectives, ASCII boxes for decisions, no unicode boxes, progress bars for scores) | `per-turn-discipline-prompt.sh` reads `.output_discipline.*` boolean keys from sutra-defaults.json and emits a reminder line | schema present since v2.9.0; **no hook reminder** — Asawa-only enforcement at output time |
| 4 | **Karpathy right-effort discipline** (think first / simpler-alt / surgical scope / verify-loop) | NEW `.right_effort` schema key added to sutra-defaults.json + reminder line in per-turn-discipline-prompt.sh | Asawa-only memory ("Right-Effort Discipline (Karpathy)" in CLAUDE.md, sourced from github.com/forrestchang/andrej-karpathy-skills 2026-04-27); **no plugin coverage at all** before v2.15.0 |

**What changed in this commit**

| File | Change |
|---|---|
| `marketplace/plugin/sutra-defaults.json` | NEW `right_effort` section (Karpathy 4 principles + applies_before + kill_switch + comment lineage). Schema version bumped 1.0.4 → 1.0.5 not yet applied (deferred — v2.15.x backlog tracking). |
| `marketplace/plugin/hooks/per-turn-discipline-prompt.sh` | +6 jq reads (SE_LINES, SE_SKILL, RG_PRACTICES, RG_SKILL, RE_PRINCIPLES, RE_TOOLS) + 3 new printf lines after the Codex-consult line. Same kill-switches; same fail-open posture. |
| `marketplace/plugin/.claude-plugin/plugin.json` | version 2.14.1 → 2.15.0 |
| `.claude-plugin/marketplace.json` | version 2.14.1 → 2.15.0 + description preamble |
| `marketplace/plugin/SBOM-v2.15.0.txt` | NEW |

**Smoke test (per-turn hook expanded)**

```
[Sutra defaults · D40 v1.0.2] Per-turn block stack (emit in this order, top to bottom):
  1. [H-SUTRA HEADER]   single bracketed line, FIRST text in response   (skill: core:human-sutra)
  2. INPUT ROUTING      fields: INPUT / TYPE / EXISTING HOME / ROUTE / FIT CHECK / ACTION   ...
  3. DEPTH + ESTIMATION fields: TASK, DEPTH, EFFORT, COST, IMPACT   ...
  4. BLUEPRINT          fields: Doing / Steps / Scale / Stops if / Switch   ...
  5. BUILD-LAYER marker fields: BUILD-LAYER / ACTIVATION-SCOPE / TARGET-PATH   ...
  6. ... tool calls (Edit / Write / Bash / Agent) ...
  7. OUTPUT TRACE       > route: <skill> > <domain> > <nodes> > <terminal>   ...

  Codex consult: Depth >= 3 with Edit/Write/MultiEdit planned → consult codex first
  Skill-explain card: emit 4-line SKILL / WHAT / WHY / EXPECT / ASKS before invoking any skill   ←  NEW v2.15.0
  Readability gate: tables_preferred_over_prose, numbers_preferred_over_adjectives, decisions_in_ascii_boxes, ...   ←  NEW v2.15.0
  Right-effort discipline (Karpathy): think first / simpler-alt / surgical scope / verify-loop — apply before Edit/Write   ←  NEW v2.15.0
```

**Smoke test (subagent dispatch hook — item #2 verify)**

```
[Sutra defaults · D40 v1.0.4] Subagent dispatch reminder (sourced from sutra-defaults.json):
  When invoking the Task tool, prefix the dispatched prompt with this exact line:
    §Sutra discipline (mandatory)
  Followed by the 5 numbered blocks: Input Routing / Depth + Estimation / Build-Layer (if D38) / Operationalization 6-section / Codex review per layer
  End the dispatched prompt with the 4-line footer: TRIAGE / ESTIMATE / ACTUAL / OS TRACE
```

**Remaining backlog (v2.16.x)**

Capability Map (D43) classification gate, Customer Focus First (Doctrine Principle 0), No-fabrication, Table Shape (Impact + Effort columns), PROTO-006 process discipline. Each candidate for future bumps.

---

## v2.14.1 (2026-05-01) — per-turn-discipline reminder expanded to full 5-block stack (vinit feedback)

**What this is**: vinit reported that v2.14.0 "didn't show BLUEPRINT or H-Sutra layer" on his fleet machine. Diagnosis: v2.14.0 shipped the H-Sutra log-write infrastructure correctly, but the `per-turn-discipline-prompt.sh` stderr nudge only enumerated Input Routing + Depth+Estimation (plus the Codex-consult line). BLUEPRINT, H-Sutra header tag, OUTPUT TRACE, and BUILD-LAYER marker were left as model-side-only disciplines with NO hook nudge — so on a T4 client without `CLAUDE.md` governance, Claude had nothing telling it to emit those blocks. v2.14.1 closes the nudge gap.

**Fix**: the hook now reads all 5 `per_turn_blocks` keys from `sutra-defaults.json` and emits the full per-turn block stack in response-output order (1. [H-SUTRA HEADER] · 2. INPUT ROUTING · 3. DEPTH + ESTIMATION · 4. BLUEPRINT · 5. BUILD-LAYER marker · 6. tool calls · 7. OUTPUT TRACE). H-Sutra header is hardcoded in the hook for v2.14.1 because `sutra-defaults.json` doesn't have a `human_sutra` block key yet — adding that key is a v2.15.0 candidate.

**What changed**

| File | Change |
|---|---|
| `marketplace/plugin/hooks/per-turn-discipline-prompt.sh` | +18 net lines: read 8 additional jq fields (IR_SKILL, DEPTH_SKILL, BP_FIELDS, BP_SKILL, BL_FIELDS, BL_HOOK, OT_FORMAT, OT_SKILL); rewrite stderr emission to enumerate the full 7-row block stack + Codex consult line. Same kill-switches; same fail-open posture. |
| `marketplace/plugin/.claude-plugin/plugin.json` | version 2.14.0 → 2.14.1 |
| `.claude-plugin/marketplace.json` | version 2.14.0 → 2.14.1 + description preamble |
| `marketplace/plugin/SBOM-v2.14.1.txt` | NEW |

**Smoke test**

```
$ echo '{"prompt":"v2.14.1 smoke"}' | bash hooks/per-turn-discipline-prompt.sh
[Sutra defaults · D40 v1.0.2] Per-turn block stack (emit in this order, top to bottom):
  1. [H-SUTRA HEADER]   single bracketed line, FIRST text in response   (skill: core:human-sutra)
  2. INPUT ROUTING      fields: INPUT / TYPE / EXISTING HOME / ROUTE / FIT CHECK / ACTION   (skill: core:input-routing)
  3. DEPTH + ESTIMATION fields: TASK, DEPTH, EFFORT, COST, IMPACT   (skill: core:depth-estimation)
  4. BLUEPRINT          fields: Doing / Steps / Scale / Stops if / Switch   (skill: core:blueprint; emit ONLY when tool calls planned)
  5. BUILD-LAYER marker fields: BUILD-LAYER / ACTIVATION-SCOPE / TARGET-PATH   (only when editing D38-protected paths; hook: build-layer-check.sh)
  6. ... tool calls (Edit / Write / Bash / Agent) ...
  7. OUTPUT TRACE       > route: <skill> > <domain> > <nodes> > <terminal>   (skill: core:output-trace)

  Codex consult: Depth >= 3 with Edit/Write/MultiEdit planned → consult codex first (skill: core:codex-sutra)
```

**What still NOT shipped to T4** (parity audit, separate v2.15.x backlog)

These Asawa-side disciplines exist in `CLAUDE.md` but have no plugin hook reminder:

| Asawa discipline | Plugin coverage | Notes |
|---|---|---|
| Skill-explain card (D40 G3) | `sutra-defaults.json` has the schema; **no hook emits the reminder** | T4 model has no nudge to emit 4-line WHAT/WHY/EXPECT/ASKS card before invoking a skill |
| Subagent dispatch contract | `sutra-defaults.json` lists briefing blocks; hook `subagent-dispatch-brief.sh` registered but T4 visibility unverified | Per `feedback_subagent_dispatch_contract` — every Agent dispatch should brief 5 Sutra blocks |
| Readability gate (tables/numbers/ASCII boxes) | `sutra-defaults.json` has output_discipline keys but **no hook emits this reminder** | Asawa enforces at output time; T4 model gets no signal |
| Karpathy right-effort discipline | Memory-only on Asawa side | No plugin coverage at all |
| Customer Focus First (Doctrine Principle 0) | Memory-only on Asawa side | No plugin coverage |
| Highlight decisions (ASCII box) | Part of readability gate; no hook reminder | T4 model not nudged |
| No fabrication / no operational capacity | Memory-only on Asawa side | No plugin coverage |
| Table Shape (Impact + Effort columns) | CLAUDE.md mandates for task lists | No hook reminder |
| Process Discipline (PROTO-006) | Memory-only anchor | No plugin coverage |
| Capability Map (D43) | Just-ratified today; deferred PreToolUse hook in TODO #5 | T4 model has no awareness |

The pattern is consistent: most Asawa-side disciplines exist as either (a) memory-only entries or (b) `sutra-defaults.json` schema entries with no corresponding hook emission. v2.14.1 closes the per-turn-block-stack subset (5 of these). The rest are v2.15.x candidates per founder priority.

---

## v2.14.0 (2026-05-01) — H-Sutra Layer v1.0 ships to fleet + marketplace catchup

**What this is**: catch-up release that closes the merged≠shipping gap D43 ratified hours earlier today. Three previous-merged-but-never-marketplaced versions (v2.12.0 dispatcher portability, v2.13.0 python3 removal, post-v2.13.0 H-Sutra fold) consolidate under one shippable pointer. The marketplace `version` field was stuck at `2.11.1` while the dev tree advanced; cached plugin runtimes never received any of those changes. v2.14.0 unsticks the pointer.

**Headline**: H-Sutra Layer v1.0 (D42 visibility-before-influence) starts firing on every UserPromptSubmit across the Sutra fleet (Asawa + T4). Each turn is classified into the 9-cell CQRS-extended grid (3 verbs DIRECT/QUERY/ASSERT × 3 directions INBOUND/INTERNAL/OUTBOUND) + 3 orthogonal tags (TENSE/TIMING/CHANNEL) + REVERSIBILITY, then appended to `holding/state/interaction/log.jsonl` (when running in Asawa) or `.sutra/h-sutra.jsonl` (default). Stage-1 gate, OUT-QUERY guardrails, bounded retry + irreversible-domain denylist all carry over from the v1.0 charter. v1.0 = instrumentation only — no behavior optimization until 100–500 turns of log evidence accrue.

### What changed (vs v2.11.1 cached)

| Surface | Change | Origin |
|---|---|---|
| `marketplace/plugin/hooks/per-turn-discipline-prompt.sh` | +79 lines: H-Sutra classifier invocation + JSONL append | af84f15 (post-v2.13.0) |
| `marketplace/plugin/skills/human-sutra/{SKILL.md, ACTIVATION.md, scripts/classify.sh, tests/}` | NEW skill (already in 2.11.0/2.11.1 cache as scaffold; activated by per-turn-discipline fold) | D42 ship commits b88b7cc/f65725a/192bea4/a00cda3/7a32af4/106a94a |
| `marketplace/plugin/scripts/_sutra_project_lib.sh` + `start.sh` + `onboard.sh` | python3 removal — bash/jq port of the bootstrap path; sandbox-tested PATH-stripped (rc=0, identity preserved) | v2.13.0 (ac4e81c + 70893df) |
| 6 Asawa-coupled hooks (`dispatcher-pretool` / `dispatcher-stop` / `architecture-awareness` / +3) | EXTRACTED from plugin to holding/ — ~890 lines of dead weight removed from T4 fleet on-disk footprint | v2.12.0 (9f5a0a0) |
| `.claude-plugin/marketplace.json` | `version` field 2.11.1 → 2.14.0 (catches up over 12.0/13.0); description preamble freshened | v2.14.0 |
| `marketplace/plugin/.claude-plugin/plugin.json` | `version` field 2.13.0 → 2.14.0 | v2.14.0 |
| `SBOM-v2.14.0.txt` | NEW — SHA256 per shipped file | v2.14.0 |

### Resume trigger this fixes

D42 (today, 2026-05-01) shipped the H-Sutra Layer v1.0 to the dev tree but the marketplace was never bumped. Founder caught the gap on this session ("Push tip plug-in, bump everything, bump to the marketplace as well") — diagnostic showed cached plugin `core@2.11.1` had the skill scaffold but not the per-turn-discipline fold, so log.jsonl went silent after 10:18Z today even though founder kept using sessions. v2.14.0 hits `/plugin update` paths across Asawa + T4 fleet and the H-Sutra logging block fires from the next UserPromptSubmit forward.

### Codex consult

Not run for this release — surgical version-bump on top of three already-converged underlying releases (v2.12.0/v2.13.0/H-Sutra fold each codex-reviewed at their own ship). Per Karpathy surgical-scope discipline. Post-ship review on request.

### Tags

- `core-v2.12.0` retroactive at `9f5a0a0` (dispatcher portability)
- `core-v2.13.0` retroactive at `70893df` (python3 removal)
- `core-v2.14.0` at HEAD (H-Sutra v1.0 + marketplace catchup)

---

## v2.13.0 (2026-05-01) — remove python3 from /core:start bootstrap entirely (vinit#38 escalation)

**What this is**: durable fix for vinit#38 (filed by Vinit on behalf of @abhishekshah, 2026-04-28; escalation 2026-05-01). v2.8.11 moved python3 from stdin-heredoc to file-form to dodge SIGKILL from macOS sandbox/EDR agents. That fixed one class. The 2026-05-01 escalation showed `python3 -c "print('hello')"` itself exits 137 on the same client — the binary is killed regardless of how it's invoked (quarantine xattr, AV process-name killer, codesign mismatch). File-form vs heredoc is irrelevant when python3 itself can't survive exec.

**Fix**: remove python3 from the bootstrap path entirely. `_sutra_project_lib.py` retired to `archive/2026-05-01-py3-removed-from-bootstrap/`. Replaced by `_sutra_project_lib.sh` (bash/jq) with identical 4-subcommand surface and identical atomic-write contract (mktemp + mv on same fs; rename(2) atomic). `start.sh` adds upfront jq health gate with install hints. `onboard.sh` 4 inline `python3 -c` reads replaced with jq.

**Sandbox acceptance**: PATH stripped of all `python3*` → bootstrap rc=0, valid JSON, all 7 required fields, profile/telemetry patches stick, install_id + first_seen stable across re-runs, identity preserved, jq-missing case returns actionable install hint with rc=127, corrupt-JSON case returns rc=2.

**Codex consult**: not run (mechanical port — same surface, same atomic-write semantics, same idempotency). Codex post-ship review available on request.

### What changed

- `marketplace/plugin/scripts/_sutra_project_lib.sh` — NEW (bash/jq port of all 4 commands)
- `marketplace/plugin/scripts/_sutra_project_lib.py` — RETIRED to `archive/2026-05-01-py3-removed-from-bootstrap/`
- `marketplace/plugin/scripts/start.sh` — upfront jq health gate; sutra_run_python wrapper deleted; lib calls switched .py → .sh
- `marketplace/plugin/scripts/onboard.sh` — 4 inline python3 -c → jq; lib calls switched .py → .sh
- `marketplace/plugin/.claude-plugin/plugin.json` — version `2.12.0` → `2.13.0`

### What clients on broken-python3 macOS do

1. `/core:update` to v2.13.0
2. `which jq` (most macs have it; if not: `brew install jq`)
3. `/core:start` — works, no python3 invoked

---

## v2.12.0 (2026-05-01) — dispatcher portability charter: 6 Asawa-coupled hooks extracted from plugin to holding/

**What this is**: closes Tier 2 SHIPPED-DEAD findings from the plugin coverage audit (companion to `sutra` issue #49). 6 plugin hooks were heavily Asawa-coupled (hardcoded portfolio company names + holding/ paths) and never wired in `plugin/hooks/hooks.json`. T4 fleet was carrying ~890 lines of dead weight on disk for files it never executed.

**Codex consult 2026-05-01**: CODEX-VERDICT ADVISORY. Per codex P1: atomic — add holding-side first, rewire settings, verify, delete plugin copies last.

### What changed

- 6 hooks extracted from `sutra/marketplace/plugin/hooks/` to `holding/hooks/` with L2 (single-instance:asawa-holding) build-layer markers:
  - `dispatcher-pretool.sh` (548 lines, 16 holding/ refs, hardcoded company switch cases)
  - `dispatcher-stop.sh` (953 lines, 57 holding/ refs, reads FOUNDER-DIRECTIONS.md / DIRECTION-ENFORCEMENT.md / ESTIMATION-LOG.jsonl / checkpoints/)
  - `architecture-awareness.sh` (51 lines)
  - `research-cadence-check.sh` (135 lines)
  - `rtk-health-check.sh` (88 lines)
  - `principle-regression.sh` (250 lines)
- Asawa local `.claude/settings.json` lines 73 + 283 rewired from `sutra/marketplace/plugin/hooks/dispatcher-{pretool,stop}.sh` to `holding/hooks/dispatcher-{pretool,stop}.sh`.
- Plugin version `2.11.1` → `2.12.0`.

### Why this matters

Plugin = generic fleet primitives. Holding = Asawa-specific governance. Hardcoded portfolio company names that wouldn't generalize were a clear "instance-only" signal — they didn't belong in fleet plugin. Decouples Asawa specifics from Sutra OS source code; future T4 plugin installs are slimmer; future Sutra OS work doesn't carry Asawa baggage.

### What's NOT changed (fleet behavior)

These 6 hooks were never wired in `plugin/hooks/hooks.json` — fleet sessions never executed them. Functional behavior on T4 is **identical** before/after this release. Only on-disk footprint changes.

### Validation

- `jq -e .` parses `hooks.json` — VALID.
- 6 dangling refs in remaining plugin hooks are all `# Source:` / `# Wired from:` comments — historical attribution, not exec dependencies.
- Holding-side dispatcher smoke test: both run with stub stdin, exit 0.
- `holding/hooks/verify-policy-coverage.sh:189` `is_dispatcher_inlined()` already handles missing plugin-side files via `[ -f "$d" ] || continue` — no update required.

### Operator notes

- T4 / T3 / T2 users: no action needed. Plugin auto-updates via marketplace.
- Asawa: `.claude/settings.json` rewiring shipped in same atomic commit; no migration step.

---

## v2.11.1 (2026-05-01) — `feedback-channel-guard.sh` false-positive fix

**What this is**: third release in the same drift family as v2.10.0 (inbox-display packaging drift) and v2.10.1 (cascade-check stdout-vs-stderr drift). Surfaced when filing the Anthropic submission-pin update at `anthropics/claude-plugins-official` — the hook blocked because the issue body contained `https://github.com/sankalpasawa/sutra/...` URLs.

### Root cause

The hook's `SUTRA_TARGET` literal-substring check ran against `CMD_LOWER` (full command including quoted body content). So any `gh issue create` whose `--body` mentioned a Sutra URL triggered the Sutra-target match — even when `--repo` explicitly targeted a different repository. Same drift class as v2.8.8 (vinit#17), which fixed the ACTION match by switching to `CMD_HEAD` (command stripped at first quoted value) but missed the TARGET match.

### Fix

`CMD_HEAD` lifted out of the action-match block; both `SUTRA_TARGET` and ACTION matches now use `CMD_HEAD`. Body content can no longer trigger the gate.

### Validation

| Surface | Result |
|---|---|
| `tests/unit/test-feedback-channel-guard.sh` (NEW, 9 cases) | 9/9 PASS |
| Full unit suite | 15/15 PASS — zero regressions |
| Reproduction: `gh issue create --repo anthropics/claude-plugins-official --body "...sankalpasawa/sutra/issues/43..."` | Pre-fix: BLOCKED (false positive). Post-fix: PASSES, hook exits 0. |

### Threat model

Unchanged. Every previously-blocked Sutra-targeted write still blocks; only the false-positive on body content is closed. Adversarial obfuscation explicitly out of scope per v2.6.2 single-trusted-operator threat model.

### Three drift fixes in one day

- v2.10.0 — `inbox-display.sh` packaging drift (vinit#43)
- v2.10.1 — `cascade-check.sh` stdout-vs-stderr drift
- v2.11.1 — `feedback-channel-guard.sh` matcher-scope drift

---

## v2.10.2 (2026-05-01) — plugin coverage trial: paused assistant layer removed; D32 posttool dispatcher wired; override-audit lib promoted; output-behavior-lint wired

**What this is**: companion to `sutra` issue #49 (plugin self-inventory). Closes the "Tier 1 SHIPPED-BROKEN" + first slice of "Tier 2 SHIPPED-DEAD" findings from the audit. Net plugin diff: −888 / +296 / 8 files / 1 new lib.

### What changed

- **5 paused assistant-* hooks DELETED**: `assistant-decommission.sh` / `assistant-explain.sh` / `assistant-feedback.sh` / `assistant-observer.sh` / `assistant-kill-switch.sh`. Layer paused per D37; all 5 referenced `$REPO_ROOT/holding/state/...` paths absent on T4 machines (vinit#8 evidence).
- **D32 posttool dispatcher WIRED**: `dispatcher-posttool.sh` in PostToolUse (no matcher). Hot-reload registry — silent-exits without `os/SUTRA-CONFIG.md` + `os/hooks/posttool-registry.jsonl`. Clients can add custom posttool hooks via registry without plugin reinstall.
- **`output-behavior-lint.sh` WIRED in Stop**: silent advisory scanning the assistant transcript for "Never ask to run" + "No HTML unless asked" violations. Writes to `.enforcement/routing-misses.log` (mkdir -p safe). Exits 0 always; needs python3.
- **`override-audit.sh` PROMOTED to plugin**: `cascade-check.sh` and `codex-review-gate.sh` source via `[ -f $REPO_ROOT/... ] || _OA_LIB="$(dirname "$0")/lib/override-audit.sh"` — the dirname fallback now resolves on user machines. Was silently degrading to no-lib else-branch.

### Why this matters

Plugin coverage audit (companion to #49) found 5 categories of drift between the holding-daily-use and plugin-shipped surfaces. v2.10.2 closes Tier 1 and opens the first wedge of Tier 2. Remaining work: dispatcher portability charter (Tier 2 unblock) covers `dispatcher-pretool.sh` (16 holding-refs) + `dispatcher-stop.sh` (57 holding-refs) — both Asawa-coupled by HOOK_LOG paths, hardcoded company-name switch cases, and `FOUNDER-DIRECTIONS.md` reads.

### Validation

- `jq -e .` parses `hooks.json` — VALID.
- `grep -l "assistant-{decommission,explain,feedback,observer,kill-switch}"` across `plugin/hooks/` + `hooks.json` — **0 matches**.
- `realpath dirname/lib/override-audit.sh` from inside `cascade-check.sh` — **RESOLVED**.
- 5 fleet-effect scenarios in CHANGELOG matrix hand-checked.

### Operator notes

- No migration needed. Plugin auto-updates via marketplace.
- If you had `~/.sutra-assistant-enabled`: now a no-op file. Safe to `rm`.
- `output-behavior-lint` needs python3 to lint; absent → hook exits 0 silently.

---

## v2.10.1 (2026-05-01) — cascade-check.sh silent-block fix + tracking-artifact whitelist

**What this is**: companion fix to v2.10.0. The same drift family Vinit reported in #43 (silent hook diagnostics) had a *second* instance — `hooks/cascade-check.sh`. Caught during the v2.10.0 release session itself: two `cascade-check.sh` PostToolUse firings emitted `Failed with non-blocking status code: No stderr output` while editing `holding/research/2026-04-22-sutra-official-marketplace-submission.md`.

### Two root causes

1. **Diagnostics on stdout, not stderr.** Claude Code's PostToolUse hook protocol relays the hook's stderr when it exits non-zero. The hook printed BLOCKED, the policy reason, and the override hint to **stdout** via plain `echo` — Claude Code surfaces "No stderr output" because nothing reached stderr. Fix: the blocking diagnostic now routes via `{ echo ... } >&2`.
2. **Tracking artifacts triggered the gate.** Routine writes to research notes, session checkpoints, state ledgers, enforcement logs, telemetry — all already CLAUDE.md-whitelisted as "no advisory, no block" — were still firing the D13 cascade gate and demanding TODO follow-ups. Fix: the exempt list now matches the CLAUDE.md whitelist.

### What changed

| File | Change |
|---|---|
| `hooks/cascade-check.sh` | Block diagnostic moved into `{ ... } >&2` group; warning prelude moved out of unconditional path into the block branch only. New exempt cases: `*/.claude/*`, `*/.enforcement/*`, `*/.analytics/*`, `*/holding/research/*`, `*/holding/state/*`, `*/holding/checkpoints/*`, `*/holding/hooks/hook-log.jsonl`, `*/sutra/archive/*`. Existing `*/TODO.md`, `*/BACKLOG.md` exempts + the `*/holding/*` and `*/sutra/layer2-operating-system/*` gated paths preserved. |
| `tests/unit/test-cascade-check.sh` | NEW. 17 cases. |

### Validation

| Surface | Result |
|---|---|
| `tests/unit/test-cascade-check.sh` | 17/17 PASS |
| Full unit suite | 14/14 PASS (zero regressions from v2.10.0) |
| Reproduction (pre-fix): `holding/SYSTEM-MAP.md` blocked path | exit 2, stdout 13-line diagnostic, stderr **empty** |
| Reproduction (post-fix): same input | exit 2, stdout **empty**, stderr 13-line diagnostic |
| Reproduction (post-fix): `holding/research/test.md` whitelist | exit 0, stdout empty, stderr empty |

### Why ship as v2.10.1, not fold into v2.10.0

v2.10.0 already has a tag, GitHub release, and pushed pin. Folding the cascade-check fix into v2.10.0 would mean force-bumping a published tag — disallowed. v2.10.1 is the clean increment.

### What did NOT change

- Threat model: unchanged. D13 still HARD-blocks governance changes without TODO evidence; only diagnostic routing + whitelist scope changed.
- API/skill/command surface: unchanged.
- Telemetry behavior: unchanged.

---

## v2.10.0 (2026-05-01) — inbox-display ships; release packaging guard

**What this is**: a release fix for the SessionStart STDERR banner reported by Vinit (Testlify) as [issue #43](https://github.com/sankalpasawa/sutra/issues/43). Every `claude -r <id>` resume printed `inbox-display.sh: No such file or directory`. The hook was authored, registered in `hooks/hooks.json`, and worked in the asawa-holding working tree — but the `.sh` file was never `git add`'d, so the published plugin tarball shipped a manifest pointing at a missing file. v2.8.5, v2.8.11, v2.9.1 all carried the bug.

**Same drift class as v2.7.1**: description / manifest / source tree merged independently with no gate that all three agree.

### What v2.10.0 ships

- `hooks/inbox-display.sh` — now tracked in git. Close-Loop Layer V0 (FEEDBACK charter §N): on SessionStart, reads `clients/<install_id>/inbox/` from the sutra-data git rail to deliver close-out messages for issues filed via `sutra feedback --public`, with a gh-API fallback for gh-UI filers. Soft-fails on every error path (never blocks). Two kill-switches: `SUTRA_INBOX_DISABLED=1` env, `~/.sutra-inbox-disabled` file.
- `scripts/validate-hook-paths.sh` — pre-release CI guard. Reads `hooks.json`, expands every `${CLAUDE_PLUGIN_ROOT}` command path, confirms each exists on disk AND is git-tracked. Exits non-zero with the offender list. Will be wired into the pre-commit hook + every release-cut acceptance gate going forward.
- `tests/unit/test-validate-hook-paths.sh` — 4 cases: green plugin tree / referenced-missing-file / non-git pass-with-note / empty hooks.json defensive fail. Auto-discovered by `tests/run-all.sh`.

### Validation

| Surface | Result |
|---|---|
| `scripts/validate-hook-paths.sh` on HEAD | 49/49 hook paths present and tracked (exit 0) |
| `tests/unit/test-validate-hook-paths.sh` | 4/4 PASS |
| Cache install of v2.10.0 | will be verified post-publish; expected: `inbox-display.sh` present in `~/.claude/plugins/cache/sutra/core/2.10.0/hooks/` |

### What did NOT change

- No threat-model change.
- No API/skill/command surface change vs v2.9.1.
- No telemetry behavior change (v2.9.1 contract preserved).

### Lesson (mirrored from v2.7.1)

Every release commit must run `scripts/validate-hook-paths.sh` and exit 0. The v2.7.1 entry already noted "description-and-code can drift across parallel sessions" — v2.10.0 generalises that to "manifest-and-source-tree can drift" and ships a deterministic check.

---

## v2.7.1 (2026-04-28) — actually apply the v2.6.3 assistant-observer fix

**What this is**: a follow-up patch to v2.7.0. The v2.6.3 entry below (and the v2.7.0 description) claimed the assistant-observer.sh B7+B9 fix had shipped, but the v2.7.0 commit `f1f2352` only included the *narrative* — the actual one-line code change in `hooks/assistant-observer.sh` was a working-tree edit that never made it into a commit (it was bundled into a parallel-session commit that captured the version metadata but missed the .sh diff).

**v2.7.1 closes the gap** by actually applying the edits described in the v2.6.3 section:

- `hooks/assistant-observer.sh` line 55 — drop the redundant nested `${CLAUDE_PROJECT_DIR}`. New form:
  ```bash
  HOOK_LOG="${SUTRA_ASSISTANT_HOOK_LOG:-$REPO_ROOT/holding/hooks/hook-log.jsonl}"
  ```
  Closes both B7 (path double-substitution) and B9 (set-u crash) with one edit.

- `hooks/assistant-observer.sh` line ~164 — event `evidence_refs[0].source` field now uses `$HOOK_LOG` (the actual path read) instead of `${CLAUDE_PROJECT_DIR}/holding/hooks/hook-log.jsonl`. So `SUTRA_ASSISTANT_HOOK_LOG` overrides are reflected accurately.

- Mirrored to `holding/hooks/assistant-observer.sh`.

**Validation**: 24/24 `holding/hooks/tests/test-assistant-observer.sh` tests green. Manual-shell test with `CLAUDE_PROJECT_DIR` unset, `SUTRA_ASSISTANT_ENABLED=1`, and minimal `SUTRA_ASSISTANT_HOOK_LOG` override now exits cleanly and writes a correct `turn.observed` event.

**Re-enable pre-conditions** for the paused Sutra Assistant Layer (D37) now actually narrows to B1, B5, B6, B8 — as the v2.6.3 section already claimed.

**No threat-model change.** Both bugs lived inside the paused-by-default observer; the fix only matters once the layer is re-enabled (`sutra enable`).

**Lesson** (logged): description-and-code can drift across parallel sessions. Future plugin bumps should include a sanity check: if a section claims a file changed, verify the file actually changed in that commit.

## v2.7.0 (2026-04-28) — Permission system streamline (codex-converged)

Plugin v2.7.0 removes ~50% of permission-system code (1366 → 690 LoC) without changing the threat model or auto-approve behavior. Codex consult 2026-04-28 converged on this restructure after the founder asked "can we streamline this — it looks complicated."

### What got removed

| Artifact | Why |
|---|---|
| `lib/sh_lex_check.py` (228 LoC) | v2.4 compositional matcher. Trust Mode is a strict superset for Bash auto-approve. Drift-prone duplicate. |
| `scripts/rollback-compositional.sh` | Ties to the deleted matcher. |
| `tests/unit/test-sh-lex-check.sh` + `test-permission-gate-compositional.sh` + `test-rollback-compositional.sh` | Tests for deleted code. |
| `_match_bash_compositional` + `_env_has_shadowing` in `permission-gate.sh` | ~50 LoC. Tier 1.5 dispatch + v2.4 env-shadowing guard. |
| `_bash_summary_compositional_re` + `_bash_summary_env_shadowing` + `_is_allowlisted` mirror branch in `bash-summary-pretool.sh` | ~80 LoC. Drifted duplicate of permission-gate's allowlist logic. |
| Haiku LLM summarizer in `bash-summary-pretool.sh` | ~80 LoC. Caching, rate limiting, prompt template. Replaced with deterministic category text from Trust Mode (no API cost, equivalent UX). |
| `_danger_tag` heuristic | Replaced by `category` field already emitted by `sh_trust_mode.py`. |

### What got refactored

**`hooks/bash-summary-pretool.sh` is now a thin Trust Mode wrapper** (152 LoC, was 318):
- Reads stdin → calls `sh_trust_mode.py` once.
- Trust Mode says auto-approve → exit silently. Permission gate handles allow + persistence.
- Trust Mode says prompt → emit `permissionDecision: "ask"` with a deterministic per-category label + hint. Six categories (`git-mutation`, `privilege`, `recursive-delete`, `disk-system`, `fetch-exec`, `remote-state`) → six fixed strings.

**`hooks/permission-gate.sh` simplified** (264 LoC, was 318):
- Dispatch is now Tier 1 → Trust Mode (was Tier 1 → Tier 1.5 → Trust Mode).
- Tier 1 (sutra cmd, plugin lifecycle, marker writes, Write/Edit/MultiEdit narrow allowlist) retained per codex correction — Trust Mode is Bash-only and doesn't cover Write/Edit scope.

### Net effect

```
Before v2.7.0: 4 files, 1138 LoC
+ tests:       sh_lex_check, compositional, rollback (~150 LoC)
= 1366 LoC total

After v2.7.0:  3 files, 690 LoC + existing trust-mode tests (~140 LoC)
= 830 LoC total

Reduction: 39% (or 49% counting test files)
Single source of truth: sh_trust_mode.py
Single decision call: every hook calls the same classifier
```

### Threat model unchanged

Same as v2.5.0+. Single trusted local operator, no adversarial input. Trust Mode catches every irreversible op (force-push, clean -f, recursive-delete, privilege, disk/system, fetch-and-exec, gh delete-class, ssh/aws/kubectl/etc., db CLIs, package publish, docker push). Recoverable mutations auto-approve.

### Behavior parity verified

- 156/156 unit tests in `tests/unit/test-sh-trust-mode.sh` green.
- Manual smoke test of `bash-summary-pretool.sh`: `git push --force` → 🚨 Git catastrophic prompt; `git commit` → silent auto-approve; `gh repo delete` → ⚠️ Remote/shared-state prompt; `sudo rm -rf /etc` → 🚨 Privilege prompt; `curl | sh` → 🚨 Fetch-and-exec prompt.
- Drift bug codex caught: `bash-summary` skipped `claude plugin update *` and `rtk *` while `permission-gate` didn't. Single-source-of-truth eliminates this class of bug structurally.

### Codex review

Convergence: B (drop sh_lex_check), E (drop env-shadowing), D-partial (drop Haiku, keep deterministic category text). Disagreement: A (keep Tier 1 for Write/Edit + plugin lifecycle), C (merge code via shared lib, not phase model), F (~350-450 LoC realistic vs my ~250). Founder direction: ship the converged set + the disagreed set. Done.

### Migration / rollout

- Existing clients on v2.6.3 → v2.7.0: zero behavior change for permission decisions. Prompts that fired before fire now; auto-approves that fired before fire now.
- LLM cost reduction: Haiku no longer called on permission prompts. Net Anthropic-API spend goes down for plugin users.
- Plugin cache: `claude plugin marketplace update sutra && claude plugin update core@sutra` to pick up. New sessions auto-load.

## v2.6.3 (2026-04-28) — assistant-observer B7+B9 single-edit fix

Plugin v2.6.3 closes two bugs in `hooks/assistant-observer.sh` that lived on the same line:

**B7 (path double-substitution)** — prior form:
```bash
HOOK_LOG="${SUTRA_ASSISTANT_HOOK_LOG:-$REPO_ROOT/${CLAUDE_PROJECT_DIR}/holding/hooks/hook-log.jsonl}"
```
When CLAUDE_PROJECT_DIR is set (the typical hook context — and it's an absolute path), this expanded to `$REPO_ROOT/$ABSOLUTE_PATH/holding/hooks/hook-log.jsonl` — a malformed path that silently no-op'd.

**B9 (crash under `set -u`)** — same line, when CLAUDE_PROJECT_DIR was unset (manual-shell contexts, opt-in path tested via `SUTRA_ASSISTANT_ENABLED=1`), the bare `${CLAUDE_PROJECT_DIR}` reference crashed the observer with `unbound variable`. Discovered 2026-04-28 while verifying the v2.6.2 deployed shim.

**Fix** (single line): drop the redundant nested `${CLAUDE_PROJECT_DIR}` component. `REPO_ROOT` alone is the correct base — `git rev-parse --show-toplevel` returns the repo root absolute path; `holding/hooks/hook-log.jsonl` is its child. New form:
```bash
HOOK_LOG="${SUTRA_ASSISTANT_HOOK_LOG:-$REPO_ROOT/holding/hooks/hook-log.jsonl}"
```

Also: switched the event's `evidence_refs[0].source` field to use `$HOOK_LOG` (the actual path read) so the override via `SUTRA_ASSISTANT_HOOK_LOG` is reflected accurately in events.jsonl.

Mirrored to `holding/hooks/assistant-observer.sh` (the L1 staging copy already had B7 fixed; consolidated line-164 source field to match).

**Re-enable pre-conditions** for the paused Sutra Assistant Layer (D37): now B1, B5, B6, B8 remain. B2, B3, B4 fixed in v2.6.2; B7+B9 fixed here.

**No threat-model change.** Both bugs lived inside the paused-by-default observer; fix only matters once the layer is re-enabled (`sutra enable`).

## v2.6.2 (2026-04-27) — D36 Feedback Channel three-layer defense + D37 Assistant Layer default-OFF

Plugin v2.6.2 ships two independent founder directives from 2026-04-27, decoupled by mechanism (one feedback-system, one interaction-layer-system) and coupled only by the trigger conversation.

### D36 — Feedback Channel: three-layer defense

**Trigger**: 2026-04-27 — a v2.6.0 client session attempted `/core:feedback --public` which failed because the binary attached non-existent labels (`feedback`, `vunknown`); `gh issue create` rejects the whole call when any label is unknown. The session AI then bypassed the failure by calling `gh issue create --repo sankalpasawa/sutra` directly, leaking the founder's authenticated identity to a public artifact at sankalpasawa/sutra#15 (since closed).

**Mechanism** (three independent layers):

1. **Textual rule** — `hooks/feedback-routing-rule.sh` UserPromptSubmit hook adds explicit "binary failure does NOT graduate the assistant to manual workaround" clause (rules 4–6).
2. **Programmatic gate** — NEW `hooks/feedback-channel-guard.sh` PreToolUse:Bash hook. Exits 2 with stderr explanation on any `gh (issue|pr) (create|comment|review)` against `sankalpasawa/sutra*` repos. Allows close/view/list/non-Sutra repos. Kill-switch: `SUTRA_FEEDBACK_GUARD_DISABLED=1` or `~/.sutra-feedback-guard-disabled`. 12/12 functional tests green.
3. **Binary fix** — `scripts/feedback.sh` drops the `--label` flag (root cause of the failure that triggered the bypass instinct); plugin version moved to title (`[feedback v2.6.2] from plugin`); gh stderr now surfaces on failure.

**Why three layers**: Single-layer textual rules get rationalized around under "let me just help finish" framing during error recovery — exactly what happened in the trigger incident. Programmatic gate is the structural backstop; binary fix removes today's specific failure mode but the gate handles the next one.

### D37 — Sutra Assistant Layer: paused, default-OFF

**Why** (separate from D36): Assistant Layer v1 dogfood surfaced infra + wiring bugs unrelated to feedback. Stop hook errored on missing `jq` in some PATH configs; kill-switch shim's polarity was opt-out despite design comments stating "default-off" (D31/D32 intent); `holding/.claude/settings.json` registered the observer twice (direct + via kill-switch shim), defeating the kill-switch entirely. Founder paused the layer pending re-architecture.

**Mechanism**:

- **Polarity flipped** in `hooks/assistant-kill-switch.sh` — opt-in required via `~/.sutra-assistant-enabled` (file) or `SUTRA_ASSISTANT_ENABLED=1` (env). Hard kill-switches (`~/.sutra-assistant-disabled`, `~/.sutra-disabled`, `SUTRA_ASSISTANT_DISABLED`) still win as emergency overrides.
- **`bin/sutra enable` / `disable`** rewritten to manage the new flag and warn when emergency-kill files override.
- **Bug list B1–B8** captured in `holding/research/2026-04-24-assistant-layer-design.md` §0 — re-enable requires clearing the list before `sutra enable`.
- **Behavior change for users** who had v1 dogfood enabled: assistant goes silent until they explicitly run `sutra enable`. No fleet clients are known to be running it (Asawa-only dogfood).

### Threat model unchanged

Same threat model as v2.5.0+. Both directives strengthen existing protections; neither expands attack surface.

### Memory artifacts (Asawa-side)

- `feedback_three_layer_defense.md` — generalized pattern for any LLM-routing rule that must hold.
- D36/D37 logged separately in `holding/FOUNDER-DIRECTIONS.md`.

### Migration / rollout

- Existing clients on v2.6.1 upgrading to v2.6.2 see no change to feedback-channel UX unless they were calling `gh issue create` directly against `sankalpasawa/sutra*` (now blocked, exit 2).
- Assistant Layer goes silent for any client who was running v1 dogfood; `sutra enable` re-enables (subject to the B1-B8 bug list).

### Threat model unchanged

Single trusted local operator. No adversarial input.

## v2.6.1 (2026-04-27) — Trust Mode `gh`/`git` catastrophic-only rule

Plugin v2.6.1 refines Trust Mode (Tier 1.6) `gh` and `git` handling per founder direction: "Keep it simple. Just approve all the Git commands. Unless they're very catastrophic, like delete." Closes the founder-reported approval-fatigue gap where every `gh` invocation prompted because `gh` was a coarse REMOTE_TOOL, and recoverable `git` operations like `commit`/`push`/`rebase`/`merge` prompted unnecessarily.

**Mechanism** (`lib/sh_trust_mode.py`):

- **`gh`**: removed from REMOTE_TOOLS. Auto-approves every `gh ...` invocation EXCEPT delete-class actions: `is_gh_mutation` returns True only when the action token ∈ {`delete`, `remove`}. Catches `gh repo delete`, `gh release delete`, `gh secret delete`/`remove`, `gh issue delete`, `gh codespace delete`, `gh label delete`, `gh extension remove`, `gh gist delete`, `gh variable delete`. `gh api` auto-approves all methods (caller can deny via settings.local.json).
- **`git`**: simplified to two catastrophic patterns: `git push --force` / `-f` / `--force-with-lease` (rewrites/destroys remote history) and `git clean -f` / `-fd` / `-fdx` / `-fx` (irrecoverable untracked deletion). Everything else (`commit`, `push` non-force, `pull`, `rebase`, `merge`, `reset --hard`, `checkout`, `branch -D`, `tag -d`, `stash drop`, `rm`, `mv`) auto-approves — recoverable via reflog or remote.

**Validation**: 156/156 unit tests green (`tests/unit/test-sh-trust-mode.sh`). 72 auto-approve cases (40 gh read-only + 32 gh recoverable-mutation + 12 git recoverable-mutation + existing primitives), 30 prompt cases (catastrophic-only).

**Threat model unchanged** — same as v2.5.0 (single trusted local operator, no adversarial input). Recovery model: anything NOT prompting is recoverable via reflog, remote, fs, or Time Machine. The minimal prompt set catches every irrecoverable operation. Stricter threat models (multi-actor or untrusted operator) can re-enable broader prompts via `settings.local.json` deny rules — existing `Bash(gh repo delete*)` deny remains.

**Charter**: PERMISSIONS §4 Tier 1.6 row 6 + new "git mutations" sub-rule amended.

**Iteration history**: shipped initially (36431a8) as a granular subcommand-aware spec (28-line GH_MUTATION_ACTIONS dict mapping ~20 commands to ~80 mutation actions; mutation-by-default). Founder reverted spec mid-flight to catastrophic-only after seeing the implementation. Net code change vs granular: -112 / +33 lines (16af031 supersedes 36431a8).

**Follow-up** (deferred): the same catastrophic-only treatment can extend to `kubectl`, `aws`, `gcloud`, `helm`, `terraform`, `pulumi` if/when fleet feedback surfaces approval-fatigue on those tools. Currently they remain in REMOTE_TOOLS (every invocation prompts).

## v2.5.0 (2026-04-27) — Tier 1.6 Trust Mode

Plugin v2.5.0 inverts permission-gate from strict allowlist (v2.4) to denylist with 6 prompt categories. Auto-approves every Bash command except git mutations, privilege escalation, recursive deletes outside safe paths, disk/system catastrophes, fetch-and-exec patterns, and remote/shared-state mutations. Helper: `marketplace/plugin/lib/sh_trust_mode.py`. Charter §4 amended with new Tier 1.6. Codex MODIFY -> GO with 6th category added; Claude GO. Per founder direction "ship it."

Threat model: single trusted local operator, no adversarial input. Closes approval-fatigue feedback.

## v2.1.1 — core plugin patch (2026-04-25)

**Trigger**: T4 Sutra user reported `/core:start` writing governance to `~/.claude/CLAUDE.md` when run from their `$HOME` directory; feedback loop silently severed because `/core:feedback` docs said "No --send in v2" despite `--public` being wired at the script layer.

**Fixes** (marketplace/plugin/):

1. **scripts/start.sh — project-root guard**. Refuses activation when PROJECT_ROOT equals `$HOME`, is `/` or `/tmp` or `/private/tmp`, or has no project markers (`.git`/`package.json`/`pyproject.toml`/`Cargo.toml`/`go.mod`/`CLAUDE.md`). `--force` override for power users. Idempotent re-runs always proceed on initialized projects. Path compare is canonical (symlink-resolved) to prevent bypass via trailing slash, `/tmp` vs `/private/tmp`, or `$HOME` symlink tricks. `.git` check uses `-e` so worktrees/submodules (where `.git` is a FILE) count as valid markers. Covered by `tests/unit/test-start-guard.sh` — 10 assertions, all green.

2. **scripts/feedback.sh + commands/feedback.md — docs sync to v2.1 reality**. `--public` flag (GitHub issue post via `gh` CLI, scrubbed, confirmed) was wired in v2.1 at `scripts/feedback.sh:46-57,91-116` but `commands/feedback.md:11` said "No --send in v2, copy manually" and `scripts/feedback.sh:40` usage help said "NOT YET IMPLEMENTED". Both now document `--public` correctly.

3. **hooks/reset-turn-markers.sh — root-cause fix for synthetic-turn detection**. Was treating empty PROMPT (stdin with no `.prompt` field / jq fail) as real-founder-input and wiping per-turn governance markers — produced a 2052:1 wipe:skip ratio that blocked multi-tool edits in `sutra/**`. Now explicitly matches `""` as synthetic. Logged as `reset-skipped-empty-prompt` for telemetry.

**Review**: Codex review DIRECTIVE-ID 1777065370 ran on diff — CHANGES-REQUIRED (3 findings: P1 .git-as-file, P2 canon path, P2 feedback.sh header drift). All absorbed, tests 8 → 10 to cover P1+P2 regressions. Re-review implicit in passing tests.

---


## v2.4.0 (2026-04-25) — Tier 1.5 compositional reads

Permission-gate auto-approves safe read-only shell pipelines (ls, cat, grep, head, tail, wc, echo, printf, pwd, date, whoami, which, basename, dirname, realpath, cut, uniq, tr, column) composed via `; && || |` and stderr redirects `2>&1` / `2>/dev/null`. Python shlex-based tokenizer with 5-gate architecture (hard rejects, env shadowing, tokenize+fold, pipeline ops, per-primitive argv validation). `sh_lex_check.py` at `marketplace/plugin/lib/`. Charter §4 Tier 1.5 amended. 58+ unit tests + 11 integration + 1 rollback test, all green. Codex 10 rounds GO, Claude plan-eng-review GO.

Rollback: `bash marketplace/plugin/scripts/rollback-compositional.sh` strips `Bash(compositional-read:*)` from settings.local.json (idempotent, backs up once).

## v2.3.0 (2026-04-25) — additive: `sutra` CLI assistant subcommands

- **8 new `sutra` subcommands** for the Assistant Interaction Layer (v2.2.0 shipped the engine; v2.3.0 ships the terminal UX):
  - `sutra enable` — turn assistant on (removes kill-switch files)
  - `sutra disable` — persistent off via ~/.sutra-assistant-disabled (zero tokens)
  - `sutra explain [--last N|--turn N]` — narrative renderer
  - `sutra ask <surface> "question" "opt1,opt2,opt3"` — queue feedback prompt
  - `sutra answer <prompt_id> <option>` — answer a queued prompt
  - `sutra pending` — list unresolved feedback
  - `sutra profile` — show client profile
  - `sutra decommission [--dry-run|--confirm]` — product kill-switch
- All subcommands work in any client repo where `sutra` is on PATH (Claude Code auto-adds plugin bin/ to PATH).
- Founder directive 2026-04-25: "It should be able to update if the user says enable Billu — from the terminal itself." One command flips the switch in any company session.

# Sutra — Current Version

## v2.2.0 (2026-04-25) — additive: Assistant Interaction Layer

- **New OS class: Interaction Layer** at `os/interaction/`. First artifact: `ASSISTANT.md` charter. Sits above the 5 foundational blocks; human-facing surface for legibility, feedback capture, per-user customization (S2+), energy tracking (S5+), and passenger-mode problem-solving (S3+). Spec: `holding/research/2026-04-24-assistant-layer-design.md`.
- **5 new scripts in plugin hooks/**: `assistant-kill-switch.sh` (3-syscall zero-cost shim), `assistant-observer.sh` (turn.observed events, cursor-from-events-tip atomic), `assistant-explain.sh` (narrative renderer), `assistant-feedback.sh` (ask/list/answer/profile), `assistant-decommission.sh` (product kill-switch with atomic settings rewrite).
- **Stop hook registered**: `hooks.json` fires `assistant-kill-switch.sh` on every Stop; shim exits zero-cost if any of 3 disable flags active; otherwise exec's observer.
- **Default OFF at L1 per D32**. Clients flip `enabled_hooks.assistant_observer: true` in `os/SUTRA-CONFIG.md` to activate. 4-layer kill-switch (L1 Sutra authority / L2 user runtime / L3 per-instance / L4 product decommission).
- **Event contract v1.0**: `turn.observed`, `log.rewound`, `feedback.prompted`, `feedback.captured`. Envelope stable; payloads starting shape (will evolve at S2+).
- **39 tests green** at Asawa reference instance (9 kill-switch + 24 observer + 6 explain). Codex rounds: 4 absorbed (1 REJECT → MODIFY → PASS on approach/spec/P2/P3).

## v1.9.1 (2026-04-20) — additive

- **Charters as first-class OS concept**: new directory `os/charters/` parallel to `os/engines/` and `os/protocols/`. Holds cross-cutting Initiative Charters (vs. unit-level Definition Charters like `departments/*/CHARTER.md`). Placement doc + protocol for adding new charters in `os/charters/README.md`. Unit-architecture model documented: every unit (org, department, sub-unit) = definition charter + skills + initiative charter participations; cascades recursively.
- **Initiative Charter: Tokens** (`os/charters/TOKENS.md`) — first cross-cutting charter. DRI Sutra-OS; Contributors Analytics, Engineering, Operations. Applies to Sutra (first instance). Downstream propagation queued (requires `upgrade-clients.sh` extension — tracked in charter roadmap step 12). Q2 OKRs: baseline 6 companies × 10 sessions by Apr 26, boot P50 −30% and gov overhead <15% by Jun 30, propagate to ≥3 companies.
- **Follow-on formalization queued in TODO**: PROTO-019 candidate for unit-architecture + `ADDING-DEPARTMENTS.md` + schema extension for charters in `state/system.yaml`.
- Triggered by: Founder direction 2026-04-20 — "A lot of tokens have been used; we need to find some optimization ways" + "departments are skills; charters are cross-sectional; both cascade at every level."

## v1.9 (2026-04-15)

- **PROTO-017 Policy-to-Implementation Coverage Gate**: every edit to a Sutra policy file surfaces a PROTO-000 reminder (5-part rule); `verify-policy-coverage.sh` generates `POLICY-COVERAGE.md` ledger mapping every written commitment to its enforcer and deployed clients. Rows without both are DRIFT.
- **PROTO-018 Auto-Propagation on Version Bump**: `upgrade-clients.sh` walks the client registry on version change and reorganizes each client to the new manifest (sync engines, pin version, install declared hooks, register in settings.json). Closes the drift loop where version bumps in Sutra didn't propagate.
- **MANIFEST-v1.9**: tier-aware (1 governance, 2 product, 3 platform). Covers ALL shipping hooks, not just `enforce-boundaries.sh`. Asserts declared ⊆ installed invariant per client.
- **verify-os-deploy.sh extended** to accept `asawa` (holding) and `sutra` (self) as targets. Holding and platform are now in the verification universe.
- Triggered by: Billu onboarding audit (2026-04-15) — declared-but-not-installed hooks (RC4) + manifest silent on 95% of shipping hooks + recurring version drift. The drift pattern stops here.

## v1.8 (2026-04-11)

- **COVERAGE-ENGINE.md v1.0**: Runtime process coverage for client companies. Tracks whether every expected Sutra step fired during a session, per task, per depth. 26 trackable methods across 6 categories (gates, engines, lifecycle phases, verification, research, calibration). Expected checklist auto-generated from assigned depth (D1=4 steps, D2=7, D3=14, D4=19, D5=24).
- **method-registry.jsonl**: Machine-readable registry of all Sutra methods with depth requirements. Deployed to each company's `os/` directory.
- **Coverage hooks**: `log-coverage.sh` (logs method fires with evidence) + `coverage-report.sh` (reads log, compares to expected, shows gaps). Deployed to `.claude/hooks/`.
- **Coverage toggle**: `coverage: on|off` in SUTRA-CONFIG.md. Silent no-op when off. Zero overhead in production.
- **Evidence requirement**: Each logged method must include task-specific evidence, not generic claims. "goal: audit 47 pages" is valid; "defined objective" is not.
- **Aggregation**: Task-level, session-level, and 30-day rolling company-level coverage reports.
- Triggered by: Founder direction 2026-04-09 — "when a client company is running on Sutra, I want to monitor whether all methods are being used." Tested on Dharmik (2 tasks, 100% coverage). Deployed to DayFlow.

## v1.7 (2026-04-06)

- **ADAPTIVE-PROTOCOL.md v3**: "Gear" renamed to "Depth" (customer focus). 5 depth levels (1-5) controlling task decomposition granularity. Speed vs precision as governing trade-off. Company size no longer determines depth. Progressive OS merged as Company State.
- **P9 principle**: Structure adapts, content is configurable. Don't hardcode values that vary by company.
- **Task-to-protocol conversion**: LEARN phase now converts solved tasks into reusable protocols. First time = problem-solving. Second time = follow the protocol.
- **PROTO-013/014**: Enterprise-grade version deploy + client-side auto-check. 5-phase deploy (classify > deploy > verify > graduate > deprecate). 4-level verification (install > behavioral > adoption scorecard > mechanical). Phase 0 baseline check catches gaps from previous versions.
- **Founding Principle 0**: Customer Focus First — supersedes all five founding principles. If the customer doesn't get it, the rest doesn't matter.
- **verify-os-deploy.sh**: Runnable verification script for all 4 levels. CEO of Asawa can audit any company's OS compliance.

## v1.6 (2026-04-06)

- **CHARTERS.md**: Cross-functional goal framework — horizontal outcome goals that span vertical practices; KRAs, KPIs, OKRs per charter; DRI + contributors model
- **ROADMAP-MEETING.md**: Replaces HOD Meeting with OKR-driven process — impact/effort matrix, forward-looking goal-setting instead of backward-looking status updates
- **INPUT-ROUTING.md**: Human input classification protocol — every founder input classified (direction/task/feedback/new concept/question) before action; 3 enforcement levels (hook gate, protocol, skill); whitelisted system-maintenance actions
- **ADAPTIVE-PROTOCOL.md v2**: 10 parameters, pre-scoring gates, two-axis routing, undertriage tracking
- **TASK-LIFECYCLE.md updated**: L1 fast-path added; artifact requirements matrix (HLD, ADR, research gate, regression test at L3+)
- **ESTIMATION-ENGINE.md updated**: Auto-calibration feedback loop, CALIBRATION-STATE.json, log format v1.1
- **HUMAN-AGENT-INTERFACE**: Consolidated from L2 contraction
- **4 artifact templates**: HLD, ADR, Research Gate, Bug Fix
- **OKRs.md**: 8 charters for Sutra (expanded from 4)
- **Versioning protocol**: CURRENT-VERSION.md split from RELEASES.md
- **Tiered research cadence**: AI research weekly, frameworks bi-weekly
- **Client registry**: 6 companies (DayFlow, PPR, Maze, Jarvis, Paisa, Asawa)
- Triggered by: Founder session 2026-04-06 — infrastructure hardening, adaptive protocol v2, artifact gates, estimation auto-calibration

## Client Registry

Reconciled 2026-04-17 (post-propagation run: `bash holding/hooks/upgrade-clients.sh` + CLAUDE.md version bumps in maze/ppr/paisa/asawa).

Status vocabulary: `IN-SYNC` (all artifacts at pinned) · `PARTIAL` (SUTRA-VERSION bumped but v1.9 artifacts missing) · `STALE` (pinned behind current) · `GHOST` (registry row exists but no on-disk directory).

| # | Company | Pinned to | Tier | Status |
|---|---------|-----------|------|--------|
| 1 | DayFlow | v1.9 | 2 | IN-SYNC — verify-os-deploy.sh 100%. |
| 2 | PPR | v1.9 | 2 | IN-SYNC — 2026-04-17 propagation run. verify-os-deploy.sh 100%. |
| 3 | Maze | v1.9 | 2 | IN-SYNC — 2026-04-17 propagation run. verify-os-deploy.sh 100%. |
| 4 | Paisa | v1.9 | 2 | IN-SYNC — 2026-04-17 propagation run (up from v1.4 STALE). verify-os-deploy.sh 100%. |
| 5 | Asawa | v1.9 | 1 | IN-SYNC — holding CLAUDE.md bumped 2026-04-17. |
| 6 | Dharmik | v1.8 | 2 | GHOST — external client, no on-disk dir at asawa-holding/dharmik. Row reflects last known. |
| 7 | Billu | v1.9 | 1 | IN-SYNC at tier-1 scope. CLAUDE.md/SUTRA-VERSION=v1.9. MANIFEST + POLICY-COVERAGE not required at tier 1. |
| 8 | Sutra | v1.9 | 3 | SELF-HOSTED. Governance + platform. POLICY-COVERAGE.md = sutra/layer2-operating-system/POLICY-COVERAGE.md (canonical). |

*Jarvis row removed 2026-04-17: archived per SYSTEM-MAP 2026-04-15, replaced by Billu. No on-disk directory; no ongoing work. Per "either onboard or remove row" directive.*

## Release Model

```
SUTRA (develops continuously)
  │
  │ Publishes: v1.0, v1.1, v1.2, v2.0...
  │
  ▼
RELEASE (versioned, stable snapshot)
  │
  │ Client fetches a specific version
  │
  ▼
DAYFLOW (pins to v1.0, runs it, gives feedback)
  │
  │ Feedback goes to Sutra (not to the release)
  │
  ▼
SUTRA (incorporates feedback into next version)
  │
  │ Publishes v1.1 (includes DayFlow's learnings)
  │
  ▼
DAYFLOW (decides when to upgrade: stay on v1.0 or fetch v1.1)
```
