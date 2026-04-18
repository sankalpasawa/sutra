# Sutra Override Schema — v1

*Status: SPEC (draft). Mechanism lands in B5.3 shared writer + B5.4 adapters.*
*Date: 2026-04-18*
*Authority: Sutra v1.9 / PROTO-004 / I-14 / D13 / D30*

## Purpose

Every governance hook in Sutra v1.9 gates some policy. Each gate supports an **operator override** — a mechanism by which the operator intentionally bypasses the gate for a stated reason, producing an auditable record. Before B5, overrides were five ad-hoc env conventions writing to three sinks in two formats with inconsistent sanitization. This document defines the single schema they all must follow.

## Scope

**In scope** (5 governance overrides, production gates):

| Alias | Gate | Direction/Protocol |
|-------|------|---------------------|
| `SECRET_OVERRIDE` | PROTO-004 secrets | dispatcher-pretool.sh Check 5 |
| `DUPLICATION_OVERRIDE` | I-14 new-path | new-path-detector.sh |
| `CASCADE_ACK` | D13 cascade | cascade-check.sh |
| `CODEX_OVERRIDE` | Codex review | codex-review-gate.sh |
| `POLICY_ACK` | Policy coverage | policy-coverage-gate.sh |

**Out of scope** (test-path overrides — path-injection helpers, not governance bypass):

- `TRIAGE_LOG_OVERRIDE` (triage-collector.sh — test log path)
- `ESTIMATION_LOG_OVERRIDE` (estimation-collector.sh — test log path)

Test-path overrides stay as-is. They do not count as policy exceptions. Separating the two buckets preserves analytical integrity of the audit log.

## Invocation Contract (operator-facing)

Operators invoke an override exactly as they do today — backward-compatible. No new syntax.

```bash
# Governance bypass, current & future
SECRET_OVERRIDE=1 SECRET_OVERRIDE_REASON='<why>' <tool call>
DUPLICATION_OVERRIDE=1 DUPLICATION_OVERRIDE_REASON='<why>' <tool call>
CASCADE_ACK=1 CASCADE_ACK_REASON='<why>' <tool call>
CODEX_OVERRIDE=1 CODEX_OVERRIDE_REASON='<why>' <tool call>
POLICY_ACK=1 POLICY_ACK_REASON='<why>' <tool call>
```

Rules:

1. Both the `*_OVERRIDE`/`*_ACK` and the matching `*_REASON` must be set. Missing reason → override rejected (gate blocks).
2. `=1` is the accepting value. Any other truthy value (e.g. `=true`, `=yes`) is rejected — single canonical truthy form prevents accidental activation.
3. Reason must be a non-empty, single-line string ≤ 500 chars. Multi-line reasons are rejected to prevent JSONL injection (F17).
4. Overrides are **per-invocation only**. See Lifetime Guard below.

## Schema Fields (audit-record)

Every accepted override writes one JSONL row to `.enforcement/override-audit.jsonl` with this shape:

```json
{
  "schema_version": 1,
  "ts": 1776331200,
  "override_kind": "governance_bypass",
  "alias": "SECRET_OVERRIDE",
  "gate": "PROTO-004",
  "hook": "dispatcher-pretool.sh",
  "decision": "allow",
  "original_gate_severity": 2,
  "reason": "test fixture with fake key",
  "actor": "asawa",
  "company": "holding",
  "file": "holding/hooks/tests/fixtures/secret.txt",
  "nonce": "a1b2c3d4e5f6",
  "valid_for_seconds": 60
}
```

### Field reference

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `schema_version` | int | yes | Forward-compat; currently `1`. Readers must tolerate future versions. |
| `ts` | int (unix seconds) | yes | Event time. |
| `override_kind` | enum `governance_bypass` (v1) | yes | Analytical bucket. v1 emits ONLY `governance_bypass` (codex review fix 2026-04-18 — original draft over-modeled `test_sink_redirect`). Test-path overrides do not emit audit records at all. Future hybrids add new enum values without bumping `schema_version`; readers must tolerate unknown enum values. |
| `mode` | enum `legacy\|strict` | yes | Per Lifetime Guard section. `legacy` for env-var-only invocations (audit amplification, F16 partial); `strict` for token-gated invocations (true F16 mitigation). |
| `alias` | enum (see table above) | yes | The env-var convention used. Bound to the gate. |
| `gate` | string | yes | Stable ID of the gate (e.g. `PROTO-004`, `I-14`, `D13`). |
| `hook` | string | yes | Source hook file (basename). |
| `decision` | enum `allow\|deny\|warn` | yes | What the gate resolved to after override. `allow` for accepted overrides. |
| `original_gate_severity` | int | yes | Exit code the gate would have emitted without override (1 or 2). Separates "denied-then-overridden" from advisory passes. |
| `reason` | string | yes | Operator-supplied, sanitized (see Serialization). |
| `actor` | string | yes | Role (asawa, company-<name>, sutra). Derived from `.claude/active-role`. |
| `company` | string | yes | Working tree company name, or `holding`. |
| `file` | string | no | File path the gate was evaluating, if applicable. |
| `nonce` | string (12 hex chars) | yes | Per-invocation random ID. Uniquely identifies this override event. |
| `valid_for_seconds` | int | yes | TTL for the override (default 60). See Lifetime Guard. |

### Event enum (for `alias`)

Every governance override uses its historical env-var name as `alias`. This is the stable identifier that external tooling (audit dashboards, compliance scans) keys on.

```
SECRET_OVERRIDE          — PROTO-004
DUPLICATION_OVERRIDE     — I-14
CASCADE_ACK              — D13
CODEX_OVERRIDE           — D29 (codex review)
POLICY_ACK               — PROTO-000 (policy coverage)
```

New governance gates added later SHOULD register their alias here. Adding a new `alias` value does not require a `schema_version` bump; readers MUST accept unknown aliases and report them as `kind=unknown_governance_bypass`.

## Sink — single append-only JSONL

All governance overrides write to **one** log file:

```
.enforcement/override-audit.jsonl
```

- Append-only. One JSON object per line. Newline-terminated.
- No rotation at this tier — left to operator / CI cleanup.
- Companies emit into their own `.enforcement/override-audit.jsonl`. Holding aggregator (future B-block) can roll up.
- Historic sinks (`.enforcement/routing-misses.log`, `.enforcement/duplication-log.jsonl`, `.enforcement/codex-reviews/*/overrides.log`, `.enforcement/policy-acks.log`) stay as **legacy fallback mirrors** for one version cycle (v1.9 → v1.10) so incumbent dashboards do not break. After v1.10, the helper stops writing mirrors.

## Serialization (mandatory, centralized)

All audit records MUST be emitted via the shared writer in `sutra/package/hooks/lib/override-audit.sh` (B5.3). Hand-rolled JSON writes in individual hooks are prohibited after B5.5 migration completes.

Reason-string handling (defends F17 — JSONL injection) follows a **reject-then-escape** pattern (codex review fix 2026-04-18, prior draft was over-destructive):

**Input validation** (reject, do not mutate):
1. Reject if reason contains `\r`, `\n`, or NUL bytes — these are the only characters that can break JSONL line boundaries or terminate records.
2. Reject if reason length > 500 chars after UTF-8 normalization.
3. Reject if reason is empty.

**Serialization** (escape, do not mutate):
1. Reason is passed through proper JSON string escaping at write time (`jq -Rsa` or equivalent), which handles `"`, `\`, and any control characters by emitting `\"`, `\\`, `\u00xx` per RFC 8259.
2. The on-disk string is escaped; the in-record value preserves the operator's intent (apostrophes, parentheses, slashes, quotes pass through correctly).

This preserves operator intent (apostrophes in "couldn't", slashes in file paths, quotes in `'as foo'`) while still defending the JSONL line boundary. The shared writer MUST be the only serializer; future gates call the same helper for free correctness.

## Lifetime Guard — TWO MODES (F16: legacy = partial, strict = true mitigation)

**Problem**: Once `SECRET_OVERRIDE=1` is exported in a shell, every subsequent hook invocation in that shell session sees it. In long-running sessions, CI wrappers, or daemonized runners, a one-time override silently widens scope into later unrelated operations.

This spec defines **two modes**. Wave 2 ships LEGACY mode (backward-compat). Wave 3 (or operator opt-in) ships STRICT mode (true mitigation). The codex 2026-04-18 review correctly flagged that the original "marker-consume" pattern was audit amplification, not scope enforcement — corrected below.

### LEGACY mode (default, backward-compat)

Invocation unchanged: `FOO=1 FOO_REASON='...' <tool call>`.

Behavior on each gate invocation that sees the env var:
1. Helper validates reason + writes ONE audit row with new nonce.
2. Helper does NOT delete the env var (cannot — it lives in the parent shell).
3. Audit row carries `mode: "legacy"`.

**This is audit amplification, not scope enforcement.** If the operator forgets to `unset FOO`, every subsequent gate logs another row. The audit log surfaces the leakage (operator can grep for repeated nonces from same alias within minutes), but the override still semantically applies. F16 is **partially** mitigated — observability up, scope enforcement nil.

### STRICT mode (opt-in via FOO_TOKEN, true F16 mitigation)

Invocation: `FOO=1 FOO_REASON='...' FOO_TOKEN=$(bash override-audit.sh mint) <tool call>`.

Behavior:
1. `mint` writes a single-use token file at `.claude/override-tokens/<random>` and prints the random ID.
2. Helper validates env var = 1 AND `FOO_TOKEN` matches a token file under `.claude/override-tokens/`.
3. On match: helper deletes the token file, writes audit row with `mode: "strict"`, accepts override.
4. On mismatch (no token, stale token, already-consumed token): helper rejects override. Gate blocks.
5. Token files older than `valid_for_seconds` are pruned by the helper on each call.

This forces per-invocation scope. A leaked `FOO=1` in the parent shell does nothing without a fresh token. F16 is **fully** mitigated for callers who opt in.

**Why two modes:** Wave 2 cannot break every existing test fixture (`SECRET_OVERRIDE=1 ... <tool call>`). LEGACY mode preserves them all. Operators who care about leakage opt into STRICT. Future Sutra versions can flip the default once all call sites migrate.

**Expiry**: If `ts + valid_for_seconds < now` when helper runs, override (legacy or strict) is rejected as expired. Default `valid_for_seconds=60`. Long operations bump via `*_OVERRIDE_TTL=<seconds>`.

## Backward Compatibility

1. **Every current env var name stays stable.** No `*_OVERRIDE` is renamed. Tests and docs continue to work.
2. **Every current call site keeps working** until B5.5 migrates it. The old inline "override accepted" code paths remain until explicitly replaced.
3. **Legacy sink mirroring** continues until v1.10 (F2, F18).
4. **Schema version 1** is the baseline. Future additions (new required fields, removed fields) bump to `schema_version: 2`. Readers MUST not fail on unknown fields (forward-compat for federation, F13).

## Federation / tiered rollout (F13)

- Companies may run older Sutra versions. Records they emit may lack newer optional fields → readers treat missing optional fields as `null`, never error.
- `schema_version` is the coordination point. Central audit aggregators filter/bucket by version.
- No attempt is made to retroactively upgrade old records.

## SOT placement (F15)

This document is referenced from `sutra/state/system.yaml` at:

```yaml
meta:
  override_schema: sutra/state/OVERRIDE-SCHEMA.md
  override_schema_version: 1
  override_audit_log: .enforcement/override-audit.jsonl
  override_implementation: sutra/package/hooks/lib/override-audit.sh
```

`validate.mjs` SHOULD (future task) verify that `override_implementation` file exists and that every governance hook declared in `hooks[]` sources it.

## Acceptance criteria — B5.2 ship

This document, alone, is the deliverable for B5.2. No code changes ship with it. B5.3 (shared writer) and B5.5 (call-site migration) implement it.

- [x] Inventory of 5 governance + 2 test-path overrides is complete.
- [x] Schema fields all have purpose + required/optional status.
- [x] Sanitization rules specify exact transformations (F17).
- [x] Lifetime guard mechanism covers F16 adversarial factor.
- [x] Backward-compat policy preserves all 5 env-var aliases.
- [x] Legacy sink mirroring path specified for 1 version cycle.
- [x] Federation/tiered read policy specified.
- [x] SOT wire-up specified (meta.override_schema).

## Open questions (defer to B5.3 design review)

1. Should the shared writer be bash (matches existing hook substrate) or Node (matches compile.mjs, validate.mjs)? Bash keeps latency low and dependencies zero; Node enables JSON validation via the shipped schema. Proposal: bash, with schema-validation lint run at CI time.
2. Should `valid_for_seconds` default be 60 or 300? Long codex reviews can take minutes. Proposal: 60 default, per-alias override possible.
3. Should `company` field auto-derive from `active-role` or be set by the hook? Proposal: helper reads `.claude/active-role` as default; hook can override.
4. Aggregator rollup (holding pulls from each company's override-audit.jsonl) — out of scope for B5, defer to B-block in next iteration.

---

*End of OVERRIDE-SCHEMA.md v1. Proceed to codex review gate before B5.3 implementation.*
