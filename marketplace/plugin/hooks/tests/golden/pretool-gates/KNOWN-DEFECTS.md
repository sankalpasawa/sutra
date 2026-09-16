**Status**: recorded pretool-gates, 4 cases, 2026-09-11

# Known defects — pretool-gates family

Scope: 52 recorded cases; 4 cases carry recorded behaviour that is a known bug (5 script records).

| case | script | observed | why it is a defect | script:line |
| --- | --- | --- | --- | --- |
| gate-enforce-boundaries | enforce-boundaries.sh | exit 2, stderr empty (0 bytes); block text on stdout | A blocking exit with no stderr gives the caller no reason. The `BLOCKED: Cannot determine active role` line is echoed to stdout, which the PreToolUse contract does not surface on a deny. | enforce-boundaries.sh:41 (echo lacks `>&2`), :43 (exit 2) |
| gate-rtk-rewrite | rtk-auto-rewrite.sh | exit 2, stderr empty (0 bytes); block text on stdout | Same shape: the whole `BLOCKED — RTK air-tight gate` block, including the override and kill-switch hints, goes to stdout, so a denied Bash call shows an empty reason. | rtk-auto-rewrite.sh:74 (echo lacks `>&2`), :86 (exit 2) |
| missing-session-id | flow-gate.sh | exit 2 on degenerate env (`CLAUDE_CODE_SESSION_ID` unset) although every flow marker exists on disk under the fixture session dir | The header promises a nudge, not a block, when marker state cannot be established; here the input, not the discipline, is degenerate, and the gate still denies. | flow-gate.sh:20 ("If either marker is missing, nudge -- do not block") vs :194 (exit 2) |
| missing-session-id | flow-gate.sh~1 | exit 2, same stderr as the first invocation | Second invocation repeats the same fail-closed-on-missing-env behaviour; both records freeze it. | flow-gate.sh:20 vs :194 |
| no-markers | flow-gate.sh | exit 2, `FLOW-GATE (HARD): construct work requires classify + resolve first.` | Recorded behaviour contradicts the script's own header contract for the missing-marker case; header line 8 and header line 20 disagree, and the record pins the blocking branch. | flow-gate.sh:20 vs :8, :194 |

Not treated as defects here: `gate-depth-missing` / `no-markers` exits from `depth-marker-pretool.sh` (the fixture sets `profile: company`, which the header documents as HARD at depth-marker-pretool.sh:7) and the `empty-input` / `malformed-json` cases, which all record exit 0.

provenance: sutra-charcap record, W0a corpus, 2026-09-11
