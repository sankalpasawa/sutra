# Sutra Marketplace Deployment — Design DAG

_Workflow instance. Sutra Kernel arch flow, manual runtime (Kernel V1 build pending)._
_Started: 2026-04-18. P0-P2 DONE. P3 ACTIVE (functionality-first). Founder pivot 2026-04-18: functionality > GTM; DayFlow is canary._
_Spec reference: `holding/research/2026-04-18-workflow-architecture-spec-v1.0-COMMITTED.md`_

---

## Workflow Input

```yaml
objective: |
  Ship Sutra as a Claude Code plugin that anyone can install via
  /plugin install sutra@<marketplace> and use as Sutra intends.

context:
  - Existing: sutra/package/ (npm distribution, live v1.9)
  - Existing: sutra/layer1..4/ (OS content, source-of-truth)
  - Existing: holding/hooks/ (with portability notes in sutra/package/MANIFEST.md)
  - Direction: plugin name = "Sutra" bare; Asawa hidden from marketplace
  - Direction: use Sutra Kernel arch flow as design method
  - Direction: minimal scaffolding ("no need to make a lot of changes")

target_confidence: 0.85
cost_cap: ~2 weeks founder time
mode: design        # publish DAG first; execute in waves after approval
```

---

## P0 CLASSIFY — DONE

**Cynefin domain: Complicated / TRAVERSE**

Rationale:
- Claude Code plugin format is documented (not unknown ⇒ not Complex)
- Sutra content exists + is stable (not chaotic)
- Content mapping + hooks portability require expert judgment (not Clear)
- Cause-effect is discoverable: "install X → gets Y → experiences Z"

Consequence for engine:
- `min_valid_siblings` floor = 6 (per kernel-v1-spec §Complicated defaults)
- TRAVERSE pattern: enumerate → select → deepen, linear progress with checkpoints
- NOT a PROBE pattern (we're not running experiments to learn)

---

## P1 ENUMERATE — DONE

Swept all 12 factor-decomposition categories. 20 factors surfaced, clustered into 10 disciplines.

**Breadth check**: 20 >> 6 floor. Pass.

### Factor table

| # | Factor | Category | U | R | O | C | Discipline |
|---|---|---|:-:|:-:|:-:|:-:|---|
| F1 | Claude Code plugin manifest schema (`plugin.json` format, required fields, skills/commands/hooks/agents layout) | Structural | H | H | H | 0.4 | Platform research |
| F2 | Content mapping — which `sutra/` content maps to plugin skills vs commands vs resources | Structural | H | M | M | 0.5 | Architecture |
| F3 | Source-of-truth between `sutra/package/` (npm) and `sutra/marketplace/plugin/` (plugin) — shared-source vs duplicate | SOT integrity | M | M | M | 0.6 | Architecture |
| F4 | Version pinning — how plugin references Sutra OS version (v1.9 today); update semantics | Compilation | M | H | H | 0.7 | Release eng |
| F5 | Marketplace GitHub repo shape + owning account (Asawa-free) | Deployment | H | M | H | 0.3 | Distribution |
| F6 | Install / update / uninstall flows (`/plugin install sutra`, `/plugin update sutra`, `/plugin remove sutra`) | Deployment | H | M | M | 0.5 | DX |
| F7 | Hooks portability — which `holding/hooks/` ship to external installers, which stay holding-only (already scoped in `sutra/package/MANIFEST.md`) | Enforcement | M | M | H | 0.8 | Enforcement |
| F8 | Enforcement tier selection at install time (individual / project / company profiles map to depth + enforcement defaults) | Enforcement | M | H | M | 0.6 | DX |
| F9 | Context / token budget at plugin load — progressive disclosure per Anthropic skill pattern | Runtime | M | H | H | 0.5 | Runtime perf |
| F10 | Coexistence with other Claude Code plugins (superpowers, vercel, etc. — namespace collisions, hook ordering) | Runtime | L | H | M | 0.4 | Runtime perf |
| F11 | Install telemetry + feedback channel (who installed, which profile, friction reports) | Data collection | M | H | H | 0.4 | Observability |
| F12 | Profile onboarding — plugin asks installer "individual / project / company?" and loads correct defaults | Ergonomics | H | M | M | 0.5 | DX |
| F13 | First-run experience (what user sees in first 60s after `/plugin install sutra`) | Ergonomics | H | H | H | 0.6 | DX |
| F14 | Claude Code version compatibility (min CC version, breaking changes, deprecation policy) | External deps | M | L | M | 0.3 | Platform research |
| F15 | **Asawa-leak audit** (strings, metadata, author fields, commit messages, file contents) — no Asawa in plugin | Risks | H | H | H | 0.7 | Governance |
| F16 | Name collision with existing Claude Code plugins named `sutra` or similar | Risks | M | M | H | 0.5 | Branding |
| F17 | npm / plugin coexistence strategy — deprecate `sutra/package/` or run both? sunset timeline? | Migration | M | M | M | 0.4 | Distribution |
| F18 | Friend-0 pilot plan — who, when, what we measure, what we learn | Migration | H | H | H | 0.3 | Distribution |
| F19 | License — currently `UNLICENSED` in `sutra/package/package.json`. MIT? Custom? Need legal clarity before publish | Risks | M | H | H | 0.3 | Legal |
| F20 | Federation readiness — plugin state is addressable + typed, so Stage 2+ CoS network doesn't require rewrite | Federation | L | L | L | 0.2 | Architecture |

**Attribute legend:**
- U = Urgency: H (blocks ship) / M (needed before GA) / L (can defer)
- R = Reversibility: H (cheap to change) / M (moderate) / L (hard to undo)
- O = Observability: H (easy to verify) / M (some judgment) / L (opaque)
- C = Confidence: 0-1 (our current understanding of this factor)

### Discipline clustering (emergent departments)

| Discipline | Factor count | Factors |
|---|:-:|---|
| Platform research | 2 | F1, F14 |
| Architecture | 3 | F2, F3, F20 |
| Release engineering | 1 | F4 |
| Distribution | 3 | F5, F17, F18 |
| DX | 4 | F6, F8, F12, F13 |
| Enforcement | 1 | F7 |
| Runtime perf | 2 | F9, F10 |
| Observability | 1 | F11 |
| Governance | 1 | F15 |
| Branding | 1 | F16 |
| Legal | 1 | F19 |

Largest cluster = DX (4 factors). This matches the founder direction "used the way Sutra is intended to be used" — the DX is the product.

### Red flag check (per factor-decomposition skill)

- [x] ≥8 factors at this depth (20 ≥ 8). No under-enumeration.
- [x] Factors cover opportunities, not only pain (F18 Friend-0, F20 federation are forward-looking).
- [x] Migration/cutover factor present (F17).
- [x] Urgency differentiation (H/M/L spread: 7 H, 9 M, 4 L).

---

## P2 VALIDATE — CLEARED (2026-04-18)

Founder verdicts on 5 customer/market decisions (companion doc §J):

| # | Decision | Verdict | Note |
|---|---|---|---|
| D-CM-1 | Wedge = Segment 1 (indie) | APPROVE, deprioritized | "not a worry right now" |
| D-CM-2 | Free forever, no auth at install | APPROVE | functionality-enabler |
| D-CM-3 | Friend-0 cohort target | REVISE: 8 → **3 confirmed + organic** | Sankalp + Benzy/Paisa + DayFlow contributor |
| D-CM-4 | F13 (first-run UX) = P3 #1 | APPROVE, **reframed as functionality** (not activation-cliff) | "focus on functionality" |
| D-CM-5 | Demo video before listing | APPROVE-in-principle, **DEFER execution**, AI-generated later | "keep that for later" |

**Meta-pivot (bigger than any single decision)**:
- **Functionality > GTM** for P3/P4. GTM factors (CM4 demo, CM6 listing, CM8 competitive watch, Phase D funnel, Phase F pricing tiers) drop to Defer.
- **DayFlow will be operated via the Sutra plugin** — NEW factor CM9 below. Replaces abstract Friend-0 cohort with an owned functional test loop.
- **No agents, incremental sessions** (2026-04-18): plugin work proceeds one chunk per session. No subagent fanout. No "do it all now" cascades.

### Factor table additions (CM1–CM9)

| # | Factor | Category | U | R | O | C | Discipline | P3 Tier |
|---|---|---|:-:|:-:|:-:|:-:|---|---|
| CM1 | Segment 1 (indie) confirmed as launch wedge, deprioritized | Strategy | L | M | H | 0.8 | Product strategy | Defer |
| CM2 | Status quo benchmark | Validation | L | H | M | 0.4 | Product research | Defer |
| CM3 | First-60-second plugin first-run script (functionality, not activation-cliff) | Activation | H | H | H | 0.5 | DX (extends F13) | Tier 1 |
| CM4 | Demo video — AI-generated, later | Acquisition | L | M | H | 0.3 | Marketing | Defer |
| CM5 | Friend-0 cohort = 3 confirmed + organic | Validation | M | H | H | 0.7 | Distribution | Tier 3 (background) |
| CM6 | Marketplace listing copy | Acquisition | L | H | H | 0.3 | Marketing | Defer |
| CM7 | Free-forever-OS posture, paid deferred 3+ months | Business model | L | M | H | 0.8 | Strategy | Defer (decided) |
| CM8 | Competitive watch (superpowers etc.) | External deps | L | L | M | 0.4 | Market intel | Defer |
| **CM9** | **Run DayFlow via Sutra plugin** — operate DayFlow's CEO session through `/plugin install sutra`. Primary functional validator. | Validation | H | M | H | 0.4 | Distribution × Architecture | **Tier 1** |

**Breadth check after fold**: 20 + 9 = 29 factors. Well above Complicated/TRAVERSE floor of 6. ✓

---

## P3 PRIORITIZE — ACTIVE (2026-04-18)

Functionality-first ranking. Formula: `score = impact × uncertainty / cost_of_decision_if_wrong`.

### Tier 1 — must resolve before any code ships

| Rank | Factor | Reason |
|:-:|---|---|
| 1 | **F13 + CM3** (first-run UX as functionality) | What the plugin DOES when installed. Canary: DayFlow first-run works end-to-end. |
| 2 | **CM9** (DayFlow-via-plugin) | Concrete test loop. If plugin can run DayFlow, plugin is functional enough to ship. |
| 3 | **F1** (plugin manifest schema) | Technical blocker. Solvable in hours once Claude Code plugin docs consulted. |
| 4 | **F2** (content mapping — `sutra/` → skills/commands/resources) | Required by F1 and CM9. |
| 5 | **F15** (Asawa-leak audit) | D29 hard constraint. Gate before any publish. |

### Tier 2 — required before listing goes live

| Rank | Factor | Reason |
|:-:|---|---|
| 6 | **F7** (hooks portability) | Which holding hooks ship externally. Partial in `sutra/package/MANIFEST.md`. |
| 7 | **F8** (enforcement tier selection at install) | Depth defaults per profile. |
| 8 | **F12** (profile onboarding — individual/project/company) | DayFlow picks "company" profile → live test. |
| 9 | **F5** (marketplace repo shape, Asawa-free) | Blocks `plugin.json` homepage URL. |
| 10 | **F19** (license decision) | Blocks first publish (currently UNLICENSED). |

### Tier 3 — parallel / deferrable

F3, F4, F6, F9, F10, F11, F14, F16, F17, F18, F20, CM5 (Friend-0 — grows organically from 3).

### Deferred (per founder direction 2026-04-18: "focus on functionality, not GTM")

CM1, CM2, CM4 (AI-generated later), CM6, CM7 (already decided), CM8, Phase D funnel, Phase F pricing tiers.

### Next action — P4 DEEPEN (one chunk per session, no agents)

Per founder direction 2026-04-18 (no agents, incremental sessions), P4 starts in a SEPARATE session. When that session opens, it picks exactly ONE of the following as its chunk:
- **Chunk A**: Read Claude Code plugin docs → draft `plugin.json` skeleton (F1)
- **Chunk B**: Map DayFlow's current CEO session ops → candidate plugin skills/commands list (F2 + CM9, doc-only)
- **Chunk C**: Script the T+0 → T+60s plugin first-run (CM3 artifact, doc-only)

Each chunk produces one artifact, commits, and stops. No multi-chunk sessions. No subagent fanout.

---

## P4 DEEPEN — QUEUED

Per top-3 factors from P3. Each produces:
- A concrete artifact (plugin.json filled out; skill list locked; first-run script drafted)
- A sub-DAG if block-recursion finds sub-factors
- A self-rated confidence score

---

## P6 MEASURE — QUEUED

- Convergence: does additional analysis change conclusions?
- Omission audit (fresh Codex context, not this conversation)
- Per-block self-ratings aggregate
- If overall confidence < 0.85 → loop back to weakest factor's phase
- If ≥ 0.85 → publish DAG + begin implementation

---

## Trace log

| Timestamp | Phase | Action | Cost est |
|---|---|---|---|
| 2026-04-18 ~19:15 | P0 | Classified as Complicated/TRAVERSE | $0.02 |
| 2026-04-18 ~19:25 | P1 | Enumerated 20 factors via factor-decomposition skill | $0.30 |
| 2026-04-18 ~19:30 | GATE | Paused awaiting founder validation | — |
| 2026-04-18 ~22:55 | P2 | CLEARED — 5 decisions locked; functionality > GTM pivot; DayFlow = canary (CM9 added); no agents / incremental sessions rule locked | $0.50 |

---

## Open decisions (parked, surface at correct phase)

| # | Decision | Surfaces at |
|---|---|---|
| D-A | Marketplace repo name (A: `sutra/sutra`, B: `sutra-os/sutra`, C: personal-handle short-term) | P3 after F5 deepen |
| D-B | License choice (MIT vs custom vs keep UNLICENSED) | P4 F19 deepen |
| D-C | Deprecate `npx sutra-os` or keep both channels? | P4 F17 deepen |
| D-D | Friend-0 identity + pilot plan | P4 F18 deepen |
| D-E | Enforcement tier defaults per profile | P4 F8 deepen |

---

_P2 CLEARED 2026-04-18. Next session picks ONE P4 chunk (A/B/C above), produces ONE artifact, commits, stops. No agents. No multi-chunk sessions._
