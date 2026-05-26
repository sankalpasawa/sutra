# MCP Governance

Tier- and depth-aware policy enforcement over claude.ai's native MCP connectors.

Native MCP connectors are pure transport: connect an account, expose tools, calls
go through. There is no notion of *who* may call a tool, in *what context*, or with
*what audit trail*. MCP Governance adds that layer. It intercepts every
`mcp__claude_ai_*` tool call in a `PreToolUse` hook and runs a policy check
*before* the call reaches the connector.

```
Claude wants to call             PreToolUse hook                 decision
mcp__claude_ai_Slack__       ─►  mcp-governance-gate.sh    ─►   exit 0  (allow)
slack_send_message               └─ policy-check.mjs             exit 2  (block + reason)
                                    ├─ map tool → capability
                                    ├─ check tier access
                                    ├─ check depth floor
                                    └─ append audit row
```

## What it governs

| Axis | Native MCP | With MCP Governance |
|---|---|---|
| Access control | allow/deny prompt | tier model **T1–T4** per capability |
| Context sensitivity | none | **depth floor** — writes require `minDepth ≥ N` |
| Tool → meaning | raw tool name | **capability map** (`...HubSpot__manage_crm_objects` → `hubspot:write-crm:*`) |
| Approval | none | `approvalRequired` flag per capability |
| Audit | none | one JSONL row per call → `.enforcement/connector-audit.jsonl` |
| PII | raw payload | `redactPaths` declared per manifest *(spec-only this phase — see Limitations)* |
| Adding a connector | OAuth + UI | drop one YAML manifest |

## Components

| File | Role |
|---|---|
| `hooks/mcp-governance-gate.sh` | `PreToolUse` hook, matcher `mcp__claude_ai`. Reads tool name, delegates. |
| `connectors/mcp-governance/policy-check.mjs` | Policy engine — manifest lookup, tier check, depth check, audit. |
| `connectors/manifests/*.yaml` | Per-connector manifest with `mcp_tool_map`, `capabilities`, `tierAccess`. |

Coverage at Phase 1: **102 tools / 8 connectors** — Slack, Gmail, Google Calendar,
Google Drive, HubSpot, Atlassian (Jira + Confluence), Apollo, Read.ai.

## Manifest schema

Each connector is one YAML file under `connectors/manifests/`. Example (HubSpot):

```yaml
name: hubspot

# claude.ai MCP tool name → Sutra capability string
mcp_tool_map:
  mcp__claude_ai_HubSpot__get_crm_objects:    'hubspot:read-crm:*'
  mcp__claude_ai_HubSpot__manage_crm_objects: 'hubspot:write-crm:*'

# capability declarations (depth floor + approval)
capabilities:
  - id: 'hubspot:read-crm:*'
    action: read
    minDepth: 1
    approvalRequired: false
  - id: 'hubspot:write-crm:*'
    action: write
    minDepth: 3
    approvalRequired: true

# which tiers may use which capabilities (':*' = wildcard prefix)
tierAccess:
  T1: ['hubspot:read-crm:*', 'hubspot:write-crm:*']   # founder — full
  T2: ['hubspot:read-crm:*']                           # read only
  T3: []                                               # blocked
  T4: []                                               # blocked

# audit + PII redaction declarations
auditFields: [objectType, objectId, properties]
redactPaths: ['results[*].properties.email', 'properties.phone']
```

## Decision logic

A call is **allowed** only if all hold:

1. The tool name resolves to a capability via some manifest's `mcp_tool_map`.
   *(No match → not a governed connector → pass through.)*
2. The capability is declared in that manifest's `capabilities`.
3. The current tier is granted the capability in `tierAccess`.
4. The current depth ≥ the capability's `minDepth`.

Any failure → `exit 2` with a human-readable reason printed to stderr (Claude shows
it). Every outcome (allowed or blocked) is appended to
`.enforcement/connector-audit.jsonl`.

### Tier + depth inputs

- **Tier** — read from `.claude/sutra-project.json` (`tier` field, `T1`–`T4`).
- **Depth** — read from `.claude/depth-registered` (`DEPTH=N`).

Both accept CLI overrides for testing: `--tier T2 --depth 1`.

## Adding a connector

1. Create `connectors/manifests/<name>.yaml` with the four sections above.
2. Map every claude.ai tool name you want governed in `mcp_tool_map`.
3. No code change. The gate auto-discovers the manifest on next call.

## Testing

```bash
# allowed read at depth 1, founder tier
node connectors/mcp-governance/policy-check.mjs \
  --tool mcp__claude_ai_HubSpot__get_crm_objects --tier T1 --depth 1
echo $?   # 0

# blocked write at depth 1 (minDepth 3)
node connectors/mcp-governance/policy-check.mjs \
  --tool mcp__claude_ai_HubSpot__manage_crm_objects --tier T1 --depth 1
echo $?   # 2

# blocked by tier (T2 cannot write)
node connectors/mcp-governance/policy-check.mjs \
  --tool mcp__claude_ai_HubSpot__manage_crm_objects --tier T2 --depth 5
echo $?   # 2
```

## Design stance: fail-open

Missing policy checker, manifest parse error, unknown tool, or any crash → the call
**proceeds** (`exit 0`). Governance blocks specific, well-understood violations; it
does not break the session on its own failure. **This makes the layer advisory, not
a hard security boundary.** Do not rely on it to contain a hostile caller — treat it
as policy hygiene over a trusted operator.

## Known limitations (Phase 1)

- **No argument inspection.** `mcp_tool_map` maps tool *name* → capability without
  reading `tool_input`. A tool that is allowed only for specific resources (e.g. a
  Slack channel) resolves to the wildcard capability, so per-resource scoping is not
  possible yet. Phase 2 passes `tool_input` through the hook.
- **Tier defaults to `T1` (full access)** when `sutra-project.json` has no `tier`
  field. This fails *open to maximum privilege* — tier scoping is effectively off
  until a tier is written. Set a tier explicitly, or harden the default to the most
  restrictive tier.
- **CWD-relative state paths.** `depth-registered`, `sutra-project.json`, and the
  audit log are resolved relative to the process working directory, not a fixed
  project/plugin anchor. If the hook fires from a different CWD, depth and tier fall
  back to defaults silently. Anchor these to a known root.
- **`redactPaths` is spec-only.** Manifests declare PII paths but `policy-check.mjs`
  does not yet apply them — a `PreToolUse` hook cannot rewrite tool *output*.
  Redaction needs a `PostToolUse` companion.

## Build layer

L0 — ships in the plugin runtime for the whole fleet
(`sutra/marketplace/plugin/{hooks,connectors}/`).
