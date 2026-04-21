# Sutra Plugin — First-Run Walkthrough (CM3)

*Purpose: scripted T+0 → T+60s experience for a user who has never seen Sutra before. Reproducible demo + doc for announcement.*
*Version covered: plugin v1.2.1 from `sankalpasawa/sutra` marketplace, 2026-04-21.*

---

## Pre-requisites (one-time, user machine)

- Claude Code CLI installed (`claude --version` works)
- git + gh CLI configured (for marketplace pull + optional telemetry push)
- Any project directory (or `mkdir /tmp/try-sutra && cd /tmp/try-sutra`)

---

## T+0 to T+60s

### T+0s — add the marketplace

```bash
claude plugin marketplace add sankalpasawa/sutra
```

Expected output:

```
Adding marketplace…
✔ Marketplace 'sutra' added
```

(If already added: `✔ Marketplace 'sutra' already on disk`.)

### T+5s — install the plugin

```bash
claude plugin install sutra@sutra
```

Expected output:

```
✔ Plugin "sutra" installed at user scope (v1.2.1)
  Restart Claude Code to activate.
```

### T+15s — verify

```bash
claude plugin list | grep sutra
```

Expected:

```
❯ sutra@sutra
  Version: 1.2.1
  Scope: user
  Status: ✔ enabled
```

### T+20s — open a Claude Code session in any dir

```bash
cd ~/any-project
claude
```

On session start, Sutra's skills (`input-routing`, `depth-estimation`, `readability-gate`, `output-trace`) auto-register. No restart noise.

### T+30s — activate in-session

Inside Claude Code, type:

```
/sutra:sutra-go
```

First-time behavior:

1. Writes `.claude/sutra-project.json` with `install_id`, `project_id`, `telemetry_optin=true`
2. Initializes `~/.sutra/metrics-queue.jsonl`
3. Prints the activation banner
4. Returns control to founder

### T+45s — first governed task

Ask Claude anything that triggers an Edit or Write. Example:

> Add a README with project name.

Expected Sutra behavior BEFORE the edit:

1. `INPUT / TYPE / ROUTE / FIT CHECK / ACTION` block emitted (input-routing skill)
2. `TASK / DEPTH / EFFORT / COST / IMPACT` block emitted (depth-estimation skill)
3. Depth marker written to `.claude/depth-registered`
4. Edit proceeds
5. Output trace line at end

If the markers are missing, PreToolUse hook warns (does NOT block in v1.2 — hardening is v0.2+).

### T+60s — observe artifacts

```bash
cat .claude/sutra-project.json      # install + project identity
cat .claude/depth-registered        # current task depth marker
cat .claude/sutra-estimation.log    # every task with depth + ts
ls ~/.sutra/                        # metrics-queue.jsonl
```

User has done one governed task end-to-end. Plugin is live.

---

## What happens next (user-driven)

| Command | Purpose |
|---|---|
| `/sutra:sutra-status` | Show install_id / project_id / queue depth / last flush |
| `/sutra:sutra-push` | Manual telemetry push (auto-push runs on Stop if opt-in=true) |
| `/sutra:depth-check` | Re-emit depth block mid-task if missing |
| `sutra-go` (shell, if helpers installed) | Fresh temp project + Sutra + Claude opened |

---

## Known rough edges (v1.2.1)

- PreToolUse hooks are warn-only. Missing depth marker is flagged, not blocked. Hard enforcement lands in v0.2+.
- Command namespace shows as `/sutra:sutra-onboard` etc. (redundant sutra- prefix). Rename queued for v1.1.2 / v1.3.
- Telemetry auto-push requires gh CLI auth + write access to `sankalpasawa/sutra-data` (portfolio-scope only). External users get local-only queue; supabase transport ships in v2.
- No Windows support. Bash only.
- No install timer / telemetry for install funnel itself (OKR 1.1, 1.4 — pending).

---

## Rollback

```bash
claude plugin uninstall sutra@sutra
claude plugin marketplace remove sutra
rm -rf ~/.sutra                     # clears telemetry queue (irreversible)
```

Or if shell helpers were installed:

```bash
sutra-uninstall    # removes plugin + marketplace, keeps data
sutra-reset        # removes plugin + marketplace + ~/.sutra (factory)
```

---

## Script-for-video (60s demo reel)

```
0s:  "Install Sutra in your terminal."
5s:  [shows] claude plugin marketplace add sankalpasawa/sutra
10s: [shows] claude plugin install sutra@sutra
20s: "Open Claude in any project."
25s: [shows] cd ~/my-project && claude
35s: "Type slash-sutra-go."
40s: [shows] /sutra:sutra-go — banner + activation
50s: "Ask Claude to do anything."
55s: [shows] "Add a README" → routing block + depth block before edit
60s: "That's it. Governance on every task, from any project."
```

---

*Authored: 2026-04-21. Verified against live install pipeline (v1.2.0 → v1.2.1 update confirmed).*
