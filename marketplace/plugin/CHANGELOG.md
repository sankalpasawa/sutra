# Changelog

**status**: active · **updated**: 2026-08-20

## 2.110.2

- **The thinking log answers every click.** Opened with zero tool runs it
  says "nothing has run yet in this turn" — an open log never renders as
  nothing, which read as a dead button.
- **The lone streaming caret is gone.** The caret now waits for the first
  visible text in BOTH render paths (settled and per-token patch), which
  share one body builder.
- **Governance text no longer leaks into replies.** Unfenced INPUT:/TYPE:/
  ROUTE: runs are stripped like their fenced forms; a lone key-looking line
  inside prose survives.
- **Design-system fixes from the new design-qa sweep**: roster buttons paint
  token ink (not UA black), the governance chip has a visible focus ring,
  and the activity pulses honor prefers-reduced-motion.
- **New verification lanes in-repo**: `qa-shell/` (state + pixel checks vs
  the RUNNING app) and `qa/` (design-qa product sweep), with the four-level
  test-authoring standard in `PUBLISH-CHECK.md`.

## %s (%s)

**Connector platform rewrite — phases P1 and P2, plus the permission engine.**
Replaces the layer removed in 96edce8. Nothing here is reachable from the
desktop app yet: the module ships as a library and a CLI, and the sutra-ui
wiring is later work. The version bump records that the code landed, not that
a user-facing feature did.

- **ADR-034 — connector token ownership.** The Connector Service is the only
  confidential client; the desktop renderer never holds a GitHub credential.
  Grounded in four verified GitHub facts, three of which contradict widely
  repeated older guidance: PKCE is now supported but does NOT relax the
  `client_secret` requirement on the web-flow code exchange, so a desktop
  binary cannot redeem a code; the device flow needs no secret; and device-flow
  refresh needs no secret either, which is what makes a secret-less local
  client viable with a full 8h/6-month lifecycle rather than a degraded one.
- **GitHub App, not OAuth App.** Per-repository, per-resource permissions are
  the only honest basis for "read-only on repo X". `administration` is not
  requested, so repository deletion is unreachable rather than merely denied.
- **Permission engine** — a faithful port of Claude Code's model: `Tool(specifier)`
  rules, deny -> ask -> allow with first-match-wins and no specificity reordering,
  six modes, a five-source settings hierarchy with managed settings undeniable,
  and hooks that can narrow but never widen.
- **P1 lifecycle** — schema and migrations, OAuth transaction FSM with
  database-enforced single-use redemption, device-flow strategy, macOS Keychain
  credential store via Security.framework (not the `security` CLI, which puts
  secrets in argv), connector lifecycle, reauthorization, disconnect.
- **P2 discovery** — installations, repositories and organizations through the
  GitHub App endpoints, Link-header pagination, HMAC-signed opaque cursors
  validated four ways before dereference, uninstall detection.
- 138 tests, stdlib only. No new runtime dependencies.
- Design pack: `marketplace/plugin/connectors/design/`.

## 2.107.3

- **Apply's transport commit passes the repo's pre-commit gate** with the
  gate's own recorded-reason channel — verification for a machine apply is
  the PR's CI plus your merge, and the smoke PR (#119) proves the full path.
- **Store writes can no longer tear under concurrency.** `_write_json`'s tmp
  file is now unique per writer; the fixed name let parallel same-record
  writes interleave and promote torn JSON (a 1-in-6 test flake, now 8/8).

## 2.107.2

- **Apply works on submodule checkouts.** The default target repo is a
  submodule, where `.git` is a file — 2.107.1 refused it as "not a git
  repo". Caught by the live smoke before any install.

## 2.107.1

- **Apply understands the worker's own diffs.** The patch-policy gate now
  accepts bare `---`/`+++` unified diffs (what the worker actually emits) —
  2.107.0's gate only knew `diff --git` headers and would have refused every
  real task. Both forms are policed identically.

## 2.107.0

- **One-click Apply.** A reviewed Teamsutra task now has an Apply button:
  the diff is policed (no CI files, no binaries), applied on an isolated
  `teamsutra/*` branch, and opened as a GitHub PR you merge yourself.
  Failures land on the card in words and stay re-clickable. Never touches
  main, never auto-merges.

## 2.106.2

- **The draft shows what you highlighted again.** Ask Sutra's pre-filled
  message carries your selection as a quote under the question — same as the
  original behavior, still fully editable, still sent only when you press
  Enter.

## 2.106.1

- **Ask Sutra no longer sends the first message for you.** The chat opens with
  "What is this about?" sitting in the composer as an editable draft — change
  it or keep it, and press Enter yourself. Nothing runs until you do.

## 2.106.0

- **Teamsutra: the task loop closes.** The Ask Sutra chat can file a bug as a
  draft task; you queue it; the hourly worker (read-only — plan mode, no write
  tools) picks it up oldest-first and returns a unified diff; you read the exact
  change on the new Teamsutra board and apply it yourself (copy the diff to
  `git apply`, or hand it to a Claude session) — a one-click apply is not in
  this release. A crashed claim
  stays claimed until you release it — no retry loops. Queue/drop/release are
  desktop-token-gated; a CLI-served panel shows why its buttons are disabled.

## 2.105.0

- **Ask Sutra: select text, get a briefed chat.** Highlight anything in the panel
  and an Ask Sutra button appears; it opens a chat that already knows which
  department the selection belongs to (per-turn provenance, DOM-first, never
  guessed — "no department" when nothing classified it). The briefing is budgeted
  byte-exact against the server's 8000-char cap and states when it was cut.
- **A durable task store** at `~/.sutra-ui/teamsutra/` (schema-checked, inert
  creation at draft) lands as the substrate for the queued-worker half, which is
  NOT in this release.
- **Scheduled-routine hardening**: `install_runner()` refuses a runner that does
  not compile, and the module docstring no longer claims `dontAsk` cannot write.

## 2.104.0

- **Balance screen IS the approved design.** The desktop Balance screen now renders
  the tabbed Five Hats design natively — TODAY / THIS WEEK / MONTH, stat tiles, the
  30-day role heatmap, hours-of-day chart, shipped timeline and per-role coaching —
  instead of the older card-and-strip shape. The nightly renderer emits
  `dashboard-data.json` as the canonical UI read model, so the generated dashboard
  and the panel consume the same semantic decisions and cannot drift apart.
- **Drop an actionable.** Each actionable carries a quiet `x`: clear one that
  doesn't matter without claiming it was done. A drop takes one of four fixed
  reasons (chips, no typing) and stays visible in a collapsed "N dropped" list —
  the ledger keeps it forever either way. Terminal state is now terminal for every
  verb (a duplicate drop no longer appends a second closing row) and responses
  carry `closed_as`.

## 2.103.0

- **Balance — the founder coach ships.** Observe-only wellbeing + executive
  coaching: the Balance screen lists your live actionables and marks them done
  in place, backed by a new token-gated `POST /api/balance/actionable` (the
  renderer never sees the token — a narrow preload verb carries the call; no
  unauthenticated fallback). The engine (15-min observer, nightly coach pass,
  dashboard generator) ships in `scripts/balance/` with per-instance state
  resolution; see `docs/BALANCE.md` to adopt it and ADR-033 for the custody
  split. Suites: `tests/unit/test-balance-endpoint.sh` (auth, 422s,
  idempotency, concurrent duplicates, CLI-mode 403).
- **Version reconciliation.** `plugin.json` and the marketplace catalog were
  stranded at 2.99.1 while desktop tags ran ahead to v2.102.0-desktop (that tag
  was cut without a manifest bump). Both manifests now say 2.103.0, matching
  the tag cut for this release.

## 2.99.1

- **Fix streamed text re-shaping ("text coming and going").** `mdHtml` now closes an
  unterminated code fence before parsing, so streamed fences render as code from the
  first token instead of prose-then-collapse; `patchStreaming` skips repaints whose
  rendered HTML is unchanged.

## 2.103.0

- **"Check for updates" now downloads.** It reported a new version and staged
  nothing: staging ran only on the Electron shell's timer (90s after launch,
  then every six hours), so a deliberate check left the operator with a pill and
  no download, and the only way forward was the blocking "Download & install"
  that quits the app. The panel cannot stage by itself —
  `/api/updates/desktop/stage` is token-authenticated and the token deliberately
  never reaches the renderer — so a third preload verb (`stageUpdate`) asks the
  shell, exactly as `applyUpdate`/`deferUpdate` do. One staging run at a time,
  shared with the scheduled path, so a click during a timer run joins it instead
  of starting a second 160MB download. The screen stays usable while it runs and
  reports what actually landed. 5 new tests.
- **Test pane removed** from the Organization nav. It rendered nothing by design
  and was wired at three sites (nav → TITLES → SCREENS); all three are gone,
  pinned by a test.

## 2.102.0

- **"Transcript not read yet" was a resting state, not a flash.** Reported on
  opening the app; reproduced in the running panel — a pane opened on an IDLE
  session sat at `loadState:"unread"` for 8s and never moved. `ensureTranscript()`
  only acts on `"unread"` and was only CALLED from the three sites that open a
  pane, so the ⋮ → "open in repo" action (which pushes into `openPanes` without
  it) stranded the pane permanently; the background re-read in
  `applySessionChange()` is no safety net because it fires on a WRITE to the
  file and an idle transcript is never written. `render()` now schedules the
  read for every open pane — idempotent, like `loadRepo` beside it — so the
  invariant is structural instead of a call every future open-path must
  remember. Second fix: `sessionBody()` claimed "not read yet" for any state
  that was not loading/error/empty, including the `ok`-with-zero-turns the busy
  guard produces without parsing; a session that HAS been read now says what was
  actually found. 5 new tests pin both facts; 86 panel tests green.

## 2.101.0

- **Connectors mirror Claude; configuring is delegated to Claude (Option A).** A new
  **Present in Claude** section on the Connectors screen reads the operator's own
  connectors live from `claude mcp list` — the authoritative source, since `~/.claude.json`
  misses claude.ai connectors (Gmail, Drive, …) — and shows each with a status badge
  (connected / needs auth / pending). Configuring is delegated, not rebuilt: the buttons
  type `claude mcp add` / `claude mcp login <name>` into the terminal (never executed for
  you), so people use Claude's own familiar flow and Sutra never handles an OAuth token.
  Display-only and fail-soft — a read-only `/api/connectors/configured` behind a
  subprocess timeout + 30s TTL cache; the governed `claude -p --strict-mcp-config` spawn
  path is untouched (claude.ai connectors are not reusable headless under strict-mcp-config,
  verified 2026-08-15). 10 new tests (parser fixtures + fail-soft + TTL cache); 66 connector
  tests green. Codex-consulted.

## 2.100.0

- **Capture the agentic output.** The transcript parser kept only the agent's text
  and tool NAMES — you could see that a Bash ran but never what it ran or what came
  back. Now `_parse_transcript` captures each tool call's INPUT (command / file /
  query) and its RESULT (output, with an error flag), matched by `tool_use` id — data
  that was previously dropped. The subagent viewer and the replayed main transcript
  render each call as a command line with a collapsible output; failed calls are
  flagged. Per-result payload is capped so a huge output can't bloat a transcript.

## 2.99.0

- **Connectors gallery — ~50 servers, grouped by category.** The default Connectors
  view goes from 6 presets to a browsable gallery of ~50 recognizable MCP connectors
  (GitHub, GitLab, Postgres, MongoDB, Redis, Supabase, Notion, Linear, Jira/Atlassian,
  Asana, Slack, Discord, Stripe, PayPal, Sentry, Grafana, Cloudflare, Figma, Canva,
  Playwright, Browserbase, ElevenLabs, …) grouped into 11 categories. Every config was
  verified against the live MCP registry or a documented remote endpoint before
  inclusion — no invented package names (broken candidates like plaid/semgrep/deepwiki
  were dropped). The full open registry (~400) stays one search away; remote connectors
  carry auth headers. 56 backend tests.

## 2.98.0

- **Connectors browse the open MCP Registry.** The catalog is live now: an empty
  search shows curated presets; typing searches the official open **MCP Registry**
  (`registry.modelcontextprotocol.io`, ~400 servers) and a result prefills the add
  form (stdio `command`/`args`/`env_keys` for packaged servers, `url` for remote).
  Fail-soft to the built-in presets if the registry is unreachable.
- **Claude-parity gaps closed:** auth **headers** for http/sse remote connectors
  (Authorization etc., merged into the session's `--mcp-config`), and **Import from
  Claude** — one-click add of the MCP servers already in `~/.claude.json`. 53
  backend tests (registry normalize, headers merge, import, fail-soft).

## 2.97.0

- **Fix "Transcript not read yet" flicker.** An open, already-loaded pane was rebuilt
  to `loadState:"unread"` on every session-list refresh — and agent activity triggers
  many of them — flipping the pane back to the placeholder. `adoptRealSessions` now
  preserves the object for a pane you're reading (busy **or** open+loaded), refreshing
  only its metadata.
- **Fix the heavy flicker while agents work.** `applySessionChange` re-read an open
  pane on every live-sync event and set `loadState:"loading"` first — flipping the
  transcript to "reading transcript…" and back on each write. It now keeps the
  transcript on screen during a background refresh (no placeholder flip), and throttles
  both the transcript re-read and the agent-fold reload to ~1/s.

## 2.96.0

- **Connectors — MCP servers for your sessions, like Claude CLI.** A new Connectors
  screen (left rail, Runtime) to add / enable / remove MCP connectors that are
  offered to every session this panel starts. Add by hand (stdio: command + args +
  env; or a remote http/sse url) or one-click from a catalog (github, filesystem,
  slack, puppeteer, brave-search, linear). Enabled connectors are merged into the
  `--mcp-config` passed to spawned `claude` (alongside `sutra`, keeping
  `--strict-mcp-config`); they run under the session's permission mode, so use
  Accept Edits or Bypass to let them act. Store at `~/.sutra-ui/connectors.json`;
  fail-soft (a broken store never breaks turn spawning). 33 backend tests.
- **Fix "Restarting in nulls".** The update banner rendered a null countdown once
  `applyUpdate` fired (clock stopped, app not yet quit). Added a dedicated
  "restarting…" state and made the countdown null-safe.

## 2.95.0

- **First desktop release built, signed, and notarized entirely in GitHub Actions.**
  With the five secrets wired (`APPLE_CERT_P12`/`APPLE_CERT_PASSWORD`,
  `APPLE_NOTARY_KEY`/`APPLE_NOTARY_KEY_ID`/`APPLE_NOTARY_ISSUER`), pushing a
  `v*-desktop` tag builds both arches on native runners, signs with the Developer
  ID, notarizes via the App Store Connect API key, and uploads `Sutra-<arch>.dmg` —
  no local build. Also fixes `test_charter_filter.js`, which had failed every CI
  run since the panel split (it parsed a pre-split inline `<script>`).

## 2.94.0

- **Native folder picker, finished.** Browse now opens Finder at the folder you're
  already in — the dialog receives a tilde-expanded `defaultPath` passed through the
  IPC — and choosing a folder in the composer **applies it immediately**. Before, the
  pick was written straight to the input with no backing state, so a live re-render
  could wipe it before you pressed SET. Settings still fills a draft you confirm with
  Save; the routine folder field persists to its form. The IPC handler now returns
  null on any dialog error instead of rejecting the renderer. Verified end-to-end:
  the button renders only with the Electron bridge, the current path is the dialog
  default, and the pick is applied.

## 2.93.0

- **Subagent viewer rebuilt to Claude's agent view.** The "N subagents" list was a
  wall of raw prompt text, each row mislabeled "1 turn", and the detail folded the
  whole run into one unreadable bubble. Now each agent is a clean card — a real
  title (the parent `Task`'s `description` when the spawning turn is still on disk,
  else derived from the prompt), an agent-type badge, and a meta line (N steps ·
  tools used · relative time). Clicking one opens a readable **step-by-step**
  transcript: the task it was handed (collapsed), each step's text + tool calls,
  and the final message set apart as the result. Backend: `list_agents` joins to
  the parent transcript's `Task` tool_use for the title/type and counts assistant
  **steps** (real work), not the always-1 user-turn count. Verified live on this
  session's 43 agents; Sutra theme kept.

## 2.92.0

- **Activity moves to a header trigger + right-docked drawer.** The bottom-right
  floating panel is replaced by a compact trigger in each chat header's top-right
  (a live count badge that pulses when work is running). Clicking it opens a
  right-docked, **non-modal** Activity drawer — "Running turns" + "Agents" with a
  per-item stopwatch — the Claude Background-tasks placement. Close with ×, Escape,
  or by re-clicking the trigger. Same `/api/activity` data; no backend change.
  Verified live: trigger renders in the header, drawer opens/closes, the badge
  syncs to the running count, and this session's own turn shows with a ticking
  stopwatch.
- Formal evals added for `/api/activity` + `head_meta` + the folder-picker gate.

## 2.91.1

- **verify-templates print evidence on pass**: grep-count -> "found N of >=M",
  file-exists -> bytes/lines/age per target. Stdout only; stderr, semantics,
  exit codes unchanged. Feeds the new EVAL line in ATOM CLOSED cards.

## 2.91.0

- **Live Activity panel — Sutra's Background-tasks equivalent.** A floating,
  collapsible panel (bottom-right) surfaces all running work live: in-flight chat
  turns (each is a spawned `claude` process) and running subagents, with a live
  count badge and a per-item stopwatch. Backed by a new read-only
  `GET /api/activity` that reuses the existing liveness/index logic rather than
  inventing a divergent one. Closes three gaps vs Claude: agentic work in
  progress, background processes running, and agent tracking.
- **Native Finder folder picker.** A "Browse…" button on every working-directory
  control opens the macOS directory chooser via a new `sutra:pick-directory` IPC
  verb; the text input stays an editable fallback and the button hides in a plain
  browser (Electron-only). No more pasting absolute paths.
- Built by two parallel agents on disjoint file sets; verified live (the endpoint
  caught this very session's running turn), 76/76 panel tests, zero console errors.

## 2.90.0

- **Notarized desktop release.** The 2.81.0 sutra-ui parity work — live sync,
  resume-in-the-right-folder, the running-turn strip, the subagent transcript
  viewer, the per-session ⋮ menu, and the panel.html → panel.css + 9-module
  split — now ships as Developer ID–signed **and Apple-notarized** DMGs for both
  Apple Silicon (arm64) and Intel (x86_64). No source change since 2.81.0; the
  version is realigned to 2.90.0 for a clean notarized cut that supersedes the
  un-notarized 2.81.0-desktop assets.

## 2.81.0

- **The desktop panel becomes one entity with Claude.** A run of sutra-ui work,
  all verified in the running app:
  - **Live sync + resume correctness.** A chat in Claude appears and updates in
    Sutra as it is written; a reply sent from Sutra continues the SAME Claude
    conversation (resumed in the session's own project folder) instead of
    silently forking a new one. Sessions show active/idle/stale and a running /
    live / N-agents badge.
  - **Titles you set in Claude** (custom-title / ai-title) show in the rail,
    not the raw first prompt.
  - **The running turn shows real progress** — a run strip with a stopwatch,
    tool counts and per-tool durations, replacing the single unreadable pill.
  - **Subagents are visible AND readable** — the "N agents" badge opens a fold
    listing each subagent with its task and a live dot; clicking one renders its
    transcript. A background agent now shows "running" until it truly finishes,
    not "done" at launch (fixed from measured stream frames).
  - **A per-session ⋮ menu** — Open in (Terminal/Editor/Finder/Repo), Pin, Mark
    as unread, Rename, Fork, Move to group, Archive, Delete. Rename appends the
    same custom-title record Claude writes; Archive/Delete MOVE the transcript to
    ~/.sutra-ui/{archive,trash} recoverably, never unlink — verified end to end.
  - **A real keyboard layer** — /, Cmd+Enter to send, Cmd+N, Cmd+[/], Cmd+.,
    Cmd+Shift+W, an Escape cascade, and a reload guard while a turn streams.
  - **Working-directory, usage, and repository controls** in the composer.
- **Architecture: panel.html split into panel.css + 9 JS modules.** The 7900-line
  single file is now a shell loading ordered modules by concern, so UI iteration
  touches one small file instead of a monolith. Behaviour-preserving: the modules
  concatenate byte-for-byte back to the original script.
- **Fix: catalog version drift.** marketplace.json's core entry (2.79.0) had
  drifted from plugin.json (2.80.1) after the verifier merge; both now read
  2.81.0 and the manifest-sync check is green.

## 2.80.1

- **verifier final-review fixes**: `sutra-eval` exits 3 (not 0) on repos without
  a verifier setup so automation never reads "no setup" as "all clear".

## 2.80.0

- **Verifier layer + Evals screen.** Desktop panel gains an Evals rail screen
  (registry counts, nightly scorecard, regression strip) over new GET /api/evals;
  `sutra-eval` ships DORMANT fleet-wide (delegates on repos with a verifier
  registry, honest no-setup answer elsewhere). ADR-032; program: VERIFIER-LEDGER.md.

## 2.79.0

- **Balance screen beauty pass.** Serif greeting with the day's one-liner,
  insight cards as accented stat tiles, day strip in a card with hour marks,
  polished composer — all from existing panel tokens; visual-only.

## 2.78.2

- **usage-guard: both windows everywhere.** session (5h) + 7-day each shown with
  pct/bar/reset in status, warning line, and hard-block box (founder ask 2026-08-07).

## 2.78.1

- **usage-guard fix**: `sutra-usage on` stamps the enabled flag with ts+host
  (empty flag failed non-empty file checks).

## 2.78.0

- **Usage-guard (opt-in, dormant by default).** New PreToolUse hook + `sutra-usage`
  CLI: warns at 70% rate-limit utilization, HARD-blocks tool use at 80% until the
  founder says "continue" (`sutra-usage continue`; override expires at window reset).
  OFF everywhere until a machine opts in with `sutra-usage on`. Fail-open on any
  data error; `sutra-usage status` shows live five-hour/seven-day utilization.

## 2.77.0

- **Balance speaks human (founder-approved register).** Observe v2 filters
  machine prompts and reads the founder's own messages — time, tempo, breaks,
  parallel threads, course corrections. Card framework: time / energy /
  awareness / understanding / actionable / custom, evidence-gated, plain
  language; energy framed as tempo, never emotion. Backing metrics stay in
  signals for audit.

## 2.76.0

- **Balance screen v3 (founder redline).** Takeaway cards in a compact
  3-across grid; day strip is 96 fixed thin 15-min slots (width-capped);
  the chat affordance is now an inline composer in the screen — type, Enter,
  and a Balance-loaded session opens already answering via the normal
  submitTurn pipeline.

## 2.75.0

- **Balance screen shows real observations.** New read-only GET /api/balance
  (fixed dir, no traversal surface, fail-closed) serves the state contract;
  the screen renders today's real state, takeaways, and window strip — the
  sample cascade now appears only when no data exists.

## 2.74.0

- **Balance chat is live in the desktop panel.** The Balance screen becomes a
  cascade (sample state line + takeaway cards) over a REAL chat: "Open Balance
  chat" starts a fresh session pre-loaded with the Balance persona via the
  existing append_system_prompt seam — coach register, ledger evidence,
  honesty floor (observation not started). No server change; 76/76 tests.

## 2.73.0

- **Balance design preview in the desktop panel.** New rail item (runtime
  section) + screen: honest "not yet observing" state + sample-labeled
  takeaway taxonomy (AWARENESS/UNDERSTANDING/ACTIONABLE). Preview only —
  no state, no counts, no chat until Stage 1/2 land. Additive; no server change.

## 2.72.0

- **verify-runner ships fleet-wide.** Shared check executor with atom-close
  semantics (pinned templates, envelope + dotdot refusals, SHA pin, 30s alarm)
  — base of the Eval Engine (ADR-031): atom checks become standing evals.

## 2.71.0

- **The chat can now drive Sutra itself.** Ask it for a routine and it makes one
  — through an MCP tool server, which is Claude Code's own extension mechanism,
  so the tools appear to the agent exactly like its built-ins. The server is
  spawned for one run over stdio; nothing is installed and your global
  `~/.claude.json` is never touched.
- **Reads act; mutations propose.** The four mutating tools write an inert
  proposal and return immediately — the agent never blocks waiting for a human,
  and nothing touches launchd or settings until you approve it under Routines.
  Three reasons, each sufficient alone: a `-p` run has nobody to answer a
  permission prompt; an agent acts on text that may not have come from you; and
  the local port is unauthenticated, so the write side of this surface is worth
  nothing to an attacker.
- Invalid requests are refused at the tool, before a proposal exists — a
  proposal that cannot apply would be approved and then fail for a reason
  nobody was shown.
- **Markdown**: nested lists were flattened (`- a / ␣␣- b` rendered as
  siblings), and fenced code came out inside a paragraph — invalid HTML, which
  is what caused the odd gaps around code blocks. Both fixed.
- **A live activity mark.** While a reply composes, the Sutra mark breathes
  beside it, and moves into the pill while tools run. It stops under
  `prefers-reduced-motion`: motion is decoration, the word carries the meaning.

## 2.70.1

- Desktop auto-update is now mandatory and staged: an update is downloaded and
  verified first (`staged`), and only then armed, so deferring costs nothing and
  a boot that finds a fresh `installing` record cannot arm a second helper.
- The routes that can quit the app and replace the bundle require a token the
  Electron shell mints and hands only to the backend it spawned — they are
  otherwise reachable by any page in any browser on this machine. When the panel
  is attached to a CLI-owned server there is no token, arming is refused, and
  auto-update is off, which is the correct answer: quitting this window would
  not stop a backend somebody else owns.
- A minimal `preload.js` is the only IPC bridge, for the one thing the panel
  cannot do over HTTP — end this process so the swap can happen. In a plain
  browser `window.sutra` is absent and the restart UI does not appear, so a
  countdown never promises a restart it cannot perform.
- This release also makes git match what shipped: 2.70.0 was built from a tree
  containing this work before it had been committed.

## 2.70.0

- **Routines.** A prompt this Mac runs on a schedule — a morning brief, a nightly
  check — without you opening anything. Create, list, run now, pause, delete,
  and read what happened on every past run.
- Claude Code has two kinds and only one is honestly ownable here: cloud routines
  live in the claude.ai account with no local file format or scriptable CLI.
  These are the **Local** kind, and the badge says so — their noun, our scope, no
  implied parity. The five schedule presets are Claude's own: Manual, Hourly,
  Daily, Weekdays, Weekly, plus a custom cron escape.
- Scheduled with a **launchd user agent**, not an in-app timer. The app quits
  when its last window closes and kills the backend with it, so an in-process
  tick would fire approximately never. This does not contradict ADR-017: that
  governs the Native engine's Trigger cadence, which is a different thing at a
  different layer.
- **A routine cannot use a write-capable permission mode.** `acceptEdits` and
  `bypassPermissions` are unreachable for a routine by code — a positive
  allow-list, not a subtraction, so editing the unsafe-modes tuple cannot
  silently re-admit one. There is no env var, settings key or consent phrase that
  reaches them. The default is `dontAsk`, not `plan`: `plan` unattended proposes
  edits nobody approves, exits 0, and reads OK while the routine does nothing
  forever.
- A per-run budget ceiling is required, the working folder must exist and be
  inside your home, and a routine may fire at most once an hour.
- The screen refuses to flatter: **"never run" is never rendered as "0 runs"**, a
  green *Run now* is labelled as proving the runner and not the schedule, a
  saved-but-not-loaded job shows launchd's own stderr rather than a generic
  failure, and next-run is not computed — launchd decides, and an invented time
  would be wrong the first time the Mac slept.
- Sleep is stated up front: if the Mac is asleep at the scheduled time launchd
  runs the job on wake, and several missed slots coalesce into **one** run.

## 2.69.1

- **The permission selector was a white box in a dark theme.** It shipped in
  2.69.0 with no CSS at all and fell back to the browser's default styling,
  sitting directly beside a correctly themed model selector. Both composer
  selects are now styled by one rule so the next control added there cannot
  drift either — and a mode that writes files without asking carries the warn
  colour, so that state is legible in the composer instead of only inside the
  dropdown.
- **The Directory view collided with itself in a narrow pane.** Two compounding
  bugs, both pre-existing: `grid-template-columns: 1fr` is `minmax(auto,1fr)`
  and `auto` floors at *min-content*, so the column sized itself to 973px inside
  a 385px pane; and when the container query collapsed the grid to one column
  the table of contents was still `position:sticky`, so it printed itself over
  the department names underneath. The column can shrink now, and the TOC goes
  static when it collapses.
## 2.69.0

- **The permission mode is chosen next to the composer now, not in Settings.** It
  was editable only in Settings, and the write-capable modes were reachable only
  by restarting the server with `SUTRA_UI_ALLOW_UNSAFE_PERM_MODES=1` — which for
  a Finder-launched app means editing a plist. The panel was showing a control,
  refusing it, and telling you to do something you realistically could not.
- The selector shows the **effective** mode, never the stored one: the server
  clamps at the point of use, so showing the stored value would claim the agent
  is doing something it is not.
- Choosing a write-capable mode opens a confirmation carrying the server's own
  wording for what that mode does, and only that confirmation sends the
  acknowledgement the server requires — a bare boolean is refused, because the
  local port is unauthenticated and enabling file-writing must be deliberate.
  Cancelling reverts the selector rather than leaving it displaying a mode that
  is not running. Consent can be withdrawn the same way.
- **Streaming no longer flickers, jumps or stutters.** A token frame called
  `render()`, which replaces the whole pane via `innerHTML` — ten times a second
  the entire transcript was destroyed and re-parsed. That was one bug producing
  three symptoms: flicker (every node replaced), the view snapping bottom→top
  (the new scroller starts at `scrollTop 0` and is then re-pinned), and
  choppiness (100 ms batching is 10 fps).
- A token now patches only the streaming reply's own node on an animation frame.
  The scroller is never replaced, so your scroll position survives by
  construction — and if you have scrolled up to read, the view is left exactly
  where you put it instead of being yanked to the bottom.
  Measured over 40 token frames: **0 full re-renders**, same DOM node throughout.

## 2.68.1

- **You can now check for, and install, both updates from Settings.** There was
  no way to find out either was out of date, and the two update by completely
  different mechanisms — showing them as one "check for updates" would
  misdescribe both:
  - **Desktop app** — no auto-updater at all. Squirrel is in the bundle only
    because Electron ships it; nothing wires it up. It changes only when
    someone installs a DMG.
  - **Plugin** — already self-updates once a day at session start, applying to
    the *next* session. The button only makes it immediate.
- Checking is never automatic: nothing runs on boot, because a desktop app that
  phones home every launch is a different product decision from one with a
  button.
- Installing the desktop update is split, because a bundle cannot overwrite
  itself while running. The app downloads and **verifies** — sha256 against the
  published checksum, `spctl` (notarized, not merely signed), and
  `codesign --verify` on the bundle inside the mounted image — and only then
  arms a detached helper that waits for the app to exit, swaps, and reopens.
  Any gate failing leaves `/Applications` untouched and says which one.
- `GET /api/updates`, `POST /api/updates/plugin`, `POST /api/updates/desktop`.
  All of it lives in the Python backend, since the Electron shell has no IPC
  surface — which also makes it testable without a server.

## 2.68.0

- Telemetry is ON by default (anonymous, once daily) per founder direction D64;
  identity still requires explicit consent, opt-out honored, one-time disclosure
  shown. Catalog version re-synced to source (drift guard was red at 2.43.0).

## 2.67.1

- **`claude` was undetected on other people's Macs** — on machines where it ran
  fine in every terminal. A Finder-launched app gets launchd's minimal PATH, so
  the app asks the login shell what PATH should be; it asked with `zsh -l -c`,
  which is a login but **non-interactive** shell, and zsh reads `~/.zshrc` only
  for interactive ones. `.zshrc` is exactly where nvm, npm-global and Claude
  Code's own native installer export PATH. Reproduced with a HOME whose
  `.zshrc` adds the directory holding the binary: `-l -c` misses it, `-l -i -c`
  finds it first. This never showed up in development because Homebrew writes
  its shellenv to `.zprofile`, which a login shell does read — the bug is
  invisible on precisely the machines that install via Homebrew.
- Fixed in two independent layers: harvest an **interactive** login shell and
  union it with the login-only answer (neither can lose a directory the other
  found), and **probe the documented install locations directly** for the case
  where no shell can be asked at all — `~/.local/bin`, `~/.claude/local`,
  `/opt/homebrew/bin`, `/usr/local/bin`, `~/.npm-global/bin`, `~/.bun|.volta|
  .deno/bin`, and every `~/.nvm/versions/node/*/bin`. A directory joins PATH
  only if it exists *and* actually contains the binary.
- The "not on PATH" message now says both searches already failed and names
  `SUTRA_UI_CLAUDE_BIN`, instead of sending people to look in the wrong place.

## 2.67.0

- The panel was dead on boot, and had been on main. `5781a2f` deleted
  `<div id="tenantMenu">` from the markup and left the code that wired it, so
  `getElementById` returned null, the next `addEventListener` threw, and
  `boot()` -- the last statement in the script -- never ran. Nothing was
  fetched. Settings said "GET /api/settings has not answered" (it was never
  called), Departments and Directory said "No domains" (58 were on disk), the
  session list showed one empty local session (47 real transcripts existed),
  and the footer read "no tenant". Every endpoint behind those screens returns
  200.
- Removed the rest of the tenant surface, which is what left the app in that
  half-removed state: the chip, the footer label, the chooser, the gate, the
  dead Tenants screen, `inTenant`/`scopeQ`/`META.tenant_id`/`showAcme`, the
  `?tenant=` on four endpoints, and boot()'s silent `if (!S.tenant) return`.
  Tenancy was already removed server-side; the client had not caught up.
- Settings could be reported unavailable when it was fine: `loadRuntime` used
  `Promise.all`, so a failure from `/api/skills` discarded a good
  `/api/settings` response and nulled SETTINGS for the life of the window.
  Now `allSettled`, and the error names which endpoint actually failed.
- Terminal, three faults. `termSetMode` called `mountTerm()`, which has never
  existed, so switching Shell/Claude threw after persisting the new mode --
  the toggle moved and the PTY did not. `.termbody{display:flex}` overrode
  `[hidden]{display:none}`, so the Preview tab left the terminal laid out at
  zero size, it fit itself to 2x1 and pushed that winsize into the PTY. And
  nothing re-fit on the way back. Floored in the client, floored again in the
  `/ws/term` handler, and re-fit when the tab is shown.
- Composer restored to the theme. It became a `<textarea>` in `03c09cc` while
  the styling still selected `.pc input`, and `font:inherit` reset it to 16px,
  so it rendered as a bordered box with a browser focus ring.
- New Automation screen. The dispatcher has real state and is read from it
  (`.sutra/*.jsonl`, `.enforcement/*.jsonl`, read-only). The scheduler has
  none: cadence is a daemon-side tick in the Native engine (ADR-017), that
  daemon does not run in this install, and the v1.0 scheduler does not
  evaluate cron at all. It reports liveness and states the absence rather than
  drawing "0 runs today", which would claim a scheduler ran and found nothing.
- History crashed on real data: two `domain_updated` events carry no `ts_ms`,
  and `fmt()` threw a RangeError that took the whole screen down. An undated
  row is a fact about that row.
- Fixed during this release: removing the tenant popover by line range also
  deleted `.app`'s grid, `.rail`'s flex column and the narrow-window media
  query that happened to sit inside the range, which collapsed the
  three-column layout and stacked the rail across the top. Restored, and
  pinned by a test.
- 129 python + 58 node tests. The new regression tests are mutation-checked:
  reintroducing each bug fails exactly its own test.

## 2.66.0

- Daily auto-update. The first session each day refreshes the marketplace and
  updates the plugin, then prints one line if the version moved. Later
  sessions that day exit immediately with no network call.
- Bounded by the hook-level timeout (macOS has no GNU timeout) and fail-open
  throughout: a missing CLI, no network, a failed update or a killed hook all
  exit 0 in silence. A broken updater must never stop a session starting.
- The update applies to the NEXT session, not the running one, and the message
  says so.

## 2.65.0

- Dispatch runtime ships to the fleet. Every file change must now belong to a
  declared unit: `sutra-dispatch resolve` -> `sutra-atom open` -> `bind`, and
  mutations outside the declared envelope are blocked. See DISPATCH-ADOPTION.md.
- CLIs, hooks, matcher and routing policy all resolve plugin-first via
  hooks/lib/sutra-paths.sh; CLAUDE_PLUGIN_ROOT is authoritative, so a missing
  asset fails loudly rather than silently running origin code.
- Fixed a client-blocking bug the origin repo could not see: with no plugin
  cache on disk, `ls -d` on the cache glob failed and pipefail+set -e killed
  `resolve` with no message.

# Changelog

> **D# namespace cleanup wayfinder (2026-05-04)**: References below to "D43" in v2.16.0 release notes mean **OUT-DIRECT 3-check** which has been **renumbered to D46** in `holding/FOUNDER-DIRECTIONS.md`. References to "D44" in v2.17.0 release notes mean **PERMISSIONS extension** which has been **renumbered to D47**. The capability-axis charter keeps original D43; Native Workflow Personalization keeps original D44. Historical refs in this CHANGELOG are preserved unchanged — they describe what was operationally true at release time.

> **CHANGELOG drift note (2026-05-09)**: v2.33.0 + v2.34.0 release notes live in `.claude-plugin/plugin.json` description field but were not back-filled into this CHANGELOG. v2.35.0 below is the first entry written here since v2.32.0. Backfill of v2.33-34 is queued as a small follow-up; full release detail for those two versions is in plugin.json.

## v2.64.3 (2026-08-04) — consult-gate false-positive fixes (WDP W1-T13, dual-reviewed)

- consult-gate: hook-owned staging exemption (session scratchpads, codex/deepseek temp; dotdot-proof, NOT blanket /tmp) — kills the prompt-staging deadlock (d12).
- consult-gate + marker: persistent consult ledger with consume-once carryover (<30min, same session) — background consults finally satisfy the per-turn gate (d9); marker match hardened to anchored command word on quote-stripped copy.
- structural-move-check: quoted args of codex/curl heads are data, not operands — HARD-path strings inside prompt text no longer block (d10). Replay suite: holding/tests/w1-t13-plugin-test.sh.

## v2.64.2 (2026-08-04) — telemetry repair: phase-exit transcript parse + spillway log split

- phase-exit-audit.sh read transcripts with the wrong jq shape (.role/.content vs .type/.message.content[].text) — every row logged transcript_status=empty; fixed, instrument live again.
- routing-misses.log had 7 unrelated writers; each now owns a file (marker-resets.jsonl, proto005-warnings.log, loop-guard.jsonl, cascade.jsonl, proto004.jsonl, proto009-warnings.log, output-behavior-lint.jsonl). routing-misses.log is pure routing misses again; old rows untouched.
- placement-touch.sh stderr no longer swallowed — engine errors land in .enforcement/placement/touch-errors.log. Codex consult: ADVISORY (2026-08-04).

## v2.64.1 (2026-08-04) — blueprint-check marker fallback for non-flushing harnesses

- On the 'missing' verdict only, accept the documented v2.2 session marker (HAS_OUTPUT/HAS_VERIFY, per-step at D3+, optional FILES= allowlist) — under Fable 5 assistant text reaches the transcript only at end of turn, so the PreToolUse text gate was unsatisfiable, not strict.
- Visible-but-invalid blocks still hard-fail; Stop-time per-turn-hard-gate keeps validating final text; every fallback audit-logged to .enforcement/blueprint-fallback.jsonl. Codex: ADVISORY.

## v2.64.0 (2026-08-02) — Sutra UI panel (PR #85) + security hardening

- Sutra UI ships: local governance panel (FastAPI + static panel.html), Electron desktop shell, org API, provider selector, installer.
- Hardening applied before fleet distribution — `/ws/chat` and `/ws/term` rejected any Origin, so any page the operator visited could drive the local agent and inject into the PTY. Both now reject non-loopback Origins before `accept()`, plus TrustedHostMiddleware against DNS rebinding.
- `acceptEdits` / `bypassPermissions` were settable over the unauthenticated settings endpoint and reached the agent spawn. Now require `SUTRA_UI_ALLOW_UNSAFE_PERM_MODES=1` and are clamped at point of use, so a stale or hand-edited settings.json cannot raise the ceiling.
- Agent workdir confined to `$HOME` (`SUTRA_UI_WORKDIR_ROOT` widens it); `openExternal` restricted to http(s); `npx --no-install`; `fixture_seed.py` refuses the live registry.
- 14 new guard tests (`test_ws_origin_guard.py`); 146 tests green across python, engine, and node suites.

## v2.63.0 (2026-08-01) — on-the-fly data + landscape section removed

- Charter pages hydrate volatile data (status, metric currents, milestone states, task done-states, fraction pills) from a single registry.json fetched fresh on every page load — textContent-only, enum-allowlisted, count-validated per section, silent static fallback. Structural changes still regen.
- Auto-refresh hook gains a FAST LANE: on any registry drift it exports + pushes ONLY registry.json (3-min coalescing); full page regen keeps the 60-min debounce. Data freshness = next page load after Pages publishes the push.
- "Where this fits" section removed (founder: not earning its place — the byline already carries owner + works-with).

## v2.62.0 (2026-08-01) — consumer charter pages (founder-approved v6)

- Charter pages redesigned to the approved product template: Goals -> metric cards with honest progress bars -> landscape strip -> merged Progress (milestone track + drill-down task tables Done/In-progress/Remaining + shipped fold) -> Key documents (artifacts U scope_in, friendly titles, new tab) -> concise fine print. Customer language only; every section data-gated so all sparse charters degrade cleanly.
- Four optional charter fields (goals/metrics/milestones/todos+tasks) with validated skeleton->apply (closed status enums, done_at only on done, milestone label matching, task shape) in charters_seed + pipeline. Placement ADR-028 populated as the worked example from true ledger state.
- Withheld-domain fix: pages of hidden descendants are also PRUNED from the output dir (stale-file leak closed).

## v2.61.0 (2026-07-31) — the whole lifecycle as one pipeline CLI

- New lib/domains_pipeline.py: init / structure skeleton+apply / charters skeleton+apply / projects (delegates to charters_seed) / design show+set / publish / autopublish on|off / status. Every stage idempotent with per-row outcome reports; LLM only fills grounded skeletons. Consent boundary: publish never enables automation — autopublish is its own explicit command (codex fold).
- Verified: new-client e2e on a fresh registry (init -> 3 depts + 1 rejection -> 3 charters -> tokens -> 7-page branded site -> full re-run 0 mutations) and a live run on the Asawa registry (status accurate, 154-page regen).

## v2.60.0 (2026-07-31) — marker migration complete

- Marker migration complete: gate self-whitelist + out-of-repo guard (double-brick fix), dispatcher-pretool session-first, P4 telemetry readers on marker-lib, P5 instruction sweep (legacy write instructions: 0 remaining), fixture s7 strict-readiness.
- ADOPT=0 default flip attempted then reverted: s7 strict passes standalone, but default=0 reddens fixture s1/s4/s5 (transitional adoption + crash-recovery re-adopt). Strict flip deferred until fleet govblock migration + fixture rework. Suites final: marker-concurrency 7/7, flow-gate 25/25, hook-integration 6/6.

## v2.60.0 (2026-07-31) — programmatic charter mining for the fleet

- New lib/charters_seed.py: `discover` (deterministic scan for history sources -> per-source skeleton rows) + `apply` (validate/resolve/dedup/mint project charters; grounding floor rejects rows without real git-tracked evidence; no status defaults; strict-skip on existing; JSON report). The LLM only reads documents and fills rows — everything mechanical is script-owned.
- SKILL.md mining playbook: discover -> read + fill under grounding rules -> apply -> report -> auto-refresh publishes. Tested: 5-case validation matrix + idempotent re-run on a temp registry.

## v2.59.1 (2026-07-31) — verify-then-link artifacts + templatized file summaries

- Charter artifacts/scope link ONLY when resolved against git-tracked files (abs paths under the work root normalize; bare filenames resolve by unique suffix and display the match; directories link to tree/ with tracked-file counts; unresolvable entries render muted, never a 404 link).
- Every linked file shows a one-line summary derived from its content (md heading / docstring / first meaningful comment, boilerplate skipped) — templatized, zero hardcoding. GH links open in a new tab; path segments URL-encoded. Verified: 248 links, 5/5 sampled URLs return 200.

## v2.59.0 (2026-07-31) — version reconcile

- Reconciles the parallel-session version collision (2.58.0 owner-first table vs 2.58.1): this release carries BOTH change sets; no code delta beyond the version field.

## v2.58.1 (2026-07-31) — codex-gate memory carve-out + orchestrator fleet ON

- codex-consult-gate.sh exempts ~/.claude/** (memory files) — scoped narrower than blueprint v2.39.20 to avoid mv-ingress bypass; regression test hooks/codex-gate-outofrepo-test.sh (3 cases). flow_orchestrator_mode -> "on" fleet-wide (founder-directed; ADR-029 D5 second amendment). ADR-026/027 posture notes + cross-refs; ADR-029 D3 return_contract naming note. Head reordered newest-first (v2.55.1 moved below v2.56.0).

## v2.58.0 (2026-07-31) — marker concurrency core (Scheme A)

- Marker concurrency core (Scheme A, founder-ratified): self-only adoption + ownership-safe reset kill cross-session contamination; 8 gates read session-first via marker-lib; 3 writers SESSION-stamped; 6-scenario two-session fixture gates it. Root cause: holding/research/2026-07-30-marker-race-root-cause.md.

## v2.58.0 (2026-07-31) — owner-first merged table, active default, GitHub artifacts

- Charter table restructured: Owner is the FIRST column; same-owner rows merge visually ("here" block first, then owners by name) — JS-safe merge that recomputes to first-visible under filter/search, screen readers still hear owner per row. Status filter defaults to ACTIVE (falls back to all when a page has no active charters).
- Charter pages: artifacts (and scope entries) are now GitHub blob links resolved from the repo's actual remotes (submodule-aware, fleet-generic), opening in a new tab; Scope-in/out rows carry hover explainers and are skipped when they duplicate the artifact list.

## v2.57.0 (2026-07-31) — SOFT auto-refresh for the domains site

- New Stop hook domains-site-refresh.sh: on registry drift, regenerates the zoom site + commits + pushes. Never blocks (exit 0 every path), 60-min debounce, full-content fingerprint, non-blocking lock, push-only, prompts off, 120s/60s caps, stamp written only after successful regen. Dormant fleet-wide until a repo opts in via .claude/domains-autopublish (D33-safe).
- Verified live: forced drift -> regen + commit + push; no drift -> no-op; drift-under-debounce -> deferred. All exits 0.

## v2.56.0 (2026-07-30) — one charter table + per-charter pages

- Own, linked, and cross-cutting charters merge into ONE table per department (canonical row per charter, relationship-grouped, O/L child columns, status filter buttons composing with search, "no charters match" empty state).
- Charter names click through to NEW per-charter structured pages (C-<id>.html, stable ids): breadcrumb + owner up-link + labelled rows (Purpose/Kind/Status/Owner/Linked/Artifacts/Scope/Obligations when non-empty). 154 pages total, 0 broken links.

## v2.55.1 (2026-07-30) — return-contract schema aligned to operative contract

- ADR-audit F1/F2: schema now tolerates extra keys + string-form verify, matching validator R1/R2 and fixture f1 (validator + fixtures unchanged). F3-F5: ADR-029 amended (flag ladder off/experimental/on; matcher v0-floor cross-ref; mechanical-floor scoping) + ADR-026 open item narrowed (v0 floor shipped; judgment layer open). Audit: holding/research/2026-07-30-adr-026-027-029-consistency-audit.md.

## v2.55.0 (2026-07-30) — charter chips: readable, minimal, mobile-friendly

- Charters render as status-dotted TAGS (design tokens from D0). Density heuristic: <= 3 in a group and short purposes -> mini-cards with the one-liner visible; more -> compact chips with hover tooltip (desktop) + native tap-to-expand panel (mobile/keyboard) carrying purpose, links, artifacts.
- Minimal text pass (founder): lane note -> "O owner / L linked", terse footer, "Linked" group, chips over prose. Search filters chips (incl. hover text) and hides empty groups. Mobile: full-row 44px targets, full-width panels. Codex folds: summary CSS normalized + focus-visible, artifact count stays on compact chips, title-attr only on closed summaries.

## v2.54.0 (2026-07-30) — charter layer: projects are charters + cross-cutting lanes

- Every department page now carries a Charters section (empty state included): Standing | Projects with status tags, artifact counts, linked-department pills, and a "Linked here (owned elsewhere)" group. One owner per charter; links are references, never homes.
- Cross-cutting lane chart on parent pages: columns = direct children, rows = charters touching >= 2 columns after roll-up (O = owner, L = linked, text markers + aria labels); lanes never descend into sub-departments. Codex P1 folds: per-column set-dedup, parent-owned case defined.
- 42 project charters mined from real history (holding/plans, holding/evolution, 29 ADRs + 6 engines, project memory) by a 4-agent workflow; artifact paths verified on disk; seeding idempotent.

## v2.53.1 (2026-07-30) — flow_orchestrator_mode off -> experimental

- ADR-029 rollout step 2, asawa-holding opt-in; f8 fixture now enum-checks the flag (off|experimental|on).

## v2.53.0 (2026-07-30) — Flow orchestrator mode (D62/ADR-029)

- Flag-gated Work-Atom dispatch for core:flow deep mode (feature_flags.flow_orchestrator_mode, default off); return-contract schema + validator bin/validate-return-contract.sh.
- Matcher v0 (ADR-026) via bin/workflow-type-match.sh + factors v0 (B8) via bin/flow-factors.sh + redacting flow ledger bin/flow-ledger-append.sh.
- 8-fixture suite tests/flow-orchestrator/ wired into run-all.sh.

## v2.52.1 (2026-07-30) — Core Plugin repository complete + minimal L3 summaries

- Core Plugin subtree is now the full grounded repository: 26 families covering all 194 plugin files (89 hooks, 26 skills, 16 libs, 10 commands, 5 bin, 42 tests + hook-nested strays), each family with an inclusion rule, file enumeration, and a minted charter. Coverage asserted by script: 0 unmapped, 0 double-mapped; idempotent re-seed.
- L3 summary cards clamp their text before file enumerations (~160 chars) — details stay on the domain's own page, per the 3-layer contract.

## v2.52.0 (2026-07-30) — exactly 3 levels of D per page (consistency layer)

- Every zoom page now shows exactly 3 layers from one shared template: L1 page domain (summary + charters + diagram), L2 children (full blocks + charters + diagram), L3 grandchildren (summary-only clickable cards — details never inline on the first page; clicking repeats the same template one level down).
- Codex ADVISORY folds: whole L3 card clickable; "open > N inside" only when N > 0; leaf empty state kept; left nav sticky + minimal — grandchild groups collapsed unless page has <= 6 grandchildren.

## v2.51.2 (2026-07-30) — zoom-site contract in SKILL.md + privacy parity (codex folds)

- SKILL.md publish contract: zoom site is the default publish shape; flat page only on explicit ask; exact 3-descendant-level window; ref filenames documented as unique/filename-safe by construction.
- build_site honors public_names_withheld like the flat renderer: hidden descendants get NO pages, withheld notes render, links stay unbroken (verified: flag on Core Plugin -> 27 pages, 0 leaks, 0 broken).

## v2.51.1 (2026-07-30) — zoom pages keep every standing page feature

- Regression fix: first zoom cut dropped the left-hand index, search, and per-level diagrams. Every zoom page now carries the full page anatomy — sticky left index (clickable, counts, collapsible), search box, an org diagram at EVERY cascading level in the window, dotted blocks, descriptions, all charters — plus breadcrumbs, up-link, and open-links at the window edge.

## v2.51.0 (2026-07-30) — drill-down zoom pages + Core Plugin detailed out

- Site mode (`domains_page.py --site`): one minimal page PER domain, rooted at itself, 3-level window, breadcrumbs up, click-to-zoom down (Native IA principle 4). Filenames = stable refs, so links survive restructure. Text is on-demand by construction — each page carries only its window.
- Core Plugin detailed to 3 levels from the real repo (Governance Hooks -> Placement Gates / Per-Turn Floors; Skills Catalog -> Review Lanes / Domains Module; Engine Library -> Placement Engine / Page Generators; Commands & Tests), a charter per node. 37 zoom pages, 0 broken links.

## v2.50.0 (2026-07-30) — ledger close: on-touch minting, post-close, file ACKs, search

- `placement-touch.sh` (PostToolUse): every edited file gets a DURABLE placement — backfill/mint on first touch, post-close supersede when evidence moves. Fresh machines populate the tree by working; no manual scan.
- File-based one-shot overrides (`.claude/placement-ack`, consumed on use) replace the unreachable env ACKs in both placement gates; printed messages now show the hatch that works.
- loop-budget-guard (holding L1): budget keyed per agent identity when visible — workflow subagents stop inheriting the parent session's spent budget (verify before promotion).
- Search everywhere: engine `search <terms>` (names, descriptions, charters, ranked) + live search box on the published page (filters sections, blocks, and the index).

## v2.49.0 (2026-07-30) — grounding rungs 4+5, multi-charter, recursive cascade

- Rung 4 `context-scope-audit.sh` (PostToolUse): cross-charter file reach is audit-logged per canon Q28 — never blocked.
- Rung 5 `placement-lint.sh` (Stop, advisory) + engine `lint`: checks the placement is TRUE (refs resolve, origin legal, engine-written) — separate from the gate by dual-lane decision; first run flagged a real hand-written marker.
- Multi-charter domains: `pick_charter()` selects by evidence overlap (deterministic tie-break); page renders ALL charters per domain.
- Domains page v3: recursive cascade at ANY depth — collapsible left index with guide lines, an org-chart diagram at every level, description+charter blocks nesting all the way down (4-level fixture proven).

## v2.48.0 (2026-07-30) — core:domains fleet feature + grounding v1

- Terminology locked: internally DOMAINS always; "departments" is a user-facing synonym. Skill renamed core:domains.
- Fleet page generator `lib/domains_page.py`: per-company GitHub Pages publication with charters per domain, design system carried by D0 (`design` tokens, detected from the company's own site; Sutra's warm cream/amber seeded from website/index.html). URL remembered on D0 (`page_url`); subsequent asks answer with the URL. Client edits = registry edits + regenerate; never hand-edit the page.
- Grounding v1: placement-resolve now injects the resolved domain's CHARTER (title + promise) into every turn's context — work is framed by its charter, not just tagged.

## v2.47.2 (2026-07-30) — departments v2: standardized two-depth layout

- Module contract standardized: left index, one-line description per department (from registry `description` fields — 25 added), two levels of depth. Web surface generated by `website/generate-departments.py`; entity-code render bug fixed.

## v2.47.1 (2026-07-30) — core:departments module

- New skill `core:departments`: on-demand MECE department view. "Show/give me the (various|relevant) departments" -> whole-tree weight view, boxes two-across; "departments around <thing>" -> YOU-ARE-HERE neighborhood. Engine supplies every number; the model only draws. LLM-rendered v1 by founder decision (ship fast); deterministic `orgchart` renderer recorded as the v2 hardening path.

## v2.47.0 (2026-07-30) — dual-lane review complete: codex folds

- Codex F7.1 exhaustive review (CHANGES-REQUIRED): 11 findings folded. Key: unresolved prompt-turns now write an engine marker so HARD mode can never block on "engine found no match" (I-P3); write_placement hard-rejects non-resolving refs (I-P2) and runs under flock (I-P5); restructure is locked, MOVE rejects cycles, DELETE re-parents children; `python3 -c`/`node -e`/`make`/`rsync`/`tar -x`/`npm run` now gate as mutations; promotion counts SOURCE=engine markers only — hand-written compliance no longer earns HARD.
- One documented dual-lane disagreement retained (presence-only gate; deepseek advised against parsing). Reconciliation: `.enforcement/codex-reviews/2026-07-30-adr028-f72-reconciliation.md`.
- `tests/placement-eval.sh` — measured precision: 55% utterance-only top-1 (20 hand-labelled cases), 0 wrong (misses abstain); 200/200 path-evidence consistency.
- 57 unit assertions green post-folds.

## v2.46.0 (2026-07-30) — the last mile: the block is engine output

- `hooks/placement-resolve.sh` (UserPromptSubmit) runs the engine and hands the model the exact line to emit. The PLACEMENT block is no longer composed from imagination.
- READ-ONLY at prompt time: utterance-only evidence never mints. Minting a domain per novel phrasing would shred the tree in a day.
- Fixed two P1s found by dogfooding, not by tests: confidence was `best/total`, which returns 1.0 whenever one domain scores at all (the floor could never fire, I-P9 was dead code); and adjacency compared absolute vs relative paths as strings, so the strongest signal silently never fired.
- Confidence floor set from measurement (OQ-028-2): 0.45. Path evidence lands 0.70-0.99; a lone shared word lands 0.40 and now floor-holds at the ancestor.
- `tests/placement-demo.sh` — visual end-to-end demo of every surface.
- 84 assertions green.

## v2.45.0 (2026-07-29) — the placement engine: addresses are now computed

- `lib/placement_engine.py` — registry (domains/charters/placements), deterministic classifier, restructure ops, MECE report, bulk discovery scan.
- Addresses are COMPUTED and PERSISTED. Until now the block was hand-written text with nothing behind it.
- deepseek P1 folds: flock(2) not O_EXCL (a crashed agent can no longer wedge minting); append-only INDEX + CURRENT read tail-first; per-process seq nonce so identical re-placements cannot collide; adjacency weighted 10x above lexical overlap.
- Verified: MOVE re-mints 0 placement rows; 12 racing minters produce exactly 1 domain; scan of 323 real files derived a 46-node nested tree in 0.7s.
- Tests: 19 engine assertions + 38 gate/renderer + 27 simulation = 84 green.

## v2.44.1 (2026-07-29) — placement wiring + Stop floor

- `per-turn-discipline-prompt.sh` now emits PLACEMENT as block 6, reading the repo's live enforcement mode.
- `reset-turn-markers.sh` clears `placement-registered` each turn (own marker only; a peer session's is preserved).
- New `placement-stop-check.sh` closes the no-tool-turn hole; loop-guarded on `stop_hook_active`.
- Simulation: 27 end-to-end assertions across 8 lifecycle scenarios, all passing.

## v2.44.0 (2026-07-29) — placement: every unit of work gets an address

- ADR-028 lands in the plugin: new `per_turn_blocks.placement` (required, fleet-wide) — one Domain + one Charter stamped before work runs.
- Ships in **WARN** mode. `placement-gate.sh` logs and exits 0; auto-promotes to HARD after 50 compliant turns per repo. A new HARD gate on day zero would have deadlocked every install.
- COMPACT one-line render is the default shape; the ancestor tree renders only when a Domain or Charter was minted.
- Bash-mutation classifier is explicit (redirection checked before the read-only allowlist); repo-local kill-switch `.claude/placement-disabled`.
- Tests: `tests/unit/placement.test.sh` — 38 assertions, renderer + gate + classifier.

## v2.41.2 (2026-07-27) — marker reconciliation: scheme A wins, guards restored

- **Scheme B deleted.** `.claude/<name>-<sid>` flat-suffix removed from flow-gate / flow-stop-check / per-turn-discipline-prompt. `marker-lib` (`.claude/sessions/<sid>/<name>`) is the single marker authority.
- **Four guards restored** in `reset-turn-markers.sh`, dropped by the P1 rewrite (90→17 lines): empty-prompt, synthetic-turn, 3s burst, forensics. Without them every system-reminder wiped markers mid-turn — for single-session users too.
- **Adoption bridge**: `sutra_marker_has` adopts a legacy global into the session dir so reader/writer migration is order-independent and no stale install is bricked. Bounded — `sutra_marker_reset` now deletes the global twin, so an adopted marker cannot survive its turn.
- **Legacy clear is ownership-aware**: a peer session's stamped global marker is no longer deleted by another session's reset.
- **RETURN-trap bug fixed** in `lib/h-sutra-classify-and-write.sh`: the trap referenced a `local` var and fired on every later `source`, killing the caller under `set -u`.
- **Fail-open hardened**: every `marker-lib` source is guarded; a broken lib degrades the gate instead of failing the user's turn.

## v2.41.0 (2026-07-27) — Flow fires by construction

- **Root cause**: `per-turn-discipline-prompt.sh` wrote the whole per-turn contract to **stderr**. For UserPromptSubmit only **stdout** reaches the model, so the contract (incl. FLOW activation) never arrived. Now emitted as `hookSpecificOutput.additionalContext`.
- **Flow now fires hook-side**: the classifier already runs every turn; it now writes `.claude/flow-classified-<session>` itself. Model no longer has to remember.
- **Markers are session-scoped**: concurrent sessions in one repo were deleting each other's markers, causing spurious hard blocks. `reset-turn-markers.sh` now clears only its own session's.
- **`flow-gate-pass` logged**: the ledger recorded only failures, so fire-rate was unmeasurable. Passes now logged.
- **Bootstrap deadlock fixed**: `depth-marker-pretool.sh` no longer gates writes to the per-turn markers themselves (scoped list, not blanket `.claude/*`).

## v2.43.1 (2026-07-28) — guard-regression test

- **`hooks/reset-guard-test.sh`**: fails if the per-turn marker reset guards are deleted or weakened. Asserts synthetic-turn / empty-prompt / burst preservation, a control that a real prompt still clears, and fail-open when `marker-lib` is broken.
- Proven by negative control: GREEN on this build, RED (exit 1) on a reconstructed guard-less `reset-turn-markers.sh` — the refactor that collapsed it 90→17 lines and would have wiped markers on every system-reminder.

## v2.43.0 — 2026-07-28

**REMOVED — H-Sutra header Stop enforcement.**

- `hooks/h-sutra-enforce.sh` **deleted**; its `hooks.json` Stop registration removed. No block, no warning, no forced redo for a missing or malformed header, on any profile.
- **Survives:** the header as a convention (`/core:start` docs, `per-turn-discipline-prompt.sh` per-turn ask, `core:human-sutra` skill) and the 9-cell classification log rail — that rail is written by `per-turn-discipline-prompt.sh`, not by the deleted hook.
- **Dies with it:** `.enforcement/h-sutra-audit.jsonl` enforcement telemetry; the `SUTRA_HSUTRA_ENFORCE_DISABLED=1` and `~/.h-sutra-enforce-disabled` kill-switches (now inert).
- **Still HARD at Stop:** `per-turn-hard-gate.sh` (Input Routing, Depth, BLUEPRINT on mutating turns), `flow-stop-check.sh` (Flow, `profile=company`).
- `sutra-defaults.json`: `per_turn_blocks.human_sutra_header.enforcement = "convention_only"`. `/core:start` template no longer claims hard enforcement — re-run `/core:start` after updating.
- Stale comments in `per-turn-hard-gate.sh`, `flow-stop-check.sh` and `blueprint-check.sh` that referenced the deleted hook were corrected rather than left pointing at a missing file.

## v2.42.0 — 2026-07-28

**Text-first BLUEPRINT gate (#81) + profile-honoring Stop layers (#72).**

- **`blueprint-check.sh` v3 reads the emitted block, not a marker.** The gate had only ever read `.claude/blueprint-registered` while the contract said "emit the block" — so a correct, complete BLUEPRINT in the response could be HARD-blocked, and re-emitting it could never help. Cause of #68, the 2026-07-08 Testlify incident (which taught a Bash + `BLUEPRINT_ACK` bypass) and its 2026-07-27 repeat. v3 validates the block in the turn's response text; the marker is demoted to a per-turn cache the hook writes for itself. Validator ported from #73 with credit, plus parsing fixes for the canonical bulleted shape (`- Doing:`) and single-line `Steps: 1) … 2) …`.
- **PreToolUse scope narrows to foundational paths**, restoring the codex round-5 scoping the 2026-05-10 blanket SOFT→HARD flip erased. Ordinary files are floored at Stop by a new BLUEPRINT arm in `per-turn-hard-gate.sh`, armed only on turns that mutated a governed file (one redo, loop-safe). Supersedes #78's depth gate.
- **Foundational globs become configuration** — `per_turn_blocks.blueprint.foundational_paths` in `sutra-defaults.json`, overridable per repo via `blueprint_foundational_paths[]` in `.claude/sutra-project.json`. They were hardcoded to the Asawa repo layout, so on every other install the set was silently empty.
- **`h-sutra-enforce.sh` v8/v9 + `flow-stop-check.sh` honor `.profile`.** Case-insensitive `DIRECTION·VERB`; forced redo only at `profile=company`, warn + log otherwise. Fail-open: no config or no `jq` → warn.
- **Catalog drift fixed** — `marketplace.json` said 2.39.20 while source said 2.41.2. Both now 2.42.0; `test-validate-manifest-json.sh` green.
- Kill-switches unchanged: `BLUEPRINT_DISABLED=1` / `~/.blueprint-disabled`, `SUTRA_HSUTRA_ENFORCE_DISABLED=1` / `~/.h-sutra-enforce-disabled`, `PER_TURN_HARD_DISABLED=1` / `~/.per-turn-hard-disabled`.
- Pre-existing red suites carried unchanged from the parent commit: `test-codex-directive-detect.sh`, `test-codex-directive-gate.sh`.

## v2.40.0 — 2026-07-20

**D63 — per-turn governance stack goes HARD, fleet-wide.** The soft-nudge blocks (Flow / BLUEPRINT / H-Sutra / Structure-First) become contract + hook enforced. New `per-turn-hard-gate.sh` (Stop, transcript-inspecting, loop-safe) floors Input Routing + Depth on no-tool turns; new `codex-consult-gate.sh` (Depth ≥ 3 Edit/Write) degrades to pass without the codex binary; new `codex-consult-marker.sh` (PostToolUse) writes its satisfying marker on a real consult.
- **Contract + enforcement activate together:** `/core:start` template expanded 4 → 9 blocks; both new hooks stay silent until `/core:start` has written the contract (`sutra-project.json` gate) — no ambush of un-onboarded users.
- **Codex challenge (CHANGES-REQUIRED) folded:** fresh-install gate, line-anchored grep (defeats the token-mention spoof), the marker writer, honest ACK message, de-stickied `codex-unavailable`.
- Kill: `PER_TURN_HARD_DISABLED=1` / `CODEX_CONSULT_DISABLED=1` (+ `~/.` files). Founder direction D63, 2026-07-20.

## v2.39.16 — 2026-06-15

**D61 amendment — Flow fires via the INLINE block, not a Skill invocation.** The v2.39.14 contract ("invoke `core:flow` every turn") could not hold: no Claude Code hook can force a Skill on the first pass, so on no-tool turns the model skipped it. Flow now fires the way Input Routing fires — an INLINE FLOW block (literal text the model emits) on every input + markers written via the Write tool. The full `core:flow` Skill is the DEEP mode (substantive / multi-step / ambiguous work only).
- **Marker-persistence fix:** marker writes must use the Write tool — Claude Code rolls back sandboxed Bash writes to `.claude/`, which made `flow-gate` / `flow-stop-check` read stale state (block a classified mutation / force a spurious redo). SKILL.md + sutra-defaults now mandate it.
- Floors unchanged: `flow-gate.sh` (mutations) + `flow-stop-check.sh` (no-tool turns), HARD fleet-wide. `emission_mode` → `inline_block_every_turn_plus_skill_for_substantive`.
- True "fires by construction" (model cannot skip) requires the spine as CODE outside the model — the Native engine. Deferred. Founder direction D61 amendment, 2026-06-15.

## v2.39.15 — 2026-06-14

**D61 floor — `flow-stop-check.sh` (Stop event).** Forces a redo when `core:flow` did not fire on a turn (no `.claude/flow-classified` marker). This floors pure no-tool turns (a one-line answer, yes/no, chitchat) that PreToolUse gates cannot reach. HARD, fleet-wide (founder direction).
- **Loop-safe:** honors `stop_hook_active` — the first miss blocks (one forced redo); the re-invoked turn passes. A client can NEVER infinite-loop, even if a marker write fails. Net: every miss gets exactly one redo, then proceeds.
- Together with `flow-gate.sh` (floors mutations) this completes "Flow fires on EVERY input." Kill-switches shared: `FLOW_ACK=1` / `FLOW_DISABLED=1` / `~/.flow-disabled`.
- Founder direction D61, 2026-06-14 ("HARD fleet-wide now").

## v2.39.14 — 2026-06-14

**D61 — Flow FIRES full-manner on EVERY input.** `core:flow` now fires on every input — the complete six-stage spine, every TYPE — the way Input Routing / the H-Sutra header fire every turn. The firing is universal; it is NOT a downstream tool gate.
- Firing mechanism: `per-turn-discipline-prompt.sh` (UserPromptSubmit) now invokes the full `core:flow` Skill every turn; `sutra-defaults.json .per_turn_blocks.flow` emission_mode → `skill_invocation_always`. The v2.39.13 literal-text fast-path (trivial-turn collapse) is REMOVED — every input pays the full spine.
- `flow-gate.sh` stays a mutation backstop only (Edit/Write + Task/Agent). The brief WebSearch/WebFetch gating is REVERTED — gating is not how Flow fires (founder: "it is not web search gating; it is flow that should be fired").
- Cost optimization (cheaper head for trivial turns) explicitly DEFERRED by founder ("optimizations can be done later"). Kill-switches unchanged (`FLOW_ACK=1` / `FLOW_DISABLED=1` / `~/.flow-disabled`).
- Founder direction D61, 2026-06-14.

## v2.39.12 — 2026-06-14

**Flow gate HARD, fleet-wide.** `flow-gate.sh` now exits 2 (blocks) when an Edit/Write to a non-whitelisted path, or a Task/Agent dispatch, skipped `core:flow` classify+resolve — same enforcement shape as `input-classification-gate.sh` + `depth-marker-pretool.sh`.
- Escape hatches: `FLOW_ACK=1 FLOW_ACK_REASON='<why>'` (audit-logged), `FLOW_DISABLED=1`, `touch ~/.flow-disabled`.
- `reset-turn-markers.sh` now wipes `flow-classified/inner/type-resolved/closed` per-turn — fixes stale markers from a prior session silently satisfying the gate.
- Founder direction 2026-06-14; risk (heavier skill than a routing block) accepted over the company-profile-gated alternative.

## v2.39.11 — 2026-06-14

**Flow on EVERY input + fast-path; gate widened to Task/Agent.**

- `per_turn_blocks.flow.applies_to_turn_types` = all 5 types; Flow activates every turn (structure universality, D45).
- Cost-proportional: trivial input -> 1-step fast-path (classify->answer, Mode-1 atom); only substantive pays the full spine.
- `flow-gate.sh` widened to fire on Task/Agent dispatch (not just Edit/Write) — fixes the workflow/subagent gap.

## v2.39.10 — 2026-06-14

**Flow auto-activation — `core:flow` now fires per turn, gated by the classified TYPE.**

- Added `per_turn_blocks.flow` to `sutra-defaults.json` (the canonical per-turn surface); `per-turn-discipline-prompt.sh` now emits a FLOW-activation reminder every turn.
- After Input Routing + H-Sutra classify the TYPE, work-bearing turns (task / direction / new_concept, substantive question/feedback) invoke `core:flow`; trivial/conversational/read-only turns skip.
- SOFT (reminder + `flow-gate.sh` backstop). Kill-switch: `~/.per-turn-discipline-disabled`.

## v2.39.9 — 2026-06-14

**The Flow — end-to-end work-resolution spine, shipped as skills + a soft gate.**

- New skills: `core:flow` (orchestrator: classify -> resolve workflow type -> follow/construct -> inner-engine-on-every-step -> run atom -> close), `core:workflow-type-resolve` (FOLLOW vs CONSTRUCT, child->platform), `core:lens` (value<->axis generic engine), `core:cynefin` (certainty gate).
- New hook `flow-gate.sh` (PreToolUse, **SOFT** — always exit 0): nudges + logs when construct work skips the flow markers. HARD promotion (company profile) documented, not enabled. Test: 25/25 incl. never-exit-2.
- Canon: ADR-026 (guidance-first resolution) + ADR-027 (value<->axis single primitive).

## v2.39.7 — 2026-06-11

**`h-sutra-enforce` hook (v6) — stop false-firing on Skill-invoking turns.**

- `is_human_user()` now returns False for `isMeta:true` user rows. Skill invocations and stop-hook feedback are recorded as `role:user`/`isMeta:true` (no `promptSource`) — not human turns.
- v4/v5 counted them as human, so any turn invoking a Skill reset the turn boundary to the skill-injection row and checked the assistant's post-skill narration (no header) → spurious block.
- Reproduced + verified against a live transcript prefix: v5 blocks, v6 passes on the real header row.

## v2.39.6 — 2026-05-31

**Prompt-capture hook (UserPromptSubmit) — fleet L0.**

- New `hooks/capture-prompt.sh` appends every founder prompt as JSONL to the project's `holding/state/prompts/<YYYY-MM>.jsonl` (schema: ts, session_id, prompt).
- Lossless, non-blocking; kill via env `PROMPT_CAPTURE_DISABLED=1` or `~/.prompt-capture-disabled`. No network.
- Registered in `hooks/hooks.json` UserPromptSubmit after `per-turn-discipline-prompt.sh`.
- Promoted from Asawa-local L1 (was at `holding/hooks/capture-prompt.sh`); Asawa L1 copy retired same day.

## v2.39.5 — 2026-05-28

**`h-sutra-enforce` hook — actionable error on mis-cased headers.**

- Block branch now splits MALFORMED (bracket+middot but fails strict match — almost always Title-case/lowercase DIRECTION·VERB) from MISSING (no header).
- Malformed → "DIRECTION·VERB must be UPPERCASE" + canonical example. Was misreporting these as "header missing".
- Pass/block logic for valid headers unchanged (regression-tested). Audit + violations logs gain `reason_code`.

## v2.39.4 — 2026-05-13

**`prd-discipline` skill v2** — REFACTOR pass per superpowers:writing-skills TDD discipline.

- TDD baseline subagent at `.enforcement/skill-tests/2026-05-13-prd-discipline-baseline.md` wrote a Senior Expert Layer-B PRD WITHOUT loading the skill. Captured 5 named rationalizations.
- v2 plugs all 5: §1 +namespace-collision check + naming-with-alternatives · §3 +scale-undershoot surface · §4 +canon-typed-entity rule · §5 +TODO-is-not-an-alibi.
- 4 new rationalization rows + sharpened red flags + v2 testing-trail section.

## v2.39.3 — 2026-05-13

**Add `prd-discipline` skill** — product-document writing discipline.

- New skill at `skills/prd-discipline/SKILL.md` codifies 5 invariants: STRUCTURED · VISUAL FIRST · RESTRUCTURE-ON-BULK (D55 4-step) · CONNECTED (anchor cross-ref discipline) · GAP-SURFACING (TODO/Q markers, never fabricate).
- Composes with ADR-020 Layer-B Product Authoring Template (ADR-020 = WHAT sections; this skill = HOW to write/maintain them).
- Authored from R1-R11 Native PRD review evidence (codex+deepseek verdicts 2026-05-12 to 2026-05-13). Formal subagent TDD baseline pass queued as follow-up.

## v2.39.2 — 2026-05-13

**Remove 15-min hard cap on `codex-sutra` + `deepseek` skills** (founder D2026-05-13).

- `skills/codex-sutra/SKILL.md`: 900-s wrapper kill removed; replaced with SIGINT trap (founder Ctrl-C → SIGTERM/SIGKILL to whole process group). Heartbeat now fires every 10 min instead of one-shot at 10 min. Stall warn unchanged (5 min no-progress).
- `skills/deepseek/SKILL.md`: same poll-loop change. `curl --max-time 900` flag removed; DeepSeek API server-side timeout is the only network bound.
- `sutra-defaults.json`: `deepseek.limits.wall_seconds_hard_cap` set to `null`; `progress_warn_seconds` renamed to `heartbeat_interval_seconds`.
- Fail-closed tables: `Hard-cap timeout / reason=timeout / exit 124` rows replaced by `Founder interrupt (Ctrl-C) / reason=interrupted / exit 130`.
- Native canon refs updated: `sutra/os/native/impl-phases/phase-D-codex-review.md` + `sutra/os/native/hardstops/HS-7-codex-queue-stale.md` carry an amendment line — HS-7 itself is unchanged (it watches review-backlog health, not per-call duration).

Rationale: long-reasoning runs (`high`/`xhigh` effort on large diffs or design docs) were being killed before completion. Without a cap, founder retains the interrupt path via Ctrl-C; the wrapper still surfaces stall + heartbeat so silent hangs remain observable.

## v2.39.1 — 2026-05-13

**Cache-invalidating patch over v2.39.0.** Same content; version field was the only thing missing to propagate the housekeeping fixes (concise plugin.json description, /core:update reload reminder).

Lesson: any content change in a release artifact requires a patch-bump even without a feature change — marketplace cache keys on version, not content hash.

## v2.39.0 — 2026-05-13

**Anti-glaze-tone skill** — brutally honest, no-flattery register for founder↔Claude sessions.

- New skill at `marketplace/plugin/skills/anti-glaze-tone/SKILL.md`.
- 16 rules adopted (verify own work, lead with counterargument, banned glaze phrases, confidence levels, accuracy > approval). 5 rejected (preserves Founding Doctrine P0 + D51 caveman).
- Asawa+Sutra: auto-active via CLAUDE.md (commits `25a728b`, `76fdcd9`). T2/T3/T4 fleet: opt-in.
- Plugin description field collapsed from ~14KB accumulated narrative to ~227 chars; CURRENT-VERSION.md trimmed from 797 → 12 lines.
- `/core:update` now prints a `/reload-plugins` reminder.

Source: @aiedge_ Anti-Glaze System Prompt. Founder-approved composition 2026-05-12.

## v2.36.0 — 2026-05-12

**3-Layer Verification Stack + V2.2 L1 hook enforcement** (founder-direction trajectory across one session).

### Direction trajectory

- **"convert them into hard hooks"** — 6 SOFT hooks flipped HARD: `blueprint-check.sh` (was SOFT advisory on non-foundational), `input-classification-gate.sh` (HARD + marker contract bug fix — was reading `/tmp/asawa-input-classified-${SESSION_ID}` with no writer; now reads `.claude/input-routed`), `depth-marker-pretool.sh` (via `profile=company`), 4 Stop-hook `|| true` wrappers removed from `.claude/settings.json`. `reset-turn-markers.sh` now also wipes `.claude/blueprint-registered` (lifecycle gap closed). `operationalization-check` enabled in `asawa-holding/os/SUTRA-CONFIG.md`.
- **"all three (layered)"** — L1 BLUEPRINT per-step Verify (skill V2.1 block format with inline `Verify:` per Step) + L2 `PHASE-EXIT-VERIFY` method-registry row (convention only, no hook) + L3 `VERIFY-*` family (existing, convention only). 3-Layer Verification Stack documented in `BLUEPRINT-ENGINE.md` + `skills/workflow/SKILL.md` + `CLAUDE.md`.
- **"force it"** — V2.2 hook enforcement. `blueprint-check.sh` reads DEPTH from `.claude/depth-registered` and HARD-blocks D3+ Edit/Write when marker lacks `HAS_PER_STEP_VERIFY=1`.

### Codex review arc (4 rounds, final PASS)

| Round | Verdict | Action |
|---|---|---|
| R1 | CHANGES-REQUIRED (2P1+2P2) | Folded P2.1 (doc coherence) + P2.2 (L2 enforcement-status honesty) + partial P1.1 (depth-parse fail-closed). Accepted P1.2 (fleet hard-stop) as intentional forcing function. |
| R2 | CHANGES-REQUIRED (1P1) | R1 regex `^DEPTH=[0-9]+` still parsed `DEPTH=3garbage` as `3`. Folded with whitespace-boundary `^DEPTH=[0-9]+([[:space:]]|$)`. |
| R3 | CHANGES-REQUIRED (1P1) | R2 boundary still parsed `DEPTH=3 junk`, `DEPTH=3<TAB>garbage`, `DEPTH=3 TASK=`. Folded with strict 2-regex full-line shape validation. |
| **R4** | **PASS** (0 findings) | "Both accepted shapes fully anchored. Old boundary-only acceptance problem is gone." |

### Final hook regex (V2.2 R3-fold)

```bash
# Form A — canonical 3-token single-line per CLAUDE.md marker spec
grep -E '^DEPTH=[0-9]+[[:space:]]+TASK=[^[:space:]]+[[:space:]]+TS=[0-9]+$'
# Form B — multi-line 1-token fallback
grep -E '^DEPTH=[0-9]+$'
# Anything else → DEPTH empty → integer-shape check → D5 fail-closed → block
```

12-scenario smoke test all PASS (4 fail-closed cases + 4 canonical/multi-line accepts + 4 regression).

### Breaking change

Every D3+ Edit/Write across fleet HARD-blocks unless `.claude/blueprint-registered` carries `HAS_PER_STEP_VERIFY=1` + valid `DEPTH=N` marker. Recovery is 1 tool-call cycle (error message shows fix). Bootstrap pattern documented in memory: write markers via Bash before first Edit/Write of every turn — `depth-marker-pretool.sh` only matches `Edit|Write` tools, not `Bash`.

### Deferred

- L2 (`PHASE-EXIT-VERIFY`) hook enforcement — requires text-scan of model response (different architecture from marker-check), not in scope.
- L3 (`VERIFY-*`) hook enforcement — task-shape dependent, stays convention-only.
- 5 charter/engine/protocol files lacking `## Operationalization` section (HUMAN-SUTRA-LAYER, SUTRA-ENGINE, HUMAN-SUTRA-ENGINE, NATIVE-ENGINE, PROTOCOLS) — backfill is a separate project.

### Files changed

Sutra: `marketplace/plugin/hooks/{blueprint-check,input-classification-gate,reset-turn-markers}.sh`, `marketplace/plugin/skills/blueprint/SKILL.md`, `marketplace/plugin/skills/workflow/SKILL.md`, `os/engines/BLUEPRINT-ENGINE.md`, `os/engines/method-registry.jsonl`, `.claude-plugin/plugin.json`, `CURRENT-VERSION.md`, `CHANGELOG.md`.
Asawa: `.claude/settings.json`, `.claude/sutra-project.json`, `os/SUTRA-CONFIG.md`, `CLAUDE.md`, `sutra/` submodule pointer.

## v2.35.3 — 2026-05-09

**Layer-2 bug fix on the same hook: `reset-turn-markers.sh` stdin handling. v2.35.2 fixed event registration; v2.35.3 fixes the stdin double-read that still made every real turn skip.**

### What v2.35.2 fixed (recap)

v2.35.2 moved registration from `Stop` → `UserPromptSubmit`. Correct event.

### What v2.35.2 missed

Even on the correct event, the script's first executable line:

```bash
PROMPT=$(jq -r '.prompt // empty' 2>/dev/null)
```

`jq` reads stdin inside the `$(...)` substitution. Under Claude Code's actual `UserPromptSubmit` payload shape, this returned EMPTY for `.prompt` on real founder turns. So every real turn STILL hit the synthetic-skip branch (`case "$PROMPT" in "")`) and never reached the `rm -f` block.

### Evidence (forensic)

`grep -E "markers-cleared|reset-skipped" routing-misses.log` showed ALL recent UserPromptSubmit hits logged `reset-skipped-empty-prompt` — zero `markers-cleared`. Same pathology as the v2.35.2 bug target, different cause.

Founder live diagnostic (2026-05-09):
- `.claude/structure-first-active` marker mtime 3+ minutes old (carried across turns)
- All recent routing-misses.log entries: `reset-skipped-empty-prompt`
- Root cause: `jq` consumed stdin in `$(...)`; under Claude Code's actual payload format, returned empty

### The fix

Capture stdin once into a variable, parse from variable:

```bash
STDIN_RAW="$(cat 2>/dev/null)"
PROMPT=$(printf '%s' "$STDIN_RAW" | jq -r '.prompt // empty' 2>/dev/null)
```

Plus instrumentation — on every skip-empty event, log `stdin_bytes` + first-200-char head so future regressions are observable.

### Verification

| Gate | Result |
|---|---|
| `bash -n reset-turn-markers.sh` | PASS |
| `echo '{"prompt":"hi"}' \| bash reset-turn-markers.sh` → marker removed | PASS |
| `echo '' \| bash reset-turn-markers.sh` → logs `{stdin_bytes:0,stdin_head:""}` | PASS |
| Live UserPromptSubmit during release session → `markers-cleared` event in routing-misses.log | PASS (observed) |

### Versions

`2.35.2` → `2.35.3` (`.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` + `hooks/reset-turn-markers.sh`).

### D55 status

D55 `structure-first-reminder.sh` dedupe-per-turn semantics now functional fleet-wide. Per-turn marker reset works as documented in CLAUDE.md Marker Lifecycle.

---

## v2.35.2 — 2026-05-09

**Major bug fix: `reset-turn-markers.sh` registration moved Stop → UserPromptSubmit. Per-turn marker discipline was silently broken fleet-wide; ALL per-turn markers persisted entire sessions instead of clearing per turn.**

### The bug

`hooks/hooks.json` registered `reset-turn-markers.sh` on the **Stop** event. The script body, however, was designed for **UserPromptSubmit** — its first executable line is:

```bash
PROMPT=$(jq -r '.prompt // empty' 2>/dev/null)
```

`.prompt` only exists in `UserPromptSubmit` event stdin. `Stop` event stdin has `.stop_hook_active`, `.session_id`, etc. — but **no `.prompt` field**. So every Stop fire returned empty PROMPT, fell into the case branch that treats empty prompt as a "synthetic turn", logged `reset-skipped-empty-prompt`, and exited without clearing any markers.

### Impact

| Marker | Wiped between turns? |
|---|---|
| `.claude/depth-registered` | NO (was supposed to per CLAUDE.md Marker Lifecycle) |
| `.claude/input-routed` | NO |
| `.claude/build-layer-registered` | NO |
| `.claude/sutra-deploy-depth5` | NO |
| `.claude/depth-assessed` | NO |
| `.claude/structure-first-active` (new in v2.35.0) | NO |

Result: any hook that dedupes via per-turn markers (including the new D55 `structure-first-reminder`) emitted ONCE per session instead of once per turn. `per-turn-discipline-prompt.sh` may have been similarly affected for its dedupe logic.

### Evidence — routing-misses.log forensic

A representative sample from `holding/state/.../routing-misses.log` shows hundreds of `reset-skipped-empty-prompt` events and **zero** `markers-cleared` events. The script ran every turn but never did its job.

### The fix

`hooks/hooks.json` — `reset-turn-markers.sh` moved from `Stop[0].hooks[0]` to `UserPromptSubmit[0].hooks[0]` (placed FIRST in the UserPromptSubmit chain so subsequent hooks see fresh marker state).

Why first: `per-turn-discipline-prompt.sh` and other UserPromptSubmit hooks may read or assume specific marker state. The reset must precede them.

### Why this matches the script's design

- Script header comment: `"UserPromptSubmit hook — clears per-turn routing/depth markers..."`
- Script body: synthetic-turn case patterns (`*"<system-reminder>"*`, `*"<local-command-caveat>"*`, `*"READ-BEFORE-EDIT REMINDER"*`) are all things that appear in `UserPromptSubmit` prompt content, never in `Stop` stdin
- `holding/CLAUDE.md` Marker Lifecycle section: "Wiped only by `reset-turn-markers.sh` on `UserPromptSubmit`"

All three sources said UserPromptSubmit. Only `hooks.json` said Stop. That's the drift.

### When did this regress

Unknown without git archaeology on hooks.json. Could have been the original registration (bug from day 1) or moved later. Out of scope for this hotfix; surfacing the question here for future blame-driven cleanup.

### Discovery path

Founder relaunched a v2.35.0 session to test D55 visibility. D55 reminder failed to visibly fire. New-session diagnostic traced to `.claude/structure-first-active` marker mtime persisting from prior turn (3+ minutes old). `routing-misses.log` showed `reset-skipped-empty-prompt` was the only event reset-turn-markers had been emitting. Root cause: event-registration mismatch.

### Versions

`2.35.1` → `2.35.2` (`.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` + `hooks/hooks.json`).

### Note on D55 verify state

D55 `structure-first-reminder.sh` install was correct since v2.35.0. v2.35.1 fixed an unrelated permission bug. v2.35.2 now fixes the dedupe-persistence bug that prevented the D55 reminder from being visible across consecutive turns. Real-runtime visibility verification (founder makes tool call in v2.35.2+ session → log row with real fields → reminder visible turn-to-turn) is the final outstanding D55 check.

---

## v2.35.1 — 2026-05-09

**chmod +x fix for `hooks/session-token-snapshot.sh` — pre-existing bug surfaced in v2.35.0 install logs.**

### What changed

`marketplace/plugin/hooks/session-token-snapshot.sh` was tracked at git mode `100644` (non-executable). Every cache install since at least v2.34.0 propagated the non-exec bit. The result: SessionStart hook failed silently (non-blocking) on every session start fleet-wide for weeks — log line `SessionStart:startup hook error / Failed with non-blocking status code: ... Permission denied` appeared but the harness kept going, so nobody noticed until founder relaunched a session into v2.35.0 and read the startup output.

Fix is a one-line `git update-index --chmod=+x marketplace/plugin/hooks/session-token-snapshot.sh` — file now ships at mode `100755`.

### Survey result

`find sutra/marketplace/plugin/hooks -name "*.sh" ! -perm -u+x` returned exactly **1 file** (the one fixed). All other 72 `.sh` files in `hooks/` source are correctly executable. No other ship-stoppers in source `bin/` or `scripts/` either (one stray `.pyc` in `scripts/__pycache__/` — gitignore territory, not a release blocker).

### Why a patch bump, not a v2.36.0

This is a true bug fix — file mode metadata correction, no functional code changes, no API/behavior change. Patch semantics apply.

### Note: D55 still pending real-runtime verification

D55 `structure-first-reminder.sh` is correctly installed in v2.35.0 cache (registered in `hooks/hooks.json` PreToolUse[0], file mode `100755`). At time of writing, the new session that picked up v2.35.0 had not yet executed any model-side tool calls (only `/doctor` and a user message), so the hook has had no opportunity to fire. v2.35.1 is unrelated to that pending verification — D55 verify is a separate task that completes when the next real tool call in a v2.35.1+ session writes a row to `holding/hooks/hook-log.jsonl` with non-`"unknown"` `tool` + `session` fields.

### Versions

`2.35.0` → `2.35.1` (`.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json`).

---

## v2.35.0 — 2026-05-09

**D55 Structure-First Default + Restructure-on-Add — hard enforcement hook fires on every tool call. Fleet-wide.**

Founder direction 2026-05-09: "Make sure by default there is structuring applied everywhere whenever you go about doing something. And then make sure that when we add new things, you structure the existing things with the new things and see if there are simplifications required. Make this as a hard. This code which has to run on every command."

### What changed

1. **NEW `hooks/structure-first-reminder.sh`** — PreToolUse hook (no matcher = every tool call). Emits two-clause reminder to stderr once per founder turn (dedupe via per-turn marker `.claude/structure-first-active`). Audit-logged to `holding/hooks/hook-log.jsonl`. Fail-open exit 0 (soft guidance per D40 hook-injects-prompt caveat).

2. **`hooks/hooks.json`** — `structure-first-reminder.sh` added to the existing PreToolUse no-matcher block alongside `feedback-auto-override.sh`. Fires before every Read/Edit/Write/Bash/Task/MCP/WebFetch/WebSearch tool call.

3. **`hooks/reset-turn-markers.sh`** — `.claude/structure-first-active` added to the per-turn `rm -f` list so the dedupe marker wipes on every `UserPromptSubmit`, allowing the reminder to re-fire at the start of each new founder turn.

### Two clauses (the D55 direction)

- **Clause 1 — Structure-First Default**: structure is the default shape of every action, not output-time polish. Tables > prose for ≥3 comparable rows. Numbers > adjectives; progress bars for scores. Decisions in ASCII-boxed callouts (no unicode box-drawing). Impact + Effort columns on every task list. Applies action-time, not only at output.

- **Clause 2 — Restructure-on-Add**: adding ANY new thing (file, section, direction, protocol, hook, skill, dep) fires four mandatory steps — **Survey** existing structure the new thing touches → **Reorg** new+existing into one coherent shape → **Simplify** (dedupe, merge, delete redundancy) → **Surface** in turn output what was added/restructured/simplified/deleted.

### Kill-switches

- Per-session: `touch ~/.structure-first-disabled` (or `~/.sutra-defaults-disabled` for all D40+D55 defaults).
- Per-call: `STRUCTURE_FIRST_ACK=1 STRUCTURE_FIRST_ACK_REASON='<why>' <cmd>` — audit-logged.
- Permanent revoke: founder utterance "stop structure-first" / "drop D55" → revert for that session; permanent removal is a follow-up commit.

### Verification gap recognized

The prior source-side commit (`sutra 888b790`, 2026-05-09 earlier) shipped the hook + registration but did NOT bump the plugin version. As a result the runtime plugin cache (`~/.claude/plugins/cache/sutra/core/2.34.0/`) never picked up the hook — PreToolUse fired without it for the rest of that session. Verified-by check in the originating BLUEPRINT covered source-side artifacts (file present, hook registered, smoke test runs) but not runtime-side (real PreToolUse calls the hook). v2.35.0 closes the gap: this version bump triggers a fresh cache pull on `/plugin update sutra@core`. Asawa memory `feedback_verify_before_commit.md` updated to require **runtime test** (new session + real tool call + log inspection) on any hook/skill/plugin ship.

### Asawa-side governance (separate repo)

- `asawa-holding/holding/FOUNDER-DIRECTIONS.md` §D55 — full direction-of-record (entry landed in asawa-holding `104b037`).
- `asawa-holding/CLAUDE.md` Core Behaviors — D55 bullet alongside D51/D52/D53.
- `asawa-holding/sutra/CLAUDE.md` Inherited Governance — D55 section so Sutra sessions load it at startup.
- Memory `feedback_structure_first_d55.md` + `MEMORY.md` row.

### Fleet propagation

T2 (DayFlow/Billu/Paisa/PPR/Maze), T3 (Testlify/Dharmik), T4 fleet receive the hook on next `/plugin update sutra@core` + session restart. Without the version bump in this release, those installs would stay on v2.34.0 forever. D33 client firewall preserved — pull-model distribution, no push.

### Versions

`2.34.0` → `2.35.0` (`.claude-plugin/plugin.json` description + version field). Marketplace registry refresh follows on push.

---

## v2.32.0 — 2026-05-04

**Permission posture realigned to catastrophic-only across Bash/MCP/Web/Task. Closes ~95% of remaining prompt friction; catastrophic floor preserved.**

Founder direction 2026-05-04: "do it" — unify permission posture. Bash already catastrophic-only since v2.6.1; MCP (v2.17) was prompts-on-all-mutations; WebFetch/WebSearch/Task/NotebookEdit had no rule at all (always prompted). Three actors, three different trust postures, same threat model — the asymmetry was legacy from gates being drafted in isolation.

### What changed

1. **`hooks/permission-gate.sh`** — dispatch case-statement now covers `WebFetch`, `WebSearch`, `Task`, `NotebookEdit` in addition to `Bash|Write|Edit|MultiEdit|mcp__.*`. WebFetch/WebSearch route to the new `_match_web()` helper (calls `lib/web_trust_mode.py`); Task auto-approves with `task-auto-approve` decision basis (subagent inherits hooks deterministically per 2026-04-24 empirical verification); NotebookEdit folded into the existing `Write|Edit|MultiEdit` branch and reuses `_match_first_time_edit` (same prompt-list as Edit/Write).

2. **`lib/web_trust_mode.py`** — NEW. Reads PermissionRequest JSON on stdin, classifies the URL, prints `{"prompt": <bool>, ...}`. Auto-approves public http(s) URLs. Prompts on: `localhost`/`ip6-localhost`/`ip6-loopback`, IP addresses that resolve as loopback/private/link-local/multicast/reserved (covers `127.0.0.0/8`, `0.0.0.0`, `::1`, `fc00::/7`, `fe80::/10`, `169.254.0.0/16` cloud metadata, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), and non-http schemes (`file://`, `ftp://`, `gopher://`, `dict://`, `ldap://`, `tftp://`, `jar://`). WebSearch auto-approves unconditionally (no URL involved).

3. **`lib/mcp_trust_mode.py`** — REWRITTEN. v2.17 rule was "auto-approve only read verbs; everything else prompts" with a per-vendor mutator denylist on top. New rule: auto-approve every MCP tool EXCEPT (a) catastrophic verb tokens (`delete`/`destroy`/`drop`/`purge`/`wipe`/`truncate`/`eradicate`/`expunge`/`uninstall`/`deauthorize`), (b) bulk/mass mutators (`bulk_*`/`batch_modify`/`batch_delete`/`mass_*`/`apply_labels`/`bulk_label`), (c) per-vendor explicit catastrophes (Playwright `browser_run_code_unsafe` + `browser_evaluate` for JS execution; Gmail `_forward_` for data exfil; Drive `move_to_trash` + `_trash_` as irreversible-without-restore). Routine create/update/send (Slack send-message, Gmail create-draft, Calendar create-event, Atlassian createJiraIssue, HubSpot manage_crm_objects, Apollo *_create, Drive create_file, Playwright browser_click/type/navigate, etc.) now auto-approve.

4. **`hooks/hooks.json`** — PermissionRequest matcher expanded from `Bash|Write|Edit|MultiEdit|mcp__.*` to `Bash|Write|Edit|MultiEdit|NotebookEdit|mcp__.*|WebFetch|WebSearch|Task`.

5. **`PERMISSIONS.md`** + **`sutra/os/charters/PERMISSIONS.md`** — Tier 3 ceiling amended: removed "Any network call other than `sutra push` (opt-in)" line (replaced by Web Trust Mode deny-list at Tier 1.9). Added Tier 1.7 amendment (MCP catastrophic-only rule, supersedes v2.17 read-allowlist + mutator-prompt). Added Tier 1.9 (Web Trust Mode — WebFetch/WebSearch). Added Tier 1.10 (Task subagent dispatch + NotebookEdit fold). Audit trail entry for v2.32.0 in plugin manifest.

6. **`tests/permission-gate-test.sh`** — added cases for WebFetch public/loopback/private/metadata/non-http, WebSearch unconditional allow, Task allow, NotebookEdit project file vs `.env`, MCP slack_send_message/Gmail create_draft/Playwright browser_click now ALLOW (was EMPTY in v2.17), MCP Gmail delete_thread + Playwright browser_run_code_unsafe still EMPTY (catastrophic).

### Threat model rationale

Single trusted local operator threat model already governs Bash (the most powerful tool surface). MCP and Web inherit the same posture under the same threat model. Catastrophic floor preserved: deletes, code execution, cloud metadata access, private network scanning, force-push, sudo, fetch-and-exec, infra CLI mutations, recursive deletes outside safe-paths, and credential file writes all still prompt.

### Versions

`2.31.0` → `2.32.0` (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `sutra-defaults.json`).

---

## v2.31.0 — 2026-05-04

**backfill-helper.sh known-values lookup for cap-001..011 + version-archaeology drift fix.**

Per codex 2026-05-04 final-push consult ADVISORY: "Best next chunk: TBD field completion for cap-001..011, then stop." Closes the only remaining tractable D43 follow-up that's evidence-producing in 1-2 hours.

### What changed

1. **`sutra/marketplace/plugin/scripts/backfill-helper.sh`** — added `KNOWN_VALUES` lookup table for cap-001..011 (existing Bucket A shipping disciplines). For each cap, fills `surface` / `artifact_path` / `charter` / `activation_surface` / `release_vehicle` / `released_in` / `version_introduced` / `tests` from canonical paths. Bucket A entries also populate `threat_model` + `telemetry_coverage` + `audience` + `distribution_scope` + `promotion_proofs.{activation_proof, test_proof, release_proof, canonical_path_exists}` from known data. Records for cap-100..117, cap-200..204, cap-300..305 still get `TBD-NEEDS-BACKFILL` placeholders (those need real research).

2. **`holding/CAPABILITY-MAP-records.md`** (Asawa-side regenerated) — cap-001..011 now fully field-populated. Phase 2 strict gate violations dropped 30 → 19 (the 19 are cap-100..107 + Bucket B + Bucket C). Phase 1 still PASSES (0 missing/orphan records).

3. **`sutra/CURRENT-VERSION.md`** — prepended a v2.30.0 (HEAD) wayfinder block summarizing the v2.21.0 → v2.30.0 release stream as a single-day D43 charter resume series. Prior v2.25.0 narrative preserved below.

4. **`.claude-plugin/plugin.json` description** — prepended v2.30.0 wayfinder; prior v2.25.0 description preserved below for archaeology.

5. **`.claude-plugin/marketplace.json` plugins[0].description** — same wayfinder prepend.

6. **Versions**: `2.30.0` → `2.31.0` (plugin.json, marketplace.json).

### Why version-archaeology drift mattered

Codex's batch review caught: "[CURRENT-VERSION.md still says v2.25.0]; plugin.json is 2.30.0 but description still starts with v2.25.0; marketplace catalog synced to 2.30.0 but description also stale." Documentation risk after 10 releases in one day; not runtime-breaking but operator-confusing.

### Codex stop signal

This release closes (a) from codex's prioritization. Next chunk requires explicit founder direction per codex stop-signal ("Require founder direction before any new cap-100..107 build, D40 G6 rewire, or any work whose acceptance depends on fresh eval data"). Autonomous push terminates here.

---

## v2.30.0 — 2026-05-04

**4 D43 CSM tools promoted L1→L0 — capability-audit.sh + backfill-helper.sh + csm-registry-diff-gate.sh + csm-classification-pretooluse.sh now plugin-canonical (closes 2026-06-01 promotion deadline 28 days early).**

Per codex 2026-05-04 batch review explicit guidance: "your future promotion of the classification hook should copy [the existing D38 promotion wave's] relative-path handling and registration shape." This release promotes all 4 D43 CSM tools at once.

### What this delivers

D43 capability-axis tooling moves from Asawa-only `holding/` (L1 staging) to plugin-shipped `sutra/marketplace/plugin/{scripts,hooks}/` (L0 fleet). Every plugin install now carries:

- **`scripts/capability-audit.sh`** — 4-state matrix audit (R/P/A/C + Status column)
- **`scripts/backfill-helper.sh`** — generates 40 YAML records from CSM table
- **`scripts/csm-registry-diff-gate.sh`** — Phase 1/2 strict gate (warn/strict-phase1/strict-phase2/report)
- **`hooks/csm-classification-pretooluse.sh`** — at-creation soft-warn for new plugin source files

### Asawa-mode gate (L0-fleet-safe)

Each tool now silently `exit 0` on T4 (no `holding/CAPABILITY-MAP.md`):

```bash
ROOT="${ROOT:-${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}}"
[ -f "$ROOT/holding/CAPABILITY-MAP.md" ] || exit 0
```

The tools only activate when `CAPABILITY-MAP.md` is present (Asawa T1 only); T4 fleet receives them as no-ops. Asawa governance remains intact; T4 surface is the `/sutra-capability` skill (v2.27.0).

### What changed under the hood

- **`sutra/marketplace/plugin/scripts/`** — 3 new files (capability-audit.sh, backfill-helper.sh, csm-registry-diff-gate.sh). Hardcoded `ROOT="/Users/abhishekasawa/..."` removed; replaced with `CLAUDE_PROJECT_DIR` + `git rev-parse` fallback.
- **`sutra/marketplace/plugin/hooks/csm-classification-pretooluse.sh`** — new file (already had Asawa-mode gate by design).
- **`hooks/hooks.json`** — `PreToolUse[Edit|Write|MultiEdit]` matcher gains `csm-classification-pretooluse.sh` entry. Activation-wired.
- **`.claude-plugin/plugin.json`** — `2.29.0` → `2.30.0`.
- **`.claude-plugin/marketplace.json`** — `2.29.0` → `2.30.0`.

### Asawa-side (separate Asawa commit)

The 4 originals at `holding/{scripts,hooks}/` become path-relative shims that `exec` the plugin canonical. Retire-by 2026-06-01. Path-relative resolution (script's own `__dirname` → `../..` → project root) avoids CLAUDE_PROJECT_DIR brittleness when invoked from submodule context.

### Verification

- 3 plugin-canonical scripts run successfully from project root with `CLAUDE_PROJECT_DIR=/Users/abhishekasawa/Claude/asawa-holding`.
- 3 plugin-canonical scripts silently `exit 0` from `/tmp` (T4-mode simulation).
- 3 holding/ shims correctly re-`exec` plugin canonical and emit identical output.
- 1 hook (csm-classification-pretooluse) WARNs on new fake plugin source path via shim.

### Codex

Pre-shipped batch-review guidance (2026-05-04) folded directly. Coexistence with v2.25.0 D38 L1→L0 wave verified — no conflict (orthogonal moves; existing `build-layer-check.sh` + `hooks.json` matcher patterns followed).

---

## v2.29.0 — 2026-05-04

**cap-118 soft post-response lint hook ships — closes the lint follow-up codex flagged when cap-114 split landed in v2.28.0.**

Per codex 2026-05-04 cap114-split-consult ADVISORY: cap-118 (`no_invented_human_ops_mechanisms`) needs a soft post-response lint to evidence-build toward full `shipping`. Schema landed in v2.28.0; this release wires the runtime detection.

### What this delivers

A Stop-event hook that scans the last assistant response in the transcript for codex-specified patterns indicating proposals of human-ops mechanisms (departments, weekly reviews, standups, manual KPI tracking, etc.). Soft-warn only — never blocks Stop event; never disrupts founder workflow.

### Design (codex stability fold)

- **Composite signal**: warn only when **≥2 distinct patterns** hit (single hits too noisy; reduces false-positive training-effect that codex flagged for the gate).
- **Log to JSONL by default**: writes to `.enforcement/cap118-lint.jsonl`. Stderr emission opt-in via `LINT_VERBOSE=1` env. Prevents founder fatigue while accumulating evidence for the 100-turn audit threshold.
- **Allowlist heuristics**:
  - Skip lines starting with `>` (markdown quote) or containing `said:` / `wrote:` (attribution).
  - Skip if `existing` / `already` / `currently` / `previously` / `legacy` / `deprecated` / `established` / `in place` appears within ~80 chars of the pattern (describing reality, not proposing).
  - Skip if `do not` / `don't` / `avoid` / `never` / `stop` / `reject` / `forbid` appears within ~80 chars (critique-of-mechanism, not proposing).

### Verification (3 scenarios pre-commit)

- 3-pattern proposal text → LOGS + verbose stderr (works as designed).
- Existing-reality description with `already` marker → silent (allowlist correctly fires).
- Single pattern hit → silent (composite signal correctly enforces ≥2 threshold).

### What changed under the hood

- **`sutra/marketplace/plugin/hooks/csm-cap118-lint.sh`** (new, ~110 LOC). Stop-event hook. Reads `transcript_path` from Claude Code Stop payload, extracts last assistant text via `jq`, scans 8 codex-specified patterns with allowlist heuristics, logs hits to JSONL.
- **`hooks/hooks.json`** — `Stop[0].hooks` array gains entry for the lint with timeout=3s. Now 14 entries total (was 13).
- **`.claude-plugin/plugin.json`** — `2.28.0` → `2.29.0`.
- **`.claude-plugin/marketplace.json`** — `2.28.0` → `2.29.0`.

### Status path for cap-118

Schema-only `shipping (policy-visible)` (v2.28.0) → schema + soft lint `shipping (policy-visible)` (this release) → full `shipping` post 100-turn audit + <5% false-positive rate (codex evidence bar).

### Kill-switches

`CSM_CAP118_LINT_DISABLED=1` env or `~/.csm-cap118-lint-disabled` file. `LINT_VERBOSE=1` enables stderr emission.

### Codex

Pre-shipped consult ADVISORY (2026-05-04) folded directly. All design choices (composite signal threshold, allowlist heuristics, log-not-stderr default) anchored to codex's stability + false-positive-aversion advice.

---

## v2.28.0 — 2026-05-04

**cap-114 split — `no_fabrication` (cap-114) + `no_invented_human_ops_mechanisms` (cap-118) ship as separate plugin-canonical schemas (D43 follow-up).**

Per codex 2026-05-04 cap114-split-consult ADVISORY (verdict file `.enforcement/codex-reviews/2026-05-04-cap114-split-consult.md`). Fold:

1. **cap-114 renamed `no_fabrication`** — covers attribution/paraphrase + factual grounding (not just filesystem facts per codex). Status `proposed (DEFER)` → `shipping (policy-visible)`.

2. **cap-118 NEW `no_invented_human_ops_mechanisms`** — codex specifically rejected the original "no_unsupported_operational_capacity_claims" name as bleeding back into truthfulness. New name draws clean boundary: cap-114 = "is this claim true / grounded?", cap-118 = "is this proposing forbidden human-ritual structure?".

### What this delivers

`sutra-defaults.json` v2.28.0 adds two top-level keys (codex confirmed top-level placement vs nested under output_discipline / consult_policy — the rules govern proposal *content* across all turns, not response shape):

```
.no_fabrication                       (cap-114) — truthfulness/attribution
.no_invented_human_ops_mechanisms     (cap-118) — no human-ritual proposals
```

Each schema entry carries:
- `rule` — declarative behavior rule
- `applies_to` + `not_applies_to` — scope boundary (codex P0)
- `examples_good` (3 each) + `examples_bad` (3 each) — codex required 3-5
- `evidence_for_full_shipping` — what unlocks full `shipping` from `policy-visible`
- `coverage_note` — explicit policy-visible caveat per codex
- `enforcement: convention_only` (cap-114) / `convention_only` + planned soft lint (cap-118)
- `cap_id` cross-reference to CAPABILITY-MAP.md

### Why no hooks (yet)

- **cap-114**: schema-only. Hard hook = theater (codex: "untestable structurally without LLM-judge eval").
- **cap-118**: schema-first; soft post-response lint **deferred to follow-up commit**. Codex specified lint patterns (`department`, `weekly review`, `standup`, `manual KPI`, `every Friday`, `appoint an owner`, etc.) and allowlist contexts (quoting founder verbatim, describing existing infrastructure, critique-of-existing-mechanism).

### Status path

Both promoted `proposed (DEFER)` → `shipping (policy-visible)`. Full `shipping` requires:
- cap-114: claim-extraction or LLM-judge eval on H-Sutra log ≥100 turns. Grep-verifiable audit alone insufficient.
- cap-118: 100-turn audit + soft lint with <5% false-positive rate. Reachable earlier than cap-114 because violation class is narrower and structurally detectable.

### What changed under the hood

- **`sutra-defaults.json`** — 2 new top-level entries (~50 lines schema each).
- **`.claude-plugin/plugin.json`** — `2.27.0` → `2.28.0`.
- **`.claude-plugin/marketplace.json`** — `2.27.0` → `2.28.0`.

### CSM impact (Asawa-side)

`holding/CAPABILITY-MAP.md` cap-114 row updated: status `proposed (DEFER)` → `shipping (policy-visible)`; new cap-118 row added with same status. Notes reference codex consult. capability-audit.sh DISCIPLINES_BACKLOG config updated to point at new schema paths.

### Codex

Pre-shipped consult ADVISORY folded directly. All 5 codex prerequisites (final names, examples, scope boundaries, status path, cap-118 lint deferred) addressed.

---

## v2.27.0 — 2026-05-04

**`/sutra-capability` skill ships — T4 fleet's on-demand CSM digest (D43 Layer 4, CSM TODO #3).**

Per CSM TODO #3 (deadline 2026-06-01). Asawa CEO sessions get the SessionStart banner (v2.21.0); T4 fleet gets this skill — invoke `/sutra-capability` (or ask "what does this Sutra plugin ship?") and Claude emits a compact ASCII-table digest of capabilities grouped by category (per-turn blocks, output discipline, governance disciplines, enforcement hooks, backlog).

### What this delivers

For T4 fleet: visibility into the capability surface without needing access to Asawa's `holding/CAPABILITY-MAP.md`. The skill reads `${CLAUDE_PLUGIN_ROOT}/sutra-defaults.json` + `skills/` + `hooks/hooks.json` + `plugin.json` and assembles the digest from what's actually installed — no hardcoded list, no separate manifest to keep in sync.

### What changed

- **`sutra/marketplace/plugin/skills/sutra-capability/SKILL.md`** (new, ~80 lines). Frontmatter description triggers on capability/CSM/skills/hooks queries + literal `/sutra-capability` invocation. Body instructs Claude to read 4 plugin files and emit the digest using ASCII tables (no unicode box-drawing per `[Terminal box formatting]`).
- **`.claude-plugin/plugin.json`** — `2.26.0` → `2.27.0`.
- **`.claude-plugin/marketplace.json`** — `2.26.0` → `2.27.0`.

### Coverage caveat baked in

Per codex 2026-05-04 ADVISORY #4: skill output explicitly distinguishes:
- `shipping` (Bucket A, runtime-enforced) vs
- `shipping (policy-visible)` (Bucket A, schema declared, behavior not verified) vs
- `proposed` (not yet shipping) vs
- `DEFER` (cap-114, awaiting split consult).

Founder reads `enforcement` field of schema entry (`convention_only` vs `hard_block`/`gate`/`pretooluse`) to disambiguate runtime enforcement.

### Kill-switch

`SUTRA_CAPABILITY_DIGEST_DISABLED=1` env or `~/.sutra-capability-disabled` file.

### Codex

Skill is content-only (no executable code); SKILL.md frontmatter + body. Per Sutra Engine charter §16 amendment B and `[Right-Effort Discipline]` (surgical scope), no pre-shipped consult required for content-only skill addition. Post-ship review covers Layer 4 + Layer 1+2+3 in the autonomous-push end-of-batch review.

---

## v2.26.0 — 2026-05-04

**4 Asawa-side disciplines moved from memory-only to plugin-canonical schema (D43 fleet-parity Layer 3).**

Per autonomous-push codex 2026-05-04 ADVISORY #2 + #4: bundle as schema entries (no thin dedicated hook nudges) under existing `output_discipline` / new top-level keys. Coverage = **policy-visible, not behavior-verified** — explicit caveat per ADVISORY #4.

### What this delivers

`sutra-defaults.json` v2.26.0 adds 4 schema entries previously Asawa-only memory:

```
.customer_focus_first                       (cap-112) — Founding Doctrine P0
.process_discipline_proto006                (cap-116) — PROTO-006 anchor
.output_discipline.highlight_decisions      (cap-113) — ASCII-box decisions
.output_discipline.table_shape              (cap-115) — Impact + Effort columns mandatory
```

Each entry carries `enforcement: convention_only` + `coverage_note: "policy-visible, not behavior-verified"` + `cap_id` cross-reference to CAPABILITY-MAP.md for audit traceability.

### Why no new hooks

Codex ADVISORY #2 explicitly rejected new dedicated hook nudges:

> That is the exact "hook injects prompt" creep risk. The safer shape is: add the schema rows; extend one existing soft-hint surface; keep enforcement advisory, not blocking.

Models can emit headers cosmetically without reasoning with them — adding more nudge lines per turn dilutes the prompt without proven behavior change. Schema-only additions surface the discipline in `core:output-trace` skill output and CSM dashboards without per-turn token cost.

### What changed under the hood

- **`sutra-defaults.json`** — 4 new entries (2 top-level, 2 nested under `output_discipline`); version `1.0.5` → `2.26.0`.
- **`.claude-plugin/plugin.json`** — `2.25.0` → `2.26.0`.
- **`.claude-plugin/marketplace.json`** — `2.25.0` → `2.26.0`.

### CSM impact (Asawa-side)

`holding/CAPABILITY-MAP.md` cap-112/113/115/116 promoted `proposed` → `shipping (policy-visible)`. cap-114 (No fabrication / no operational capacity) marked `proposed (DEFER)` per codex ADVISORY #4 — two distinct disciplines bundled, requires own split consult before promotion. capability-audit.sh re-run confirms P=YES for all 4 promoted caps.

### Coexistence note

This commit ships in parallel with v2.21.0 / v2.22.0 / v2.23.0 / v2.24.0 / v2.25.0 from the parallel Sutra Delivery OS workstream + D38 L1→L0 promotion wave. v2.26.0 takes the next number to coexist cleanly with all those releases.

### Codex

Pre-shipped ADVISORY at `.enforcement/codex-reviews/2026-05-04-everything-push-consult.md` folded directly. Post-ship batch review covers Layer 1+2+3 at end of autonomous push.

---

## v2.24.0 — 2026-05-04

**Sutra Delivery OS Wave 4 (FINAL) ships: fourth first-party Decisional+Generative skill `core:incremental-architect` — migration planning.**

Closes the migration-planning gap: nothing in the surveyed ecosystem ships a structured migration-planning skill (strangler fig / branch by abstraction / parallel-run / decompose-then-recompose / hybrid) with operational decommission gate enforcement and Fowler/Newman/Adzic-derived pre-planning checklist.

### What changed

1. **`sutra/marketplace/plugin/skills/incremental-architect/`** — new skill directory.
   - `SKILL.md` (~170 lines): authors a MIGRATION-PLAN.md (9 sections incl. operational decommission gate with named approver + evidence artifact + observation window + final-deletion phase). Pre-planning checklist forces dependency-coupling map, data ownership boundaries, dual-write consistency strategy, schema evolution path, and thinnest viable slice. Description tightened to fire ONLY for live-state transitions (not routine library upgrades, feature-flag cleanup, vendor swaps without state migration).
   - `evals/{README,E1-monolith-to-microservices,E2-database-replacement,E3-api-deprecation}.md`: 3 structural-only assertion evals (loosened from initial draft per codex P0; removed eval contract drift where assertions were stronger than SKILL contract).
2. **`sutra/marketplace/plugin/.claude-plugin/plugin.json`** — version 2.23.0 → 2.24.0.
3. **`sutra/.claude-plugin/marketplace.json`** — catalog entry version 2.23.0 → 2.24.0.

### Codex REVIEW chain

Verdict: CHANGES-REQUIRED → all P0 + P1 folded.
- **P0**: eval contract drift — E1/E2/E3 each required domain-specific phase shapes and tastes not guaranteed by the SKILL contract (E1 routing-layer-as-phase-1, E2 specific phase names like parallel-read-verify, E3 warning-then-error specifics). Fix: loosened all three to structural-only assertions; removed phase-shape requirements not in SKILL.
- **P1 #1**: trigger surface too broad — "replace a dependency", "introduce a new platform", "decommission a feature" could mis-fire on routine upgrades, feature-flag cleanup, vendor swaps. Fix: description now narrowed to "live-state transition, compatibility period, phased cutover, or retirement of an existing production path"; explicit Skip cases for routine upgrades / flag cleanup / vendor swaps.
- **P1 #2**: decommission discipline was prose-only, not operationally enforced. Fix: gate now requires all 4 — named approver, evidence artifact, observation window default, final-deletion phase blocked on gate completion. A plan missing any of the 4 is decommission theater.
- **P1 #3**: missing migration literature gap — Fowler/Newman seam-finding, Adzic thin-slice, distributed-monolith trap. Fix: added Pre-planning checklist (5 items: dependency/coupling map, data ownership boundaries, dual-write consistency, schema evolution path, thinnest viable slice) MUST run before phase plan; risk register MUST include at least one of hidden-coupling/dual-write/schema-evolution/distributed-monolith trap.

Verdict file: `.enforcement/codex-reviews/2026-05-04-w4-incremental-architect-build-review.md`.

### Distinct from existing ecosystem skills

- `core:architect` (W2) — authors net-new architecture; this skill plans the evolution of an EXISTING architecture. If the to-state architecture isn't defined enough to phase, compose `core:architect` first then return here.
- gstack `plan-eng-review` — reviews a plan; this skill AUTHORS the plan.
- gstack `gsd-execute-phase` — executes phased work; this skill plans the phases.

### Sutra Delivery OS expansion — COMPLETE

Wave plan executed end-to-end:
- W1 v2.20.0 — `core:test-strategy` (Decisional+Generative)
- W2 v2.22.0 — `core:architect` (Generative; Sutra D38 Build-Layer integration as distinctive value)
- W3 v2.23.0 — `core:deterministic-testing` (Generative+Procedural; golden + snapshot + property + contract + drift detector)
- W4 v2.24.0 — `core:incremental-architect` (Decisional+Generative; migration planning with operational decommission gate)
- ~~W5~~ `core:idea-to-delivery` — DEFERRED indefinitely per codex P0 ("product thesis, not bounded skill"); revival criteria documented in `holding/research/2026-05-04-sutra-delivery-os-skills-spec.md` §2.5

3 of 4 problem-mode gaps from yesterday's skill-validation framework now closed (Generative + Procedural + Decisional). Diagnostic gap remains for future consideration.

### Downstream cascade (D13)

T2/T3/T4 fleet receives via plugin update; additive non-breaking. Single fleet pulse note recommended after v2.24.0 to surface the 4-wave Delivery OS expansion as a coherent story.

## v2.23.0 — 2026-05-04

**Sutra Delivery OS Wave 3 ships: third first-party Generative+Procedural skill `core:deterministic-testing`.**

Closes the I/O determinism scaffolding gap: `core:test-strategy` (W1) designs the strategy; `gstack gsd-add-tests` generates general tests; `superpowers:test-driven-development` is the workflow. Nothing in the surveyed ecosystem ships I/O-determinism-focused scaffolding (golden + snapshot + property + contract + drift detector) as a first-party skill. v2.23.0 fills it.

### What changed

1. **`sutra/marketplace/plugin/skills/deterministic-testing/`** — new skill directory.
   - `SKILL.md` (~290 lines): generates I/O determinism test scaffolding for a function/API/skill/pipeline. 8-section output contract: golden fixtures, golden test runner, snapshot tests, property-based tests (≥1 invariant), contract tests, snapshot drift detector, FIXTURES.md (rotation policy), Open questions. Includes fixture decision matrix (8 subject types: pure function, stateful, HTTP own/third-party, DB query, LLM prompt, CLI tool, stream/pipeline) + property invariant patterns table (round-trip, idempotent, commutative, identity, bounded, schema-conforming, length/cardinality) + snapshot drift discipline (assert SHAPE not exact text).
   - `evals/README.md` + `evals/{E1-pure-function,E2-http-api,E3-llm-prompt}.md`: 3 structural-assertion evals. E1 covers `parseURL`-style pure function with golden + property; E2 covers HTTP API with snapshot SHAPE assertion + contract + idempotency property; E3 covers LLM prompt with JSON Schema assertion + enum-membership constraint + no-exact-text-equality discipline.
2. **`sutra/marketplace/plugin/.claude-plugin/plugin.json`** — version 2.22.0 → 2.23.0; description prepended.
3. **`sutra/.claude-plugin/marketplace.json`** — catalog entry version 2.22.0 → 2.23.0; description synced.

### Codex REVIEW chain

Verdict: PASS-WITH-FIXES (no P0 blockers; 3 P1s folded inline).
- **P1 #1**: E1 assertion 4 hard-coded "no-throw on arbitrary string input" as required property — too specific for the general skill contract. Fix: made it conditional on user prompt naming such an invariant.
- **P1 #2**: E2 assertion 1 required full-body golden fixtures for an endpoint with `created_at` variability — would push toward brittle goldens against the SKILL's own SHAPE-not-text discipline. Fix: allow normalized fixtures or fixture+matcher pairs.
- **P1 #3**: E3 assertion 9 required flake-mitigation guidance (reruns, statistical pass-rate) — not in SKILL contract. Fix: relaxed to "any acknowledgement of LLM variability"; specific mitigations not required.

P2 items deferred to W3.1: tighten trigger phrasing further to "write/add/generate scaffolding for"; add locale/Unicode/timezone/line-ending/floating-point-formatting/iteration-order to pure-function anti-patterns; add unstable-IDs/DB-auto-increment/list-ordering to HTTP anti-patterns; add semantic-guardrail (enum membership / required-field coherence / refusal-path coverage) requirement for LLM tests beyond schema-only.

Verdict file: `.enforcement/codex-reviews/2026-05-04-w3-deterministic-testing-build-review.md`.

### Distinct from existing ecosystem skills

- `core:test-strategy` (W1) — designs the test STRATEGY (pyramid, fixture choice, boundaries); this skill IMPLEMENTS the strategy as actual test files.
- gstack `gsd-add-tests` — general test generation; this skill is I/O-determinism-focused (golden + snapshot + property + contract).
- `superpowers:test-driven-development` — workflow (red-green-refactor); this skill is the artifact (test files + fixtures).
- gstack `qa` — runs tests + fixes bugs; this skill writes the tests.

### Downstream cascade (D13)

T2/T3/T4 fleet receives via plugin update; additive, non-breaking. Wave plan continues: W4 incremental-architect (final wave). Self-score telemetry now optional + non-side-effecting.

---

## v2.22.0 — 2026-05-04

**Sutra Delivery OS Wave 2 ships: second first-party Generative skill `core:architect`.**

(Note: v2.21.0 was concurrently allocated by the CSM SessionStart banner work; this Delivery OS wave bumps to v2.22.0 to avoid the version collision.)

Closes the architecture-authoring gap: gstack `plan-eng-review` reviews architecture but doesn't author; nothing in the surveyed ecosystem writes structured ARCHITECTURE.md as a first-party skill. v2.22.0 fills it with Sutra D38 Build-Layer integration as the distinctive value-add.

### What changed

1. **`sutra/marketplace/plugin/skills/architect/`** — new skill directory.
   - `SKILL.md` (~340 lines): designs and authors a single ARCHITECTURE.md covering 9 sections — Purpose+scale+constraints, C4 L1 (System Context), C4 L2 (Container), C4 L3 (Component for 1-3 high-leverage containers only), ADRs (Status / Context / Decision / Consequences with no-theater rule), STRIDE threat model with system-specific top 5-10 risks, Scaling axes (load/data/team/geography), Sutra D38 Build-Layer table (the distinctive value-add), Open questions + noted limitations. Existing-codebase mode adds D38 enforcement-category mapping (PLUGIN-RUNTIME / SHARED-RUNTIME / HOLDING-IMPL / LEGACY-HARD / SOFT) so the architecture matches what the runtime hook checks at edit time.
   - `evals/README.md` + `evals/{E1-greenfield-saas,E2-existing-codebase,E3-regulated-system}.md`: 3 structural-assertion evals. E1 covers blank-slate B2B SaaS with team-size taste check; E2 grounds in actual `sutra/marketplace/plugin/` directory and tests no-fabrication discipline (file-level path references required per L3 container); E3 covers regulated FinTech (RBI data-localization + DPDP consent) constraint-driven design.
2. **`sutra/marketplace/plugin/.claude-plugin/plugin.json`** — version 2.21.0 → 2.22.0; description prepended.
3. **`sutra/.claude-plugin/marketplace.json`** — catalog entry version 2.21.0 → 2.22.0; description synced.

### Codex REVIEW chain

Verdict: CHANGES-REQUIRED → all P0 + P1 folded.
- **P0 #1**: eval contract drift — E2/E3 required "Open questions" entry but SKILL.md's section contract didn't include one (same drift class as W1's section 6 "skip" issue). Fix: added section 9 "Open questions + noted limitations" to the always-emit contract; never silently omitted.
- **P0 #2**: D38 enforcement-mapping gap — E2 expected PLUGIN-RUNTIME / LEGACY-HARD / SOFT details but SKILL.md only defined L0/L1/L2 abstractly. Fix: added the 5-category enforcement-path mapping table to section 8, scoped to existing-codebase mode.
- **P1 #1**: telemetry append to `skill-adoption-log.jsonl` was an ecosystem anti-pattern (creates side effects unrelated to user intent, may fail in constrained environments). Fix: made the append OPTIONAL and non-blocking — silently skip if sink unwritable or telemetry opted out.
- **P1 #2**: "at least one component should be L1/L2" was build-layer cosplay — some systems legitimately are all-L0. Fix: reframed to "if all-L0, justify why everything generalizes."
- **P1 #3**: E2 "no fabrication" test was gameable (could pass with only top-level directory references). Fix: each L3 section must cite at least one file-level path within the container being decomposed.

Verdict file: `.enforcement/codex-reviews/2026-05-04-w2-architect-build-review.md`.

### Distinct from existing ecosystem skills

- gstack `plan-eng-review` — reviews an architecture proposal; this skill AUTHORS the architecture document.
- gstack `gsd-plan-phase` — phase planning (decomposition into tasks); this skill is one level higher (system structure).
- `core:incremental-architect` (W4) — evolves an existing architecture (migration patterns); this skill writes the original.

### Downstream cascade (D13)

T2/T3/T4 fleet receives via plugin update; additive, non-breaking. Self-score telemetry now optional + non-side-effecting per codex anti-pattern flag. Wave plan continues: W3 deterministic-testing, W4 incremental-architect.

---

## v2.21.0 — 2026-05-04

**CSM SessionStart banner — first execution of CSM TODO #2 visibility surface (D43).**

Per D43 + codex P2 surfacing path (CSM TODO #2, deadline 2026-05-15). 5-line banner on SessionStart shows capability bucket counts, pending fleet-parity count, latest audit timestamp, recurring-instrument pointer, and how to run the audit on demand. Closes the visibility loop the audit instrument (`holding/scripts/capability-audit.sh`, shipped same day in commit da41958) opened.

### What this delivers

For Asawa CEO sessions: every session start emits one screen of CSM state, so capability gaps are visible without manual `cat holding/CAPABILITY-MAP.md`.

```
[CSM·D43] Buckets: 13 shipping · 15 proposed · 5 asawa-only · 6 sutra-internal
[CSM·D43] Pending fleet-parity (cap-1xx proposed): 15; deadlines 2026-05-08 → 2026-06-01
[CSM·D43] Latest audit: 2026-05-04T06:01:38Z (audit jsonl: 31 rows)
[CSM·D43] Recurring instrument: holding/scripts/capability-audit.sh (L1, promote-to plugin/scripts/ by 2026-06-01)
[CSM·D43] Run audit on demand: bash holding/scripts/capability-audit.sh
```

### Behavior modes

- **Asawa-mode** (file `holding/CAPABILITY-MAP.md` present): full 5-line banner.
- **T4-mode** (file absent per D33 firewall): silent skip (`exit 0` before any output).
- **Kill-switch**: `CSM_BANNER_DISABLED=1` env or `~/.csm-banner-disabled` file.

T4 fleet doesn't carry `CAPABILITY-MAP.md` — it's Asawa-internal governance per D33. T4 visibility into the capability surface ships separately via the `/sutra-capability` skill (CSM TODO #3, deadline 2026-06-01).

### What changed under the hood

- **New hook** `sutra/marketplace/plugin/hooks/csm-sessionstart-banner.sh` (~60 LOC). Reads `holding/CAPABILITY-MAP.md` for bucket/status counts (regex grep on cap-### table rows) and `holding/state/capability-map-audit.jsonl` for latest audit timestamp (jq path lookup). Soft-fail throughout (`set -u` only, never `-e`); never blocks SessionStart.
- **`hooks/hooks.json`** — `SessionStart[0].hooks` array gains entry for the banner with timeout=3s. Now 8 entries total (was 7).
- **`.claude-plugin/plugin.json`** — `2.20.0` → `2.21.0`.
- **`.claude-plugin/marketplace.json`** — `2.20.0` → `2.21.0`.

### Verification

Banner tested in 3 modes pre-commit:
- Asawa-mode: emits 5 lines with real counts (13 shipping / 15 proposed / 5 asawa-only / 6 sutra-internal).
- T4-mode (no CAPABILITY-MAP.md): silent (exit 0).
- Kill-switch (`CSM_BANNER_DISABLED=1`): silent (exit 0).

### Codex

Not pre-consulted. Mechanical surfacing hook, reversible, ~60 LOC, soft-fail by design. Per Sutra Engine charter §16 amendment B (codex review at abstraction-freeze points, not per micro-step) and `[Right-Effort Discipline]` (surgical scope only). Post-ship review available on request.

### Coexistence note

This commit ships in parallel with v2.20.0 (Sutra Delivery OS Wave 1, `core:test-strategy` skill — separate working-tree changes by parallel Delivery OS workstream). v2.21.0 takes the next number to avoid collision. Both releases stack cleanly: v2.20.0 ships the new skill, v2.21.0 ships the new hook + version bump.

---

## v2.20.0 — 2026-05-04

**Sutra Delivery OS Wave 1 ships: first first-party Generative+Decisional skill `core:test-strategy`.**

Founder direction 2026-05-04: "I need some skills in the testing framework... in figuring out input, test, output test ways to go about writing architecture and schemas... I want these to be incorporated as part of Sutra... and I want this to be provided to clients as well of Sutra. Add this to plugins as well." Yesterday's [skill-validation framework](../../../holding/research/2026-05-04-skill-validation-framework.md) identified 4 problem-mode gaps (Diagnostic / Generative / Reactive / Refining) — all 9 existing Sutra skills are Governance-mode. v2.20.0 closes the Generative+Decisional gap with the first of 4 Delivery OS skills.

### What changed

1. **`sutra/marketplace/plugin/skills/test-strategy/`** — new skill directory.
   - `SKILL.md` (~250 lines): designs a TEST-STRATEGY.md document for any subject (function / module / system / AI prompt) before tests are written. Includes pyramid heuristics by domain (8 rows: pure compute / stateful service / API / CLI / LLM classifier / RAG / data pipeline / infra), fixture decision matrix (8 rows: own DB / managed DB / HTTP own / HTTP third-party / LLM / FS / clock / random), mock-vs-real boundary discipline, coverage targets matched to risk profile, AI eval-pack design (≥3 evals, baseline-without-skill, multi-model, structural+LLM-judge scoring, drift detection, fixture rotation), CI gate placement.
   - `evals/README.md` + `evals/E1-payment-processing.md` + `evals/E2-llm-classifier.md` + `evals/E3-cli-tool.md`: 3 structural-assertion evals covering safety-critical / user-facing / internal-tooling risk profiles. No fragile specifics (per yesterday's codex P1 fold).
2. **`sutra/marketplace/plugin/.claude-plugin/plugin.json`** — version 2.19.0 → 2.20.0; description prepended with v2.20.0 narrative.
3. **`sutra/.claude-plugin/marketplace.json`** — catalog entry version 2.19.0 → 2.20.0; description prepended (sync with plugin.json per v2.18.2 contract test).

### Codex review chain

- **CONSULT** on the original 5-skill spec: verdict RESCOPE → cut `core:idea-to-delivery` (codex P0: "product thesis, not bounded skill"), rename `io-contract-test` → `deterministic-testing` (codex P1: name now matches 4-technique scope), promote `test-strategy` to W1 (codex P1: broader demand, easier eval). All folded. Verdict at `.enforcement/codex-reviews/2026-05-04-sutra-delivery-os-spec-consult.md`.
- **REVIEW** on W1 build: verdict CHANGES-REQUIRED → all P0 (Anthropic-spec description shape: imperative second-person → third-person WHAT+WHEN; section contract: "7 sections" vs 8 listed → reconciled; section 6 "skip" vs eval expects placeholder → "always present, placeholder if no AI"; eval brittle specifics → loosened to structural-only) + all P1 (trigger discriminator added; fixture matrix DB rule corrected; own-DB threshold anti-pattern removed; infra pyramid softened) folded inline. Verdict at `.enforcement/codex-reviews/2026-05-04-w1-test-strategy-build-review.md`.

### Distinct from existing ecosystem skills

- gstack `gsd-add-tests` — generates the tests themselves; this skill plans BEFORE.
- gstack `qa` / `qa-only` — runs tests; this skill plans them.
- `superpowers:test-driven-development` — workflow (red-green-refactor); this skill is the strategy artifact.
- `superpowers:writing-plans` — generic planning; this skill is testing-specific with pyramid heuristics.

### Downstream cascade (D13)

T2 owned (DayFlow / Billu / Paisa / PPR / Maze) + T3 projects (Testlify / Dharmik) + T4 fleet — receives skill via plugin update; additive, non-breaking. No client TODO updates required. Sutra plugin self-dogfoods on the next test-strategy authoring task. Self-score appended to `holding/research/skill-adoption-log.jsonl` as telemetry only (not a ship gate, per codex P2). Wave plan: W2 architect, W3 deterministic-testing, W4 incremental-architect — all per `holding/research/2026-05-04-sutra-delivery-os-skills-spec.md`.

---

## v2.18.0 — 2026-05-03

**Opt-in telemetry push restored. Default OFF posture preserved.**

Founder direction: "make it on if the user said yes" (2026-05-03). The `--telemetry on` flag (added v2.9.1) persisted `telemetry_optin=true` to `.claude/sutra-project.json`, but `scripts/push.sh:19-24` had a hard gate from the v2.0 privacy reset that bailed out unconditionally unless `SUTRA_LEGACY_TELEMETRY=1`. Net effect: opt-in flag was theater — no transport regardless of consent. v2.18.0 lifts the gate and honors the opt-in.

### What changed

1. **`scripts/push.sh`** — drops the v2.0 hard gate. `SUTRA_TELEMETRY=0` short-circuits BEFORE the `telemetry_optin` check (uniform with capture path). All `python3` JSON probes (5 sites) replaced with `jq` to match `start.sh` v2.13.0 EDR-killed-python3 fix. Manifest writer (lines 77-95) replaced with atomic `jq | mktemp | mv -f` pattern. Missing jq → exit 127 with install hint. New `SUTRA_DATA_REMOTE` env override for testability and self-host paths.
2. **`scripts/_sutra_project_lib.sh:180-186`** — banner branches on 3 telemetry states: `SUTRA_TELEMETRY=0` kill-switched / opt-in ENABLED / off. Old "local-only — push disabled in v2.0 privacy model" wording removed (no longer accurate when opt-in=true).
3. **`scripts/go.sh`** — full jq migration (write + read paths). Without this, `/sutra-go` silently failed on EDR-killed-python3 hosts — toggle reported success but `telemetry_optin` stayed false.
4. **`scripts/status.sh`** — jq for sutra-project.json read, with graceful "(jq missing)" fallback. Surfaces `SUTRA_TELEMETRY=0` kill-switch state explicitly.
5. **`hooks/flush-telemetry.sh:97-107`** — jq replaces python3 OPTIN probe; `SUTRA_TELEMETRY=0` short-circuit added BEFORE the read. Non-blocking nohup/disown semantics preserved.
6. **`hooks/posttool-counter.sh`** — `SUTRA_TELEMETRY=0` early exit before any tool-name parsing or `.counters` write. Closes the kill-switch hole on the capture rail (per codex R4: PRIVACY.md amendment claims "stops both capture and push uniformly" — needed both rails to actually do that).
7. **`hooks/emit-metric.sh`** — `SUTRA_TELEMETRY=0` early exit before any metric write. Same R4 finding.
8. **`PRIVACY.md`** — version bump 2.0 → 2.18; top-of-doc amendment **explicitly supersedes** the v2.0 changelog "no outbound transmission in v2 default mode" sentence AND the "Tier-specific defaults" T1/T2 auto-consent paragraph (both stale post v2.9.1 decoupling). Discloses on opt-in: WHAT pushed (telemetry rows + manifest with `install_id`/`project_id`/`project_name_optional`/`sutra_version`/`push_count`/`first_seen`/`last_seen`), CADENCE (every Stop), DESTINATION (collaborator-visible `sankalpasawa/sutra-data` per PROTO-024 V1), KILL-SWITCH (`SUTRA_TELEMETRY=0` uniform across capture and push).
9. **`tests/integration/test-onboard-to-push.sh`** — full rewrite. Calls `push.sh` directly via `SUTRA_DATA_REMOTE` override against a local bare repo. Asserts: `--telemetry on` triggers push; `SUTRA_TELEMETRY=0` + `telemetry_optin=true` skips push with structured reason; jq absent → exit 127; `telemetry_optin=false` skips push. No python3 in test path.
10. **`.claude-plugin/plugin.json`**, **`marketplace.json`** — 2.17.0 → 2.18.0.

### Codex review (5 rounds, converged at PASS)

- **R1** CHANGES-REQUIRED: [P1] `SUTRA_TELEMETRY=0` not honored by push.sh; [P2] manifest leakage (`project_name_optional` + stable IDs) on collaborator-visible repo needs explicit disclosure; [P2] python3 fragility contradicts v2.13.0 jq migration.
- **R2** CHANGES-REQUIRED: [P1] `flush-telemetry.sh:101` also uses python3 OPTIN probe — same EDR fragility on the trigger side.
- **R3** CHANGES-REQUIRED: [P1] `scripts/go.sh` (opt-in toggle) and [P2] `scripts/status.sh` also use python3 — silent toggle failure on EDR-kill hosts.
- **R4** CHANGES-REQUIRED: [P1] If PRIVACY.md amendment claims `SUTRA_TELEMETRY=0` stops both capture and push uniformly, then `hooks/posttool-counter.sh` AND `hooks/emit-metric.sh` need early exits — otherwise the documented kill-switch is a lie.
- **R5** PASS: "13-file design closes the remaining R1-R4 defects... Proceed to edits exactly as specified."

Verdict file: `.enforcement/codex-reviews/2026-05-03-v2.18.0-opt-in-push.md` (DIRECTIVE-ID 1777800873).

### Deferred (codex-accepted, tracked separately)

- `hooks/flush-telemetry.sh:23,76` (session_id parsing + per-tool counter parsing) — same file but different domain (NOT opt-in control); deferred to keep diff surgical.
- `hooks/emit-metric.sh:43` (VERSION read with "unknown" fallback) — not opt-in path; the new SUTRA_TELEMETRY=0 guard at top of file makes the codepath unreachable when telemetry is off.
- `hooks/output-behavior-lint.sh`, `hooks/bash-summary-pretool.sh`, `hooks/posttool-counter.sh:17-18` (post-guard JSON parsing) — different domains; broader python3 sweep tracked separately.

### Threat-model honesty

This release **restores** outbound transport for opted-in users. That is a deliberate policy expansion vs v2.0's "no transport" framing. PRIVACY.md amendment makes the disclosure prominent (top-of-doc, table format) and supersedes — not silently amends — the prior contract.

---

## v2.17.0 — 2026-05-01

**Connector tools and routine project edits no longer prompt every time.**

Two coverage gaps in the existing permission system are closed:

1. **MCP connector tools** — Slack search/list/get, Apollo enrich/search, Atlassian search/get, Gmail search/list, Google Drive read/search, etc. now auto-approve on read-class verbs. Mutator/send tools (Slack send-message, Gmail create-draft, Atlassian create-issue, Drive copy-file, Calendar create-event, Apollo organization-create, HubSpot manage-crm, etc.) still prompt — by an explicit per-vendor denylist. Playwright observational tools (snapshot, screenshot, console-messages) auto-approve when their verb is in the read-list; stateful tools (click, fill-form, navigate, run-code-unsafe) still prompt.

2. **First-time Edit/Write inside cwd** — routine project edits no longer trigger a permission prompt the first time. The prompt-list still gates: secrets (`.env*`, `credentials.json`, `secrets.yaml`), repo metadata (`.git/`), publish auth (`.npmrc`, `.pypirc`), CI configs (`.github/workflows/`, `.circleci/`, `.gitlab-ci.yml`), deploy configs (`vercel.json`, `fly.toml`, `render.yaml`, `netlify.toml`), container/orchestration (`docker-compose*.yml`, `k8s/`, `helm/values*.yaml`), infrastructure-as-code (`.terraform/`, `*.tfvars`, `Pulumi.*`), Cloudflare/Railway/Firebase/GCP deploy configs, Supabase backend, and anything outside cwd.

### Why

Founder direction D44: *"for the permissions, create it as a separate ADR... auto approve them unless they are very big operations or delete... like connectors, first-time edits."* Sister to D43 (ADR-002 OUT-DIRECT 3-check, ships in v2.16.0) — same friction class (founder-side approval), different actor (harness vs model).

### What changed under the hood

- **New module** `sutra/marketplace/plugin/lib/mcp_trust_mode.py` (~190 LOC). Reads PermissionRequest payload on stdin; returns `{prompt: bool, category, reason}`. Read-verb allowlist regex + per-vendor mutator/send denylist. Anchored regex to keep drift-prone names like `get_or_create`, `read_write`, `fetch_and_delete` falling through to prompt.
- **Hook dispatch** `permission-gate.sh` extended with `_match_mcp` (calls the helper) and `_match_first_time_edit` (path-based allow + prompt-list).
- **Hook config** `hooks.json` PermissionRequest matcher widened: `Bash|Write|Edit|MultiEdit` → `Bash|Write|Edit|MultiEdit|mcp__.*`.
- **Charter** `PERMISSIONS.md` adds Tier 1.7 (MCP) and Tier 1.8 (first-time-edit). Sibling banner clarifies relationship to HUMAN-SUTRA-LAYER.md.
- **Cross-link** in `HUMAN-SUTRA-LAYER.md` § Related disciplines points to PERMISSIONS.md as a sibling charter.
- **Telemetry** `.enforcement/permission-gate.jsonl` schema extended with `tool_class` and `decision_basis` fields.

### Files

- `sutra/os/decisions/ADR-003-permissions-mcp-and-first-time-edit.md` (new)
- `sutra/os/charters/PERMISSIONS.md` (sibling banner + Tier 1.7 + Tier 1.8)
- `sutra/os/charters/HUMAN-SUTRA-LAYER.md` (Related disciplines cross-link)
- `sutra/marketplace/plugin/lib/mcp_trust_mode.py` (new)
- `sutra/marketplace/plugin/hooks/permission-gate.sh` (extended dispatch)
- `sutra/marketplace/plugin/hooks/hooks.json` (matcher widened)
- `.claude-plugin/plugin.json`: 2.16.0 → 2.17.0
- `.claude-plugin/marketplace.json`: 2.16.0 → 2.17.0

### Architectural note (codex caught this)

The original brief modeled `REQUEST·HUMAN-APPROVE` as a Stage-3 OUT-DIRECT sub-form within H-Sutra. Codex R1 flagged this as a P1 blocker — Stage 3 owns founder-visible *model emission*, not harness permission dialogs (different actor). Fix: PERMISSIONS.md is a **sibling discipline** to HUMAN-SUTRA-LAYER.md, not a sub-form. ADR-001's 3-direction MECE invariant is preserved.

### Verification

- `lib/mcp_trust_mode.py` smoke-tested: Slack search auto-approves; Slack send-message prompts; Atlassian createJiraIssue prompts; Playwright click prompts; ambiguous names (e.g. `get_or_create`) fall through to prompt.
- Codex R1 CHANGES-REQUIRED (2 P1 architectural / 2 P2 / 2 P3) → all 6 folded → R2 ADVISORY (4 tighten-before-ship items folded into implementation directly per `[Converge and proceed]`). DIRECTIVE-ID 1777641500.

---

## v2.16.0 — 2026-05-01

**Sutra now self-executes terminal commands by default.**

Before this release, Sutra often asked you to run terminal commands yourself. After v2.16.0, Sutra runs the command itself — unless one of three things is true:

1. **The command needs a real terminal** — interactive auth like `gcloud auth login`, GUI tools, or anything that won't work in headless mode.
2. **The command is on the danger list** — force-pushes, recursive deletes outside safe paths, publishing to npm / Play Store / App Store, sending emails, money movement, or legal/compliance actions.
3. **You've explicitly marked the command class as "always ask me"** — opt-out for specific commands you want to keep approving by hand.

If any of those hit, Sutra surfaces the command normally. Otherwise it runs the command and tells you what it did.

Founder direction D43: *"when Sutra asked me to do some terminal things, for Sutra to do those things on its own."* The v1.0 H-Sutra layer already had a guardrail for over-*asking* (the OUT-QUERY 3-check from ADR-001). v2.16.0 adds the matching guardrail for over-*handoff* — the OUT-DIRECT 3-check.

### What ships

- New OUT-DIRECT sub-form `REQUEST·HUMAN-EXEC` (Sutra asking founder to run a terminal command) — joins existing `ASK·LATER` / `HANDOFF` / `CASCADE`.
- New Stage-3 OUT-DIRECT 3-check, parallel-but-different to OUT-QUERY 3-check:
  - **cant-self-exec** — interactive TTY / GUI / founder OAuth required, or no Bash path.
  - **denylist-hit** — falls in ADR-001 §4 Rule 4's 6-domain irreversible denylist verbatim (no fork).
  - **opt-out** — command class explicitly marked "always founder-runs".
- Default: NONE hit → demote to internal action (Sutra runs via own Bash) + OUT-ASSERT (INFORM). ANY hit → surface REQUEST·HUMAN-EXEC normally.
- Demotion telemetry: 3 new optional fields on the **existing** turn row in `holding/state/interaction/log.jsonl` (`out_direct_3check_hits` · `out_direct_demoted` · `original_out_form`). One-row-per-turn invariant preserved.
- 2 new fixtures (#14 demoted-good-case, #15 surfaced-denylist-case) + new regression test `tests/test-out-direct-3check.sh`. All 94 human-sutra tests green pre-commit.

### Why this is a safety floor, not behavior optimization

Codex R2 verdict (PASS, DIRECTIVE-ID 1777640243): the OUT-DIRECT 3-check is a *floor* analogous to OUT-QUERY 3-check, not a "v1.1+ behavior optimization." Both kill specific pathologies — over-asking and over-handoff — at Stage 3. Charter §v1.0 limits updated from "4 safety guardrails" → "5 safety guardrails."

### Files

- `sutra/os/decisions/ADR-002-out-direct-3check.md` (NEW — ADR text)
- `sutra/os/charters/HUMAN-SUTRA-LAYER.md` (extended — §OUT-DIRECT 3-check + new sub-form + 3 optional log fields + v1.0 limits update)
- `sutra/marketplace/plugin/skills/human-sutra/SKILL.md` (extended — §Stage-3 OUT-DIRECT discipline)
- `sutra/marketplace/plugin/skills/human-sutra/tests/fixtures.json` (+2 rows: #14, #15)
- `sutra/marketplace/plugin/skills/human-sutra/tests/test-out-direct-3check.sh` (NEW — 17 assertions)
- `holding/FOUNDER-DIRECTIONS.md` (D43 appended)
- `.claude-plugin/plugin.json`: 2.15.1 → 2.16.0
- `.enforcement/codex-reviews/2026-05-01-adr-002-r1-consult.md` (CHANGES-REQUIRED with 7 findings)
- `.enforcement/codex-reviews/2026-05-01-adr-002-r2-consult.md` (PASS — all 7 folded correctly)
- `holding/research/2026-05-01-adr-002-out-direct-3check-design-brief.md` (R1-folded, R2-PASSed)

### Codex convergence

R1 CHANGES-REQUIRED (1 P1 surface gate inconsistency between §1 and §2 / 4 P2: "symmetric" overstates · demotion telemetry must reuse turn row · PostToolUse hook is wrong layer · denylist must reuse ADR-001 verbatim / 2 P3: skip schema_version · row #10/#15 mirror cases) → all 7 folded → R2 PASS verbatim: *"No new findings. All seven R1 folds are closed from the text provided. ... CODEX-VERDICT: PASS"*. DIRECTIVE-ID 1777640243.

---

## v2.15.1 — 2026-05-01

**Systemic fix for the recurring nudge-skip pattern (founder direction "systemically fix it").**

Three preceding releases (v2.14.1 BLUEPRINT-not-showing → v2.15.0 4-discipline parity → this H-Sutra-header-not-showing) all had the same root cause: hook reminder phrased as `(skill: X)` parenthetical, which the model misread as "invoke skill X" rather than "emit text directly." When skill auto-discovery didn't fire, the block was silently skipped. v2.15.1 closes the pattern, not just the instance.

### What changed

- `sutra-defaults.json`: NEW `.per_turn_blocks.human_sutra_header` key (format + format_with_tense + format_stage_1_fail + emission_mode + emission_note + log paths + skill_reference). Closes the v2.14.1 deferred TODO.
- `hooks/per-turn-discipline-prompt.sh`: rewrote stderr emission with imperative phrasing — `MUST emit literal text` / `MUST invoke skill` instead of `(skill: X)` parenthetical. Reads new schema key for H-Sutra format. 7 numbered "MUST emit" lines for per-turn block stack + 4 "Conditionals" lines.
- Asawa CLAUDE.md (separate commit): NEW H-Sutra Header section above Input Routing; canonical-schema pointer at top of Mandatory Blocks pointing to sutra-defaults.json so future block additions update one place.

### Why imperative phrasing matters

`(skill: core:human-sutra)` was a hint the model treated as a Skill-tool invocation directive. Skill invocation requires intent-matching the user's prompt against the skill description — doesn't always fire (e.g., bare "hello"). When auto-discovery didn't fire, the model emitted nothing for that block. v2.15.1's `MUST emit as FIRST line of response — literal bracketed text, NOT a skill invocation` removes the ambiguity.

### Files

- `sutra-defaults.json`
- `hooks/per-turn-discipline-prompt.sh`
- `.claude-plugin/plugin.json`: 2.15.0 → 2.15.1
- `.claude-plugin/marketplace.json`: 2.15.0 → 2.15.1 + description preamble
- `SBOM-v2.15.1.txt`: NEW

---

## v2.15.0 — 2026-05-01

**Governance-parity bump: 4 Asawa-side disciplines ship to T4 fleet.**

Founder direction this session: "ship everything to clients." Closes 4 of the v2.14.1 audit gaps. Three ship as expanded `per-turn-discipline-prompt.sh` stderr emissions; the fourth (subagent dispatch briefing) was already shipping in v2.14.1 via `subagent-dispatch-brief.sh` PreToolUse:Task hook and is verified here.

### What ships

| # | Discipline | Mechanism |
|---|---|---|
| 1 | Skill-explain card (D40 G3) | per-turn-discipline-prompt.sh reads `.skill_explanation.template_lines` from sutra-defaults.json, emits reminder line on every UserPromptSubmit |
| 2 | Subagent dispatch briefing | subagent-dispatch-brief.sh PreToolUse:Task — already in v2.14.1; verified emitting 5-block briefing + 4-line footer |
| 3 | Readability gate (tables>prose, numbers>adjectives, ASCII boxes, no unicode boxes, progress bars) | per-turn-discipline-prompt.sh reads `.output_discipline.*` boolean keys, emits reminder line |
| 4 | Karpathy right-effort discipline (think first / simpler-alt / surgical scope / verify-loop) | NEW `.right_effort` key in sutra-defaults.json + reminder line in per-turn-discipline-prompt.sh |

### Files

- `sutra-defaults.json`: NEW `right_effort` section (4 principles + applies_before + kill_switch + lineage comment)
- `hooks/per-turn-discipline-prompt.sh`: +6 jq reads + 3 new printf lines after Codex-consult line
- `.claude-plugin/plugin.json`: 2.14.1 → 2.15.0
- `.claude-plugin/marketplace.json`: 2.14.1 → 2.15.0 + description preamble
- `SBOM-v2.15.0.txt`: NEW

### Remaining audit backlog (v2.16.x)

Capability Map (D43) classification gate, Customer Focus First, No-fabrication, Table Shape (Impact + Effort columns), PROTO-006 process discipline.

---

## v2.14.1 — 2026-05-01

**Per-turn-discipline reminder expanded to enumerate ALL 5 per-turn blocks (vinit feedback on v2.14.0).**

vinit reported on v2.14.0: "didn't show BLUEPRINT or H-Sutra layer." Diagnosis: `per-turn-discipline-prompt.sh` only nudged Input Routing + Depth+Estimation; BLUEPRINT, H-Sutra header tag, OUTPUT TRACE, and BUILD-LAYER marker had no hook reminder. On a T4 client without `CLAUDE.md` governance context, Claude had nothing telling it to emit those 3 blocks visibly. v2.14.1 closes the nudge gap.

### What changed

- `hooks/per-turn-discipline-prompt.sh`: read 8 additional jq fields from `sutra-defaults.json`, emit full 7-row block stack on stderr.
- Block stack order in the new emission: `[H-SUTRA HEADER]` → `INPUT ROUTING` → `DEPTH + ESTIMATION` → `BLUEPRINT` → `BUILD-LAYER marker` → tool calls → `OUTPUT TRACE`. Plus the existing Codex-consult-at-Depth-≥3 line.
- H-Sutra header is hardcoded in this hook; `sutra-defaults.json` doesn't have a `human_sutra` block key yet — adding it is a v2.15.0 candidate.

### Smoke test

```
$ echo '{"prompt":"v2.14.1 smoke"}' | bash hooks/per-turn-discipline-prompt.sh
[Sutra defaults · D40 v1.0.2] Per-turn block stack (emit in this order, top to bottom):
  1. [H-SUTRA HEADER]   single bracketed line, FIRST text in response   (skill: core:human-sutra)
  2. INPUT ROUTING      fields: INPUT / TYPE / EXISTING HOME / ROUTE / FIT CHECK / ACTION
  3. DEPTH + ESTIMATION fields: TASK, DEPTH, EFFORT, COST, IMPACT
  4. BLUEPRINT          fields: Doing / Steps / Scale / Stops if / Switch
  5. BUILD-LAYER marker fields: BUILD-LAYER / ACTIVATION-SCOPE / TARGET-PATH
  6. ... tool calls (Edit / Write / Bash / Agent) ...
  7. OUTPUT TRACE       > route: <skill> > <domain> > <nodes> > <terminal>
```

### Governance-parity audit (NOT shipped, v2.15.x backlog)

These Asawa-side disciplines are NOT yet nudged on T4: skill-explain card (D40 G3), subagent dispatch contract briefing visibility, readability gate (tables/numbers/ASCII boxes), Karpathy right-effort discipline, Customer Focus First, Highlight decisions, No fabrication, Table Shape (Impact + Effort columns), PROTO-006 process discipline, Capability Map (D43) classification at-creation. Pattern is consistent: most exist as Asawa-only memory entries or `sutra-defaults.json` schema with no matching hook emission. Each is a candidate for a future bump.

---

## v2.14.0 — 2026-05-01

**H-Sutra Layer v1.0 ships to fleet (D42 visibility-before-influence) + marketplace catchup over v2.12.0 / v2.13.0 / post-v2.13.0 H-Sutra fold.**

D42 shipped H-Sutra Layer v1.0 to the dev tree earlier today (commits b88b7cc / f65725a / 192bea4 / a00cda3 / 7a32af4 / 106a94a + af84f15 fold) but the marketplace `version` field was stuck at 2.11.1 — cached plugin runtimes never received the per-turn-discipline H-Sutra block, so `holding/state/interaction/log.jsonl` went silent after 10:18Z while founder kept using sessions. This is exactly the merged≠shipping anti-pattern D43 ratified hours earlier today. v2.14.0 unsticks the pointer.

### What ships

| File | Change | Origin |
|---|---|---|
| `hooks/per-turn-discipline-prompt.sh` | +79 lines folded — invokes `skills/human-sutra/scripts/classify.sh`, derives `IR_TYPE` from prompt heuristics, appends a 9-cell + 3-tag + reversibility JSONL row to `holding/state/interaction/log.jsonl` (Asawa override) or `.sutra/h-sutra.jsonl` (default). Fail-open stderr-only; never blocks the prompt. | af84f15 |
| `skills/human-sutra/{SKILL.md, ACTIVATION.md, scripts/classify.sh, references/, tests/}` | Activated end-to-end (skill files were in 2.11.0/2.11.1 cache as scaffold, but no hook called classify.sh until the v2.14.0 fold) | D42 ship commits + post-fold |
| `scripts/_sutra_project_lib.sh` + `scripts/start.sh` + `scripts/onboard.sh` | python3 removed from bootstrap; bash/jq port with identical 4-subcommand surface and identical atomic-write contract | v2.13.0 (ac4e81c + 70893df) |
| 6 Asawa-coupled hooks (dispatcher-pretool / dispatcher-stop / architecture-awareness / +3) | EXTRACTED from plugin to `holding/hooks/` (Asawa-only L2); ~890 LoC dead weight removed from T4 fleet on-disk footprint | v2.12.0 (9f5a0a0) |
| `marketplace.json` | `version` 2.11.1 → 2.14.0 + description preamble freshened (was 3 versions stale at v2.10.1) | v2.14.0 |
| `.claude-plugin/plugin.json` | `version` 2.13.0 → 2.14.0 | v2.14.0 |
| `SBOM-v2.14.0.txt` | NEW supply-chain manifest (SHA256 per shipped file) | v2.14.0 |

### Why catchup vs three separate releases

v2.12.0 (dispatcher portability) and v2.13.0 (python3 removal) were merged to the dev tree but the `marketplace.json` pointer was never bumped past 2.11.1 — both versions were therefore phantom-shipped per D43's definition (merged but not released). v2.14.0 ships all three deltas in one marketplace pointer move with retroactive `core-v2.12.0` and `core-v2.13.0` tags so the version archaeology stays clean.

### Tags

- `core-v2.12.0` retroactive at `9f5a0a0` (dispatcher portability)
- `core-v2.13.0` retroactive at `70893df` (python3 removal)
- `core-v2.14.0` at HEAD (H-Sutra v1.0 + marketplace catchup)

### Verification

After `/plugin update` clients will see `~/.claude/plugins/cache/sutra/core/2.14.0/` materialize. The H-Sutra log starts appending from the next UserPromptSubmit. Smoke check: `tail -1 holding/state/interaction/log.jsonl` (or `~/.sutra/h-sutra.jsonl` on non-Asawa clients) should advance per turn after the update.

---

## v2.13.0 — 2026-05-01

**Remove python3 from /core:start bootstrap path entirely (vinit#38 escalation).**

v2.8.11 moved python3 from stdin-heredoc to file-form to dodge SIGKILL from macOS sandbox/EDR agents (vinit#38 first report). That fixed the heredoc class but not all of them. On 2026-05-01 user @abhishekshah reported that `python3 -c "print('hello')"` itself exits 137 on his machine — the binary is killed regardless of how it's invoked (quarantine xattr, AV process-name killer, codesign mismatch). File-form vs heredoc is irrelevant when python3 can't survive exec. v2.13.0 removes python3 from the bootstrap entirely.

### What changed

| File | Change |
|---|---|
| `scripts/_sutra_project_lib.py` | RETIRED → `archive/2026-05-01-py3-removed-from-bootstrap/`. Zero live callers after this release. |
| `scripts/_sutra_project_lib.sh` | NEW. Bash/jq port of all 4 subcommands (`patch-profile`, `write-onboard`, `stamp-identity`, `banner`). Atomic write via `mktemp` + `mv -f` (rename(2) atomic on same fs). Validates JSON before patching so empty/corrupt files surface a `rc=2` actionable error instead of silently writing a stale-shaped object. |
| `scripts/start.sh` | Upfront `jq` health gate with install hints (brew/apt/dnf/source). 2 lib calls switched from .py to .sh. `sutra_run_python` wrapper deleted (the 137 trap is moot once python3 is gone). |
| `scripts/onboard.sh` | 4 inline `python3 -c` reads (VERSION, EXISTING_OPTIN, FIRST_SEEN, EXISTING_IDENTITY) replaced with `jq -r` equivalents. 2 lib calls switched from .py to .sh. Falls back to "unknown" version when jq is unavailable so direct `/sutra-onboard` calls don't brick on legacy machines. |
| `.claude-plugin/plugin.json` | `version: 2.12.0` → `2.13.0`. |
| `archive/2026-05-01-py3-removed-from-bootstrap/README.md` | NEW. Lineage doc for the retired .py — explains why archived, replacement, and why kept rather than deleted. |

### Why this fix is durable

The previous fix attempts (heredoc → file form, atomic write, 137 diagnostic trap) all assumed python3 itself would run. That assumption breaks the moment a Mac's Endpoint Security / AV / Gatekeeper config refuses to let `python3` exec at all. jq has no equivalent process-name-based killers in the wild because it isn't a scripting interpreter that EDR vendors heuristically flag. Plus jq is a single static binary — `which jq` returning a path is a reliable proxy for "this will work."

### Sandbox acceptance

Tested with PATH symlinked from /usr/bin + /bin minus all `python3*`:

| Check | Result |
|---|---|
| `start.sh` rc | 0 |
| `.claude/sutra-project.json` valid JSON | yes |
| All 7 required fields present | yes |
| Profile patch (`--profile company`) sticks | yes |
| Telemetry flag (`--telemetry on`) patches | yes |
| `install_id` stable across re-runs | yes |
| `first_seen` preserved across re-runs | yes |
| Identity block preserved across re-onboard | yes |
| jq missing → actionable install hint, rc=127 | yes |
| Empty/corrupt JSON → rc=2 with recover instruction | yes |
| No leftover `.sutra-*.tmp` files after normal runs | yes |

### Scope discipline (Karpathy surgical-scope)

Test files (`tests/**/*.sh`) and other plugin hooks (`hooks/**/*.sh`) still call python3 in places. They're left as-is intentionally — those code paths run on developer machines with working python3, not on broken-python3 client machines. Migrating them would be churn without user-visible benefit. If a future user report shows a hook also dying with 137, we'll migrate that hook on demand. The bootstrap path is the one that bricks first-session installs, which is why it's the one that gets the python3-free guarantee.

### What clients on broken-python3 macOS need to do

1. `/core:update` to v2.13.0.
2. Confirm `which jq` returns a path (most macs already have it via Xcode CLT or Homebrew). If not: `brew install jq`.
3. `/core:start` — bootstrap completes, no python3 invoked.

If they prefer to debug the underlying python3 SIGKILL (recommended for general system health, not required for Sutra), the original diagnostic remains useful: `xattr $(which python3); codesign -dv $(which python3); log show --last 5m --predicate 'process == "python3"' --info`.

---

## v2.12.0 — 2026-05-01

**Dispatcher portability charter — extract Asawa-coupled hooks from plugin to holding/.**

Closes Tier 2 SHIPPED-DEAD findings from the plugin coverage audit (companion to issue #49). 6 plugin hooks were heavily Asawa-coupled (hardcoded portfolio company names dayflow|maze|ppr|jarvis|billu|paisa, holding/FOUNDER-DIRECTIONS.md reads, holding/checkpoints/ writes) — never wired in plugin/hooks/hooks.json (T4 fleet had ~890 lines of dead weight on disk). Extracted to `holding/hooks/` as L2 single-instance:asawa-holding files; Asawa wires from local `.claude/settings.json`. Plugin slimmer, separation cleaner.

**Codex consult 2026-05-01: CODEX-VERDICT ADVISORY** (acceptable extraction; sequence per codex P1: add holding-side first, rewire settings, verify, delete plugin copies last — atomic).

### What changed (plugin)

| File | Change |
|---|---|
| `hooks/dispatcher-pretool.sh` | DELETED (548 lines). 16 holding/ refs; hardcoded company switch cases at lines 117/488. Extracted to `holding/hooks/dispatcher-pretool.sh` with L2 marker. |
| `hooks/dispatcher-stop.sh` | DELETED (953 lines). 57 holding/ refs (FOUNDER-DIRECTIONS.md, DIRECTION-ENFORCEMENT.md, ESTIMATION-LOG.jsonl, holding/checkpoints/). Extracted to holding/. |
| `hooks/architecture-awareness.sh` | DELETED (51 lines). Echoed "check holding/SYSTEM-MAP.md" — useless on T4. Extracted to holding/. |
| `hooks/research-cadence-check.sh` | DELETED (135 lines). Scans `holding/research/` for staleness — useless on T4. Extracted to holding/. |
| `hooks/rtk-health-check.sh` | DELETED (88 lines). Writes `holding/observability/rtk-gain-log.md` — Asawa observability dir. Extracted to holding/. |
| `hooks/principle-regression.sh` | DELETED (250 lines). Asawa principle codes (P11/D6/D13). Extracted to holding/. |
| `.claude-plugin/plugin.json` | `version: 2.11.1` → `2.12.0`. |

### What this means for fleet

| User class | Behavior |
|---|---|
| T4 default (no Asawa context) | These 6 files no longer ship. Plugin is ~890 lines lighter. None of them were ever wired in plugin/hooks/hooks.json, so functional behavior is identical (zero hooks fire that didn't before). |
| Asawa T1 | Local `.claude/settings.json` updated to point `dispatcher-pretool` + `dispatcher-stop` invocations at `holding/hooks/...` paths. The other 4 hooks were called *from* the dispatchers — they continue to work because the dispatchers' relative-path calls now resolve inside `holding/hooks/`. |
| T2/T3 (owned + projects) | No effect — these clients don't wire dispatchers. |

### Validation

- `jq -e .` parses `hooks.json` — VALID (no Stop or PreToolUse references to deleted files; dispatcher-posttool wire from v2.10.2 unaffected).
- 6 dangling refs in remaining plugin hooks are all comments (`# Source: holding/hooks/dispatcher-stop.sh section 16`) — historical attribution, not exec dependencies.
- Holding-side smoke test: both `dispatcher-pretool.sh` and `dispatcher-stop.sh` run with stub stdin, exit 0.
- Asawa `.claude/settings.json` line 73 + 283 updated atomically (pre-delete, per codex P1).

### What's NOT in this release

- No fleet behavior change — these 6 hooks were never wired.
- No T4 functional gain (yet) — Tier 2 wins ship as separate batches.
- The `is_dispatcher_inlined()` check in `holding/hooks/verify-policy-coverage.sh:189` already gracefully handles missing plugin-side dispatchers via `[ -f "$d" ] || continue` — no update required.

---

## v2.11.1 — 2026-05-01

**`feedback-channel-guard.sh` false-positive fix.**

Caught during the v2.10.0/v2.10.1 release session: filing an Anthropic submission-pin update at `anthropics/claude-plugins-official` was blocked by `feedback-channel-guard.sh` because the issue body included `https://github.com/sankalpasawa/sutra/...` URLs. The hook's `SUTRA_TARGET` literal-substring check ran against `CMD_LOWER` (full command including `--body "..."`), so any body text mentioning a Sutra URL false-positive-triggered the gate — even when `--repo` explicitly targeted a different repository.

Same drift class as v2.8.8 (vinit#17), which fixed the ACTION match by switching to `CMD_HEAD` (command stripped at first quoted value) but missed the TARGET match.

### Fix

| Item | Change |
|---|---|
| `hooks/feedback-channel-guard.sh` | `CMD_HEAD` computation lifted out of the action-match block to right after `CMD_LOWER` declaration. The `SUTRA_TARGET` `*sankalpasawa/sutra*` case-match now operates on `CMD_HEAD` instead of `CMD_LOWER` — body content can no longer trigger the gate. Path B (git-remote inference inside a sutra checkout) still uses `CMD_LOWER` to detect the explicit `--repo`/`-R` flag presence (intentional — that's a structural check, not a body check). |
| `tests/unit/test-feedback-channel-guard.sh` | NEW. 9 cases covering: v2.11.1 false-positive (foreign --repo + body URL → exit 0), literal Sutra --repo (block), gh api POST against Sutra issues (block), read-only gh against Sutra (pass), non-gh (pass), bypass file (pass), bypass env var (pass), gh pr create against Sutra (block), unrelated external repo (pass). |

### Validation

- 9/9 new cases pass
- 15/15 full unit suite pass — zero regressions from v2.10.x / v2.11.0
- Real-world reproduction: `gh issue create --repo anthropics/claude-plugins-official --body "...sankalpasawa/sutra/issues/43..."` now exits 0, hook accepts.

### Threat model

Unchanged. The hook still blocks every previously-blocked Sutra-targeted write; only the false-positive path on body content is closed. Adversarial obfuscation remains explicitly out of scope per the original v2.6.2 design (single-trusted-operator threat model).

### Related drift in this release window

- v2.10.0 fixed `inbox-display.sh` packaging drift (vinit#43)
- v2.10.1 fixed `cascade-check.sh` stdout-vs-stderr drift
- v2.11.1 fixes `feedback-channel-guard.sh` matcher-scope drift (this release)

Three instances of the same hook-output / hook-matcher drift family, all closed in one day.

---

## v2.10.2 — 2026-05-01

**Plugin coverage trial: paused assistant layer removed; D32 posttool dispatcher wired; override-audit lib promoted; `output-behavior-lint` wired in Stop.**

Companion to `sutra` issue #49 (plugin self-inventory). Closes the "Tier 1 SHIPPED-BROKEN" + first slice of "Tier 2 SHIPPED-DEAD" findings from the audit. Net: **−888 lines, +296 lines, 8 files changed, 1 new lib**.

### What changed

| File | Change |
|---|---|
| `hooks/assistant-decommission.sh` | DELETED. Paused per D37; referenced `$REPO_ROOT/holding/state/...` paths absent on T4 machines (vinit#8 evidence). |
| `hooks/assistant-explain.sh` | DELETED. Same reason as above. |
| `hooks/assistant-feedback.sh` | DELETED. Same. |
| `hooks/assistant-observer.sh` | DELETED. Same. |
| `hooks/assistant-kill-switch.sh` | DELETED. Was wired in Stop, exec'd the now-deleted observer; default-off so harmless silent-exit for everyone except opted-in users running the paused layer. Removing it finishes the D37 pause cleanly. |
| `hooks/hooks.json` | (a) Unwired `assistant-kill-switch.sh` from Stop. (b) NEW: wired `dispatcher-posttool.sh` in PostToolUse (no matcher) — D32 hot-reload registry, silent-exits without `os/SUTRA-CONFIG.md` + `os/hooks/posttool-registry.jsonl`. (c) NEW: wired `output-behavior-lint.sh` in Stop — silent advisory scanning transcript for "Never ask to run" + "No HTML unless asked" violations, writes to `.enforcement/routing-misses.log` (mkdir -p safe). |
| `hooks/lib/override-audit.sh` | NEW. Promoted from `holding/hooks/lib/`. `cascade-check.sh` and `codex-review-gate.sh` source via `[ -f $REPO_ROOT/... ] || _OA_LIB="$(dirname "$0")/lib/override-audit.sh"` — the dirname fallback now resolves on user machines instead of degrading to the no-lib else-branch. |
| `.claude-plugin/plugin.json` | `version: 2.10.1` → `2.10.2`. |
| `CHANGELOG.md` | This entry. |

### Behavior matrix (fleet impact)

| Scenario | v2.10.1 | v2.10.2 |
|---|---|---|
| T4 default install (no opt-in to assistant layer) | 5 phantom assistant-* scripts on disk; kill-switch silently exits | Cleanly absent. -887 lines of disk weight removed. |
| T4 user with `~/.sutra-assistant-enabled` | kill-switch exec'd dead observer → broken | Layer fully gone; no enable surface remains. Revive via `holding/research/2026-04-24-assistant-layer-design.md` when un-paused. |
| Client with `os/SUTRA-CONFIG.md` + `os/hooks/posttool-registry.jsonl` | Custom posttool hooks would not fire (no dispatcher wired) | Hot-reload dispatcher fires registered hooks per matcher; no plugin reinstall required to add new hooks |
| Stop-event behavioral linting | Lived in `holding/hooks/dispatcher-stop.sh` only — Asawa-only | Fires on every fleet Stop; flags "please run", "could you run", `<!DOCTYPE html>` in assistant text when last user message didn't request HTML. Silent advisory; exits 0; needs python3. |
| `cascade-check.sh` / `codex-review-gate.sh` override audit | Fell through to no-lib else-branch on user machines (degraded but not broken) | Lib resolves via plugin path; full audit incl. PROTO-004 / D13 / D29 typed override rows |

### What's deferred (next phase: dispatcher portability charter)

| Item | Holding refs | Reason |
|---|---|---|
| Wire `dispatcher-pretool.sh` | 16 | HOOK_LOG path, hardcoded company switch cases dayflow/maze/ppr/jarvis/billu/paisa, holding/checkpoints/ whitelist |
| Wire `dispatcher-stop.sh` | 57 | Reads FOUNDER-DIRECTIONS.md, DIRECTION-ENFORCEMENT.md, ESTIMATION-LOG.jsonl, holding/checkpoints/ |
| Delete 4 Asawa-only hooks (architecture-awareness / research-cadence-check / rtk-health-check / principle-regression) | various | Referenced by deferred dispatchers; can't safely remove until charter resolves |
| Wire ~17 other unwired hooks | mixed | Most have ≥1 holding-coupling; triage as part of charter |

### Validation

- `jq -e .` parses `hooks.json` — VALID.
- `grep -l "assistant-{decommission,explain,feedback,observer,kill-switch}"` across `plugin/hooks/` + `hooks.json` — **0 matches**.
- `realpath dirname/lib/override-audit.sh` from inside `cascade-check.sh` — **RESOLVED**.
- Five fleet-effect scenarios in matrix above hand-checked.

### Operator notes

- No migration needed. Plugin auto-updates via marketplace pipeline.
- If you had `~/.sutra-assistant-enabled` set: now a no-op file (assistant layer gone). Safe to `rm` it.
- New `output-behavior-lint` requires `python3`; absent → hook exits 0 silently.

---

## v2.10.1 — 2026-05-01

**`cascade-check.sh` silent-block fix + tracking-artifact whitelist.**

Companion fix to v2.10.0. Same drift family as Vinit's #43 (silent hook diagnostics): `hooks/cascade-check.sh` was the *second* hook surfacing `Failed with non-blocking status code: No stderr output` — observed during the v2.10.0 release session itself. Two root causes:

1. **Diagnostics on stdout, not stderr.** Claude Code's PostToolUse protocol relays the hook's stderr when it exits non-zero. The hook printed BLOCKED, the policy reason, and the override hint to **stdout** via plain `echo` — Claude Code surfaces "No stderr output" because nothing reached stderr. Fix: the entire blocking diagnostic now routes via `{ echo ... } >&2`.
2. **Tracking artifacts triggered the gate.** Routine writes to research notes, session checkpoints, state ledgers, enforcement logs, telemetry — all CLAUDE.md-whitelisted as "no advisory, no block" — were firing the D13 cascade gate and demanding TODO follow-ups. Fix: the existing exempt list now matches the CLAUDE.md whitelist.

### What changed

| File | Change |
|---|---|
| `hooks/cascade-check.sh` | Block diagnostic moved into `{ ... } >&2` group; warning prelude moved out of the unconditional path into the block branch only (was printing on accept paths too). New exempt cases: `*/.claude/*`, `*/.enforcement/*`, `*/.analytics/*`, `*/holding/research/*`, `*/holding/state/*`, `*/holding/checkpoints/*`, `*/holding/hooks/hook-log.jsonl`, `*/sutra/archive/*`. Existing `*/TODO.md`, `*/BACKLOG.md`, `*/holding/*` (gated), `*/sutra/layer2-operating-system/*` (gated) preserved. |
| `tests/unit/test-cascade-check.sh` | NEW. 17 cases: 10 whitelist exit-0-silent paths, 4 blocked-path stderr-routing assertions, 1 CASCADE_ACK override accept, 1 missing-file_path defensive, 1 non-governance pass-through. |

### Behavior matrix

| Path class | Old | New |
|---|---|---|
| `holding/research/*`, `holding/state/*`, `holding/checkpoints/*`, `.enforcement/*`, `.analytics/*`, `.claude/*`, `sutra/archive/*` | BLOCKED unless TODO evidence found | exit 0 silently (whitelist exempt) |
| `holding/<governance>` non-research | BLOCKED — diagnostic to **stdout** (invisible to Claude Code) | BLOCKED — diagnostic to **stderr** (Claude Code surfaces it) |
| `holding/<governance>` with `CASCADE_ACK=1` | exit 0, message on stdout | exit 0, message on stdout (unchanged — accept paths) |
| `holding/<governance>` with TODO evidence in diff | exit 0, message on stdout | exit 0, message on stdout (unchanged — accept paths) |
| Anything outside the gated prefixes | exit 0 silently | exit 0 silently (unchanged) |

### Validation

- 14/14 unit tests pass (no regressions from v2.10.0)
- Reproduction (pre-fix): `printf '{"tool_input":{"file_path":"/foo/holding/SYSTEM-MAP.md"}}' | bash hooks/cascade-check.sh` → exit 2, stdout has 13-line diagnostic, stderr empty
- Reproduction (post-fix): same input → exit 2, stdout empty, stderr has 13-line diagnostic
- Reproduction (research path, post-fix): `/foo/holding/research/test.md` → exit 0, stdout + stderr both empty

### Why ship as v2.10.1, not fold into v2.10.0

v2.10.0 already has a tag, GitHub release, and pushed pin. Folding the cascade-check fix into v2.10.0 would mean force-bumping a published tag — disallowed. v2.10.1 is the clean increment.

### What did NOT change

- Threat model: unchanged. The D13 enforcement still HARD-blocks governance changes without TODO evidence; only the diagnostic routing + whitelist scope changed.
- API/skill/command surface: unchanged.
- Telemetry behavior: unchanged.

---

## v2.10.0 — 2026-05-01

**Inbox display ships + release packaging guard.**

Closes [issue #43](https://github.com/sankalpasawa/sutra/issues/43) (vinit, Testlify) — every `SessionStart:resume` printed `inbox-display.sh: No such file or directory` because `hooks/hooks.json` declared the hook but the script was never `git add`'d. Working tree had it; the published plugin tarball did not. Same drift class as the v2.7.1 description-vs-code incident.

### Fixes

| Item | Change |
|---|---|
| `hooks/inbox-display.sh` | Now tracked in git (was working-tree-only). FEEDBACK charter §N Close-Loop Layer V0 hook — soft-fails on every error path, two kill-switches (`SUTRA_INBOX_DISABLED=1`, `~/.sutra-inbox-disabled`). |
| `scripts/validate-hook-paths.sh` | NEW. Pre-release CI guard. Reads `hooks.json`, expands every `${CLAUDE_PLUGIN_ROOT}` command path, confirms each exists on disk AND is git-tracked. Exits non-zero with the offender list when a path is missing or untracked. |
| `tests/unit/test-validate-hook-paths.sh` | NEW. 4 cases — green plugin tree / referenced-missing-file / non-git-tree pass-with-note / empty hooks.json defensive fail. Picked up by `run-all.sh`. |

### Why this matters

Two prior releases (v2.8.5, v2.9.1) shipped the same bug because the description, the manifest, and the source tree were merged independently with no gate that all three agree. Going forward:

- Every release commit must run `scripts/validate-hook-paths.sh` and exit 0.
- `tests/run-all.sh` runs the validator's unit test, so any reviewer running tests sees the regression class is covered.

### What did NOT change

- No threat-model change.
- No API/skill/command surface change.
- No telemetry behavior change (v2.9.1 contract preserved).

### Affected versions of bug

| Version | hooks.json refs `inbox-display.sh`? | File shipped in tarball? | User-visible? |
|---|---|---|---|
| ≤ v2.7.3 | No | n/a | No |
| v2.8.5 | Yes | No | **Yes — STDERR banner on every resume** |
| v2.8.11 | Yes | No | **Yes** |
| v2.9.1 | Yes | No | **Yes** |
| **v2.10.0** | Yes | **Yes** | **No (fixed)** |

### How to update

```
/core:update
```

Or:

```
claude plugin marketplace update sutra && claude plugin update core@sutra
```

### Codex review

Validator + unit test packet self-reviewed against `validate-hook-paths.sh` v1 spec; verdict logged at `.enforcement/codex-reviews/2026-05-01-v2-10-0-release.md` if codex is reachable from the founder's session.

---

## v2.9.1 — 2026-04-30

**Telemetry: explicit opt-in during install (founder direction).**

Founder direction (2026-04-30): "when installing Sutra, give an option to switch on the telemetry — do this for the plugin." Currently `/core:start` runs onboarding silently — the user has no visible say in whether telemetry is on. v2.9.1 makes it an **explicit interactive choice** at first install.

### Behavior change

- `/core:start` now asks the user **before** running onboard:
  > "Do you want to enable Sutra telemetry to help improve the plugin? (default: no)"
- If user says **yes** → invokes onboard with `--telemetry on`
- If user says **no** (or default) → invokes onboard with `--telemetry off`
- Idempotent: skip prompt if `.claude/sutra-project.json` already exists (preserve existing setting)

### Precedence (codex review verdict ADVISORY → fold)

```
CLI flag (--telemetry on|off) > existing .claude/sutra-project.json > default OFF
```

### What changed

| File | Change |
|---|---|
| `commands/start.md` | Frontmatter description fixed (no longer claims "enables local telemetry"); body adds preflight instruction telling Claude to ASK before running; body item 2 fixed (was "telemetry_optin = true" — wrong since v2.0; now "opt-in only; default OFF"); body item 5 clarifies queue is used only if opt-in. |
| `scripts/start.sh` | New `--telemetry on\|off` CLI flag parsing. Profile-based telemetry default REMOVED (decoupled — profile governs governance enforcement only, not telemetry). New default = OFF (matches PRIVACY.md v2.0 contract; previously project/company profiles silently auto-opted-in). |

### Why default OFF (not profile-based)

Per codex consult on this design: "Keep default no. That matches PRIVACY.md v2.0 and onboard.sh's current default-false behavior. 'Ask explicitly with no default-yes' is the safest phrasing." The previous profile-based auto-opt-in for project/company silently contradicted PRIVACY.md and bypassed user consent. v2.9.1 fixes the contract gap.

### Backwards compatibility

- **Existing installs**: unchanged — `onboard.sh` preserves whatever `telemetry_optin` was already in `.claude/sutra-project.json`. No silent flip.
- **New installs of `individual` profile**: was OFF; still OFF.
- **New installs of `project`/`company` profile**: was silently ON; **now OFF unless user explicitly says yes**. Behavior change.
- **Non-interactive callers** (CI, scripts): use `--telemetry on` to get the prior default-on behavior; otherwise default OFF.

### How to flip later

- Edit `.claude/sutra-project.json` directly (`telemetry_optin: true|false`)
- Or re-run `/core:start --telemetry on` (or `off`)
- `/core:status` shows current setting

---

## v2.9.0 — 2026-04-30

**D40 governance parity — every Sutra plugin client inherits Asawa's per-turn discipline by default.**

Founder direction D40 (2026-04-30): the rich governance Asawa uses internally (Input Routing, Depth + Estimation, BLUEPRINT, codex consult before Edit/Write at Depth ≥ 3, 4-line skill cards, subagent dispatch contracts) was previously locked behind ~30 personal memories that don't ship with the plugin. Clients got skills + hooks but missed the convention layer that makes the discipline actually fire. v2.9.0 closes that gap.

### What's NEW for clients

| Surface | What you get |
|---|---|
| **Single canonical policy surface** | New `sutra-defaults.json` — machine-readable policy schema consumed by hooks at runtime via `jq`. `SUTRA-DEFAULTS.md` is the human-readable equivalent. ALL governance defaults documented in one place. |
| **Per-turn discipline reminder** | New `UserPromptSubmit` hook (`per-turn-discipline-prompt.sh`) reminds the model on every turn — including pure-question turns — to emit Input Routing + Depth blocks. Reads policy from json (no hardcoded reminder text). |
| **Codex-before-Edit policy** | `core:codex-sutra` skill now declares default policy: consult before Edit/Write/MultiEdit at Depth ≥ 3. Per `[Codex consult on everything]` discipline. |
| **4-line skill cards** | New `core:skill-explain` skill — emits 4-line WHAT/WHY/EXPECT/ASKS card before any Skill invocation so non-technical users can predict the experience. |
| **Subagent dispatch contract** | New `PreToolUse` hook on `Task` tool (`subagent-dispatch-brief.sh`) reminds Claude to brief subagent prompts with the 5-block §Sutra discipline + 4-line footer (TRIAGE/ESTIMATE/ACTUAL/OS TRACE). |
| **/core:workflow** | New slash command + skill — pedagogical wrapper that walks Claude through the full canonical Sutra discipline (8-step sequence) on a single task. Use for onboarding, pedagogy, reset, or audit. |
| **/core:start polish** | Honest inventory: 8 skills + 10 commands + 51 hooks across 6 events. Quick-start example included. References SUTRA-DEFAULTS.md for the full convention pack. |
| **5-turn acceptance harness** | New `tests/governance-parity-acceptance.sh` — `--verify <log>` checks a fresh-client session for the 5 governance behaviors using multi-line regex (perl -0777), absence assertions, and temporal ordering. Codex-reviewed 3 rounds. |

### How to update

```
/core:update
```

Or manually:
```
claude plugin marketplace update sutra && claude plugin update core@sutra
```

### Try the new surface

After update:
1. `/core:start` — see the polished onboarding with full inventory
2. `/core:workflow plan a small refactor` — see the full 8-step Sutra discipline applied
3. Run any task — observe the per-turn discipline reminder + the codex-consult policy at Depth ≥ 3

### Caveats (codex-flagged, preserved)

Hook injections of prompt text are **soft guidance only** — fragility class includes prompt dilution, prompt collision, token bloat, cosmetic emission, and subagent drift. Skills/docs EXPLAIN; hooks ENFORCE. Where a deterministic check exists, it backs the soft hint. Where it doesn't (e.g., 4-line skill cards — Claude Code lacks PreSkillUse), the convention relies on the model emitting it.

### Codex review trail

DIRECTIVE 1777505000 — D40 implementation review:
- Round 1: CHANGES-REQUIRED → v1.0.1 fold (G6 real json consumption + G7 multiline regex + kill_switches comprehensive)
- Round 2: CHANGES-REQUIRED → v1.0.2/1.0.3 fold (Q3 MultiEdit + Q1 regex tightening + Q5 contract alignment + version drift)
- Round 3: ADVISORY → gate cleared

DIRECTIVE 1777510000 — start polish + workflow skill:
- Consult: ADVISORY → renamed core:do→core:workflow + sutra-learn classification fix
- Review #1: CHANGES-REQUIRED → count drift fold (Skills 7→8, Commands 9→10, workflow.md created)
- Review #2: PASS → counts match filesystem

### Files shipped

8 new + 3 modified across plugin/:
- NEW: `SUTRA-DEFAULTS.md`, `sutra-defaults.json`, `hooks/per-turn-discipline-prompt.sh`, `hooks/subagent-dispatch-brief.sh`, `skills/skill-explain/SKILL.md`, `skills/workflow/SKILL.md`, `commands/workflow.md`, `tests/governance-parity-acceptance.sh`
- MODIFIED: `hooks/hooks.json` (registered 2 new hooks), `skills/codex-sutra/SKILL.md` (consult-before-Edit policy), `commands/start.md` (rewrite — honest inventory)

### Deferred to v2.x.y

- **G6 finalization** — rewire ALL existing Core hooks to consume `sutra-defaults.json` (currently only the 2 NEW hooks consume it; ~50 existing hooks still hardcode policies)
- **Q5 log segmentation** by tool_use boundary (full hook-vs-model provenance proof in the acceptance harness)

---

## v2.8.11 — 2026-04-28

**Vinit#38 — `/core:start` SIGKILLed by macOS sandbox/EDR on stdin-fed `python3` heredocs (P0 — bricks new-client onboarding).**

@vinitharmalkar reported (#38) on behalf of @abhishekshah that `/core:start` exits 137 (SIGKILL) on a v2.8.10 macOS install. Two `python3` subprocesses fed code via stdin heredoc (`python3 - <<'PY' ... PY`) are killed mid-execution by signal 9; bash code paths in the same script complete normally. Result: 0-byte `.claude/sutra-project.json`, partial governance block in `.claude/CLAUDE.md`, bricked onboarding.

The kill is external — likely a macOS Endpoint Detection agent (Crowdstrike, SentinelOne, Jamf MDM, Apple Endpoint Security framework, Gatekeeper) flagging stdin-fed `python3` as suspicious. Vinit's own v2.8.5 Mac on the same plugin pattern works fine, confirming this is an environment-specific kill — not a universal Sutra bug — but enough macOS setups have one of these agents that we need to defend.

### Fix (Vinit's recommendations A + B + C)

**A. File-execution form replaces stdin-fed heredocs.** All `python3 - <<'PY' ... PY` heredocs in `start.sh` and `onboard.sh` (4 total) moved into a real `.py` file: `scripts/_sutra_project_lib.py` with subcommands `patch-profile`, `write-onboard`, `stamp-identity`, `banner`. The file form is much less likely to be flagged by sandbox/EDR than stdin-fed code.

**B. SIGKILL diagnostic.** New `sutra_run_python` wrapper in `start.sh` detects exit 137 and prints a clear, actionable diagnostic — what to check (`ps -ef | grep crowdstrike/jamf/sentinel`, `codesign -d $(which python3)`), where to report, and confirmation that the user's `sutra-project.json` is not corrupted (because of fix C).

**C. Atomic writes.** All file mutations in the new helper use `tempfile + os.replace`. A SIGKILL between the temp-file create and the rename leaves the prior valid file content untouched — no more 0-byte corruption. Applies to both initial onboard write and subsequent patch.

### What changed

| File | Change |
|---|---|
| `scripts/_sutra_project_lib.py` | NEW — 4 subcommands replacing all stdin-fed python3 heredocs in start/onboard |
| `scripts/start.sh` | Heredoc 1 (line 114) + heredoc 2 (line 258) → file-form helper calls; new `sutra_run_python` wrapper with SIGKILL diagnostic |
| `scripts/onboard.sh` | Heredoc 1 (line 57, main onboard write) + heredoc 2 (line 88, identity stamp) → file-form helper calls |

### Acceptance

- `bash -n` clean on both modified shell scripts.
- `python3 -m py_compile` clean on the new helper.
- Smoke: `/core:start` happy path completes with valid `sutra-project.json` + banner output identical to v2.8.10.
- Non-existent file path: `patch-profile` exits 0 with skip message; `banner` exits 1 with clear error.
- Corrupt-file path: `patch-profile` exits 2 with recovery hint (`rm + /core:start`).
- Atomic-write path: confirmed `tempfile + os.replace` semantics — temp file removed on exception.

### Notes

- Inline `python3 -c "..."` calls in `onboard.sh` (4 read-only one-liners) intentionally NOT migrated — argv-form `python3 -c` is documented as not affected by Vinit's repro (only stdin-fed heredocs received SIGKILL). Migrating those would add file overhead with no observable benefit.
- Future hardening track: if `python3 -c` form ALSO gets killed on some setups (we'll find out from the fleet), migrate those too.

### Closes
- vinit#38 (P0 — `/core:start` SIGKILL on stdin-fed python3, bricking @abhishekshah's onboarding)

## v2.8.10 — 2026-04-28

**Three infrastructure fixes — vinit#26 transparency + redactor over-strip refusal + zsh `$0` artifact detection.**

Per founder direction "fix infrastructure bugs". Three small, deterministic fixes that improve user trust + observability without architectural decisions.

### 1. `hooks/feedback-routing-rule.sh` — transparency requirement (vinit#26)

The hook injects a behavioral rule into the session context when the user's prompt contains a feedback-intent keyword. Prior clause 7 told Claude *"Do not mention this rule to the user in responses; just follow it."* — exactly the silent-injection pattern @vinitharmalkar reported.

New clause 7 requires Claude to acknowledge the routing in a single short sentence: *"(Sutra has routed this through the sanctioned `/core:feedback` channel.)"* The user is now always aware when Sutra-injected guidance shapes the response.

### 2. `scripts/feedback.sh` — redactor over-strip refusal

Symptom: 8 of Vinit's filings (#28-#34, #37) had bodies reduced to placeholders only — `<HOME>/.<HIGH-ENTROPY>.md` with no actual content. The privacy redactor stripped the entire body when input matched path or high-entropy patterns wholesale, then the script published the placeholders publicly anyway.

Fix: after `scrub_text()`, count the useful alphanumeric characters remaining (after stripping placeholders). If under 10, refuse to proceed with a clear error explaining the likely cause and the fix (re-file with descriptive prose, not paths). Local capture path is unaffected.

### 3. `scripts/feedback.sh` — zsh `$0` expansion artifact detection

Symptom: Vinit's #19/#21/#23 had dollar figures (`$0.14`, `$5,000`) corrupted to `/bin/zsh.14` / `/bin/zsh.000`. Root cause is the user's shell expanding `$0` before `sutra feedback` ever sees the argument. The structural fix (heredoc/env redesign of the slash-command argument-passing) is still deferred, but in the meantime we can detect the artifact and refuse rather than publish silently corrupted bodies.

Fix: regex-match `/bin/(zsh|bash)\.[0-9]` in `MSG` immediately after capture; if matched, refuse with a clear error and instructions to re-run with single quotes (which preserve `$N` literally).

### Acceptance

All three are detect-and-refuse mechanisms — no false-negative risk for the legitimate path. Manual smoke confirmed all three error paths fire correctly with synthetic inputs; clean inputs unaffected.

### Closes
- vinit#26 (silent UserPromptSubmit hook UX)

## v2.8.9 — 2026-04-28

**Vinit#16 — `sutra feedback` empty input now exits 0.**

@vinitharmalkar reported (#16) that calling `sutra feedback` with no arguments prints usage to stdout but exits with code 1, which makes the `/core:feedback` slash-command invocation report failure in pipelines.

### Changed

`scripts/feedback.sh` line 65: `exit 1` → `exit 0` after the usage block. Empty input is not a failure — printing usage IS the action when no args are provided. Equivalent to most `git`/`gh` subcommand conventions where `--help` exits 0.

## v2.8.8 — 2026-04-28

**Vinit#17 second encounter — `feedback-channel-guard.sh` body-content false-positive (re-fix).**

Discovered while attempting to close vinit#36 with a comment that mentioned "gh issue create" as a concept (referring to the threat model). The shipped guard's regex `gh +issue +(create|comment)` matched the substring inside `--comment "..."` body text — same class of bug @vinitharmalkar reported in #17, which I'd previously assessed as fixed. The earlier "fix" addressed the threat-model framing but not the regex's command-vs-body discrimination.

### Root cause

`feedback-channel-guard.sh` `grep`'d the entire command line for action verbs. Any flag value (`--comment "..."`, `--body "..."`) containing the literal text `gh issue create` or `gh issue comment` triggered a false-positive block — even on legitimate operations like `gh issue close --comment "..."`.

### Fix

Replaced whole-command `grep` with explicit token parsing:

1. Strip everything after the first quoted value (`sed -E "s/[[:space:]]['\"].*$//"`) — flag bodies cannot influence the action match.
2. Read remaining tokens; locate `gh` position; extract the next two tokens (noun + verb).
3. Match against `(noun, verb)` tuples directly: `(issue, create)`, `(issue, comment)`, `(pr, create)`, `(pr, comment)`, `(pr, review)`.
4. `gh api` mutation detection unchanged (its parameters always live unquoted on the line, so whole-string scan is acceptable).

### Acceptance — 8/8 tests pass

| Test | Expected | Result |
|---|---|---|
| `gh issue close 36 ... --comment "guard blocks unsanctioned gh issue create paths"` | pass (false-positive case) | ✅ pass |
| `gh issue create -R sankalpasawa/sutra ...` | block | ✅ block |
| `gh issue comment -R sankalpasawa/sutra ...` | block | ✅ block |
| `gh issue close -R sankalpasawa/sutra --comment "..."` (simple) | pass | ✅ pass |
| `gh issue create -R someother/repo ...` | pass | ✅ pass |
| `gh api -X POST /repos/sankalpasawa/sutra/issues ...` | block | ✅ block |
| `gh pr create -R sankalpasawa/sutra ...` | block | ✅ block |
| `gh issue close ... --comment "...gh issue comment was matched..."` | pass | ✅ pass |

### Why this matters

The original false-positive @vinitharmalkar reported in #17 was discovered when the guard blocked legitimate `sutra feedback --public` invocations whose feedback-text body contained the repo name. The threat-model fix in v2.6.2 addressed that specific path (the sanctioned binary) but left this broader class of false-positive in place. Confirmed in the wild today (2026-04-28) when an attempt to close #36 with a descriptive comment was blocked.

## v2.8.7 — 2026-04-28

**Vinit#36 — slash-command zsh history-expansion fix (8 command files).**

@vinitharmalkar reported (issue #36, 2026-04-28) that `/core:start` fails with exit 127 on zsh: the `!`-prefix line in the slash-command file (`!${CLAUDE_PLUGIN_ROOT}/bin/sutra start`) reaches zsh's `eval`, where the leading `!` triggers history expansion (`(eval):1: no such file or directory: !/path/to/sutra`). The `!`-prefix syntax is **not the documented Claude Code slash-command auto-execute mechanism**; the canonical form is a fenced bash code block that Claude reads and executes via the Bash tool. Confirmed via Claude Code documentation lookup.

### Changed

All 8 affected command files migrated from broken `!`-prefix form to documented fenced-bash form:

| File | Subcmd |
|---|---|
| `commands/start.md` | `sutra start` |
| `commands/feedback.md` | `sutra feedback "$ARGUMENTS"` |
| `commands/learn.md` | `sutra learn $ARGUMENTS` |
| `commands/permissions.md` | `sutra permissions` |
| `commands/sbom.md` | `sutra sbom` |
| `commands/status.md` | `sutra status` |
| `commands/uninstall.md` | `sutra uninstall $ARGUMENTS` |
| `commands/update.md` | `sutra update` |

Pattern (before/after):

```diff
- !${CLAUDE_PLUGIN_ROOT}/bin/sutra start
+ Run this command via the Bash tool:
+
+ ```bash
+ ${CLAUDE_PLUGIN_ROOT}/bin/sutra start
+ ```
```

### Why the new form works

The fenced-bash block is read by Claude (the model), which then emits a `Bash` tool call. Claude Code's Bash tool runs the command in a controlled bash environment — it does NOT pass through the user's interactive zsh, so `!` history expansion never triggers. This works identically across bash, zsh, fish, and any other user shell.

### Acceptance

- `grep -rn "^!" commands/` returns zero matches.
- All 8 files contain a `\`\`\`bash` fenced block with the prior invocation.
- Plugin smoke unaffected (slash-command files are pre-Claude-rendered, no syntax to break at install time).

### Not addressed in this version

- The zsh `$0`/`$N` expansion bug in `sutra feedback --public` body (separate issue, deferred to a future round; rooted in `$ARGUMENTS` substitution semantics, not the `!`-prefix). Tracked in v2.8.6 changelog "Not addressed" section.

## v2.8.6 — 2026-04-28

**Vinit feedback round — two deterministic fixes (`vinit#25` bug 2 + `vinit#35`).**

Round of marketplace-feedback closures from @vinitharmalkar's reports filed 2026-04-28. Two bugs that had clear specs and surgical fixes are addressed here; non-deterministic issues (#8 plugin/holding L1 layering, #26 hook-transparency UX, zsh `$0` expansion at command-substitution boundary) deferred pending design decisions.

### Fixed

- **`scripts/feedback.sh` — derive GitHub issue title from first content line** (vinit#25 bug 2). Prior behavior: every `sutra feedback --public` invocation produced an issue titled `[feedback v${PLUGIN_VERSION}] from plugin`, regardless of body — making the inbox untriageable (16+ identical titles in #16-#34). New behavior: title is `[v${PLUGIN_VERSION}] <first non-blank, non-frontmatter, non-redacted content line, capped at 80 chars>`. Falls back to the legacy generic format only when the body has no usable line. Awk-based extraction (single-pass, bash-3.2-safe). Version prefix retained for filterability. Tested with 6 cases (Bug:/Feature: prefixes, leading blanks, frontmatter separators, fully-redacted bodies, long lines, empty input).

- **`scripts/start.sh` — accept `.claude/` directory as a valid project marker** (vinit#35). Prior behavior: `/core:start` refused to activate in directories that contain `.claude/settings.local.json` or `.claude/heartbeats` but lack `.git/`/`package.json`/`pyproject.toml`/`Cargo.toml`/`go.mod`/`CLAUDE.md`, requiring users to discover `--force`. New behavior: `.claude/` directory presence is sufficient to identify a Claude Code project. Marker list in error message updated to surface `.claude/`. Existing protections (HOME-dir refusal, `/`/`/tmp` refusal, canonical-path symlink-resolution) preserved. Smoke-tested: a tempdir with only `.claude/settings.local.json` is now accepted.

### Not addressed in this version (deferred)

- **vinit#8** (Assistant Interaction Layer ships as L1 in marketplace plugin; observer not registered in hooks.json; `holding/` paths missing on user machines) — requires architectural decision: promote observer to L0 + register, or strip the `sutra explain/ask/answer/pending` subcommands from `bin/sutra`. Tracked separately.
- **vinit#26** (feedback-routing-rule hook silently injected via UserPromptSubmit; user has no UI surface) — requires UX design for transparency surfacing.
- **zsh `$0` expansion bug** (dollar amounts like `$0.14` corrupted to `/bin/zsh.14` in published feedback bodies) — root cause is at the Claude-Code `$ARGUMENTS` text-substitution boundary in `commands/feedback.md`; fix requires moving body delivery to a quoted heredoc / env-passing path with split flag parsing in `feedback.sh`. Tracked separately.

### Acceptance

- `bash -n scripts/feedback.sh` and `bash -n scripts/start.sh` clean.
- 6/6 title-derivation cases pass under bash 3.2 (macOS default).
- `.claude/`-only tempdir accepted by the marker-check; HOME-dir / `/tmp` refusals preserved.

## v2.8.5 — 2026-04-28

**D38 Wave 9 — Bucket C activation: 10 promoted hooks now registered in plugin hooks.json (fleet-wide auto-fire).**

Per founder direction "finish it off as well", 10 of the 28 Bucket C hooks promoted in v2.8.4 are now activation-wired in plugin hooks.json — they fire fleet-wide automatically on /core:update, not just for Asawa via settings.json pointer.

### Hooks activated

- **SessionStart**: session-start-rotate
- **PreToolUse Edit|Write**: blueprint-check
- **PreToolUse Write|Edit|MultiEdit**: self-assess-before-foundational, input-classification-gate
- **PostToolUse Edit|Write**: process-fix-check
- **PostToolUse Bash|Edit|Write**: agent-completion-check (new matcher)
- **PostToolUse Write**: onboarding-self-check, narration-not-artifact (new matcher)
- **Stop**: policy-only-sensor, context-budget-check

### Hooks NOT activated (canonical-only, no auto-fire)

- **auto-push** — Stop hook would auto-push every session for every fleet client; deferred pending per-client config (T2/T3/T4 may not want auto-push).
- 17 other Bucket C hooks (architecture-awareness, check-graduation, hook-health-sensor, kpi-tracker, latency-collector, lifecycle-check, new-path-detector, output-behavior-lint, principle-regression, research-cadence-check, rotate-logs, rtk-health-check, session-checkpoint, test-in-production-check, time-allocation-tracker, triage-collector, tripwire-hook-sizes) — not currently invoked from holding/.claude/settings.json; canonical files exist in plugin/hooks/ for any future activation. Per-hook event-matcher analysis required for each; no need to auto-activate vestigial hooks.

### Acceptance

After /core:update, fleet clients running Sutra v2.8.5 get blueprint-check, self-assess, input-classification, process-fix, agent-completion, onboarding-self-check, narration-not-artifact, policy-only-sensor, context-budget-check, session-start-rotate firing automatically — no settings.json customization required. D38's "canonical = distributed + activation-wired + released" criterion is now met for these 10.

### Wave plan — D38 COMPLETE

This is the last D38 wave. Remaining items deferred-by-design:
- 17 vestigial Bucket C canonicals: live in plugin/hooks/ but no auto-fire registration. Future wave can activate per-hook on demand.
- Bucket D L2 in-file headers: cosmetic; promotion ledger already documents WHY_NOT_L0_KIND for each.
- Wave-3 shim deletion (pre-commit-test-gate, mark-tests-ran in holding/hooks/): safe to keep until callers all updated; revisit at 2026-05-05 retire-by.

## v2.8.4 — 2026-04-28

**D38 Waves 6+7 — Bucket C bulk promotion (28 governance hooks → plugin canonical).**

Per founder direction "finish all the rest of the things" + D38 §Acceptance ("documented disposition within 14 days, target 2026-05-12"), 28 Bucket C governance hooks moved from holding/hooks/ to sutra/marketplace/plugin/hooks/. Plugin is now the canonical home for them.

### Hooks promoted (28)

agent-completion-check, architecture-awareness, auto-push, blueprint-check, check-graduation, context-budget-check, hook-health-sensor, input-classification-gate, kpi-tracker, latency-collector, lifecycle-check, narration-not-artifact, new-path-detector, onboarding-self-check, output-behavior-lint, policy-only-sensor, principle-regression, process-fix-check, research-cadence-check, rotate-logs, rtk-health-check, self-assess-before-foundational, session-checkpoint, session-start-rotate, test-in-production-check, time-allocation-tracker, triage-collector, tripwire-hook-sizes.

### What does NOT change in this version

- These hooks are NOT yet registered in plugin hooks.json (each requires per-hook event-matcher analysis — deferred to a follow-up wave). Marketplace consumers see canonical files in plugin/hooks/ but no automatic activation. Holding-side consumers (Asawa) continue to invoke them via existing settings.json (paths updated in companion holding commit to point at plugin canonicals).
- Asawa-specific hooks (Bucket D — high holding/Asawa references) stay at holding/hooks/ with `WHY_NOT_L0_KIND=instance-only` headers (separate commit).

### What's still pending

- Wave 8 (companion holding commit): update holding/.claude/settings.json to point at plugin canonicals + delete holding/hooks/ shims and Bucket C originals.
- Wave 9 (future): per-hook plugin hooks.json registration so promoted Bucket C hooks fire fleet-wide automatically.

## v2.8.3 — 2026-04-28

**D38 Wave 3 — `pre-commit-test-gate.sh` + `mark-tests-ran.sh` paired promotion to `sutra/hooks/` (shared-runtime carve-out).**

Per codex amendment (DIRECTIVE-ID 1777362899), git/runtime universal hooks live at `sutra/hooks/` (parallel L0 surface to `marketplace/plugin/hooks/`). These are NOT Claude Code marketplace hooks — they're git pre-commit hooks invoked from `.git/hooks/pre-commit` wrapper. Promoting them to `sutra/hooks/` makes them canonical for Sutra-tree dev workflows.

### What changed

- `sutra/hooks/pre-commit-test-gate.sh` — synced from holding's latest. Existing file (since 6b088db); now D38-aware.
- `sutra/hooks/mark-tests-ran.sh` — synced from holding's latest. Existing file; now paired explicitly with the test-gate per codex's "treat as one mechanism" recommendation.

### Note on this version bump

This is an infrastructure update — not a marketplace plugin feature. The bumped version is for visibility in the v2.8.x sequence; consumers on `/core:update` see no behavior change in plugin hooks (the shared-runtime hooks live in the Sutra source tree, not in the marketplace plugin path).

### Wave plan continuation

- Wave 4+: Bucket A — 22 silent mirror retirement, shim or delete.

## v2.8.2 — 2026-04-28

**D38 Wave 2 — `structural-move-check.sh` (PROTO-025) plugin L0 promotion.**

PROTO-025 enforcement (unauthorized rm/mv/git mv on HARD paths — closes the 2026-04-06 evolution-archive incident) moves from `holding/hooks/` (Asawa-only) to `sutra/marketplace/plugin/hooks/` (fleet L0). Same atomic-cutover pattern as Wave 1.

### What changed

- `hooks/structural-move-check.sh` — new in plugin (211 lines). Gates Bash structural ops (`mv`, `rm`, `git mv`, `git rm`, `find -delete`, `bash -c` containing destructive shell) on the same HARD path list as `build-layer-check.sh` (PROTO-021 + D38). Same marker schema; same override path; same audit ledger.
- `hooks/hooks.json` — registers `structural-move-check.sh` on PreToolUse `Bash`.
- Plugin version 2.8.1 → 2.8.2.

### Wave plan continuation

- Wave 3: `pre-commit-test-gate.sh` + `mark-tests-ran.sh` paired promotion to `sutra/hooks/` (shared-runtime carve-out).
- Wave 4+: Bucket A — 22 silent mirror retirement, shim or delete.

## v2.8.1 — 2026-04-28

**D38 Wave 1 — `build-layer-check.sh` plugin L0 promotion (HARD enforcement now fleet-distributed).**

Per D38 (`holding/FOUNDER-DIRECTIONS.md` §D38) and codex consult DIRECTIVE-ID 1777362899, the `build-layer-check.sh` HARD-enforcement hook moves from `holding/hooks/` (Asawa-only) to `sutra/marketplace/plugin/hooks/` (fleet L0). The hook implements PROTO-021 + D38 with structured marker schema + plugin-first decision logic.

### What changed

- `hooks/build-layer-check.sh` — new in plugin (385 lines). Five path categories (D38_PLUGIN_RUNTIME, D38_SHARED_RUNTIME, D38_HOLDING_IMPL, LEGACY_HARD, SOFT). Codex's exact decision logic. Override audit emits `path` + `actor` + `cmd` + `reason` + `ts` + `session_id` + `declared_layer` + `override_kind`. Backward compat: LEGACY_HARD paths accept old single-line marker.
- `hooks/hooks.json` — registers `build-layer-check.sh` on PreToolUse `Write|Edit|MultiEdit`.
- Holding copy at `holding/hooks/build-layer-check.sh` (Asawa repo) becomes a 4-line shim per D38 §5 mirror retirement rule (canonical = plugin; retire-by 2026-05-05).

### Impact

Every fleet-installed Sutra plugin gets D38 HARD enforcement on next `/core:update`. Plugin-runtime files require `LAYER=L0`; holding-implementation paths require structured L1/L2 justification. Phantom-feature class becomes structurally impossible across the fleet — not just at Asawa.

### What does NOT change

- LEGACY_HARD paths (`holding/departments/**`, `holding/evolution/**`, `holding/FOUNDER-DIRECTIONS.md`, `sutra/os/charters/**`) keep PROTO-021 original semantics: marker present (any content) = pass. Backward compat preserved for clients on older marker schemas.
- Override path (`BUILD_LAYER_ACK=1 BUILD_LAYER_ACK_REASON='<reason>'`) unchanged in API; logging schema enriched.

### Codex review

Verdict files: `.enforcement/codex-reviews/d38-codex-consult-1777362899.md` (Pass 1 ADVISORY) + `d38-codex-impl-review-1777362899.md` (Pass 2 ADVISORY). Two structural refinements absorbed (canonical = distributed + activated + released; sutra/hooks/ carve-out for shared runtime; marker schema upgrade). Two implementation findings absorbed (override JSON `path` field; marker single-line documented).

### Wave plan continuation

- Wave 2 (next): `structural-move-check.sh` (PROTO-025) plugin L0 promotion, same atomic pattern.
- Wave 3: `pre-commit-test-gate.sh` + `mark-tests-ran.sh` paired promotion to `sutra/hooks/` (shared-runtime carve-out).
- Wave 4+: Bucket A — 22 silent mirror retirement, shim or delete, 7-day TTL max per codex.

## v2.8.0 — 2026-04-28

**codex-sutra v1.0.0 — Sutra-owned codex CLI wrapper, replaces gstack /codex for PROTO-019.**

Founder direction (2026-04-28): "we have to provide this skill to all the clients of Sutra, so it goes by default. We use this skill only when we are trying to review by codex going forward."

### Added

- **`marketplace/plugin/skills/codex-sutra/SKILL.md`** (540 lines) — full skill spec with four modes:
  - **Review (2A)** — git-diff codex review with P1/P2 gate (`high` reasoning effort).
  - **Challenge (2B)** — adversarial mode looking for production failure modes (`high`).
  - **Consult (2C)** — free-form Q&A with session continuity via `.context/codex-session-id` (`medium`).
  - **Design-review (2D)** — single-file review of specs, plans, RFCs (`medium`). Used during this very release for self-review of v1→v2→v3 of the SKILL.md itself.
- Forked from gstack `/codex` skill v1.0.0 (`~/.claude/skills/gstack/codex/SKILL.md`, observed 2026-04-28). Quarterly upstream-sync cadence documented inline.

### Changed vs gstack /codex (5 functional changes — not a one-line fork)

1. **Hard cap 5m → 15m.** Bash foreground `timeout: 300000` is too short for `high`-effort reviews on medium diffs. Bash foreground hard-caps at 10m anyway, so a 15m cap requires background execution.
2. **Foreground timeout → background + wrapper polling.** Codex runs in its own process group (`setsid` or python `os.setsid()` fallback), polled every 30s. Three liveness thresholds: stall warn at 5m no-output, progress warn at 10m wall-clock, hard kill at 15m via `kill -TERM -<pgid>` (whole-group, closes the v2 hole where killing only the subshell PID could leave codex running past the cap).
3. **Log path** `~/.gstack/.../review-log` → `.enforcement/codex-reviews/gate-log.jsonl` (the canonical PROTO-019 path).
4. **Filesystem-boundary list extended** to exclude `sutra/marketplace/plugin/skills/` and `sutra/marketplace/plugin/hooks/`.
5. **Canonical for codex-by-codex review under PROTO-019**, replacing gstack `/codex` only for that path. Other gstack skills unaffected.

### Fail-closed semantics for non-model failures

PROTO-019 gate is fail-closed for every infra error path (codex auth error, codex crash, empty response, malformed output, hard-cap timeout, log-write failure, session-id write failure). Each maps to `GATE: FAIL` with a structured `reason` code so callers can branch on infra-fail vs model-fail.

### Failure durability — three result channels

PROTO-019 hooks need an observable verdict even when the primary log-write fails. Three channels in priority order: (1) primary `.enforcement/codex-reviews/gate-log.jsonl` JSONL append, (2) fallback `/tmp/codex-sutra-fail-<directive_id>-<ts>.json`, (3) stderr `CODEX-SUTRA-RESULT verdict=... reason=... directive=... commit=...` beacon. Skill exit code mirrors verdict (0 for PASS/ADVISORY, 1 for CHANGES-REQUIRED/FAIL, 124 for hard-cap timeout). PROTO-019 hooks treat non-zero exit + no readable verdict file as `reason=infra_silent`.

### Other invariants documented in skill

- **Single-writer rule** for `$TMPDONE` (wrapper-only). Subshell writes only `$TMPNAT` (its own exit code). Eliminates the v2 race where two writers could clobber each other.
- **Stdin closed via `</dev/null`** on all `codex exec` invocations. Without it, `codex exec` blocks indefinitely waiting on stdin even when a prompt is provided as argv (discovered the hard way during this skill's own v2 design-review iteration).
- **Orphan reaping**: every codex-sutra invocation prepends `find /tmp/codex-sutra-* -mmin +1440 -delete` to clean prior crashed-session artifacts.
- **gate-log.jsonl JSONL schema** documented inline (12 fields) + rotation logic with `flock` (or `mkdir`-based fallback on macOS without flock) at 10MB.
- **Single active consult per repo** (v1 limitation; v2 will add file-locking + session registry).

### Rollout (staged, gated by infra-fail observation)

| Tier | Cohort | Window | Gate to advance |
|---|---|---|---|
| T2 (owned) | DayFlow, Billu, Paisa, PPR, Maze | Week 1 | Zero infra-fail verdicts in gate-log.jsonl |
| T3 (projects) | Testlify, Dharmik | Week 2 | Same gate + founder sign-off |
| T4 (Sutra users / fleet) | External adopters | Week 3+ | Same gate + announcement in feedback channel |

Skill is identical across tiers; only PROTO-019 hook activation differs.

### PROTO-019 hooks updated to point at /codex-sutra

- `marketplace/plugin/hooks/codex-directive-gate.sh` — two user-facing messages (lines 106, 130) now read `Run /codex-sutra review` and `re-run /codex-sutra review`.
- `marketplace/plugin/hooks/codex-review-gate.sh` — three references (line 6 header comment, lines 98, 107) all updated to `/codex-sutra review` form.
- All five message changes are pure text/comment changes; no semantic behavior change.

### Bug fix — codex-directive-detect.sh false-positive

`codex-directive-detect.sh` (UserPromptSubmit hook) was matching codex-related keywords inside system-emitted XML wrappers — `<task-notification>`, `<system-reminder>`, `<command-name>`, `<command-message>`, `<command-args>`, `<local-command-stdout>`, `<local-command-stderr>` — which the harness injects into the `.prompt` field when background tasks complete or local slash commands run. Every background codex review during the codex-sutra v1→v2→v3 iteration spawned a false-positive directive marker that required a separate verdict file to clear, creating cascading governance friction.

Fix: a perl-based system-XML strip step inserted between the empty-prompt guard and the existing fenced-code-block stripping. Allowlist-based (the seven harness-emitted tag names above). Falls back gracefully to original prompt if perl unavailable (regression-equivalent). 6/6 unit tests pass (XML cases stripped, genuine asks still match, negation suppression intact, regression test for the exact phrase that caused this session's first false positive).

### Codex review chain (audit trail)

- **codex-sutra design**: v1 CHANGES-REQUIRED (6 P1, 8 P2; 40,736 tokens) → v2 CHANGES-REQUIRED (2 P1, 2 P2; 45,375 tokens) → v3 ADVISORY (0 P1, 2 PARTIAL items resolved post-review; 46,726 tokens) → ship.
- **PROTO-019 hook fix proposal**: v1 CHANGES-REQUIRED (1 P1: A2/A3 inconsistency; 42,270 tokens) → v2 PASS (41,072 tokens) → delta PASS for two missed `/codex` references (39,547 tokens) → ship.
- Total codex spend: ~256K tokens, ~$0.75–1.00.
- Verdict files: `.enforcement/codex-reviews/2026-04-28-codex-sutra-design-v1.md`, `2026-04-28-codex-sutra-design-v3.md`, `2026-04-28-hook-fix-proposal-pass.md` (plus two false-positive verdict files for directives 1777355386 and 1777355668 — the very class of false positive Change B fixes; documented for traceability).

### What does NOT change

- gstack `/codex` skill itself remains untouched at `~/.claude/skills/gstack/codex/SKILL.md`. Only the **canonical-for-PROTO-019** designation moves to codex-sutra.
- Verdict-file format (`DIRECTIVE-ID:` + `CODEX-VERDICT:`) is identical between gstack and codex-sutra. Existing verdict files remain valid.
- PROTO-019 protocol semantics, marker file paths, gate exit codes — all unchanged.

### Known issue (pre-existing, not blocking)

`marketplace/plugin/tests/unit/test-codex-directive-detect.sh` and `test-codex-directive-gate.sh` reference the v2 single-slot marker path `.claude/codex-directive-pending` (no SID suffix), but the v3 hook (shipped 2026-04-25) writes session-scoped markers `.claude/codex-directive-pending-<SID>`. 9 of 12 tests in each suite report false failures because they look at the v2 path. Pre-existing test rot from the 2026-04-25 v3 transition; tracked as a separate follow-up. My change to detect.sh is purely additive (XML strip step) and does not affect these failures — verified by running 6 targeted unit tests independently (all pass) plus reading the diff (one block added, no existing logic modified).

### Out of scope

- Updating the pre-existing test rot in test-codex-directive-detect.sh and test-codex-directive-gate.sh.
- Adding codex CLI install to a Sutra installer (no `install.sh` exists yet; T2 clients are assumed to have codex via npm).
- Plugin README mention of codex-sutra (separate doc-update commit).
- Reaping the orphan v2 marker `.claude/codex-directive-pending-156aa0a5-...` from a dead session (separate cleanup).

## v2.7.3 — 2026-04-28

**Honesty pass II — RTK opt-in disclosure + telemetry banner truth (vinit#7, vinit#9).**

Vinit (Testlify) reported two more phantom-feature gaps:

- **gh#7 (RTK)** — README advertises `rtk auto-rewrite` for "30-60% tool-output reduction"; the hook is registered and ships. But the `rtk` binary is not bundled with the plugin or any install path; on machines without it, the hook silently exits 0 and the feature is inert. Users believe context bloat is being managed; it isn't.
- **gh#9 (telemetry)** — `/core:start` banner reads `Telemetry: on`; `push.sh` line 19 unconditionally exits with "push disabled in v2.0 privacy model" unless `SUTRA_LEGACY_TELEMETRY=1`. Banner copy is misleading — push is off regardless of `telemetry_optin` flag.

### Banner reflects real state

- `scripts/start.sh` activation banner now derives **two new lines** from runtime state:
  - `Telemetry: local-only — push disabled in v2.0 privacy model (see PRIVACY.md)` when `telemetry_optin=true` and legacy push not active. Shows `on — legacy push active` only when `SUTRA_LEGACY_TELEMETRY=1`. Shows `off` when opt-in flag false.
  - `RTK rewrite: active` when `rtk` binary is on PATH and `~/.rtk-disabled` absent. `inactive — rtk binary not installed (opt-in; see README)` otherwise.

### README honest about external deps

- RTK feature line marked **(opt-in)**; explicit "requires `rtk` binary installed separately (not bundled with the plugin)"; kill-switch path documented inline.
- Telemetry feature line marked **(v2.0+ privacy model)**; explicit "push to a data store is disabled by default"; legacy reactivation path documented.
- Removed stale `Session retrieve — recover abruptly-closed sessions after a laptop crash` line (consistency with v2.7.2 plugin removal).

### What does NOT change

- `rtk-auto-rewrite.sh` hook code unchanged — already correctly silently exits when binary missing. The bug was discovery/disclosure, not behavior.
- `push.sh` v2.0 privacy gating unchanged — that's by design, not a bug. Users who want fleet telemetry can still set `SUTRA_LEGACY_TELEMETRY=1`.
- No rtk binary bundled with the plugin (out of scope: supply-chain implications, multi-platform builds).

### Out of scope

- Strategic decision on telemetry: do we re-enable a privacy-respecting push channel so the team can see fleet usage? (Currently we have zero data from any external client — see vinit#9 follow-up.) Founder call needed.
- vinit#6 memory-honesty (Sutra memory vs Claude native).

## v2.7.2 — 2026-04-28

**Honesty pass — stop advertising session-retrieve in the core plugin (vinit#6 partial fix).**

Vinit (Testlify) reported in gh#6 that the `/core:start` banner hardcodes `session-retrieve` as a "loaded skill" but no SKILL.md ships in the plugin. The skill folder lives at `sutra/skills/session-retrieve/` (Sutra OS extensions tree), not at `marketplace/plugin/skills/`. Founder direction 2026-04-28: don't advertise it from the plugin; keep it as a Sutra extensions skill only for now.

### Files changed

- `scripts/start.sh:265` — banner string drops `session-retrieve` from "Skills loaded" line.
- `.claude-plugin/plugin.json` — `keywords[]` drops `session-retrieve`; version → 2.7.2.
- `.claude-plugin/marketplace.json` (Sutra repo root) — `keywords[]` drops `session-retrieve`; description text scrubs the "Includes session-retrieve…" sentence; version → 2.7.2.

### What does NOT change

- Skill folder at `sutra/skills/session-retrieve/` is left in place — it remains available for users who explicitly load Sutra extensions.
- Banner does not yet list `blueprint` and `sutra-learn` skills which DO ship in plugin/skills/. Tracking as a separate honesty gap (banner is hardcoded — dynamic detection is a larger refactor; see vinit#6 follow-up).

### Out of scope this turn

- README claim about session-retrieve (no current README mention found in plugin/README.md).
- Memory-system honesty pass per vinit#6 (the bigger CLAUDE.md-vs-Claude-native-memory question — needs strategic call).
- Dynamic banner skill detection.

## v2.6.0 — 2026-04-27

**PROTO-024 V1 — client→team feedback fanout (collaborator-visible inbox).**

Closes the gap from the 2026-04-24 vinitharmalkar incident: T4 strangers had no way to send feedback to the Sutra team. PROTO-024 V1 reuses the existing `sankalpasawa/sutra-data` git rail — clients scrub locally and push to `clients/<install_id>/feedback/<ts>.md`. Honest disclosure in PRIVACY.md: this is a **collaborator-visible inbox, not a private team-only channel**. V2 (planned) adds client-side encryption (RSA-4096 + AES-256-CBC via openssl) to close the cross-tenant readability gap.

Codex review (DIRECTIVE-ID 1777062127 + 1777058308) at `.enforcement/codex-reviews/2026-04-25-proto-024-feedback-fanin-and-reset-hook-fix.md`. Round-1 FAIL on transport choice (codex preferred Cloudflare Worker); founder picked V1-on-existing-rail with iterate-to-V2 plan. Round-2 FAIL on wording ("don't claim stringent"); fixed via honest disclosure throughout PROTOCOLS.md + PRIVACY.md. Round-3 verification pending.

### Added

- **`fanout_to_sutra_team()`** in `scripts/feedback.sh`: scrubs content, ensures `~/.sutra/sutra-data-cache/` clone, sweeps prior-unmarked feedback files (≤7d), pushes each via explicit-path `git add clients/<install_id>/feedback/<fname>` + commit + push. Touches `<src>.uploaded` marker on success. User-driven retry only (no Stop hook, no cron).
- **Kill-switches** for fanout: `--no-fanout` flag, `SUTRA_FEEDBACK_FANOUT=0` env, `~/.sutra-feedback-fanout-disabled` file. Any one disables. Local capture proceeds regardless.
- **Strengthened `scrub_text()`** in `lib/privacy-sanitize.sh`: GitHub `gh[posru]_` tokens, OpenAI `sk-(proj-)?` keys, AWS `(AKIA|ASIA)`, Slack `xox[abprs]-`, Stripe `(sk|pk|rk)_(live|test)_`, Bearer tokens, Slack/Discord webhook URLs, S3/GCS/Azure signed URL params, DSNs, KEY=val, E.164 phones, plus a 40+ character high-entropy fallback for anything regex misses by name.
- **PROTO-024 spec** in `sutra/layer2-operating-system/PROTOCOLS.md` with HONEST V1 wording (collaborator-visible inbox; V2 plan documented).

### Changed

- **`/core:feedback` decoupled from `SUTRA_TELEMETRY=0`**: manual feedback now works even when telemetry is fully off (codex L17 finding). The two opt-outs are independent.
- **`scripts/push.sh` STOP writing `manifest.identity`** on new versions: closes the v1.9.0 PII leak that stamped `github_login` / `github_id` / `git_user_name` into remote manifests on every telemetry push. Pre-v2.6.0 manifests on remote are left intact (no retroactive scrub; planned for V2 transport replacement).
- **`reset-turn-markers.sh` registration moved from `UserPromptSubmit` to `Stop` event** (both `.claude/settings.json` and `sutra/marketplace/plugin/hooks/hooks.json`): structurally closes the spoof vulnerability where a real user prompt containing a sentinel string could suppress per-turn governance reset. Fires only at assistant turn end where there is no synthetic-turn ambiguity. Content-pattern detection logic in the script body becomes dead code (preserved for now; remove in next cleanup).
- **`hooks/keys-in-env-vars.sh`** (both holding L1 + plugin L0 copies): added `lib/privacy-sanitize.sh` and `tests/test-scrub*` to the path whitelist. Privacy-scrub libraries legitimately contain API-key SHAPE PATTERNS; without this whitelist the scrubber cannot be improved. Path-pinned, does not widen general attack surface.
- **PRIVACY.md** updated with v2.2.0 changelog entry + main body fanout disclosure + kill-switch documentation.

### Migration

- Existing T1/T2 installs: scrubbed feedback now lands on remote when users run `/core:feedback`. No action needed; PRIVACY.md disclosure covers expectations.
- Existing T3/T4 installs: same. Users who want zero outbound transmission set `SUTRA_FEEDBACK_FANOUT=0` or `touch ~/.sutra-feedback-fanout-disabled`.
- Plugin reload required to pick up the new `hooks.json` registration. Run `/reload-plugins` in any active Claude Code session.

### Deferred to V2 (documented as TODO in PROTOCOLS.md PROTO-024)

- Client-side encryption with shipped Sutra public key (closes H1/H10 cross-tenant readability)
- Random 128-bit `install_id` (closes H3 deterministic-id linkage)
- Random UUID filenames on remote (breaks install↔file link)
- Hard-delete on remote (currently soft via reap; history retains scrubbed payload)
- Documented key-rotation policy

## v2.5.0 — 2026-04-27

### Added
- **Tier 1.6 Trust Mode** in `permission-gate.sh`: inverts v2.4 strict
  allowlist to a denylist. Auto-approves every Bash command except those
  matching one of 6 prompt categories. Closes founder approval-fatigue
  feedback ("I am just saying yes, yes, yes to things... the architecture
  design itself should handle this").
- New: `lib/sh_trust_mode.py` — regex/case detector for the 6 categories.
  Fail-safe-to-prompt on errors.
- New: `tests/unit/test-sh-trust-mode.sh` — 60+ test cases covering all 6
  prompt categories and ~30 auto-approve cases.
- Charter `PERMISSIONS.md` §4: new Tier 1.6 block with normative threat
  model + detection table + recovery model + exit ramp.
- `bash-summary-pretool.sh` mirrors trust-mode fast-path so summarizer
  skips entirely when trust-mode auto-approves.

### Six Prompt Categories
1. Git history mutations (commit, push, pull, rebase, merge, reset --hard,
   checkout branch, push --force, branch -D, tag -d, stash drop, clean -f)
2. Privilege escalation (sudo, su, doas, pkexec)
3. Recursive deletes outside safe-path allowlist (build/dist/cache/tmp ok)
4. Disk/system catastrophes (dd, mkfs.*, chmod -R, chown -R, diskutil,
   launchctl, defaults, fdisk, parted, mount, umount, kextload)
5. Fetch-and-exec (curl|sh, wget|bash, etc.)
6. Remote/shared-state (gh, ssh, scp, rsync, aws, gcloud, kubectl, helm,
   ansible, terraform, vercel, supabase, doctl, fly, heroku, render,
   railway, netlify, npm/yarn/pnpm/bun publish, docker push/login,
   pip/twine/poetry upload/publish, psql/mysql/mongo/redis-cli/sqlite3)

### Threat Model
"Trust Mode assumes a single trusted local operator on a personally managed
machine, no adversarial prompt/file/environment injection, and reserves
prompts only for commands with high risk of irreversible local loss,
privilege escalation, or remote/shared-state mutation."

### Review
Codex round 1: MODIFY (add 6th category for remote state, narrow recursive-
delete allowlist, accept regex heuristic). All 3 conditions absorbed.
Claude plan-eng-review: GO. Both converged.

### Compatibility
v2.4 Tier 1.5 (strict compositional reads) remains as second matcher in
permission-gate.sh dispatch — pattern names like
`Bash(compositional-read:ls+grep+tail)` still persist to settings.local.json.
Trust mode is third matcher and covers everything else.

### Kill-switch
Unchanged: `SUTRA_PERMISSIONS_DISABLED=1` or
`touch ~/.sutra-permissions-disabled`.

## v2.4.0 — 2026-04-25

### Added
- **Tier 1.5 compositional reads** in `permission-gate.sh`: auto-approves
  read-only shell pipelines over a fixed primitive whitelist (ls, cat, head,
  tail, wc, echo, printf, pwd, date, whoami, which, basename, dirname,
  realpath, grep, cut, uniq (≤1 path), tr (stdin-only), column) composed via
  `; && || |` and stderr redirects (`2>&1`, `2>/dev/null`).
- New file: `lib/sh_lex_check.py` — Python shlex-based tokenizer with
  per-primitive argv validators, 5-gate architecture (hard rejects, env
  shadowing delegated to hook, tokenize+fold, pipeline ops, primitive +
  argv validation).
- New file: `scripts/rollback-compositional.sh` — idempotent cleanup for
  rolled-back installs (strips `Bash(compositional-read:*)` from
  `.claude/settings.local.json`, creates .pre-rollback.bak).
- New tests: `tests/unit/test-sh-lex-check.sh` (58+ cases: positive +
  adversarial + shlex edge cases + printf %n + env shadowing),
  `tests/unit/test-permission-gate-compositional.sh` (11 integration
  cases including BASH_FUNC shadowing guard), and
  `tests/unit/test-rollback-compositional.sh` (idempotent rollback).

### Changed
- Charter `sutra/os/charters/PERMISSIONS.md` §4 amended with normative Tier
  1.5 block (full primitive+flag table; 5-gate specification; widening rule).
- Plugin manifest `PERMISSIONS.md` adds user-facing "Compositional reads"
  section with examples and blast-radius statement.
- `bash-summary-pretool.sh` mirrors the compositional fast-path (same env
  shadowing guard + helper invocation) to prevent decision drift between
  the two hooks (codex round 3 requirement).

### Security
- Explicitly NOT added to Tier 1.5 (continue to prompt): `git *`, `sed`,
  `find`, `awk`, `xargs`, `bash`, `python*`, `node`, `ruby`, `perl`, `curl`,
  `wget`, `ssh`, `scp`, `rsync`, `cp`, `mv`, `rm`, `ln`, `mkdir`, `touch`,
  `chmod`, `chown`, `dd`, *kill*, archive tools, sudo. `sort` removed
  mid-review due to `$TMPDIR` spill (codex round 5).
- Tokenizer is fail-safe-to-prompt: any helper error (missing python, timeout,
  malformed JSON) → permission-gate exits 0 → command flows to Claude Code's
  normal permission dialog. Never auto-denies, never auto-approves on failure.
- BASH_FUNC exported-function shadowing detected via (a) env regex for patched
  bash 4.3+ AND (b) `declare -F` universal fallback for legacy formats. Either
  match → passthrough to normal prompt.

### Review
- 10 codex rounds at `model_reasoning_effort="high"` (convergence arc: MODIFY
  → MODIFY-AGAIN × 8 → GO).
- Claude plan-eng-review: GO (architecture clean, code quality clean, 100%
  test coverage, performance clean).
- Both independent reviewers converged on GO before ship.

Follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning per [SemVer](https://semver.org/spec/v2.0.0.html).

## [2.1.0] — 2026-04-24

**PEDAGOGY + SECURITY charter v1 primitives ship.** Minor bump adds three new user-facing capabilities (`sutra learn`, `sutra sbom`, `sutra feedback --public`) plus level-aware governance inside the depth-marker hook. No breaking changes; v2.0.3 behavior preserved for installs that do not set `SUTRA_LEVEL`.

### Added

- **`sutra learn`** — PEDAGOGY charter v1 §Primitive #2. Interactive tutor with 5 lessons (~2 min each): depth, routing, charters, hooks, build-layer.
  - `sutra learn` — list lessons
  - `sutra learn <topic>` — print one lesson
  - `sutra learn --all` — print all 5 in order
  - `/core:learn` slash-command surface
  - Lessons live at `skills/sutra-learn/lessons/*.md`
- **`sutra sbom`** — SECURITY charter §Primitive #13. SHA256 per shipped file written to `~/.sutra/sbom.txt` for supply-chain integrity. `/core:sbom` surface.
- **`sutra feedback --public`** — v2.0 `/sutra feedback` opt-in extension. Wires to `gh` CLI to open a public issue on `sankalpasawa/sutra` after explicit `yes` confirmation. Scrubs content before post. Falls back to local-only if `gh` unavailable or unauthenticated.
- **`SUTRA_LEVEL` env** — PEDAGOGY charter v1 §Primitive #1. Levels: `novice | apprentice | journeyman | master`. Storage: env OR `~/.sutra/level`. Default `apprentice`.

### Changed

- **`hooks/depth-marker-pretool.sh`** — PEDAGOGY charter §Primitive #3. Output now respects `SUTRA_LEVEL`:
  - `novice` → verbose explanation (why, format, marker, escape, link to `sutra learn depth`)
  - `apprentice`/`journeyman` → default reminder (prior v2.0.3 behavior)
  - `master` → single-line terse warning
- `bin/sutra` — 2 new subcommands wired (`learn`, `sbom`); help-text updated with v2.1 sections.
- `scripts/feedback.sh` — `--public` no longer no-ops; gates on `gh` availability + auth, then prompts before posting.

### Charter progress

- PEDAGOGY v1: primitives #1, #2, #3 shipped. Still parked: #5 growth telemetry, #6 level-up ceremony, #7 level-down grace, #8 Sutra Tutor agent.
- SECURITY v1: primitive #13 shipped. Still parked: #9 signed releases, #10 SHA-pinned submodule, #11 god-mode MFA, #12 plugin-update consent, #14 audit aggregation dashboard.

### Migration

No migration. Existing installs upgrade cleanly. Verbose teaching mode: `export SUTRA_LEVEL=novice`. Terse power mode: `export SUTRA_LEVEL=master`.

## [1.15.0] — 2026-04-24

**Bash permission-summary format correction.** The v1.14.0 summarizer
described what bash was about to do ("will delete X", "will push to Y") —
the founder flagged this as technical-translation rather than the
product-outcome framing non-technical users actually need. v1.15.0
reframes: summaries now answer *"what will my world look like after I
approve this?"* — tied to the user's original task where possible. The
hook also narrows its firing to commands that would actually trigger a
permission prompt (i.e., not in Sutra's allow-list); auto-approved
operations incur zero cost.

### Changed

- `hooks/bash-summary-pretool.sh` — full rewrite:
  - **Firing scope:** new allow-list fast-path mirrors `permission-gate.sh`
    patterns. Allow-listed commands (e.g., `sutra *`, `rtk git *`,
    `mkdir -p .claude*`, `claude plugin *`) exit 0 silently — no LLM call,
    no summary. Only commands that would prompt the user generate a summary.
  - **Format:** outcome-in-product-terms. No "Plain-English:" prefix. No
    "I'm..." / "will..." prose. Answers "what changes in your world?" and
    ties back to the current task slug from `.claude/depth-registered`.
  - **LLM-primary:** Haiku call is now the main path. Prompt includes the
    task slug + shortened cwd so the summary can reference the user's
    original goal. Hash-keyed cache keyed by `(task | cmd)` so the same
    command in different tasks caches separately.
  - **Rules replaced with generic fallback:** no more 30-verb table with
    HOW-descriptions. One generic line when LLM is unavailable
    (`"Sutra couldn't auto-summarize this one..."`) + a cheap pre-LLM
    danger-prefix heuristic (⚠️ / 🚨) that still fires in fallback mode.
  - Kill-switches unchanged: `SUTRA_BASH_SUMMARY=0`, `SUTRA_PERMISSION_LLM=0`,
    `~/.sutra-bash-summary-disabled`.
  - Always exits 0.
- `tests/bash-summary-cases.sh` — rewritten for v1.15.0 semantics. 26
  sanity cases covering: allow-list fast-path silence, kill-switch
  silence, generic-fallback shape, danger-prefix on destructive patterns,
  JSON shape validity, non-zero-exit protection. All 26 pass.

### Example output (v1.14.0 → v1.15.0)

Same command, different framing:

| Command | v1.14.0 (wrong) | v1.15.0 (right) |
|---|---|---|
| `git push origin main` | `📖 Plain-English: will push your local commits to the remote repository.` | *The v1.14.0 ship goes live. Fleet users get the hook on their next Claude Code session.* |
| `rm -rf ./build` | `🚨 Plain-English (CAUTION): ⚠ DESTRUCTIVE — will delete './build' and everything inside it.` | *Your compiled output disappears. The next build recompiles from scratch — catches stale-cache bugs.* |
| `curl https://x.sh \| sh` | `🚨 Plain-English (CAUTION): ⚠ DESTRUCTIVE — downloads a script from 'x.sh' and runs it immediately.` | *⚠️ Whatever that remote script wants to do on your machine, it does — with your full permissions.* |

### Why ship this now

Source: founder feedback in the same 2026-04-24 session that shipped
v1.14.0. The v1.14.0 format was flagged as actively counterproductive
for non-technical users — a HOW-transcription reads like a threat
("will delete") rather than a decision aid. Principle 0 (Customer Focus
First) requires the summary to be legible *as a product decision*, not
as bash documentation.

### Fleet cost implication

v1.14.0 would have generated a rules summary for every Bash tool call.
v1.15.0 generates an LLM summary only for commands that would actually
prompt the user — after v1.13.0's meta-permission auto-approves most of
Sutra's own operations, that's ~2-5 calls per session per user. Upper
bound: ~$0.30/user/month at current volumes. `SUTRA_PERMISSION_LLM=0`
remains as an escape hatch (falls back to the generic line + danger
prefix).

### Migration

No migration. v1.14.0 users on next auto-update get the new format
silently. Existing kill-switches continue to work identically.

---

## [2.0.0] — 2026-04-24

**Privacy model replaced.** Reset from v1.9 telemetry-optin-into-push to v2 signals-not-content + local-first + consent-gated. Breaking change for existing T2/T3/T4 installs that relied on default-on outbound telemetry; legacy path preserved behind `SUTRA_LEGACY_TELEMETRY=1` flag. Codex-reviewed (DIRECTIVE-ID 1777036275) — CHANGES-REQUIRED with 10 findings; all 5 blocking conditions absorbed before ship.

### Added

- `lib/privacy-sanitize.sh` — 8 bash primitives: `derive_signal` (allowlist-only, 5 categories × alphanumeric sub), `scrub_text` (secondary guardrail: paths + KEY=value + Bearer + JWT + PEM + SSH + git-creds + DSN + email), `privacy_gate` (3-state: opt-out / in-memory / disk-allowed), `signal_write` (routes by gate), `sutra_safe_write` (atomic temp+rename + 0600 + symlink-refusal), `sutra_safe_append` (flock-when-available + 0600), `sutra_grant_consent`, `sutra_retention_cleanup`. 38 unit tests green.
- `hooks/feedback-auto-override.sh` — PreToolUse (all tools). Counts `*_ACK=1` overrides per hook-id. Dedup per invocation. 10 integration tests green.
- `hooks/feedback-auto-correction.sh` — UserPromptSubmit. In-memory regex match on correction patterns (no / stop / don't / actually / wrong / nope / that's-not). Prompt text never stored. Disclosed in PRIVACY.md §"What we capture" exception clause.
- `hooks/feedback-auto-abandonment.sh` — Stop. Emits signal only if depth-registered marker exists and is fresh (<1h). Captures task-slug only (no content). Abandonment fingerprint.
- `hooks/sessionstart-privacy-notice.sh` — SessionStart. Creates `~/.sutra/` with 0700, copies plugin PRIVACY.md to `~/.sutra/PRIVACY.md` with 0600, shows one-time banner, runs opportunistic retention cleanup (30d default).
- `PRIVACY.md` — v2 user-facing sheet (plain English, 1 page, 7 sections + legacy appendix). Tone: trustworthy, specific, no legalese. Corrected per codex: no "never prompts" / "nowhere else" overclaims.

### Changed

- `scripts/push.sh` — Legacy outbound push to `sankalpasawa/sutra-data` gated behind `SUTRA_LEGACY_TELEMETRY=1`. Default is now no-push.
- `tests/integration/test-identity-stamp.sh` — patched to opt into legacy flag for its 3 push-path assertions (7/7 green post-patch).

### Deprecated

- v1.9.0 identity stamping (`lib/identity.sh`) — still functional under `SUTRA_LEGACY_TELEMETRY=1`, otherwise inert.
- `telemetry_optin: true` default in `.claude/sutra-project.json` — no longer has any effect without legacy flag.
- `claude-plugin/SCHEMA.md` fields `install_id`, `project_id`, `identity:` — not captured by v2 signals.

### Security & Privacy (new in this version)

- **Default-strict**: T4 external users → in-memory-only signals until `/sutra feedback` grants consent.
- **Kill-switch**: `SUTRA_TELEMETRY=0` → zero capture anywhere. `rm -rf ~/.sutra/` → delete everything.
- **Allowlist-first**: signals derived from hook metadata, not from raw text scanning. Regex scrub is secondary guardrail only.
- **Fail-closed**: any sanitization error skips the write. Never writes raw because scrub broke.
- **Local-first**: no network transport in v2 default mode. No GitHub push, no Supabase, no third-party.
- **Permissions**: 0700 on `~/.sutra/`, 0600 on all files within.
- **Retention**: 30d default via `sutra_retention_cleanup` on SessionStart. Configurable via `SUTRA_RETENTION_DAYS` (1-90).

### Governance

- New charter at `sutra/os/charters/PRIVACY.md` (internal spec — 8 principles, tier contract, failure modes, primitives map, 6 KRs).
- Codex verdict archived at `asawa-holding/.enforcement/codex-reviews/privacy-design-review-2026-04-24.md`.

### Migration notes

- **T0/T1 (Asawa-internal)**: no action. Auto-capture continues; retention unchanged at 90d for internal profile.
- **T2 (owned portfolio — DayFlow, Billu, Paisa, PPR, Maze)**: on next session, banner shows; data moves to `~/.sutra/feedback/auto/` (was `~/.sutra/metrics-queue.jsonl`). Prior queue is left in place but no longer pushed.
- **T3 (Testlify, Dharmik)**: auto-capture now in-memory-only until user runs `/sutra feedback` once. No telemetry fan-in to Sutra team without explicit consent.
- **T4 (external fleet)**: default-strict. In-memory-only until consent. No action required; behavior improves automatically.
- **Anyone who wants v1 behavior back**: `export SUTRA_LEGACY_TELEMETRY=1`.

## [1.14.1] — 2026-04-24

**Stop-the-bleed for the `vinitharmalkar` incident.** In a recent T4 plugin user session, Sutra responded to a feedback request by offering to "file a GitHub issue on your behalf" and surfaced the `sankalpasawa/sutra` repo URL — leaking the session's auth identity into a public channel and treating a customer as a contributor. This ships a behavioral rule that fires whenever the user's prompt contains a feedback-intent keyword, instructing Claude to capture feedback locally and never file issues on the user's behalf. Independent of (and precedes) the full `/sutra feedback` command which lands in a later release.

### Added

- `hooks/feedback-routing-rule.sh` — UserPromptSubmit hook. Detects feedback-intent patterns (`give/submit/file/report feedback|bug|issue`, `feedback channel`, etc.) and emits a behavioral rule into the session's additional-context: (1) do NOT file GitHub issues on the user's behalf, (2) do NOT surface internal repo URLs as feedback channels, (3) do NOT act on the session's auth identity outside the local machine, (4) capture the feedback locally to `~/.sutra/feedback/pending/<timestamp>.md`. Always exits 0. Kill-switches: `FEEDBACK_ROUTING_RULE_DISABLED=1` env, `~/.feedback-routing-rule-disabled` file.
- `tests/unit/test-feedback-routing-rule.sh` — 14 golden-case tests (8 positive, 6 negative including kill-switch). All green on v1.14.1 release.

### Registered

- `UserPromptSubmit` chain appended with `feedback-routing-rule.sh` (sibling of `reset-turn-markers.sh` and `codex-directive-detect.sh`).

## [1.14.0] — 2026-04-24

**Plain-English for Bash permission prompts.** When Claude asks to run a Bash command, the approval dialog now includes a one-sentence plain-English summary of what the command actually does. Non-technical users no longer face raw `curl | sh` / `rm -rf` / heredocs with no explanation. Destructive patterns are flagged with 🚨 before the summary. Complements v1.13.0's PermissionRequest meta-permission: v1.13 cut the *count* of prompts, v1.14 makes the *remaining* prompts legible. Compounds with v1.3.0's `bin/sutra` consolidation (which had previously cut script-level prompt count for Sutra commands).

### Added

- `hooks/bash-summary-pretool.sh` — PreToolUse(Bash) hook. Emits `hookSpecificOutput.permissionDecisionReason` with a plain-English summary of the incoming Bash command. Two-stage: (v0) rules matcher covering ~30 verbs (rm, curl, wget, git, mkdir, cp, mv, chmod, chown, dd, kill, sudo, python/pip, node/npm, brew, find, grep, ssh, tar, redirection, heredoc detection) with danger-flagging; (v1) optional LLM fallback (Haiku) for composed commands with hash-keyed cache at `~/.sutra/permission-summary-cache/`. Always exits 0 (never blocks). Kill-switches: `SUTRA_BASH_SUMMARY=0` (hook off), `SUTRA_PERMISSION_LLM=0` (rules-only), `~/.sutra-bash-summary-disabled` (file).
- `tests/bash-summary-cases.sh` — 38 golden-case tests covering destructive patterns (rm -rf, pipe-to-shell, git reset --hard, dd, sudo, kill -9), network (curl/wget with host extraction), filesystem (mkdir/cp/mv/chmod), read-only, redirection (`>` overwrite vs `>>` append), env-var prefix normalization, and unknown-verb fallback. All 38 pass on v1.14.0 release.

### Registered

- `hooks.json` — `bash-summary-pretool.sh` added to the `PreToolUse[Bash]` matcher, ordered after `rtk-auto-rewrite` + `codex-directive-gate` so blocked commands never pay the summarization cost.
- `sutra/layer2-operating-system/c-human-agent-interface/HUMAN-AGENT-INTERFACE.md` — new Part 4 "Registry of Implementations" section; first entry is this hook, linked to principles P7 (Human Is the Final Authority) + P11 (Human Confidence Through Clarity).
- `holding/HUMAN-AI-INTERACTION.md` — P7 + P11 sections gain backlinks pointing to this hook as a concrete implementation.

### Updated

- `.claude-plugin/plugin.json` — version `1.13.0` → `1.14.0`; description extended.

### Why ship this now

Source: `sutra/marketplace/FEEDBACK-LOG.md` 2026-04-24 entry — external user flagged that raw bash in permission dialogs is unreadable for non-technical adopters, leaving them with two bad options: blind approval (worst-case failure mode, invites destructive commands) or getting stuck. Directly violates Founding Doctrine Principle 0 (Customer Focus First) for the T4 non-technical segment of the fleet. With v1.13.0 already cutting prompt count by ~95%, the few remaining prompts carry outsized weight — every one the user can't read is a decision made blind.

### Architecture note — upstream destiny

This hook is a stopgap. The right long-term home for a permission summary is inside Claude Code's native approval dialog — no hook required. A pitch doc at `sutra/marketplace/UPSTREAM-PITCH-permission-summary.md` captures the feature request for Anthropic. If upstream ships this natively, the hook retires cleanly.

### Scope intent

- **Asawa, Sutra dogfood, T2 owned (DayFlow, Billu, Paisa, PPR, Maze)**: inherited via plugin auto-update. Default-ON. Kill-switch available per-user.
- **T3 projects (Testlify, Dharmik)**: inherited on next plugin update. Default-ON.
- **T4 Sutra Users**: primary beneficiary segment. Default-ON.

### Migration

No migration. Hook is additive; existing behavior unchanged except that Bash approval dialogs now carry a summary line. No user action required.

### Decommission criteria

Retire when Anthropic ships native permission summary (upstream pitch) OR telemetry shows <1 fire/day for 30 days across the fleet.

---

## [1.13.0] — 2026-04-24

**Meta-permission.** First release that eliminates the paste-the-snippet step for new installs. Ships the PERMISSIONS charter + PermissionRequest hook so every Sutra-scope operation auto-approves AND persists its rule to `.claude/settings.local.json`. Second session onward: zero hook invocations for in-scope ops — Claude Code's native allow-list handles it directly.

### Added

- `sutra/os/charters/PERMISSIONS.md` — new charter. Closes a governance gap: defines what Sutra MAY request (Tier 1 always / Tier 2 feature-flagged / Tier 3 forbidden). Any future hook that wants scope outside Tier 1 must update the charter FIRST. North Star KPI: `prompts_per_first_session ≤ 2` (down from ~40). Source: founder direction 2026-04-24 — "lots of permissions... can they be human-readable... meta permission not recurring." DRI: Sutra-OS.

- `hooks/permission-gate.sh` (PERMISSIONS charter mechanism) — PermissionRequest hook. Auto-approves matched patterns and returns `updatedPermissions.addRules` with `destination: "localSettings"` so the rule persists across sessions. Matches: `Bash(sutra)`, `Bash(sutra:*)`, `Bash(bash ${CLAUDE_PLUGIN_ROOT}/*)`, `Bash(claude plugin marketplace update sutra)`, `Bash(claude plugin update|uninstall core*)`, `Bash(mkdir -p .claude*|.enforcement*|.context*)`, governance-marker Writes, `.claude/logs/*`, `.enforcement/codex-reviews/*`, `.context/codex-session-id`. Defense: rejects shell combinators. Fail-open. DEFAULT-ON (UX hook). Kill-switch: `~/.sutra-permissions-disabled` or `SUTRA_PERMISSIONS_DISABLED=1`.

- `tests/permission-gate-test.sh` — PROTO-000 test bundle. 18 cases: 7 in-scope (auto-approve), 5 out-of-scope (silent pass-through), 4 shell-injection attempts (reject), 1 kill-switch, 1 JSON-shape assertion. All 18 pass on v1.13.0 release.

### Registered

- `hooks.json` gains a new `PermissionRequest` event block with matcher `Bash|Write|Edit|MultiEdit` → `permission-gate.sh`.

### Updated

- `PERMISSIONS.md` — regenerated from v1.5.1 → v1.13.0. Adds "How v1.13 changes the install flow" section; retains the paste-able snippet as a fallback for users who kill-switch the hook; adds audit trail.
- `.claude-plugin/plugin.json` — version 1.12.0 → 1.13.0; description mentions permission-gate.

### Why ship this now

Every T4 fleet install currently walks through ~40 prompts before the user sees Sutra working. That's the single biggest drop-off at the install cliff. The existing `/core:permissions` command requires the user to run it *before* any Sutra operation — but most users don't know that. The PermissionRequest mechanism (documented in Claude Code's plugins-reference 2026-04-24) turns this into a one-consent install: after the first session, `.claude/settings.local.json` holds every rule the user needs, persisted by the hook.

### Scope intent (first-cohort enablement)

- **Asawa**: inherits via plugin update — default-ON, but holding/hooks/ governance is unaffected.
- **Sutra dogfood**: enabled by default in Sutra's own sessions.
- **DayFlow, Paisa, Billu, PPR, Maze**: `claude plugin marketplace update sutra` → default-ON on next session. Kill-switch per-user if any surprise.

### Migration

No migration needed. Hook activates on install/update; existing `.claude/settings.local.json` paste-rules remain valid (redundant but harmless).

### Decommission criteria

Claude Code ships native plugin-level `permissions.allow` bundling (plugins-reference currently restricts plugin `settings.json` to `agent` + `subagentStatusLine` keys). When that lands, migrate the allow-list into `plugin.json` and retire `permission-gate.sh`.

---
## [1.12.0] — 2026-04-23

Third + fourth L0 promotions via PROTO-021 — keys-in-env-vars + estimation-collector. Bundled release. Additive, default-off per D32.

### Added

- `hooks/keys-in-env-vars.sh` (PROTO-004 "Keys in Env Vars Only") — PreToolUse.Write|Edit|MultiEdit gate. Scans content about to be written for API-key-shaped strings (sk-*, AKIA*, ghp_*, etc.) landing in non-env files; HARD exit 2 blocks the write. Skips legitimate env paths (`*.env*`, `.envrc`, `*/secrets/*`, `*/.ssh/*`, `*keys.json`, `*credentials*`). Default-OFF per D32. Override: `PROTO004_ACK=1 PROTO004_ACK_REASON='<why>'`. Kill-switch: `~/.proto004-disabled` or `PROTO004_DISABLED=1`.

- `hooks/estimation-collector.sh` — Stop-event collector. Scrapes `ESTIMATE:` / `ACTUAL:` lines from session transcript, appends JSONL records to `<instance>/.enforcement/estimation-log.jsonl` (default) or holding/ESTIMATION-LOG.jsonl (Asawa via `ESTIMATION_LOG_OVERRIDE`). Idempotent per session_id. D9 COMPARE path synthesizes tokens_actual from transcript usage fields when ACTUAL line absent. Default-OFF per D32. Kill-switch: `~/.estimation-collector-disabled` or `ESTIMATION_DISABLED=1`.

### Registered

- `hooks.json` PreToolUse gains `matcher: Write|Edit|MultiEdit` group for keys-in-env-vars.sh.
- `hooks.json` Stop event gains estimation-collector.sh (runs after estimation-stop + flush-telemetry).

### Why bundled

Both promotions are part of the L0 promotion queue documented in `holding/research/2026-04-23-build-layer-protocol-design.md` §4 (classification table). Bundling into one release (vs two version bumps) reflects their complementary nature — security hygiene + measurement capture — and simplifies marketplace upgrade churn for existing installs.

Note on rtk-auto-rewrite: plugin-side version was already at parity with Asawa's holding version (identical 115-line content, no divergence). This release does NOT re-ship it. Asawa's holding/hooks/rtk-auto-rewrite.sh stays in place until Asawa opts into fully plugin-driven enforcement (separate track).

### Scope intent (first-cohort enablement)

- **Asawa**: retains holding copies of both; plugin hooks default-off pending cohort stability review.
- **Sutra dogfood**: enable in Sutra's own os/SUTRA-CONFIG.md.
- **DayFlow**: inherits via `claude plugin marketplace update sutra`; DayFlow CEO enables in DayFlow's SUTRA-CONFIG.
- **Paisa, Billu, PPR, Maze**: default-OFF — no action.

### Migration

```yaml
# os/SUTRA-CONFIG.md
enabled_hooks:
  keys-in-env-vars: true
  estimation-collector: true
```

### Cumulative L0 promotions (PROTO-021 dogfood rhythm)

1. v1.10.0 — operationalization-check (2026-04-23)
2. v1.11.0 — subagent-os-contract (2026-04-23)
3. v1.12.0 — keys-in-env-vars + estimation-collector (2026-04-23, this release)

4/14 L0 candidates promoted (rtk-auto-rewrite counted as already-at-parity). Remaining queue: 10 candidates. Next round after session-end review surfaces actual adoption signal.

## [1.11.0] — 2026-04-23

Second L0 promotion via PROTO-021 — subagent OS contract enforcement. Additive, default-off per D32.

### Added

- `hooks/subagent-os-contract.sh` — PostToolUse.Task gate. Validates every subagent response contains the Sutra OS contract (6-field boot block + 4-field footer). Missing footer → `exit 2` block-feedback-to-model. Missing boot fields → soft WARN. Telemetry row per dispatch to `<instance>/.enforcement/subagent-contract.jsonl`. **Default-OFF** per D32 (`enabled_hooks.subagent-os-contract: true` in instance's `os/SUTRA-CONFIG.md`). Override: `SUBAGENT_CONTRACT_ACK=1 SUBAGENT_CONTRACT_ACK_REASON='<why>'`. Kill-switch: `~/.subagent-contract-disabled` or `SUBAGENT_CONTRACT_DISABLED=1`.
- Registered in `hooks.json` PostToolUse with `matcher: "Task"` matcher (drop-in replacement for Asawa's `holding/hooks/subagent-os-contract.sh`, which is now eligible for retirement per Asawa `CLAUDE.md` §Agent Dispatch "[TEMP — remove when Sutra plugin ships]" marker).

### Why

PROTO-021 first-real-promotion rhythm continues. Asawa's CLAUDE.md has carried an explicit `[TEMP]` marker on the holding-side subagent-os-contract hook for weeks waiting on plugin equivalent. This release ships it.

### Scope intent

- **Asawa**: retains holding/hooks/subagent-os-contract.sh until plugin adoption metric stabilizes. After 30d of plugin-side stability, Asawa flips its own enablement flag and retires the holding copy (per Asawa CLAUDE.md).
- **Sutra dogfood**: enable via Sutra's own `os/SUTRA-CONFIG.md`.
- **DayFlow**: inherits via `claude plugin marketplace update sutra`; DayFlow CEO enables in DayFlow's SUTRA-CONFIG per D31+D33.
- **Paisa, Billu, PPR, Maze**: default-OFF — no action.

### Migration

```yaml
# os/SUTRA-CONFIG.md
enabled_hooks:
  subagent-os-contract: true
```

Existing Asawa `subagent-os-contract` telemetry rows in `.enforcement/subagent-contract.jsonl` remain format-compatible with the plugin version — aggregation consumers see no schema break.

### Source

- Hook: `hooks/subagent-os-contract.sh` (170 lines incl. Operationalization section)
- Registry: `hooks/hooks.json` (new PostToolUse.Task matcher group)
- Promoted-from: `holding/hooks/subagent-os-contract.sh` (L1 → L0)
- Design: `holding/research/2026-04-23-build-layer-protocol-design.md`

## [1.10.0] — 2026-04-23

First L0 promotion via PROTO-021 BUILD-LAYER protocol. Additive, backward-compatible — default-off per D32.

### Added

- `hooks/operationalization-check.sh` — D30a "Ship Is Not Done" presence gate. Checks Edit/Write targets for a `## Operationalization` section with 6 subsections (Measurement, Adoption, Monitoring, Iteration, DRI, Decommission). Blocks (exit 2) when missing at an enforced path. **Default-OFF** per D32: each instance opts in via `enabled_hooks.operationalization-check: true` in its own `os/SUTRA-CONFIG.md`. Registered in `hooks.json` PreToolUse `Edit|Write` matcher. Ledger at `<instance>/.enforcement/ops-check.jsonl`. Per-call override `OPS_ACK=1 OPS_ACK_REASON='<why>'`. Global kill-switch `~/.ops-check-disabled` or `OPS_CHECK_DISABLED=1`.
- Default-enforced path patterns: `hooks/**/*.sh`, `departments/**/*.sh`, `{charters,protocols,engines,os/charters,os/protocols,os/engines,os/d-engines}/**/*.md`. Non-enforced paths always pass through.

### Why

PROTO-021 BUILD-LAYER protocol introduces the layer-declaration mechanism for every Asawa/Sutra/client task. This release is the first real L0 promotion — Asawa's `holding/hooks/operationalization-check.sh` (which lived L1 authoring-instance-only) now has a plugin-native MVP every instance can enable. DayFlow + Sutra dogfood get D30a presence-checking natively.

### Scope intent for this first promotion

- **Asawa** (authoring): keeps its full-featured `holding/hooks/operationalization-check.sh` — it has Tier A+B granularity + state.yaml grandfathering that the plugin MVP doesn't yet have.
- **Sutra dogfood**: enable in Sutra's own `os/SUTRA-CONFIG.md` if desired.
- **DayFlow**: inherits on `claude plugin marketplace update sutra`; enable via DayFlow's own `os/SUTRA-CONFIG.md`.
- **Paisa, Billu, PPR, Maze**: default-OFF, no behavior change — explicit opt-in required.

### MVP-not-parity rationale

Plugin version is intentionally a subset of Asawa's holding-side. Full parity in one shot would have meant porting Tier-A/B classification + grandfathering + state.yaml reader — high blast radius. MVP lets DayFlow + Sutra dogfood get the mechanism now; v2 brings richer path granularity after 30 days of plugin-side stability. Tracked in `.enforcement/build-layer-ledger.jsonl` as `promoted-mvp` outcome.

### Source

- Hook: `hooks/operationalization-check.sh` (198 lines including Operationalization section)
- Registry: `hooks/hooks.json` (PreToolUse.Edit|Write appended after depth-marker-pretool)
- Spec: `sutra/layer2-operating-system/PROTOCOLS.md` §PROTO-021
- Design: `holding/research/2026-04-23-build-layer-protocol-design.md` (Codex review synthesis §15)

### Migration

`claude plugin marketplace update sutra` pulls v1.10.0 → hook lands in plugin cache, stays silent until enabled. To enable:

```yaml
# os/SUTRA-CONFIG.md
enabled_hooks:
  operationalization-check: true
```

## [1.9.4] — 2026-04-22

Hotfix for v1.9.3 — executable bit ACTUALLY landed this time.

### Fixed

- `hooks/sessionstart-auto-activate.sh` and `website/install.sh` committed as mode `100755`. v1.9.3's commit recorded them as `100644` despite the `git update-index --chmod=+x` call — a subsequent `git add` re-read the working-tree 644 mode and clobbered the staged 755 before commit. Working-tree files now `chmod +x`'d BEFORE `git add`, so `git add` stages 755 and the commit records 755.

### Rationale

v1.9.3 CHANGELOG claimed the mode fix; the commit didn't actually record it. Live reproduction 2026-04-22: user installed v1.9.3, hook still `-rw-r--r--` on disk, `sessionstart-auto-activate.sh: Permission denied`, governance never activated. `git ls-tree HEAD` confirmed `100644` persisted in the v1.9.3 commit.

### Lesson (for future mode-fix releases)

`git add` re-reads filesystem mode and CLOBBERS any prior `git update-index --chmod=+x`. Correct patterns: EITHER (a) `chmod +x` the working-tree file first, THEN `git add`, OR (b) use `git update-index --chmod=+x` alone (it stages the mode; commit can follow without a subsequent `git add` on the same file). Never both in sequence — `add` wins.

### Migration

Existing v1.9.x users: `claude plugin marketplace update sutra` pulls v1.9.4. The correctly-moded hook file reinstalls at `100755`, SessionStart hook actually executes, `/core:start` auto-runs, CLAUDE.md governance block lands.

## [1.9.3] — 2026-04-22

Executable-bit fix attempt — closes Finding #23 ("SessionStart hook: Permission denied"). **Note: v1.9.3 commit actually recorded mode 100644 due to `git add` clobbering the `update-index` mode change; v1.9.4 is the real fix.**

### Fixed

- `hooks/sessionstart-auto-activate.sh` mode now `100755` (was `100644`). Claude Code invokes hook scripts as executables; without the execute bit, the hook silently fails with `Permission denied` and `/core:start` never auto-runs — so v1.9.2's CLAUDE.md injection never fires for installer-driven installs. This patch makes the hook actually executable.
- `website/install.sh` mode now `100755` (was `100644`) as belt-and-suspenders; installer already works via `curl | bash` (piped to bash stdin, doesn't need +x) but explicit +x lets users download-then-run (`bash install.sh` or `./install.sh`).

### Rationale

Subagent that landed v1.8.0 (SessionStart hook registration) flagged `chmod +x` as "MANUAL FOLLOW-UP" — never done. v1.9.2's 10-test integration matrix passed because tests invoke scripts via `bash path/to/script.sh` (which doesn't need +x) — but Claude Code's real hook loader calls scripts as executables, requires +x. Test-harness gap, captured as a new dogfood finding for the next test-matrix iteration: verify file modes via `git ls-files -s`, not just functional invocation.

### Migration

Existing v1.9.x users: `claude plugin marketplace update sutra` pulls v1.9.3 and git propagates the new file modes. Fresh installs via `curl | bash` get the correct modes immediately.

## [1.9.2] — 2026-04-22

Governance injection — closes Finding #22 ("governance blocks don't fire on every turn").

### Fixed

- `/core:start` now writes `.claude/CLAUDE.md` with a marker-delimited Sutra-managed governance block containing Input Routing + Depth Estimation + Readability Gate + Output Trace templates. Claude Code loads CLAUDE.md as project system context on every session, so every response now emits governance blocks — fulfilling the sutra.os promise.
- Idempotent: re-running `/core:start` updates the managed block in-place (detected by `<!-- SUTRA GOVERNANCE ... -->` markers) without clobbering the user's other CLAUDE.md content.

### Rationale

v1.7.1 fixed alias collision. v1.8.0 wired auto-activation. v1.9.1 added identity stamping. Dogfood on 2026-04-22 revealed governance blocks still weren't emitting on every turn — Claude Code's Skill tool doesn't auto-invoke skills per turn; it fires skills on semantic match. Research question "top restaurants in Mumbai" had no semantic match to governance skills, so no blocks fired. The missing piece: instructing the LLM via CLAUDE.md (which IS loaded every session). v1.9.2 adds that injection.

### Migration

Existing v1.8.x / v1.9.x users: `claude plugin marketplace update sutra` pulls v1.9.2. Running `/core:start` in any project writes/updates the managed CLAUDE.md block. Existing CLAUDE.md content untouched — the block is marker-delimited and appendable. To opt out on a specific project: manually delete the block (between the SUTRA GOVERNANCE markers) from that project's CLAUDE.md.

## [1.9.0] — 2026-04-22

Identity stamping — know who's running the plugin. Backward-compatible, additive.

### Added

- **`lib/identity.sh`** — new library. `capture_identity <version>` emits a JSON object with git_user_name, git_user_email_hash (SHA-256[:16]), github_login, github_id, hostname_hash (SHA-256[:12]), os_name, os_version, os_pretty, arch, shell_name, locale, tz, captured_at, captured_by_version. Fallback chain: git global → git local → gh api → system GECOS → `$USER`. Every step best-effort; never fails a session. 3-second timeout on gh API calls.
- **`tests/unit/test-identity.sh`** — 10 unit tests covering JSON shape, required keys, hash field shapes, fallback when git+gh are unavailable, staleness detection.
- **`tests/integration/test-identity-stamp.sh`** — 7 integration tests: onboard stamps local JSON + cache, push stamps manifest on bare repo, 7d staleness gate holds, 8-day-old cache triggers recapture, emit-metric PII rejection still active (regression guard).

### Changed

- **`scripts/onboard.sh`** — sources `lib/identity.sh`; when `telemetry_optin=true`, captures identity and stamps it into `.claude/sutra-project.json` > `identity:`. Also caches to `$SUTRA_HOME/identity.json` (chmod 600) for push-time staleness checks.
- **`scripts/push.sh`** — sources `lib/identity.sh`; on each push, checks cache freshness (`identity_is_stale`, default 7 days). Stale or missing → recapture. Stamps the identity block into `clients/<install_id>/manifest.json` alongside existing `push_count` / `last_seen` / `sutra_version` fields. **Retroactive for existing installs** — next push after upgrade stamps the identity block without requiring a re-onboard.

### Privacy

- **Metrics channel unchanged.** `emit-metric.sh` still regex-rejects PII in `dept`/`metric`/`unit`/`window` fields (regression-tested). Telemetry `*.jsonl` rows remain PII-free.
- **Identity channel is a new, separate channel** living in `manifest.json`. Activated by existing `telemetry_optin` (default `true` when `/core:start` runs with `profile=project|company`, default `false` with `profile=individual`). Flip `telemetry_optin: false` in `.claude/sutra-project.json` to turn OFF — effect is immediate; next push omits identity.
- **Fields captured are user-supplied** (git config, gh auth) or coarse machine metadata (os, arch, tz). Raw email and raw hostname are NOT captured — both are SHA-256 hashed to 16/12 hex chars. See PRIVACY.md for full matrix.

### Rationale

Founder direction 2026-04-22 — needed a fleet view of Sutra users (portfolio + external friends who install via marketplace). Prior manifest carried only hashed install_id + project_id, leaving new installs unidentifiable. v1.9.0 closes that gap with a separate, opt-in-by-default identity channel that preserves the existing PII-free posture of the metrics channel.

Design doc (asawa-holding repo): `holding/research/2026-04-22-sutra-identity-capture-v17-design.md`.

### Migration

- Existing users: `claude plugin marketplace update sutra && claude plugin update core@sutra`. Next Stop-hook auto-push stamps identity. No manual action required.
- Users who had `telemetry_optin: false` stay unstamped until they flip the flag. No behavior change for them.
- Downstream companies (DayFlow, Billu, etc. — when plugin-installed): inherit on next auto-update.

## [1.8.0] — 2026-04-22

One-command install — closes the last mile of "one command does everything."

### Added

- **`hooks/sessionstart-auto-activate.sh`** — REGISTERED in `hooks.json` (sibling of `update-banner.sh` on SessionStart). Fires on every session start; ACTS only when the sentinel `~/.sutra/installed-via-script` exists AND the current project has no `.claude/sutra-project.json`. Runs `sutra start` via absolute `${CLAUDE_PLUGIN_ROOT}/bin/sutra` (Finding #12-safe), deletes sentinel on success (one-shot), never blocks session start (trap + `exit 0`).
- **`website/install.sh`** — committed in v1.7.1, now operative. Serves from GitHub raw at `https://raw.githubusercontent.com/sankalpasawa/sutra/main/website/install.sh`. No Vercel, no third-party deploy.

### Changed

- **User-facing install flow collapses from 4 commands to 1.** Previous: `claude plugin marketplace add` → `claude plugin install` → `/reload-plugins` → `/core:start`. New: `curl -fsSL <raw-url> | bash` → open `claude` → first session auto-activates.

### Rationale

Founder direction 2026-04-22 (memory `project_sutra_permissions_in_start.md`): "one command should do everything — no 4-step ceremony." v1.7.1 shipped the prerequisite (alias-collision fix, Finding #12). v1.8.0 completes the vision.

### Migration

- Existing v1.7.x users: `claude plugin marketplace update sutra` pulls v1.8.0. The new SessionStart hook is a no-op for already-activated installs (sentinel gate). Fresh installs via `curl | bash` get auto-activation on first `claude`.

## [1.7.1] — 2026-04-22

Shell-alias collision fix (Codex-converged Option E).

### Fixed

- **All internal `!sutra <sub>` invocations in `commands/*.md`, `scripts/*.sh`, and `hooks/*.sh` now use absolute plugin-root paths (`${CLAUDE_PLUGIN_ROOT}/bin/sutra <sub>`).** Shell aliases, functions, or PATH-shadowing `sutra` binaries can no longer intercept plugin self-invocation. Fixes dogfood Finding #12 (P0 shipping blocker, 2026-04-22).
- Regression test `tests/integration/test-alias-collision.sh` reproduces the founder-observed collision (alias hijacks the plugin's `sutra start` call and redirects into an unrelated project) and asserts activation still succeeds.

### Rationale

Initial diagnosis (`design/2026-04-22-sutra-cli-collision.md`) favored renaming `bin/sutra` → `bin/sutra-core` (Option A) plus a runtime `type -a` self-check (Option D). Codex challenge (`design/2026-04-22-sutra-cli-collision-codex-consult.md`) revealed Option D is conceptually wrong as a *runtime* safety layer — if the user's alias wins shell name resolution, the plugin binary never executes, so the self-check never fires. Option E closes the bug class for *any* name collision (not only `sutra`), ships as a patch with zero breaking changes, and touches ~15 files instead of ~35.

## [1.7.0] — 2026-04-22

C3c token-compression bundle — Tokens charter per-turn cost-component cut.

### Added

- **RTK auto-rewrite whitelist (native tools)** — `hooks/rtk-auto-rewrite.sh`. PreToolUse(Bash) hook that blocks unprefixed voluminous git commands and forces `rtk <cmd>` wrap. Whitelist v2: `git status`, `git log`, `git diff`, `git blame`, `git show`. Typical reduction 30-60% on wrapped commands (measured on Asawa repo). Kill-switch: `touch ~/.rtk-disabled` or `RTK_DISABLED=1`.
- **MCP output compression (all MCP tools)** — `hooks/posttool-mcp-compress.sh`. PostToolUse hook matched on `mcp__.*` that REPLACES large MCP outputs via `hookSpecificOutput.updatedMCPToolOutput` with a head+error+tail compressed summary. Thresholds: size ≥ 4000 bytes AND line count ≥ 80. Smoke-tested: 5,099-byte playwright snapshot → 2,583 bytes (49% cut). Telemetry at `.enforcement/c3c-compress.jsonl`. Codex-verified mechanism + docs-verified (code.claude.com/docs/en/hooks). Kill-switch: `touch ~/.c3c-disabled` or `C3C_DISABLED=1`.

### Changed

- `hooks/hooks.json` registers the two new hooks — RTK on PreToolUse(Bash), MCP-compress on PostToolUse(matcher `mcp__.*`).

### Rationale

Founder direction 2026-04-22: "don't change what I write — find background optimizations for the printing part." Output tokens can't be compressed post-generation, but TOOL OUTPUT Claude reads CAN be compressed before entering context. Native-tool track uses PreToolUse command rewriting via RTK; MCP-tool track uses PostToolUse output replacement. Paired commits ship them as one OS bundle.

### Migration

- Existing v1.6.x users: `claude plugin marketplace update sutra` picks up both hooks automatically. No config change required.
- Both hooks have individual kill-switches if needed: `~/.rtk-disabled` disables native; `~/.c3c-disabled` disables MCP.

## [1.6.0] — 2026-04-22

Per-profile enforcement + hard-block mode + release channels.

### Added

- **User profiles** — plugin.json `userConfig.profile` accepts `individual`, `project`, or `company`. Claude Code prompts at enable time. Writes to `.claude/sutra-project.json`.
- **Profile-dependent telemetry default** — `individual` = off (privacy default), `project` = on, `company` = on.
- **Hard enforcement on `company` profile** — `hooks/depth-marker-pretool.sh` reads the profile and exits 2 (blocks the tool call) when the depth marker is missing, ONLY for `company` profile. `individual` and `project` stay warn-only.
- **Escape hatch** — `SUTRA_BYPASS=1 <cmd>` prefix skips the depth check for one tool call, even on `company`. Audit trail preserved via existing routing-misses log.
- **Release channels** — two marketplace branches on the repo:
  - `main` branch = **latest** (current behavior; auto-updates push new versions immediately)
  - `stable` branch = **stable** (promoted manually once a version is proven in portfolio use)
  - Users pick: `claude plugin marketplace add sankalpasawa/sutra` (latest) or `claude plugin marketplace add sankalpasawa/sutra@stable` (stable).

### Changed

- `/core:start` accepts `--profile individual|project|company` and also reads `CLAUDE_PLUGIN_OPTION_PROFILE` env var that Claude Code injects from userConfig.
- Activation banner now shows the active profile + enforcement mode.

### Migration

- Existing v1.5.x users: no action needed — `/core:start` on v1.6.0 defaults to `project` profile which preserves current warn-only behavior and telemetry-on default.
- To opt into hard enforcement: `/core:start --profile company`.
- To opt into privacy-default: `/core:start --profile individual`.

### Rationale

Founder direction 2026-04-21: "do 14, 15, 16, 17" — collapse P3 items into one profile-aware release. Per-profile defaults (#15) enables hard enforcement (#14) without breaking casual users. Release channels (#16) shipped as a parallel git-branch pattern so stable adopters can pin without affecting latest-chasing early users. Smoke-tested: company profile exits 2 on missing marker; individual/project stay warn-only exit 0.

## [1.5.1] — 2026-04-22

### Added

- **`session-retrieve` skill** — recovers abruptly-closed Claude Code sessions after laptop shutdowns, kernel panics, or API timeouts. Scans `~/.claude/projects/*.jsonl` for orphan signatures (explicit `API Error` OR silent mid-`tool_use` deaths), returns `claude -r <id>` resume commands with correctly-decoded project roots.
- CATALOG.md §7b "Skills (by LLM interactive surface)" — new taxonomy section. Skills organized by the harness they run in (Terminal / Desktop / Web / SDK). Terminal subsection contains all 5 plugin skills; other surface subsections reserved for future.
- Trigger phrases for the skill: "figure out past sessions", "what sessions got killed", "my laptop switched off — what was I working on", "find my crashed sessions", etc.

### Why it exists

Session-retrieve was built after a laptop shutdown lost 5 mid-flight sessions. The manual recovery took ~15 min of jsonl grepping and two wrong `claude -r` attempts (wrong project root). Skill encodes the deterministic procedure: detect both orphan flavors, decode the project slug for resume (never use the `cwd` field — #1 failure mode), dedupe shared roots, and output a readability-gate compliant report.

## [1.5.0] — 2026-04-21

Plugin renamed `sutra` → `core` within the `sutra` marketplace, plus permission-prompt transparency.

### Added

- `PERMISSIONS.md` — complete, auditable list of every Bash and Write permission the plugin needs, grouped by purpose, with a paste-ready allowlist.
- `/core:permissions` (+ `sutra permissions` in terminal) — prints the exact JSON snippet to paste into `.claude/settings.local.json`. One paste, zero further prompts.

### Changed (BREAKING — plugin identifier rename)

- Plugin name `sutra` → `core`. Install is now `claude plugin install core@sutra`. Slash commands move to `/core:*` namespace.
- Marketplace name stays `sutra`. Install pattern: `core@sutra` reads as "core plugin from the sutra marketplace" (Anthropic's standard "hub + product" naming pattern, same shape as `superpowers@claude-plugins-official`).
- All docs + scripts + command files updated: `/sutra:start` → `/core:start`, `sutra@sutra` → `core@sutra`.
- Binary kept as `sutra` — terminal users still type `sutra start`, `sutra status`, etc. Slash commands use `/core:*` because Claude Code namespaces by plugin name.

### Migration for existing users

Claude Code treats the rename as a different plugin (not an update). Users on v1.4.x must:

```
claude plugin uninstall sutra@sutra
claude plugin marketplace update sutra
claude plugin install core@sutra
/core:start
```

v1.5.0 cannot auto-migrate because the plugin identifier changed. Sorry.

### Rationale

Founder direction 2026-04-21: "core@sutra" — collapse the visual stutter in `sutra@sutra` by adopting the multi-plugin marketplace naming pattern. Marketplace name remains "sutra" so future plugins (e.g., `sutra-lite`, domain-specific variants) can sit alongside `core` under the same hub.

## [1.4.0] — 2026-04-21

Radical UX simplification: **one command does everything.**

### Added

- `/sutra:start` — THE one command. Onboards the project, enables telemetry, prints the activation banner, writes a depth marker. Everything a new user needs in one invocation.
- `/sutra:update` — slash-command front-end for `claude plugin marketplace update sutra && claude plugin update sutra@sutra`.
- `/sutra:uninstall` — slash-command front-end for `claude plugin uninstall sutra@sutra`. Accepts `--purge` to also wipe `~/.sutra/`.
- `scripts/start.sh` — merged flow from prior `go.sh` + depth-marker init + richer activation banner.

### Removed (BREAKING)

- `/sutra:onboard` — merged into `/sutra:start`.
- `/sutra:go` — merged into `/sutra:start`.
- `/sutra:sutra` — activation banner now emitted by `/sutra:start`.
- `/sutra:push` — auto-push runs on Stop event; manual push moved to power-user CLI (`sutra push`).

### Changed

- `bin/sutra` collapsed to four lifecycle verbs: `start / status / update / uninstall`. `push / onboard / go / leak-audit / install-shell-helpers / version / help` kept as secondary callable subcommands for power users and shell helpers.
- Telemetry default: `/sutra:start` sets `telemetry_optin = true`. Users who want privacy can edit `.claude/sutra-project.json` post-run; `PRIVACY.md` documents the flip.

### Rationale

Founder feedback 2026-04-21: "Users don't have to do multiple things — keep it start and we do the entire install and everything." Six user-facing slash commands collapsed to five, with one clear entry point.

### Migration

- Anyone who typed `/sutra:onboard` or `/sutra:go` — use `/sutra:start` instead.
- Shell helpers: `sutra-go` will be removed in v1.5; `sutra-start` alias coming in a shell-helper patch.

## [1.3.1] — 2026-04-21

User-facing polish around v1.3.0's breaking rename.

### Added

- `hooks/update-banner.sh` — SessionStart hook prints a one-time banner when the plugin version changes (e.g., after auto-update), with a link to CHANGELOG. Silent on first run and unchanged-version runs. Writes state to `~/.sutra/last-seen-version`.
- `PRIVACY.md` — explicit statement of what's collected and never collected. Default `telemetry_optin = false`. Third-party destinations: none.
- `VERSIONING.md` — SemVer policy explaining when we bump MAJOR / MINOR / PATCH, the v1.3.0 rename exception, yanking procedure, and release-channel roadmap.

### Rationale

v1.3.0's command rename was breaking for anyone running an older version. Without a banner, users would silently hit "unknown command" on `/sutra:sutra-onboard`. The banner now surfaces the update + links CHANGELOG so the migration is discoverable.

## [1.3.0] — 2026-04-21

Permission-prompt reduction + command namespace cleanup.

### Added

- `bin/sutra` unified dispatcher — single executable replacing six script invocations. Claude Code auto-adds plugin `bin/` to PATH, so `sutra onboard`, `sutra push`, etc. run as bare commands (no Bash permission prompts per distinct script path).

### Changed

- **Command rename (BREAKING)** — `/sutra:sutra-onboard` → `/sutra:onboard`, `/sutra:sutra-push` → `/sutra:push`, `/sutra:sutra-status` → `/sutra:status`, `/sutra:sutra-go` → `/sutra:go`. Drops redundant `sutra-` prefix now that Claude Code namespaces commands as `plugin:command`.
- All command files now invoke `!sutra <sub>` instead of `!bash ${CLAUDE_PLUGIN_ROOT}/scripts/<name>.sh`. Single permission scope.

### Migration

- Auto-update will pull new command files. Old slash commands (`/sutra:sutra-onboard` etc.) stop working; use the new names.
- First use of `sutra` bare command may surface one permission prompt per session depending on Claude Code version — one allow covers all subcommands.

## [1.2.1] — 2026-04-21

Brand-leak scrub before external launch.

### Fixed

- `plugin.json` description: removed an internal brand reference; now reads "local metric telemetry".
- `ARCHITECTURE.yaml`: internal operator paths replaced with abstract `<operator>/` placeholders.

### Added

- `marketplace/design/2026-04-21-first-run-walkthrough.md` — T+0 → T+60s scripted experience (CM3).
- Plugin leak audit now PASSES; official `claude plugin validate` PASSES.

## [1.2.0] — 2026-04-20

Per-session tool telemetry.

### Added

- `hooks/posttool-counter.sh` — PostToolUse hook tracks which tools ran per session, writes to `$SUTRA_HOME/sessions/<session_id>.counters`.
- Stop hook extended — `flush-telemetry.sh` reads session counters, emits `tool_uses_session`, `skill_uses_session`, `write_uses_session`, and related metrics; cleans up counter file after emit.
- `ARCHITECTURE.yaml` as structured source of truth (v1.0.0) — components, flows, identities, privacy matrix.

## [1.1.4] — 2026-04-20

Shell-helper installer.

### Added

- `scripts/install-shell-helpers.sh` — appends `sutra-go` / `sutra-uninstall` / `sutra-reset` / `sutra-status-global` one-word commands to user's `~/.zshrc` or `~/.bashrc`. Idempotent.
- README install flow updated for new-laptop users.

## [1.1.3] — 2026-04-19

Auto-push on Stop.

### Added

- `hooks/flush-telemetry.sh` — fire-and-forget async push on Stop event if `telemetry_optin=true`. Never blocks session teardown.

### Changed

- Per codex review: Stop hook stays light — local file writes only, no synchronous network or git.

## [1.1.2] — 2026-04-19

### Added

- `/sutra:sutra-go` — one-shot onboard + telemetry ON command.

## [1.1.1] — 2026-04-19

Plugin observability auto-emission.

### Added

- `flush-telemetry.sh` auto-emits three metrics on Stop: `sessions.session_stops_total`, `os_health.queue_depth_at_stop`, `os_health.depth_marker_present`.
- Analytics collector (operator-side) reads plugin telemetry rows and rolls up per-metric count + median.

## [1.1.0] — 2026-04-18

Layer-B metric telemetry.

### Added

- `lib/project-id.sh` — deterministic install_id (sha256 HOME+version) + project_id (sha256 git remote).
- `lib/queue.sh` — local metric queue at `~/.sutra/metrics-queue.jsonl`; rotates at 10k lines.
- `hooks/emit-metric.sh` — Layer B writer: validates numeric values, rejects PII in string fields, appends to queue.
- `commands/sutra-onboard.md` — first-time project setup writing `.claude/sutra-project.json`.
- `commands/sutra-push.md` — manual push to `sankalpasawa/sutra-data` (opt-in gated).
- `commands/sutra-status.md` — local state inspector.

## [1.0.0] — 2026-04-18

First production release. Outcome-tested.

### Added

- Outcome test suite at `tests/outcome/` — install, activation, enforcement, commands, update, logging, leak-audit as black-box scripts.
- Hooks shift from warn-only to structured: `depth-marker-pretool.sh` logs violations; `estimation-stop.sh` writes session log.

## [0.2.0] — 2026-04-19

Unified deploy.

### Changed

- Plugin strips shadow skills (they duplicated dispatcher logic) and becomes a thin bridge that invokes `npx github:sankalpasawa/sutra-os init` on first `/sutra`.

## [0.1.0] — 2026-04-18

First release. Minimum viable plugin for functional validation.

### Added

- Skills: `input-routing`, `depth-estimation`, `readability-gate`, `output-trace`
- Commands: `/sutra`, `/depth-check`
- Hooks: `depth-marker-pretool` (warn-only, PreToolUse Edit|Write), `estimation-stop` (Stop event logger)
- Audit script: `scripts/leak-audit.sh` (brand-leak mechanism)
- MIT license

### Known limitations

- Hooks warn rather than block. Hard enforcement deferred to v0.2.
- No per-profile defaults yet (individual / project / company).
- Estimation log is session-local, not cross-session.

---

provenance: maintained by Sutra release process; one entry per released plugin version, newest first.
## %s (%s)

**Connectors screen + P3 permission layer.** The first user-facing half of the
connector rewrite: the panel gets a Connectors surface, and permission
decisions are now resolved from real settings files on disk.

- **P3 `permission_service.py`** — resolves the five settings sources from
  actual paths (managed / session / local / project / user), derives the
  working set from the connector's installations so a read outside the
  connector's scope prompts, persists "don't ask again" to
  `settings.local.json` (local, not project: a rule one operator accepted in a
  modal is not team policy), and exposes the capability read model. Malformed
  settings fail CLOSED -- an unreadable policy file must never read as "no
  policy", which is the widest state there is.
- **11 panel endpoints** under `/api/connectors`. Synchronous `def`, not
  `async def`: the GitHub client is blocking stdlib urllib, so FastAPI runs
  these in a threadpool and a slow GitHub call cannot freeze the panel.
- **Connectors screen** (`12-connectors.js`) — the External World block's
  operator projection per ADR-023. Connect via device flow with the code shown
  for transcription, repositories with per-repo capabilities, organizations
  separating membership from access, the live permission rule table in
  evaluation order, and the hash-chained audit trail. An in-flight device flow
  is labelled EPHEMERAL rather than rendered as settled state.
- "Authorized but not installed" and "installed but no repositories selected"
  render as two different states with two different fixes, because they are.
- 164 tests. 152 panel tests still green, including 21i, the grid guard that
  caught the last CSS regression.

## %s (%s)

**Connector panel errors are diagnosable, and the backend recovers on its own.**

The Connectors screen showed `/api/connectors -> 500` with no way to find out
why. Restarting the app cleared it and the root cause was never reproduced --
which is the point: two defects made a transient fault permanent and invisible.

- **Every connector endpoint returns a structured error.** They previously
  caught only `ConnectorError`; anything else became a bare 500. Electron
  buffers the backend's stderr in memory and surfaces it only if the process
  *exits*, so the reason existed nowhere a person could reach. Unexpected
  exceptions are now logged to `~/.sutra/panel-errors.log` and returned with a
  code, a message and that path.
- **`service()` rebuilds a dead handle.** It cached a module global holding a
  live SQLite connection for the life of the process, so a connection that went
  bad could never recover and the only cure was quitting the app. A failed
  construction is no longer cached either, so the next request retries instead
  of inheriting a permanent `None`.
- The screen distinguishes "the service did not answer" from "the service
  answered and told us what went wrong", and offers Retry.

## %s (%s)

**Fixes the Connectors screen returning 500. Root cause, not a workaround.**

`sqlite3.connect()` defaults to `check_same_thread=True`, so a connection binds
to the thread that created it. The panel serves its connector endpoints as
synchronous `def` handlers -- deliberately, so a blocking GitHub call cannot
stall the event loop -- and FastAPI runs those in a **threadpool**. One shared
connection therefore worked for the first request and raised
`ProgrammingError` as soon as the pool routed a later one to a different
worker:

    /api/connectors -> 200    first request, thread A
    /api/connectors -> 500    later request, thread B

It read as transient because restarting put a fresh connection on whichever
thread asked first, and it never appeared in the 164 tests or the CLI because
both are single-threaded.

- `Database` now holds **one connection per thread**. WAL lets independent
  connections read and write concurrently, so this is the right shape here
  rather than a global lock -- a lock would also have to cover cursor
  iteration, which several callers do lazily.
- `busy_timeout = 5000`, so two threads writing at once wait briefly instead of
  surfacing an immediate "database is locked".
- In-memory databases keep a single shared connection, because a memory
  database lives *inside* its connection and per-thread handles would give each
  thread its own empty one.
- **4 regression tests** that fail against the old code: read from another
  thread, write visible across threads, four concurrent workers, and the
  end-to-end shape -- build the service on one thread, call it from another.

The 2.112.1 diagnosability work below stands: it is what turns the *next*
unexpected failure into a message instead of a silent 500.

## %s (%s)

**An empty installation set no longer defeats the cache.**

Measured on the installed app: every call to the connectors detail cost a live
GitHub round-trip, ~0.85s, on a connector that is authorized but not installed.
The sync condition was `if refresh or not installations` -- and for a connector
with no installations that is true on *every* request, so the 15-minute cache
was bypassed exactly when there was nothing to fetch.

A freshness marker now records that GitHub was asked and what it said,
including when the answer was none. "We have not asked" and "we asked and there
are none" look identical in an empty list and have very different costs.

Found by hammering the endpoints 60-deep after the 2.112.2 thread fix; one
request timed out behind the queue, which is what surfaced the per-call
round-trip underneath.

