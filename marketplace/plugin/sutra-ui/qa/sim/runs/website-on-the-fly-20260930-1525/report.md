# Run 5, run 5: the rerun on the released build (Sutra Beta 2.306.21-beta.1), the goal and its variances

| Field | Value |
|---|---|
| **status** | 2026-09-30 15:25-15:42 IST, Sutra Beta 2.306.21-beta.1 (8331), the organisation "Hampi Trip Planner" (61: the record held the baseline's "Hampi Guide") |
| Person | founder (qa/sim/person/founder.json) |
| Driver | run5.py through the app's own routes; the variances after the site went live: a question, a rule, add a page, stop mid-run (root-settings is a screen variance, left for the founder) |
| Cost | 4 min from Found to "Live site v1 is live."; the variances 12 min; stamps: setup, line, publish, rule |

## Outcomes

| Outcome | Result | Seen |
|---|---|---|
| founded | PASS | Hampi Trip Planner Root born from the sheet |
| child-born | PASS | Hampi Trip Planner Website, kind organic, engines [] at birth |
| line-shaped | PASS | one ask: "Set up the line Scout -> Vetting -> Layout -> Launch? ..."; nothing ran before the stamp |
| engines-born | PASS | the four born, chained Brief -> Facts -> Vetted Facts -> Pages -> Live site |
| data-from-internet | PASS | Facts v1 with sources; the pages carry a Source link after each fact |
| site-live | PASS | the publish ask, the stamp, Live site v1 served (index, see, when, reach, stay) |

## Variances

| Variance | Result | Seen |
|---|---|---|
| a-question | PASS | "Which source did you use for the opening hours?" answered from the record in the chat ("The record does not say which source was used for opening hours ... Holidify on How to reach, Karnataka Tourism and Wikipedia on What to see ..."); no new version |
| a-rule | PASS (64) | asked back as a rule, stamped, on the record's rules; Scout's need step said "not needed" for it (38 holds); the rule also became Brief v2 |
| add-a-page | FAIL (62, 63) | Scout filed Facts v2 with "5. FOOD TO TRY (new, for the food page you asked for)"; Vetting's Vetted Facts v2 dropped the section; Pages v2 came back as the same five pages; Launch judged the new pages "not needed"; the food thread closed at its bound |
| stop-mid-run | PASS | "Add a short page on local food safety tips" then Stop and Start: both turns of the chat; Scout resumed on Brief v4 |
| root-settings | not walked | a screen variance; the founder's look |

## Findings

| # | What | Kind | State |
|---|---|---|---|
| 61 | the driver founded the baseline's organisation again; the app handed the words to the old department (right) | driver | FIXED in run5.py (RUN5_ORG) |
| 62 | the need step, made for engines that read the owner's words, gated a chained engine's new input | capability | FIXED IN CODE: no need step for an engine that does not read the Brief |
| 63 | a chained text engine dropped the new section of its input; a pages engine writes every page in one answer (60) | capability | OPEN, building: what changed in the input shown to every born engine; a pages engine plans then writes one page per call |
| 64 | a stamped rule also became a Brief version; one need call, no search | observation | none |

## The kill line of N-028

Read: a site from words went live through engines Adaptation named, none of them a template's, with facts from the internet, in 4 min after one stamp on the line, on the released build. Supported. Growth of the site (a new page) is the next claim (63).

provenance: {author: claude, session: 17842ce0, date: 2026-09-30, inputs: [ledger.jsonl (27 rows), run.json, the record under ~/.sutra-ui-beta/native/dref-35d132206634bbf5 (brief v1-v4, facts v2, vetted-facts v2, pages v2, runs.json)], review: none by a second model, confidence: high on every row (route reads and the record's files)}
