# Sutra — Defaults Architecture

**Classification**: Core Infrastructure (not a protocol — this is HOW companies are built on Sutra)

## Pattern: Inherited Defaults with Override Governance

This is the **runtime substrate** that every Sutra-powered company executes on. It defines the policy inheritance chain — analogous to kernel-space vs user-space in operating systems, or Standing Orders vs Rules of Engagement in NATO command doctrine. Every behavior ships with a Sutra-defined default. Companies inherit defaults via **convention over configuration** (cf. Rails). Override capability is governed by directive classification using formal safety property analysis (Lamport) and FMEA blast radius assessment (NASA).

---

## Directive Classification

Three tiers, drawn from formal verification (invariants), distributed systems (consensus requirements), and military doctrine (command authority levels).

### Tier 1: Immutable Invariants (Sealed Directives)

**Military analog**: Standing Orders — always in effect, cannot be modified by field commanders under any circumstance.  
**Software analog**: Kernel-space constraints. `final` / `sealed` methods in OOP. Byzantine fault tolerance invariants.  
**Formal property**: These are **safety properties** (Lamport) — "something bad never happens."

| Invariant | Why it's sealed | Enforcement |
|-----------|----------------|-------------|
| Secrets never in source (PROTO-004) | Supply chain compromise | Hard gate — grep hook, exit 2 |
| Human is final authority (P7) | Alignment guarantee | Structural — override protocol always available |
| Audit trail for all overrides | Non-repudiation | Hard gate — override-tracker.sh |
| Data sovereignty per company | Isolation guarantee | Hard gate — enforce-boundaries.sh |
| Feedback flows up, never sideways | Prevents cascade corruption | Hard gate — cross-company edit block |
| Direction encoding required (D28) | System integrity | Hard gate — direction without encoding = incomplete |

**Override**: IMPOSSIBLE. No company, no agent, no session can disable these. Only the founder (CEO of Asawa) can modify an invariant, and it requires a **constitutional amendment** — explicit versioned change to this document with cascade impact assessment.

---

### Tier 2: Controlled Parameters (Gated Overrides)

**Military analog**: Rules of Engagement (ROE) — field commanders can escalate or de-escalate within authorized bounds, but changes require theatre command approval.  
**Software analog**: Feature flags with authorization gates. `protected` methods — subclass can override but must maintain the contract. Raft consensus — changes require quorum.  
**Formal property**: These are **liveness properties** — "something good eventually happens" — but the path is constrained.

| Parameter | Default | Override requires | Rationale |
|-----------|---------|-------------------|-----------|
| Enforcement level (SOFT/HARD) | SOFT for most hooks | Asawa approval | Loosening enforcement = systemic risk |
| Thoroughness floor for security tasks | Level 3 minimum | Asawa approval | Auth/data tasks cannot be fast-tracked |
| Pipeline phase activation | All phases active | Asawa approval to skip phases | Skipping POST = no feedback loop |
| Cross-company data access | Denied | Asawa explicit grant | Information barrier |
| Protocol retirement | EXPERIMENTAL→STABLE→REMOVED lifecycle | Sutra CEO + Asawa acknowledgment | Removing process = removing safety net |
| Agent delegation depth | Max 2 levels | Asawa approval for deeper | Unbounded delegation = loss of control |

**Override**: Via **change request** to Asawa. Company submits request to `feedback-to-sutra/`. Sutra evaluates. Asawa approves or denies. Logged, versioned, time-bounded if applicable.

---

### Tier 3: Tunables (User-Space Configuration)

**Military analog**: Standard Operating Procedures (SOPs) — adapted by unit commanders to local terrain, weather, and mission without higher approval.  
**Software analog**: User-space configuration. CSS custom properties. `.env` overrides. Dependency injection. Strategy pattern — swap the implementation, keep the interface.  
**Formal property**: These are **parametric variations** — the system behavior changes within defined bounds.

| Tunable | Sutra Default | Company overrides in | Example override |
|---------|--------------|---------------------|-----------------|
| Git push cadence | Push after every commit | `SUTRA-CONFIG.md` | Push at session end only |
| Estimation depth for low-risk tasks | Level 2 (standard) | `SUTRA-CONFIG.md` | Level 1 for CSS-only |
| Hook verbosity | SOFT (reminder shown) | `SUTRA-CONFIG.md` | SILENT (audit only, no output) |
| Involvement level | Strategic | `SUTRA-CONFIG.md` | Hands-on or Delegated |
| Evolution pulse cadence | 5 minutes | `SUTRA-CONFIG.md` | 15 minutes or session-end only |
| Documentation format | Markdown | `SUTRA-CONFIG.md` | HTML for exec docs (D14) |
| Standup frequency | Daily | `SUTRA-CONFIG.md` | Async / weekly |
| Feature lifecycle detail | Full SHAPE→VERIFY | `SUTRA-CONFIG.md` | Lightweight for personal tier |
| Notification channel | stdout (terminal) | `SUTRA-CONFIG.md` | Email, Slack, or silent |

**Override**: Unilateral. Company CEO writes to `SUTRA-CONFIG.md`. No approval needed. Takes effect immediately. Logged in config diff history.

---

## Classification Decision Framework

**The Blast Radius Test** (adapted from NASA's Failure Mode and Effects Analysis — FMEA):

```
WHO GETS HURT IF THIS IS OVERRIDDEN AND IT GOES WRONG?
│
├── Users / data / security / other companies
│   └── TIER 1: Immutable Invariant (sealed)
│
├── System integrity / Sutra's ability to function / the feedback loop
│   └── TIER 2: Controlled Parameter (gated override)
│
└── Only this company's workflow preferences
    └── TIER 3: Tunable (user-space config)
```

**The Reversibility Test** (adapted from Amazon's one-way vs two-way door decisions):

| Reversibility | Classification |
|--------------|---------------|
| **One-way door** — cannot undo (data loss, security breach, broken audit trail) | Tier 1: Immutable |
| **Slow-reverse door** — can undo but costly (wrong architecture, skipped testing) | Tier 2: Controlled |
| **Two-way door** — easily reversible (process preference, cadence, verbosity) | Tier 3: Tunable |

---

## Inheritance Chain

```
┌─────────────────────────────────────────┐
│  ASAWA (Governance Layer)               │
│  ├── Immutable Invariants (Tier 1)      │  ← sealed, no override
│  └── Override Approval Authority         │  ← approves Tier 2 changes
└────────────────┬────────────────────────┘
                 │ inherits
┌────────────────▼────────────────────────┐
│  SUTRA (Operating System Layer)         │
│  ├── Controlled Parameters (Tier 2)     │  ← gated override
│  ├── Tunable Defaults (Tier 3)          │  ← convention-over-configuration
│  └── Protocol Library                   │
└────────────────┬────────────────────────┘
                 │ inherits (filtered by stage + product type)
┌────────────────▼────────────────────────┐
│  COMPANY (Execution Layer)              │
│  ├── Inherits all Tier 1 (immutable)    │
│  ├── Inherits Tier 2 (can request change)│
│  ├── Overrides Tier 3 via SUTRA-CONFIG  │
│  └── Adds company-specific tunables     │
└─────────────────────────────────────────┘
```

**Precedence** (highest to lowest):
1. Immutable Invariants — always win
2. Asawa explicit override (D24 PUSH mode)
3. Company's SUTRA-CONFIG.md overrides
4. Sutra defaults
5. Inferred behavior (agent judgment)

This follows the **specificity cascade** model from CSS — more specific rules override less specific ones, but `!important` (Tier 1) always wins.

---

## Runtime Resolution

When the system encounters a configurable behavior:

```
1. Check Tier 1 invariants     → if violated, BLOCK (no exceptions)
2. Check Tier 2 parameters     → if override exists, verify Asawa approval
3. Check company SUTRA-CONFIG  → if override exists, apply it
4. Fall back to Sutra default  → convention over configuration
5. Fall back to agent judgment  → last resort, logged for review
```

This is a **policy engine** pattern (cf. Open Policy Agent / Rego in cloud-native infrastructure, or XACML in enterprise access control).

---

## Adding New Defaults

When Sutra adds a new behavior:

1. **Classify** using Blast Radius Test + Reversibility Test
2. **Set default** in the appropriate Sutra protocol
3. **Document** in this file under the correct tier
4. **Deploy** — Tier 3 tunables are immediately available for company override; Tier 2 requires version bump; Tier 1 requires constitutional amendment
5. **Notify** existing companies via `feedback-from-sutra/` (D24 PULL model)

---

*Architecture pattern: Inherited Defaults with Override Governance*  
*Influences: Convention over Configuration (Rails), Policy-as-Code (OPA), Standing Orders / ROE (NATO doctrine), Sealed Classes (Kotlin/C#), FMEA (NASA), One-Way/Two-Way Doors (Amazon), Specificity Cascade (CSS), Formal Safety/Liveness Properties (Lamport)*
