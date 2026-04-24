# PRIVACY — Sutra Governance Charter

*Version: v2.0.0 · Adopted: 2026-04-24 · Status: active · Owner: CEO of Sutra*

Internal governance spec for the Sutra team. Distinct from the **user-facing** sheet at `sutra/marketplace/plugin/PRIVACY.md` (what clients read) and the deployed copy at `~/.sutra/PRIVACY.md` (what runs on user machines).

## Purpose

Control **what data** Sutra collects **about its users**, **for what purpose**, **for how long**, **who can see it**, and **how it is disposed** — across all tiers (T0 founder · T1 Asawa-internal · T2 owned portfolio · T3 client-owned projects · T4 external fleet).

Privacy ≠ Security. Security protects against unauthorized access. Privacy controls collection, purpose, retention, disposal. They intersect at the boundary-guard layer but solve different problems.

## 8 Principles (ordered by enforcement priority)

1. **Data minimization** — collect only what serves a stated purpose. Signals not content.
2. **Purpose limitation** — purpose declared at collection time. Secondary use requires re-consent.
3. **Retention limits** — TTL on every captured datum. Default 30d; configurable via `SUTRA_RETENTION_DAYS`.
4. **Transparency** — user can see everything captured about them. Sheet links to `~/.sutra/feedback/auto/`.
5. **Consent + control** — user can opt out, delete, set retention. No dark patterns.
6. **Boundary enforcement** — data stays in its tier; crossing D33 requires explicit consent.
7. **Defense in depth** — allowlist derivation + regex scrub + atomic writes + 0700/0600 perms + symlink-refusal.
8. **Fail closed** — any sanitization error = skip write. Never write raw because scrub broke.

## Tiered Contract

| Tier | Default auto-capture | Retention | Fan-in to Sutra team | Consent model |
|---|---|---|---|---|
| **T0** Founder-operator | ON, full signals | 90d | Yes (founder IS team) | Implicit |
| **T1** Asawa-internal | ON, full signals | 90d | Yes | Implicit |
| **T2** Owned portfolio (DayFlow, Billu, Paisa, PPR, Maze) | ON, signals-only | 60d | Yes-with-notice | Per-install banner on first run |
| **T3** Projects (Testlify, Dharmik — client owns IP) | ON, signals-only, strictest sanitization, no code/path | 30d | Requires-explicit-consent-per-fan-in | Opt-in toggle + per-batch confirm |
| **T4** External fleet | **In-memory-only** until first `/sutra feedback` | 30d | **Off by default**; opt-in only | Opt-in; loud banner |

## Failure Modes + Primitives Map

| Mode | Risk | Primitive |
|---|---|---|
| Exfiltration (secret in commit, LLM echo) | High | `derive_signal` allowlist + `scrub_text` secondary + PROTO-004 secret-gate |
| Aggregation (benign fields re-identify) | Medium | Day-precision timestamps, no `install_id`/`project_id` in v2 signals |
| Retention creep | Medium | `sutra_retention_cleanup` in SessionStart hook (opportunistic) |
| Secondary use | High | Purpose hardcoded at collection (`override`/`correction`/etc); no runtime rebinding |
| Cross-boundary leak | High | `privacy_gate` checks consent before ANY disk write; fan-in always explicit |
| Re-identification | Medium | SHA256-truncated IDs where needed; no hostname/email/git-identity in v2 |
| Training leak | Low (Anthropic-controlled) | Pre-sanitize what we can; external dependency otherwise |
| Third-party exposure | Medium | Encrypt-at-source for sensitive fields; policy audit cadence (future) |
| Concurrent write corruption | Low | `flock` in `sutra_safe_append` when available; atomic `mv` on writes |
| Symlinked synced storage | Low | `sutra_safe_write` + `sutra_safe_append` refuse symlinks |

## Implementation Primitives (all at `sutra/marketplace/plugin/`)

| # | Primitive | Location |
|---|---|---|
| 1 | `derive_signal` | `lib/privacy-sanitize.sh` |
| 2 | `scrub_text` | `lib/privacy-sanitize.sh` |
| 3 | `privacy_gate` | `lib/privacy-sanitize.sh` |
| 4 | `signal_write` | `lib/privacy-sanitize.sh` |
| 5 | `sutra_safe_write` | `lib/privacy-sanitize.sh` |
| 6 | `sutra_safe_append` | `lib/privacy-sanitize.sh` |
| 7 | `sutra_grant_consent` | `lib/privacy-sanitize.sh` |
| 8 | `sutra_retention_cleanup` | `lib/privacy-sanitize.sh` |
| 9 | Override-count hook | `hooks/feedback-auto-override.sh` |
| 10 | Correction-signal hook | `hooks/feedback-auto-correction.sh` |
| 11 | Abandonment-signal hook | `hooks/feedback-auto-abandonment.sh` |
| 12 | SessionStart install notice | `hooks/sessionstart-privacy-notice.sh` |
| 13 | User-facing sheet | `PRIVACY.md` (copied to `~/.sutra/PRIVACY.md` on SessionStart) |
| 14 | Legacy push guard | `scripts/push.sh` (gated behind `SUTRA_LEGACY_TELEMETRY=1`) |

## Key Results (measurable)

| KR | Target | Measurement |
|---|---|---|
| KR1 | 0 secrets committed to git | PROTO-004 gate logs (already enforced) |
| KR2 | 100% captured data has declared purpose + TTL | `derive_signal` allowlist enforces; audit quarterly |
| KR3 | 0 cross-tier data crossings without matching consent ledger entry | `privacy_gate` + consent file audit |
| KR4 | `~/.sutra/PRIVACY.md` present-day coverage = 100% of captured fields | Diff sheet claims vs JSONL contents monthly |
| KR5 | Median retention ≤30d for T3/T4 | `find -mtime +30` returns zero in sampled installs |
| KR6 | Sanitization fail-closed rate = 100% | Unit + integration tests in CI; fail on any write-on-error |

## Relationship to Other Charters

- **SECURITY** (parked, not yet formalized): Privacy ≠ Security. Clean interface — Security owns access control, authentication, supply-chain integrity. Privacy owns collection/retention/disposal. They share the boundary-guard primitive (`privacy_gate` for data; separate access-gate for code execution — future).
- **TOKENS**: audit-log token budget is downstream of Privacy's retention limits. Shorter retention → less audit data → fewer tokens.
- **SPEED**: Privacy adds overhead per capture (gate check + sanitize). Budget: <1ms per hook fire. Measure via hook latency telemetry.

## Relationship to D33 Firewall

D33 is **accidental-access prevention** at the filesystem boundary (bidirectional deny between Asawa and external clients). Not a security boundary.

Privacy's `privacy_gate` + consent ledger operationalizes D33 for **data flows**:
- Between tiers (T1 ↔ T2 ↔ T3 ↔ T4)
- Between plugin and external transport (currently disabled; legacy only)
- Between user and Sutra team (via future fan-in — requires consent ledger entry per batch)

## Review Cadence

- **Monthly**: KR1-KR6 dashboard (Analytics dept pulse).
- **Quarterly**: re-read sheet vs captured fields; reconcile.
- **On each Sutra version bump**: diff privacy surface; update sheet changelog.
- **On any new data field added to any hook/lib**: must update allowlist + sheet + charter in same commit.

## Kill-Switches

Per layer:

| Scope | Kill-switch | Effect |
|---|---|---|
| Global | `SUTRA_TELEMETRY=0` | Zero capture anywhere |
| Legacy mode | `SUTRA_LEGACY_TELEMETRY=1` | Re-enables v1.9 identity+push path (deprecated) |
| Per-install | `rm -rf ~/.sutra/` | Delete all collected data |
| Per-signal-category | `SUTRA_SKIP_<CATEGORY>=1` (future) | Disable individual signal types |
| Retention | `SUTRA_RETENTION_DAYS=N` | 1-90 range; default 30 |

## Prior Art + References

- Codex design review verdict: `.enforcement/codex-reviews/privacy-design-review-2026-04-24.md` (DIRECTIVE-ID 1777036275, CHANGES-REQUIRED → 5 conditions absorbed)
- User-facing sheet: `sutra/marketplace/plugin/PRIVACY.md` v2.0.0
- Legacy model (deprecated): same sheet tail
- Asawa parked TODO: `holding/TODO.md` (Security & Privacy entry, 2026-04-24)

---

*This charter supersedes the prior telemetry contract (v1.9.0 identity stamping + outbound push to `sankalpasawa/sutra-data`). Legacy behavior gated behind `SUTRA_LEGACY_TELEMETRY=1`.*
