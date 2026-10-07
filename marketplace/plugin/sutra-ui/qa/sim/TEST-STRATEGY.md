# Human Simulation: the test strategy

| Field | Value |
|---|---|
| **status** | v1, 2026-09-29, session 17842ce0 (the map's Prove phase, `core:test-strategy`) |
| Subject | how a finding from a run as the user becomes a named test before its fix, and how the rerun proves the fix |
| Risk profile | user-facing: the person sees the app work or say why not, at every step (Founding Doctrine P0) |
| Suites | `test_engine_runtime.py` (unittest, a fake Model per step id, a throwaway registry per test), `test_website.js` (node, a vm with a fake `apiGet` and a rendered view), `test_website_dept.py` (the record) |
| Home | `qa/sim/` beside `AGENT.md` (the runbook) and its skills map |

## 1. Subject and risk

A finding is a row `{outcome, expected, seen, capture, why_it_matters}` written by the agent while it walked the installed app as the person. The fix is only a fix when a test states the finding's `expected` and fails on the code that produced `seen`; the rerun on the released build is the acceptance test, its outcome row the kill line for a design finding (ledger N-024..N-027).

## 2. The pyramid

| Layer | Share | What it carries |
|---|---|---|
| Unit, runtime (`test_engine_runtime.py`) | 55% | one test per runtime finding: the department walked by `live()`, `ask()`, `stamp()`, `idle()`; the Model answers by step id; assertions on the record (versions, asks, rules, run rows, chat lines) |
| Unit, screen (`test_website.js`) | 30% | one test per screen finding: the view rendered in the vm from a fixed map and chat; assertions on the HTML and the state (`st.tab`, `st.sel`, `dpS().tab`) |
| Golden strings | 10% | an ask's or a tell's exact lead ("Your words need internet, which no engine of mine reaches", "A rule, as understood") asserted by prefix, never by regex on the whole |
| Acceptance | 5% | the rerun as the person on the released Beta; its report's outcome rows |

No E2E in CI: the app under a browser driver is the rerun, run by the agent, not by a job.

## 3. Fixtures

| Boundary | Fixture | Why |
|---|---|---|
| the model | the fake `Model` (answers per step id, counts prompts) | a test never calls the model; a prompt's text is asserted (`self.M.prompts`) |
| the record | a real registry in a tmp dir per test | the record is the product; faking it would test nothing |
| the clock | `R.WAITS = (0, 0, 0)`; times read from rows, never compared to now | no sleeps, no flakes |
| the Library | a copy of `engine-templates/` in a tmp dir when a test births an engine | a born template must not land in the repo |
| the panel's routes | a fake `apiGet` returning fixed JSON | the screen is tested on what the routes give, not on the server |
| the web | never | a step with tools is asserted by the args handed to `claude -p` (test_90), never by a search |

## 4. The mock-vs-real boundary

```
+--- BOUNDARY ----------------------------------------------------+
| Real:  engine_runtime.py, website_dept.py, the record on disk,  |
|        the templates, the screen code in a vm                   |
| Fake:  the model (per step id), the clock, apiGet, the web      |
| Reason: the product is the record and the code that writes it; |
|        the model's judgement is the eval pack's, not the unit's |
+----------------------------------------------------------------+
```

## 5. Coverage

| Target | Value | Why |
|---|---|---|
| a test per finding | 100% of the findings a unit closes | the atom's verify counts them (`def test_9[6-9]`) |
| branch on the changed functions | every new branch touched by a test | the fake Model reaches each verdict/answer by name |
| line | not measured | the finding list, not a percentage, is the floor |

## 6. AI eval pack

The judgement itself (Identity's take, Adaptation's shape, Audit's judge) is the model's. Its eval pack is the run: the person's words on the released build, the department's own answers, read from the record. Three evals stand today: the dermatologists goal (from scratch, the internet on the person's word), the Sankalp Asawa goal (a person's own facts), the Parasthi Hospital goal (a site from given facts). Scoring: the goal's outcome rows (structural: an ask of kind engine, an artifact with a URL after each name) plus the agent's reading as the person. Drift: a rerun after every release; a finding that recurs keeps its number.

## 7. CI gates

| Test class | Gate |
|---|---|
| `test_engine_runtime.py`, `test_website.js`, `test_website_dept.py`, `test_dept.py`, `test_org2.py` | block the release (the release lane runs them on the clone) |
| the beta smoke | block stable; never on the simulation's port while a run is live (finding 31) |
| the rerun | after stable, by the agent; its report closes or keeps each finding |

## 8. Anti-patterns for this work

- a test that asserts a keyword cue in the runtime (the founder's ruling: agents judge, code checks closed lists): the fake Model answers by step id, the code is asserted on what it does with the answer
- a test that passes on the old code (write it, watch it fail, then fix)
- one test for many findings: one finding, one test, one name in the TODO row
- a screen test that sleeps: `await sleep()` twice is the harness's tick, not a wait
- asserting a whole tell by regex: the lead by prefix, the rest by `assertIn`

## The mapping for this unit (findings 34-46)

| # | Kind | Test | Asserts |
|---|---|---|---|
| 34 | runtime | test_96 | with an engine ask pending, `next_due` says the line waits for the stamp; one chat line says so; after the stamp the line runs |
| 35 | runtime | test_97 | a born engine's run row's `what` reads its step's name while the make step runs |
| 40 | runtime | test_98 | `write_file` links a bare address; leaves an `href` alone |
| 41 | runtime | test_99 | Audit's judge prompt carries the filed artifact; with a web engine, the holes go to it, not to the person |
| 43 | runtime | test_100 | words said to Priority: the plan and live tells of that chain show in Priority's chat |
| 44 | runtime | test_101 | a nav link "Still to be confirmed" is no hole; a body sentence is |
| 45 | runtime | test_102 | the take names a rule: the ask is a rule ask; the stamp writes the rule; no Brief version |
| 38 | runtime | test_103 | a born engine's need step says no: no new version, the row says why, Plan runs |
| 46 | runtime | test_104 | the make prompt carries the previous result and the keep/add/dropped instruction |
| 36 | screen | W38 | a filed turn's chip reads "Open <artifact>" and targets that artifact; a live turn's reads "Open the live site" |
| 39 | screen | W39 | opening from Root's chat sets the child's tab to now, its row to Live site; a repaint keeps the preview |
| 42 | screen | W40 | Send in a function's chat keeps the function's tab and reloads its chat |

provenance: {author: claude, session: 17842ce0, date: 2026-09-29, inputs: [core:test-strategy, the suites as they stand (96 runtime tests, W1-W37), run 3's findings 34-46, the founder's rulings of 2026-09-29 on judgement in the runtime], review: none by a second model, confidence: high on the mapping, which names tests this unit writes; moderate on the shares}
