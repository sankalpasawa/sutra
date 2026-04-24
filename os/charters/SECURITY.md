# SECURITY — Sutra Governance Charter

*Version: v1.0.0 · Adopted: 2026-04-24 · Status: active · Owner: CEO of Sutra*

Internal governance spec for the Sutra team on protecting access, integrity, and authenticity of the plugin + its deployment surface. Companion to PRIVACY charter (which covers collection/retention/disposal of user data); Security covers **access, integrity, and authentication** of the system itself.

## Purpose

Protect against **unauthorized access**, **tampering**, and **authenticity failure** across the three distinct threat surfaces Sutra operates on. Privacy ≠ Security — Privacy asks *what data* and *how long*; Security asks *who can touch* and *can we trust it*.

## 3 Threat Surfaces (NOT one thing — each needs different primitives)

| # | Surface | What breaks if compromised | Failure mode |
|---|---|---|---|
| 1 | **Asawa IP** | Sutra Core engine weight, Context Engine design, founder strategy, client contracts | Confidentiality |
| 2 | **Fleet integrity** | Plugin hooks execute as bash on every tenant machine. One compromised push → all tenants (T2+T3+T4) have arbitrary code execution | Supply-chain integrity |
| 3 | **Tenant authenticity** | Client session identity (e.g., `vinitharmalkar` incident — session auth leaked into text; Claude offered to act as that user on public systems) | Authenticity + identity confusion |

Each has different primitives. A single "security checklist" papering over all three will misprioritize.

## 8 Principles (ordered by enforcement priority)

1. **Least privilege** — every operation uses the narrowest permission that accomplishes it. God-mode is a narrow, time-boxed escape hatch, not the default.
2. **Integrity before availability** — when in doubt, refuse the action. Fail-closed semantics match PRIVACY's sanitization model.
3. **Identity boundaries** — session auth identity never crosses tier boundaries. "You're authenticated as X, I can act as X" patterns are banned.
4. **Signed artifacts** (future) — plugin releases signed + verified at install time. Unsigned install = loud banner + consent.
5. **Audit-by-default** — every cross-tier or cross-boundary action writes an audit row. Reads too, when operationally meaningful.
6. **Defense in depth** — multiple layers (D33 firewall + hook enforcement + permission gates + signed artifacts).
7. **Secret hygiene** — secrets in env vars only; PROTO-004 at write time; `scrub_text` at capture time.
8. **Fail closed** — missing signature, missing capability, missing consent → refuse. Never default-allow because "probably fine".

## Tiered Access Contract (parallel to PRIVACY, different axis)

| Tier | Default access | Override mechanism | Audit |
|---|---|---|---|
| **T0** Founder-operator | Full god-mode available | 2h window, password-gated, logged | `.enforcement/god-mode.log` |
| **T1** Asawa-internal | Full asawa-role via `.claude/active-role=asawa` | Implicit (operator is founder) | `.enforcement/sutra-deploys.log` |
| **T2** Owned portfolio | `company-<name>` role; `enforce-boundaries.sh` blocks cross-submodule edits | God-mode from T0 only | Boundary-hook exit 2 events |
| **T3** Projects (client IP) | Strictly scoped — company-role, D33 firewall, no god-mode from their session | None; cross-firewall via T0 god-mode only | D33 boundary violations logged |
| **T4** External fleet | Plugin-hook execution only; no filesystem access to Asawa artifacts | None | Fleet telemetry (when consented) |

## Failure Modes + Primitives Map

| Mode | Example | Primitive (existing or needed) |
|---|---|---|
| **Unauthorized edit cross-tier** | Asawa session edits a T3 client's IP | `enforce-boundaries.sh` (exists) — PreToolUse, role-scoped, exit 2 on violation |
| **Arbitrary code exec via plugin** | Compromised push to `sankalpasawa/sutra` → all tenants run the attacker's bash | Code signing (needed); SHA-pinned installs (needed); plugin-update consent on SHA change (needed) |
| **Session identity leak** | Claude says "I'll file an issue as you" and acts on session auth | `feedback-routing-rule.sh` (exists, v1.14.1) — stops the vinitharmalkar pattern; extend to all "act as user" patterns |
| **Secret in commit** | API key pasted into code → git history leak | PROTO-004 `keys-in-env-vars.sh` (exists) — PreToolUse HARD block on key-shaped strings |
| **Secret in LLM output** | Claude echoes an API key it saw in prompt | PRIVACY's `scrub_text` (exists) — secondary guardrail |
| **God-mode abuse** | Password leaked, persistent session, unbounded writes | 2h TTL (exists); password-gate (weak — `Asawa` — upgrade to strong needed); MFA (needed); activity log (exists) |
| **Submodule tamper** | Attacker pushes to sutra submodule; Asawa pulls it blindly | SHA verification on submodule update (needed); signed commits (needed) |
| **Plugin update unconsented** | Plugin auto-updates with malicious hook | Plugin-update consent for SHA change (needed) |
| **Third-party compromise** | Supabase/Vercel/Resend breach → data exposed | Encryption-at-source (partial); policy audit cadence (needed) |
| **Backup exposure** | iCloud/Time Machine replicates sensitive local files | PRIVACY's local hardening (exists: 0700/0600, symlink-refusal); Spotlight exclusion (documented) |

## Implementation Primitives (existing + needed)

| # | Primitive | State |
|---|---|---|
| 1 | `enforce-boundaries.sh` (role-scoped file access) | ✓ Exists — plugin hook |
| 2 | `keys-in-env-vars.sh` (PROTO-004 secret-gate) | ✓ Exists — plugin hook |
| 3 | `god-mode.sh` (2h TTL, logged) | ✓ Exists — holding/hooks |
| 4 | `feedback-routing-rule.sh` (identity-leak prevention) | ✓ Exists — plugin hook, v1.14.1 |
| 5 | D33 firewall (accidental-access fence) | ✓ Exists — bidirectional `.claude/settings.json` deny |
| 6 | PRIVACY `scrub_text` (secondary guardrail) | ✓ Exists — v2.0 lib |
| 7 | Permission gate (`permission-gate.sh`) | ✓ Exists — v1.13 |
| 8 | `codex-directive-gate.sh` (pre-ship review) | ✓ Exists — PROTO-019 v2 |
| 9 | Signed plugin releases | ❌ Needed — next iteration |
| 10 | SHA-pinned submodule updates | ❌ Needed — next iteration |
| 11 | God-mode strong-password / MFA | ❌ Needed — password is currently `Asawa`, weak |
| 12 | Plugin-update consent on SHA change | ❌ Needed — currently auto-updates on `claude plugin update` |
| 13 | Supply-chain SBOM (software bill of materials) | ❌ Needed — audit cadence |
| 14 | Cross-tier audit aggregation (dashboard) | ❌ Needed — data exists in `.enforcement/*.log`, no rollup |

## Key Results (measurable)

| KR | Target | Measurement | Current state |
|---|---|---|---|
| KR1 | 0 secrets committed to git | PROTO-004 gate fires on every Write/Edit/MultiEdit | ✓ Enforced |
| KR2 | 0 cross-tier edits from wrong role | `enforce-boundaries.sh` exit 2 rate monitored | ✓ Enforced |
| KR3 | 0 "act as user" patterns in model output | `feedback-routing-rule.sh` behavioral rule; audit samples | ✓ Rule live, audit pending |
| KR4 | 100% of plugin releases signed (future KR) | Signature verification at install | ❌ Not yet |
| KR5 | God-mode total TTL ≤2h per activation + logged 100% | `.enforcement/god-mode.log` has start+end per session | ✓ Enforced |
| KR6 | 0 unreviewed submodule pointer bumps | SHA pinning + changelog diff review | ❌ Informal today |
| KR7 | Mean time to detect supply-chain anomaly | Codex-directive-gate catches "use codex" patterns; broader scan needed | ❌ Not measured |

## Relationship to Other Charters

- **PRIVACY** (v2.0, shipped) — Privacy owns *what data* and *how long*. Security owns *who can touch* and *can we trust it*. They share the fail-closed + boundary-enforcement primitives.
- **PEDAGOGY** (v1.0, drafted alongside) — novice users need clear security mental model. LEARN mode should teach D33 / god-mode / permission-gate BEFORE user encounters them.
- **TOKENS** — security audit logs consume token budget. Need rollup to avoid unbounded growth.
- **SPEED** — security checks at hook layer add latency. Budget: <5ms per PreToolUse hook fire.

## Relationship to D33 Firewall

D33 is the **accidental-access fence** layer of Security — explicitly NOT a security boundary against adversarial actors. It protects against cooperative-LLM drift (Claude accidentally reading across tiers).

Security as a whole needs **adversarial-actor defenses** above and beyond D33:
- Signed artifacts (plugin + submodule)
- SHA-pinned installs
- Audit aggregation
- Strong auth for god-mode

## Review Cadence

- **Weekly**: scan `.enforcement/*.log` for anomalies.
- **Monthly**: KR1-KR7 dashboard (Analytics dept pulse).
- **Quarterly**: full security audit via `/cso comprehensive` skill; update primitives-needed list.
- **On every plugin version bump**: diff security surface; codex-review any change to enforce-boundaries / PROTO-004 / permission-gate.
- **On any incident**: post-mortem → new primitive → charter update.

## Kill-Switches (per layer)

| Scope | Kill-switch | Effect |
|---|---|---|
| Fleet | Plugin uninstall (`claude plugin uninstall core@sutra`) | Removes all governance hooks |
| Per-install | `~/.codex-directive-disabled`, `~/.proto004-disabled`, `~/.rtk-disabled` | Individual hook opt-outs |
| God-mode | `bash holding/hooks/god-mode.sh deactivate` | Early deactivate before 2h TTL |
| D33 | Remove bidirectional deny from settings.json | Falls back to plugin-only enforcement |

## Prior Art + References

- Codex security consults: `.enforcement/codex-reviews/*.md`
- `/cso` skill: tactical infrastructure-first audit (daily or comprehensive modes)
- `/security-review` skill: PR diff scan
- `holding/INFRASTRUCTURE-OWNERSHIP.md`: infra ownership policy
- PROTO-004 secret-gate design
- PROTO-019 v2 codex-directive gate design
- D33 firewall documentation: `holding/FOUNDER-DIRECTIONS.md` §D33

## What's NOT in scope (for this charter)

- Content moderation (Claude refusing harmful requests) — Anthropic-policy-level
- Network security — no network transport in v2 default; future when fan-in ships
- Physical security — laptop encryption is founder's responsibility

---

*SECURITY is the charter that owns access + integrity + authenticity. PRIVACY is the charter that owns collection + retention + disposal. Together they cover "can we trust this system with this data?"*
