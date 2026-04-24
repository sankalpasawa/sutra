# Charter: Permissions

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

### Tier 1.5 — Compositional reads (v2.4+)

Read-only shell compositions over a fixed primitive whitelist are auto-approved
when the entire composition passes ALL five gates. This table is **NORMATIVE**
— the `sh_lex_check.py` helper at `sutra/marketplace/plugin/lib/` reproduces
exactly these rules.

**Gate 1 — Pre-tokenization hard rejects.** Reject if the raw command contains
any of: control chars (bytes < 0x20 other than space/tab), CR (`\r`),
substring `$(`, backtick, `<(`, `>(`, `<<`, `bash -c`, `sh -c`, `zsh -c`,
` eval `, ` exec `; or starts with `eval ` or `exec `.

**Gate 2 — Environment shadowing check.** Reject if any allowlisted primitive
is shadowed. Two checks, both must pass:
  - **2a — Fast-path env regex:** match `^BASH_FUNC_<primitive>(%%|\(\))=`
    against each env row (covers patched bash 4.3+).
  - **2b — Universal fallback:** for each allowlisted primitive, call
    `declare -F <primitive>` in the hook's shell. This is the load-bearing
    check; it catches legacy bash formats, non-exported inherited functions,
    and anything else shell-visible.
Fail either → fall through to normal prompt.

**Gate 3 — Tokenization with `shlex(posix=True, punctuation_chars=True)`.**
Unclosed quotes → `ValueError` → reject. Fold (remove) the 3-token sequences
`['2', '>&', '1']` (`2>&1`) and `['2', '>', '/dev/null']` (`2>/dev/null`) from
the stream. After folding, reject if ANY token equals `>`, `<`, `&`, `>>`,
`<<`, `>|`, `&>`, `>&`.

**Gate 4 — Pipeline operators.** Allowed between segments: `;`, `&&`, `||`, `|`.
Any other token acts as a segment separator only if it is one of those four.

**Gate 5 — Primitive whitelist (segment leading token).**

| Primitive | Flag denylist (reject if matched) | Positional-arg rule |
|---|---|---|
| `ls` | — | paths OK |
| `cat` | — | paths OK |
| `head` | — | paths OK |
| `tail` | `-F`, `--retry`, `--follow=name` | paths OK; `-f` allowed (stdout-only) |
| `wc` | — | paths OK |
| `echo` | — | literal strings |
| `printf` | `-v`, `%n` in format string (bytes-so-far write; defanged without `-v` but blocked for strict read-only) | format + args |
| `pwd` | — | no args |
| `date` | `-s`, `--set`, `-d`, `--date` | `+FMT` OK |
| `whoami` | — | no args |
| `which` | — | cmd names |
| `basename` | — | path |
| `dirname` | — | path |
| `realpath` | — | paths |
| `grep` | `--devices=` | pattern + paths |
| `cut` | — | paths |
| `uniq` | — | ≤1 positional (2nd positional = output file) |
| `tr` | — | ≤2 positional (SET strings only; no file args) |
| `column` | `-J` | optional path |

A primitive name (segment leading token) not in this table → reject.

**Codex round 5 removal (2026-04-25):** `sort` was considered but removed
because GNU `sort` can spill temp files to `$TMPDIR`/`/tmp` on large input
even without `-o`, violating the strict read-only posture. If a future need
emerges, re-introducing `sort` requires charter amendment + a forced
`TMPDIR=/dev/null` wrapper or equivalent mitigation.

**Not in Tier 1.5** (explicit denylist — these continue to prompt):
`git`, `sed`, `find`, `awk`, `xargs`, `bash`, `sh`, `zsh`, `python`,
`python3`, `node`, `ruby`, `perl`, `curl`, `wget`, `ssh`, `scp`, `rsync`,
`cp`, `mv`, `rm`, `ln`, `mkdir`, `touch`, `chmod`, `chown`, `dd`, `kill`,
`pkill`, `killall`, `tar`, `zip`, `gzip`, `gunzip`, `unzip`, `nc`, `socat`,
`sudo`, `su`, `sort`.

**Widening rule**: a future release that needs to add a primitive to Gate 5
MUST amend this charter block FIRST, then ship the hook change. The flag
denylist in Gate 5 is normative. Tokenization and `BASH_FUNC_*` shadowing
(Gates 2-3) are non-negotiable floors.

**Known limitations (accepted false-negatives, NOT security gaps):**
- `grep ";" file`: shlex posix mode strips quotes from standalone punctuation
  chars. The literal `;` is indistinguishable from a separator. User approves
  manually once per session.
- `grep -F '$(' file`: literal text search for `$(` triggers Gate 1 reject.
  Rare benign pattern; user approves manually.

### Tier 2 — Permissible when feature enabled in `os/SUTRA-CONFIG.md`

| Feature | Additional patterns | Enabled by |
|---|---|---|
| `telemetry_optin=true` | `Bash(gh auth status)`, network calls from `sutra push` | Explicit opt-in flag. |
| `codex_review` hook enabled | `Write(.enforcement/codex-reviews/*)`, `Write(.claude/codex-directive-pending)` | `enabled_hooks.codex-review-gate: true` in SUTRA-CONFIG. |
| `keys-in-env-vars` hook enabled | Read-only content scan — no additional Write scope | `enabled_hooks.keys-in-env-vars: true`. Default-OFF per D32. |

### Tier 3 — NEVER permissible (hard-coded deny in hook logic)

| Pattern | Why forbidden |
|---|---|
| Any path outside `.claude/`, `.enforcement/`, `.context/`, or plugin cache | Sutra is governance OS, not general-purpose filesystem tool. |
| Any network call other than `sutra push` (opt-in) | Privacy floor (PRIVACY.md). |
| Any access to `~/.ssh`, `~/.aws`, `~/.gnupg`, Keychain | Credentials are never in Sutra's threat model. |
| Any `sudo`, `su`, privilege escalation | Sutra runs at user-level only. |
| Shell combinators widening scope past Sutra operations (`;`, `&&`, `||`, `|`, `&` backgrounding, backticks, `$(...)`, redirections, `bash -c`/`sh -c`, `eval`, `exec`, control chars including newlines and CR) | Defense against command-injection inside matched patterns. |

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
