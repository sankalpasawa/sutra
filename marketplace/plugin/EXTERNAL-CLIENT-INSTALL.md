# External Client Install — Sutra Plugin

**Version**: v1 (Phase 5 deliverable, 2026-04-23)
**Audience**: new external client onboarding (DayFlow · Paisa · Billu · future)
**Companion**: `sutra/INTERFACE-CONTRACTS.md` (Phase 2)

---

## One-command install

```
/plugin install sutra@marketplace
```

That's it. No 4-step ceremony.

---

## What lands in your repo after install

| Path | Purpose |
|---|---|
| `.claude/plugins/sutra/` | Plugin cache (read-only) |
| `.claude/settings.json` | Hook registration (managed by plugin) |
| `os/SUTRA-CONFIG.md` | Per-client config you edit to enable features |
| `os/SUTRA-VERSION.md` | Version pin (managed by plugin) |
| `.enforcement/` | Audit logs (auto-created) |
| `.context/` | Session context (codex-session-id etc.) |

---

## Tier selection (choose one at install)

| Tier | What's on | Who uses this |
|---|---|---|
| **Tier 1 — Governance only** | Core gates (Input Routing, Depth, Readability, Output Trace) + Boundary · `depth_range: [1,2]` | Billu; lightweight tooling |
| **Tier 2 — Product company** | T1 + Estimation + Coverage + tier-2 hooks (opt-in via `enabled_hooks`) · `depth_range: [1,5]` | DayFlow · Paisa · new product companies |
| **Tier 3 — Self-host** | Everything · all extensions · vendor-internal readable | Sutra Co. only |

Edit `os/SUTRA-CONFIG.md` to toggle tier + enabled hooks + extensions.

---

## D33 firewall (external clients)

Your repo lives standalone at `~/Claude/<your-company>/`. Asawa holding cannot read your files. You cannot read Asawa's files. Plugin install/update is the only channel across the firewall.

If you need something Asawa has: send feedback via `.enforcement/feedback-upstream.jsonl` (consumed by Sutra vendor on plugin update round-trip).

---

## Day-1 checklist for external clients

1. `cd ~/Claude/<your-company>/`
2. `/plugin install sutra@marketplace`
3. Edit `os/SUTRA-CONFIG.md`: set `tier`, pick hooks/extensions
4. Start a session — plugin auto-activates
5. Work normally. Plugin enforces Boundary + Runtime Gates automatically

---

## When a new Sutra version ships

1. Plugin auto-notifies on SessionStart (PROTO-014)
2. Review changelog at `~/.claude/plugins/sutra/CHANGELOG.md`
3. Stay on current version (pin via `.sutra-freeze` marker) OR `/plugin update sutra`
4. Post-update: `verify-os-deploy.sh` reports alignment

---

## Operationalization

### 1. Measurement mechanism
Install success: `clients_installed_successfully_pct` from marketplace install logs.

### 2. Adoption mechanism
`/plugin install sutra` writes this file path to client's `.claude/plugins/sutra/EXTERNAL-CLIENT-INSTALL.md`. Marketplace listing references this doc.

### 3. Monitoring / escalation
Sutra vendor monitors marketplace install success rate. Warn: <90% success. Breach: repeated failure pattern across ≥3 clients.

### 4. Iteration trigger
New tier introduced; install flow simplification; new auto-notifications.

### 5. DRI
Sutra-OS.

### 6. Decommission criteria
Superseded when marketplace v2 ships (if install UX changes fundamentally).

---

## Stems

external-client-install, tier-selection, sutra-config, D33-firewall-external, phase-5-deliverable
