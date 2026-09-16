**Status**: recorded lib, 0 defect cases, 2026-09-13

# Known defects — lib family

No known defects in the recorded cases. Scope: 27 recorded cases. No record pairs
exit 2 with an empty stderr; no recorded stderr contains `command not found`,
`syntax error`, `unbound variable` or `No such file`; no case records all-127.

| case | script | observed | why it is a defect | script:line |
| --- | --- | --- | --- | --- |
| (none) | - | - | no recorded case matched the defect criteria | - |

## Retired entry — the env-splitting all-127 recording

The case that pins `CASCADE_ACK_REASON=fixture override` used to record
`exit 127` / `env: override: No such file or directory` for every slot: the
harness word-split the case `env` file, so `env` exec'd `override` and the
audited-override path was never reached. Fixed in `sutra-charcap` v1.6.0
(`run_in_env`, one line = one argument, README s10) and re-recorded.

| item | value |
|---|---|
| now recorded | `cascade-check.sh` exit 0, with the case's own `.fx` |
| why one slot, not six | the lib family is mixed-event; since v1.6.0 a case runs only the registrations of ITS OWN event (README s8), so this PreToolUse case selects the PreToolUse caller alone |
| why the row is gone | the first column of this table is the ONLY all-127 whitelist `record` reads (`known_defect`); leaving the case named there would keep the s5 guard disarmed for a case that is healthy again |
| re-check | `sutra-charcap record --family lib` exits 0 with no `REFUSED` line |

provenance: sutra-charcap record, W0a corpus; defect rows retired 2026-09-13
after the v1.6.0 env-vector fix, re-recorded with v1.6.1.
