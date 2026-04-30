# Sutra Charter — Human-Sutra Interaction Layer (v1.0)

- **Version**: v1.0
- **Status**: instrumentation + safety guardrails (no behavior optimization)
- **Build-layer**: L0 (fleet)
- **Engine of record**: `sutra/os/engines/HUMAN-SUTRA-ENGINE.md` (shipped at commit 192bea4)
- **ADR (locked decisions)**: `sutra/os/decisions/ADR-001-h-sutra-9cell-grid.md` (accepted at commit b88b7cc)
- **Skill**: `sutra/marketplace/plugin/skills/human-sutra/SKILL.md` (shipped at commit 106a94a)
- **Classifier**: `sutra/marketplace/plugin/skills/human-sutra/scripts/classify.sh` (shipped at commit 7a32af4)
- **Founder direction**: D42 in `holding/FOUNDER-DIRECTIONS.md` (shipped at commit 8305df8)
- **Quick-card**: shipped at commit a00cda3
- **Activation doc**: `sutra/marketplace/plugin/skills/human-sutra/ACTIVATION.md` (shipped at commit a372f8b)
- **Plugin manifest bump**: shipped at commit 9910910
- **Codex verdicts**:
  - Prior DESIGN consult brief: `holding/research/2026-04-30-h-sutra-layer-codex-consult.md`
  - PLAN consult R2 PASS, DIRECTIVE-ID 1777572677: `.enforcement/codex-reviews/2026-05-01-h-sutra-v1.0-plan-consult.md`

This charter is the **policy** layer. The ADR is the **lock** (what is decided). The engine is the **bound** that gathers project memory + time + context around the bound skill. The skill is the **raw rule**. This document explains HOW the charter applies the locked ADR-001 decisions across every founder ↔ Sutra ↔ Sutra interaction.

---

## Purpose

Per founder direction D42 (2026-05-01):

> "first I want to institute the above framework, so I get visibility of the flow and then influence it as per the way which is efficient"

This is **Visibility Before Influence**. v1.0 ships classification + logging + four safety guardrails. v1.1+ ships behavior-optimization rules — only after 100-500 turns of instrumented data tell us where the real friction lives. Until then, every change risks optimizing on intuition (memory `[Wait for data before optimizing]`).

The charter classifies every founder→Sutra, Sutra↔Sutra, and Sutra→founder act into a single MECE scheme so flow becomes observable, ADR-driven evolution becomes auditable, and downstream rule changes are anchored to evidence.

---

## The 9-cell grid

Two axes, three values each, nine cells.

|  | QUERY | ASSERT | DIRECT |
|---|---|---|---|
| **INBOUND** (founder → Sutra) | IN-QUERY (`"what is X?"`) | IN-ASSERT (`"you missed Y"`) | IN-DIRECT (`"do X"` / `"build it"`) |
| **INTERNAL** (Sutra ↔ Sutra) | INT-QUERY (subagent asks main for context) | INT-ASSERT (codex verdict / subagent result) | INT-DIRECT (main dispatches subagent) |
| **OUTBOUND** (Sutra → founder) | OUT-QUERY (CLARIFY) | OUT-ASSERT (INFORM / DISAGREE / ACK) | OUT-DIRECT (ASK·LATER / HANDOFF / CASCADE) |

Verbs are CQRS-extended: **QUERY** (read, no state change), **ASSERT** (declare a fact / claim), **DIRECT** (request state change / action). MECE holds because every act is exactly one of {read, tell, ask-to-act} along exactly one of {founder→sutra, sutra↔sutra, sutra→founder}.

### Classification precedence (codex P1.1 fold)

A single turn often carries multiple acts. The principal act is the highest-precedence verb present; the rest log as `mixed_acts`.

```
DIRECT  >  QUERY  >  ASSERT
```

Rationale: directives have the highest blast radius and own the routing; questions still gate execution but never override a clear directive; assertions are the lowest-priority side channel.

| Example input | Principal | Mixed | Why |
|---|---|---|---|
| `"you missed Y, fix it"` | DIRECT | [ASSERT] | imperative present → DIRECT wins |
| `"should I ship X? do it now"` | DIRECT | [QUERY] | imperative present → DIRECT wins |
| `"I think that is done. Is it done?"` | ASSERT | [QUERY] | no directive → QUERY does NOT promote over ASSERT |
| `"what is the status?"` | QUERY | [] | pure read |
| `"this is wrong"` | ASSERT | [] | pure tell |

---

## The 3-stage diagram

Every turn flows through three stages inside Sutra. Stages are owned, not interchangeable.

```
   founder              SUTRA (the operating system)
  +--------+        +---------------------------------------------+
  |        |  IN-*  |  STAGE 1: INTAKE                            |
  |        | -----> |  classify · confidence-gate · denylist-flag |
  |        |        +-----------------------+---------------------+
  |        |                                | (verb · tags · REV) |
  |        |                                v                     |
  |        |        +---------------------------------------------+
  | HUMAN  |  INT-* |  STAGE 2: PROCESSING                        |
  |        |  <-->  |  reasoning · subagent dispatch · hooks      |
  |        |        |  Anthropic 5 patterns · codex consult       |
  |        |        +-----------------------+---------------------+
  |        |                                | (drafts only)       |
  |        |                                v                     |
  |        |        +---------------------------------------------+
  |        | OUT-*  |  STAGE 3: SURFACE                           |
  |        | <----- |  per-turn blocks · OUT-{Q|A|D} · header tag |
  +--------+        +---------------------------------------------+
```

### Stage ownership invariants (codex P1.1 + P2.3 fold)

| Stage | Owns | Does NOT own |
|---|---|---|
| **STAGE 1 — Intake** | inbound classification (verb · direction · tags) · confidence gate · irreversible-domain flag | execution · founder-facing emission · subagent dispatch |
| **STAGE 2 — Processing** | internal reasoning · subagent dispatch (INT-*) · hook execution · codex consult · drafting candidate outputs | inbound classification (Stage 1's job) · founder-facing surfacing (Stage 3's job) |
| **STAGE 3 — Surface** | ALL founder-facing emission (in-band + out-of-band) · header tag · per-turn governance blocks · log row append | reasoning · classification · subagent dispatch |

**Stage-3-only emission invariant** (ADR-001 Rule 2): only Stage 3 may emit founder-visible output. Stage 1 and Stage 2 may **draft** candidate emissions; they MUST NOT surface them. A subagent mid-execution that needs to ask the founder promotes its draft up the chain via INT-ASSERT; Stage 3 then re-emits as OUT-QUERY (or demotes to OUT-ASSERT under the guardrails below).

Single audit point. Single surface. No leakage.

---

## The 3 orthogonal tags

```
TENSE     past | present | future        (what content references)
TIMING    now  | later   | recurring     (when execution happens)
CHANNEL   in-band | out-of-band          (outbound delivery surface)
```

Why these three:

- **TENSE** separates "what shipped" from "what's shipping" from "what will ship". Load-bearing for INFORM (past) vs ASK·LATER (future) routing.
- **TIMING** separates immediate execution from deferred reminders from cron-like recurring work. Load-bearing for routing into Sutra schedule vs immediate action.
- **CHANNEL** separates terminal output from out-of-band notifications (Resend email, push, Slack, daily pulse). Load-bearing for surface selection.

AUDIENCE / SEVERITY / CONTINUITY were considered and deferred to v1.1+ per ADR-001 Alternatives §c.

---

## REVERSIBILITY as execution metadata

REVERSIBILITY is captured per turn but lives as **execution metadata on the act**, NOT as a 4th tag (codex P2.4 fold). Tags describe content/timing/surface; REVERSIBILITY describes downstream consequence and gates safety rules.

Two fields:

| Field | Values | Source |
|---|---|---|
| `reversibility` | `reversible` \| `irreversible` | classifier (denylist match → irreversible) |
| `decision_risk` | `low` \| `medium` \| `high` | classifier (denylist + sensitive-domain keywords) |

Stage 3 consults BOTH before emitting OUT-QUERY. For non-denylist domains, the default is **proceed on stated assumptions** with bounded retry — the over-asking pathology is killed at the surface layer, not at the gate.

### Irreversible-domain denylist (codex P1.2 fold — 6 categories)

For these categories, "proceed with assumption" is **forbidden** regardless of what the REVERSIBILITY heuristic returns. Acts touching these domains route to refuse-and-re-prompt:

1. **Destructive file ops** — `rm -rf`, `git reset --hard`, `git push --force`, mass-delete, mass-rename
2. **External sends** — Resend / email / Slack / Discord / SMS / push notifications crossing the founder→external boundary
3. **Founder-reputation outputs** — anything signed as Sankalp / Asawa / Sutra to an external party (investor, client, hire)
4. **Money movement** — Stripe / wire / PSP / crypto / payroll
5. **Legal / compliance** — contracts, ToS, privacy policy, regulatory filings
6. **Irreversible publication** — git push to public repos, npm publish, Play Store / App Store release, public website publish

For all OTHER domains (the vast majority), the default is "proceed on stated assumptions" with bounded retry (Stage 1 § below).

---

## Translation table

The h-sutra Layer is a **superstructure** over existing Input Routing — it does NOT replace it. One canonical classification pass per turn (codex P2.6 backward-compat fold). The existing Input Routing TYPE classifier emits its TYPE; the h-sutra classifier consumes that TYPE and maps to the 9-cell verb.

| Input Routing TYPE | 9-cell direction × verb | Note |
|---|---|---|
| `question` | IN-QUERY | direct mapping |
| `feedback` | IN-ASSERT | direct mapping |
| `direction` | IN-DIRECT | direct mapping |
| `task` | IN-DIRECT | direct mapping |
| `new-concept` | IN-QUERY (default) | intent-based override possible to IN-ASSERT when content is clearly a critique-of-status-quo rather than an inquiry |

**Backward-compat invariant**: existing Input Routing block format/field-order/content remains unchanged. The h-sutra layer adds a header tag and a log row — it does NOT mutate the existing block. Golden-output diff against pre-implementation baseline = 0.

---

## Stage 1 — Intake

Stage 1 receives the raw founder turn and produces a classified record. Owners: classifier script + Input Routing skill (already shipping).

**Procedure**:

1. Read founder input + Input Routing TYPE (already classified upstream).
2. Apply translation table → preliminary verb.
3. Apply classification precedence DIRECT > QUERY > ASSERT for mixed acts → principal_act + mixed_acts.
4. Run 4 checks (existing INTAKE skill discipline):
   - **Surface Assumption** — what is the input assuming about state, scope, prior context?
   - **Manage Confusion** — is the referent resolvable? if not, mark Stage 1 FAIL.
   - **Push Back** — does the directive contradict an active charter / D-direction / hard rule?
   - **Enforce Simplicity** — is there a simpler interpretation that would change the route?
5. Compute REVERSIBILITY + decision_risk (denylist scan + sensitive-domain keywords).
6. Compute tags (TENSE / TIMING / CHANNEL).
7. Emit classified record to Stage 2. Stage 1 does NOT surface anything to the founder.

### Confidence gate + bounded retry rule (codex P1.2 fold)

If Stage 1 FAILS (referent unresolvable, ambiguous direction, multiple irreconcilable interpretations), it emits an OUT-QUERY (CLARIFY) draft up to Stage 3 via INT-ASSERT. Stage 3 surfaces the CLARIFY question.

After ONE CLARIFY attempt for the same turn:

| REVERSIBILITY × decision_risk | Action on second Stage 1 FAIL |
|---|---|
| reversible / low | proceed on stated assumptions (logged as OUT-ASSERT before action) |
| reversible / medium | proceed on stated assumptions; surface assumption explicitly in OUT-ASSERT |
| irreversible / any · OR · denylist hit | refuse + escalate (OUT-ASSERT DISAGREE; require explicit IN-DIRECT re-prompt) |

This terminates the gate-fail loop. No infinite polite paralysis. No silent wrong-action either.

---

## Stage 2 — Processing

Stage 2 owns reasoning + subagent dispatch + hook execution. Anthropic's 5 patterns ("Building Effective Agents") are **preferred initial handlers**, NOT strict bindings (codex P2.5 fold). The classifier does not force a pattern — it suggests one based on the inbound class. Stage 2 is free to escalate or substitute.

| Inbound class | Preferred initial handler | Substitution allowed when |
|---|---|---|
| IN-QUERY | Routing | scope expands → promote to Orchestrator-Workers |
| IN-ASSERT | Evaluator-Optimizer | claim is structural → also dispatch Routing for context |
| IN-DIRECT | Orchestrator-Workers | task is atomic → demote to Routing |

Prompt Chaining and Parallelization are internal strategies applicable under any cell — they describe HOW Stage 2 decomposes work, not WHAT cell to enter.

**Internal traffic** (the INT-* cells):

| Cell | Sender → Receiver | Example |
|---|---|---|
| INT-QUERY | subagent → main (or sibling) | "what's the path to the charter?" |
| INT-ASSERT | subagent → main | results returned · codex verdict · CLARIFY draft promoted |
| INT-DIRECT | main → subagent | "implement Task 2.1" · "review this diff" |

INT-* traffic is logged but never surfaced as-is. If the founder needs to see internal traffic, Stage 3 paraphrases via OUT-ASSERT (INFORM).

Stage 2 may DRAFT founder-visible candidates but MUST NEVER surface them directly. All drafts route up to Stage 3.

---

## Stage 3 — Surface

Stage 3 owns ALL founder-facing emission, both procedural (per-turn) and event-driven.

### Procedural per-turn surfacing

These run on every turn that has tool calls:

- **Stated Depth** — the DEPTH + ESTIMATION block (existing skill `core:depth-estimation`).
- **Pre-Action BLUEPRINT** — the BLUEPRINT block (existing skill `core:blueprint`, engine `sutra/os/engines/BLUEPRINT-ENGINE.md`).
- **Readability Gate** — applies at output time (existing skill `core:readability-gate`).
- **Output Trace** — one-line OS trace (existing skill `core:output-trace`).
- **Header tag** — the new visible string emitted on every response (see § Header tag format).

### Event-driven surfacing

These emit only when the cell + gate condition triggers:

| Cell | When | Form |
|---|---|---|
| OUT-QUERY | Stage 1 FAIL (1st attempt) · OR · DIRECT + irreversible/denylist | CLARIFY (must satisfy 3 guardrails below) |
| OUT-ASSERT | every Stage-3 emission of factual content (default form) | INFORM · DISAGREE · ACK |
| OUT-DIRECT | scheduling work · handoffs · cascades to next session | ASK·LATER · HANDOFF · CASCADE |

### OUT-QUERY guardrails (codex P1.2 fold)

Every OUT-QUERY MUST satisfy ALL three before it surfaces. Failure of any one demotes to OUT-ASSERT (INFORM) with stated assumption:

1. **Names exact missing variable** — the question targets a specific named variable (file path · A vs B · numeric value), not an open-ended fishing prompt.
2. **Explains why default is unsafe** — gate-condition declaration says why proceeding with the default would be wrong (`"irreversible publication"` · `"ambiguous referent could overwrite wrong file"`).
3. **One-turn-answerable** — the founder can answer in a single message (yes/no · A/B/C · a name · a path) — not a multi-step deliberation.

If any of (1)/(2)/(3) fails, demote to OUT-ASSERT (INFORM) and proceed-with-assumption. This kills the over-asking pathology at the surface layer.

### Channels

| Channel | Mechanism | When |
|---|---|---|
| `in-band` | current conversation (terminal output / web UI) | default for OUT-* in active sessions |
| `out-of-band` | push notification · ScheduleWakeup · cron (CronCreate) · email (Resend) · daily pulse · audit log (`.enforcement/`) · gh issues | TIMING=later · TIMING=recurring · founder away · cross-session handoff |

CHANNEL is decided by Stage 3 based on the (TIMING, founder-presence, severity) triple. Default is `in-band`.

---

## Logging schema

One row per turn. Atomic append to `holding/state/interaction/log.jsonl`. JSONL = one JSON object per line, no commas between rows.

Fields:

| Field | Type | Notes |
|---|---|---|
| `ts` | string (ISO-8601 UTC) | turn timestamp |
| `turn_id` | string (uuid or session-prefixed counter) | correlation key; same turn under retry shares this id (codex Phase 3 fit-point §5) |
| `direction` | `INBOUND` \| `INTERNAL` \| `OUTBOUND` | from grid |
| `verb` | `QUERY` \| `ASSERT` \| `DIRECT` \| `STAGE-1-FAIL` | from grid |
| `principal_act` | same as verb (semantic alias) | for joins / aggregation clarity |
| `mixed_acts` | array of strings | secondary acts present (precedence-demoted) |
| `tense` | `past` \| `present` \| `future` \| `null` | nullable when act is tense-agnostic |
| `timing` | `now` \| `later` \| `recurring` | from tags |
| `channel` | `in-band` \| `out-of-band` | from tags |
| `reversibility` | `reversible` \| `irreversible` | execution metadata |
| `decision_risk` | `low` \| `medium` \| `high` | execution metadata |
| `stage_1_pass` | bool | true = classifier resolved cleanly |
| `stage_3_emission_type` | `OUT-QUERY` \| `OUT-ASSERT` \| `OUT-DIRECT` \| `none` | what Stage 3 actually surfaced |
| `input_routing_type` | `direction` \| `task` \| `feedback` \| `new-concept` \| `question` \| `null` | source TYPE we translated from (null for INT-*) |

Example row:

```json
{"ts":"2026-05-01T14:23:11Z","turn_id":"sess-7f2-0042","direction":"INBOUND","verb":"DIRECT","principal_act":"DIRECT","mixed_acts":["ASSERT"],"tense":null,"timing":"now","channel":"in-band","reversibility":"reversible","decision_risk":"low","stage_1_pass":true,"stage_3_emission_type":"OUT-ASSERT","input_routing_type":"task"}
```

Failure policy (Phase 3.4): fail-CLOSED for the log row (skip the append on classifier crash; never half-write); fail-OPEN for downstream skills (a missing log row MUST NOT block Edit/Write/Bash).

---

## Header tag format

Visible string emitted by Stage 3 in every response. This IS the visibility instrument:

```
[<DIRECTION>·<VERB> · TIMING:<...> · CHANNEL:<...> · REV:<...> · RISK:<...>]
```

Rendered example:

```
[INBOUND·DIRECT · TIMING:now · CHANNEL:in-band · REV:reversible · RISK:medium]
```

Five rendered examples covering the most common cells:

```
[INBOUND·QUERY  · TIMING:now   · CHANNEL:in-band      · REV:reversible   · RISK:low]
[INBOUND·DIRECT · TIMING:now   · CHANNEL:in-band      · REV:irreversible · RISK:high]
[INBOUND·DIRECT · TIMING:later · CHANNEL:out-of-band  · REV:reversible   · RISK:low]
[INBOUND·ASSERT · TIMING:now   · CHANNEL:in-band      · REV:reversible   · RISK:low]
[OUTBOUND·QUERY · TIMING:now   · CHANNEL:in-band      · REV:irreversible · RISK:high]
```

The header tag occupies one line. Founder reads it in <2s. Aggregation across turns gives a flow distribution.

---

## v1.0 limits

**Deliberately included** (in scope):

- 9-cell classification (3 verbs × 3 directions)
- 3 orthogonal tags (tense / timing / channel)
- REVERSIBILITY + decision_risk as execution metadata
- 4 safety guardrails:
  - Classification precedence DIRECT > QUERY > ASSERT
  - Stage-3-only emission invariant
  - OUT-QUERY guardrails (named-var · why · one-turn-answerable)
  - Bounded retry (1 CLARIFY attempt) + irreversible-domain denylist (6 categories)
- Logging to `holding/state/interaction/log.jsonl`
- Header tag in every response

**Deliberately deferred** to v1.1+ (NOT in scope; require ADR-002+ with regression test):

- Behavior-optimization rules (over-asking fix beyond the bounded-retry guardrail)
- AUDIENCE tag (who-is-this-for routing)
- CONTINUITY tags (CONTINUE / RESUME / REFINE — turn-to-turn linkage)
- SEVERITY tag (escalation pressure)
- New cells (e.g., META-* for self-reflection traffic)
- Confidence-gate threshold tuning
- Log rotation / retention policy

Per D42: visibility before influence. We instrument, we collect 100-500 turns of real data, we then write ADR-002+ to influence flow based on observed patterns. Not before.

---

## Evolution discipline

Every change to v1.0 ships as a numbered ADR with a regression test. ADR-001 = v1.0 baseline (already accepted at commit b88b7cc). All subsequent ADRs follow this template:

```
ADR-### : <change>
  STATUS         : proposed | accepted | superseded-by ADR-###
  CONTEXT        : real interaction(s) v_n didn't catch
  DECISION       : new cell / new tag / new rule
  ALTERNATIVES   : what else was considered
  REGRESSION TEST: asserts the change catches cited interactions
                   AND keeps all prior fixtures passing
```

Rules:

- No grid change without an ADR.
- No new tag without an ADR.
- No safety-rule modification without an ADR.
- Every ADR MUST cite at least one real prior interaction the v_n schema failed to capture, and add ≥1 new fixture to `sutra/marketplace/plugin/skills/human-sutra/tests/fixtures.json` that demonstrates the new shape catches it.
- ADR-001's 13-fixture regression set MUST keep passing under every future ADR. Failure = blocker.

This is the same discipline used by the architecture-decision-record literature (Nygard 2011) and aligns with the "Visibility Before Influence" principle: changes are auditable, evidence-anchored, and reversible.

---

## References

Pattern source material the v1.0 grid + tags + rules draw from:

- **CQRS** (Command Query Responsibility Segregation) — Greg Young; Martin Fowler ("CQRS", martinfowler.com/bliki/CQRS.html); Microsoft Azure Architecture Center ("CQRS pattern"). Provides the QUERY / ASSERT / DIRECT verb axis (extended from CQS's 2-verb split).
- **MECE Pyramid Principle** — Barbara Minto, *The Pyramid Principle* (McKinsey, 1973). Provides the MECE constraint we apply to the 9-cell grid.
- **Anthropic "Building Effective Agents"** — anthropic.com/research/building-effective-agents. Provides the 5 Stage-2 patterns (Routing, Orchestrator-Workers, Evaluator-Optimizer, Prompt Chaining, Parallelization).
- **addy/agent-skills "Core Operating Behaviors"** — github.com/addy/agent-skills. Precedent for "HOB-as-checks" pattern adopted in Stage 1.
- **Cline Plan/Act architecture** — github.com/cline/cline. Closest framework analog to the Stage 1 → Stage 2 → Stage 3 separation.
- **LangGraph Human-in-the-Loop middleware** — langchain-ai.github.io/langgraph/. Reference implementation for OUT-QUERY gate semantics.
- **arXiv 2502.13069** — "Interactive Agents for Ambiguity Resolution". Empirical basis for bounded-retry termination policy.

---

## Codex consult fold

Two rounds of consult. Verdict file: `.enforcement/codex-reviews/2026-05-01-h-sutra-v1.0-plan-consult.md`.

**R1 (CHANGES-REQUIRED, 2026-05-01)** — 8 findings on the v1.0 PLAN. All 8 folded:

| Finding | Severity | Where folded |
|---|---|---|
| P1.1 — Activation/wiring missing in Phase 2; "single atomic commit" wording wrong | P1 | classification-precedence sub-section + Stage ownership invariants table (this charter) · Tasks 2.8 + 2.9 + 5.2 (PLAN) |
| P1.2 — Bounded retry + irreversible-domain denylist | P1 | REVERSIBILITY § (denylist) + Stage 1 § (bounded-retry rule) + Stage 3 § (OUT-QUERY guardrails) |
| P2.3 — Phase 1 under-covers invariants (Stage-3-only emission + emission-type negatives) | P2 | Stage ownership invariants table + Stage 3 emission rules |
| P2.4 — REVERSIBILITY framing as 4th tag | P2 | "REVERSIBILITY as execution metadata" § (NOT a 4th tag) |
| P2.5 — Anthropic patterns as strict bindings | P2 | Stage 2 § (preferred initial handlers, NOT strict bindings) |
| P2.6 — Backward-compat / superstructure framing | P2 | Translation table § (h-sutra is a superstructure over Input Routing) |
| P3.7 — Compact decision table at top of ADR-001 | P3 | folded into ADR-001 (not this charter; charter cites the ADR) |
| P3.8 — ADR-001 ordering before fit verification | P3 | folded into PLAN task ordering (Task 2.6 ADR before Task 2.1 charter; this charter cites the locked ADR) |

**R2 (PASS, 2026-05-01, DIRECTIVE-ID 1777572677)** — verbatim verdict:

> "The fold closes all eight prior findings without introducing a new obvious gap from the text provided. Verdict: PASS."

This charter implements the R2-PASS shape verbatim.
