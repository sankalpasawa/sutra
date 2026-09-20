# runtime/steps/ — native step contract (Sutra Runtime MVP-1)

Every script here is spawned by `bin/sutra-turn` through `sutra_shim_run`,
exactly like a `shim:` step (own stdin copy, own watchdog, own rc file), but
registered as `impl":"native:<name>"` with `"phase":"post"` — it runs once,
serially, after the pass-1 `wait` (BRIEF.md D3, D4).

**Inputs**: stdin = the same JSON the host gave the event (UserPromptSubmit
or Stop). **Env** (exported by the spawning subshell, D3): `SUTRA_STEP_ID`,
`SUTRA_TURN_ID`, `SUTRA_EVENT`, plus everything `sutra_ledger_init` already
exported (`SUTRA_LEDGER_CANON`, `SUTRA_LEDGER_FLAT`, ...), `CLAUDE_PROJECT_DIR`,
`CLAUDE_PLUGIN_ROOT`, `HOME`.

**Outputs**: nothing on stdout, nothing on stderr, whenever the step's
per-box flag resolves `off` (D12, amended by adherence row 1 D-A1: with its
flag `on` a step may print exactly ONE JSON object, which `bin/sutra-turn`
merges like any shim's). Golden parity runs under a private HOME, so every
flag is absent there and the byte-identical requirement is untouched. A
killed native step is the one exception that DOES print (`bin/sutra-turn`
itself, not this script, on watchdog timeout). Every diagnostic is a ledger
row via `sutra_ledger_write` on both `SUTRA_LEDGER_CANON` and `SUTRA_LEDGER_FLAT`
(D13) — never `sutra_ledger_step`/`sutra_ledger_acc`, those are the parent's.

**Synthetic prompts**: every step that keys on `.prompt` calls
`sutra_prompt_synthetic` from `runtime/lib/prompt.sh` (the six
reset-turn-markers.sh guards plus `<task-notification>` and
`[SYSTEM NOTIFICATION`, added 2026-09-16 after a notification rewrote the
depth marker).

**Failure**: always exits 0. Each script wraps its logic in `main` called as
`main "$@" || true; exit 0`, plus an outer `trap 'exit 0' EXIT` — no input
shape, missing tool, or internal error can make the step non-zero.

## The adherence family (rows 1-5, 2026-09-17), flag `~/.sutra-runtime-adherence` on|warn|off

| Step | Event | What it does |
|---|---|---|
| `steps_ledger.sh` (`ups.steps_ledger`, after markers_write) | UserPromptSubmit | opens `.sutra/turn/<sid>/<turn>.steps.json` (11 steps); emits ONE additionalContext: the RENDERED STACK from facts (row 5, `<<FILL:x>>` for judgment fields), the STEP TRACE, the lens/cynefin prompts while pending (row 3), the previous turn's lane results. Budget `budgets.context.render_chars_max`, drop order prompts, stack, never the trace |
| `adherence_gate.sh` (`pre.adherence_gate`, class B) | PreToolUse | refuses a mutation (deny on, systemMessage warn) until `<turn>.lens.json` + `<turn>.cynefin.json` validate (`runtime/lib/artifact.sh`); artifact writes, session markers, memory files, `.enforcement/` and the governance CLIs are exempt; Bash is judged per segment (quote-aware), a command is exempt when every MUTATING segment is |
| `steps_close.sh` (`stop.steps_close`) | Stop | closes the ledger: statuses, `trace_pasted`, `fills_left` |
| `blueprint_progress.sh` (`post.blueprint_progress`) | PostToolUse | row 6.2 (2026-09-20): runs the blueprint's verify commands not yet passed after every tool call (1.5 s each, 3 s per call, 4500 ms step budget), writes `<turn>.progress.json`, prints `[sutra <t8>] blueprint step n/N done: <do>` the moment a step flips; slow (>2 s) and manual steps are marked once and left to the Stop lane. The sealed `<turn>.verifies.json` from `stop.review_lane` stays the record; the Stop table and `sutra-steps statusline` show the blueprint's own steps from whichever exists |
| `review_lane.sh` (`stop.review_lane`) | Stop | when the turn mutated repo files: detaches the declared `test_command` and a second-lane review of the diff (`runtime/lib/deepseek-review.sh`, or `$SUTRA_REVIEW_LANE_CMD`), writing `<turn>.tests.json` / `<turn>.review.json` and the session marker `deepseek-consulted` (SOURCE=runtime). `hooks/codex-consult-gate.sh` accepts a fresh (1800 s) done verdict |

Rows: `steps_open` `steps_skip` `steps_rotate` `steps_drop` `steps_close` `adherence_decision` `adherence_transition` `adherence_rules` `lane_tests` `lane_review` `lane_skip`. The one override file `~/.sutra-overrides` (row 4) is applied by `bin/sutra-turn` through `runtime/lib/overrides.sh` before step 0 (row `override_file`, audit `.enforcement/overrides.jsonl`); since 2.285.1 it is honoured only when it predates the session stamp and the runtime flags are not override keys. `bin/sutra-steps` prints a turn's ledger (`latest`, `pretty`, `statusline`, `truthdiff`, `--json`).

### Row 6, slice 1 (2.286.0, 2026-09-19): the rules table

`runtime/rules/gates.json` declares rules R1-R9 (`when`: kind, path_category from the D38 table as data, depth_min, new_path, placement_unresolved, lane_configured; `needs`: `step:<id>`, `artifact:<kind>`, `review:sealed`, `override:<KEY>`; `needs_any`). `adherence_gate.sh` builds one context per call, evaluates every applicable rule and names every unmet one in a single refusal (D-A13). Artifacts (`runtime/lib/artifact.sh`): `lens`, `cynefin`, `blueprint` (steps with `verify:{kind:cmd|manual,cmd}`; cmd required at depth 3+, shell no-ops refused; a manual-only blueprint is `open`, never `done`), `build_layer` (L1 promotion fields or L2 kind + reason), `placement` (only on an engine no-match), `depth` (raise only). Lane verdicts carry `seal` (`runtime/lib/seal.sh`, HMAC-SHA256 with the per-box key); step 8 counts only a sealed, corroborated verdict of this or the previous turn (D-A14). Runtime-owned paths (R9, D-A15): the flag, kill and override files, the seal dir, the session stamp, and the turn's facts / steps / lane / truth-diff files. Armed collapse (D-A12/D-A17): `bin/sutra-turn` exports `SUTRA_ADHERENCE_GATE_ARMED=1` for a PreToolUse event only when the mode is exactly `on`, jq is present and `pre.adherence_gate` is selected; the eleven registrations in `collapsed_steps.ids` still run, their decision is written to `<turn>.truthdiff.jsonl` and dropped from the emission; unarmed (warn, kill-switch, jq or pipeline missing) they decide as before. Deleting them (2.287.0) waits on the brief's truth-diff gate. Tests: `runtime/tests/test-gate-rules.sh`.

## markers_write.sh — `native:markers_write`, UserPromptSubmit, phase post

Computes `input-routed`, `depth-registered`, `flow-classified`,
`flow-type-resolved` from `classify.sh` / `workflow-type-match.sh` /
`flow-factors.sh` and writes them with `sutra_marker_set` when the per-box
flag (`runtime/flags.sh`) is `on`, or to `.sutra/shadow/markers/<sid>/<turn>/`
when `shadow`. Writes `.sutra/turn/<sid>/<turn>.facts.json` (D14) in both
modes. A marker already carrying a model-narrated body (no `SOURCE=runtime`
/ `FIRED_BY=hook` line) is left untouched (D6) — logged `marker_skip`
`reason:narrated`, never overwritten.

Rows: `marker_flag` (once, mode+source) · `marker_write` · `marker_skip`
(`flag-off` | `synthetic` | `narrated` | `no-session`) · `marker_shadow` ·
`marker_source_failed` (`tool`, `exit`) per failed source call.

## markers_diff.sh — `native:markers_diff`, Stop, phase post

Only runs its comparator when the flag is `on`/`shadow` (a `marker_flag`
row is still written on `off`, matching markers_write.sh). Reads the
model's `[DIR·VERB · TIMING:.. · CHANNEL:.. · REV:.. · RISK:..]` header,
the FLOW `[2] RESOLVE:` line, and the `DEPTH: N/5` block from
`.last_assistant_message` (or the last 262144 bytes of `transcript_path`),
and diffs each field against the turn's `.facts.json` and the CURRENT
marker files. `name` = which marker the field belongs to
(`flow-classified`: DIRECTION/VERB/TIMING/CHANNEL/REV/RISK;
`depth-registered`: DEPTH, compared within 1; `flow-type-resolved`:
RESOLUTION/SCOPE). `gate_field` is true for everything except
RESOLUTION/SCOPE. `would_have_blocked` reads the marker file's presence
RIGHT NOW, independent of `runtime` (from facts). One `marker_diff_turn`
summary line per turn to `.sutra/shadow/markers/turns.jsonl`; every
non-equal `gate_field` row also lands in `.sutra/shadow/markers/diffs.jsonl`.
No facts file → one row `facts_present:false`. No parseable header → one
row `header_parsed:false`. Neither ever crashes; both just stop.
