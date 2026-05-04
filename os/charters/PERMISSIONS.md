# Charter: Permissions

> **Sibling discipline to HUMAN-SUTRA-LAYER.md** (ADR-003, 2026-05-01). Different actor: Claude Code harness here vs H-Sutra Stage-3 model emission there. Both close founder-friction gaps where the founder must approve / do something the system could safely handle. ADR-001 §4 Rule 4's 6-domain irreversible denylist (semantic categories) is distinct from the 6 Bash detector categories below (technical Trust Mode patterns) — see ADR-003 §4 for the disambiguation.

**Objective**: Every Sutra operation that is architecturally safe executes without prompting the user; every request Sutra makes is human-readable and auditable.
**DRI**: Sutra-OS
**Contributors**: Engineering (hook), Marketplace (manifest), Governance (audit)
**Status**: ACTIVE
**Applies to**: Sutra marketplace plugin — all tiers (T1 Governance-only, T2 Product, T3 Self-host), all clients (T1-T4 per Asawa D34).
**Created**: 2026-04-24
**Review cadence**: Per release (plugin version bump), audited quarterly.
**Source plan**: Founder direction 2026-04-24 — "lots of permissions when using the plugin; can they be human-readable; can we ask one meta-permission instead of recurring ones."
**Governs**: Marketplace department's permission UX surface. Sibling of TOKENS (cost) and SPEED (latency) — this charter owns *friction* as a first-class measurable.

---

## 1. Why this charter exists

Sutra's v1.5.1 PERMISSIONS.md shipped a human-readable manifest and a `/core:permissions` command that prints a paste-able allow-list. Two residual gaps triggered this charter:

1. **Paste-mechanics fail new users.** Every new install still walks through ~40 individual prompts across `/core:start`, first hook fire, first marker write — unless the user knows to run `/core:permissions` *before* doing anything. Conversion at the install cliff is the single biggest drop-off in T4 fleet adoption.

2. **No policy ceiling on what Sutra may ask for.** The manifest describes the *current* set of permissions but not the *allowed* set. Without a charter, any future hook could silently widen the ask — a governance hole.

Founder ask (direct, 2026-04-24):

> "There are a lot of permissions being asked when someone uses the plugin... can a human-readable output be given there? How can we just ask the meta permission and not have the recurring permissions thing?"

This charter closes both gaps.

---

## 2. Key Result Areas (KRAs)

| # | KRA | Scope |
|---|---|---|
| 1 | **Scope policy** | What Sutra is permitted to request at each tier. The ceiling. |
| 2 | **Meta-permission mechanism** | One install consent → zero recurring prompts for in-scope operations. |
| 3 | **Human-readable manifest** | Every permission grouped by *user intent*, not by pattern type. |
| 4 | **Audit + telemetry** | Every auto-approval logged; quarterly allow-list audit. |

---

## 3. KPIs

| Tier | Metric | Formula | Source | Target | Warn | Breach |
|---|---|---|---|---|---|---|
| ★ NORTH STAR | **`prompts_per_first_session`** | count of permission-dialog fires during the user's first 30 min after `/plugin install sutra` | `session-logger.sh` → `holding/observability/LATEST.md` new panel | **≤2** (tier+config prompts only) | >5 | >10 |
| Driver | `auto_approve_hit_rate` | `auto_approved / (auto_approved + prompted)` per session | `.enforcement/permission-gate.jsonl` (new) | ≥95% | <80% | <50% |
| Guardrail | `auto_approve_false_positive` | Founder-reported cases of hook approving something it shouldn't have | Issue tracker tag `permission-scope` | 0 | ≥1 in 90d | ≥3 in 90d |
| Guardrail | `manifest_drift_pct` | `(hooks_behavior ∆ manifest_documented) / hooks_behavior` audited quarterly | `tests/permission-gate-test.sh` coverage diff | 0% | >5% | >15% |

---

## 4. Scope policy — what Sutra MAY request

### Tier 1 — Always permissible (any install, any client)

| Category | Pattern shape | Rationale |
|---|---|---|
| Plugin dispatcher | `Bash(sutra)`, `Bash(sutra <subcommand> ...)` | Bare `sutra` command is Sutra's single entrypoint; every `/core:*` slash command routes through it. |
| Plugin-internal scripts | `Bash(bash ${CLAUDE_PLUGIN_ROOT}/...)` | Plugin can only execute files inside its own cache dir. Path-scoped by Claude Code's cache isolation. |
| Plugin-internal hooks | `Bash(bash ${CLAUDE_PLUGIN_ROOT}/hooks/...)` | Same, for hook script invocations inside hook bodies. |
| Plugin lifecycle | `Bash(claude plugin marketplace update sutra)`, `Bash(claude plugin update core*)`, `Bash(claude plugin uninstall core*)` | Claude Code's own plugin-management commands, scoped to the Sutra plugin name. |
| Marker files | `Write(.claude/depth-registered)`, `Write(.claude/input-routed)`, `Write(.claude/sutra-deploy-depth5)`, `Write(.claude/build-layer-registered)` | Per-turn governance markers. Wiped by `reset-turn-markers.sh`. Not transmitted. |
| Project state | `Write(.claude/sutra-project.json)` | One-time install_id + project_id + telemetry_optin. |
| Local logs | `Write(.claude/sutra-estimation.log)`, `Write(.claude/logs/*)` | Telemetry captured at Stop events. Never leaves machine unless `telemetry_optin=true` AND user runs `sutra push`. |
| Filesystem setup | `Bash(mkdir -p .claude*)`, `Bash(mkdir -p .enforcement*)` | First-use directory creation, scoped to `.claude/` and `.enforcement/` only. |

### Tier 1.5 — Compositional reads (v2.4, REMOVED in v2.7.0)

Removed in v2.7.0. The five-gate compositional matcher (`sh_lex_check.py`,
228 LoC) was a v2.4 strict-allowlist artifact. Trust Mode (Tier 1.6, below)
is a strict superset for Bash auto-approval — every command Tier 1.5 allowed
also passes Trust Mode unless it falls into one of the prompt categories.
The dual-matcher introduced drift (codex review 2026-04-28) and added zero
catch coverage under the trusted-operator threat model.

**Removed artifacts** (v2.7.0):
- `sutra/marketplace/plugin/lib/sh_lex_check.py`
- `sutra/marketplace/plugin/scripts/rollback-compositional.sh`
- `sutra/marketplace/plugin/tests/unit/test-sh-lex-check.sh`
- `sutra/marketplace/plugin/tests/unit/test-permission-gate-compositional.sh`
- `sutra/marketplace/plugin/tests/unit/test-rollback-compositional.sh`
- `_match_bash_compositional` + `_env_has_shadowing` in `permission-gate.sh`
- `_bash_summary_env_shadowing` + `_is_allowlisted` mirror branch in `bash-summary-pretool.sh`

**Reversion path**: if the threat model expands to multi-actor or untrusted
env, restore Tier 1.5 from git history (last commit before v2.7.0).

### Tier 1.6 — Trust Mode (v2.5+, sole Bash matcher post-v2.7.0)

**Threat model**: Trust Mode assumes a single trusted local operator on a personally managed machine, no adversarial prompt/file/environment injection, and reserves prompts only for commands with high risk of irreversible local loss, privilege escalation, or remote/shared-state mutation.

**Decision rule**: Auto-approve every Bash command EXCEPT those matching one of the prompt categories below. Inverts v2.4's strict allowlist. v2.7.0 removed Tier 1.5 (the v2.4 compositional matcher) — Trust Mode is now the sole Bash auto-approve path.

**6 prompt categories** (commands matching any of these fall through to the normal permission dialog — user makes the call):

| # | Category | Detection |
|---|---|---|
| 1 | **Git catastrophic mutations** (v2.6.1+ catastrophic-only) | `git push --force`/`-f`/`--force-with-lease` (rewrites/destroys remote history); `git clean -f`/`-fd`/`-fdx`/`-fx` (irrecoverable untracked deletion). Everything else (`commit`, `push` non-force, `pull`, `rebase`, `merge`, `reset --hard`, `checkout`, `branch -D`, `tag -d`, `stash drop`, `rm`, `mv`) auto-approves — recoverable via reflog or remote. Per founder direction "keep it simple — only delete-class catastrophic." |
| 2 | **Privilege escalation** | leading token: `sudo`, `su`, `doas`, `pkexec` |
| 3 | **Recursive deletes outside safe-path allowlist** | `rm -rf` / `rm -r` / `rm -R` UNLESS every positional path matches `dist\|build\|out\|.next\|node_modules\|.cache\|cache\|tmp\|.tmp\|coverage\|target\|.turbo\|.parcel-cache\|.pytest_cache\|__pycache__` (with optional `./` or `/tmp/` prefix) |
| 4 | **Disk/system catastrophes** | leading token: `dd`, `diskutil`, `launchctl`, `defaults`, `fdisk`, `parted`, `mount`, `umount`, `kextload`, `kextunload`, `mkfs.*`; OR `chmod -R`/`chown -R` anywhere |
| 5 | **Fetch-and-exec** | regex: `(curl\|wget\|fetch\|http)…\|…(sh\|bash\|zsh\|ksh\|fish\|dash)` |
| 6 | **Remote / shared-state mutations** | leading token: `ssh`, `scp`, `rsync`, `aws`, `gcloud`, `vercel`, `supabase`, `doctl`, `fly`, `heroku`, `kubectl`, `helm`, `ansible`, `terraform`, `pulumi`, `render`, `railway`, `netlify`, `psql`, `mysql`, `mongo`, `mongosh`, `redis-cli`, `sqlite3`, `duckdb`; OR regex: `(npm\|yarn\|pnpm\|bun) publish`, `docker (push\|login)`, `(pip\|twine\|poetry) (upload\|publish)`. **`gh` is catastrophic-only (v2.6.1+):** auto-approves ALL `gh ...` invocations EXCEPT delete-class actions (token ∈ {`delete`, `remove`}). Prompts on: `gh repo delete`, `gh release delete`, `gh secret delete`/`remove`, `gh issue delete`, `gh codespace delete`, `gh label delete`, `gh extension remove`, `gh gist delete`, `gh variable delete`. `gh api` auto-approves all methods. Per founder direction "Unless they're very catastrophic, like delete." |

Helper: `sutra/marketplace/plugin/lib/sh_trust_mode.py` — Python regex/case detector. Reads stdin, prints `{"prompt": bool, "category": str, "reason": str}`. Fail-safe-to-prompt on lex errors.

**Recovery model (why this is safe enough)**: anything NOT in the 6 categories is recoverable via local fs, git, Time Machine. The 6 catch every irreversible / shared-state / privilege-elevating operation. Approval fatigue (50 blind-approves per session) was a worse security mode than the 6-prompt baseline.

**Exit ramp**: if threat model changes (multi-user, prompt injection, untrusted env), restore the v2.4 Tier 1.5 strict-allowlist matcher from git history (last commit before v2.7.0 — `sh_lex_check.py` + `_match_bash_compositional` + env-shadowing guards) and re-register it ahead of Trust Mode in `permission-gate.sh`'s dispatch.

### Tier 1.7 — MCP tool auto-approve (ADR-003, v2.17.0+; AMENDED v2.32.0)

**v2.32.0 amendment** (founder direction 2026-05-04 "do it"): rule flipped from "read-allowlist + mutator-prompt" to **catastrophic-only deny**, aligning with Bash Trust Mode (v2.6.1). The v2.17 posture prompted on every MCP mutation (every Slack send, every Jira create, every Drive create_file) — that asymmetry vs Bash's catastrophic-only rule produced ~95% of remaining MCP prompt friction with no incremental safety under the single-trusted-operator threat model. Catastrophic floor preserved: deletes, code execution, mass mutations, and per-vendor high-impact actions still prompt.

**Threat model**: same as Trust Mode (single trusted local operator on a personally managed machine, no adversarial prompt/file/environment injection).

**Decision rule (v2.32.0+)**: auto-approve every MCP tool EXCEPT (a) catastrophic verb tokens, (b) bulk/mass mutators, (c) per-vendor explicit catastrophes. Implementation: `lib/mcp_trust_mode.py` (separate from `sh_trust_mode.py` to keep shell vs MCP semantics decoupled).

**Catastrophic verb tokens (vendor-agnostic, always prompt)**: `delete`, `destroy`, `drop`, `purge`, `wipe`, `truncate`, `eradicate`, `expunge`, `uninstall`, `deauthorize`.

**Bulk / mass mutation patterns (always prompt)**: `bulk_*`, `batch_modify`, `batch_delete`, `mass_*`, `apply_labels`, `bulk_label`.

**Per-vendor explicit catastrophes (TIGHT — only true catastrophes that don't reduce to a verb token)**:

| Vendor | Tool | Why prompt |
|---|---|---|
| Playwright | `browser_run_code_unsafe`, `browser_evaluate` | JavaScript code execution in user's browser context |
| Gmail | `_forward_` | Data exfiltration risk (email forward to arbitrary recipient) |
| Drive | `move_to_trash`, `_trash_` | Irreversible without restore action |

**v2.17 → v2.32 net behavior change**: routine create/update/send across all vendors (Slack send-message, Gmail create-draft, Calendar create-event, Atlassian createJiraIssue, HubSpot manage_crm_objects, Apollo *_create, Drive create_file, Playwright browser_click/type/navigate, etc.) now **auto-approve**. Catastrophes (deletes, mass-mutations, code-exec, data-forward) still prompt.

**v2.17 legacy decision rule (deprecated)**: read-verb allowlist regex + per-vendor mutator/send denylist + safe-default-prompt-on-fall-through. Preserved in git history (last commit before v2.32.0) for emergency reversion if threat model expands to multi-actor / untrusted-env. The v2.17 denylist (Slack send/canvas, Gmail send/forward/delete/archive/label-mutations, Drive create/copy/batch-update/import, Calendar create/update/delete/respond, Apollo create/update/campaigns, Atlassian create/edit/transition/comment/worklog, HubSpot manage-crm/feedback, Playwright stateful click/fill-form/navigate/run-code-unsafe) is now redundant — only the catastrophic subset survives in v2.32.

**Allowlist (read-class)** — verbs include `search`, `list`, `get`, `read`, `fetch`, `query`, `describe`, `enrich`, `match`, `status`, `info`, `view`, `metadata`, `count`, `index`, `profile`, `resolve`, `open`, `outline`, `availability`, `preview`, `download`. Anchored regex; drift-prone names like `get_or_create`, `read_write`, `fetch_and_delete` will NOT match (fall through to prompt).

**Denylist (mutator/send-class, always prompts)** by vendor family:

| Vendor | Tools that prompt |
|---|---|
| Slack | `slack_send_message`, `slack_send_message_draft`, `slack_schedule_message`, `slack_create_canvas`, `slack_update_canvas` |
| Gmail | `create_draft`, `update_draft`, send-class (`*_send_*`, `*_forward_*`, send-draft execution), `delete_thread`, `delete_message`, `archive_*`, label mutations (`label_message`, `label_thread`, `unlabel_message`, `unlabel_thread`, `create_label`, `apply_labels_*`, `batch_modify_*`, `bulk_label_*`) |
| Google Drive | `create_file`, `copy_file`, `batch_update_*`, `import_*`, `template-copy_*`, `duplicate-sheet_*` |
| Google Calendar | `create_event`, `update_event`, `delete_event`, `respond_to_event` |
| Apollo | `apollo_*_create`, `apollo_*_update`, `apollo_emailer_campaigns_*`, `apollo_organizations_bulk_enrich` |
| Atlassian Rovo | `createJiraIssue`, `editJiraIssue`, `transitionJiraIssue`, `addCommentToJiraIssue`, `addWorklogToJiraIssue`, `createConfluencePage`, `updateConfluencePage`, `createConfluenceFooterComment`, `createConfluenceInlineComment`, `createIssueLink` |
| HubSpot | `manage_crm_objects`, `submit_feedback` |
| Read.ai | (none — passive reads `list_meetings`, `get_meeting_by_id` auto-approve) |
| Playwright stateful | `browser_click`, `browser_drag`, `browser_drop`, `browser_evaluate`, `browser_fill_form`, `browser_file_upload`, `browser_handle_dialog`, `browser_hover`, `browser_navigate`, `browser_navigate_back`, `browser_press_key`, `browser_resize`, `browser_run_code_unsafe`, `browser_select_option`, `browser_tabs`, `browser_type`, `browser_wait_for`, `browser_close` |

**Decision precedence**: prompt-list ALWAYS wins over allowlist regex. Anything not matched by either falls through to prompt.

### Tier 1.8 — First-time Edit/Write/NotebookEdit inside cwd (ADR-003, v2.17.0+; v2.32 includes NotebookEdit)

**Threat model**: deliberate widening of Tier 3 (acknowledged — see ADR-003 §3.2 honesty section). Same single-trusted-operator threat model as Trust Mode; recovery via git/backups/fs trash.

**Decision rule**: auto-approve `Edit`/`Write`/`MultiEdit`/`NotebookEdit` (NotebookEdit added v2.32.0) to paths inside cwd-tree, EXCEPT entries in the prompt-list below.

**Prompt-list** (overrides allow):
- `.claude/settings*.json` (Claude Code hardcoded guard — not bypassable anyway)
- `.env*` (secrets surface)
- `.git/**` (repo metadata)
- `.npmrc`, `.pypirc` (publish auth)
- `**/credentials.json`, `**/secrets.yaml`, `**/.secret*` (generic secret patterns)
- `.github/workflows/**`, `.circleci/**`, `.gitlab-ci.yml` (CI config)
- `vercel.json`, `fly.toml`, `render.yaml`, `netlify.toml` (deploy config)
- `docker-compose*.yml`, `docker-compose*.yaml` (container orchestration)
- `k8s/**`, `helm/**/values*.y*ml` (Kubernetes + Helm)
- `.terraform/**`, `*.tfvars`, `*.tf` (infrastructure-as-code)
- `Pulumi.*` (Pulumi config)
- `wrangler.toml`, `railway.json`, `firebase.json` (Cloudflare/Railway/Firebase deploy)
- `cloudbuild.yaml`, `app.yaml` (GCP)
- `supabase/**` (Supabase backend config)
- Anything outside cwd (cross-company / cross-project — Tier 3 preserved)

### Tier 1.9 — Web Trust Mode (v2.32.0+, WebFetch / WebSearch)

**Threat model**: same as Trust Mode — single trusted local operator, no adversarial network. Public http(s) URLs auto-approve; internal/metadata/private endpoints prompt to defend against SSRF and cloud-metadata exfiltration.

**Decision rule**: auto-approve `WebFetch` and `WebSearch` EXCEPT WebFetch URLs targeting (a) loopback hostnames (`localhost`, `ip6-localhost`, `ip6-loopback`), (b) IP addresses parsing as loopback / private / link-local / multicast / reserved (covers `127.0.0.0/8`, `0.0.0.0`, `::1`, `fc00::/7` ULA, `fe80::/10` link-local, `169.254.0.0/16` cloud metadata service, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` RFC1918), or (c) non-http schemes (`file://`, `ftp://`, `gopher://`, `dict://`, `ldap://`, `tftp://`, `jar://`).

**Rationale**: cloud-metadata service (`169.254.169.254`) is the canonical SSRF exfiltration vector for AWS / GCP / Azure credentials; RFC1918 addresses enable LAN port scanning; `file://` enables local-file disclosure (`file:///etc/passwd`). All three classes prompt; everything else (public web docs, blog posts, GitHub, npm registry, etc.) auto-approves. WebSearch has no URL parameter and auto-approves unconditionally.

Helper: `sutra/marketplace/plugin/lib/web_trust_mode.py` — Python URL classifier using `ipaddress` module for accurate private-range detection. Reads PermissionRequest JSON on stdin, prints `{"prompt": bool, "category": str, "reason": str}`. Fail-safe-to-prompt on parse errors.

**Supersedes Tier 3 v2.17 line "Any network call other than `sutra push` (opt-in only)"** — that absolute network ban was a privacy floor designed before WebFetch was a recurring friction class. Net behavior: outbound writes (Bash `curl POST`, telemetry push) still gated separately; inbound reads (WebFetch on documentation URLs) auto-approve when targeting public hosts.

### Tier 1.10 — Subagent dispatch (Task tool, v2.32.0+)

**Threat model**: subagents inherit `PreToolUse` / `PostToolUse` hooks deterministically (verified empirically 2026-04-24, archived at `holding/research/2026-04-24-subagent-contract-archive.jsonl`). Governance is enforced *inside* the subagent context at the action point — not at dispatch time. Auto-approving `Task` does not widen any policy; the subagent's own tool calls go through the same `permission-gate.sh` dispatch.

**Decision rule**: auto-approve every `Task` invocation with `MATCHED_PATTERN="Task"` and `decision_basis="task-auto-approve"`. Telemetry: `tool_class=task`, `tool_family=null`. No URL/path/command to validate at dispatch level.

### Tier 2 — Permissible when feature enabled in `os/SUTRA-CONFIG.md`

| Feature | Additional patterns | Enabled by |
|---|---|---|
| `telemetry_optin=true` | `Bash(gh auth status)`, network calls from `sutra push` | Explicit opt-in flag. |
| `codex_review` hook enabled | `Write(.enforcement/codex-reviews/*)`, `Write(.claude/codex-directive-pending)` | `enabled_hooks.codex-review-gate: true` in SUTRA-CONFIG. |
| `keys-in-env-vars` hook enabled | Read-only content scan — no additional Write scope | `enabled_hooks.keys-in-env-vars: true`. Default-OFF per D32. |

### Tier 3 — NEVER permissible (hard-coded deny in hook logic)

| Pattern | Why forbidden |
|---|---|
| Any path outside `.claude/`, `.enforcement/`, `.context/`, or plugin cache (governance writes only) | Sutra is governance OS, not general-purpose filesystem tool. (First-time-edit inside cwd is Tier 1.8, deliberately widened — see that section.) |
| WebFetch to loopback / RFC1918 / 169.254.* / IPv6 ULA+link-local / non-http schemes | SSRF + cloud-metadata exfiltration defense (v2.32+). Replaces v2.17's "Any network call other than `sutra push`" absolute ban — see Tier 1.9. |
| Any access to `~/.ssh`, `~/.aws`, `~/.gnupg`, Keychain | Credentials are never in Sutra's threat model. |
| Any `sudo`, `su`, privilege escalation | Sutra runs at user-level only. |
| MCP catastrophic verbs / bulk patterns / per-vendor catastrophes (Playwright code-exec, Gmail forward, Drive trash) | Irreversible / large-scale / high-impact mutations on shared external state (v2.32+). See Tier 1.7 for the full catastrophic deny-list. |
| Shell combinators widening scope past Sutra operations (`;`, `&&`, `||`, `|`, `&` backgrounding, backticks, `$(...)`, redirections, `bash -c`/`sh -c`, `eval`, `exec`, control chars including newlines and CR) — within Tier 1 match path only | Defense against command-injection inside matched patterns. Trust Mode (v2.5+) evaluates first-token only by design (single-trusted-operator threat model); compound commands like `sutra ;rm -rf /` reach Trust Mode where the first token determines decision. |

**Any future hook that needs a permission outside Tier 1 must update this charter FIRST, then ship the hook.**

---

## 5. Meta-permission mechanism

### Implementation: `PermissionRequest` hook

Claude Code fires a `PermissionRequest` event before every permission dialog. A hook that returns `{"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow", "updatedPermissions": [...]}}}` auto-approves the pending tool call AND persists the matched rule to `.claude/settings.local.json` so future invocations are silent without any hook execution cost.

Mechanism file: `sutra/marketplace/plugin/hooks/permission-gate.sh` (L0, plugin-native).

### First-session flow (fleet goal)

```
Session 1, minute 0:  /plugin install sutra@marketplace            ← consent 1 (Claude Code's plugin consent)
Session 1, minute 1:  /core:start                                  ← triggers ~8 tool calls
                      ├─ Bash(sutra start)                         → permission-gate matches → auto-allow + persist
                      ├─ Write(.claude/sutra-project.json)         → permission-gate matches → auto-allow + persist
                      ├─ Write(.claude/depth-registered)           → permission-gate matches → auto-allow + persist
                      └─ (5 more)                                  → all auto-approved
Session 1 end:        8 rules now in .claude/settings.local.json
Session 2+:           zero hook invocations for in-scope ops — Claude Code's allow-list handles it directly.
```

### Fail-open posture

If the hook crashes, times out, or returns malformed JSON: Claude Code falls back to normal prompt flow. **We never auto-deny through this hook.** Deny stays manual (user clicks "No") or via explicit deny rules in Tier 3.

### Kill-switch

- Per-user global: `touch ~/.sutra-permissions-disabled`
- Per-session env: `SUTRA_PERMISSIONS_DISABLED=1`
- Per-config: set `auto_approve_permissions: false` in `os/SUTRA-CONFIG.md` (future — not live v1.13.0)

---

## 6. Human-readable manifest contract

`sutra/marketplace/plugin/PERMISSIONS.md` must satisfy:

| Requirement | Implementation |
|---|---|
| Group by user intent, not pattern type | Sections titled "Starting a session", "Writing governance markers", "Lifecycle operations" — not "Bash rules / Write rules". |
| Every row carries: what fires it, why needed, blast radius | Table with columns `Pattern / When it fires / Why / Blast radius`. |
| Tier labeling | Tier 1 (always) / Tier 2 (opt-in) / Tier 3 (forbidden) visible per section. |
| Version header | `Plugin version: X.Y.Z · Manifest updated: YYYY-MM-DD` on line 3. |
| Out-of-scope statement | Explicit "Sutra does NOT need permission for..." negative list. |
| Audit trail | Last 3 permission-scope changes summarized. |

Manifest drift against hook behavior is detected by `tests/permission-gate-test.sh` — CI gate on every plugin version bump.

---

## 7. Operationalization

### 1. Measurement mechanism

- Per-call: `.enforcement/permission-gate.jsonl` — one line per hook fire, fields: `ts, tool, matched_pattern, decision, persisted`.
- Per-session: `prompts_per_first_session` panel added to `holding/observability/LATEST.md` (session-logger extension).
- Per-release: `tests/permission-gate-test.sh` diff-audits manifest against hook allow-list.

### 2. Adoption mechanism

- Plugin v1.13.0 ships `permission-gate.sh` registered in `hooks.json` under `PermissionRequest` matcher `Bash|Write|Edit|MultiEdit`.
- Default-ON (contrast to D32's default-off for governance hooks — this is UX, not enforcement).
- Fleet upgrade: `claude plugin marketplace update sutra` on each instance.

### 3. Monitoring / escalation

- Founder reviews `prompts_per_first_session` monthly in OBSERVABILITY-PULSE.
- Warn: `auto_approve_hit_rate < 80%` → allow-list incomplete; add missing patterns.
- Breach: `auto_approve_false_positive ≥ 1` → immediate hook patch; post-mortem in `.enforcement/`.

### 4. Iteration trigger

- Any new hook that writes outside current Tier 1 scope → charter §4 update BEFORE hook ships (PROTO-000).
- Founder-reported friction ("this is still prompting for X") → add pattern to allow-list with evidence in commit message.

### 5. DRI

- **Charter**: Sutra-OS (Asawa-CEO).
- **Hook**: Plugin Marketplace dept (`sutra/marketplace/plugin/hooks/`).
- **Manifest**: Plugin Marketplace dept (`sutra/marketplace/plugin/PERMISSIONS.md`).
- **Audit**: Quarterly, Asawa-CEO.

### 6. Decommission criteria

- Claude Code ships native plugin-level `permissions.allow` bundling (currently only `agent` + `subagentStatusLine` keys supported per 2026-04-24 plugins-reference doc line 695). When that lands, this hook becomes redundant — migrate the allow-list into `plugin.json` and retire `permission-gate.sh`.
- Sutra stops shipping hooks that need Write scope (unlikely).

---

## 8. PROTO-000 bundle

| Artifact | Path |
|---|---|
| Words (charter) | `sutra/os/charters/PERMISSIONS.md` (this file) |
| Mechanism (hook) | `sutra/marketplace/plugin/hooks/permission-gate.sh` |
| Test (PROTO-000) | `sutra/marketplace/plugin/tests/permission-gate-test.sh` |
| Deploy (registered) | `sutra/marketplace/plugin/hooks/hooks.json` §PermissionRequest |
| User-facing doc | `sutra/marketplace/plugin/PERMISSIONS.md` |
| Version bump | `sutra/marketplace/plugin/.claude-plugin/plugin.json` → 1.13.0 |
| Changelog | `sutra/marketplace/plugin/CHANGELOG.md` [1.13.0] entry |

---

## 9. Stems

permissions-charter, meta-permission, permission-gate, friction-reduction, fleet-install-ux, tier-policy, auto-approve-hook
