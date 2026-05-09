---
part-id: B10
bucket: blocks
template: L8-feature-spec
parity-source: §12.13 row B10 + §12.12 founder voice round 4 + §10.2 P10 + Q30
parity-source-sha256: e28f8ccd3e9042bcd3f332fb316712ea74ecae36274deee869273056e7f8e0a8
status: DRAFT v1
authored: 2026-05-09
---

# B10: Domain Typed Config + Charter Typed Config

## 1-line summary

Domain carries typed `principles[]` + `guidelines[]` + `decisions[]`; Charter carries typed `instructions[]` + `guidelines[]` + `constraints[]` — every constraint is declared, not tacit, and consumed at prompt-build time per B11.

## Scope (in / out)

**In scope (v1)**:
- EXTEND existing Domain (§2.1) — add `guidelines[]` + `decisions[]` typed arrays per §12.13 row B10. (Domain.principles[] exists partial per canon §2.1.)
- EXTEND existing Charter (§2.2) — add `instructions[]` + `guidelines[]` + `constraints[]` typed arrays per §12.13 row B10. (Charter.invariants / .constraints exist partial per §2.2.)
- All consumed at prompt-build time per B11 (constrained problem construction per P11).
- Per Q30 default (2026-05-09) — structured typed predicates v1 (PNC-aligned per ADR-012); free-form `notes` field allowed for human commentary.

**Out of scope (v1)**:
- Auto-derivation of guidelines from operator behavior — overlaps B18 Person Formation; deferred v2+.
- Cross-Tenant config sharing — Tenant-scoped only per §6.2.
- Dynamic mutation of typed config mid-Workflow — overlaps 7e (mid-exec mutation); routed via 7e.

## User outcome

Every LLM call receives explicit Domain + Charter config (principles, guidelines, decisions, instructions, constraints) as part of the prompt — no tacit-knowledge LLM calls. Founder voice round 4: "for each domain ... guidelines, principles or some decisions and for each charter ... instructions guideline constraints".

## UX flow (narrative; terminal + audit log)

1. Domain authored with `principles[]` + `guidelines[]` + `decisions[]`.
2. Charter authored with `instructions[]` + `guidelines[]` + `constraints[]`.
3. Each typed entry is a PNC-aligned predicate (per Q30 default + ADR-012) OR includes a free-form `notes` field for human commentary.
4. Workflow fires inside Charter inside Domain.
5. B11 PromptBuilder reads both configs; embeds in prompt context per P11.
6. LLM call receives constrained problem.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Domain has principles + guidelines + decisions populated | Workflow in Domain fires | B11 PromptBuilder embeds all three arrays in prompt context |
| 2 | Charter has instructions + guidelines + constraints populated | Workflow in Charter fires | B11 embeds all three arrays in prompt context |
| 3 | Config entry uses unstructured prose only (no PNC predicate) | validation | rejected per Q30 v1 (structured typed predicates required); `notes` field still allowed |
| 4 | Config entry's PNC predicate parses successfully | runtime check | entry usable; consumed by B11 |
| 5 | Charter constraint conflicts with Domain principle | conflict | conflict-resolution rule NOT specified in canon (gap per F2; founder-side ambiguity per Q30 + per Q28 cross-Charter cascade) |

## Data model

Per §12.13 row B10: EXTEND existing Domain + Charter (§2.1 + §2.2). No new §2 primitive (per F5).

Per Q30 default + ADR-012:

```
Domain (extended) = {
  ...existing §2.1 fields (tenant_id, principles[] partial),
  guidelines: TypedPredicate[]    // NEW
  decisions: TypedPredicate[]     // NEW
}

Charter (extended) = {
  ...existing §2.2 fields (invariants[] / constraints[] partial),
  instructions: TypedPredicate[]  // NEW
  guidelines: TypedPredicate[]    // NEW
  constraints: TypedPredicate[]   // extends existing constraints
}

TypedPredicate = {
  predicate_body    // PNC-aligned typed predicate per ADR-012
  notes             // free-form prose allowed per Q30
}
```

Cross-refs:
- `../primitives/domain.md` (host)
- `../primitives/charter.md` (host)

## Edge cases

- **Empty guidelines / decisions / instructions / constraints** → PromptBuilder embeds nothing for those slots; allowed (no minimum specified in canon — gap per F2).
- **Predicate fails parse** → rejected at config-write time per Q30 + ADR-012.
- **Two typed predicates contradict** → conflict-resolution NOT specified in canon (gap per F2).
- **Operator mutates Domain config mid-Workflow** → routed via 7e classification.

## Telemetry

Events (canon-existing only):
- `policy_decision` (§3.2) — when typed-predicate evaluates as part of B11 prompt-build.
- `artifact_registered` (#9) — config-as-artifact per P1 closed-loop.

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Pattern-detection precision — explicit constraints raise proposal precision.
- Approval-gate latency — constrained problems reduce founder review time.

## Dependencies

- **Primitives**: `domain` (host), `charter` (host), `engine-event`.
- **Events**: `policy_decision`, `artifact_registered`.
- **Surfaces**: `audit`, `route`.
- **Hardstops**: HS-4 (audit-unwritable).
- **Blocks**: B11 (PromptBuilder consumer), B4 (Charter context-scope; complementary), B3 (Domain MECE; complementary), 7e (mid-exec mutation route).
- **Pillars**: P10 (Typed config at every primitive layer), P11 (Constrained problem construction).
- **ADRs**: ADR-012 (PNC typed predicates).

## References

- NATIVE-ENGINE.md §12.13 row B10 (founder voice round 4).
- NATIVE-ENGINE.md §2.1 Domain primitive.
- NATIVE-ENGINE.md §2.2 Charter primitive.
- NATIVE-ENGINE.md §10.2 P10 (Typed config at every primitive layer).
- Q30 (§12.15) — structured typed predicates v1; free-form notes allowed.
- ADR-012 (PNC typed predicates).
