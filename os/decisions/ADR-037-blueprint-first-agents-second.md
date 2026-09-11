# ADR-037: Blueprint first, agents second

Purpose: record why Native adopts the ordering "write the workflow, then dispatch agents onto it, then let the run record correct the workflow" as doctrine, where that doctrine and its vocabulary live, and how the six product layers sort under it.

| Field | Value |
|---|---|
| **Status** | Proposed (authored 2026-09-11; Accepted on founder ratification) |
| **Scope** | Native canon: adoption of pillar P22, vocabulary by reference, phase sort of the six product layers |
| **Owner** | Sutra Engine charter (D0 Asawa Inc. > D1 Sutra OS) |
| **Updated** | 2026-09-11 |
| **Source inputs** | artifact "Blueprint First, Agents Second" (2026-09-10), `holding/website/native/platform/model/workflow-engine.html`, `holding/website/native/the-six-layers.html` (v2, 2026-09-08), `holding/website/native/the-system-simply.md` |
| Driver | founder direction 2026-09-11: "Add this to the native documentation", pointing at the artifact |

## Context <a id="context"></a>

- The website's Vocabulary layer already splits the two halves of a unit of work: the Workflow is the written, stateless blueprint and the Engine is born at the workflow's first run (`workflow-engine.html:75`, `:94`). Two axioms, X1 and X2, make the split total (`workflow-engine.html:325-326`).
- None of that is in `sutra/os` canon. A grep of `sutra/os/**/*.md` for X1, X2, "naked work" or "stateless blueprint" returns 0 hits outside archives (checked 2026-09-11). `primitives/workflow.md` holds the Workflow type; no canon file states an ordering between authoring and dispatch.
- The six-layers front door lists the product layers in time order, 1 Ontology through 6 Tooling (`the-six-layers.html:199-204`), and says "Marketplaces and tooling equip the agent before it runs" (`:159`). It does not say which layers are authored before any run and which only execute.
- Consequence: the principle the system leans on was implicit across three pages and one artifact. No part-file, hook or review could cite it.

## Decision <a id="decision"></a>

1. **Adopt the ordering as doctrine.** The rule itself is stated once, in pillar [P22](../native/pillars/P22-blueprint-first-agents-second.md). This ADR records why and does not restate it.
2. **Vocabulary by reference.** Canon cites `workflow-engine.html:75` and `:94` for the written and grown halves and `:325-326` for X1 and X2. No canon file restates them and no new primitive is minted; they are axioms over the existing Workflow and Engine.
3. **Phase sort of the six product layers.** Layer numbers stay the site's time order. The phase sort is this ADR's.

| Layer (site number) | Phase | Why |
|---|---|---|
| 1 Ontology | Blueprint | what exists and how it connects, authored before any run |
| 2 Workflow design | Blueprint | how each outcome is produced, the written half |
| 5 Marketplaces | Blueprint | supplies playbook shapes before a run; your limits stay yours |
| 3 Agents | Run | who or what executes the written workflow |
| 6 Tooling | Run | what the agent may reach during execution (Inference: the site says tooling "equips before it runs"; sorted to Run because tooling is reached, not authored) |
| 4 Feedback | Loop | run record corrects the model and the playbooks, with approval |

4. **Where the thesis is stated in the documentation spine.** L1 Theory: the SHAPE, RUN, RECORD, GROW loop (`the-system-simply.md:36-45`, the markdown source, not the HTML render). L2 Vocabulary: Workflow and Engine, X1 and X2. L3 Platform: System of Process is the blueprint store, Orchestration plus Host is the run, System of Record is the loop. L4 Engineering, L5 Products and L6 Governance build, sell and police it. Canon home: this ADR plus P22, indexed in `NATIVE-ENGINE.md` section 5.
5. **Two different sixes.** The product has six layers (the six-layers page). The documentation spine has six layers (L1 Theory through L6 Governance). Writers name which one they mean.

## The gap between the phases today <a id="gap"></a>

**Current rule** as of 2026-09-11: X2 holds in doctrine and is PARTIAL in the runtime. The user-kit has no `workflows/` directory and zero runtime workflow instances, and "no engine is ever born" (`workflow-engine.html:371-378`). The hop from "workflow fired" to "agent wrote the result" without Claude in the founder's own session is v1.3 scope. The artifact's piece-by-piece status table is not carried into canon; it is a dated snapshot and one of its rows conflicts with that page.

## Consequences <a id="consequences"></a>

- Part-files, hooks and reviews can cite ADR-037 or P22 for "no run from a blank prompt".
- Dispatching an agent with no workflow and no declared done-check is a P22 falsification. Operationally it is already blocked by the atom floor and dispatch gate (plugin 2.260.2).
- `NATIVE-ENGINE.md` section 3 counts corrected to the file inventory (pillars 14 to 23; ADRs 20 to 38, the two files sharing ADR-030 recorded as a pre-existing collision); section 5 gains rows for ADR-032 through ADR-037.
- Reviews: codex design-review round 1 CHANGES-REQUIRED (3 P1: 2 accepted, 1 refuted with a wording fold; 4 P2), round 2 pending on the folded files; DeepSeek design-review ADVISORY (3 P2 folded). Records under `.enforcement/codex-reviews/` and `.enforcement/deepseek-reviews/`.

## Not adopted <a id="not-adopted"></a>

- Renumbering the six-layers page to match the phase sort. The numbers are time order and the page is founder-owned.
- Promoting X1 and X2 to new section 2 primitives (source-fidelity rule F5).
- A new "Blueprint" primitive. Workflow already is it.
- Carrying the artifact's runtime status table into canon.

---

provenance: {author: claude, date: 2026-09-11, inputs: [artifact da61ccf3 "Blueprint First, Agents Second" 2026-09-10, workflow-engine.html, the-six-layers.html v2 2026-09-08, the-system-simply.md, founder direction 2026-09-11], review: dual-lane, supersedes: none, confidence: high, gaps: [codex round 2 pending at authoring; runtime gap per workflow-engine.html:371-378]}
