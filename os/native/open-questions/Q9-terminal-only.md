---
part-id: Q9
bucket: open-questions
template: research-log
parity-source: §14.10 Q9
parity-source-sha256: ca9e863bbf4ab33e4f13db4c8221f06863b64b28aae282666c071fd3b1e692e4
status: ANSWERED
answered: 2026-05-09
authored: 2026-05-09
---

# Q9: Surface scope — terminal-only v1 vs web/app v1

## Question

Verbatim per §14.10 row Q9 (post-2026-05-09 ratification): the row records the resolved answer in place of an open prompt. The original question shape was: does v1 ship terminal-only, or does it also include a web / mobile-app surface?

## Why it matters

Surface count is the single biggest scope multiplier. Each non-terminal surface adds frontend, auth, session, deploy, ops, design — easily 3-5× engineering load for the same feature set. Terminal-only v1 aligns with founder-portfolio (Q1) and NG7 HARD-rule (Q2). Adding web/app v1 inflates v1 ship cost, dilutes wedge focus, and competes for the engineering hours that should harden v1 invariants.

## Default if unanswered

**Smaller v1 TAM accepted; broader TAM via web/app comes after PMF** (per §14.10 row Q9 "Default if unanswered" column).

## Answer

**Stay terminal-only v1.** Web/app surfaces are deferred to v2+. Smaller v1 TAM is consciously accepted; broader TAM via web/app comes after PMF. The terminal surface gets the engineering hours and design oxygen v1 needs to land its invariants cleanly. Q2 NG7 HARD-rule depends on this answer staying terminal-only.

## Sources informing the answer

- Founder voice 2026-05-09 (this session) — ratification statement captured in §14.10 row Q9.
- Canon `NATIVE-ENGINE.md` §14.10 row Q9 default ("Smaller v1 TAM accepted; broader TAM via web/app comes after PMF").
- Cross-link Q2 NG7 — non-technical TAM blocked by terminal-only choice; both choices co-bind.
- Memory `feedback_no_Sutra_sycophancy` — Native runs on Claude Code substrate; terminal is the native habitat.
- Canon `NATIVE-ENGINE.md` §14.7 — ROUTE/RUN/EMERGE surfaces all live in terminal v1.

## References

- `NATIVE-ENGINE.md` §14.10 row Q9
- `NATIVE-ENGINE.md` §14.7 surface map
- `Q2-ng7-non-tech.md` (sibling — non-tech NG depends on terminal-only)
- `../surfaces/route.md`, `../surfaces/run.md`, `../surfaces/emerge.md` (downstream — terminal-surface part-files)
