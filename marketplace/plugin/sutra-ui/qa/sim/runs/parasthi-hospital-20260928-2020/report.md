# Run: Parasthi Hospital on Sutra Beta 2.306.8, as the founder, 2026-09-28 20:20 to 20:36 IST

| Field | Value |
|---|---|
| **status** | RECORD; run 1 of the Human Simulation; the agent was the session (Claude in Chrome on the Beta's panel, 8331); every action through the panel's controls; reads for verifying only |
| Person | `person/founder.json` |
| Goal | `goals/parasthi-hospital.json` |
| Ledger | `ledger.jsonl` (22 actions, each with why) |
| Findings | `findings.jsonl` (10) |

## Outcomes

| # | Outcome | Reached | When | Seen |
|---|---|---|---|---|
| 1 | founded | yes | 4 s after Found | Parasthi Hospital and Root in the tree; Root's chat with my words |
| 2 | root-asks | yes | 4 s | the ask card with Stamp and Refuse |
| 3 | child-born | yes, with a miss | 30 s after Stamp | Root said it filed my words; the tree did not show the department until a reload (finding 1) |
| 4 | line-ran | yes | 2 min | Plan, Write, Check ran; the publish ask in the department's chat |
| 5 | live | yes | 20 s after Stamp | the site with What We Treat, Our Doctors, Book an Appointment, About, Contact, FAQ |
| 6 | emergency-on-every-page | in shape, not in fact | | an Emergency Contact section on every page; the number 'to be confirmed' (finding 7) |

## Variances

| # | Variance | Reached | Seen |
|---|---|---|---|
| 1 | facts given in the department's chat (the number, the doctors, what we treat) | NO | Root handed them on in 6 s; then four minutes of silence; the record shows the handling FAILED on a step that was not needed (Restate it as a rule) and nobody was told (finding 9) |

The run stopped here: the fix comes before the other variances.

## Findings, by weight

| # | Finding | Kind | Fix |
|---|---|---|---|
| 9 | a handed request's handling failed on a skipped step's check; silence; Health says all answered | app | a skipped step never fails a run; a failed handling is said back; Health counts Root-handed requests |
| 7 | every fact 'to be confirmed': the department published what it did not know instead of asking | app | Identity asks for the facts a goal needs, one ask, before or right after the first publish |
| 1 | the tree does not show a Root-born department until a reload | app | the Org tree learns of a spawn |
| 6 | after the publish stamp the chat says nothing; no 'live' line, no link | app | Identity tells the owner the site is live, with the link, in the chat |
| 5 | nothing in the chat shows the department working (Write running) | app | a working line in the chat while an engine runs |
| 2 | the department chip in the chat is not a link | app | the chip opens the department |
| 4 | after a reload, Org shows the old chart with ids and jargon | app | one Org screen |
| 3 | my own sentence echoed as a second turn of mine at the child's birth | app | the birth reads as Root's line |
| 10 | the chat shows my words cut at the last sentence; the record has them whole | app | the turn's line shows every word |
| 8 | three unasked pages (About, Contact, FAQ) | expectation | the goal says whether extra pages are welcome |

provenance: {author: claude, session: 17842ce0, date: 2026-09-28, inputs: [the ledger and findings of this run, the Beta's record read for verifying], review: none, confidence: high on what was seen; the causes named in Fix are from the record, not the screen}
