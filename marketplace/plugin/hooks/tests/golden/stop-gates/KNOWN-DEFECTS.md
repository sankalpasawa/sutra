**Status**: recorded stop-gates, 0 defect cases, 2026-09-13

# Known defects — stop-gates family

No known defects in the recorded cases. Scope: 30 recorded cases. No record pairs
exit 2 with an empty stderr; no recorded stderr contains `command not found`,
`syntax error`, `unbound variable` or `No such file`; no case records all-127.

| case | script | observed | why it is a defect | script:line |
| --- | --- | --- | --- | --- |
| (none) | - | - | no recorded case matched the defect criteria | - |

## Retired entry — the env-splitting all-127 recording

The case that pins a multi-word `CLAUDE_TRANSCRIPT`
(`read holding/a.md holding/b.md ...`) used to record `exit 127` /
`env: holding/a.md: No such file or directory` for all six Stop gates: the
harness word-split the case `env` file, so `env` exec'd `holding/a.md` and no
gate ran. Fixed in `sutra-charcap` v1.6.0 (`run_in_env`, one line = one
argument, README s10) and re-recorded.

| item | value |
|---|---|
| now recorded | all six gates exit 0, `placement-stop-check.sh` writes 190 bytes of stderr, three gates carry a non-empty `.fx` |
| why the row is gone | the first column of this table is the ONLY all-127 whitelist `record` reads (`known_defect`); leaving the case named there would keep the s5 guard disarmed for a case that is healthy again |
| re-check | `sutra-charcap record --family stop-gates` exits 0 with no `REFUSED` line |

provenance: sutra-charcap record, W0a corpus; defect rows retired 2026-09-13
after the v1.6.0 env-vector fix, re-recorded with v1.6.1.
