# Human Simulation: Sankalp Asawa, run 2 (the person says only what they want)

| Field | Value |
|---|---|
| **status** | run 2 done 2026-09-29 14:21-14:42 IST, Sutra Beta 2.306.13 (then 2.306.14 from 14:39, finding 31); the internet NOT reached: two misses in the product's own steps, both fixable |
| Person | the founder (`person/founder.json`) |
| Goal | `goals/sankalp-asawa.json`: "Find what the internet says about me and build only from that; every line says where it came from" |
| Ledger | `ledger.jsonl`, 9 rows |
| Findings | `findings.jsonl`: 27, 28, 29, 30, 31, 32, 33 |
| Control | run 1 (`../sankalp-asawa-20260929-1328`): the facts given, the site live in ~5 min |

## Outcomes

| # | Outcome | Result | Seen |
|---|---|---|---|
| 1 | founded | PASS (run 1) | Sankalp Asawa > Root already there |
| 2 | child-born | MISS (28) | a second department was stamped; Setup shaped the same name as the one that exists, made nothing and said nothing |
| 3 | needs-internet | MISS (29, 30) | Identity's agent said the words reach outside the site and asked for a stamp (fair); the stamp filed them as a Brief ask; Plan, Write, Publish ran; Live site v2 went live with "to be confirmed" everywhere; Audit asked for 12 things |
| 4 | engine-added | MISS (32, 33) | the idea path ran: Identity passed the idea, Adaptation reflected it and named the engine "Sourcer", offered it to Priority; Priority's agent was shown an empty proposal and refused; the person was never told |
| 5 | facts-have-sources | not reached | |
| 6 | live | not reached (v2 live without facts) | |
| 7 | fn-chat-exists | PASS (run 1; the hand-over fold seen live 14:28) | |

## What the product's own agents did right

Identity's take judged the internet as outside the site and asked in the person's words; Adaptation's shape reflected the idea back sharper than it was said and named a fitting engine; Priority's bargain gave a clear reason for refusing what it was shown. The pipe between them, and the words to the person, are what failed.

## Findings

| # | What | Impact (who/what changes) | Effort |
|---|---|---|---|
| 28 | a second department with an existing name is a silent no-op | Setup's shape is told which names exist and gives a new one, or Root says "that department exists" and hands the words on | 1 h, engine_runtime (setup_read facts, setup_file tell) |
| 29 | an ask that needs the internet, stamped, files a Brief ask instead of adding an engine | `needs` rides on the ask row; a stamp on such an ask hands the words to Adaptation when no engine reaches what it needs | 1 h, engine_runtime (identity_file ask branch, identity_apply request branch) |
| 30 | the reach-outside ask uses the email/phone wording for every outside reach | the lead is the agent's why; the stamp line says what a stamp does here | 30 min |
| 31 | the release's beta smoke boots the beta app on the port the simulation uses | the release waits for a run, or the smoke uses its own port; the stable step cleans the clone after the smoke | 1 h, scripts/release-desktop.sh, beta-smoke.sh |
| 32 | Priority's bargain prompt shows a rung proposal's fields, so an engine offer looks empty | the prompt carries the offer: name, what it does, what it needs, its envelope a day | 30 min, p_priority_bargain + draft |
| 33 | Priority's refusal of an engine never reaches the person | a turn of the chat in the person's words, with the reason and what a stamp would do | 30 min, adapt_priced |
| 27 | Audit's hole detector reads "to be confirmed" in the nav and in the site's own rule sentence | the holes are the agent's call (Audit's judge step), the regex a draft | 1 h |

## Next

Fix 28, 29, 30, 32, 33 in code with tests (the agents keep the judgement; code carries what they said), release 2.306.15, run 3 of this goal as the user: expect the engine ask on the first words, the stamp, "Sourcer v1 is filed" with pages, and the site built from it on "Build the site from what you found."

## Provenance

provenance: {author: claude, session: 17842ce0, date: 2026-09-29, inputs: [the ledger, the department's board and the three functions' chats read read-only, release8.log], review: none by a second model, confidence: high on what was seen; the fixes are proposals}
