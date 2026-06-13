---
part-id: AB-UI
bucket: arch-blocks
template: arch-block-spec
parity-source: master/index.html §1.0.1 #so-ui + §2.F (B.1-B.5 · D.1-D.4 · F.1-F.5 · G.1-G.5 · H.1-H.4)
parity-source-sha256: 5761c9d263792207076ec97adccb9ed4f5fecc3c7a7597ad47a0ab31d6c3e278
status: DRAFT v1 — extracted from a founder-UNLOCKED §1.0.1 working draft; re-sync + promote to authoritative on §1.0.1 lock. Source SHA above = drift sentinel.
authored: 2026-06-13
governed-by: ADR-024 (arch-block canon migration, Option A)
---

# Architecture Block: UI (Consumer Product)

> First arch-block canon part-file (ADR-024 Option A). The §1.0 architecture blocks had no canon homes; this is the first migrated. Source is the founder-unlocked §1.0.1 second-order ("WORKING DRAFT, founder review pending") — captured here as DRAFT with a source SHA so drift is detectable; promote to authoritative when the founder locks §1.0.1.

## Role in §1.0

The UI block is the operator's edge of the runtime: `Human <-> [UI] -> Host -> Daemon{...} -> {SoR, External World}`. It carries **intent down and results up**. It does NOT think — the request runs on the Host (Claude CLI). Authority+Tenancy gates every access along the way. It is the block that hosts the operator-facing surfaces (and, per ADR-023, the render home of the Platform UI Kit's Governance Surfaces).

## Engine parts (MECE re-cut: 3 parts + 2 render-only annotations)

| Part | Role | Detail |
|---|---|---|
| **Channels** | transport in/out | Inbound Day-1: text chat · Slack mention · email forward · scheduled prompt (voice + screenshot Future, B.1). Outbound channel by 3-rule order: explicit > standing preference > default-to-origin, with one-step escalation when time-sensitive AND default is async (D.3). |
| **Ask** | utterance → intent read → journey fan-out | Resolves every utterance to one of 5 intent types (Task/Query/Directive/Feedback/New Idea, B.2), fans out to journeys C.1-C.5 (B.5). Multi-turn carry (B.3): recent intent, named entities, active charter, deferred follow-ups, open questions. Ask-side trust folds in here (F.1 ask-before-acting, B.4 confidence ladder). |
| **Receive** | how Native talks back | 6 modalities M1-M6 (D.1), 3 landing times sync/scheduled/async (D.2), modality routed by ask shape (D.4). Standing Surfaces are a CASE OF Receive (Daily Pulse H.3, capability map H.1, proactive surfacing H.2, weekly retro H.4). Receive-side trust folds in: M5 approval card, F.2 reversibility tags, F.3 audit replay. **Per ADR-023, the UI Kit's Governance Surfaces are a render-only area of Receive.** |

**Render-only annotations (NOT engine parts — must not leak into the engine):** Adaptation (skill modes SM1-SM3 + personalization E.1-E.4) · Need-surfaces (which JTBD a surface serves).

## Trust gates (F.x)

| ID | Rule |
|---|---|
| **F.1** | Ask-before-acting — 4 trigger classes pull Native into ask-first: high-risk (spend/send/share/commit), irreversible (delete/publish/notify/contract), new authority (no prior permission template), first-time channel/contact. Else act-and-report. |
| **F.2** | Reversibility tags — every action carries one of: **reversible** (undo window, "say undo"), **reversible-with-effort** (retract/re-issue/re-pay — doable, not free), **not-reversible** (confirming locks it in). |
| **F.3** | Audit visibility — "show me what you did and why": replays any past action (what asked / what done / why / what it'd do differently). Reads the DecisionProvenance trail (ADR-007). |
| **F.4** | Trust ladder — 4 rungs over time (Day 0-14 ask-every-external → Day 90+ runs standing routines, surfaces what it did); monotonic by default, operator can dial up/down at any rung. |
| **F.5** | Ask-vs-act cascade — ordered, first-yes-wins: irreversible→ASK(multi-step) · high-risk→ASK(one-tap) · new-authority→ASK(grant once/always/no) · first-time-channel→ASK(preview) · else ACT-and-report. |

## Error surfaces (G.x)

| ID | Rule |
|---|---|
| **G.1** | Misclassified intent — surface the read with yes/no/clarify (one focused question max) before acting on anything ambiguous. |
| **G.2** | Failed action — state the failure plainly in operator's words + 3 recovery options. **No stack traces, no codes.** |
| **G.3** | Operator override — `stop` (halt + report what completed) · `undo` (reverse if reversible, else next-best recovery) · `different approach` (discard plan, re-read ask, propose fresh). |
| **G.4** | Wrong-answer loop — ask what was wrong (facts/tone/scope/recipient/timing), correct, re-run once. Two consecutive misses → stop, ask operator to walk through what right looks like. |
| **G.5** | Learning from correction — every correction visibly acknowledged ("I noted that"), never silent, carried forward. |

## Modalities (M1-M6) + operator-visible states

**Modalities (D.1):** M1 text reply (default) · M2 Slack ping · M3 email · M4 summary card (headline/3 bullets/link/timestamp) · M5 approval-ask card (planned action + reversibility note + Approve/Adjust/Cancel) · M6 scheduled reminder.

**States:** error (G.x surfaces) · empty ("I don't know what to ask for" → capability map H.1) · onboarding (~10 min: light charter + persona read + first REAL job) · notification (outbound landings the operator didn't just ask for; cadence + quiet-hours from charter E.2).

## Invariants

1. Every utterance resolves to exactly one of 5 intent types (B.2).
2. Confidence gate always runs: high → proceed; medium/low/very-low → confirm-back before acting (B.4).
3. F.5 ask-vs-act cascade is ordered, first-yes-wins.
4. Every action carries a visible F.2 reversibility tag.
5. Channel selection applies the 3-rule order, first match wins; escalation override fires ONLY when time-sensitive AND default channel async.
6. Daily Pulse (H.3) is always 4 fixed blocks in order: Yesterday / Open / Suggested / Signal; skimmable < 60s.
7. Multi-turn context (B.3) carries 5 things across turns: recent intent (last 3-5), named entities, active charter, deferred follow-ups, open questions.
8. Authority+Tenancy gates every access (cross-cutting wrap).

## Prohibitions

- UI block does NOT think — carries intent down + results up; the request runs on the Host.
- Render-only annotations (Adaptation, Need-surfaces) must NOT leak into the engine as parts.
- G.2 failures: no stack traces / no codes — plain operator words only.
- G.1 clarify: ONE focused question, no more.
- Corrections (G.5) never silent, never repeated-without-surface.
- H.2 capability suggestions never block; decay after 2 declines.
- Operator never surprised by an unauthorized action, never nagged for one already blessed (F.1/F.5).

## Open gaps (founder-pending — inherited from §1.0.1 draft)

- Curation surface (E.5 "what do you remember about X?" forget/correct/pin) — case of Receive or its own part?
- "Empty" state has no literal §2.F spec (closest: §2.F.H).
- G.x error surfaces don't name which M-modality carries them (M4/M5 or a 7th shape?).
- Notification state spans two homes (§2.F.D modalities vs charter §2.F.E cadence).
- F.1 "grant always" implies a persisted permission template — storage home unspecified (Charter? SoR?).

## Downstream consumers

- **C1 Approval Inbox** cites F.1/F.2/F.5 + M5 (this file is now its canon anchor — replaces the frozen-monolith citation).
- **C3 What's-Running Board** cites G.2 (plain-words failures) — now anchored here.
- Platform UI Kit (ADR-023) Governance Surfaces render inside this block's Receive part.
