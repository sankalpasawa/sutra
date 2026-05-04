# ADR-003: PERMISSIONS extension — MCP auto-approve + first-time Edit/Write inside cwd

- **Status**: accepted
- **Date**: 2026-05-01
- **Author**: CEO of Asawa session (Claude) + founder Sankalp
- **Parent charter**: PERMISSIONS.md (existing, v1.13.0+)
- **Sibling ADR**: ADR-002 (REQUEST·HUMAN-EXEC) — same friction class (founder-side approval), different actor (model emission vs harness gate)
- **References**:
  - Charter (extended): `sutra/os/charters/PERMISSIONS.md`
  - Cross-link (added): `sutra/os/charters/HUMAN-SUTRA-LAYER.md` §Related disciplines
  - New mechanism: `sutra/marketplace/plugin/lib/mcp_trust_mode.py`
  - Hook (extended): `sutra/marketplace/plugin/hooks/permission-gate.sh`
  - Hook config (extended): `sutra/marketplace/plugin/hooks/hooks.json` (matcher widened)
  - Tests (extended): `sutra/marketplace/plugin/tests/permission-gate-test.sh`
  - Design brief (R1-folded, R2-ADVISORY): `holding/research/2026-05-01-adr-003-permissions-h-sutra-fold-design-brief.md`
  - D-direction: D47 in `holding/FOUNDER-DIRECTIONS.md` (renumbered from D44 on 2026-05-04 to resolve duplicate-D44 namespace; pre-rename references in CHANGELOG remain D44 historically)
  - Codex verdicts: `.enforcement/codex-reviews/2026-05-01-adr-003-r{1,2}-consult.md` (DIRECTIVE-ID 1777641500)
  - Two prior permission audits: `.enforcement/permission-audit-log.md` §2026-04-17 + §2026-04-22

---

## Decision (compact)

ADR-003 is a **pure extension of PERMISSIONS.md**. It closes two coverage gaps:
1. **MCP tool auto-approve** — connectors (Slack, Apollo, Atlassian, Gmail, Drive, Calendar, HubSpot, Read.ai, Playwright, etc.) currently prompt every call. ADR-003 adds an explicit read-verb allowlist + mutator/send denylist, implemented in a new `lib/mcp_trust_mode.py` module separate from `sh_trust_mode.py`.
2. **First-time Edit/Write inside cwd** — auto-approve project-tree edits except a curated prompt-list (secrets, deploy/CI configs, repo metadata).

ADR-003 is **NOT** a new sub-form within H-Sutra's OUT-DIRECT cell. It is a **sibling discipline** to H-Sutra. PERMISSIONS.md handles harness-mediated permission dialogs; H-Sutra handles model emission. Same goal (minimize founder friction), different actor.

---

## What did NOT change (preserved invariants)

| Invariant | Source | Preservation |
|---|---|---|
| ADR-001 §4 Rule 4 6-domain irreversible denylist (semantic categories) | ADR-001 | UNCHANGED — used by H-Sutra Stage-3 emission discipline only |
| ADR-001 §4 Rule 2 Stage-3-only emission invariant | ADR-001 | PRESERVED — ADR-003 is harness-mediated, not Stage-3 emission |
| ADR-001 3-direction MECE invariant (INBOUND / INTERNAL / OUTBOUND) | ADR-001 | PRESERVED — no new direction, no new cell |
| ADR-002 OUT-DIRECT 3-check (REQUEST·HUMAN-EXEC) | ADR-002 | UNAFFECTED |
| Trust Mode 6 Bash detector categories | PERMISSIONS.md §1.6 | UNCHANGED |
| Tier 3 hard-deny (paths outside .claude/.enforcement/.context/, ssh/aws/gnupg, sudo, shell combinators) | PERMISSIONS.md §4 | UNCHANGED |

---

## Two distinct denylist concepts (codex P1.2 disambiguation)

| Layer | Source | Form | Used by |
|---|---|---|---|
| **6-domain irreversible denylist** (SEMANTIC categories) | ADR-001 §4 Rule 4 | destructive file ops · external sends · founder-reputation outputs · money movement · legal/compliance · irreversible publication | H-Sutra Stage-3 emission discipline (ADR-002 OUT-DIRECT 3-check `denylist-hit` check) |
| **6 prompt categories** (TECHNICAL Bash detectors) | PERMISSIONS.md §1.6 Trust Mode | force-push/clean-f · sudo · recursive-delete · disk/system · fetch-and-exec · remote/shared-state | `permission-gate.sh` Bash auto-approval gate |
| **MCP allowlist + denylist** (TECHNICAL detectors, NEW) | this ADR | read-verb allowlist + mutator/send pattern denylist | `permission-gate.sh` MCP auto-approval gate (via `lib/mcp_trust_mode.py`) |
| **First-time-edit allowlist + prompt-list** (PATH detectors, NEW) | this ADR | cwd-only allowlist + secrets/deploy/CI prompt-list | `permission-gate.sh` Edit/Write auto-approval gate (extends Tier 1) |

The technical detectors APPROXIMATE the semantic denylist. They are NOT interchangeable. ADR-003 extends only the technical detector layer; ADR-001 §4 Rule 4 is **untouched**.

---

## 1. MCP auto-approve (codex P1.2 + A1 + A3 folds)

### 1.1 Read-verb allowlist (auto-approve)

Match against the tool name (everything after `mcp__<server>__`):

```
^mcp__.*__([a-z]+_)?(search|list|get|read|fetch|query|describe|enrich|match|status|info|view|metadata|count|index|profile|resolve|open|outline|availability|preview|download)(_[a-z]+)?$
```

**Allowlist verbs** (codex A1 expanded set): `search`, `list`, `get`, `read`, `fetch`, `query`, `describe`, `enrich`, `match`, `status`, `info`, `view`, `metadata`, `count`, `index`, `profile`, `resolve`, `open`, `outline`, `availability`, `preview`, `download`.

**Tightening** (codex A1 fold): the regex is anchored — verb must appear as a clearly-bounded token, with at most one optional leading namespace (e.g. `slack_search_channels`) and at most one optional trailing modifier (e.g. `search_channels` not `search_or_create`). Drift-prone names like `get_or_create`, `read_write`, `fetch_and_delete`, `status_update`, `apply_labels` will NOT match the allowlist and fall through to prompt.

### 1.2 Mutator/send denylist (always prompt, overrides allowlist)

Explicit prompt-class patterns by vendor family. Implementation is per-pattern string match — no regex generalization.

| Vendor | Tools that prompt |
|---|---|
| **Slack** | `slack_send_message`, `slack_send_message_draft`, `slack_schedule_message`, `slack_create_canvas`, `slack_update_canvas` |
| **Gmail** | `create_draft`, `update_draft`, any send-class (`*_send_*`, `*_forward_*`, send-draft execution), `delete_thread`, `delete_message`, `archive_*`, label mutations (`label_message`, `label_thread`, `unlabel_message`, `unlabel_thread`, `create_label`, `apply_labels_*`, `batch_modify_*`, `bulk_label_*`) |
| **Google Drive** | `create_file`, `copy_file`, `batch_update_*`, `import_*`, `template-copy_*`, `duplicate-sheet_*` |
| **Google Calendar** | `create_event`, `update_event`, `delete_event`, `respond_to_event` |
| **Apollo** | `apollo_*_create`, `apollo_*_update`, `apollo_emailer_campaigns_*` (add/remove/stop), `apollo_organizations_bulk_enrich` |
| **Atlassian Rovo** | `createJiraIssue`, `editJiraIssue`, `transitionJiraIssue`, `addCommentToJiraIssue`, `addWorklogToJiraIssue`, `createConfluencePage`, `updateConfluencePage`, `createConfluenceFooterComment`, `createConfluenceInlineComment`, `createIssueLink` |
| **HubSpot** | `manage_crm_objects`, `submit_feedback` |
| **Read.ai** | (none — passive reads `list_meetings` and `get_meeting_by_id` auto-approve) |
| **Playwright stateful** | `browser_click`, `browser_drag`, `browser_drop`, `browser_evaluate`, `browser_fill_form`, `browser_file_upload`, `browser_handle_dialog`, `browser_hover`, `browser_navigate`, `browser_navigate_back`, `browser_press_key`, `browser_resize`, `browser_run_code_unsafe`, `browser_select_option`, `browser_tabs`, `browser_type`, `browser_wait_for`, `browser_close` |

**Decision precedence**: prompt-list ALWAYS wins over allowlist regex. Anything not matched by either falls through to prompt (safe default).

---

## 2. First-time Edit/Write inside cwd (codex P2 + A2 folds)

### 2.1 Allow

Auto-approve `Edit` / `Write` / `MultiEdit` to paths inside cwd-tree, EXCEPT entries in §2.2 below.

### 2.2 Prompt-list (overrides allow)

| Pattern | Why prompt |
|---|---|
| `.claude/settings*.json` | Claude Code hardcoded guard — not bypassable anyway |
| `.env*` | Secrets surface |
| `.git/**` | Repo metadata — accidental corruption risk |
| `.npmrc`, `.pypirc` | Publish auth tokens |
| `**/credentials.json`, `**/secrets.yaml`, `**/.secret*` | Generic secret patterns |
| `.github/workflows/**`, `.circleci/**`, `.gitlab-ci.yml` | CI config — silent prod-relevant changes |
| `vercel.json`, `fly.toml`, `render.yaml`, `netlify.toml` | Deploy config |
| `docker-compose*.yml`, `docker-compose*.yaml` | Container orchestration — local + prod overlap |
| `k8s/**`, `helm/**/values*.y*ml` | Kubernetes manifests + Helm values |
| `.terraform/**`, `*.tfvars`, `*.tf` | Infrastructure-as-code state + variables |
| `Pulumi.*` | Pulumi infrastructure config |
| `wrangler.toml`, `railway.json`, `firebase.json` | Cloudflare/Railway/Firebase deploy |
| `cloudbuild.yaml`, `app.yaml` | GCP Cloud Build + App Engine |
| `supabase/**` | Supabase backend config |
| Anything outside cwd | Cross-company / cross-project (Tier 3 preserved) |
| `~/.ssh/**`, `~/.aws/**`, `~/.gnupg/**`, Keychain | Tier 3 forbidden — preserved |

### 2.3 Threat-model honesty (codex P2 fold)

Widening Edit/Write from governance markers to arbitrary cwd-tree files **IS a policy expansion** relative to current Tier 3. This is documented and deliberate, not hand-waved:

- **Justification**: same single-trusted-operator threat model as Trust Mode (PERMISSIONS.md §1.6); recovery via git/backups/fs trash; the §2.2 prompt-list keeps high-blast-radius targets gated.
- **Honest framing**: this is a deliberate widening, not a no-op extension.

---

## 3. Conceptual usability cross-link (codex P1.1 fold)

Founder asked: *"I want it within the same charter of human sutra"* (usability POV). Codex correctly rejected the architectural fold (PERMISSIONS.md is a sibling, not a sub-form). Reconciliation:

- **HUMAN-SUTRA-LAYER.md** gets a small "Related disciplines" section pointing to PERMISSIONS.md as the **sibling discipline** that handles harness-mediated permission friction (different actor, same goal: minimize founder friction). The pointer is documentation-only — no architectural fold, no new sub-form, no new cell.
- **PERMISSIONS.md** gets a reciprocal banner clarifying its sibling status: *"Sibling discipline to HUMAN-SUTRA-LAYER.md. Different actor (Claude Code harness vs H-Sutra Stage-3 model). Both close founder-friction gaps."*

Founder reads ONE charter to start (HUMAN-SUTRA-LAYER); the cross-link surfaces PERMISSIONS as the sibling for permission-specific concerns.

---

## 4. Telemetry extension (codex P3 fold)

`.enforcement/permission-gate.jsonl` schema gains 3 fields:

| Field | Type | Values |
|---|---|---|
| `tool_class` | string | `bash` · `write` · `edit` · `mcp` · `edit-first-time` |
| `tool_family` | string \| null | for MCP: `slack` · `gmail` · `apollo` · `atlassian` · `hubspot` · `drive` · `calendar` · `read_ai` · `playwright` · `context7` · `unknown`. For non-MCP: `null`. |
| `decision_basis` | string | `tier-1` · `trust-mode-allowlist` · `trust-mode-denylist` · `mcp-allowlist` · `mcp-denylist` · `tier-3-deny` · `first-time-edit-allow` · `first-time-edit-prompt` |

Backward-compat: existing rows simply omit these fields. Aggregation queries default missing values.

---

## 5. Implementation files

| File | Change |
|---|---|
| `sutra/marketplace/plugin/lib/mcp_trust_mode.py` | NEW — read-verb allowlist regex + mutator/send pattern denylist |
| `sutra/marketplace/plugin/hooks/permission-gate.sh` | extend dispatch: route `mcp__*` to `mcp_trust_mode.py`; route `Edit`/`Write` to first-time-edit logic |
| `sutra/marketplace/plugin/hooks/hooks.json` | PermissionRequest matcher widened: `Bash\|Write\|Edit\|MultiEdit` → `Bash\|Write\|Edit\|MultiEdit\|mcp__.*` |
| `sutra/os/charters/PERMISSIONS.md` | sibling banner + new §3 covering MCP allowlist/denylist + first-time-edit |
| `sutra/os/charters/HUMAN-SUTRA-LAYER.md` | new §Related disciplines cross-link to PERMISSIONS.md |
| `sutra/marketplace/plugin/PERMISSIONS.md` | user-facing manifest — document MCP + first-time-edit additions |
| `sutra/marketplace/plugin/tests/permission-gate-test.sh` | add fixtures: MCP read auto · MCP send prompt · first-time edit cwd auto · .env edit prompt · Playwright snapshot auto · Playwright click prompt |

Per codex P3 fold: **single atomic commit per repo** (submodule + holding pointer, each atomic).

---

## 6. Codex consult

Two rounds.

**R1 (CHANGES-REQUIRED, 2026-05-01, DIRECTIVE-ID 1777641500)** — 6 findings: 2 P1 (H-Sutra fold framing wrong as Stage-3 sub-form / denylist mapping conflated semantic with technical + MCP catalog incomplete) + 2 P2 (first-time-edit exclusion list too thin / MCP matcher should be option-a not option-b) + 2 P3 (telemetry tool_class · single atomic commit). All 6 folded into the brief.

**R2 (ADVISORY, 2026-05-01, DIRECTIVE-ID 1777641500 continuation)** — verbatim verdict: *"This is no longer in blocker territory. The architecture is fixed, the denylist separation is fixed, and the remaining issues are tighten-before-ship advisories. CODEX-VERDICT: ADVISORY."*

R2 raised 4 advisory tightenings (A1 regex too wide AND too narrow / A2 first-time-edit infra/deploy surfaces missing / A3 Gmail mutator denylist missing entries / A4 §1 PreToolUse → PermissionRequest factual nit). All 4 folded directly into THIS ADR-003 implementation (no R3 round needed per `[Converge and proceed]`).

Verdict files: `.enforcement/codex-reviews/2026-05-01-adr-003-r1-consult.md`, `.enforcement/codex-reviews/2026-05-01-adr-003-r2-consult.md`. Brief (R1-folded, R2-advisory): `holding/research/2026-05-01-adr-003-permissions-h-sutra-fold-design-brief.md`.
