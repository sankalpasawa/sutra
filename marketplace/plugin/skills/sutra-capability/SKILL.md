---
name: sutra-capability
description: Use when user asks about Sutra plugin capabilities, what skills/hooks ship, the capability surface map, fleet-shippable vs Asawa-only vs Sutra-internal disciplines, CSM digest, or types /sutra-capability. Emits a compact on-demand summary of capabilities shipping in this plugin install. T4 fleet's analog of the Asawa SessionStart banner.
---

# Sutra Capability Surface — On-Demand Digest

This skill is the T4 fleet's view into the Capability Surface Map (CSM). Asawa
has `holding/CAPABILITY-MAP.md` + the SessionStart banner; T4 fleet has this
skill. Per CSM TODO #3 (D43, deadline 2026-06-01).

## When invoked

Read these sources in order:

1. **`${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`** — `version` field tells
   the founder which plugin version is installed.
2. **`${CLAUDE_PLUGIN_ROOT}/sutra-defaults.json`** — `.per_turn_blocks`,
   `.right_effort`, `.skill_explanation`, `.subagent_dispatch`, `.output_discipline`
   (with sub-keys `.highlight_decisions` and `.table_shape`),
   `.customer_focus_first`, `.process_discipline_proto006`, `.consult_policy`,
   `.kill_switches`. Each top-level key is a capability surface.
3. **`${CLAUDE_PLUGIN_ROOT}/skills/`** directory listing — each subdirectory is
   a shipped skill.
4. **`${CLAUDE_PLUGIN_ROOT}/hooks/hooks.json`** — registered runtime hooks per
   event (PreToolUse / PostToolUse / UserPromptSubmit / SessionStart / Stop).

## Emit format

Produce a single compact response with this structure (ASCII tables, no unicode
box-drawing chars):

```
+-- Sutra Plugin v<version> — Capability Surface ----------------+
|                                                                |
| PER-TURN BLOCKS (D40 governance parity):                      |
|   - human-sutra header        (cap-???)                       |
|   - input-routing             (cap-001)                       |
|   - depth-estimation          (cap-002)                       |
|   - blueprint                 (cap-003)                       |
|   - output-trace              (cap-005)                       |
|                                                                |
| OUTPUT DISCIPLINE (cap-004 + nested entries):                  |
|   - readability-gate          (cap-004)                       |
|   - highlight-decisions       (cap-113, policy-visible)       |
|   - table-shape               (cap-115, policy-visible)       |
|                                                                |
| GOVERNANCE DISCIPLINES (memory → schema, 2026-05-04):          |
|   - karpathy-right-effort     (cap-108)                       |
|   - skill-explain-card        (cap-109)                       |
|   - subagent-dispatch         (cap-110)                       |
|   - customer-focus-first      (cap-112, policy-visible, P0)   |
|   - process-discipline        (cap-116, policy-visible)       |
|                                                                |
| ENFORCEMENT HOOKS:                                             |
|   - permissions (Tier 1/2/3) (cap-009)                       |
|   - build-layer / D38         (cap-010)                       |
|   - telemetry opt-in          (cap-011, partial)              |
|   - keys-in-env-vars (PROTO-004)                              |
|   - estimation-collector                                       |
|                                                                |
| BACKLOG (proposed, not yet shipping):                          |
|   - skill-explain hook nudge          (cap-109, schema only)  |
|   - readability-gate hook nudge       (cap-111, schema only)  |
|   - csm at-creation hook              (cap-117, L1 staging)   |
|   - no-fabrication / no-op-cap        (cap-114, DEFER)        |
|                                                                |
+----------------------------------------------------------------+
| For full schema + audit-log records:                           |
|   github.com/sankalpasawa/sutra (search "CAPABILITY-MAP")      |
| To see Asawa-side governance breakdown (T1 only):              |
|   open holding/CAPABILITY-MAP.md (file present in Asawa repo)  |
+----------------------------------------------------------------+
```

Pull actual cap-### IDs and current statuses from `sutra-defaults.json`'s
`cap_id` fields where present. Skip caps not declared in the plugin install.

## Coverage caveat

Per codex 2026-05-04 ADVISORY #4: capability **status `shipping (policy-visible)`**
means the discipline is documented in plugin-canonical schema and surfaced as
convention; it does NOT mean runtime enforcement. Behavior verification is
deferred (depends on D42 H-Sutra interaction log accumulating ≥100 turns of
data).

For runtime-enforced capabilities (Bucket A status `shipping`), look at the
`enforcement` field of the schema entry: if it's `convention_only`, behavior
is policy-visible. If it's `hard_block` / `gate` / `pretooluse`, runtime
actually enforces.

## Kill-switch

`SUTRA_CAPABILITY_DIGEST_DISABLED=1` env or `~/.sutra-capability-disabled` file
to silence this skill.

## Build-layer

L0 fleet. Universal across T1/T2/T3/T4 plugin installs. Reads only files
inside `${CLAUDE_PLUGIN_ROOT}/` so it works without `holding/CAPABILITY-MAP.md`.
