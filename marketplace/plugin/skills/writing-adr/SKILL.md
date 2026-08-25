---
name: writing-adr
description: Author an Architecture Decision Record (Status / Context / Decision / Consequences) in the Sutra canon shape. Use when recording any decision with lasting consequences.
---

---
name: writing-adr
description: Standard for authoring Sutra ADRs (Architecture Decision Records) at sutra/os/decisions/ADR-NNN-*.md. Use when capturing one decision's rationale.
type: writing-standard
---

# Writing an ADR

## Filename
`sutra/os/decisions/ADR-NNN-<kebab-slug>.md` where NNN is zero-padded next sequence number (current max is ADR-003; new Native ADRs start at ADR-004).

## Section order (mandatory, in this order)
1. **Status** — `Proposed` | `Accepted` | `Superseded by ADR-NNN` | `Deprecated`. Date stamped (`YYYY-MM-DD`).
2. **Context** — what forces drove the decision; environment + constraints. ≤200 words. Rejected alternatives go here (or in an `### Alternatives considered` sub-section).
3. **Decision** — the choice made; one sentence + clarifying bullets. State as imperative ("Native engine MUST ...").
4. **Consequences** — what becomes true after; positive + negative + neutral. Table format with columns `Kind | Effect`.

## Hard constraints
- Length: ≤500 words (word count governs; line count advisory ~150 — code blocks and tables make line count unreliable)
- ONE decision per ADR (split if compound)
- Charter is referenced, NEVER duplicated ("see `sutra/os/engines/NATIVE-ENGINE.md` §3"; not "Native engine has primitives X, Y, Z")
- Date format: `YYYY-MM-DD`
- Author: durable role ("CEO of Asawa") not personal name unless founder explicitly requests

## Anti-patterns (reject)
- Restating charter contract in Decision (link instead)
- Tutorials / step-by-step (this is rationale, not how-to)
- Multi-decision ADRs (split each into its own ADR)
- ADR for a settled engineering convention with no controversy ("we use UTF-8") — settled conventions live in the charter

## Anchors (read before authoring)
- `sutra/os/decisions/ADR-001-h-sutra-9cell-grid.md`
- `sutra/os/decisions/ADR-002-out-direct-3check.md`
- `sutra/os/decisions/ADR-003-permissions-mcp-and-first-time-edit.md`

**Note on anchors**: ADR-001/002/003 predate this standard. Read them for **voice (technical, terse), evidence-grounding (cite specific files/commits), and table use in Consequences**. Their structure may not match the 4-section order verbatim — that's expected. Going forward, ADR-004+ uses the 4-section order canonically.

## Verification (post-author)
1. `wc -w <file>` ≤ 500
2. Filename matches `ADR-[0-9]+-[a-z0-9-]+\.md`
3. `## Status` block within first 10 lines
4. Exactly 4 H2 sections (Status / Context / Decision / Consequences); `### Alternatives considered` is a sub-section under Context, not a new H2
