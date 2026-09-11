# Threat map -- every APPS-THREATS.md row against a kit check

`test_kit_threats.py` parses `APPS-THREATS.md` (the six STRIDE rows and X-1..X-10) and requires every row id below to name a check id from `angles/*.json` or a stated non-coverage. An unmapped row fails the test.

| Field | Value |
|---|---|
| **status** | ACTIVE -- v1 |
| **updated** | 2026-09-12 |

## STRIDE rows

| Row | Kit coverage | Check ids or non-coverage |
|---|---|---|
| Spoofing | a builder-made app cannot claim another identity: `id` equals the folder name and the stamp is server-written | C17, C20; registry sha256 and signature stay with import (ADR-039, ADR-041) |
| Tampering | the folder holds only the kind's allowed files, nothing outside it is referenced | C18, C26 |
| Repudiation | the chat never writes events; the server appends them | C18 (no hand-written event log); events remain server-side (APPS-EVENTS.md) |
| Information disclosure | a page has no network and no storage; no secret in any file | C25, C28, C35 |
| Denial of service | size caps on members, files and total | C19 |
| Elevation of privilege | instructions cannot order commands the owner did not write down; a link opens only a live screen; the manifest is data | C30, C32, C17 |

## Safe-extraction contract

| Row | Kit coverage | Check ids or non-coverage |
|---|---|---|
| X-1 | non-coverage: import quarantine and sha256 verification are the installer's (`modules_pkg.import_app`), not a folder check | non-coverage (installer) |
| X-2 | the manifest validates and `id` equals the folder name | C17 |
| X-3 | only whitelisted members plus the local record are present | C18 |
| X-4 | non-coverage: path normalization inside a tarball is the installer's | non-coverage (installer) |
| X-5 | the caps are read from `modules_pkg` and applied to the folder | C19 |
| X-6 | non-coverage: the two-phase replace is the installer's | non-coverage (installer) |
| X-7 | non-coverage: the atomic rename is the installer's | non-coverage (installer) |
| X-8 | non-coverage: `app.imported` is written by the installer; the kit only forbids hand-written event files | non-coverage (installer); C18 |
| X-9 | the chat authors no `publish` block; server-owned `exported` and `imported` states pass | C8 |
| X-10 | non-coverage: the flag gate is the server's; the kit states it in the Backend row (BA-9) | non-coverage (server flag) |

---
provenance: written 2026-09-12 by Claude (session c0a2923c, atom a-c0a2923c-23) from `APPS-THREATS.md` and `angles/*.json`; program step 4.
