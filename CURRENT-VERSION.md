# Sutra — Current Version

**status**: active · **updated**: 2026-08-25

## v2.235.4 (2026-08-26, HEAD)

Provider detection: Claude Desktop is recognised as a different product from the
Claude Code CLI (Desktop ships no `claude` binary) and the panel says what to
install; version-manager shim dirs (pnpm, mise, asdf, nodenv, fnm) are probed;
the login-shell PATH harvest gets 25s instead of 8 and explains why it failed;
and a binary path can be set from the panel instead of only through an
environment variable a Finder-launched app cannot receive.

NOTE: this file had drifted — its previous top entry was v2.226.3 while
plugin.json was already at 2.235.3. The intervening releases are in
marketplace/plugin/CHANGELOG.md; the gap below is real, not a lost entry.

## v2.226.3 (2026-08-25)

Attach-mode auto-update: the shell updates itself via its bundled sidecar CLI
(updates_cli wrapping updates.py, flock-serialised) even while a CLI/checkout
server holds 8330; feature-detected renderer lights up at the next DMG.
(2.225.2-2.226.2 in between: see marketplace/plugin/CHANGELOG.md.)

## v2.225.1 (2026-08-25)

Editor lifecycle race fixed (light-mode blocker); saved label; emphasis weights.

## v2.225.0 (2026-08-25)

Native editing: forked SB editor core vendored in-panel; iframes deleted;
sidecar retired from the app path.

## v2.224.6 (2026-08-25)

Settings > Usage opens with the Account card: who is signed in, email, plan,
subscription/billing, organization/role, tier, IDs, data age — local reads,
allow-listed, no tokens. Manifests re-synced after 2.224.5.

## v2.224.5 (2026-08-25)

Shadow interactive: dot home corner, click-to-card, card mounts and sends,
Now empty state starts a chat (changelog-only bump; manifests stayed 2.224.4).

## v2.224.4 (2026-08-25)

Rhythm hygiene: 22px content start, quiet zero-doc departments.

## v2.224.2 (2026-08-25)

Theme comment honesty (verify-floor catch).

## v2.224.1 (2026-08-25)

Closeout: theme v3 edit scale, 680/232 measure, panel token, daemon hygiene.

## v2.224.0 (2026-08-25)

S92 cutover: Workspace default-on fleet-wide; Knowledge/Files folded in.

## v2.223.1 (2026-08-25)

Workspace parity loop closed (reviewer SIGN-OFF); search top-bar swap fixed.

## v2.222.9 (2026-08-25)

Panel-native rendered READ state (iframe only behind Edit) + reviewer minors.

## v2.222.8 (2026-08-25)

Review-loop: search in-flight state + content cache, clip fix, filing join
unified, cursor/renderer one predicate, 14-row cap, stable sidecar port.

## v2.222.7 (2026-08-25)

Tree indents render (button-reset specificity); DOM-verified vs mock spec.

## v2.222.6 (2026-08-25)

Editing default-on (READ_ONLY opt-out + origin guard, dual-consulted); tree
collapses to the active path (founder structure ruling); tighter type scale.

## v2.222.5 (2026-08-25)

Settings > Updates: desktop row now tells the truth in attach mode (shell
attached to a CLI/source-checkout server) — "desktop updates unavailable" +
recovery step, instead of the false "not managed here / source checkout".

## v2.222.4 (2026-08-25)

Workspace/Files visual parity: theme v2 (SB chrome hidden, panel tokens both
themes, serif headings), search-result styling per mock 03, nativeTheme bridge.

## v2.222.3 (2026-08-24)

Workspace: openScreen loads the screen again — the per-screen dispatch line was
lost in a worktree restore, so the click path rendered an empty shell. Restored
+ pinned by a workspace-suite test.

## v2.222.2 (2026-08-24)

Optimus copy in customer voice (P0); technical detail demoted to muted; trust
gates unchanged. (2.222.1 in between: workspace flag propagation — see CHANGELOG.)

## v2.222.0 (2026-08-24)

**Optimus — the daemon, visible (Focus tab).** A window over sutra-daemon's
stores: status+PID, decision queue, routes with department/charter chips,
recent runs, ask box, route builder. Screen requests; the daemon CLI gate
decides (two-step typed approve, PID-echo stop, desktop-token mutations).

## v2.220.4 (2026-08-24)

Releases come from .github/workflows/release-dmg.yml only: make-dmg.sh now
refuses to notarize unless SUTRA_RELEASE_CI=1, which only the workflow sets.
The `fork` remote is removed -- development and pushes go to sankalpasawa/sutra,
where the update channel already pointed. Settings pane groups collapse
individually, keyed per destination, storing only what was explicitly closed.

## v2.220.3 (2026-08-24)

Chat rows in user language: 'not opened yet' (no sizes, no 'transcript'),
'opening…', "can't be opened"; workspace label only when it differentiates.


## v2.220.2 (2026-08-24)

Every connector type gets its own tile: five connectors, five tiles, each with
its own glyph, state, account line and controls. The single "Connected in
Claude" card is gone. The probe remains one CLI run for all of them, and the
Re-check tooltip says so rather than letting per-tile placement imply otherwise.

## v2.220.1 (2026-08-24)

Six vertical panes: the session surface holds up to 6 side-by-side chat
panes (FIFO eviction, no duplicates, horizontal scroll).


## v2.220.0 (2026-08-24)

Slack stops being a connector Sutra owns and becomes one it observes through
Claude, like Gmail and Drive. Sutra runs no Slack OAuth app and holds no Slack
token.

The mediated catalogue is generalised: Slack matches on display name until a
real row teaches it the host -- it has never been connected in Claude here, so
there is no host to look up, and guessing one would render "not listed" forever
and confidently. Any connector Claude reports that Sutra has no catalogue entry
for is now surfaced rather than dropped (the operator has an Atlassian Rovo
connector the old code silently ignored).

Slack is retired IN PLACE, not deleted. Deregistering it was verified by
execution to make every /api/connectors/slack/... route 404 -- including DELETE
-- which does not remove an upgrader's tokens, it removes their only way to
remove them.

## v2.119.5 (2026-08-24)

Subtitle round 3: free-form ritual (CAPS-KEY headings, metric parentheses)
trimmed from the header subtitle; the ask opens it.


## v2.119.3 (2026-08-24)

Chat header round 2: title + subtitle rows (hover for full text), department
beside the live dot ("latest filed"), aligned to the chat column; per-turn
transcript boilerplate and the pane's "transcript" tag removed.


## v2.118.3 (2026-08-24)

Ownership inversion: the desktop update channel now points at
`sankalpasawa/sutra` (the founder's repo, where CI signs and notarizes).
`tchandrakar/sutra` publishes one migration bridge and then retires as a
release channel. Pinned in `test_update_channel.py` (default, override,
and the URL the updater actually requests).


## v2.118.1 (2026-08-24)

Governance chips now render on transcript turns -- which is every real session
read from `~/.claude/projects`. Until now that branch skipped the chip while
the body strip removed the same content: Input Routing, Depth, FLOW, BLUEPRINT
and traces were invisible on real sessions. The chip is gated on an actual
capture, toggles via a real turn uid, and says **terminal** (a fact) rather
than "unresolved" (a failure that never happened). L1+L2+L3 pinned.


## v2.117.2 (2026-08-23)

The chat surface, redesigned and verified in the shipped app: every turn's
governance captured under its chip (never leaked into the reply), subagent
fan-outs visible as rows inside the turn, an openable step log, a minimal
header (what the chat is about in 45 words + close), one ⋯ composer menu
carrying every session control, Routing as a tree. Plus a two-lane publish
standard (state over CDP, then pixels) and a design-QA product.

Two hardcoded defaults replaced with what Claude already knows: the rail footer
avatar comes from the signed-in Claude account instead of a literal "TC", and
the agent's default workdir falls back to the operator's most recent Claude
workspace instead of ~/sutra-ui-workspace. Both are DEFAULTS only -- a stored
workdir still wins -- and the recent path is filtered through workdir_allowed()
before it is offered, because it becomes the agent's cwd.

## v2.117.1 (2026-08-22)

Google connector, as a MEDIATED tile: a connection Sutra observes and cannot act
on. Membership ("Added in Claude") is rendered as state; the CLI's status string
is rendered as a timestamped observation, because the same connector reported
four different statuses within one hour. The connected Google account is NOT
shown -- it is not knowable from any local store or from Claude's API, and the
nearest value to hand is the Claude account email, which would have been a
convincing wrong answer. See ADR-035.

## v2.117.0 (2026-08-22)

Carries the 2.116.x line (Teamsutra rewritten to read like a person wrote it;
Files v1.1 with folder tree + Knowledge bridge) plus three fixes:

- **Streaming text flows instead of arriving in lumps.** The reply is no longer
  re-rendered from scratch each frame -- settled paragraphs keep their DOM
  identity, so a selection made mid-stream survives -- and the per-frame
  character step is capped, so a bursty network no longer paints a lump. On a
  real 4850-char reply: 38 network chunks averaging 127 chars became 619
  display frames averaging 7.8.
- **"Not now" on the update banner dismisses it**, keyed to the staged version.
- **Connector lookups scoped by provider**, closing a cross-provider read /
  validate / disconnect path that could strand a live token in the keychain.

## v2.115.1 (2026-08-21)

"Not now" on the update banner dismisses it. Deferring previously swapped the
countdown for a message with no buttons, leaving a permanent notice on screen
until the app quit. Dismissal is keyed to the staged version so a newer build
still announces itself, and a failed or already-armed install always shows.

## v2.115.0 (2026-08-21)

**Slack connects, disconnects and reconnects from the app.** Verified against a
real workspace: bot and user tokens in separate keychain slots, both rotating,
identity keyed team_id:user_id, no token bytes anywhere in the database.

The two defects that stood between a working connector and a usable one were a
reconnect that left the account ACTIVE and invisible simultaneously, and a
validate path that still called GitHub's client method on a Slack client. Both
were found by using the installed app; neither was reachable from the test
suite. Three new tests check the class of each rather than the instance.

## v2.113.3 (2026-08-21)

**Slack could never be connected after an app restart.** An idempotent
begin_connect kept returning an open transaction whose in-process loopback
listener had died with the previous process, so every Connect click resurrected
the same unusable flow. Strategies now declare whether they can still service a
transaction; one they cannot is retired and replaced.

Found by running the connect through the installed app rather than the test
suite -- the suite never restarts a process.

## v2.113.2 (2026-08-21)

Tiles share a height again, with their action buttons pinned to the bottom edge
so a row lines up without a short tile showing dead space. Connector failures
render as a sentence plus a hint keyed to the provider's error code, instead of
printing the structured error body as raw JSON.

## v2.113.1 (2026-08-21)

**Connector tile layout fixed, including a regression it had caused on the
Updates screen.** A tile clipped its own Manage button at two-column width,
tiles stretched to the tallest instead of sizing to content, the device-code
card's button label was an entire URL and overflowed a narrow pane, and a
global `a.btn` margin added for this screen had misaligned anchor-buttons
against real buttons panel-wide.

Two new tests check the blast radius rather than the four symptoms: the
connectors CSS may not add a global margin to `a.btn`, and every selector it
adds must be scoped to a connector container.

## v2.113.0 (2026-08-21)

**Slack is the second provider, and Connectors is now a tile view.** One tile
per provider whether connected or not, each stating its auth mode, whether it
can connect on this machine, and its caveat. Slack's tile says plainly that its
flow is weaker than GitHub's: no device flow, no PKCE, a loopback port.

Slack issues two tokens from one authorization -- a bot token that posts (so
agent actions are attributable to Sutra) and a user token that reads and
searches. They live in separate credential slots and disconnect erases both.

Adding a provider is now a registry row plus a package; the service, the API
and the screen no longer know which provider they are serving.

## v2.112.5 (2026-08-21)

**Connectors screen layout fixed.** An `<a class="btn">` was `display: inline`,
so its padding overlapped the surrounding text, and the activity table was
clipped at 407px with `overflow-x: visible`, silently losing its last column.
Anchors with `.btn` are `inline-block`; tables scroll in their own container.

Both were found by driving the real panel in a browser and measuring, not by
reading the source -- which is also how the dead buttons in 2.112.4 were
confirmed fixed.

## v2.112.4 (2026-08-21)

**The Connectors buttons work.** They were inert in 2.112.0-2.112.3: the click
handlers sat inside the rail's listener, which never sees clicks in the screen
body. The screen rendered fine, which is why the defect survived a screenshot
and 152 panel tests -- those extract panel.html's inline script, and this
screen is an external file.

Handlers moved to a document-level delegate scoped to `#scBody`, plus a new
10-test suite whose main assertion is general rather than specific: every
control the markup emits must have a handler, and every handler must have a
control.

## v2.112.3 (2026-08-21)

**Discovery stops re-asking GitHub on every page view.** With no installations,
`not installations` was true on each request, so the 15-minute cache was
bypassed and every call cost ~0.85s of live GitHub. A freshness marker now
records that GitHub answered, including when the answer was none.

Ships with the 2.112.2 thread fix: the Connectors screen is correct under
concurrency (60 requests, 12-way, all 200) and no longer chatty.

## v2.112.2 (2026-08-21)

**The Connectors 500 is fixed at the root.** A single SQLite connection was
shared across FastAPI's threadpool, and `sqlite3` binds a connection to its
creating thread. First request 200, next request on another worker 500. It
looked transient because a restart reset which thread held the handle, and it
escaped 164 tests and the CLI because both are single-threaded.

`Database` now keeps one connection per thread, with `busy_timeout` for
concurrent writers and a single shared handle for in-memory databases (a memory
database lives inside its connection). Four regression tests cover it,
including the end-to-end shape: construct the service on one thread, call it
from another.

Shipped together with the 2.112.1 diagnosability fix, which is what would have
named this failure in one step instead of several.

## v2.112.1 (2026-08-21)

**Panel connector errors became diagnosable.** A 500 on `/api/connectors` had
no discoverable cause: the endpoints caught only `ConnectorError`, and
Electron buffers backend stderr in memory unless the process exits, so the
traceback existed nowhere reachable. Unexpected exceptions now log to
`~/.sutra/panel-errors.log` and come back as a structured error the screen can
render. Separately, the service cached a SQLite connection for the process
lifetime with no way to recover a broken one -- it now health-checks and
rebuilds, and never caches a failed construction.

The original fault was not reproduced. Restarting cleared it. What is fixed is
the pair of defects that made it invisible and unrecoverable.

## v2.112.0 (2026-08-20)

**The connectors screen is live, and permissions are resolved from disk.** P3
lands the permission layer over real settings files, and the panel gets its
Connectors surface back -- rebuilt rather than restored: it renders the new
connector model, not the Composio/1MCP one that was removed.

What an operator can now do in the app: connect a GitHub account through the
device flow (the code is shown large and monospaced because it is transcribed
by hand into another window), see which repositories the installation actually
covers and what each one permits, see which organizations have Sutra installed
and which merely have you as a member, read the permission rules in the order
the engine evaluates them, and read the hash-chained audit trail. The panel
never sees a credential -- it deals in connector ids and connector state only.

**Honest scope:** the agent tool gateway is not built. Nothing invokes these
capabilities yet; the screen shows what WOULD be permitted. That is P4.

## v2.111.0 (2026-08-20)

**Connector platform rewrite: P1 + P2 + the permission engine.** The layer
deleted in 96edce8 is rebuilt as a provider-agnostic module under
`marketplace/plugin/connectors/`. GitHub is the first and only provider.
Authorization is the GitHub App device flow, which needs no client secret and
has no redirect URI at all -- deleting the entire callback attack surface. The
credential lives in the macOS Keychain; the database holds a reference and
expiry timestamps and no token bytes, verified by a raw scan of the db file.
The permission model is a port of Claude Code's own: `Tool(specifier)` rules,
deny -> ask -> allow with specificity never reordering, six modes, managed
settings that no other scope can override. 138 tests, zero new dependencies.

**Honest scope:** this is a library plus a CLI. `sutra-ui` is untouched, so the
installed desktop app has no connectors screen and no connect button. Wiring is
P3+.

## v2.110.1 (2026-08-18)

**Synced with upstream main; both connector models kept side by side.** This merge brings sankalpasawa/main (25 commits: Composio tool router, the 1MCP local aggregator, the chat governance surface, Balance graduation) together with this fork's line (agentic tool output, the transcript-pane fix, the update-check fix, asset cache-busting, Test pane removal). The connectors collision was resolved by keeping **both**: upstream's Hosted (Composio) and Local (1MCP) halves are the live screen, and this fork's **Present in Claude** mirror — the one half with no upstream equivalent, and whose `/api/connectors/configured` endpoint survives because it reads Claude rather than Sutra's own store — is kept beneath them. `connectors_store.py` and its 66 tests are retained in the tree; the preset gallery and registry search they backed are not re-wired, because upstream's local half now owns those routes. Version set to 2.110.1 as the base for the next connectors rewrite. Upstream's own notes below are labelled v3.0.0/v3.1.0; their `plugin.json` read 2.99.1, so the numbering here is deliberately ahead of both.

## v2.103.0 (2026-08-18)

**Checking for updates downloads them.** "Check for updates" found a new version and staged nothing — background staging ran only on the shell's timer (90s after launch, then every six hours), leaving the blocking "Download & install" (which quits the app) as the only manual path. The panel can't stage itself: that route is token-authenticated and the token never reaches the renderer, so a third preload verb asks the shell, like apply/defer. One download at a time, shared with the scheduled path; the screen stays usable and reports what actually landed. **Test pane** — an empty scaffold wired at three sites — is out of the Organization nav. 6 new tests; 92 panel tests green.

## v2.102.0 (2026-08-18)

**"Transcript not read yet" no longer sticks.** An open pane on an idle session could sit on that message forever: `ensureTranscript()` only acts on `unread` and was called only from the sites that open a pane (the ⋮ → "open in repo" action skipped it), while the background re-read fires only on a write to the file — which an idle transcript never gets. Reproduced live (8s, no recovery), then fixed structurally: `render()` schedules the read for every open pane, idempotent like `loadRepo` beside it, so every path into `openPanes` is covered. Also, `sessionBody()` no longer claims "not read yet" for a session that WAS read (`ok` with zero turns, which the busy guard produces without parsing). 5 new tests; 86 panel tests green.

## v2.101.0 (2026-08-15)

**Connectors mirror Claude.** A "Present in Claude" section reads the operator's own connectors live from `claude mcp list` and shows each with a status badge; configuring is delegated to Claude's own `claude mcp add` / `claude mcp login` flow rather than rebuilt, so Sutra never handles an OAuth token. Read-only endpoint behind a subprocess timeout + 30s TTL cache. 66 connector tests green.

## v2.100.0 (2026-08-12)

**Agentic output is captured and shown.** The transcript reader now records, for every tool call an agent (or subagent) makes, the tool name, the actual input (command / file path / pattern / query, capped) and the returned result (capped 8 KB, error-styled when the tool failed) — not just a bare tool name. The chat replay and the subagent viewer share one renderer (`toolCallsHtml`): each call shows a name pill, its command, and a collapsible **output** toggle that reuses the live tool-row open-state. Verified: parsing a real 9,979-line session captured 1,243 tool calls, 1,236 with output (name + input + result); 81 panel tests, JS syntax clean on all four touched modules.
## v3.1.0 (2026-08-13, upstream)

**A second connector: local MCP servers, assorted, behind one aggregator.** Composio is a hosted API for cloud SaaS and structurally cannot reach `filesystem`, `git`, `playwright` or `sqlite` — so the local half is back, and aggregated rather than multiplied. `local_store.py` fronts every enabled local server with **1MCP** (`@1mcp/agent`, Apache-2.0, `serve --transport=stdio`): one process the CLI spawns per turn, no daemon, no port. MetaMCP was the other candidate and lost on shape not licence (Docker + Postgres + its own web UI); `1mcp proxy` lost because it needs a long-lived `serve` to proxy to. **Assorting is real config, not a label:** every server carries a 1MCP `tag` — Composio's category for the same slug where one exists (so `github` files under `developer-tools` in *both* connectors), else a keyword heuristic that says it guessed and is editable per server. The screen groups by tag; `--filter` narrows on the same strings. Servers come from the **open MCP Registry**, so neither connector's catalog is hand-maintained. **Auto-update grows from three mechanisms to five:** local servers resolve at spawn time via `npx -y`/`uvx` (immediate), and the aggregator's pinned version tracks npm's `latest` dist-tag on a 24h TTL — pinned because an unpinned `npx -y` could swap the process fronting every local tool between two turns of one session. Optional switch routes Composio *through* the aggregator for one connector covering everything; off by default, and when on the direct entry is omitted rather than duplicated. A session sees at most three MCP servers (`sutra`, `composio`, `local`) however much is enabled. **CHARTER v0.4.0** admits the local aggregator as a third integration pattern and adds RULE 6 (invoked never imported, pinned, no privileged config) — **PROTO-019 codex review bypassed by explicit founder direction and marked as such in the charter**. Verified: 63 new backend tests (incl. provable negatives on the pin and the derived config), 329 Python + 112 JS all green; live-checked against npm, the MCP Registry and a real derived `mcp.json`.

## v3.0.0 (2026-08-13)

**Connectors are Composio.** The hand-maintained MCP model is gone — `connectors_store.py`, its ~50-preset gallery, the open-MCP-registry search, and the `~/.claude.json` import are deleted and replaced by Composio's *current* open-source connector: a tool router session (`POST /api/v3/tool_router/session`, the SDK's own `composio.create(user_id, mcp=True)` path — **not** the deprecated `composio.mcp.*` server API). One HTTP MCP endpoint now carries however many of Composio's **1181 toolkits** the operator enables, authenticated by an `x-api-key` header; per-toolkit OAuth is handled in-browser by the session's connection manager, so no login flow ships here. `workbench` is explicitly disabled per `connectors/CHARTER.md` RULE 2. **Auto-update, three mechanisms, stated separately:** new tools inside a toolkit need no client change (the endpoint is remote); the toolkit catalog tracks `ComposioHQ/composio@next:docs/public/data/toolkits-list.json` by ETag-conditional GET, TTL-gated on screen open *and* on the Electron shell's existing update tick; the session re-provisions when the (user id, toolkits) fingerprint changes. A vendored snapshot makes first run work offline. Verified: 56 new backend tests (incl. provable negatives against the deprecated API and against re-enabling the workbench), 175 app tests, 81 panel tests, 36 others — all green. **Breaking:** local stdio MCP servers (filesystem, git, playwright, sqlite) are no longer configurable from this panel.

## v2.99.0 (2026-08-12)

**Connectors gallery.** The Connectors screen's default view expands from 6 presets to a browsable gallery of ~50 recognizable MCP connectors, grouped into 11 categories (Development, Data & Databases, Productivity, Communication, Search & Web, Browser & Automation, Payments & Business, Monitoring & Cloud, Design, AI & Models, Utility) — every config verified against the live MCP registry or a documented remote endpoint (no invented package names). The full open registry (~400 servers) remains one search away; remote connectors carry auth headers. Verified live: 50 connectors / 11 categories render grouped; 56 backend + 81 panel tests.

## v2.98.0 (2026-08-12)

**Connectors = the open MCP Registry.** The catalog is live: an empty search shows curated presets, typing searches the official open MCP Registry (~400 servers, `registry.modelcontextprotocol.io`) and a result prefills the add form. Closed the Claude-parity gaps: auth **headers** for remote (http/sse) connectors — merged into the session's `--mcp-config` — and **Import from Claude** (adds the MCP servers already in `~/.claude.json`). Verified live: registry search returns real servers (github → 12), headers appear only for remote transports, curated presets on empty search; 53 backend + 81 panel tests. *(Next: an in-panel permission popup so a spawned session can ask to run a tool instead of stalling in text.)*

## v2.97.0 (2026-08-12)

**Two live-sync flicker fixes.** (1) "Transcript not read yet" no longer flashes on an open pane: `adoptRealSessions` preserves the pane you're reading (turns + loadState) across the frequent list refreshes agent activity triggers, instead of rebuilding it as "unread". (2) The heavy flicker while agents work is gone: `applySessionChange` keeps the transcript on screen during a background refresh (no "reading transcript…" flip) and throttles re-reads + agent-fold reloads to ~1/s. Verified at the state level: an open loaded pane survives a refresh; a background re-read never hides content; a 2nd event within a second starts no re-read. Connectors re-confirmed (33 backend tests + the mcp-config merge).

## v2.96.0 (2026-08-12)

**Connectors + update-banner fix.** New Connectors screen (Runtime) to add MCP connectors — like Claude CLI's — by hand (stdio command/args/env, or a remote http/sse url) or one-click from a catalog (github, filesystem, slack, puppeteer, brave-search, linear); enabled connectors are merged into the `--mcp-config` passed to every spawned session (alongside `sutra`, keeping `--strict-mcp-config`), running under the session's permission mode. Store at `~/.sutra-ui/connectors.json`, fail-soft. Also fixes the "Restarting in nulls" update banner (a dedicated restarting state + a null-safe countdown). Verified live: the screen adds/toggles/removes connectors and an enabled connector reaches the session's MCP config; 33 backend + 81 panel tests.

## v2.95.0 (2026-08-11)

**First release published entirely through GitHub Actions.** With the signing + notarization secrets wired, pushing a `v*-desktop` tag builds both arches on native runners, signs with the Developer ID, notarizes via the App Store Connect API key, and uploads `Sutra-<arch>.dmg` — no local build. Also fixes `test_charter_filter.js`, which had failed every CI run since the panel split.

## v2.94.0 (2026-08-11)

**Native folder picker, finished.** The Browse… button opens Finder at your current folder (a tilde-expanded `defaultPath` is passed through the IPC), and a pick in the composer's working-directory control applies immediately — the old code wrote it to the input with no backing state, so a live re-render could wipe it before SET. Settings keeps the fill-a-draft-then-Save flow; the routine folder field persists to its form; the handler returns null on any dialog error. Verified end-to-end headlessly: the button renders only with the Electron bridge present, the current path is passed as the dialog default, and the pick is applied to the session.

## v2.93.0 (2026-08-11)

**Subagent viewer = Claude's agent view.** The subagent list stops being a wall of raw prompt text: each agent is a clean card (real title + agent-type badge + "N steps · tools · relative time"), and clicking one opens a readable step-by-step transcript — the task it was handed (collapsed), each assistant step with its tool calls, and the final message set apart as the result. Backend: `list_agents` joins to the parent's `Task` tool_use for the description/subagent_type and counts assistant steps (real work) instead of the always-1 user-turn count. Verified live on this session's 43 agents; kept the Sutra theme.

## v2.92.0 (2026-08-11)

**Activity: header trigger + right drawer.** The Activity panel moves from a bottom-right floating widget to a compact trigger in the chat header's top-right (a live count badge that pulses on activity) that opens a right-docked, non-modal drawer — "Running turns" + "Agents" with stopwatches — matching Claude's Background-tasks placement. Close via ×, Escape, or re-click. Verified live in the browser: the trigger renders in the header, the drawer opens/closes, the badge syncs to the running count, and this session's own turn appears with a ticking stopwatch. Plus formal evals for `/api/activity`, `head_meta`, and the picker gate.

## v2.91.0 (2026-08-10)

**Live Activity panel + native folder picker.** A floating, collapsible Activity panel (bottom-right) surfaces all running work live — in-flight chat turns and running subagents, with a count badge and per-item stopwatch — Sutra's equivalent of Claude's Background-tasks view, backed by a new read-only `/api/activity` that reuses the existing liveness logic. Plus a native macOS Finder "Browse…" button on every working-directory control (new `sutra:pick-directory` IPC), with the text field kept as an editable fallback. Built by two parallel agents on disjoint files; verified live (endpoint caught this session's own turn; 76/76 panel tests; zero console errors).

## v2.90.0 (2026-08-10)

**Notarized desktop build.** Everything in v2.81.0 — live sync, resume correctness, the running-turn strip, the subagent viewer, the per-session ⋮ menu, the panel split, and the working-directory / usage / repository controls — now Developer ID–signed and **Apple-notarized** for both arm64 and x86_64. No source change since v2.81.0; the version is realigned for a clean notarized release that supersedes the un-notarized 2.81.0-desktop DMGs.

## v2.81.0 (2026-08-09)

**The desktop panel becomes one entity with Claude.** Live sync (a chat in Claude appears and updates in Sutra as written) plus resume-in-the-right-folder so a reply from Sutra continues the same Claude conversation instead of forking; titles you set in Claude; a running-turn progress strip with a stopwatch; a subagent transcript viewer (the "N agents" badge now opens each agent's turns) and correct async-agent completion timing; a per-session ⋮ menu (Open in / Pin / Unread / Rename / Fork / Group / Archive / Delete, with rename appending Claude's own custom-title record and archive/delete moving files recoverably); a real keyboard layer; and working-directory / usage / repository controls in the composer. Architecture: panel.html split into panel.css + 9 JS modules, behaviour-preserving, so UI iteration touches one small file. Also fixes the catalog-vs-source version drift (both now 2.81.0). Verified in the running app end to end.

## v2.79.0 (2026-08-07)

**Balance screen beauty pass.** Serif greeting with the day's one-liner, insight cards as accented stat tiles, day strip in a card with hour marks, polished composer — all from existing panel tokens; visual-only.

**This file had gone stale at v2.43.0.** Thirty-six releases shipped to the fleet while `CURRENT-VERSION.md` still named v2.43.0 as HEAD — the catalog (`.claude-plugin/marketplace.json`) and the plugin manifest (`marketplace/plugin/.claude-plugin/plugin.json`) both read 2.79.0, and the plugin CHANGELOG carried every entry. Anyone reading this file to find the current version got an answer 143 commits out of date. The gap is closed here; the arcs it covered are summarized below and detailed in `marketplace/plugin/CHANGELOG.md`.

**What shipped between v2.43.0 and v2.79.0**

| Range | Arc |
|-------|-----|
| v2.44.0 – v2.47.0 | **Placement engine.** Per-turn block + warn-first gate, then the engine itself (addresses are computed, not typed), the last mile (the block is engine output), and the codex F7.1 dual-lane review folds. |
| v2.47.1 – v2.63.0 | **Domains layer.** `core:departments` MECE view, fleet page, grounding rungs, drill-down zoom pages, ledger close with on-touch minting, the charter layer (projects as charters), consumer charter pages, `charters_seed.py` / `domains_pipeline.py`, and on-the-fly hydration with fast-lane data pushes. |
| v2.53.0 – v2.53.1 | **Flow orchestrator mode v1.** D62 / ADR-029 flag-gated dispatch — contracts, matcher, factors, ledger, fixtures. Flag moved off → experimental. |
| v2.58.0 | **Markers Scheme A concurrency core.** Self-only adoption, ownership-safe reset, session-first gates. |
| v2.64.1 – v2.65.0 | **Dispatch runtime to the fleet**, plus three governance hooks that had been misfiring. |
| v2.66.0 | **Daily auto-update** at the first session of the day. |
| v2.68.0 | **Telemetry on by default** (D64) — anonymous, once daily. |
| v2.69.0 – v2.72.0 | **Desktop panel.** Permission mode moved beside the composer with effective-mode clamping, streaming rewritten to patch a single node (0 full re-renders over 40 token frames), Routines on launchd with write-capable modes unreachable by construction, staged mandatory auto-update behind a shell-minted token, dual update checks in Settings, and `verify-runner` fleet-wide as the base of the Eval Engine (ADR-031). |
| v2.73.0 – v2.79.0 | **Balance module.** Design preview → chat live on a preloaded session → real observations → v3 founder redline → human register cards (evidence-gated, tempo not emotion) → this beauty pass. |
| v2.78.0 – v2.78.2 | **Usage-guard (opt-in, dormant by default).** Warns at 70% rate-limit utilization, HARD-blocks at 80% until `sutra-usage continue`; both the session (5h) and 7-day windows shown on every surface. |

## v2.43.0 (2026-07-28)

**Removed: the H-Sutra header Stop enforcement layer.** `hooks/h-sutra-enforce.sh` is deleted and its Stop registration is gone. No profile gets a block, a warning, or a forced redo for a missing or malformed header any more. Founder direction, 2026-07-28 — the layer had produced repeated forced redos for a formatting slip that changes nothing about the work.

**What survives.** The header is still a convention: `/core:start` documents the format, `per-turn-discipline-prompt.sh` still asks for it on every turn, the `core:human-sutra` skill is untouched, and the 9-cell classification log rail (`holding/state/interaction/log.jsonl` / `.sutra/h-sutra.jsonl`) keeps recording — that rail was always written by `per-turn-discipline-prompt.sh`, never by the enforcer.

**What dies with it.** The `.enforcement/h-sutra-audit.jsonl` enforcement telemetry, and the `SUTRA_HSUTRA_ENFORCE_DISABLED=1` / `~/.h-sutra-enforce-disabled` kill-switches (nothing left to disable — the sentinel file is now inert and can be deleted).

**Stop floors that remain HARD.** `per-turn-hard-gate.sh` (Input Routing, Depth, and BLUEPRINT on mutating turns) and `flow-stop-check.sh` (Flow, `profile=company` only). `sutra-defaults.json` now records `per_turn_blocks.human_sutra_header.enforcement = convention_only`, and the `/core:start` CLAUDE.md template no longer claims the header is hard-enforced. Re-run `/core:start` after updating to regenerate the block.

Unit suites unchanged at 21/23 — `test-codex-directive-detect.sh` and `test-codex-directive-gate.sh` stay red, pre-existing and off this path.

## v2.42.0 (2026-07-28)

**Two Stop layers stop punishing correct behavior.**

1. **`blueprint-check.sh` v3 — text-first (#81).** The hook had only ever read `.claude/blueprint-registered`, while every surface told the model to *emit the block*. A model could emit a complete, correct BLUEPRINT in the response the user reads and still be HARD-blocked, with no re-emission able to help. Three incidents came from that one divergence (#68 2026-05-23; the Testlify field incident 2026-07-08, where the model escaped via a Bash + `BLUEPRINT_ACK` bypass the error text taught; a repeat 2026-07-27). v3 validates the BLUEPRINT **in the turn's response text** — the same source `per-turn-hard-gate.sh` already uses for Input Routing + Depth. The marker becomes a per-turn cache the hook writes for itself; nothing asks the model for it. PreToolUse enforcement narrows to **foundational paths**, whose globs move to `per_turn_blocks.blueprint.foundational_paths` in `sutra-defaults.json` (overridable per repo via `blueprint_foundational_paths[]` in `.claude/sutra-project.json`) — they had been hardcoded to the Asawa layout, so on every other install the "important documents" set was empty. Ordinary files are floored at Stop by a new BLUEPRINT arm in `per-turn-hard-gate.sh`, armed only when the turn actually mutated a governed file. Degrades to the legacy marker check when no transcript or python3 is available. Tests: `test-blueprint-text-first.sh` 25/25, `test-per-turn-hard-gate-blueprint.sh` 13/13, existing blueprint suites 6/6 + 6/6.

2. **`h-sutra-enforce.sh` v8/v9 + `flow-stop-check.sh` honor `.profile` (#72).** `DIRECTION·VERB` is now case-insensitive (Postel's law — emit UPPERCASE, accept any case), killing the case-error block class. Only `profile=company` gets a forced redo; `individual` / `project` / unknown get warn + log. **Fail-open by design:** no `sutra-project.json` or no `jq` → warn, never a hard block. The `Enforce: warn-only` banner is finally true for the loud layers too. Note for `project`-profile repos (including asawa-holding): H-Sutra and Flow drop from forced redo to warning — set `"profile": "company"` in `.claude/sutra-project.json` to keep the hard redo.

3. **Release hygiene.** The `marketplace.json` catalog had drifted to 2.39.20 while source read 2.41.2 — two releases of narrative the catalog never carried. Both now read 2.42.0 and `test-validate-manifest-json.sh` is green again.

Known-red suites on this release, pre-existing and untouched here: `test-codex-directive-detect.sh` (11/20) and `test-codex-directive-gate.sh` (3/12). Both fail identically on the parent commit; neither is on the blueprint or Stop-layer path.

## v2.40.0 (2026-07-20)

**D63 — per-turn stack HARD fleet-wide.** New Stop floor `per-turn-hard-gate.sh` makes Input Routing + Depth hard on no-tool turns (like Flow / H-Sutra already are); `codex-consult-gate.sh` hard at Depth ≥ 3 (degrades without codex); `/core:start` contract expanded 4 → 9 blocks; both new gates activate only post-onboarding, so enforcement never precedes the contract. Codex CHANGES-REQUIRED folded (5 fixes). New hooks: `per-turn-hard-gate.sh`, `codex-consult-gate.sh`, `codex-consult-marker.sh`.

## v2.39.20 (2026-07-08)

**Blueprint marker visibility + out-of-repo guard (Testlify field incident 2026-07-08).** A fleet client emitted a correct prose BLUEPRINT (Output + Verified-by included) and `blueprint-check.sh` still HARD-blocked Write twice — the hook reads ONLY `.claude/blueprint-registered`, and no fleet-visible surface (per-turn reminder, hook stderr) said to write it; the marker contract lived solely in the non-auto-invoked `core:blueprint` skill. The model's only advertised exit (`BLUEPRINT_ACK=1`, unusable on Write tool calls) taught a Bash+ACK bypass of the gate. Fix 1: `per-turn-discipline-prompt.sh` now states the marker contract (write the marker via the Write tool with `HAS_OUTPUT`/`HAS_VERIFY`/`HAS_PER_STEP_VERIFY`) before the first Edit/Write of each turn. Fix 2: `blueprint-check.sh` out-of-repo guard — absolute paths outside `$CLAUDE_PROJECT_DIR` (`~/.claude/**` memory files, sibling repos) are out of scope; they could never match any whitelist and were blocked by accident. Inside-repo enforcement unchanged. Tests: `test-blueprint-marker-visibility.sh` 6/6. Fix + bump ship together (self-shipping PR #80). (#78 depth-gate + error-text split ships separately; A4 text-validation via #73.)


## v2.39.19 (2026-07-06)

**#63 — /core:start documents the H-Sutra header contract it enforces.** `h-sutra-enforce.sh` HARD-blocks every response whose first line isn't a valid header, but `/core:start` wrote a CLAUDE.md governance block with zero references to that header (`grep "H-Sutra|DIRECTION|VERB"` → 0 hits) — an invisible rule that caused repeated "redo with the header" blocks. `scripts/start.sh` now writes an **"H-Sutra Header"** section (exact format, DIRECTION/VERB vocabulary, example, STAGE-1-FAIL variant) as the first documented behavior; the hook's diagnostic points to it. Verified: generated-block grep → 5 hits. The fix + this version bump ship together in this PR (self-shipping). After update, clients re-run `/core:start` to regenerate the block. (A4 block-text validation ships separately via #73.)


## v2.39.18 (2026-06-30)

**loop-budget-guard: per-turn reset + agent-orchestration exemption (fixes the session-wide hard-stop).** The guard's tool-call counter was cumulative-per-session and never reset, so a long working session crossed the 250 ceiling on ordinary Bash/Read/Write calls and hard-stopped itself ("tool-budget guard hard-stopped further file reads this session") — and the deadlock blocked the very Bash needed to update out of it. New `loopguard-turn-reset.sh` (UserPromptSubmit) truncates the counter at the start of each real user turn → budget is now **per-turn** (a 250-call runaway in one turn still blocks; synthetic turns skipped, so within-turn loop detection is intact). `Agent`/`Task`/`Workflow` dispatches are exempt from counting (a fan-out is not a loop; opt back in with `LOOP_GUARD_COUNT_AGENTS=1`). Guard suite 12/12. Also ships **A4 block-text validation** (`perturn-text-validate.sh` — validates the emitted Input Routing / Depth / Output Trace; `blueprint-text-validate.sh` detection hardening; profile-aware). D13 cascade: risk LOW, backward-compatible.


## v2.39.17 (2026-06-25)

**Loop/tool-budget guard promoted to L0 (A6).** Always-on PreToolUse hook blocks runaway agents + infinite loops before execution; fail-open. Per-session budget (250) + frequency-in-window repeat detection; kill-switches + LOOP_GUARD_ACK. 8/8 tests. D13 cascade: risk LOW.


## v2.39.13 (2026-06-14)

**Flow fires every turn like the H-Sutra header — emission_mode literal-text fix.** Root cause: Flow was the only per-turn block with `emission_mode: skill_invocation` (a Skill tool call), which the model rationalized skipping on light turns while literal-text blocks (header/routing/depth) fired reliably. Fix: fast-path now emits a literal one-line `FLOW: <type> · fast-path · <n> atom · classify->answer` block as TEXT every turn; the `core:flow` Skill is invoked only on substantive/multi-step/mutation turns. Two files: `sutra-defaults.json` `.per_turn_blocks.flow` + `hooks/per-turn-discipline-prompt.sh` FLOW ACTIVATION block (duplicate Backstop line collapsed).

## v2.39.12 (2026-06-14)

**flow-gate HARD fleet-wide.** Edit/Write to non-whitelisted path or Task/Agent dispatch without core:flow markers → exit 2.

## v2.39.11 (2026-06-14)

**Flow on EVERY input/type + 1-step fast-path for trivial; gate widened to Task/Agent.** sutra-defaults all-types + cost_model, per-turn reminder, flow-gate Task branch.

## v2.39.10 (2026-06-14)

**Flow auto-activation — core:flow fires per turn, TYPE-gated** (work-bearing turns run the spine; trivial skip). sutra-defaults.json per_turn_blocks.flow + per-turn-discipline-prompt.sh reminder + flow-gate backstop.

## v2.39.9 (2026-06-14)

**The Flow — work-resolution spine shipped as skills (core:flow + workflow-type-resolve + lens + cynefin) + SOFT flow-gate hook.** Canon ADR-026 + ADR-027. See plugin CHANGELOG.

## v2.39.6 (2026-05-31)

**Prompt-capture hook (UserPromptSubmit) — fleet L0.** Every founder prompt is appended losslessly to the project's `holding/state/prompts/<YYYY-MM>.jsonl` (ts · session_id · prompt). Non-blocking; kill via `PROMPT_CAPTURE_DISABLED=1` or `~/.prompt-capture-disabled`. Registered in `hooks/hooks.json` UserPromptSubmit. Promoted from Asawa-local L1 same day.

## v2.39.5 (2026-05-28)

**`h-sutra-enforce` hook — actionable mis-cased-header error.** Malformed (Title-case/lowercase DIRECTION·VERB) headers now report "DIRECTION·VERB must be UPPERCASE" with a canonical example, instead of the misleading "header missing". Valid-header pass/block logic unchanged (regression-tested).

## v2.39.4 (2026-05-13)

**`prd-discipline` skill v2** — REFACTOR pass plugs 5 baseline-test rationalizations.

- Skill body at `sutra/marketplace/plugin/skills/prd-discipline/SKILL.md`.
- v2 additions: §1 namespace-collision check + naming-with-alternatives · §3 scale-undershoot surface · §4 canon-typed-entity rule · §5 TODO-is-not-an-alibi.
- Baseline test at `.enforcement/skill-tests/2026-05-13-prd-discipline-baseline.md`.
- Run `/reload-plugins` to activate.

## v2.39.3 (2026-05-13)

**Add `prd-discipline` skill** — product-document writing discipline.

- New skill at `sutra/marketplace/plugin/skills/prd-discipline/SKILL.md`.
- 5 invariants: STRUCTURED · VISUAL FIRST · RESTRUCTURE-ON-BULK · CONNECTED · GAP-SURFACING.
- Composes with ADR-020 Layer-B Product Authoring Template.
- Run `/reload-plugins` to activate in-session.

## v2.39.2 (2026-05-13)

**Remove 15-min hard cap on `codex-sutra` + `deepseek` skills** (founder D2026-05-13).

- 900-s wrapper kill removed from both skills; replaced with SIGINT trap (founder Ctrl-C → SIGTERM/SIGKILL on the whole process group).
- Heartbeat warnings now fire every 10 min during long-running calls (was one-shot at 10 min). Stall warn at 5 min no-progress unchanged.
- `deepseek`: `curl --max-time 900` flag removed — DeepSeek API server-side timeout is the only network bound.
- `sutra-defaults.json`: `deepseek.limits.wall_seconds_hard_cap` is now `null`.
- Fail-closed: `Hard-cap timeout / reason=timeout / exit 124` → `Founder interrupt (Ctrl-C) / reason=interrupted / exit 130`.
- Native canon: `phase-D-codex-review.md` + `HS-7-codex-queue-stale.md` updated with amendment line. HS-7 itself unchanged (watches review-backlog health, not per-call duration).

Rationale: long-reasoning runs were being killed before completion. Founder Ctrl-C is the only interrupt path now; stall + heartbeat keep silent hangs observable.

For prior release history, see `marketplace/plugin/CHANGELOG.md`.

---

provenance: maintained by Sutra release process; newest release first, HEAD marks the shipped version.
