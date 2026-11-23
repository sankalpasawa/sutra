# Multi-agent nodes: the first real-model beta run (checklist)

Status: proposed by the architect, 2026-11-20 (D347); corrected after run 1, 2026-11-20 (D380 to D385, the section "Corrections after run 1" at the end). For the owner, with a developer or an agent beside them. Run 1 was done once with the real Claude on build `edb46f42`; the commands below were then corrected where run 1 showed them wrong. Runs 2 and 3 are not done.
Paths are under `~/.sutra-pro-beta` (the beta app's own data folder, `AGENTS.md`). The stable app and `~/.sutra-pro` are never touched.

## What this run is, and is not

A flag-on beta app, the real Claude, a throw-away git folder, a request of **two read-only steps**. It tests what only a real model can show: the planner splitting a request, the real tool-call shape, a real process, a real stop, a real restart, real cost. It is **not** a test of writers, Codex, lanes, Windows, the Work page, Recipes or Ask. Those stay off.

**Go, if all of these are true (D347):** the folder is a throw-away git folder with its work committed; the working folder's access in Settings is **Read only** (the owner's access caps every step, so even a plan that wanted to write cannot); the owner has set a low dollar limit (suggest $3); Claude is signed in (`claude` answers in a terminal); the beta app was built from the nodes branch (code of `24c7c1be` to `c138f633`; not from the Devin-parity branch, which adds two more migrations); the owner is at the computer for the whole run; Decide for me is **off** in the first run.

**No-go, any of these:** a folder that is not git or has uncommitted work; a folder that matters; no dollar limit; the stable app in use for this; a beta data folder that an older build has opened after a newer one (a database from a newer app is refused: delete `~/.sutra-pro-beta` to start over, as `docs/RELEASE.md` allows); a run on Windows; a release.

**Switches:** `SUTRA_NODES_V1=1` only, and `SUTRA_TOKEN` (below). Leave `SUTRA_NODES_SLOTS`, `SUTRA_NODES_LANES`, `SUTRA_NODES_REVIEWER`, `SUTRA_WORK_V1`, `SUTRA_RECIPES_V1` and `SUTRA_ASK_V1` unset (`0`) for run 1 (the coordinator decided slots stay off in the first run; run 1 was made that way). The app reads `SUTRA_*` from its environment only (not from `.env`), and the desktop app passes on the environment it was started with, so start the beta program from a terminal (quit the beta first):
`SUTRA_NODES_V1=1 SUTRA_TOKEN=<a long random word you make up> SUTRA_DATA_DIR=<a new empty folder> "/Applications/Sutra Pro Beta.app/Contents/MacOS/Sutra Pro Beta"` (if the name differs, `ls` that folder). Opening the app from the Dock has no flags. **The token is never on disk** (a launch token is not written anywhere), so every write you make from a terminal (`curl -X POST ...`) needs `X-Sutra-Token: <the word you set>`; without `SUTRA_TOKEN` the app makes its own and only its own page knows it. `SUTRA_DATA_DIR` keeps the run off `~/.sutra-pro-beta`; the paths below say `~/.sutra-pro-beta` and mean whichever folder you gave. The first time the app opens it shows a **Welcome** dialog: dismiss it before anything else (it covers the chat).

## The runs

- **Run 1** (checks C1 to C11): the two-step request, Decide for me off.
- **Run 2** (C12 to C14): Stop everything and the kill switch while a step runs; then Decide for me on; then `SUTRA_NODES_REVIEWER=1`.
- **Run 3** (C15): a closed-app restart while a step runs.

Stop the whole thing, press Stop everything (or the command line, written as in C4: `... nodes kill --data-dir ~/.sutra-pro-beta`) and write down what you saw when **any** of these happens: a file of the folder changes (`git status --porcelain` is not empty); the cost goes above $3, or above twice the plan's estimate; one step passes 60 model calls or 20 minutes; a question asks for something you did not expect in run 1 (GitHub, the app's own data, several places of the folder); the page or the chat does not answer for 30 seconds; a `claude` program is still running after Stop.

## Checks

**Before**

- **C1 What is installed.** `scripts/py scripts/install_app.py status`: the beta's version and commit; the stable app and its port are unchanged and still answer.
- **C2 The folder.** A small throw-away folder, for example `~/Documents/sutra-beta-try` (a protected folder shows the real Mac window, P5), with 10 to 30 real files, `git init`, everything committed. Write down `git rev-parse HEAD`. `git status --porcelain` must print nothing.
- **C3 Settings in the beta.** Working folder = that folder, access = **Read only**; the monthly dollar limit; Decide for me **off**.
- **C4 Switches.** The command line of the beta is the beta's own program, not a `sutra-pro` on your path: `"/Applications/Sutra Pro Beta.app/Contents/Resources/python/bin/python3" -I -B -m sutra_app nodes status --data-dir ~/.sutra-pro-beta` (the same for `pause`, `kill` and `resume`). Since the fix round it prints the settings **of the shell you typed it in**, labelled so, and then asks the running app for **its own** ("projects are ON" with its settings, or "projects are OFF"); trust the second line, not the first. Expected: projects on, slots, lanes and reviewer off, no pause, no kill. In the app, `GET /api/nodes/status` answers `{"level":"none"}`.

**Run 1: the request**

Say, in the org chat (a message typed there goes to `POST /api/chats/cs_org/messages`; `POST /api/projects` is the other way in and also posts the line to the org chat, with a `client_id`): "Do two separate read-only jobs in this folder and change nothing. Step 1: list the main files and say what each is for. Step 2: read the tests and say what is not tested. Run them as two steps, one after the other, then give me both answers." **A request the planner reads as ONE step does not make a project: it runs the old team path** (that is fine and safe, and it is not a failure of the feature). To get a project of two steps say "two steps, one after the other" in so many words; the run-1 request that did it is the one above.

- **C5 The plan.** The chat makes a project of two steps and shows an "Open the project" link. If it makes one step, say "as two steps" once; if it still does not split, write that down (B1 not seen) and stop: that is not a safety failure. A plan under 400 credits asks nothing. Any question: read the words aloud, answer **No** to anything about GitHub, the app's data or changing the folder; a No must cancel only that step (P1), the others go on.
- **C6 The page.** `/p/<id>` (from the link): the title, two boxes and the line between them, each step's state in words, the spend moving, "What happened" in plain words, Stop everything visible. It updates without a reload. No word like node, lease, tier, grant.issued.
- **C7 The audit.** `sqlite3 -readonly ~/.sutra-pro-beta/db.sqlite3 "select seq, datetime(at,'unixepoch','localtime'), actor, action, target, decision, substr(reason,1,80) from node_audit order by seq desc limit 80;"`. Expected: `project.created`, `plan.accepted`, `grant.issued` for each step, `node.spawned`, `node.leased`, `handoff.accepted` for each step, `tool.used` rows after each step (kind read or search, a file's base name at most, **no command, no URL, no argument**), `project.ended`. Not expected: `scope.violation`, `scope.quarantined`, `scope.unchecked` (read steps are not scope-checked: if one appears, say why in the notes), `node.heartbeat_lost`, `node.error`, `handoff.refused`, `trigger.*`, `grant.denied`. `project.slept` only if the computer slept.
- **C8 Slots and chat.** While a step runs: `ls -la ~/.sutra-pro-beta/connectors/slots`; `lsof +D ~/.sutra-pro-beta/connectors/slots` shows a process holding a slot during a call and nothing after the project ends. Send a plain message in another chat meanwhile: it answers. Write down how many seconds it took (more than 10 seconds means F-2 is needed).
- **C9 Cost and minutes (a first P4 sample).** `select n.plan_ref, n.state, n.attempt, count(u.id) as calls, round(sum(u.usd),4) as usd, round(sum(u.seconds)) as seconds from agent_nodes n left join usage_ledger u on u.task_id = n.task_id group by n.id;` Each step under 60 calls and 30 minutes. A retried step has more than one task, so the page's number is the truth; the credits it shows equal the calls. The dollars match what the provider reported (none is also an answer: write it down).
- **C10 The record of a step (R11).** In `~/.sutra-pro-beta/departments/<team>/runs/<run id>/` count the tool calls and the ones that still hold an input:
  ```
  python3 - <<'PY'
  import json
  total = kept = 0
  for line in open("calls.jsonl"):
      calls = (json.loads(line).get("tools") or {}).get("calls") or []
      total += len(calls)
      kept += sum(1 for c in calls if c.get("input"))
  print("tool calls", total, "still with an input", kept)
  PY
  ```
  Expected: tool calls above 0 and still with an input **0**; the same for `snapshot.json` under `call_log`; `agent_live.json` has no agent left; the run folder has **no** `tools.jsonl`; `~/.sutra-pro-beta/nodes/tools/<run id>.jsonl` exists, one line per tool call with a name and a kind. If the tool calls are 0 for a step that read files, the real shape was not tested: write "not verified".
- **C11 The folder.** `git status --porcelain --ignored` is empty (apart from what was ignored before), `git rev-parse HEAD` is the same, `git diff` is empty.

**Run 2**

- **C12 Stop and kill.** (a) A new project; while step 1 runs press **Stop everything**: all steps end within about 12 seconds, the project is `stopped` with a reason, `project.stopped` is in the audit, `pgrep -fl claude` shows none that the beta started. (b) Another project; while a step runs the beta program's `nodes kill --data-dir ~/.sutra-pro-beta` (C4): everything ends within about 12 seconds, `nodes status` says kill, a new request starts nothing; `nodes resume ...` (C4) and a new request starts again. (c) On the step that was stopped, run the C10 check and write down whether inputs remain (the F-1 question: a hard stop may keep them).
- **C13 Decide for me, off and on.** Turn it **on** in the Simple view. Run a request that makes a question appear, for example step 2 reading the app's own data ("also use my teams and tasks in the app to say which team fits this folder"). Expected: that question (the app's data) is **still asked of you** even with Decide for me on; any ordinary question Sutra answers is listed under "Sutra decided for you" with its words. Turn it on while a question is open: that question is answered at once; turn it off: the next question asks you. If the planner never asks, write "not seen".
- **C14 The reviewer.** Start the beta again with `SUTRA_NODES_REVIEWER=1` added. After the steps a reviewer runs: `review.started` and `verdict.received` in the audit, its call is a usage row of the project, the card or note says "not independent" when only Claude is signed in (and says nothing when Codex is too), the verdict is an opinion, the project ends `done` and not `stopped`.

**Run 3**

- **C15 A closed-app restart.** Start a project, wait until step 1 runs (`pgrep -fl claude` shows its program), then **quit the beta from its menu** (never `kill -9`). Expected: within about 12 seconds no `claude` program of the beta is left; no orphan. Open the beta again with the same switches. Expected: the page loads; each step is resumed or ends with a plain reason; nothing starts twice (one `claude` per step, the usage rows are not doubled); no step stays "working" for ever (a lost heartbeat ends it within the lease, a few minutes); the project reaches a clear state with a reason. The closed time **counts** in the project's running time (D345 h): no `project.slept`. Optional: close the lid for two minutes while a step runs; on waking there is one `project.slept` row and the step goes on.

**After**

- **C16 Words and the Mac window (R9, P5).** Copy every sentence on a card, the page or a note that reads oddly or uses a machine word. Write down the first-start windows macOS showed, when, and whom they named (Sutra Pro Beta, or `claude`, or `node`).
- **C17 Close.** `nodes status` says none; no project is running; no `claude` is left; the folder is clean; the stable app was never touched. Put what was **seen** and what was **not seen** in `dev-notes.md` (N72 on), and tick only what was seen in `build-plan.md`, section "Before publish", group B.

## What a pass is

Every expected result of C5 to C11 in run 1, with any difference written down and explained; C12 to C15 done with their results written down (a difference there is information, not a failure, unless an abort rule fired); no abort rule fired. A pass says only: **this feature worked once, on a Mac, with Claude, on a read-only folder.** It does not say a writer is safe, Codex is safe, Windows works, or a release may go out. The next step after a pass is the owner's choice: a bigger read-only project, then one writer with a scope in a throw-away folder.

## Corrections after run 1 (2026-11-20, build `edb46f42`, real Claude, read-only folder)

What run 1 showed, so the next run starts from facts and not from the first draft of this file. Seen: the planner split the request sensibly into two steps; step a1 finished with a hand-off to a2; the folder was untouched (the tree hash was the same); the kill switch, the command-line kill and quitting the app all worked; no `claude` program was left. Found and fixed afterwards (D380 to D385): a step's tools were wider than its grant; the monthly dollar limit did not stop a running step; the chat reply carried no link to the project page; the project page used engine words; `nodes status` read the shell, not the app; the tool log and `calls.jsonl` look as if they disagree.

- **The token.** Never on disk. Set `SUTRA_TOKEN` when you start the program and send it as `X-Sutra-Token` (see the Switches paragraph).
- **The command line.** `<bundle>/Contents/Resources/python/bin/python3 -I -B -m sutra_app nodes status|kill|resume --data-dir <dir>`. There is no `sutra-pro` on the path of a beta.
- **Where a typed request goes.** To the org chat (`/api/chats/cs_org/messages`), not to `/api/projects`.
- **The Welcome dialog.** It must be dismissed before the chat can be used.
- **One step is not a project.** See C5. The old team path then runs: it is allowed, it is the same as before the feature, and it spent more than a step of a project (below).
- **The first P4 sample.** A trivial two-step read-only job on a folder of 6 files: about **$0.7 and 17 model calls per step** (the page said 23 credits and about $0.97 when the kill switch stopped it in the second step; the ledger also holds the planner's three calls, about $0.08, which the page now counts). The same work as one step on the old path: **31 calls, 6 minutes, $1.83**. These are one sample each, on one folder: not a price list.
- **The monthly limit.** In run 1 the watchdog stopped the second step at $2.93 of a $3 limit; Sutra itself would not have: the Settings sentence ("a task already running finishes") is true for an ordinary task and was true for a step. Now (D381) a project's own dollar limit is what is left of the month when it starts, each step starts with a cap of what is left, and a running project is stopped with "Your monthly limit was reached, so the project stopped." Keep the watchdog anyway in run 2.
- **What a step may do (D380).** Run 1 found the grant line saying "tools none" while the real step could use `Bash` (7 times), `Write`, `Edit` and the web tools; the sandbox was off (`srt not found`). Now the router takes a step's builder tools down to its grant: reads always, writes only in the step's own scratch folder, no shell, no web (D386). Check C7 and C10 again: no `Bash` row, no web row.
- **The Mac permission window was not exercised.** The folder was under `/private/tmp`, which macOS does not protect. P5 and C16 still need a folder under Desktop, Documents or Downloads.
- **Times of the tool rows (D383).** A step's `tool.used` rows are written when the step ends, so they carry the time it ended; the page says so.
- **Counts that look different (D385).** `nodes/tools/<run id>.jsonl` has one line per **tool call**; `calls.jsonl` has one line per **model call**, written when the call **ends**. A model call makes many tool calls (28 log lines against 11 calls), and a step killed in the middle has a call that never ended, so it can have 18 log lines and 0 lines in `calls.jsonl`. Neither is wrong; do not reconcile them.
- **Run 1 did not see:** both steps done and the project ended; a question card; a Mac window; the Stop button on the page; slots; a chat message during a step. They are still open for runs 2 and 3.

## Corrections after run 2 (2026-11-20, build `037750c2`, real Claude, reviewer on Codex)

Seen: the narrowed tool list was accepted by the real program and the step wrote its files in its own folder; no `Bash` or web row; both steps finished and the project ended; the reviewer ran; Stop everything about 2 seconds; kill and SIGTERM left no program behind; the folder was untouched; peak spend $3.49 (keep the watchdog: the limit is a promise Sutra now keeps, but one call can still pass it by a little, D387). Found and fixed afterwards (D390 to D397). For the next run:

- **Resume.** `nodes status` only looks; `nodes resume` is the command in C4 (an app has no `sutra-pro`). There is no Resume button on the page for the switch.
- **SIGTERM mid-step (D397).** The project must NOT end: after the next start the step has a fresh attempt (`node.restarted`), the project is still working, the closed time is left out. Check it in the real app; it was proved only with the fake engine.
- **The reviewer (D393).** Its question says "Send them back" / "Leave as it is"; its verdict should now be about what the step wrote. Read the verdict against the step's own text.
- **Splitting.** Use the wording that worked: "Do two separate read-only jobs ... Run them as two steps, one after the other" (N79).
- **What the page shows (D394, D395).** Each step says its calls, minutes and about how many dollars; no plumbing file is named; the project is titled by the request.
