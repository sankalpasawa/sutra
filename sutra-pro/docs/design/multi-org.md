# Multiple orgs (phase 2)

Founder ask (2026-11-11): "Can create multiple orgs. Hopefully connect those orgs in future."

## Today

The app has one org. One chart (`org_charts`, highest revision wins), one root (`org_nodes_one_root`), one org chat
(`cs_org`), and no org key on any table. Each data folder already has its own lock, database, connector work root and port.

## Proposal: one data folder per org

An org is a data folder. The app keeps a small registry and starts one server per open org.

| Piece | What it does |
|---|---|
| Registry | `~/.sutra-pro/orgs.json`: `[{id, name, data_dir, created}]`. The first entry is the existing data folder, named "Your org". |
| Create | `sutra-pro org new "<name>"` and a New org button: makes `~/.sutra-pro/orgs/<id>/`, adds a registry row. |
| Switch | The Home's org slot lists the registry. Picking one asks the desktop shell to start (or reuse) that org's server and load its Home. |
| Desktop shell | `desktop/src/runtime.js` and `server.js` take a data folder per window; one window per open org, or one window that swaps. |
| Shared library | Templates in `library/` stay shared across orgs (read-only from each org), so a template made in one org is usable in another. |
| Backup and export | `backup`, `restore`, `export` already work per data folder; they gain `--org <id>`. |

## Why not one database for all orgs

It needs an `org_id` on `org_charts`, `org_nodes`, `chart_changes`, `departments`, `chat_sessions`, `tasks` and the
ledgers, one root per org, a per-org org chat id, namespaced department folders, and an org scope on every route. That is a
migration across the whole orchestrator. The folder approach needs none of it and keeps orgs fully apart.

## Connecting orgs later

With one folder per org, a link between orgs is a message: org A's team sends a request to org B's org chat through B's
local server, with an explicit allowlist per pair. Nothing is shared by default.

## Build steps

- [ ] Registry file and `sutra-pro org new|list|rename` commands, with tests.
- [ ] `/api/orgs` on the server: the registry, and which org this server is.
- [ ] Home org slot lists orgs; New org; switching opens that org.
- [ ] Desktop shell starts a server per org folder (one window per org first).
- [ ] Backup, export and doctor take `--org`.
- [ ] Docs: GETTING-STARTED and OPERATIONS describe orgs.
