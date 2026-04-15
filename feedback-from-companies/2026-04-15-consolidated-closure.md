# Sutra Response — Consolidated Closure (2026-04-15)

**From**: CEO of Sutra
**Depth**: 5/5
**Scope**: Close feedback items addressed by today's D27/D28 + D18 + boundary + feedback-sweep work.
**Purpose**: Prevent re-processing of resolved feedback in future sessions (per founder directive: "don't redo anything").

---

## Items CLOSED (addressed by today's shipments)

| Feedback file | Resolution | Commit(s) |
|---|---|---|
| `dayflow/os/feedback-to-sutra/2026-04-06-boundary-hook-gap.md` | Boundary hook hardened to fail-CLOSED + active-role file written. Submodule-as-own-repo case handled. | R4 fix — `729b7d2` and cascade |
| `dayflow/os/feedback-to-sutra/2026-04-06-depth-block-skipped.md` | D28 per-turn enforcement: markers cleared on every `UserPromptSubmit`, dispatcher HARD-blocks missing depth block. | `21e797f` |
| `dayflow/os/feedback-to-sutra/2026-04-06-v17-infrastructure-gaps.md` | D18 Milestone 1 shipped: `npx sutra-os@latest` now delivers 29 hooks + 22 OS core docs + templates + `.claude/settings.json` wiring. | `5ecf083`/`41288e6`/`625ba51`/`f25378d` |
| `dayflow/os/feedback-to-sutra/2026-04-06-verify-gate-miss.md` | `verify-connections.sh` re-run this session; billu minimal-tier exception added. Regression tests for D27/D28 + D13 shipped. | `64709a2`/`0d7c0be` |
| `dayflow/os/feedback-to-sutra/2026-04-15-v1.9-upgrade-audit-gaps.md` | GAP A (manifest regex) + GAP B (stderr) both fixed. | `3ab693e` |
| `billu/os/feedback-to-sutra/2026-04-15-policy-without-mechanism-rca.md` | All 7 root causes addressed: D27/D28 gates + D18 packaging + R1 tier flag + R4 fail-closed boundary. | See `2026-04-15-billu-response.md` (prior) + this session's chain |
| `billu/os/feedback-to-sutra/2026-04-15-rca-sutra-not-deployed-on-billu.md` | Same as above — D18 installer can now deploy full manifest; billu can opt to tier-1-governance. | `3ab693e` |
| `billu/os/feedback-to-sutra/2026-04-15-protocol-emergence-model.md` | R1 (tiered profiles) SHIPPED. E2/E3 (LEARN pathway, harvester) PARKED — see Deferred below. | `3ab693e` |
| `ppr/os/feedback-to-sutra/2026-04-15-ppr-archive-learnings.md` | Signal noted: two archives in Q2 2026 at scaffold stage. Defer acting until third data point — not a pattern yet. | Logged, no code change |

## Items DEFERRED (explicit, multi-session)

| Item | Why deferred | Triggers for revisit |
|---|---|---|
| **R2** — company-creation as PROTO-000 change | Requires lifecycle redesign in `/sutra-onboard`. Current onboarding works. | Next `/sutra-onboard` or when a new company onboards |
| **R3** — `sutra-doctor` tool | Multi-session build. Would centralize today's ad-hoc checks (verify-connections, MANIFEST conformance, hook-integrity). | When 3rd manifest/hook drift incident surfaces |
| **E2** — LEARN → protocol promotion pathway | Emergence model design — founder parked. | Revisit after 2-3 companies have populated `os/protocols/` with promoted candidates |
| **E3** — Protocol harvester | Depends on E2. | Same |
| **Older dayflow 04-14 feedback** (departments derivation, lifecycle governance, compliance depth4) | Not re-read this session to avoid redo. Flag for next dayflow session. | Next dayflow focused session |
| **Maze feedback** (supabase org confusion, pipeline stress test, 2026-04-04/05) | Maze on v1.7, deprioritized per Q2 focus memory. | Next maze focused session or Q3 revival |

## Policy going forward

Each feedback file now gets one of three states:
- **CLOSED-in-response**: resolved, listed here with commit chain. Can be archived.
- **OPEN**: actively work item (none currently outside this list).
- **DEFERRED**: logged with revisit trigger. Not re-read unless trigger fires.

On next session, read only OPEN items and files newer than 2026-04-15.

