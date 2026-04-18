# Sutra Marketplace Deployment — Design DAG

_Workflow instance. Sutra Kernel arch flow, manual runtime (Kernel V1 build pending)._
_Started: 2026-04-18. Paused at P1→P2 gate awaiting founder validation._
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

## P2 VALIDATE — GATE (awaiting founder)

Next actions at this gate:

1. **Founder reads factor table** — approve / amend / add missing factors
2. **Coverage scoring** — drop overlap (manual, until `coverage-validator` skill ships with Kernel V1)
3. **Codex adversarial review** — independent omission check per `feedback_codex_everywhere` memory
4. **Gate criteria to advance**:
   - ≥95% of factors have founder-approved attributes
   - Codex review surfaces ≤2 missed factors (fold into list, don't block)
   - No factor marked "C < 0.3 AND U = H" (those need research before validation)

Current candidates for research-before-P3:
- **F1** (plugin schema, C=0.4, U=H) — read Claude Code plugin docs
- **F5** (marketplace repo shape, C=0.3, U=H) — pick org/repo name
- **F18** (friend-0 plan, C=0.3, U=H) — who is friend-0?

---

## P3 PRIORITIZE — QUEUED

Will be filled after P2 gate passes. Ranking formula (per kernel spec §4):
`score = impact × uncertainty / cost_of_decision_if_wrong`

Early guess (not final):
- Top candidates: F1 (manifest schema), F2 (content mapping), F13 (first-run UX)
- These shape everything else; other factors become sub-blocks under them.

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

_End P1 output. Resume: founder validates factor list → P2 VALIDATE begins._
