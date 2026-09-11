# App manifest migrations (module.json)

How an app written under an older `schema` keeps working, and what changes on disk when.

| Field | Value |
|---|---|
| **status** | ACTIVE — schema 1 → 2 (program step 23) |
| **updated** | 2026-09-11 |
| Schema of record | `schemas/app-manifest.schema.json` |
| Reader | `modules_api._normalize` (read-time), `modules_api.apply_action` / `create_module` (write-time) |
| Fixtures | `schemas/fixtures/schema1-minimal.json`, `schemas/fixtures/schema1-unknown-stale.json` |

## <a id="rules"></a>Rules

| # | Rule | Why |
|---|---|---|
| M-1 | Migration is read-time normalization only: a schema-1 file is read as if it were schema 2 with `department: null` and `publish: null` | the folder is the app; a read must never write |
| M-2 | Write-back happens on the NEXT mutation of that app (any `apply_action`), and patches the raw file: bump `schema` to 2, keep every other field | codex 2026-09-11 P1: the normalized UI row is a projection, never the durable record |
| M-3 | Never a bulk rewrite of `~/.sutra-ui/modules/` | a startup that rewrites every folder is a startup that can corrupt every folder |
| M-4 | Unknown fields are preserved verbatim on read and on write-back | ADR-039: forward compatibility for `publish` and for fields later schemas add |
| M-5 | A stale or unknown `department.ref` reads as Unassigned; it is NOT rewritten on write-back | the operator moves it on purpose (Move in the chat); the reader never guesses |
| M-6 | An unparsable file reads as a "building…" row (folder exists, manifest invalid), never as a missing app | program step 54, PRD §Resilience |
| M-7 | Schema 1 is department-capable: the v1.1 server (2026-09-11) writes `schema: 1` WITH `department` and the reader accepts it. Schema 2 differs only by `publish` and by `marketplace` in `origin.created_by`. From program step 55 on, `create_module` writes `schema: 2` and every write-back bumps 1 → 2; until then a schema-1 file with a department is valid, not a defect | codex R1b P1/P6: registry entries require `manifest_schema: 2`, so export (step 59) refuses a schema-1 folder until its next mutation has bumped it — never a bulk rewrite |

## <a id="1to2"></a>1 → 2

| Field | Schema 1 | Schema 2 |
|---|---|---|
| `schema` | 1 | 2 |
| `department` | absent (v1.0) or `{ref}` (v1.1 writes) | `{ref}` or `null` |
| `publish` | absent | `{…}` or `null` |
| `origin.created_by` | app · shadow · chat · disk · system | adds `marketplace` |
| everything else | unchanged | unchanged |

## <a id="tests"></a>Tests (program step 46)

| Fixture | Expected read |
|---|---|
| `schema1-minimal.json` | row with `department: null`, `publish: null`, no warning |
| `schema1-unknown-stale.json` | row with `department: null` (stale ref), `publish: null`, the unknown field `colour` still present in the raw file after a write-back |

---
provenance: authored 2026-09-11 (session c0a2923c, atom a-c0a2923c-11) from ADR-039 and the codex pre-consult P1/P4 (`.tmp/modules-review/codex-c-pre.out`); program step 23.
