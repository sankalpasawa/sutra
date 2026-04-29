# Test Data Fixtures — M4.10 Convention

**Status**: shipped at M4.10 (R-5 audit RED → GREEN)
**Source-of-truth**: `holding/plans/native-v1.0/M4-schemas-edges.md` §M4.10

Every primitive + schema in `@sutra/native` ships with a fixture file at
`tests/fixtures/<primitive>.fixture.ts` exporting at minimum the following
factory functions:

| Factory | Returns | Use |
|---|---|---|
| `validMinimal()` | the primitive with required-only fields populated to spec-minimum | smoke tests, default arms in property tests |
| `validFull()` | the primitive with every optional field populated and rich data | full round-trip + serialization tests |
| `invalidMissingRequired()` | a `Partial<T>` deliberately lacking ≥1 required field | constructor/validator rejection tests |

## Conventions

1. **Pure**: factories return fresh objects every call (no shared mutable state).
2. **Deep-cloneable**: returned objects pass `structuredClone()` without throwing.
3. **Spec-grounded**: each fixture cites the V2 spec section (or D1-D5 deliverable)
   the shape is sourced from in a JSDoc comment above the factory.
4. **Type-safe**: factories return the typed primitive, not `any`. The
   `invalidMissingRequired()` family returns `Partial<T>` (or an `unknown`-cast)
   so TS doesn't object to the missing-by-design field.
5. **Composable with arbitraries**: any fixture used as a "seed" in property
   tests must compose cleanly with `tests/property/arbitraries.ts` shapes.

## File layout (M4)

```
tests/fixtures/
├── README.md                          ← this file
├── domain.fixture.ts                  ← M4.10 baseline
├── charter.fixture.ts                 ← M4.10 baseline
├── workflow.fixture.ts                ← M4.10 baseline (extended in M4.4)
├── execution.fixture.ts               ← M4.10 baseline (extended in M4.2)
├── tenant.fixture.ts                  ← M4.1
├── decision-provenance.fixture.ts     ← M4.3
├── cutover-contract.fixture.ts        ← M4.7 (chunk 2)
└── fixtures.test.ts                   ← validates every fixture round-trips
```

## Validation contract

Each fixture is itself tested by `tests/fixtures/fixtures.test.ts`:

- `validMinimal()` MUST round-trip through the primitive's constructor and pass
  the `isValid<Primitive>` predicate.
- `validFull()` MUST round-trip through the primitive's constructor and pass
  the predicate.
- `invalidMissingRequired()` MUST cause the constructor to throw OR fail the
  predicate (one or both).

> The third arm is critical: it's how we catch a future spec amendment that
> tightens a field to required without updating fixtures.

## Operationalization

- **Measurement**: count of fixtures vs. count of primitives ≥ 1:1
- **Iteration trigger**: any new primitive in M4-M12 ships with a matching
  fixture file in the same commit
- **DRI**: Sutra-OS team
- **Decommission**: replaced when V3 schema generators auto-emit fixtures

## See also

- `tests/property/arbitraries.ts` — fast-check arbitraries (related but different
  contract: arbitraries are random generators; fixtures are stable seeds).
- `holding/plans/native-v1.0/M4-schemas-edges.md` §M4.10 (spec source)
