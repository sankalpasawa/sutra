# Human Simulation run 4: the SEO tool as a new use case

| Field | Value |
|---|---|
| **status** | done, 2026-09-29 17:04-18:19 IST, session 17842ce0 |
| Person | the founder, as the user (founder 2026-09-29: "Can you try creating an SEO tool as a new use case?") |
| Goal | `qa/sim/goals/page-seo.json`: a tool that improves the SEO of any page given to it, born from the person's words, never built by hand |
| App | first the Beta on 2.306.17 (8331), then the app from source at sutra 58b39cc0 on 8341 with a record of its own, after the founder's ruling of 17:48; the Chrome extension lost its permission for 127.0.0.1 when its tab group died, so the person's acts went through the app's own front door (the calls the buttons make: found, asks/<id>, ask, stop, resume) and the screen is unobserved from 17:40 on |
| Record | `ledger.jsonl` (14 rows), `findings.jsonl` (49-52), `order.json`, `run.json` |
| Cost | the department's own runs: two page reads by Do (~1 min each), Identity's takes, one Adaptation + Priority round on the first try |

## The ruling this run produced

At 17:48, watching the first try (a stamp, then Adaptation shaping "Page Read", Priority pricing it, a second stamp, then nothing), the founder ruled: "Can you ensure the prompts are very simple and they are not over-engineering things? Very, very little internet is required. Internet is given, and everything. I don't want to lose all the basic features of agents." Built as sutra 58b39cc0: every agent step has the web tools; no ask, no stamp, no shaped engine for reading a page; the idea → engine path stays for a real new capability; the take and do-make prompts trimmed. The second try below runs on it.

## Outcomes (second try, one stamp)

| # | Outcome | Result | Seen |
|---|---|---|---|
| 1 | founded | PASS | Page SEO with its Root from the front door; the one-line setup ask |
| 2 | child-born | PASS | "Page SEO Optimizer", kind default (the first non-website department born from words alone), engine Do |
| 3 | waits-for-engine | expectation stale | written before the ruling; on the first try the ask, the shaping and the stamps happened as expected and then nothing ran (50); on the second try no engine is needed: the words were filed at once |
| 4 | engine-added | expectation stale | same; on the first try Page Read was shaped and stamped (the tool from the words) |
| 5 | report-filed | PASS | "Result v1 is filed." 58 s after the Brief: the page's own H1, H2s and opening text quoted; no title, no description found; five things that hold it back; a title, a description, an H1 and four H2 rewrites, each with its reason; "Delete free unless it is true; the price was not given to me" |
| 6 | second-page | PASS | the address I gave was a 404 (my miss); v2 says so, invents nothing, tries two more addresses, traces where Native lives on the site, keeps the first report |

## Variances (the drawn order: which-matters, other-chats-kept, stop-mid-run, meaning-rule, say-to-priority)

| # | Variance | Result | Seen |
|---|---|---|---|
| 1 | which-matters | FAIL, 51 + 52 | "The record doesn't say which change matters most. It shows no plan yet, a site that is not live..." — the answer never sees the Result's text; the question shown twice |
| 2 | other-chats-kept | not observed | a screen variance; no browser in this stretch |
| 3 | stop-mid-run | PASS | Stop while Do weighed the new words, Start 19 s later; Stopped and Started as turns; Result v2, one version |
| 4 | meaning-rule | PASS | "A rule, as understood: Never change what a page claims; change only how it says it." → stamped → the record's third rule; Do: "not needed: the newest words are a rule" |
| 5 | say-to-priority | PASS | the words in Priority's chat at 18:16:44 and the reply ("A rule, as understood: From now on, always do the second page first.") in the same chat |

## Findings

| # | Finding | Kind | Fix home |
|---|---|---|---|
| 49 | the New organisation sheet's placeholder assumes a website | fix | `22-website.js` wbFoundHtml |
| 50 | nothing ran after the engine stamp on the ask path (no Brief) | superseded by the ruling (sutra 58b39cc0) | - |
| 51 | the answer step reads website-shaped record lines and never the filed Result | fix | `engine_runtime._record_lines`: the latest text of the kind's last artifact, in the kind's words |
| 52 | the owner's words shown twice in a department reached directly | fix | `chat_view` / `request()` for a department without Root in between |

## What the person got

A department born for a tool, not a site, that reads a page it is given and files an SEO report with quoted evidence and a reason per change; a second page reported honestly as unreachable; a rule kept on the record and not re-run; words said to Priority answered where they were said. What the person did not get: an answer about the report's content (51), and a screen (the browser's permission, not the app's).

## Next

51 and 52 through the skills map (a test each, then the fix); 49 with them; the goal file's outcomes 3-4 rewritten to the ruling; the rerun on the Beta once 2.306.18 lands and the browser is allowed again, with other-chats-kept observed.

provenance: {author: claude, session: 17842ce0, date: 2026-09-29, inputs: [ledger.jsonl rows 1-14, findings.jsonl 49-52, read-only route reads of /chat, /chat?fn=priority, /map, /preview/result/1 and /2 on 8331 and 8341, the founder's words at 17:48], review: none by a second model (codex usage-limited, no DeepSeek key), confidence: high on outcomes and variances read from the record; the screen variance is not observed}
