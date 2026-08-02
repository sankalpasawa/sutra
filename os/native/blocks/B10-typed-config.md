---
part-id: B10
bucket: blocks
template: L8-feature-spec
parity-source: §12.13 row B10 + §12.12 founder voice round 4 + §10.2 P10 + Q30
parity-source-sha256: e28f8ccd3e9042bcd3f332fb316712ea74ecae36274deee869273056e7f8e0a8
status: DRAFT v1
authored: 2026-05-09
---

# B10: Domain Typed Config + Charter Typed Config

## 1-line summary

Domain carries typed `principles[]` + `guidelines[]` + `decisions[]`; Charter carries typed `instructions[]` + `guidelines[]` + `constraints[]` — every constraint is declared, not tacit, and consumed at prompt-build time per B11.

## Scope (in / out)

**In scope (v1)**:
- EXTEND existing Domain (§2.1) — add `guidelines[]` + `decisions[]` typed arrays per §12.13 row B10. (Domain.principles[] exists partial per canon §2.1.)
- EXTEND existing Charter (§2.2) — add `instructions[]` + `guidelines[]` + `constraints[]` typed arrays per §12.13 row B10. (Charter.invariants / .constraints exist partial per §2.2.)
- All consumed at prompt-build time per B11 (constrained problem construction per P11).
- Per Q30 default (2026-05-09) — structured typed predicates v1 (PNC-aligned per ADR-012); free-form `notes` field allowed for human commentary.

**Out of scope (v1)**:
- Auto-derivation of guidelines from operator behavior — overlaps B18 Person Formation; deferred v2+.
- Cross-Tenant config sharing — Tenant-scoped only per §6.2.
- Dynamic mutation of typed config mid-Workflow — overlaps 7e (mid-exec mutation); routed via 7e.

## User outcome

Every LLM call receives explicit Domain + Charter config (principles, guidelines, decisions, instructions, constraints) as part of the prompt — no tacit-knowledge LLM calls. Founder voice round 4: "for each domain ... guidelines, principles or some decisions and for each charter ... instructions guideline constraints".

## UX flow (narrative; terminal + audit log)

1. Domain authored with `principles[]` + `guidelines[]` + `decisions[]`.
2. Charter authored with `instructions[]` + `guidelines[]` + `constraints[]`.
3. Each typed entry is a PNC-aligned predicate (per Q30 default + ADR-012) OR includes a free-form `notes` field for human commentary.
4. Workflow fires inside Charter inside Domain.
5. B11 PromptBuilder reads both configs; embeds in prompt context per P11.
6. LLM call receives constrained problem.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Domain has principles + guidelines + decisions populated | Workflow in Domain fires | B11 PromptBuilder embeds all three arrays in prompt context |
| 2 | Charter has instructions + guidelines + constraints populated | Workflow in Charter fires | B11 embeds all three arrays in prompt context |
| 3 | Config entry uses unstructured prose only (no PNC predicate) | validation | rejected per Q30 v1 (structured typed predicates required); `notes` field still allowed |
| 4 | Config entry's PNC predicate parses successfully | runtime check | entry usable; consumed by B11 |
| 5 | Charter constraint conflicts with Domain principle | conflict | conflict-resolution rule NOT specified in canon (gap per F2; founder-side ambiguity per Q30 + per Q28 cross-Charter cascade) |

## Data model

Per §12.13 row B10: EXTEND existing Domain + Charter (§2.1 + §2.2). No new §2 primitive (per F5).

Per Q30 default + ADR-012:

```
Domain (extended) = {
  ...existing §2.1 fields (tenant_id, principles[] partial),
  guidelines: TypedPredicate[]    // NEW
  decisions: TypedPredicate[]     // NEW
}

Charter (extended) = {
  ...existing §2.2 fields (invariants[] / constraints[] partial),
  instructions: TypedPredicate[]  // NEW
  guidelines: TypedPredicate[]    // NEW
  constraints: TypedPredicate[]   // extends existing constraints
}

TypedPredicate = {
  predicate_body    // PNC-aligned typed predicate per ADR-012
  notes             // free-form prose allowed per Q30
}
```

Cross-refs:
- `../primitives/domain.md` (host)
- `../primitives/charter.md` (host)

## Edge cases

- **Empty guidelines / decisions / instructions / constraints** → PromptBuilder embeds nothing for those slots; allowed (no minimum specified in canon — gap per F2).
- **Predicate fails parse** → rejected at config-write time per Q30 + ADR-012.
- **Two typed predicates contradict** → conflict-resolution NOT specified in canon (gap per F2).
- **Operator mutates Domain config mid-Workflow** → routed via 7e classification.

## Per-instance operational knob surface (PROTO-023 port)

**Amendment (2026-06-12 — port of ACTIVE PROTO-023 "Centralized Config")**: B10 above covers *declarative typed config per primitive layer* — Domain/Charter typed-predicate arrays consumed by B11 at prompt-build time (what the engine reasons WITH). PROTO-023 adds a second, distinct config domain that B10 did not state: the *operational knob surface* — one shell-sourceable per-instance file holding every kill-switch, opt-in, and threshold, readable by every policy hook via a single `source`. Relationship: typed per-layer config constrains the problem the engine constructs; the knob surface configures the runtime machinery itself (which hardstops/hooks are on, with what thresholds). Same config domain, disjoint consumers — B11 PromptBuilder vs policy hooks + daemon. Neither subsumes the other; both are required.

Production precedent (`$HOME/.sutra/config.env`):

- One shell-sourceable KEY=VALUE file per instance; per-instance under `$HOME` respects the D33 client firewall.
- CLI `sutra/marketplace/plugin/bin/sutra-config`: `get` (strips inline comments + quotes) / `set` (validates keys, shell-escapes values, preserves inline comments via awk in-place edit) / `list` / `init` (idempotent defaults) / `path`.
- Key conventions ported verbatim: UPPERCASE_ALNUM_UNDERSCORE keys starting with a letter; `SUTRA_` prefix; **additive, not exclusive** — pre-existing env-var overrides keep working (backward compat).
- Initial key registry: kill-switches (`SUTRA_RTK_ENABLED`, `SUTRA_CODEX_DIRECTIVE_ENABLED`, `SUTRA_ESTIMATION_COLLECTOR_ENABLED`, `SUTRA_COMPLETION_PROTOCOL_ENABLED`), thresholds (`SUTRA_CODEX_TIMEOUT_MS=600000`, `SUTRA_DEPTH_DEFAULT=5`, `SUTRA_BUILD_LAYER_DEFAULT=L0`), observability (`SUTRA_TELEMETRY=off`), tier (`SUTRA_TIER=governance`).

Native shape:

- Daemon AND host-side hooks read the same file; the CLI re-lands as a `sutra-native config get|set|list` subcommand writing the same file.
- **Adoption mandate (closes the known production weakness)**: production never closed the adoption loop — 1 of ~75 hooks sources the file (`completion-protocol-check.sh` L27-L29). Native mandates (and lints) that every hardstop/hook declares its kill-switch key in this registry.

Acceptance criteria (knob surface):

| # | Given | When | Then |
|---|---|---|---|
| K1 | Any user-controllable knob (kill-switch / opt-in / threshold) | a policy hook starts | knob readable via the single sourceable per-instance file |
| K2 | Valid key written then read | `config set` → `config get` round-trip | value preserved; comments + other keys untouched; `init` idempotent |
| K3 | Pre-existing env-var override set alongside the file | hook evaluates knob | env var still honored (additive, never exclusive) |
| K4 | New Native hardstop/hook ships without a declared kill-switch key | registry lint | rejected — every hardstop/hook declares its key |

**Falsification test**: a kill-switch, opt-in, or threshold exists that a policy hook cannot reach via the single sourceable per-instance file, OR a shipped Native hardstop/hook has no declared kill-switch key in the registry — either observation proves the knob surface violated.

Provenance: port of ACTIVE PROTO-023 (FOUNDATION tier — read-surface, no enforcement; origin gstack-patterns-review 2026-04-24, which found 6 scattered config locations; codex ranked consolidation top-1 ROI). Amendment parity-source (deviation from the NATIVE-ENGINE.md-anchor norm — this content is a canon gap; source is the protocol corpus): `sutra/layer2-operating-system/PROTOCOLS.md` §PROTO-023 L878-938, sha256 `5178cd7a6d1fbfd8b0953b7099e46b70d1b992d2ea5a4b6f9ba061d889c4cd8d`.

## Telemetry

Events (canon-existing only):
- `policy_decision` (§3.2) — when typed-predicate evaluates as part of B11 prompt-build.
- `artifact_registered` (#9) — config-as-artifact per P1 closed-loop.

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Pattern-detection precision — explicit constraints raise proposal precision.
- Approval-gate latency — constrained problems reduce founder review time.

## Dependencies

- **Primitives**: `domain` (host), `charter` (host), `engine-event`.
- **Events**: `policy_decision`, `artifact_registered`.
- **Surfaces**: `audit`, `route`.
- **Hardstops**: HS-4 (audit-unwritable).
- **Blocks**: B11 (PromptBuilder consumer), B4 (Charter context-scope; complementary), B3 (Domain MECE; complementary), 7e (mid-exec mutation route).
- **Pillars**: P10 (Typed config at every primitive layer), P11 (Constrained problem construction).
- **ADRs**: ADR-012 (PNC typed predicates).

## References

- NATIVE-ENGINE.md §12.13 row B10 (founder voice round 4).
- NATIVE-ENGINE.md §2.1 Domain primitive.
- NATIVE-ENGINE.md §2.2 Charter primitive.
- NATIVE-ENGINE.md §10.2 P10 (Typed config at every primitive layer).
- Q30 (§12.15) — structured typed predicates v1; free-form notes allowed.
- ADR-012 (PNC typed predicates).
- `sutra/layer2-operating-system/PROTOCOLS.md` §PROTO-023 (ACTIVE, FOUNDATION) — operational knob surface source.
- `sutra/marketplace/plugin/bin/sutra-config` + `sutra/marketplace/plugin/tests/unit/test-sutra-config.sh` — production CLI + test.
- `sutra/marketplace/plugin/hooks/completion-protocol-check.sh` L27-L29 — sole production sourcing consumer (adoption-gap evidence).
