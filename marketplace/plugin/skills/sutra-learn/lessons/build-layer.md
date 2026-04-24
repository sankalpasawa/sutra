# BUILD-LAYER — L0 / L1 / L2, where code lives and why

Sutra code lives in one of three layers. Knowing which layer you're touching determines the blast radius and the promotion ceremony.

## The 3 layers

| Layer | Scope                              | Location                                        | Aspiration            |
|-------|------------------------------------|-------------------------------------------------|------------------------|
| L0    | Plugin-shipped, fleet-wide         | sutra/marketplace/plugin/**                     | YES (default target)   |
| L1    | Staging with promotion deadline    | Anywhere, but with BY: date + OWNER + criteria  | Promote to L0 or demote|
| L2    | Instance-local, forever            | holding/hooks/**, project-specific code         | Stays local            |

## Why this exists

Without the layer concept, every change becomes "should this affect everyone or just me?" — a question that gets asked wrong 80% of the time. Declaring the layer up front forces the decision visible.

## PROTO-021 enforcement

Before any Edit/Write to plugin paths, you declare:

```
BUILD-LAYER: L0 | L1 | L2
ACTIVATION-SCOPE: fleet | cohort:<name> | single-instance:<name>
TARGET-PATH: <absolute path>
PROMOTION:
  SOURCE: founder | sutra-forge | client-feedback
  (if L1): TARGET-PATH, BY:<YYYY-MM-DD>, OWNER, ACCEPTANCE-CRITERIA, STALE-DISPOSITION
```

The build-layer-check.sh hook reads this from the marker file. HARD enforcement on `holding/hooks/**`, `holding/departments/**`, `sutra/marketplace/plugin/**`, `sutra/os/charters/**`.

## Promotion flow

L2 → L1: add promotion block with BY date + acceptance criteria.
L1 → L0: meet acceptance criteria, move file into `sutra/marketplace/plugin/`, ship in next version.

## When to pick each

- **L0**: the feature makes sense for every Sutra install (e.g., privacy sanitization, depth-marker).
- **L1**: not-yet-proven but promising; 30-60 day promotion horizon.
- **L2**: only makes sense for this instance (e.g., Asawa-specific god-mode password).

Aspire to L0 by default. L2 is a smell — most L2 code should eventually promote or be deleted.
