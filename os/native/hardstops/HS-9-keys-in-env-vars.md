---
part-id: HS-9
bucket: hardstops
template: ADR-style-invariant
parity-source: PROTOCOLS.md §PROTO-004 + plugin hook keys-in-env-vars.sh + dispatcher-pretool.sh Check 5
parity-source-sha256: b85f06765eaf8e28f97e0d05e2541b4c0a47a597c5e67b97a96dafb1c33c08be
status: DRAFT v1 (lesson-port from ACTIVE production PROTO-004; not yet wired in Native runtime)
authored: 2026-06-12
---

# HS-9: Keys in env vars only

## Status

DRAFT v1 — production contract is ACTIVE + HARD in Sutra (two enforcement layers); Native runtime wiring pending.

## Context (when this fires)

HS-9 fires when any artifact write attempts to introduce secret material into a committed/persistent file.

Trigger conditions:
1. A Write/Edit-class action's INCOMING content (not prior file state) contains a key-shaped string — provider-shaped (`sk-…`, `AKIA…`, `ghp_…`, `ghs_…`, `xoxb-…`, `ya29.…`, `AIza…`, `BEGIN PRIVATE KEY`) or assignment-shaped (dispatcher Check-5 patterns) — the two sets catch disjoint cases; port both verbatim.
2. AND the target is not an exempt env-type location (`*.env`, `*/secrets/*`, `*credentials*`), a privacy-scrub library (legitimately contains key SHAPES), or a binary.

Observable state at trigger time: tool_input content matches a secret pattern; target path outside the exemption set.

## Decision (fail-mode)

> Secrets live only in environment variables or env-type files. Any artifact write introducing a key-shaped string into a non-env file is **denied at the boundary BEFORE the file is touched** (exit-2 class block; the write never lands). Remediation edits that remove secrets always pass.

Scope boundary (reconciles the §5.1 connector-token tension without stretching the rule): HS-9's enforcement boundary is the **repository write path** — it guards what can enter committable artifacts. Out-of-repo secret stores are NOT silently exempt; they are a second, separately-governed sanctioned pattern: untracked stores outside any repository, mode 0600, under a named location (`~/.sutra-connectors/oauth/` precedent), with edits gated by the adjacent secret-file edit gate (ADR-003). Two patterns, two gates — a secret that is in neither pattern violates one of them. (deepseek MODIFY absorbed 2026-06-12.)

Native kill-switch key (declared per B10 K4 registry mandate): `SUTRA_HS9_KEYS_DISABLED` — production analog is `PROTO004_ACK=1` + reason, audit-logged; default-OFF gating per D32 noted in the production hook.

## Recovery path

1. The blocked write returns the violation message + matched pattern class; the author moves the secret to an env var or the sanctioned out-of-repo store and re-issues the write without the secret literal.
2. If the block is a false positive (key-SHAPED test fixture), the override key + reason is accepted once and audit-logged (`{event:proto004-block}` row family in the audit stream).
3. If a secret already landed historically: rotate the credential first, then scrub; rotation is the recovery, history rewriting is not.

## Downstream effects

- No secret ever reaches a committable artifact → fleet pulls can never exfiltrate credentials; key rotation never requires history rewriting.
- Privacy-scrub libraries and env-type files keep working (exemption set ports verbatim) — remediation and scrubbing flows are never blocked.
- Violated (hypothetical): a single committed key compromises every install that pulls the repo; blast radius = the credential's full scope.

## STRIDE relevance

**Information Disclosure** (primary): credential exfiltration via repository distribution. Secondary: **Elevation of Privilege** if the leaked credential grants write scopes.

## Enforcement shipped today (production evidence)

- Plugin L0: `sutra/marketplace/plugin/hooks/keys-in-env-vars.sh` — PreToolUse on Write|Edit|MultiEdit (hooks.json), scans INCOMING content, exit 2 BLOCK, JSONL audit row to `.enforcement/routing-misses.log`. Pattern set sourced from OWASP/git-secrets.
- Holding layer: `holding/hooks/dispatcher-pretool.sh` Check 5 — assignment-shaped patterns (disjoint coverage; port BOTH sets verbatim).

## References

- sutra/layer2-operating-system/PROTOCOLS.md §PROTO-004 — protocol of record (production evidence).
- sutra/marketplace/plugin/hooks/keys-in-env-vars.sh — primary enforcer (production evidence).
- sutra/marketplace/plugin/hooks/hooks.json — PreToolUse registration (production evidence).
- holding/hooks/dispatcher-pretool.sh Check 5 — second pattern family (production evidence).
- `../decisions/` ADR-003 — secret-file edit gate (adjacent rule: gates edits TO secret stores; HS-9 gates secrets INTO non-stores).
- holding/website/native/master/index.html §5.1 (frozen monolith, post-IA-migration path) — connector token storage; reconciled by the two-pattern boundary above.
