# Impact: sut-27-output-agnostic-result
Base: f21add06. Evidence is file:line under sutra-pro/.

## 0. The constraint that shapes everything
j2_ui.html is the output of scripts/port_j2_ui.py (54 Edit(id, old, new, count) entries; docstring: "Re-port; never hand-edit the copy"). D137 and D191 reject hand edits. D439 rejected new port edits for a render change ("the parity goldens pin the rendered rail; a script from outside changes no byte of the page's own render") and shipped avatars.js, which is listed in MODULES (port_j2_ui.py:57; mirrored in tests/ui/test_port_edits.py MODULES) and wraps root.renderSimple and root.face at load (static/js/avatars.js:190-205).

Recommended route: one new Sutra module (for example static/js/result_view.js) added to MODULES, which takes over sTabs, sViews, sTeamwork's plan cards, sFinish and sTop's #sopen. Port edits are the alternative; they need test_port_edits.py table rows, a re-port, and golden updates.

Page globals declared with `function` (sTabs, sViews, sTeamwork, sFinish, sTop, renderSimple) can be replaced on window. Ones declared with `const` (sNoun, isReady, TYL, runQ, GTYPE) can be read from another script but not replaced. The render harness behind the goldens runs the page script alone, so it does not see a module (stated in D439; not re-tested here).

## 1. The centre panel today (j2_ui.html)
Markup: #sstage > #sframebox > .schrome with #sviews (tabs), #surl and device buttons; #sout holds #sprevbox (iframes #sframe and #sframe2, sandbox "allow-scripts allow-forms allow-popups") and #steamwork; then #sfinish (the bottom bar). Lines 51-63. Top-bar "Open the site" is #sopen (:41).

- Tabs, sTabs (:1326-1339):
  - Doc tabs per docset (:1329-1331).
  - "Page" (TYL("site","Page")) whenever s.versions > 0 and !s.doc (:1332-1333). A folder (script) run has versions > 0 but no page file, so it still gets "Page". That is the "before" mock's empty Page tab.
  - One tab per extra deliverable, "a:"+d.name, opened as /view?name=<file> (:1335-1336). It is de-duplicated by name, and every file of one multi-file type shares one name: j2_artifacts.rows gives name = label when t["kind"]=="type" (j2_artifacts.py:159-160). So one tab appears ("Environment report script") and the other files are hidden.
  - "How it was made" when done or saved, else "Team at work" (:1337).
- Default tab, sViews (:1342): the user's pick, else the LAST output tab, else team. No notion of a main result. A toast fires while running: "The page is taking shape" / "The X is being written" (:1344). URL label: "preview", "live preview", "<label> · document", "how your project was made" (:1350).
- Grey bars: each part card in sTeamwork always ends with `<span class="sl"><i></i><i></i><i></i></span>` unless it is doing/fix (:1613); done cards get them too. CSS: static/css/j2.css:344-358 (`.spart .sl i`, `.spart.done .sl i`). Placeholder cards while there is no plan: :1617-1618.
- "What the team made": one card per SV.arts.deliverables (from /api/artifacts) plus "Proof and records" (:1621-1623). Clicking opens sOpenArt (:1741), a drawer with Goal/Method/Output/Check from /api/record?art=.
- "What you got" / "Ready so far": markdown/docx links, plus "The <page>, version N" when !s.doc && s.versions > 0 (:1624-1628).
- Activity log "Worked for Xm · N steps" (:1630-1637). Lines come from j2_studio.stream, e.g. "Mira finished env report.py" (j2_studio.py:157-160).
- Bottom bar, sFinish (:1124-1132), drawn at :1244. Text: sPhase → "Your <noun> is ready" (:1110), noun = sNoun (:1106) = output_label. Non-doc Download is `<a href="/site/latest" download="<output>.html">Download</a>` (:1128), so a script run downloads an empty or "No site" HTML. Also "Download the page" for docset runs (:1127), "All files (N)", "Copy share link", "Open full view".
- Top bar #sopen: "Open the site" when !s.doc && versions > 0, else "Download" (:1300-1303). Hidden on phone (j2.css:592).

User-visible site/page strings to make output-aware:
| line | text |
|---|---|
| :41, :1302 | Open the site |
| :1127 | Download the page (TYL("site","page")) |
| :1128 | Download → /site/latest as .html |
| :1314, :1615 | group heading "Page" (GN.site) |
| :1332-1333 | tab "Page" |
| :1344 | toast "The page is taking shape" |
| :1350 | url "preview" / "live preview" |
| :1120 | "Checking it on a phone and a laptop" (phase while checking) |
| :1627 | "The page, version N" |
| :1736 | "The part, on the page." (part drawer) |
| :1662 | "Your <what> passed the checks and is ready." (noun-based; fine) |
| views.py:705 | "No site in this run." (saved /site stub; engine-side, out of scope) |
| views.py:720 | "Your <noun> will appear here once it's built." (live stub) |

Start page examples (:1118, "A website for my bakery") are not the result panel.

## 2. Page preview to reuse
- The double-buffered sandboxed iframe: sLoad/sFrameLoaded (:1359-1370), with sFrameSetup decoration (:1371+). The sandbox has no allow-same-origin (D83, D153), so sDoc() cannot reach the frame's document and decoration quietly does nothing.
- Server: /site/v<N> and /site/latest (views.site, :729-731; live reads site/v<N>.html, saved lists site/v*.html|md). /view?name=<file> runs view_page (views.py:574-598): markdown rendered, html as is, images inline as data URLs, anything else as an escaped `<pre>`. It is the existing generic file-as-page viewer. Every text/html engine response gets a CSP sandbox header (D83, engine/api/reply.py).

## 3. Data the UI already has per run
- /api/state (views.state :342; J2Run.snapshot j2.py:4327-4366):
  - status, outcome; isReady = /^Done/ && !paused && status != running (j2_ui.html:1010).
  - output, output_label, doc, page, files (only the output's .md/.docx), docset_files, versions (= builds), types (labels/forms per type), workflows (each: id, name, purpose, outputs = files planned, status, covers, section, real_run when planned), atoms_v1 (each atom: workflow, output: [{verb:"make", ref:<file>}]), chat/allChat.
  - studio = j2_studio.build: parts [{sec, id, name, doc, kind, person, st (done|doing|fix|next|bad|ask), fixing, fixes, workflows}], stream, done, total (j2_studio.py:96-118, :163-167). Parts carry no files and no summary.
- Files per part: workflows[].outputs (fixture: ['index.html']) and atoms_v1[*].output refs, both keyed by workflow id; part.workflows links them. A heuristic alternative: /api/artifacts/groups folder rows give files[].made_by, the workflows whose checks named the file (j2_artifacts.py:731-757).
- Builder summary: NO dedicated one-line field. Closest is the builder's chat message (who "W-n") with human_output, "1 to 3 plain sentences telling a person what you built" (prompt j2.py:10427, :10738, :12159; set :10583, :10723, :10972; canned for mocks/reuse :10365, :10374, :10859, :10901). It is model-written, can be up to 3 sentences, and a fix writes a newer message, so take the last W-n message per part. j2_studio deliberately avoids agents' words (j2_studio.py:6-8). /api/record?sec= gives goal/method/output/check, not a summary (j2_studio.py:171-195). We cannot change the engine.
- Output files: /api/artifacts → {deliverables, records}; each row has name, type, kind, form (page|document|agent…), file, version, sha256, time, label, open (j2_artifacts.py:184-194). Folder (agent form) outputs are "{name}/*" (types.json forms.agent: output "folder", preview "folder"), one row per file.
- Main result: none today. The type has entry_file (j2_types.py:435: page site/index.html, folder "<name>/*"). There is no per-run main-file field; SUT-23 adds it.

## 4. Serving files
- /api/artifact?name= (views.py:559-570): raw bytes; png → image/png, docx → DOCX with a filename, .html → text/html, everything else text/plain (so jpg/gif/svg/csv are text/plain).
- /view?name= (views.py:625-627): as a page (see 2).
- /file/{name} (views.py:686-697): only the output's .md/.docx and documents.json kinds.
- /doc/{name}, /shot/{n}, /site/{key}.
- Allow-list j2_artifacts.served (:197-206): rows ∪ tree files, no "..", no absolute paths, MAX_BYTES 2,000,000 (:20). A larger file cannot be served.
- Listing: /api/artifacts (rows) and /api/artifacts/tree, /api/artifacts/groups (everything, grouped). There is no flat "list the run's output files" route beyond these.
- The real-run output folder (e.g. report.txt in the user's folder) is NOT in the run folder and has no route. Today that file shows up only in deliverable.json changes (D135, git-based, only when the folder is a git work tree; loop.py:760-770, host/folder_watch.py:1-15) and in the real_run receipt. D428 export copies deliverables into the team folder after the run (host/export.py).

## 5. Share link and private data
- Code: j2_ui.html:1883-1884. It writes `${location.origin}/site/latest${runQ}` to the clipboard, shows "Link copied", then resets after 2.5 s. It shares the page only, and the origin is loopback-only (main.py:20, :78-107), so it works only on this machine.
- Private-data markers: there is no run-level flag. Searched sensitive|private|share|secret_file across sutra_app; the hits are unrelated (egress scrubbing, file modes). Available signals:
  a. workflows[].real_run in /api/state: folder, reads, secret_files (realpaths), settings (j2.py:775-778 real_folders, :828-831, :9823-9847).
  b. A team working-folder grant: WorkFolder(...).team_grant(dept) (loop.py:331, :562-573, :730-742). The run is seeded from the folder, and deliverable.json.changes lists what changed. Not exposed in /api/state (unverified whether any other route exposes it).
  c. receipts.jsonl real_run rows (approved, ran, exit, stdout/stderr tails since P42/D447, dry_run created/changed/deleted; j2.py:6101, :6134, :6170, real_run :903-962). /api/artifacts/groups exposes a subset without stdout (j2_artifacts.py:774-793).
  d. Chat attachments (D440) and connector tools live in orchestrator chats; a run's /api/say body has none (j2_ui.html:1782).
- Proposal for the spec: treat a run as private when (a) any workflow has real_run, or (b) the team had a folder grant, or (c) receipts hold a real_run. Then "Copy share link" asks before copying, or is off until the user turns sharing on. (b) needs a server-side read that is not in the engine (views/state or a small UI route).

## 6. SUT-23 and SUT-28: stay out
- Main result later: a plan field from SUT-23; nothing exists today. Real-run stdout exists in receipts (P42/D447) but no route carries it to the page.
- Do not edit (engine real-run, sandbox, env): sutra_app/engine/j2.py, engine/runenv.py, engine/llm.py, engine/artifacts/real_run.md, engine/artifacts/types.json, engine/j2_types.py, engine/j2_artifacts.py, engine/capabilities/base.py, engine/host/* (loop.py, export.py, folder_watch.py), engine/VENDORED.md, scripts/vendor_j2.py, orchestrator/builder_rights.py, connectors/egress.py, ops/browser.py, tests/engine/test_engine_patches.py.
- Grey zone: engine/views.py and engine/api/* are the app's own handlers (D25) rather than vendored J2. The request says "UI only", so treat them as off-limits unless the spec says otherwise.

## 7. Tests
| test | covers | narrowest command |
|---|---|---|
| tests/ui/js/page_render.test.js | the generated page vs J2 goldens; finish card asserts "Copy share link", "Open full view", download=*.html (:292-302) | node --test tests/ui/js/page_render.test.js |
| tests/ui/test_port_edits.py | edit table, MODULES list (:36-37), page invariants | scripts/py -m pytest tests/ui/test_port_edits.py -q |
| tests/ui/test_dept_page.py (browser) | finished studio: finish shows ["Download","Copy share link"] (:888-918); part record (:1072) | SUTRA_BROWSER=1 scripts/py -m pytest tests/ui/test_dept_page.py -k "one_way_to_each_thing or opens_its_record" |
| tests/ui/test_serve.py | page serving, CSP hashes, module tags | scripts/py -m pytest tests/ui/test_serve.py -q |
| tests/ui/js/avatars.test.js | the module-wraps-page pattern to copy | node --test tests/ui/js/avatars.test.js |
| tests/engine/test_engine_views.py | view_page, artifact, served | scripts/py -m pytest tests/engine/test_engine_views.py -q |
| tests/ui/test_node_suite.py | runs every tests/ui/js/*.test.js inside pytest | scripts/py -m pytest tests/ui/test_node_suite.py -q |
| tests/engine/legacy/j2_flow_test.py | legacy J2 strings ("Copy share link", "What the team made") | slow; leave alone |

Gaps: no fixture for a folder/agent-form run, no test for a non-page result, none for privacy or share. The fixtures are a website run (tests/ui/fixtures/j2/state.json: output "website", versions 5). A new state fixture for a script run is needed. Fake backend: tests/ui/fake_backend.py serves /view and /api/artifact for browser tests.

## 8. Decisions that constrain the panel
- D137, D191: the page is generated; no hand edits.
- D439: new UI behaviour as a Sutra module, not port edits; the goldens stay byte-stable.
- D82: script-hash CSP. No new inline `<script>`, no CDN, no fonts; img-src allows data: and blob:.
- D83, D153: generated HTML is served sandboxed and frames never get allow-same-origin. A rendered HTML result must stay in the sandboxed frame.
- D74, D138: one stylesheet, no web fonts. j2.css is generated and Home keeps j2-shell.css, so new styles go in a Sutra sheet (avatars.css precedent).
- D25, D168: data routes are views over J2's data, one implementation.
- D241: forms are data (page, document, folder). Choose a viewer by form/extension, never by type name.
- D165: no default output type; the UI must handle output == null.
- D428: deliverables are copied to the team's own folder on done; relevant to "Show in folder".
- D135: folder changes come from git, never from an agent; the source for "what changed in the folder" later.
- D434-D438, D446-D448: real-run rules (receipts, dry run, env); read-only for this task.
- D99: no home paths in files.
- Next free decision number for this task: D450 (request.md).

## Open questions (orchestrator defaults, pending owner OK at plan review)
1. Route: new Sutra module (D439 pattern). Default: yes.
2. Builder summary: show the last W-n chat message's human_output, first sentence, clipped to one line. Default: yes (the request asks for the builder's one-line summary; it is the only source).
3. Private-data rule: which signals count. Default: real_run workflows or real_run receipts (both visible without a server change); a folder grant needs a server read, so the spec proposes it as a follow-up.
4. Download for a folder run: default per file through /api/artifact; no zip.
5. engine/views.py: not touched. CSV/JSON parse client-side from /api/artifact text; images via /view (data URL) or blob.

## Unverified
- A folder-form run shows an empty "Page" tab live and "No site in this run." when saved (inferred from views.py:295-301, :696-708 and j2.py:10811-10830, not run).
- Whether /site/* needs the page token.
- Desktop tests not inspected.
