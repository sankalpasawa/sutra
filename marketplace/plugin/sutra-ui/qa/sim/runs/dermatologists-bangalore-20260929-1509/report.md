# Human Simulation run 3: Best dermatologists in Bangalore, from scratch

| Field | Value |
|---|---|
| **status** | done, 2026-09-29 15:10-15:54 IST, session 17842ce0 |
| Person | the founder, as the user (founder 2026-09-29: "Can you start from scratch? Best dermatists in Bangalore as an example of a department"; "obey the prompts so it builds everything as a user, as a product") |
| Goal | `qa/sim/goals/dermatologists-bangalore.json`: a new organisation from the app's own sheet whose first department finds the dermatologists on the internet through its own functions and builds the site from what it found, each with where it came from |
| App | Sutra Beta 2.306.15 on 8331 (run 2's fixes 28-33 carried); department `dref-d2ebc5193ec30d67` under Bangalore Skin Guide Root |
| Record | `ledger.jsonl` (24 rows, every click with its why), `findings.jsonl` (34-46), `order.json` (the drawn variance order), `captures/` |
| Cost | four web searches by Source Reader (~1.9 USD each); five Brief versions; four live versions |

## Outcomes

| # | Outcome | Result | Seen |
|---|---|---|---|
| 1 | founded | PASS | Bangalore Skin Guide with its Root from New organisation..., Found (rows 1-3) |
| 2 | child-born | PASS | one Stamp on a one-line ask; Bangalore Skin Guide Website born 15:11:18 with the goal in its own words (row 4) |
| 3 | needs-internet | PASS with 34 | Identity: "no engine of mine reaches the internet yet, so Adaptation is shaping one, and an ask to add it follows"; the engine ask at 15:12:02; the line ran meanwhile and built a site of "to be confirmed" (34) |
| 4 | engine-added | PASS with 35, 36 | Source Reader first in the line at 15:13:36, running at once; "Source Reader v1 is filed." 15:15:19 |
| 5 | list-has-sources | PASS | real dermatologists with URLs and read dates, single-source claims marked, Not sure for the page it could not read (37) |
| 6 | live | PASS with 39-41, 44, 46 | "Build the site from what you found" -> v1 live 15:28 (9 pages, 12 addresses on Sources); v2 15:38 (Top Three); v3 15:47 (the dropped name gone); v4 15:52 (source under every line) |

## Variances (the drawn order: stop-mid-run, drop-one, source-rule, other-chats-kept, say-to-priority)

| # | Variance | Result | Seen |
|---|---|---|---|
| 1 | stop-mid-run | PASS | Stop on System status while Write was on the pages: "Stopped by you: every engine stops where it is." 15:45:54; Start: "Started by you: every engine looks to its own triggers." 15:46:29; Write resumed at page 4 of 8; one version (rows 19-20) |
| 2 | drop-one | PASS | "Take Dr. Rasya Dixit out everywhere." -> v3 has no page or line with the name (row 21) |
| 3 | source-rule | PARTIAL, 45 | the words were asked for with the request's lead and, stamped, went into the Brief under Asked since; Write honoured them; the map's rules unchanged; nothing checks them |
| 4 | other-chats-kept | PASS | Identity's, Adaptation's, Identity's chat again: each its own existing chat with its think rows; nothing started, nothing lost (row 17) |
| 5 | say-to-priority | PASS on the words; 42, 43 | the words in Priority's chat at 15:34:50; Send took the screen to the department chat; what came of the words landed only there |

## Findings

| # | Finding | Kind | Fix home |
|---|---|---|---|
| 34 | the line runs before the engine the goal needs exists; a site of invented facts reached its publish ask | design (idea -> claim, untested by choice) | `engine_runtime.py` Identity's gate |
| 35 | the working line says "reading Brief" for the whole 90 s search | fix | the run row's `what` per step |
| 36 | the filed turn's button says "Open the live site" | fix | the tell's button word |
| 37 | PASS: the internet reached from the person's words alone | - | - |
| 38 | an engine that reads the Brief re-runs its search on every Brief version (4 of 4 here, 1 asked for) | design (untested by choice) | the engine's own step reads whether the words ask for it |
| 39 | Open the live site opens the preview without lighting the row; the next repaint takes the person to the Human Sutra page | fix | `22-website.js` open selects the row |
| 40 | source addresses are text, not links | fix | Write's page template |
| 41 | Audit checks against the Brief only; the facts question asks the person for what an engine could find | design (untested by choice) | Audit reads the filed artifacts; the facts question to the engine first |
| 42 | Send in a function's chat takes the person to the department chat | supported (founder ruling 2026-09-29) | `22-website.js` |
| 43 | what came of words said to Priority lands only in the department chat | supported (same ruling) | the tells posted to the source chat too |
| 44 | the "does not know N things" reader quotes the nav bar's link text (finding 27 again) | fix | the hole reader skips nav and header text |
| 45 | a stamped rule is filed as a request line, not a rule; nothing checks it | fix (finding 12's path) | Identity's take files a rule as a rule; Check runs it |
| 46 | each re-search replaces the source record; v4 covers 3 sources where v1 had 4 | design (goes with 38) | a search adds, or says what it dropped |

## What the person got

A site that lists dermatologists named on public pages, each with the page it came from, that says it does not rank and marks single-source claims; the top three first; a name dropped everywhere on one sentence; a rule honoured on the next build. What the person paid for that they did not ask for: three web searches, one site of "to be confirmed" with a publish ask, one wrong "put right" ask, and two screen jumps.

## Next (the skills map in `qa/sim/AGENT.md`)

Stage per `core:native`: 35, 36, 39, 40, 44, 45 fix; 42, 43 supported; 34, 38, 41, 46 untested by choice with their kill line = the rerun's outcome row on the released build. Then `core:native-builder` per group, `core:test-strategy` for the test per finding, release from the shared clone (never while a run is live: 31), rerun this goal with the untried moment of stop-mid-run right after the publish ask.

provenance: {author: claude, session: 17842ce0, date: 2026-09-29, inputs: [ledger.jsonl rows 1-24, findings.jsonl 34-46, read-only route reads of /chat, /chat?fn=priority, /map, /site/*.html, /preview/brief/5, the screenshots of the session], review: none by a second model (codex usage-limited to 2026-10-16, no DeepSeek key), confidence: high on outcomes and variances, which the record shows; moderate on the cost figures, which are the run rows' totals}
