# Run 2: Parasthi Hospital on Sutra Beta 2.306.10, as the founder, 2026-09-28 21:39 to 22:06 IST

| Field | Value |
|---|---|
| **status** | RECORD; run 2 of the Human Simulation (the rerun after v2.306.10 shipped run 1's fixes); the agent was the session (Claude in Chrome on the Beta's panel, 8331); every action through the panel's controls; reads for verifying only |
| Person | `person/founder.json` |
| Goal | `goals/parasthi-hospital.json` (the department of run 1, continued: its Root and site already existed) |
| Ledger | `ledger.jsonl` (31 rows, each with why) |
| Probe | `probe.jsonl` (two probes, every 2 s on the department's map) |
| Report of run 1 | `../parasthi-hospital-20260928-2020/report.md` |

## Outcomes

| # | Outcome | Reached | When | Seen |
|---|---|---|---|---|
| 1 | founded | yes (run 1) | | Parasthi Hospital > Root > Parasthi Hospital Website in the tree |
| 2 | root-asks | yes (run 1) | | |
| 3 | child-born | yes (run 1) | | the chip opened the department (finding 2 fixed) |
| 4 | line-ran | yes | 3 min per version | Plan, Write, Check, Publish; the chat said which function was working (finding 5 fixed) |
| 5 | live | yes: v2 at 21:45, v3 at 21:56, v4 at ~22:04 | 3 min after the words | "Live site vN is live." with Open the live site, which previewed it in the app (finding 6 fixed) |
| 6 | emergency-on-every-page | NO: 3 of 8 (v2), 4 of 8 (v3), 3 of 8 (v4) | | "to be confirmed" gone from every page (finding 7 fixed, the department asked for the facts); 108 on some pages only, with a stamped rule that says every page (finding 12) |

## Variances

| Variance | Done | What happened |
|---|---|---|
| facts given | yes | the words of run 1 that died at 20:30 were filed at 21:42 (finding 9 fixed); six holes asked at 21:46, answered, one new hole asked at 21:57, answered |
| question | no | typed and lost: the box had moved as turns grew and the Send click missed (the driver's miss, not the app's); not retried |
| rule | yes | restated in one line within a minute, stamped; the next two versions broke it on four and five pages (finding 12) |
| stop/start | yes | the Map's switch; Off, engines STOPPED; On, the line finished its request; one failed run in the day's count; no word of it in the chat (finding 15) |
| careers, feedback | no | not tried this run |

## Findings

| # | Finding | State |
|---|---|---|
| 1, 2, 5, 6, 7, 9, 10 | run 1's | FIXED as seen by the person (10: not measured this run) |
| 3 | the goal echoed as an owner turn at birth | alive (seen on Namrati's birth, 22:03) |
| 4 | the app opens on the old Departments chart with ids | alive, at the very first screen |
| 11 | the panel stops answering around a publish | MEASURED: 25 s twice at 21:45:30 and 21:45:56, 18 s at 21:56 |
| 12 | "every page" honoured on some pages; a stamped rule is not a check | NEW, hard: v2 3/8, v3 4/8 with the rule stamped, v4 3/8 |
| 13 | the person's own address put to them for a stamp with "This reaches outside the site" | NEW |
| 14 | a stamp on a go-ahead or rule ask inside the department leaves no turn | NEW (publish asks do show Stamped / Refused) |
| 15 | Stop and Start leave no word in the chat; the working line survives a stop | NEW (the record holds them as Identity runs) |
| 16 | an answer to the department's own facts question read as a rule and put for a stamp | NEW |
| small | after Send the chat scrolls to its top; no chip on the person's turn when the department is named in words; Root's box placeholder invites a new department; no page n of m on the working line; a quoted hole cut mid-word | NEW |

## Speed (SIM-3 b)

The words answered ("filed in the Brief") within the minute; a version live 2.5 to 3 min after the words; the panel answered under 3 s at every reading but the three around a publish.

## Verdict

Run 1's fixes hold as a person meets them: the app now says what it is doing, says when the site is live with the way to it, asks for the facts it lacks, and never loses a word at the front door. The site is not what the person asked for on one count: the emergency number on every page, and a stamped rule did not make it so. That is the next fix (finding 12), with the publish stall (11) and the chat's silence on stamps, stops and starts (14, 15).

---
provenance: {author: claude, session: 17842ce0, date: 2026-09-28, inputs: [ledger.jsonl 31 rows, probe.jsonl 292 readings, site-check.sh over 8 pages at v2 v3 v4, the department's chat and map by the panel's routes], review: none by a second model; the founder's own look is the control, confidence: high on outcomes and findings 11 to 16 (each has a row with what was seen); moderate on the cause of 11 (numbers, not the mechanism)}
