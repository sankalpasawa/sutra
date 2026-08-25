---
name: writing-engine-charter
description: Author an engine-of-record charter markdown for a new governance engine or discipline. Use when a new engine/hook family needs its spec.
---

---
name: writing-engine-charter
description: Standard for authoring Sutra OS engine charters (e.g., NATIVE-ENGINE.md). Use when writing or revising any sutra/os/engines/*.md file.
type: writing-standard
---

# Writing an Engine Charter

## Section order (mandatory)
1. **Purpose** — 1-paragraph why-this-engine-exists
2. **Primitives** — entities + their fields + invariants (table per primitive)
3. **Contract** — interface surface for callers (function signatures / API / event types)
4. **Invariants** — runtime laws that hold for all valid states (numbered list)
5. **Integrations** — boundaries with other layers (table per boundary)
6. **Operations** — observability, telemetry, error semantics
7. **Threat Model** — top STRIDE risks + mitigations (table)
8. **Open Seams** — known extension points + deferred decisions (link to relevant ADRs)

## Hard constraints
- Length: ≤5000 words (word count governs; line count advisory ~750 — code blocks and tables make line count unreliable)
- Format: tables > prose; ASCII diagrams > prose; bullets > paragraphs
- Voice: declarative present tense ("the engine emits ..." not "the engine should emit ...")
- NO rationale: every "why" lives in an ADR (the charter only states what is)
- NO history: every wave/version note lives in archive (the charter is timeless)
- Reference style: ADRs by number ("see ADR-007"); peer engines by relative path ("see `sutra/os/engines/BLUEPRINT-ENGINE.md`")

## Anti-patterns (reject)
- Mixing WHY into a WHAT section ("we chose X because Y" — extract WHY to ADR)
- Wave/timestamp narrative ("In v1.2 we added X" — belongs in archive)
- Prose paragraphs where a 4-row table fits
- Future-tense aspirations ("we plan to ..." — defer to Open Seams + ADR)
- Restating an ADR's decision (link to it instead)

## Sibling anchors (read before authoring)
- `sutra/os/engines/BLUEPRINT-ENGINE.md`
- `sutra/os/engines/HUMAN-SUTRA-ENGINE.md`
- `sutra/os/engines/ESTIMATION-ENGINE.md`

**Note on siblings**: BLUEPRINT/HUMAN-SUTRA/ESTIMATION engines predate this standard. Read them for **voice, density, and formatting conventions** (tables-over-prose, declarative present tense, ASCII layout). Their **section order** may not match the 8 above — that's expected. Going forward, the 8-section order is canonical for new engine charters; existing siblings may be brought up to standard incrementally if/when they're touched.

## Verification (post-author)
1. `wc -w <file>` — must be ≤ 5000
2. `grep -nE 'because|we chose|rationale' <file>` — should return 0 matches in WHAT sections
3. `grep -nE 'v[0-9]+\.[0-9]+' <file>` — should return 0 matches outside Open Seams
4. Section header order matches the 8 above (run `grep -n '^## ' <file>`)
