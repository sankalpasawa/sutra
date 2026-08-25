# System Map

**status**: scaffold (materialized by /core:start, profile=company)

What exists in this repo and where. Update when structure changes.

| Path | What it is |
|------|------------|
| os/ | Operating layer: backlog, directions, departments, state |
| os/departments/ | Department registry + per-department docs |
| os/state/ | Machine-written operational state (ledgers, logs) |
| .githooks/ | Test gates installed by /core:start (pre-commit, pre-push) |

provenance: Sutra plugin template (templates/os/SYSTEM-MAP.md), materialized by /core:start
