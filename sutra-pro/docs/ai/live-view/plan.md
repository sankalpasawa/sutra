# Plan: Show who is working and what, live, on the Map and in chat
Branch: live-view (worktree ~/Downloads/sutra-liveview; already cut). All commands run from `sutra-pro/` unless they say otherwise.
Design: architecture.md (the JS in "Interfaces" is the exact code E32 inserts). Spec: spec.md (Refined).

Rules for every commit
- Stage files by name (`git add <file> <file>`); never `git add -A` or `git add .`.
- Commit subject style of the recent history: `feat(live-view): <plain sentence> (D453 FR-n)`, `test(live-view): …`, `docs(live-view): …`. Follow your commit-identity rule (own email, no co-author trailer).
- j2_ui.html is only ever written by `scripts/port_j2_ui.py`; j2_studio.py and VENDORED.md only by `scripts/vendor_j2.py`.
- Ignore tests that already fail on `origin/main` (run the same command there once if a failure looks unrelated, and note it).
- Test first where the step says so: write the test, run it, see it fail for the stated reason, then change the code.

The two J2 extractions (made once, reused; the folders are temporary):
```sh
cd ~/Downloads/sutra-liveview          # the repository root (git archive paths are from here)
export J2PAGE="$(mktemp -d)"; git archive 00efb179e21cb79fae157a0679e819921ac37726 prototypes/j2 | tar -x --strip-components=2 -C "$J2PAGE"   # the page pin (tests/ui/test_port_edits.py:586)
export J2ENG="$(mktemp -d)";  git archive ee659fb54aec75bf7f5139516791aee20a0474fa prototypes/j2 | tar -x --strip-components=2 -C "$J2ENG"    # the engine pin (VENDORED.md line 3)
cd sutra-pro
```
If T0's rebase moved either pin (the removal may re-vendor), take the new values from those two places instead.

- [x] T0: Rebase onto the landed removal and claim the numbers (no commit)
  - Files: none
  - Change: `git fetch origin`. Confirm remove-real-run-gates has landed: `git log --oneline origin/main | grep -i -m3 "real-run\|D452"`. If it has not, stop and tell the owner (FR-13 says it lands first). Then `git rebase origin/main`. On a conflict in `sutra_app/ui/pages/j2_ui.html`, take origin's file and re-port (`scripts/py scripts/port_j2_ui.py --j2 "$J2PAGE" --commit <pin>`); never merge it by hand.
  - Numbers: `git grep -n '## D453' origin/main -- docs/DECISIONS.md`, `git grep -n '"E32' origin/main -- scripts/port_j2_ui.py`, `git grep -n 'Edit("P47"' origin/main -- scripts/vendor_j2.py`. Each must print nothing. If one prints, use the next free number everywhere this plan says D453, E32 or P47 (also in the spec's FR-12 row, with a change-log line).
  - Done when: `git merge-base --is-ancestor <the removal's last commit> HEAD && echo ok` prints ok; the three greps print nothing; `scripts/py scripts/port_j2_ui.py --j2 "$J2PAGE" --commit <pin> --check` exits 0.
  - Covers: FR-12, FR-13

- [x] T1: Record decision D453
  - Files: `docs/DECISIONS.md`, `docs/diagram/decisions.json`
  - Change: append `## D453 — The team page shows who works now and what, from the run's live record` after the last D entry, in D451's shape (Sources, Decided, Why, Rejected, Rollback, Follow-ups, Diagram), taking its content from architecture.md "Decisions" (D453, D453-a, D453-b) and the Q-1..Q-10 answers. Diagram entry: `{"id": "D453", "label": "the Map and chat say who works now and what, from agent_live.json; fixed crew sentences removed", "anchor": "band:EXPERIENCE"}` appended to decisions.json; the Diagram line in DECISIONS.md repeats that label.
  - Tests: existing `tests/test_diagram_decisions.py`
  - Done when: `scripts/py -m pytest tests/test_diagram_decisions.py -q` passes
  - Covers: FR-12

- [x] T2: The live fixture and the FR-1 key test (test only)
  - Files: `tests/ui/fixtures/live/agent_live.json` (new), `tests/engine/test_engine_agent_live.py`
  - Change: the fixture, exactly:
    ```json
    {"schema": "agent-live/1", "at": 1793786403.0, "agents": {
      "adaptation": {"call": 3, "since": 1793786390.0, "step": 2, "text": "{\"workflows\": [{\"name\": \"Build_menu\"", "tool": "", "tools": 0},
      "W-2": {"call": 11, "since": 1793786400.0, "step": 6, "text": "I will read the file and then write the menu.", "tool": "Reading src/a.py", "tools": 3},
      "audit": {"call": 12, "since": 1793786401.0, "step": 7, "text": "", "tool": "Reading .env (fake-token-0123456789)", "tools": 1},
      "agent": {"call": 13, "since": 1793786402.0, "step": null, "text": "free words an agent wrote", "tool": "", "tools": 0}}}
    ```
    Test `test_a_planner_and_a_judge_call_are_keyed_by_their_function` (parametrised over `("planner", "plan")`, `("judge", "judge")`): inside `with llm.tagged(function="adaptation", step=2): with llm.tagged(role=role, purpose=purpose): t = llm.current_tag()`, call `live.progress(t, {"tool": "Reading a"})`; assert `list(live.snapshot()["agents"]) == ["adaptation"]`; `live.finished(t)`; assert the agents are `{}`.
  - Tests: the new test is expected to pass at once (Q-1: llm.py:340-350). **If it fails with key `"agent"`**: in the same commit change agents.py:154 and :169 to `tag.function or tag.role or "agent"` (both places, same expression) and say so in the commit message.
  - Done when: `scripts/py -m pytest tests/engine/test_engine_agent_live.py -q` passes
  - Covers: FR-1, FR-11

- [x] T3: The writer redacts before it cuts, and records the call's step
  - Files: `sutra_app/engine/capabilities/agents.py`, `sutra_app/engine/rawchat.py`, `tests/engine/test_engine_agent_live.py`, `tests/engine/test_engine_rawchat.py`
  - Tests first:
    - `test_a_secret_is_redacted_before_either_cut`: `SECRET = "fake-token-0123456789"`; `cap = AgentLiveCapability(threaded=False, clock=lambda: 1000.0, redact=Redactor(environ={"DEMO_API_TOKEN": SECRET}))` (`from sutra_app.orchestrator.redact import Redactor`); `progress(tag(), {"tool": "x" * 195 + SECRET})`, then `progress(tag(), {"text": SECRET + "y" * 3995})`; for every 5-char slice of SECRET assert it is in neither `entry["tool"]` nor `entry["text"]`; assert `len(entry["tool"]) == 200` and `len(entry["text"]) == 4000`. Run it: it must fail on today's code (the `TypeError` for `redact=` is not enough: also run it once with the argument removed and `Redactor` applied by hand after `snapshot()`, and see the slice `"56789"` survive). Keep the version with `redact=`.
    - `test_an_entry_records_the_step_of_its_call`: `progress(CallTag(function="W-3", purpose="agent_turn", call_no=7, step=6), {"tool": "Read"})` → `entry["step"] == 6`.
    - Update the existing tests that compare a whole entry dict to include `"step": None` (the `tag()` helper sets no step).
    - test_engine_rawchat.py `test_the_live_tail_reads_agent_live_and_ignores_a_foreign_file`: add `"step": 6` to the planted W-1 entry and assert it comes back.
  - Change (architecture.md "Interfaces"): `__init__` gains `redact: Optional[Callable[[str], str]] = None` stored as `self._redact`; `install` (after the mock-mode return) sets `self._redact = Redactor(default_env_file())` when it is None, importing `Redactor` from `sutra_app.orchestrator.redact` and `default_env_file` from `sutra_app.config` inside the method, with a comment: `# D453: redact before the cut (a cut can split a secret the API's whole-value Redactor then misses); the same .env and environment as the server's`; `progress` stores `entry["text"] = text`, `entry["tool"] = tool` and the new entry's `"step": tag.step`; `snapshot` returns each entry as `{**entry, "text": r(entry["text"])[-LIVE_TAIL:], "tool": r(entry["tool"])[:TOOL_CHARS]}` with `r = self._redact or (lambda t: t)`. Update the class docstring's file shape to name `step`. rawchat.py `live_tail` adds `"step": _num(entry.get("step"))` to the row it builds.
  - Done when: `scripts/py -m pytest tests/engine/test_engine_agent_live.py tests/engine/test_engine_rawchat.py tests/orchestrator/test_runs_watcher_partials.py -q` passes
  - Covers: FR-4 (step), FR-5

- [x] T4: `/api/state` of a live run carries the live agents
  - Files: `sutra_app/engine/views.py`, `tests/engine/test_engine_api_redact.py`
  - Tests first (in test_engine_api_redact.py; its `api` fixture makes a live run at `/api/state?dept=web` and a saved one with `&run=`):
    - In the fixture, copy `tests/ui/fixtures/live/agent_live.json` into the run folder, and add `"fake-token-0123456789"` to `svc.secrets`.
    - `test_a_live_state_carries_the_live_agents_and_a_saved_one_does_not`: `body = GET /api/state?dept=web`: `set(body["live"]) == {"adaptation", "W-2", "audit", "agent"}`; `body["live"]["W-2"]["tool"] == "Reading src/a.py"`, `["since"] == 1793786400.0`, `["step"] == 6`; `"fake-token-0123456789" not in got.text`; `"[redacted]" in body["live"]["audit"]["tool"]`; `len(body["chat"]) == 1` (FR-7: the chat is what chat.jsonl holds). `GET /api/state?dept=web&run=<id>`: `"live" not in body`.
    - The existing `test_no_text_reply_of_any_route_contains_the_planted_secret` must keep passing with the fixture planted.
  - Change: views.py:352-353, inside `if ctx.mode == "live":`, add `live=rawchat.live_tail(_dir(ctx))["agents"]` to the `snap.update(...)` call, with the comment `# D453: who works now (agent_live.json), on the page's one poll`; import `rawchat` (`from . import rawchat`) if views.py does not already.
  - Done when: `scripts/py -m pytest tests/engine/test_engine_api_redact.py tests/engine/test_engine_views.py tests/engine/test_engine_api_scope.py tests/engine/test_engine_rawchat.py -q` passes
  - Covers: FR-2, FR-5, FR-7

- [x] T5: E32a, E32c, E32d, E32e: the live line in chat and on the Map
  - Files: `scripts/port_j2_ui.py`, `tests/ui/test_port_edits.py`, `tests/ui/js/page_render.test.js`, `sutra_app/ui/pages/j2_ui.html` (regenerated)
  - Tests first (page_render.test.js, new section `// E32 (D453): who works now, from agent_live.json`). Helpers: `const LIVEFIX = readJson(path.join(ROOT, "tests/ui/fixtures/live/agent_live.json")).agents; const RUNNING = live => ({...readJson(fixture("state.json")), status: "running", paused: null, live});` and `const call = (page, code) => JSON.parse(page.run(`JSON.stringify(${code})`));` (values cross the vm realm as JSON). Each test makes its own `plain()` page (LIVE is per page).
    - "E32: the who of each live key": `liveLines(RUNNING(LIVEFIX))` maps `k → p` as `adaptation→asha, W-2→mira, audit→nora, agent→""`; lines start `Asha: `, `Mira: `, `Nora: `, `agent: `.
    - "E32: the what is the tool, else the part, else the step; never the text": W-2 what `Reading src/a.py`; adaptation what `Adaptation proposes workflows` (step 2); agent what `Is the site workable?` (no step → the state's step 8); a W-2 with `tool: ""` gives `Item 1` (its part); a tool of 300 chars gives 120; none of the fixture `text` values appears in `JSON.stringify` of the result.
    - "E32: the chat line: one per agent by since, three then +N": `liveTyping(RUNNING(LIVEFIX))` equals `["Asha: Adaptation proposes workflows", "Mira: Reading src/a.py", "Nora: Reading .env (fake-token-0123456789)"].join("<br>") + "<br>+1"` (escaped by `esc`; the page has no redactor, the server did it, T4); with only W-2, `Mira: Reading src/a.py`; with status `waiting`, `Your turn.`; the source of `liveTyping` (`page.run("liveTyping.toString()")`) has no `addMsg` (FR-7).
    - "E32: between calls the last line stays; a fresh page says the step": after `liveLines(RUNNING(LIVEFIX))`, `liveTyping(RUNNING({}))` equals the `agent` line; on a new page, `liveTyping(RUNNING({}))` equals `Is the site workable?`.
    - "E32: the Map lights the live boxes and its chip says the latest line": `m = {status: {state: "Running"}, nodes: [{id: "fn:adaptation", kind: "function", label: "Adaptation", status: "idle"}, {id: "step:charter>site", kind: "engine", label: "Build", workflows: ["W-2"], status: "filed"}, {id: "fn:audit", kind: "function", label: "Audit", status: "idle"}]}`; with `CTX = RUNNING({adaptation, W-2 from LIVEFIX})`, `mapLive(m)` sets both to `running`, leaves `fn:audit` idle, labels unchanged; `mapChip(m)` is `["Mira: Reading src/a.py", "running"]`; then `CTX = RUNNING({})`, `mapLive(m)` restores `idle`/`filed` and leaves no `st0`; `mapChip(m)[0]` is still the Mira line (FR-9).
    - Run them: they fail (`liveLines is not defined`).
  - Change: in `PAGE_EDITS` after E30d add, under a comment block `# E32 (D453): who works now and what …` (three lines, as E30's), using the old/new text in architecture.md "Interfaces":
    - `Edit("E32a", <the sNum/sCap line + "\n">, <the LIVE/liveStep/liveLines/liveTyping/mapLive block> + <the same sNum/sCap line + "\n">, 1)` (sCrew still uses sNum/sCap until T6)
    - `Edit("E32c", <j2_ui.html:1976-1977, both lines>, <the liveTyping line + the lk/paintMap line>, 1)`
    - `Edit("E32d", "function mapChip(m){\n  const st = m.status || {}, ns = m.nodes || [];\n", <same + the CTX/live line>, 1)`
    - `Edit("E32e", "function paintMap(){ paint(", "function paintMap(){ mapLive(MAP); paint(", 1)`
    - Header (:18): 59 → 63 edits, `E19 to E30` → `E19 to E30, E32`, list `E32a, E32c to E32e` in the letters.
    - test_port_edits.py: add the ids to `EDIT_IDS` (:67-71) and one table row each: present fragments (`"function liveLines(s){"`, `"$(\"typing\").innerHTML = liveTyping(s);"`, `"if (CTX && CTX.status === \"running\" && !CTX.paused){ const L = liveLines(CTX)"`, `"function paintMap(){ mapLive(MAP); paint("`), absent fragments (`'s.thinking ? `<b style="color:${col(s.thinking)}">'`, `': s.status === "running" ? "Working…"'`).
    - Regenerate: `scripts/py scripts/port_j2_ui.py --j2 "$J2PAGE" --commit <pin>`.
  - Done when: `node --test tests/ui/js/page_render.test.js` passes (all parity keys still equal: no golden state is running); `scripts/py -m pytest tests/ui/test_port_edits.py -q` passes; `scripts/py scripts/port_j2_ui.py --j2 "$J2PAGE" --commit <pin> --check` exits 0
  - Covers: FR-3, FR-4, FR-6, FR-7, FR-8, FR-9, NFR-1, NFR-3

- [x] T6: E32b: the crew says what the live agents do; the fixed sentences go
  - Files: `scripts/port_j2_ui.py`, `tests/ui/test_port_edits.py`, `tests/ui/js/page_render.test.js`, `sutra_app/ui/pages/j2_ui.html` (regenerated)
  - Tests first:
    - "E32: the crew says what the live agents do": `T = sCrew(S, sModel(S))` with `S = RUNNING(LIVEFIX)`: `T.asha.line === plain("Adaptation proposes workflows")` and `T.asha.busy`; `T.mira.line === plain("Reading src/a.py")` and busy; `T.nora.line === plain("Reading .env (fake-token-0123456789)")` and busy; kabir and dev lines `""`, not busy. Then `sCrew(RUNNING({}), …)`: asha, mira, nora keep those lines and are not busy (Q-5). With the fixture state as it is (waiting, an open question), `T.asha.ask` is true and `T.asha.line` is one of `Needs your OK` / `Has a question for you` (:1087 kept; the same as today's golden-team).
    - Parity (NFR-6): add `const blankCrew = (key, value) => key === "team" ? JSON.parse(JSON.stringify(value).replace(/<small>[^<]*<\/small>/g, "<small></small>")) : value;      // E32 (D453): the crew's lines are Sutra's, the rest of the markup stays J2's` and use it on both sides in the golden loop (:144-148) and per key in the opt-in J2 test (:355-358). Run the suite before the edit: the `team` parity test fails on the deleted lines; with the normaliser it passes.
  - Change:
    - `Edit("E32b", <j2_ui.html:1084-1100 verbatim, from "  const th = s.thinking" to the makers' "} });\n">, <the new body below>, 1)`:
      ```js
        const open = needsYou(s).length > 0 && s.status !== "running" && !s.saved, t = {};
        SKEYS.forEach(k => t[k] = {k, busy: false, ask: false, line: plain(LIVE.last[k] || ""), parts: M.parts.filter(p => p.person === k)});
        const qp = M.parts.find(p => p.st === "ask");
        if (open){ <j2_ui.html:1087's body, verbatim> }
        ["mira", "kabir", "dev"].forEach(k => { const m = t[k];
          if (qp && qp.person === k){ <j2_ui.html:1096's body, verbatim> } });
        liveLines(s).forEach(l => { if (l.p && !t[l.p].ask){ t[l.p].busy = true; t[l.p].line = plain(l.what); } });      // E32 (D453): what the live agents do, from agent_live.json
      ```
      (:1101's handoff line and `return t;` follow unchanged.)
    - E32a's `new` drops the trailing sNum/sCap line (nothing uses them now: their only calls were on :1100). Check with `grep -c "sNum(\|sCap(" sutra_app/ui/pages/j2_ui.html` → 0 after the port.
    - Header: 63 → 64 edits, letters `E32a to E32e`. test_port_edits.py: `E32b` in `EDIT_IDS`; its row: present `"liveLines(s).forEach(l => { if (l.p && !t[l.p].ask)"`, absent each of "Planning the parts", "Deciding what comes first", "Lining up who goes next", "Making sure each part is ready to start", "Talking it through with the team", "Keeping things on track", "Checks each part as it finishes", "Free for the next part", "Waiting for the plan", "Nothing for this project", "Hit a problem", "Wrapped up", "Ready when you are", "Checked the work", "const sNum =". (Not "coming up" or "Reading your request": they are used elsewhere.)
    - Regenerate with the port.
  - Done when: `node --test tests/ui/js/page_render.test.js` and `scripts/py -m pytest tests/ui/test_port_edits.py -q` pass; port `--check` exits 0; the block from `function sCrew(s, M){` to its closing `}` plus the E32a block's removed sNum line is shorter than today's 22 lines for :1082-1103 (count with `awk '/^function sCrew\(s, M\)\{/,/^}/' sutra_app/ui/pages/j2_ui.html | wc -l`, today 21)
  - Covers: FR-10, NFR-4, NFR-6

- [-] T7 (skipped, owner change 3): P47: the rule comment in j2_studio.py
  - Files: `scripts/vendor_j2.py`, `sutra_app/engine/j2_studio.py` (regenerated), `sutra_app/engine/VENDORED.md` (regenerated), `tests/engine/test_engine_vendor.py`
  - Tests first: add `"P47": ("j2_studio.py", "P47 (D453)")` to `marks` in test_engine_vendor.py:191; run `scripts/py -m pytest tests/engine/test_engine_vendor.py -q`: it fails (mark missing).
  - Change: in `OTHER_EDITS` (before its closing `)` at :3607):
    ```python
    # ---- P47 (D453): the studio's rule says what the page's live line may show (comment only)
    Edit("P47", "j2_studio.py", "  the workflow ids it names), never the agents' own words, so no internal term reaches the page.\n",
         "  the workflow ids it names), never the agents' own words, so no internal term reaches the page. P47 (D453): tool lines may be\n"
         "  shown (the page's live line, from agent_live.json); the agents' free text still may not.\n"),
    ```
    and in `PATCH_NOTES` (:3611-3648) `"P47": "(D453; comment only, no code or prompt changes) the docstring of j2_studio.py says that tool lines may be shown and the agents' free text still may not"`. Re-vendor: `scripts/py scripts/vendor_j2.py --source "$J2ENG" --commit <engine pin>`. Check that `git diff --stat` shows only j2_studio.py (docstring), VENDORED.md, vendor_j2.py and the test; if the script changes any other generated file, stop: the pin is wrong.
  - Done when: `scripts/py -m pytest tests/engine/test_engine_vendor.py tests/engine/test_engine_patches.py -q` passes; `scripts/py scripts/vendor_j2.py --source "$J2ENG" --commit <engine pin> --check` exits 0; `grep -n "P47 (D453)" sutra_app/engine/j2_studio.py` prints the line
  - Covers: FR-14

- [x] T8: Full gate, diff review, beta (no commit unless a fix is needed)
  - Files: none (a fix gets its own commit naming its files)
  - Change: `git fetch origin`; if origin/main moved, `git rebase origin/main`, re-port (and re-vendor if a pin moved), rerun T5-T7's done checks. Then, in the foreground: `scripts/gate.sh`.
  - Review: `git diff --stat origin/main...HEAD` lists only the files in architecture.md "Components" plus docs/ai/live-view/*; `git diff origin/main...HEAD -- sutra_app/engine/j2.py sutra_app/engine/j2_map.py sutra_app/engine/j2_realization.py sutra_app/engine/events.py sutra_app/engine/host sutra_app/engine/api` is empty (NFR-2, NFR-5); `git diff origin/main...HEAD -- scripts/port_j2_ui.py | grep '^+' | grep -o '"[^"]*"'` shows no new status sentence (NFR-3); E28, E29 unchanged.
  - Then the live test below.
  - Done when: `scripts/gate.sh` exits 0 (bar failures that also fail on origin/main, listed in the hand-off); the review greps are clean
  - Covers: all FR and NFR (regression); NFR-1, NFR-2, NFR-3, NFR-5

## How to test it live in the beta app
Costs model quota (a real run). The owner starts it; nothing here touches `~/.sutra-pro` or the stable app.

1. Build and open the beta: `scripts/py scripts/install_app.py beta` (it refuses, exit 3, while the beta has a run or a reply going: wait). Tell the owner the version and commit it prints (`Sutra Pro Beta X.Y.Z beta <sha>`). `scripts/py scripts/install_app.py status` shows its port.
2. In Sutra Pro Beta open a team (or make one), switch to the Agent view, and start a run with a page brief, e.g. "A one-page website for a small bakery: menu with prices, opening hours, a pre-order form".
3. Q-1 runtime check, during "What I build" (right after the first questions are answered, before any part exists; the step strip shows J2.b): in a terminal, read the live record once:
   `ls -t ~/.sutra-pro-beta/departments/<team>/runs/ | head -1` gives the run; then `python3 -m json.tool ~/.sutra-pro-beta/departments/<team>/runs/<run>/agent_live.json`. Expect a key `adaptation` with `"step": 2`. A key `agent` instead means Q-1's fallback is needed: tell the developer (T2's fix). Read nothing else in that folder, and never `.env`.
4. What the owner should see:
   | Where | During "What I build" / planning | During building | Between calls |
   |---|---|---|---|
   | Agent view chat, the line under the messages (`#typing`) | `Asha: Adaptation proposes workflows` | one line per working agent, e.g. `Mira: Reading index.html`, at most 3, then `+N` | the last line stays (never `Working…`) |
   | Map tab: status pill | the same line as chat (the latest one) | the line of the agent that started last | the last line |
   | Map tab: boxes | the Adaptation box shows running | each working team box (the "Build" box of that part) shows running | boxes go back to their own state |
   | Simple view: crew | Asha is busy, her line is the step in plain words | the maker of that part is busy, their line is the tool line | each keeps their last line, not busy |
5. Compare with Settings & logs → Raw AI chat (`/d/<team>/raw`), which already shows `/api/agent-live`: a new tool line there should reach chat and the Map in about a second, at most 2 s (NFR-1).
6. Reload the page mid-run: the chat history has no live rows; the line under the messages shows the run's step until the next live entry arrives (FR-7, FR-9).
7. After the run ends, open it again: no live line, the Map pill says how it ended, the crew shows names and roles with the needs-you and parked lines only.

Data read in this test: `GET /api/state` (the page's own poll, now with `live`), which reads `<run>/snapshot.json`, `live.json` and `agent_live.json`; `GET /api/map` for the boxes; nothing new is stored.
