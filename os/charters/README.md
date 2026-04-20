# Sutra — Charters (Model + Protocol)

**Home for cross-cutting, horizontal initiatives. Parallel to `os/engines/` and `os/protocols/`.**

---

## 1. The Cascading Unit Model

Every organizational unit — org, department, sub-department — has the SAME shape:

```
UNIT (org | department | sub-department)
├── Definition Charter   — who we are, what we own, mission (1)
├── Skills               — discipline-specific capabilities (N)
└── Initiative Charters  — cross-cutting efforts we contribute to (N)
        └── as DRI (own it) OR Contributor (contribute to it)
```

This shape cascades:

```
ORG (Sutra)
├── Definition Charter: PRODUCT-VISION.md + VISION.md
├── Skills: layer4-practice-skills/
└── Initiative Charters (org-level): os/charters/TOKENS.md, os/charters/SPEED.md, ...
        │
        ▼ cascades down to
DEPARTMENT (Analytics, Engineering, Product, ...)
├── Definition Charter: departments/<name>/CHARTER.md
├── Skills: departments/<name>/skills/ or SKILLS.md
└── Initiative Charter Participations: listed in dept CHARTER.md
        │
        ▼ cascades down to
SUB-UNIT (if team is large enough)
└── Same shape recursively.
```

**Core invariant**: every unit answers three questions:
1. **Who are we?** (Definition Charter)
2. **What can we do?** (Skills)
3. **What outcomes are we driving?** (Initiative Charter participations)

If a unit cannot answer all three, it is incomplete.

---

## 2. Two Kinds of Charter

Both are called "charter" — they are structurally distinct.

| Kind | Purpose | Scope | Owner | Example |
|---|---|---|---|---|
| **Definition Charter** | Constitution — defines a unit | One unit | The unit itself | `holding/departments/analytics/CHARTER.md` |
| **Initiative Charter** | Strategic priority — cross-cuts units | Multiple units | One DRI unit, many contributors | `sutra/os/charters/TOKENS.md` (this dir) |

**This directory (`os/charters/`) holds Initiative Charters only.** Definition Charters live with their unit (next to the dept directory, or at company root for the company itself).

The reference anatomy for Initiative Charters is `sutra/layer2-operating-system/a-company-architecture/CHARTERS.md` — do not duplicate; follow it.

---

## 3. Protocol: Adding a New Initiative Charter

Run this checklist before creating any new file in `os/charters/`.

| Step | Gate | Artifact |
|---|---|---|
| 1. **Name the strategic priority** | One word, memorable (Tokens, Speed, Quality, Growth) | file name |
| 2. **Check it's cross-cutting** | Must span ≥2 units; single-unit concerns belong in the unit's own roadmap | justification paragraph |
| 3. **Assign DRI** | Exactly ONE unit owns the outcome | `DRI:` field |
| 4. **List Contributors** | Other units and WHAT they contribute | Practice Contributions table |
| 5. **Define KRAs** | 3–5 Key Result Areas (domains inside the charter) | KRAs section |
| 6. **Define KPIs** | Always-on metrics with target/warn/breach | KPIs table |
| 7. **Set Q-OKRs** | Quarterly, scored 0.0–1.0, linked to KRAs | OKRs section |
| 8. **Write roadmap** | Concrete actions with dates + owner + OKR link | Roadmap table |
| 9. **Register** | Add to org OKRs.md index + TODO W1 entry | edits to parent files |
| 10. **Propagate decision** | Does this charter apply to downstream companies? If yes, note in charter + queue upgrade-clients.sh | `Applies to:` field |

**Tier gate**: per `layer2-operating-system/a-company-architecture/CHARTERS.md`:
- Tier 1: max 1–2 charters (Rocks format)
- Tier 2: max 3–5
- Tier 3: unlimited, but each must pass the "actively failing cross-cutting concern" test

More charters = more coordination overhead. Say no when in doubt.

---

## 4. Protocol: Adding a New Department (preview)

Full protocol formalization pending (tracked in TODO). Sketch:

| Step | Artifact |
|---|---|
| 1. Write dept Definition Charter | `departments/<name>/CHARTER.md` (purpose, scope, what it owns) |
| 2. List discipline skills | `departments/<name>/SKILLS.md` or `skills/` folder |
| 3. List initiative charters this dept participates in | in the Definition Charter |
| 4. Ship minimum tooling | whatever scripts/hooks the dept runs (see Analytics exemplar) |
| 5. Register in org map | `SYSTEM-MAP.md` + org `OKRs.md` contributors column |

**Exemplar**: `holding/departments/analytics/` — CHARTER.md, METRICS.md, GOALS.md, TELEMETRY-CONTRACT.md, collect.sh, publish.sh. Copy this shape.

---

## 5. Why this protocol exists

Without a protocol, each new dept or charter invents its own shape, and cross-linkages rot. The protocol forces:
- Every unit has a definition (prevents ambiguous ownership)
- Every charter has one DRI (prevents "everyone owns it = nobody owns it")
- Every skill belongs to a unit (prevents orphan capabilities)
- Cross-cutting concerns live in `os/charters/` (prevents duplication across dept roadmaps)

---

## 6. Active Initiative Charters

| Charter | DRI | Status | Q | Created |
|---|---|---|---|---|
| [TOKENS](TOKENS.md) | Sutra-OS | ACTIVE | Q2 2026 | 2026-04-20 |
| [SPEED](SPEED.md) | Sutra-OS | ACTIVE | Q2 2026 | 2026-04-20 |

---

## 7. Related

- **Pattern reference**: `sutra/layer2-operating-system/a-company-architecture/CHARTERS.md`
- **Dept exemplar**: `holding/departments/analytics/` (Asawa-level Analytics Dept v0)
- **Telemetry contract**: `holding/departments/analytics/TELEMETRY-CONTRACT.md`
- **Propagation**: charter-aware propagation via `upgrade-clients.sh` (PROTO-018) is **not yet implemented** — the current version is manifest-driven only. Extending it is tracked in Tokens charter roadmap step 12. Until then, propagation to client companies is a manual deploy via god mode.
