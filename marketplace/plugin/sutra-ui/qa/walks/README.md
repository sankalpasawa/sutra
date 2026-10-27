# Walks: the app from source, a person at the front door, the screens captured

| Field | Value |
|---|---|
| **status** | v1, 2026-09-28, session 17842ce0 (founder: "add the tools at the right place so that we can fetch it again for the Mac app Sutra") |
| Home | `sutra-ui/qa/walks/`; the checks ADHERENCE quotes live beside the record, `holding/plans/engine-runtime/adherence-run.sh` |
| Touches | a record directory of its own; never `~/.sutra-ui` |

Every tool takes its paths as arguments. None names a session's scratchpad.

| Tool | Does | Usage |
|---|---|---|
| `devserver.sh` | the app from source on a record of its own, engine runtime and motor on, real model; foreground | `devserver.sh [record-dir] [port]` |
| `devserver-detach.sh` | the same as its own process; stops this app's listener first; checks it answers | `devserver-detach.sh [record-dir] [port]` |
| `devserver-stop.sh` | stops the listener on the port, only if it is this app's uvicorn; prints any other holder | `devserver-stop.sh [port]` |
| `kill-stale.sh` | stops this app's uvicorns that lost the port but still hold the record's motor lock on old code; waits for the listener to take it | `kill-stale.sh [record-dir] [port]` |
| `walk-front.sh` | says words on a Root and prints each turn as Root hands them on and the department answers | `walk-front.sh "<words>" [root-name] [base-url] [seconds]` |
| `shot-chat.js` | headless Chrome captures: Root's chat, a department's chat, the Board, Priority's Settings | `node shot-chat.js <out-dir> [base-url]`; env `WALK_ROOT`, `SHOT_PORT`, `CHROME` |
| `suites.sh` | every suite of the department and its screen, one process each | `suites.sh` |
| `shot-j2.js` | headless Chrome over the DevTools protocol: the J2 page in the app, looking, clicking, counting its claims, writing the screenshots; or the page's DOM outline | `node shot-j2.js <out-dir> <base-url> <dept-ref> [kind]`; env `CHROME` |
| `j2ui-e2e.sh` | the five seeded departments (start, question, building, ready, hostile) on a record of its own, `shot-j2.js` on each, and the page's structure against the prototype's own; says so and exits 0 without Chrome | `j2ui-e2e.sh [record-dir] [port] [out-dir]` (port 8362) |
| `j2ui-against.sh` | does the J2 page still hold against a branch about to merge: the contract, render, chat and audit tests on a temporary merge, then the worktree is removed | `j2ui-against.sh <branch> [base]` |

A walk, end to end:

```bash
W=sutra/marketplace/plugin/sutra-ui/qa/walks
bash $W/devserver-detach.sh /tmp/sutra-walk 8341        # the app on a record of its own
open http://127.0.0.1:8341/                             # Org, New organisation..., a name, Found
bash $W/walk-front.sh "On Sunrise Physio Website, add a Careers page." "Sunrise Physio Root"
node $W/shot-chat.js /tmp/sutra-walk/shots              # the four screens
bash $W/kill-stale.sh /tmp/sutra-walk 8341              # when a walk stalls: an old process may hold the clock
bash $W/devserver-stop.sh 8341
```

What each one proved on 2026-09-28 is in `holding/plans/website-department/WALK.md` sections 7 to 10.

## Provenance

provenance: {author: claude, session: 17842ce0, date: 2026-09-28, inputs: [the session's scratchpad scripts devserver6.sh, devserver-stop.sh, devserver-detach.sh, kill-stale-uvicorns.sh, shot-chat.js, walk-front.sh, suites-front.sh], review: none by a second model, confidence: high; each tool ran at least once from the scratchpad the same day}
