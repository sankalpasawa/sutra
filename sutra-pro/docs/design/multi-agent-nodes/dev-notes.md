# Multi-agent nodes: developer notes

Status: written while building phase 1 (MAN-1 to MAN-4), 2026-11-20. These notes are for the architect: where the design met the real code and what was changed or left
open. Each item says what the design said, what the code showed, what was done, and what the architect should decide. Paths are under `sutra-pro/`.

## MAN-1. Foundations

### N1. `node_messages.seq` cannot be gap-free per project if it is the table's AUTOINCREMENT (small change, done)

- Design: architecture.md section 4.1 and 7 say `seq` is "gap-free per project, from the table's autoincrement"; D264 says "gap-free `seq` per project".
- Code: an `INTEGER PRIMARY KEY AUTOINCREMENT` counts for the whole table. With two projects posting, project A would see seq 1, 3, 4 and project B 2, 5. A page that detects a gap
  (the `after=` catch-up of the streaming contract) would think messages were lost.
- Done: migration v6 makes the key `(project_id, seq)`. The writer (MAN-6, `NodeStore.post`) takes `MAX(seq) + 1` for the project inside its one write transaction. The server is
  the only writer and a write transaction is exclusive (`BEGIN IMMEDIATE`), so two posts cannot take the same number. `UNIQUE (project_id, src_ref)` is as designed.
- Architect: nothing to decide unless you want a global sequence for the page. If so, the page must stop treating a gap as loss.

### N2. Columns the design names elsewhere but the table list did not show (additive, done)

The migration is "never edited later", so what the later packages need is in it now:

- `projects.decide_for_me` (0 or 1): D294 and guardrails 5.1 say the switch lives on the project row; the table list in architecture.md section 7 left it out.
- `projects.paused` (0 or 1): `POST /api/projects/{id}/pause` needs somewhere to keep "paused", and the status list has no `paused` value (a paused project is still `running`).
- `projects.review_loops` (count): "review loops ... counted in `projects` rows" (architecture.md 4.4).
- `approvals.created_at`: for the expiry clock and the card's age.

### N3. Append-only triggers on `node_messages` as well as `node_audit` (small addition, done)

D264 says messages are append-only; the design's data model only gave triggers to `node_audit`. A table that is only appended to by the server is cheaper to trust with the
rule written into it, as `atom_ledger` does. If MAN-6 needs to redact a stored message it must scrub before it stores (which the design already says), not edit afterwards.

### N4. `docs/design/traceability.json` was out of date before this work

The committed file said 200 decisions while the log was at D252. Registering D253 to D296 meant running `scripts/build_traceability.py`, which rewrote the file and
`docs/TRACEABILITY.md` from the current sources. A few unrelated rows (D133, D176, D179, D190) moved because the generator re-read the notes. Nothing was edited by hand.

### N5. Two existing tests pinned the schema version

`tests/orchestrator/test_live_turn.py` (migration v5) asserted `SCHEMA_VERSION == 5` and "nothing else changed"; `tests/orchestrator/test_schema.py` (v3 to v4) counted every
table of `TABLES`. Both now migrate only as far as their own version and skip the tables of later migrations. No assertion was weakened: the v5 test still checks that v5 changes
nothing but its table, and the v6 swap of the index has its own test file.

### N6. The new flags are not in `Settings.public()`

`GET /api/config` and `sutra-pro config show` list `public()`. Adding keys there would change an existing route's output while the feature is off, so the four flags are
left out for now. The kill switch command (MAN-4, `sutra-pro nodes status`) prints them.
