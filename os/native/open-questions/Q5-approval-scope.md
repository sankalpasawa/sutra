---
part-id: Q5
bucket: open-questions
template: research-log
parity-source: §14.10 Q5
parity-source-sha256: 152941c3b8aadc12e233381f74a8bb72b4a474d1b24365dd940c0029ea312675
status: ANSWERED
answered: 2026-05-09
authored: 2026-05-09
---

# Q5: Approval scope — single-founder vs multi-party

## Question

Verbatim per §14.10 row Q5 (post-2026-05-09 ratification): the row records the resolved answer in place of an open prompt. The original question shape was: is the v1 approval gate single-founder (one approver, instant ratification), or multi-party (quorum / chain-of-approvers)?

## Why it matters

Approval shape is the trust boundary of Native's autonomy story. Single-founder matches the founder-portfolio wedge (Q1) — one human, fast turn-around, low ceremony. Multi-party expands TAM into operator-class teams but adds quorum-state primitive, conflict resolution, escalation, expiry-on-non-response — substantial v1 scope creep.

## Default if unanswered

n/a — answer is recorded in canon row directly; no fallback default applies once ratified.

## Answer

**Single-founder approval v1** (matches founder-portfolio wedge per Q1). Multi-party quorum is deferred per **OS-15** to v2+ when portfolio scale demands cross-approver workflows. v1 ships with one Approval primitive shape: one founder, one signal, audit-logged. Multi-party adds primitives + ledger semantics not justified pre-PMF.

## Sources informing the answer

- Founder voice 2026-05-09 (this session) — ratification statement captured in §14.10 row Q5.
- Canon `NATIVE-ENGINE.md` §8 OS-15 — multi-party approval open seam deferred to v2+.
- Canon `NATIVE-ENGINE.md` §6 — Approval ledger v1 single-signer schema.
- Cross-link Q1 founder-portfolio persona — single-human assumption baked in.
- Cross-link Q13 (§12.4) — per-cycle execution approval gate (orthogonal to registration approval per codex round-3 distinction).

## References

- `NATIVE-ENGINE.md` §14.10 row Q5
- `NATIVE-ENGINE.md` §8 OS-15
- `NATIVE-ENGINE.md` §6 Approval ledger
- `Q1-persona.md` (sibling — persona drives single-founder choice)
- `../primitives/` (Approval primitive — single-signer schema)
