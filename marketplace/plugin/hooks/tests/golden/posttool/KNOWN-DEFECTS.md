**Status**: recorded posttool, 0 cases, 2026-09-11

# Known defects — posttool family

No known defects found in the recorded cases. Scope: 26 recorded cases. `empty-input` and `malformed-json` record exit 0; no recorded stderr contains `command not found`, `syntax error`, `unbound variable` or `No such file`; no record pairs exit 2 with an empty stderr.

| case | script | observed | why it is a defect | script:line |
| --- | --- | --- | --- | --- |
| (none) | - | - | no recorded case matched the defect criteria | - |

## Environment dependency the sandbox cannot pin

`agent-completion-check.sh` reads `/tmp/claude-agent-*` and `/tmp/claude-tasks`
by absolute path, outside the fresh root and outside the per-run `TMPDIR`. On
the machine that recorded this corpus neither exists, so every case takes the
early-exit path. On a machine where a Claude session has created them the
recording would differ, and re-recording there is the only honest fix - the
corpus cannot normalise a path the hook hardcodes.

| item | value |
|---|---|
| script:line | `hooks/agent-completion-check.sh:12`, `:40` |
| pinned by fixtures | no - the path is absolute, not `$TMPDIR` |
| state at record time | `/tmp/claude-tasks` absent, no `/tmp/claude-agent-*` |
| effect if present | the hook proceeds past the early exit; stdout, exit and `.fx` may all change |

provenance: sutra-charcap record, W0a corpus, 2026-09-11; environment
dependency added 2026-09-12 during the round-1 charcap fix.
