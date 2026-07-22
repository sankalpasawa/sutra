# Native canon — orientation index

**Source of truth**: [`../engines/NATIVE-ENGINE.md`](../engines/NATIVE-ENGINE.md) (runtime
charter) + [`../decisions/`](../decisions/) (ADRs). Everything here is navigation; if this
index conflicts with the charter or an ADR, they win (founder direction D54).

**Reading order for a first visit**: NATIVE-ENGINE.md → the ADRs it cites → the bucket
that answers your question below.

## Buckets

Each directory holds one part-file per concern, authored to a bucket-specific template.
Entries below describe each bucket's *purpose*, not its contents.

| Directory | Documents |
|---|---|
| `blocks/` | The building blocks of the engine, one part-file each |
| `arch-blocks/` | Architecture-level block views |
| `pillars/` | The product pillars Native commits to |
| `primitives/` | The primitive types the engine operates on |
| `events/` | Event-related canon |
| `surfaces/` | The surfaces through which Native is used |
| `hardstops/` | The lines the system will not cross |
| `doc-layers/` | How Native's documentation itself is layered |
| `impl-phases/` | Implementation phasing |
| `metrics/` | How Native measures itself |
| `open-questions/` | Tracked unknowns awaiting decision |
| `components/` | Component-level canon |
| `MIGRATION-PLAN.md` | The plan that moved canon into this structure |

## Related

- **What is Native, in one paragraph** — repo [README](../../README.md)
- **Why / for whom / what's open** — [CLARITY.md](../../CLARITY.md)
- **New Native facts** route through the D54 decision tree (charter §, new ADR, or both) —
  never directly into this index.
