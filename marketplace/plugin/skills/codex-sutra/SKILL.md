---
name: codex-sutra
preamble-tier: 3
version: 1.0.0
description: |
  Sutra-owned wrapper for the OpenAI Codex CLI. Three modes — Review (diff
  pass/fail gate), Challenge (adversarial), Consult (Q&A with session
  continuity). Forked from gstack /codex (source SHA: see "Upstream sync"
  section). Hard cap raised from 5 min to 15 min, with 10-min progress warn
  and 5-min stall warn. Use when invoked by the founder or by PROTO-019 hooks
  for the codex-by-codex review path. NOT auto-invoked.
allowed-tools:
  - Bash
  - BashOutput
  - Read
  - Write
  - AskUserQuestion
upstream-source:
  repo: gstack /codex skill (~/.claude/skills/gstack/codex/SKILL.md)
  sha-at-fork: 1.0.0 (gstack codex skill v1.0.0, observed 2026-04-28)
  sync-cadence: quarterly review of upstream diff; manual port of relevant changes
---

## Why this skill exists

Sutra needs an owned, controlled-cap codex review primitive for PROTO-019
v2's codex-by-codex path. The gstack `/codex` skill enforces a 5-minute
Bash timeout (`timeout: 300000`) — too short for "high" reasoning effort on
medium diffs. codex-sutra uses background execution with a 15-minute hard
cap enforced by the wrapper's own polling logic.

## What changed vs gstack /codex

This is **not** a one-line change. Five functional changes:

1. **Hard cap 5m → 15m** (the explicit ask).
2. **Foreground `timeout: 300000` → background + polling** (Bash foreground
   maxes at 10 min; 15-min cap requires bg).
3. **Log path** `~/.gstack/.../review-log` → `.enforcement/codex-reviews/gate-log.jsonl` (PROTO-019 path).
4. **Boundary list extended** to exclude `sutra/marketplace/plugin/skills/`
   and `sutra/marketplace/plugin/hooks/` (Sutra skill files).
5. **Canonical for codex-by-codex review** under PROTO-019, replacing
   gstack /codex for that specific path. Other gstack skills unaffected.

Each change widens the migration / regression surface vs gstack. Sync
policy: see "Upstream sync" section.

---

## Default policy: consult-before-Edit at Depth >= 3 (D40 G2)

**Per founder direction D40 (2026-04-30)** + memory `[Codex consult on everything]` + `[Converge and proceed]`:

When the model is preparing to call **Edit / Write / MultiEdit** AND the current task's **Depth is >= 3** (thorough / rigorous / exhaustive per `core:depth-estimation`), invoke this skill in **consult mode** with a tight <500-word prompt **before** the first Edit/Write call. Surface convergence with codex; per `[Converge and proceed]` execute end-to-end if both agree.

**Where the policy lives**: `sutra-defaults.json` `.consult_policy` is the **SINGLE canonical source**. This skill defers to that surface — fields are NOT duplicated here per codex CHANGES-REQUIRED fold (v1.0.1). Runtime read: `jq '.consult_policy' "$CLAUDE_PLUGIN_ROOT/sutra-defaults.json"`. For thresholds, override paths, or convergence pattern, query the json — do not hardcode.

**Why this is convention, not enforcement**: per codex caveat in the D40 verdict, hook-injects-prompt is fragile (prompt dilution, cosmetic emission, prompt collision, token bloat, subagent drift). Consult-before-Edit relies on the model choosing to invoke this skill at the right moment. Skills/docs EXPLAIN; hooks ENFORCE — and Claude Code has no PreEditWithDepthThreshold hook. The policy is documented at the canonical surface so the model has a stable instruction; the deterministic backstop is `codex-directive-gate.sh` for explicit founder directives.

**Override path**: see `sutra-defaults.json` `.kill_switches.consult_before_edit`. Founder explicit override phrase ("skip consult, just edit") is founder authority, not a bypass per `[Never bypass governance]`.

**Chunking**: per `[Chunk LLM work]` keep each consult call < 5 minutes; per `sutra-defaults.json` `.consult_policy.max_call_duration_minutes`. Split larger questions into sequential consults rather than one long call.

---

## Defense layers (boundary is NOT the only control)

Three layers protect against codex reading skill files, in order of strength:

1. **Sandbox** (primary): `codex exec ... -s read-only -C $REPO_ROOT` — codex
   is filesystem-confined to the repo root. It cannot read `~/.claude/`,
   `~/.agents/`, or anything outside the repo. This is enforced by codex itself.
2. **Prompt boundary** (defense-in-depth): every prompt leads with the
   filesystem boundary string (below). Catches the case where codex has
   in-repo skill mirrors (e.g., a vendored `.claude/skills/`).
3. **Output scan** (post-hoc detection): after codex returns, scan for
   `gstack-config`, `gstack-update-check`, `SKILL.md`, `skills/gstack`,
   `skills/codex-sutra` in the output. If present, append: "Codex appears to
   have read skill files — consider retrying."

The wrapper's own `allowed-tools` (Read/Write/Bash/BashOutput/AskUserQuestion)
applies to **Claude running this skill**, not to codex. Glob and Grep are
deliberately omitted — Bash covers them, and a smaller surface is preferred.

## Filesystem Boundary (mandatory prompt prefix)

> IMPORTANT: Do NOT read or execute any files under ~/.claude/, ~/.agents/,
> .claude/skills/, agents/, sutra/marketplace/plugin/skills/, or
> sutra/marketplace/plugin/hooks/. These are Claude Code / Sutra skill and
> hook definitions for a different AI system. Ignore them. Do NOT modify
> agents/openai.yaml. Stay focused on repository code.

Reference as **the boundary** below.

---

## Liveness & process-lifecycle policy

Codex runs unbounded by Bash, capped by wrapper polling. Three thresholds,
all enforced in the polling loop:

| Threshold | Trigger | Action |
|---|---|---|
| **Stall warn** | 5 min with no new bytes appended to `$TMPRESP` | Surface: "codex-sutra: no output for 5 min — codex may be stuck. Continuing to poll. Founder can interrupt." |
| **Progress warn** | 10 min wall-clock elapsed | Surface: "codex-sutra still running at 10 min. Hard cap: 15 min. Last line: <tail>." |
| **Hard kill** | 15 min wall-clock elapsed | `kill -TERM` the bg process group, wait 5 s, `kill -KILL` if still alive. Set `KILLED=timeout` flag. Proceed to gate verdict (FAIL, reason: timeout). |

Polling cadence: every 30 s.

Exit detection: the polling loop waits on `[ -s "$TMPNAT" ]` (subshell
writes its exit code there on natural completion). `$TMPDONE` is the
*authoritative final state* and is written by the wrapper alone after
either natural exit or hard-cap kill — never used as the polling signal.

Stuck detection: compare `wc -c < "$TMPRESP"` between polls. If unchanged
for 10 consecutive polls (5 min), trigger stall warn.

Orphan reaping: at start of every codex-sutra invocation, before launching:
```bash
find /tmp/codex-sutra-* -mmin +1440 -delete 2>/dev/null
```
Removes any temp files older than 24 h from prior crashed sessions.

BashOutput truncation: if BashOutput reports output truncated, fall back
to direct `tail -c 8192 "$TMPRESP"` for the progress / final read. The
canonical record is always the on-disk `$TMPRESP`, not BashOutput buffer.

---

## Failure semantics — fail-closed

PROTO-019 gate is **fail-closed** for non-model failures. Every infra error
maps to `GATE: FAIL` with a `reason` field, written to gate-log.jsonl.

| Failure | Detection | Verdict | reason |
|---|---|---|---|
| codex binary missing | Step 0 `which codex` empty | (skill aborts; no verdict file) | n/a — surface install instructions |
| codex auth error | stderr contains `auth` | FAIL | `auth_error` |
| codex crash (non-zero exit) | `EXIT:N` in `$TMPDONE`, N != 0 | FAIL | `codex_exit_<N>` |
| Empty response | `$TMPRESP` size 0 after exit | FAIL | `empty_response` |
| Malformed output (no recognizable verdict markers in review mode) | grep for `[P1]`/`[P2]` returns nothing AND no "no findings" line | FAIL | `malformed_output` |
| Hard-cap timeout | wrapper-killed at 15 min | FAIL | `timeout` |
| Log-write failure | `printf >> gate-log.jsonl` exit non-zero | FAIL (and surface to founder) | `log_write_failed` |
| Session-id write failure | consult mode, write to `.context/codex-session-id` fails | ADVISORY (continue, log warning) | `session_persist_failed` |

`reason` field is appended to the gate-log.jsonl entry alongside `verdict`,
`findings`, `commit`. PROTO-019 callers read `reason` to differentiate
infra fail from real model fail.

---

## Step 0: Pre-flight

```bash
# Reap orphan temp files >24h old from prior crashed sessions
find /tmp/codex-sutra-* -mmin +1440 -delete 2>/dev/null || true
# Verify codex binary
CODEX_BIN=$(which codex 2>/dev/null || echo "")
[ -z "$CODEX_BIN" ] && { echo "NOT_FOUND"; exit 0; }
echo "FOUND: $CODEX_BIN"
```

If `NOT_FOUND`: stop. Tell founder: "Codex CLI not found. Install:
`npm install -g @openai/codex`. codex-sutra cannot run without it."
Do not write a verdict file (skill never started).

---

## Step 1: Mode detection

| Input | Mode | Step |
|---|---|---|
| `/codex-sutra review` (or `... <focus>`) | Review | 2A |
| `/codex-sutra challenge` (or `... <focus>`) | Challenge | 2B |
| `/codex-sutra consult <prompt>` or `/codex-sutra <prompt>` | Consult | 2C |
| `/codex-sutra design-review <path>` | Design Review | 2D |
| `/codex-sutra` no args, diff exists | AskUserQuestion: review / challenge / other | — |
| `/codex-sutra` no args, no diff | Ask: "What should codex-sutra look at?" | — |

**Design-review mode (2D)**: review a design document (skill spec, plan,
RFC). Different from Review mode (which targets a git diff) because the
input is a single file, not a diff. Used by codex-sutra itself for
self-review during fork iterations (this skill's v1/v2/v3 reviews used
this mode). Mirrors Consult mode's launcher but reads the target file
into the prompt with the standard P1/P2 finding format and verdict line.

`--xhigh` flag anywhere in input: strip it, set `model_reasoning_effort="xhigh"`.
Before invoking xhigh, surface a cost warning: "xhigh uses ~23x tokens of high
and can hang 50+ min on large context (OpenAI #8545, #8402, #6931). Continue?"
AskUserQuestion: A) yes proceed B) cancel C) downgrade to high.

---

## Per-mode reasoning effort defaults

| Mode | Default | Reason |
|---|---|---|
| Review (2A) | `high` | Bounded by diff; needs thoroughness |
| Challenge (2B) | `high` | Adversarial; bounded by diff |
| Consult (2C) | `medium` | Large context (plans); needs speed |
| Design-review (2D) | `medium` | Document-bounded; speed > max reasoning |

Override via `--xhigh` (with cost warning) or via `-m <model>` passthrough.

---

## Step 2A: Review

Run `codex review` against the current branch diff. Use the launcher
pattern below. Output contract:

**Review output contract** (machine-readable, consumed by PROTO-019):
```
GATE: PASS|FAIL
findings: <int>           # count of [P1] markers
advisories: <int>         # count of [P2] markers
tokens: <int>|unknown
reason: <string>          # only present if GATE=FAIL; one of the values in fail-closed table
commit: <short-sha>
```
Always write this contract to gate-log.jsonl regardless of human-facing
output. PROTO-019 gate hook reads JSONL, not the human-facing block.

Review-specific codex args:
```bash
codex review "<the boundary>\n\n<focus, if any>" \
  --base "$BASE" \
  -c 'model_reasoning_effort="high"' \
  --enable web_search_cached
```
where `$BASE` is `git symbolic-ref --short refs/remotes/origin/HEAD | sed s@^origin/@@`,
defaulting to `main` if no remote HEAD.

P1/P2 gate:
- Output contains `[P1]` → **GATE: FAIL**, `findings = count`.
- Otherwise → **GATE: PASS**, `findings = 0`.

---

## Step 2B: Challenge

Adversarial mode — codex looks for ways the diff fails in production.

Default prompt (no focus): the boundary + "Review the changes on this
branch against the base branch. Run `git diff origin/<base>` to see the
diff. Find ways this code will fail in production. Think like an attacker
and a chaos engineer. Be adversarial. No compliments — just the problems."

With focus (e.g. `/codex-sutra challenge security`): same prompt + a
"Focus specifically on SECURITY" line.

Codex args:
```bash
codex exec "<prompt>" -C "$REPO_ROOT" -s read-only \
  -c 'model_reasoning_effort="high"' \
  --enable web_search_cached --json
```

**Output contract**:
```
mode: challenge
focus: <string>|none      # if user passed `/codex-sutra challenge security`
findings: <int>           # count of [Pn] markers in codex output
tokens: <int>|unknown
commit: <short-sha>
```
Stopping criteria: codex's own turn.completed event. No iterative loops.
Findings format MUST be `[P1]`/`[P2]` — same as review — so callers can
union challenge + review results without parser branching.

---

## Step 2C: Consult

Free-form Q&A with session continuity via `.context/codex-session-id`.

1. Check existing session: `cat .context/codex-session-id || echo NO_SESSION`.
   If present, AskUserQuestion: A) continue B) start fresh.
2. Plan-file detection (when founder said "review my plan" or `/codex-sutra`
   no-args): scan `~/.claude/plans/*.md` for project-scoped plan via
   `xargs grep -l "$(basename $(pwd))"`. Codex is sandboxed to repo root —
   read the plan file yourself and embed contents in the prompt; never
   reference the path.
3. Build prompt: boundary + persona ("brutally honest technical reviewer")
   + embedded plan (or free-form question) + repo-relative source paths
   referenced in the plan.
4. Launch via the launcher pattern with codex args:
   - New session: `codex exec "<prompt>" -C "$REPO_ROOT" -s read-only -c 'model_reasoning_effort="medium"' --enable web_search_cached --json`
   - Resume: `codex exec resume <session-id> "<prompt>" ...` (same flags)
5. Capture session id from the `thread.started` JSONL event. Persist to
   `.context/codex-session-id`.
6. Present codex output verbatim inside `CODEX-SUTRA SAYS (consult)` block.
   Append "Note: Claude disagrees on X because Y." after the block if
   warranted — never inside.

**Session limitations (v1):**
- Single active consult per repo. `.context/codex-session-id` is per-repo,
  last-writer-wins. Concurrent consults in the same repo will clobber.
- No cross-branch isolation. Switching branches mid-conversation can
  surface stale session context. Document: "If you switch branches,
  start a new consult."
- Stale-session recovery: if `codex exec resume <id>` fails, the wrapper
  deletes `.context/codex-session-id` and offers to start fresh.
- File path is repo-local (`.context/codex-session-id`), so worktrees
  get their own session. `.gitignore` `.context/codex-session-id` to
  avoid cross-developer contamination.

v2 (future): file-locking + session registry for concurrent consults.

---

## Step 2D: Design Review

Review a single design document (skill spec, plan, RFC). Used for
self-review during fork iterations and any design-review-of-document use
case.

1. Read the target file at the path passed in: `cat <path>`.
2. Build prompt: the boundary + "You are a brutally honest technical
   reviewer. Mark each finding [P1] (blocker) or [P2] (advisory). End with:
   `CODEX-VERDICT: PASS|ADVISORY|CHANGES-REQUIRED`. Be decisive — only true
   blockers as P1." + the file content embedded.
3. Launch via the launcher pattern with codex args:
   `codex exec "<prompt>" -C "$REPO_ROOT" -s read-only -c 'model_reasoning_effort="medium"' --enable web_search_cached --json </dev/null`
4. Parse the final `CODEX-VERDICT:` line. Map to gate-log entry with
   `mode=design-review`, `verdict=<value>`, `findings=<P1 count>`,
   `advisories=<P2 count>`.
5. If invoked under an active PROTO-019 directive, write a verdict file
   to `.enforcement/codex-reviews/<date>-<slug>.md` with `DIRECTIVE-ID:`
   and `CODEX-VERDICT:` headers so the directive gate can clear.

---

## The launcher pattern (used by all four modes)

**Single-writer rule.** The wrapper owns the final disposition. The bg
subshell writes only `$TMPNAT` (its own exit code on graceful exit). The
wrapper writes `$TMPDONE` (the authoritative final state). This eliminates
races where two writers could clobber each other.

**Process-group rule.** Codex runs in its own process group via `setsid`
(or python `os.setsid()` fallback on macOS without `setsid`). On hard-cap
timeout the wrapper signals the *entire group* with `kill -TERM -<pgid>`
so codex and any children terminate together. Closes the hole where
killing only the subshell PID could leave codex running past the cap.

**Stdin rule.** Codex always launched with `</dev/null`. Without it,
`codex exec` waits on stdin and hangs forever even when the prompt is
provided as argv. (Discovered the hard way during this skill's own
v2 design review iteration.)

```bash
# Reap orphans (>24 h)
find /tmp/codex-sutra-* -mmin +1440 -delete 2>/dev/null || true
TS=$(date +%s)
TMPRESP=/tmp/codex-sutra-resp.$$.${TS}.txt
TMPERR=/tmp/codex-sutra-err.$$.${TS}.txt
TMPDONE=/tmp/codex-sutra-done.$$.${TS}            # WRAPPER WRITES ONLY
TMPNAT=/tmp/codex-sutra-natural.$$.${TS}          # SUBSHELL WRITES ONLY

# Launch codex in its own process group. Prefer setsid; fall back to python.
if command -v setsid >/dev/null 2>&1; then
  setsid bash -c "codex \"\$@\" </dev/null > \"$TMPRESP\" 2> \"$TMPERR\"; echo \$? > \"$TMPNAT\"" _ <args> &
else
  python3 -c "
import os, sys, subprocess
os.setsid()
r = subprocess.run(['codex'] + sys.argv[1:],
                   stdin=subprocess.DEVNULL,
                   stdout=open('$TMPRESP','w'),
                   stderr=open('$TMPERR','w'))
open('$TMPNAT','w').write(str(r.returncode))
" <args> &
fi
CODEX_PID=$!
PGID=$CODEX_PID  # session leader: pgid == pid

START=$(date +%s)
LAST_BYTES=0
STALL_POLLS=0
KILLED=""

while [ ! -s "$TMPNAT" ] && [ -z "$KILLED" ]; do
  sleep 30
  NOW=$(date +%s); ELAPSED=$((NOW-START))
  BYTES=$(wc -c < "$TMPRESP" 2>/dev/null || echo 0)
  if [ "$BYTES" = "$LAST_BYTES" ]; then STALL_POLLS=$((STALL_POLLS+1));
  else STALL_POLLS=0; LAST_BYTES=$BYTES; fi
  # Stall warn at 5 min no-progress (10 polls of 30 s)
  [ $STALL_POLLS -eq 10 ] && echo "codex-sutra: no output for 5 min — may be stuck."
  # Progress warn at 10 min wall (one-shot window)
  [ $ELAPSED -ge 600 ] && [ $ELAPSED -lt 630 ] && echo "codex-sutra still running at 10 min. Hard cap: 15 min."
  # Hard kill at 15 min wall — kill the whole process group
  if [ $ELAPSED -ge 900 ]; then
    kill -TERM "-$PGID" 2>/dev/null
    sleep 5
    kill -KILL "-$PGID" 2>/dev/null
    sleep 2  # let OS reap; subshell's $TMPNAT write (if any) is irrelevant
    KILLED=timeout
    break
  fi
done

# WRAPPER is the single writer of TMPDONE (authoritative final state).
if [ "$KILLED" = "timeout" ]; then
  echo "EXIT:124 REASON:timeout" > "$TMPDONE"
elif [ -s "$TMPNAT" ]; then
  NAT_EXIT=$(cat "$TMPNAT")
  if [ "$NAT_EXIT" = "0" ]; then
    echo "EXIT:0 REASON:natural" > "$TMPDONE"
  else
    echo "EXIT:$NAT_EXIT REASON:codex_exit_$NAT_EXIT" > "$TMPDONE"
  fi
else
  echo "EXIT:255 REASON:unknown" > "$TMPDONE"
fi
```

Then per-mode parses `$TMPRESP` / `$TMPERR`, builds the verdict block, and
appends to gate-log.jsonl (with the durability fallback below).

---

## Failure durability — three channels

PROTO-019 hooks consume codex-sutra results. If the primary channel fails,
the gate must still be observable; otherwise fail-closed becomes silent
fail-open from the hook's POV. Three channels in priority order:

1. **Primary**: append JSONL entry to `.enforcement/codex-reviews/gate-log.jsonl`.
2. **Fallback file** (if primary fails): write the same JSON to
   `/tmp/codex-sutra-fail-<directive_id>-<ts>.json`. PROTO-019 hooks scan
   this glob in addition to the main log.
3. **Stderr beacon** (always emitted regardless of file-write success):
   ```
   CODEX-SUTRA-RESULT verdict=FAIL reason=log_write_failed directive=<id> commit=<sha>
   ```
   Hook authors can grep this from the skill's stderr stream when both
   filesystem channels are unwritable. The beacon is the last-resort
   durable signal — survives full-disk, permission errors, missing dirs.

Skill exit code mirrors the verdict:
- PASS / ADVISORY → exit 0
- CHANGES-REQUIRED / FAIL → exit 1
- Hard-cap timeout → exit 124

PROTO-019 hooks treat **non-zero exit + no readable verdict file** as
FAIL with `reason=infra_silent`. The skill must never exit 0 without
emitting a parseable result on at least one of the three channels.

---

## gate-log.jsonl schema

One JSON object per line. POSIX append (`>>`) is atomic for writes <PIPE_BUF
(4096 bytes on Linux/macOS). Every entry stays well under that.

```json
{
  "skill": "codex-sutra",
  "mode": "review|challenge|consult|design-review",
  "ts": "2026-04-28T03:00:00Z",
  "verdict": "PASS|FAIL|ADVISORY|CHANGES-REQUIRED",
  "directive_id": <int|null>,
  "findings": <int>,
  "advisories": <int>,
  "tokens": <int|null>,
  "reason": "<string|null>",
  "commit": "<short-sha|null>",
  "wall_seconds": <int>,
  "killed": "timeout|null"
}
```

**Rotation (v1, single-writer assumption)**: at start of each codex-sutra
invocation, if `<repo>/.enforcement/codex-reviews/gate-log.jsonl > 10 MB`,
attempt rotate. All paths below are absolute (rooted at repo top via
`$(git rev-parse --show-toplevel)`), so the snippet works regardless of
the wrapper's current directory.

```bash
REPO=$(git rev-parse --show-toplevel)
LOG="$REPO/.enforcement/codex-reviews/gate-log.jsonl"
LOCK="$REPO/.enforcement/codex-reviews/.rotate.lock"
ROTATED="$REPO/.enforcement/codex-reviews/gate-log-$(date -u +%Y-%m-%d).jsonl"

if command -v flock >/dev/null 2>&1; then
  flock -w 5 "$LOCK" sh -c "
    [ -f \"$LOG\" ] && [ \"\$(wc -c < \"$LOG\")\" -gt 10485760 ] && mv \"$LOG\" \"$ROTATED\"
  " 2>/dev/null || true
else
  # macOS / minimal env: mkdir-based advisory locking
  if mkdir "$LOCK" 2>/dev/null; then
    trap 'rmdir "$LOCK"' EXIT
    [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 10485760 ] && mv "$LOG" "$ROTATED"
  fi
fi
```
If lock cannot be acquired in 5 s, skip rotation this turn — entries
continue appending to the current file. Worst case is a slightly oversized
log; never lost entries.

**Concurrent appends**: POSIX guarantees atomic append for writes <PIPE_BUF
(4096 bytes). Every entry stays well under that. If interleaving is ever
observed in practice, upgrade to `flock` on append; not expected for v1.

---

## Rollout policy (operational, not skill behavior)

This skill ships in the Sutra plugin, but rollout to active codex-by-codex
review path is staged:

| Tier | Cohort | Window | Gate to advance |
|---|---|---|---|
| T2 (owned) | DayFlow, Billu, Paisa, PPR, Maze | Week 1 | Zero infra-fail verdicts in gate-log.jsonl |
| T3 (projects) | Testlify, Dharmik | Week 2 | Same gate + founder sign-off |
| T4 (Sutra users / fleet) | External adopters | Week 3+ | Same gate + announcement in feedback channel |

Skill is identical across tiers — only PROTO-019 hook activation differs.
Gate criteria observable in `.enforcement/codex-reviews/gate-log.jsonl`
(filter by `mode` and `reason`).

---

## Upstream sync

Forked from gstack /codex skill v1.0.0 (file:
`~/.claude/skills/gstack/codex/SKILL.md`, observed 2026-04-28).

Sync cadence: **quarterly review** of upstream diff. Process:
```bash
diff -u ~/.claude/skills/gstack/codex/SKILL.md \
        sutra/marketplace/plugin/skills/codex-sutra/SKILL.md
```
Port relevant gstack changes manually. Bump codex-sutra version. Document
ported items in CHANGELOG.

Divergence is expected (different log path, different cap, different boundary
list). Sync is for upstream improvements, not lockstep.

---

## Important rules

- **Hard cap 15 min.** Wrapper-enforced via `kill -TERM -<pgid>` after 900 s.
- **Read-only codex.** Always `-s read-only`. Wrapper writes only to
  `.enforcement/codex-reviews/`, `.context/codex-session-id`, and `/tmp/codex-sutra-*`.
- **Verbatim presentation.** Codex output goes inside `CODEX-SUTRA SAYS`
  block unmodified. Synthesis after, never inside.
- **Boundary always first.** Even with no founder focus.
- **Fail-closed.** Every non-model failure path maps to GATE: FAIL with
  a structured `reason`. PROTO-019 callers branch on `reason`.
- **Never invoke gstack `/codex` from within codex-sutra.** Codex-sutra IS
  the codex primitive going forward; calling gstack /codex would re-introduce
  the 5-min cap and bypass our gate-log path.
