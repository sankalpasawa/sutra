---
issue: 38
title: "[feedback v2.8.5] from plugin"
author: vinitharmalkar
state: CLOSED
created: 2026-04-28T14:48:32Z
updated: 2026-04-28T15:23:10Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/38
comments: [{'id': 'IC_kwDOR5MNCs8AAAABAnyHnQ', 'author': {'login': 'sankalpasawa'}, 'authorAssociation': 'OWNER', 'body': 'Fixed in **v2.8.11** (commit `92c2de3`).\n\nThanks for the precise repro + Vinit-ranked hypotheses. Shipped all three of your recommendations:\n\n**A. File-execution form replaces stdin-fed heredocs.**\nAll 4 stdin-fed `python3 - <<PY ... PY` heredocs (2 in `scripts/start.sh`, 2 in `scripts/onboard.sh`) moved into a real `.py` file: `scripts/_sutra_project_lib.py` with subcommands `patch-profile`, `write-onboard`, `stamp-identity`, `banner`. File-execution form is much less likely to be flagged by sandbox/EDR than stdin-fed code.\n\n**B. SIGKILL diagnostic.**\nNew `sutra_run_python` wrapper in `start.sh` catches exit 137 and prints what to check (`ps -ef | grep -iE crowdstrike/jamf/sentinel`, `codesign -d --verbose=4 \\$(which python3)`), where to report, and confirms that `sutra-project.json` was NOT corrupted (because of fix C below).\n\n**C. Atomic writes.**\nAll file mutations in `_sutra_project_lib.py` use `tempfile + os.replace`. A SIGKILL between create-temp and rename leaves the prior valid file content untouched — no more 0-byte corruption regardless of whether anything still kills the process.\n\n**Inline `python3 -c "..."` not migrated** — argv-form `-c` is not affected by your repro per your analysis (only stdin-fed heredocs received SIGKILL). If we hear of `-c` form also dying on some setups, we migrate those too.\n\nAcceptance: 19/19 targeted tests pass — syntax, all subcommands functional with expected exit codes, no leftover tempfiles after normal runs, 3 adjacent unit suites green.\n\nFor @abhishekshah specifically: please run `/core:update` to v2.8.11, then `/core:start` again. If the SIGKILL still happens, the diagnostic will print actionable hints. If you keep seeing exit 137 even after the fix, please re-open with the diagnostic output — that means `python3 file.py` is also being killed, not just stdin form, which is a different (rarer) profile we should chase next.\n\nVinit — sincere thanks. Your three-recommendation breakdown was the most actionable reproduction I have ever received in this issue tracker. The atomic-write protection is a permanent improvement regardless of whether the EDR fix lands.', 'createdAt': '2026-04-28T15:23:08Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/38#issuecomment-4336682909', 'viewerDidAuthor': True}]
---

# #38 [feedback v2.8.5] from plugin

**Author:** vinitharmalkar  |  **State:** CLOSED  |  **Labels:** —
**Created:** 2026-04-28T14:48:32Z  |  **Updated:** 2026-04-28T15:23:10Z
**URL:** https://github.com/sankalpasawa/sutra/issues/38

---

## Summary

Sutra `2.8.10` `/core:start` exits **137** (SIGKILL) on macOS. The two `python3` heredoc subprocesses inside `scripts/start.sh` are killed by signal 9 mid-execution. Bash code paths in the same script complete normally — only the inline `python3 - <<PY` heredocs die. Result: a **0-byte `sutra-project.json`** and a partial governance block in `~/.claude/CLAUDE.md`.

> **Note on provenance:** This report is filed by a Claude Code session on behalf of a user. The failing machine runs **2.8.10** as user `abhishekshah`. The session filing this issue is on a *different* Mac running **2.8.5** as user `vinit`, where `/core:start` works fine. Findings below combine the failing-machine logs the user pasted with positive-control checks I ran locally on 2.8.5.

## Reproduction (failing machine)

- **OS:** macOS (Darwin)
- **Sutra version:** `2.8.10`
- **Plugin path:** `<HOME>/.claude/plugins/cache/sutra/core/2.8.10/`
- **Trigger:** `/core:start` invoked inside Claude Code

## Observed errors

```
line 124: 66020 Killed: 9  python3 - "$PROFILE" "$TELEMETRY_DEFAULT" <<'PY' ...
line 300: 66031 Killed: 9  python3 <<PY ...
```

Both subprocesses receive `SIGKILL` (signal 9) — the script cannot intercept this; the kill is external.

## Resulting state

| Artifact | State after failed run |
|---|---|
| `~/.claude/sutra-project.json` | Exists, **0 bytes** |
| `~/.claude/CLAUDE.md` governance block | Partially written |
| `~/.sutra/metrics-queue.jsonl` | Initialized OK |
| Subsequent `/core:start` runs | Same SIGKILL |

The 0-byte JSON is explained by the heredoc body itself:

```python
# scripts/start.sh — first python3 heredoc
d = json.load(open(p))
d['profile'] = profile
d['telemetry_optin'] = telemetry_default
open(p, 'w').write(json.dumps(d, indent=2))   # ← truncates first, writes second
```

If `python3` is killed *between* `open(p, 'w')` (which truncates) and `.write(...)` (which fills), the file ends 0 bytes. The second heredoc (success banner) then fails too — partly because the now-empty JSON would throw on `json.load`, but more likely the same root cause kills it.

## Positive control on 2.8.5 (this filing session's Mac)

| Check | Result |
|---|---|
| `python3 - <<'PY' ... PY` inside Claude Code's bash | Exit **0**, clean execution |
| `/core:start` on 2.8.5 | Success banner, valid JSON written |
| Same plugin architecture (heredoc pattern at lines 110, 254) | No SIGKILL |

So the heredoc pattern *itself* is not universally lethal under Claude Code — something specific to **2.8.10** OR **a hook installed by a prior 2.8.10 run** is implicated.

## Hypotheses (ranked)

### 1. A hook installed by `2.8.10` self-blocks subsequent runs

Most likely. If `2.8.10` installs a `PreToolUse` hook that intercepts `python3` (e.g. for telemetry capture, depth-marker enforcement, or sandbox checks), the **first** run completes the install of that hook, but the hook then kills `python3` invocations from later runs — including subsequent `/core:start` calls. The fact that bash code paths survive but `python3` dies fits a hook that filters on interpreter or argv.

**Asks for the maintainer:**
- What changed in `start.sh` (and any installed hooks under `~/.claude/settings.json` or `~/.claude/hooks/`) between `2.8.5` → `2.8.10`?
- Does `2.8.10` install any `PreToolUse` / `PreBash` hook that targets `python3` or pattern-matches heredoc bodies?

### 2. macOS sandbox-exec under Claude Code v2.8.10's launcher

Plausible. If 2.8.10 changed how it's launched (e.g. via a different `exec` shim or a child shell with stricter sandbox profile), nested heredoc-form `python3` is exactly the pattern that gets denied. Bash file edits go through the parent shell's allowed-syscalls, but a freshly-execve'd `python3` may not.

### 3. Endpoint Security / Gatekeeper

Less likely (would page widely), but possible if 2.8.10's `python3` invocations carry an unsigned attribute the parent shell's didn't.

## Suggested fixes (ordered by surface area)

### A. Replace heredocs with file-execution form

The heredoc pattern is the kill target. Both invocations are short enough to live in a sibling `.py` file:

```bash
# Before
python3 - "$PROFILE" "$TELEMETRY_DEFAULT" <<'PY'
import json, sys
...
PY

# After
python3 "$PLUGIN_ROOT/scripts/_patch_project_json.py" "$PROFILE" "$TELEMETRY_DEFAULT"
```

This sidesteps **all three** hypothesized killers — sandbox, hooks that filter on argv `-`, and endpoint-security heuristics that flag stdin-fed code.

### B. Add SIGKILL retry/diagnostic

Wrap `python3` calls with:

```bash
if ! python3 ... ; then
  rc=$?
  if [ $rc -eq 137 ]; then
    echo "Sutra: python3 was SIGKILLed — likely sandbox or hook interference."
    echo "Workaround: re-run from Terminal.app, or set SUTRA_NO_PYTHON=1 to use a bash-only fallback."
    exit 137
  fi
fi
```

### C. Atomic JSON writes (`tmp + rename`)

Even if the kill keeps happening, prevent the corruption-then-empty-file failure mode:

```python
import json, os, tempfile
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), prefix='.sutra-', suffix='.json')
with os.fdopen(fd, 'w') as f:
    f.write(json.dumps(d, indent=2))
os.replace(tmp, p)
```

So if the python3 dies mid-write, `sutra-project.json` keeps its prior valid content rather than turning into a 0-byte file.

### D. Surface a clearer recovery path

Today's failure leaves the user with a 0-byte JSON, a half-written governance block, and no obvious next step. A `sutra repair` subcommand (or an automatic check at the top of `start.sh` for "JSON exists but is 0 bytes → restore from `.bak` or recreate from template") would let the user self-recover without filing an issue.

## Information needed from the maintainer

1. Diff of `scripts/start.sh` between `2.8.5` and `2.8.10`
2. List of hooks `2.8.10` installs (paths under `~/.claude/`)
3. Whether `2.8.10` was tested under Claude Code's bash sandbox specifically (vs. plain Terminal)
4. Any known interactions between Sutra hooks and `python3` interpreter launches

## Constraint to note

The reporting user has access to **only this one Mac**. Recommendations like "run on a different machine" or "try it on another laptop" aren't actionable. In-session bypasses (Claude Code `dangerouslyDisableSandbox`, hook disable via file rename, JSON reconstruction via `Write` tool) are the only available remediation paths until 2.8.10 ships a fix.

---

*Filed via `gh issue create` from a Claude Code session. Happy to run additional diagnostics on the failing machine if you can share what to capture.*
