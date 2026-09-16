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

**Outputs**: nothing on stdout, nothing on stderr, in every mode (D12) — a
killed native step is the one exception that DOES print (`bin/sutra-turn`
itself, not this script, on watchdog timeout). Every diagnostic is a ledger
row via `sutra_ledger_write` on both `SUTRA_LEDGER_CANON` and `SUTRA_LEDGER_FLAT`
(D13) — never `sutra_ledger_step`/`sutra_ledger_acc`, those are the parent's.

**Failure**: always exits 0. Each script wraps its logic in `main` called as
`main "$@" || true; exit 0`, plus an outer `trap 'exit 0' EXIT` — no input
shape, missing tool, or internal error can make the step non-zero.

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
