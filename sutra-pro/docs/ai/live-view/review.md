# Review: live-view (D453, E32)

## Round 1  (2026-11-26, commit 1af30893)
Verdict: Changes requested (one P2 bug to fix before release; the rest are cuts and notes)

Base 6c79a1db (origin/main), branch `live-view`, worktree /Users/disha/Downloads/sutra-liveview.

### Findings
| ID | Sev | File:line | Finding | Evidence | Suggested fix |
|---|---|---|---|---|---|
| R1-1 | P2 | scripts/port_j2_ui.py:167 (page j2_ui.html:1106), :344 | `LIVE.last` is per page session, not per run, and `sCrew` reads it whatever the status. After a live run ends, or when you open a saved or other run in the same tab, the crew shows the old run's tool lines instead of the stream lines. implementation.md "How to test live" step 7 says the opposite ("the crew shows last stream lines") | Probe on the fixture state (status waiting). On a fresh page, mira = "Mira finished item 5." and nora = NORA_LAST. After one `liveLines(RUNNING(LIVEFIX))`, the same state gives mira = "Reading src/a.py" and nora = "Reading.env (fake-token-…)". With `saved` set, asha = "Reading brief.md". The existing crew test only checks running states | Use `LIVE.last` only while running: `line: (s.status === "running" && plain(LIVE.last[k] || "")) \|\| liveSaid(s, k)`. Also clear `LIVE` (last/line) when a running state's `run_id` differs from the one seen before. Add one assertion: after live lines, a non-running state gives the stream lines |
| R1-2 | P2 | sutra_app/engine/capabilities/agents.py:127-130; spec.md FR-5 | The host's Redactor does not have "the same environment as the server's". `child_environment` (orchestrator/runs.py:63-80) removes every secret-named variable, and the host gets neither the launch token nor an override key set only in the environment. So the host redacts `.env` values only (same file: SUTRA_ENV_FILE and SUTRA_DATA_DIR reach the host, so `default_env_file()` resolves the same). A secret exported in the server's shell (e.g. a provider key) that an agent prints, for example after reading a dotfile, can still be cut at the 200/4000 boundary in the writer. The server's whole-value Redactor then misses the remaining piece | redact.py: environ = os.environ of the host; runs.py:65-80 | This is not a regression: before this branch nothing was redacted before the cut. Fix the text of FR-5 and D453 so they say "`.env` values only in the host; environment secrets only whole, in the API", and accept it as Q-7. Do not pass secrets into the host to close the gap |
| R1-3 | P3 | sutra_app/engine/views.py:354 | `/api/state` now carries each live agent's `text` (up to 20000 chars per agent, up to 64 agents) on the 700 ms poll. The page never reads it (FR-4 forbids it) | rawchat.live_tail keeps `text`; liveLines reads only tool/step/since | Drop `text` from the state's copy (a dict comprehension without `text`). The `/api/agent-live` debugger route keeps it |
| R1-4 | P3 | port_j2_ui.py:350-351 (raw_chat.js load) | Confirmed real, but short-lived. dept_ext.js injects raw_chat.js asynchronously (dept_ext.js:209-215, :475). Until it loads, `liveLines` gives "Client Lead: …", "Strategist: …", "Quality Reviewer: …", Asha and Nora are not busy, and `LIVE.last` is not set for them. It fixes itself on the next poll after the load. It stays wrong only if raw_chat.js fails to load | Probe with `plain()` (no RawChat): `["Client Lead: Reading brief.md","Strategist: Adaptation proposes workflows","Mira: …","Quality Reviewer: …","agent: …"]` | Smallest fix: one port edit that puts `<script id="raw_chat-js" src="/ui/js/raw_chat.js"></script>` before the page's inline script. dept_ext's `rawChat()` already skips when that id exists, and raw_chat.js defers its `init` to DOMContentLoaded, so a synchronous load is safe. Cost: +1 line and one more edit. Or accept it and keep F3 |
| R1-5 | P3 | port_j2_ui.py:344, :355, :371 | `LIVE.p` is dead state. It is set together with `LIVE.line`, and `LIVE.line` is never empty once set, so `liveSaid(CTX, LIVE.p)` only runs while `LIVE.p === ""`. implementation.md deviation 7 says this too | Read of E32a/E32d | Remove `p: ""`, `LIVE.p = p;` and pass `""` (see cuts) |
| R1-6 | P3 | port_j2_ui.py:360-363 | `mapLive` mutates `MAP.nodes` in place and keeps the old status in `st0`. Anything else that reads `MAP.nodes[].status` between polls sees "running" | Read | Return a copy instead (see cut C1). It is shorter and has no side effect |
| R1-7 | P3 | port_j2_ui.py:169 | The crew line goes through `plain()`, which joins a path to the word before it: "Reading .env (…)" becomes "Reading.env (…)" in the crew (the chat line is fine). Every dotfile or `.github/` path is affected | Probe output above | FR-10 asked for `plain()`. Use `esc` only (sCrew output is already escaped at render), or leave it |
| R1-8 | P3 | tests/ui/js/page_render.test.js LINES.audit; fixture audit entry | The JS tests expect "Nora: Reading .env (fake-token-0123456789)" on screen. That is correct only because the page fixture bypasses the server, but a reader can take it as "secrets are shown". The fixture line is a path plus a fake value, not only a path | test_engine_agent_live `test_a_secret_is_redacted_before_either_cut` (writer, both cuts, fails on cut-then-redact by construction: tail keeps "56789", tool keeps "fake-") and test_engine_api_redact (API gives "Reading .env ([redacted])") do prove redaction | Add one comment in the JS test ("the server redacts; this fixture is pre-server"), or use "Reading .env ([redacted])" in the JS expectations |
| R1-9 | P3 | tests/ui/test_port_edits.py:618 | `PIN = "00efb179…"` is still what the opt-in real-J2 test passes as `--commit`. It is only a label (the page holds no commit), so the test passes, but it names the wrong pin | `SUTRA_J2_CHECKOUT=<ee659fb5 extraction>` pytest passes | Set it to ee659fb54aec75bf7f5139516791aee20a0474fa or leave it. This line predates the branch |

### Owner question 1: cuts in E32's JavaScript (port_j2_ui.py)
Current: +43/-2 in port_j2_ui.py. Hand-written total is +51 net.

| # | Cut | Where | Saves |
|---|---|---|---|
| C1 | `mapLive` as a pure copy, called inside E32e: `const mapLive = m => { const L = liveLines(CTX); return {...m, nodes: (m.nodes \|\| []).map(n => L.some(l => n.kind === "function" ? n.id === "fn:" + l.k : n.kind === "engine" && (n.workflows \|\| []).includes(l.k)) ? {...n, status: "running"} : n)}; };` and E32e becomes `paint($("pane-map"), renderMap(mapLive(MAP)))`. No `st0` save and restore | :360-363 | -2 (also fixes R1-6) |
| C2 | Remove `LIVE.p` (dead, R1-5); E32d becomes `LIVE.line \|\| liveSaid(CTX, "")` | :344, :355, :371 | 0 lines, about 25 chars |
| C3 | Remove the header comment of E32a (`// E32 (D453): who works now …`). The E32a edit-table entry and the inline comments already carry it | :343 | -1 |
| C4 | Remove the `# E32b's anchor` comment line above SCREW_J2 (the Edit's own trailing comment says the same) | :161 | -1 |
| C5 | Fold `rc` into the `r =` binding: `r = typeof RawChat === "object" ? RawChat.helpers.personOf(k) : {}` | :350-351 | 0 to -1 once rewrapped |
| C6 | SCREW: keep J2's own first sCrew line (start the regex after it) instead of rewriting it to remove `th`/`live`. This leaves two unused variables in the generated page | :162-166 | -1 (trade-off: dead vars in a generated file) |
| C7 | agents.py: put `"tools": 0}` back on the dict's line, and write `snapshot` as one comprehension line that uses `r` | agents.py:164-165, :183-185 | -1 to -2 |

Realistic total: about -6 to -8, so +51 goes to about +43-45. Getting to ~35 means dropping a feature, not compressing code. The candidates are the crew's per-person memory (`LIVE.last`, which is also the source of R1-1: roughly 3 lines) or the chip's `liveSaid` fallback. With confidence moderate, I would not chase 35 with one-liners. C1 plus R1-1's fix is the best net change.

### Owner question 2: the page pin
- The pin is the sutra commit whose `prototypes/j2` gets extracted (`git archive <pin> prototypes/j2`) and fed to `port_j2_ui.py --j2`. The port applies the edits to that J2 page and `--check` compares the result with the committed files.
- 00efb179 fails because plan.md took it from test_port_edits.py's PIN constant (sync-4 era). J2's page at 00efb179 predates edits E2c, E19, E20f1-i, E23, E24a-f, E25a/c, E27b and E30a/d. Base 6c79a1db's own port script reports exactly 19 drifted anchors there (verified). On the branch it reports 21, because E32a and E32b also do not anchor there (sNum and sCrew do not exist yet).
- ee659fb5 is correct. It is the engine pin (VENDORED.md:3, test_engine_vendor PIN, D244), and D244 records that the page at ee659fb5 equals what sync 7 ported. Base 6c79a1db's port `--check` against the ee659fb5 extraction gives "ok: the 59 anchors … equal a fresh port". The branch gives "ok: the 64 anchors …". The branch's j2_ui.html diff is only the E32 lines. j2.css, the harnesses and vendor files are unchanged.
- HEAD's own `prototypes/j2` (later J2 commits ba3aed6a, 82d4f991, …) does not match the committed page or j2.css, on base or on the branch. So it is not the pin and was not touched. Nothing unintended changed.

### Owner question 3: can a secret reach a live line?
Path: `AgentLiveCapability.progress` keeps the raw tool and the whole text (agents.py:161-170). `snapshot()` applies `r(...)` and then cuts: `r(entry["text"])[-LIVE_TAIL:]` and `r(entry["tool"])[:TOOL_CHARS]` (:183-185). So redaction comes before the cut on both. `write_now` writes the snapshot (0600). `rawchat.live_tail` reads it, cuts the text to 20000 and passes `tool` uncut. `views.state` adds `live` (views.py:353-354). The engine's reply passes `services.redact` (whole values, server Redactor with env, `.env`, token and override key), and the API test proves "Reading .env ([redacted])". The page shows only `tool`, the part name or the step name, cut to 120, through `esc`/`mapWords`/the crew's `esc`. `text` is never rendered.
- In the host, the Redactor is built lazily in `install` as `Redactor(default_env_file())`, and test_install_gives_the_writer_the_apps_redactor covers the engine-side import. It knows the same `.env` file, but not the server's environment secrets, token or override key (R1-2). The gap matters only for a secret cut across the boundary.
- The fixture "Nora: Reading .env (fake-token-0123456789)" holds a path plus a fake value. The writer test proves redaction before both cuts, and the API test proves the fake value comes back as `[redacted]`. The JS test shows it unredacted only because it skips the server (R1-8).

### Other checks
| Rule | Status |
|---|---|
| Only recorded data (agent_live.json, studio.parts/stream, steps) | ok |
| No new status lists or person tables; no Pulse logic | ok. String literals are separators, "Your turn." (existing) and "running" |
| ce457a0e personOf plus name match to PEOPLE | Not a copy and not a new lookup. It reuses raw_chat.js's existing PEOPLE and joins it to the panel's PEOPLE by display name. The join is fragile (a rename in either file silently drops to the role title), so P3 at most |
| What-line = tool, else part name, else step; never text | ok (test asserts no fixture `text` in output) |
| Redact before truncation | ok (R1-2 caveat) |
| Chat lines live only, 3 then +N | ok; no `addMsg`, `state.chat` length unchanged (API test) |
| Fixed sCrew sentences removed | ok (both test files assert absence) |
| Crew lines and chip never blank | ok while running; R1-1 for non-running |
| Golden comparison does not blank crew lines | ok: E32_CREW maps them to exact expected strings |
| No changes to approval, hosts, dry-run; no P47 | ok (diff stat) |
| j2_ui.html generated, `port --check` clean | ok |

### Spec coverage
| Requirement | Covered by | Status |
|---|---|---|
| FR-1 key = function | agents.py, test planner/judge | met |
| FR-2 live on /api/state | views.py, api_redact test | met |
| FR-3 who | liveLines | met per owner's later rule (adaptation is "Planner", not Asha as FR-3 said; recorded as deviation 3) |
| FR-4 what | liveLines, test | met |
| FR-5 redact then cut | snapshot, tests | met for `.env`; FR-5 text wrong about environment (R1-2) |
| FR-6 chat 3 + N | liveTyping, test | met |
| FR-7 live only | test | met |
| FR-8 Map boxes and chip | mapLive, mapChip, test | met |
| FR-9 never blank | test | met while running |
| FR-10 crew | E32b, test | met; stale across runs (R1-1) |
| FR-11 fixture | fixture, tests | met |
| FR-12 D453 / E32 | docs | met; P47 dropped by owner |
| NFR-4 sCrew shorter | 21 to 11 lines | met |

### Tests run
| Command | Result |
|---|---|
| `node --test tests/ui/js/` | 1753 pass, 0 fail, 2 skipped |
| `SUTRA_J2_CHECKOUT=<ee659fb5 extraction> node --test tests/ui/js/page_render.test.js` | 60 pass, 0 fail |
| `scripts/py -m pytest tests/ui/test_port_edits.py tests/engine/test_engine_agent_live.py tests/engine/test_engine_rawchat.py tests/engine/test_engine_api_redact.py tests/engine/test_engine_views.py` | 356 passed, 2 skipped |
| same test_port_edits.py with `SUTRA_J2_CHECKOUT` | pass |
| `port_j2_ui.py --j2 <ee659fb5> --check` (branch) | ok, 64 anchors, 7 files equal |
| base 6c79a1db port `--check` at ee659fb5 / 00efb179 / HEAD's prototypes/j2 | ok (59) / 19 drifted anchors / committed files differ |
| scratch probe (node, page harness) for R1-1, R1-4, R1-7 | reproduced |
| scripts/gate.sh | not run (optional; implementation.md reports 4 known pre-existing failures) |

### Earlier findings
None (first round).

## Round 2  (2026-11-26, commit 262db15a)
Verdict: Approve-ready. Both P2s are fixed. Two new P3s and one browser check for the owner's beta run do not block.

### Findings
| ID | Sev | File:line | Finding | Evidence | Suggested fix |
|---|---|---|---|---|---|
| R2-1 | P3 | scripts/port_j2_ui.py:166 (page j2_ui.html:1104-1105) | The R1-1 reset lives in `liveLines`, but `sCrew` reads `LIVE.last` before it calls `liveLines(s)`. If `sCrew` is the first thing to see a new run's running state, it shows the previous run's tool lines for that render. Today this cannot happen: `poll()` calls `liveTyping(s)` (line 1985, which resets) before the Studio render, and every other render runs after the poll. It is order-dependent, though, and the R1-1 test hides it by calling `liveTyping` first | Probe: after `liveLines({…LIVEFIX, run_id:"j2-a"})`, `sCrew({…RUNNING({}), run_id:"j2-c"})` called first gives mira "Reading src/a.py" and nora "Reading .env (…)" | In sCrew, call `liveLines(s)` once at the top and reuse the result in the busy loop. This is a reorder, not a new line. Or leave it |
| R2-2 | P3 (unverified, needs a browser) | E32f (port_j2_ui.py:371; page :209) | raw_chat.js now loads synchronously before the page script, so its `DOMContentLoaded` listener is registered before dept_ext.js's. On `/d/<team>/raw`, raw_chat's `init`/`open({full:true})` now runs before `DeptExt.init`. Before this change it ran after it, when dept_ext injected the script. raw_chat needs only `document.body` and `SutraCtx`, both present at DOMContentLoaded. dept_ext's MutationObserver on the body class is attached after `rc-open` is set, so it does not see that change. I found no dependency, but did not verify in a browser. There is no double load: dept_ext `rawChat()` returns early on the `raw_chat-js` id, and the harness runs only the last inline script | dept_ext.js:209-215, :475, :515; raw_chat.js:379-409 | In the owner's beta check, open Settings & logs → Raw AI chat (`/d/<team>/raw`) once and confirm it opens full screen with its run list |

### R1 verification
| ID | Status | Evidence |
|---|---|---|
| R1-1 | fixed | `sCrew` uses `LIVE.last` only while running, and `liveLines` clears `LIVE` on a `run_id` change. New test plus my probes: a finished run shows the stream lines, a saved run equals a fresh page, a new run's chat line is the step name, and a waiting state uses `liveSaid`. The chip fallback is still never blank while running (run change with no live entries gives the run's last stream line). Mock runs have no `run_id` and no agent_live, so there is nothing to reset. Ordering caveat: R2-1 |
| R1-2 | fixed (wording) | spec FR-5 and A-4, D453, decisions.json and the agents.py:127 comment now say `.env` values only in the host, with environment secrets, token and override key redacted only whole by the API |
| R1-3 | fixed | views.py:354 removes `text`; the API test asserts no `text` key. Readers: the page uses tool/step/since only; raw_chat.js reads `/api/agent-live` (unchanged, still has text); no other JS or Python reads `state.live` |
| R1-4 | fixed | E32f puts `<script id="raw_chat-js" src="/ui/js/raw_chat.js">` before the inline script, and dept_ext skips its own load on that id. Load order: R2-2 |
| R1-5 | fixed | `LIVE.p` removed; the chip calls `liveSaid(CTX, "")` |
| R1-6 | fixed | `mapLive` returns a copy, used as `renderMap(mapLive(MAP))`. Test asserts that `MAP.nodes` is unchanged |
| R1-7 | fixed | Crew shows `l.what` and `LIVE.last[k]` without `plain()` ("Reading .env (…)"). They are still escaped where the crew is drawn |
| R1-8 | open (owner: not approved) | still P3 |
| R1-9 | open (owner: not approved) | still P3 |
| Cuts | C1-C5 and C7 done, C6 skipped (owner) | hand-written production is +47 net (port_j2_ui.py +41/-2, agents.py +13/-6, views.py +3/-2, rawchat.py and record_api_shapes.py 0), matching implementation.md |

### Spec coverage
Unchanged from round 1. FR-10's "through plain()" is now deliberately not followed (R1-7, recorded in implementation.md). FR-5's text is corrected.

### Tests run
| Command | Result |
|---|---|
| `node --test tests/ui/js/` | 1754 pass, 0 fail, 2 skipped |
| `SUTRA_J2_CHECKOUT=<ee659fb5 extraction> node --test tests/ui/js/page_render.test.js` | 61 pass, 0 fail |
| `port_j2_ui.py --j2 <ee659fb5> --commit ee659fb5 --check` | ok: 65 anchors, 7 files equal |
| `scripts/py -m pytest tests/ui/test_port_edits.py tests/engine/test_engine_agent_live.py tests/engine/test_engine_rawchat.py tests/engine/test_engine_api_redact.py tests/engine/test_engine_views.py tests/engine/test_engine_api_scope.py` | 385 passed, 2 skipped |
| same test_port_edits.py with `SUTRA_J2_CHECKOUT` | 184 passed |
| scratch probes (reset order, waiting state, chip after run change, mock chip) | as reported in R1-1 and R2-1 |
| scripts/gate.sh | not rerun (developer reports 13662 passed, 4 known failures) |

### Earlier findings
R1-1 fixed · R1-2 fixed (wording) · R1-3 fixed · R1-4 fixed · R1-5 fixed · R1-6 fixed · R1-7 fixed · R1-8 still open (P3, owner skipped) · R1-9 still open (P3, owner skipped)
