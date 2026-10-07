# PRD: J1 and J2 as published — close the gap between the shipped build and the department page

| Field | Value |
|---|---|
| Status | Built 2026-10-07; not committed, not released |
| Date | 2026-10-07 |
| Source of truth | https://sankalpasawa.github.io/asawa-site/native/system/department.html (sections `#j1`, `#j2`, rulings S-18, S-20, S-24, S-29) |
| Baseline | `origin/main` at `fb12276f` (J1 and J2 flows as first shipped) |
| Supersedes for build order | `issues/prd.md` (J1), `docs/superpowers/plans/2026-10-06-j2-prd.md` (J2). Both stay as detail references; where they differ from the page, the page wins. |
| Evidence | 34 live scenarios (90 checks) run 2026-10-07 on a local server; 5 live-model runs |

## 1. Why this exists

The first build passes its 25 unit tests and fails the page in three ways the tests cannot see.

| # | Finding | Evidence |
|---|---|---|
| 1 | With a real model, J1 creates no department. | 4 of 4 live requests failed at `setup.shape`: the model answered `template_ref {"id": "website", "version": "1"}`; the check accepts only `{"id": "department/website", "version": 1}`. The owner is told nothing. |
| 2 | J1's questions are code, not the AI the page asks for (S-24). | `_j1_clear` is a keyword list; the questions are a fixed list in `setup.json`; `setup.converse` is a code step. |
| 3 | J2 is a ledger of five events written at Start. It neither drives nor records the department's work. | A department planned, wrote, checked, published and was audited; the ledger held 5 events and the state read `ready, step 6` throughout. No bargain, no Root check, no done-when. |

## 2. The page, row by row, against the build

### J1 (seven steps, nine edges)

| Row | The page says | Shipped | This build |
|---|---|---|---|
| 1 Name, Found | Built | Works (8 parallel clicks, one Root) | Keep |
| 2 Sutra appears | Built, name to change | Screen says Root | S3: the screen says Sutra |
| 3 Sutra asks until clear | A model step with an instruction; no question in code | Keyword list and fixed questions | **S1: `setup.converse` becomes a model step; the keyword logic stays only as its offline draft** |
| 4 You answer | Answers are Request versions | Works; an answer is misrouted to a child when Root already has one | S1: an open question always receives the next words |
| 5 Sutra decides | Name, template, purpose; no stamp | Fails live (finding 1) | **S2: code derives route and template reference from the kind** |
| 6 Sutra builds | Built | Works | Keep |
| 7 Sutra tells | Department, engines, what happens first | Works; told twice in 2 of 13 runs | S3: one lock around the tell |
| J1.1, J1.2 | Keep asking; "just do it" decides with defaults and says which | Works offline | Carried into the model step's covering |
| J1.3 Name exists | Words handed to the existing department | Works | Keep |
| J1.4 No template | Organic | Works | Keep |
| J1.5 Two departments | First made; the second offered as a chip to click | Saved on the record, never shown | **S3: the tell carries the offer; the chat shows a chip** |
| J1.6 Ask rule | One ask, then waits | Works; a refusal leaves the Request open | S2: a refusal closes the Request |
| J1.7 No answer in 60 s | Said back as waiting | Works | Keep |
| J1.8 Model away | 30, 120, 600 s, then told | Works for a failed call; a CLI error reply is read as a bad answer | S2: an error reply counts as away |
| J1.9 Close mid-questions | Continues where you left | Works | Keep |

Rows B3 (a `required` flag per engine) and B4 (Adaptation's overlay at every birth) are marked *later* on the page and stay out.

### J2 (eight steps, eight edges)

| Step | The page says | Shipped in the runtime | Shipped in `j2_runtime` | This build |
|---|---|---|---|---|
| 1 Identity: good enough? | Asks until its standard is met; then the department starts | First thin words get one question (`identity_file`) | A code check; the question cannot be answered | **S4: Identity's question takes a typed answer, writes it to the identity and re-checks** |
| 2 Adaptation proposes | Workflows from the Library or its own | Organic only (`adapt.line`) | One event, no proposal on the board | **S5: every kind gets a proposal on the board: the Library line, or the shaped one** |
| 3 Priority: grant, refuse, counter | Bounded: four hops, fifteen minutes, its spend | For an idea's engine only; no counter | One event | **S5: Priority answers the line proposal; counter added** |
| 4 Identity closes a conflict | Then you, if it cannot | Bound's default is refuse; nothing goes up | None | **S5: a refusal or a bound goes to Identity; what it cannot settle is one ask to you** |
| 5 Root checks, registers | On the department's record, not the Library | `validate` exists; `born_template` writes the Library | Two events, no check | **S5: Root's check runs `validate`; the workflow is registered on the department record** |
| 6 Coordination orders; runs | Built | Built | Not recorded | **S6: slot, run, artifact events from the runtime** |
| 7 Audit reads | Built | Built | Not recorded | **S6: finding event** |
| 8 Next move, or done | Loop until done-when holds; Identity says so | Not built | None | **S6: done-when is read from Audit's finding; Identity declares the goal reached; Adaptation stops** |

| Edge | This build |
|---|---|
| J2.1 Not good enough | S4 |
| J2.2 Bound hit | S5: goes to Identity |
| J2.3 Identity cannot settle | S5: one ask |
| J2.4 Root refuses | S5: reasons back to Adaptation, nothing registered |
| J2.5 Over the envelope | Built; S6 records it |
| J2.6 Goes outside | Built; S6 records it |
| J2.7 Fails its check | Built (twice, then told); S6 records it |
| J2.8 Goal moves | Open on the page. Not built here. |

## 3. Decisions taken for this build

| # | Decision | Why |
|---|---|---|
| D1 | J2 starts by itself when J1 hands over. There is no Start button to press. | The page: "J1 ends there: what the department does with your words is its own life, J2." A manual start leaves the department running outside its own lifecycle, which is what was observed. |
| D2 | Work engines wait for step 5. A workflow that Root has not registered does not run. | Step order on the page: propose, grant, check, register, then run. |
| D3 | The J2 ledger is written by the runtime where the thing happens (a post on the board, a run row, a filed version), not by a second state machine. | One source; the ledger cannot drift from the work. |
| D4 | The functions talk on the department's one board, on the edges it already has. Identity alone speaks to the owner. | The page, step 3 and the lead paragraph. |
| D5 | Every AI step keeps a code draft for offline and for a failed model. | The runtime's existing box: code covering, AI inside, draft below. |
| D6 | `J2_FLOW_V1` defaults on, like `J1_FLOW_V1`; `0`, `false`, `off` turn it off and the department runs as it did before J2. | The shipped flag is never set by a launcher, so J2 is off for everyone. |
| D7 | Existing API paths (`/api/dept/{ref}/j2…`) stay; an answer route is added. | The screen already uses them. |

## 4. Slices, in build order

| Slice | What | Files | Proof |
|---|---|---|---|
| S1 | Converse as a model step; answers always reach an open question | `engine-templates/setup.json`, `engine_runtime.py` | Unit: a model that says ask / clear; routing with a child present. Live: 3 requests |
| S2 | Shape made safe; failure and refusal close the Request and tell the owner; error replies count as away | `engine_runtime.py`, `website_dept.py` | Unit: the exact answer the live model gave. Live: a department is born |
| S3 | One tell; the second department as a chip; the screen says Sutra | `engine_runtime.py`, `static/js/22-website.js`, `static/js/19-org2.js` | Unit + JS tests |
| S4 | J2 auto-start; Identity's question answered in words | `j2_runtime.py`, `j2_api.py`, `founding.py`, `engine_runtime.py` | Unit + live |
| S5 | Proposal, bargain with counter, Identity's close, Root's check and registration; engines held until registered | `engine_defs/website.json`, `engine_runtime.py`, `j2_runtime.py` | Unit per branch + live |
| S6 | Run, artifact, finding events; done-when; goal reached; Stop and Resume agree; ordered activity; one cycle under parallel starts | `engine_runtime.py`, `website_dept.py`, `j2_runtime.py`, `static/js/20-dept.js` | Unit + the 34 live scenarios re-run |

## 5. Acceptance

1. A live-model founding of "Build a website that teaches algebra to Class 8 students" births one website department and tells the owner once.
2. The same founding with a vague first line gets its questions from the model, one a turn, and resumes after a restart.
3. A request for two departments births one and shows the second as a chip.
4. A born department's ledger shows steps 1, 2, 3, 5, 6, 7 in order with no button pressed, and step 8 when done-when holds.
5. No work engine runs before `workflow.registered`.
6. Priority's refusal reaches Identity; an unsettled conflict is one ask to the owner; a Root refusal registers nothing.
7. Eight parallel starts give one cycle. Stop then Resume leaves J2 running.
8. The existing department suites still pass.

## 6. What was built, and what proves it (2026-10-07)

| Slice | Built | Proof |
|---|---|---|
| S1 | `setup.converse` is a model step; `setup.say` is its covering; an open question takes the next words even when a department exists or the answer starts with "yes" | `test_j1.py`: 3 new tests; live: the model asked 1 to 2 questions a founding, one a turn |
| S2 | `_shape_norm` derives route and template reference; a failed Setup and a refused preview close the Request and say so; a CLI error reply is the model being away | `test_j1.py`: the live model's exact answer now makes the department; live: 4 of 4 foundings born (0 of 4 before) |
| S3 | One lock around the birth tell; the second department as a chip (`data-wbsay`) | `test_j1.py` (8 threads, one tell), `test_website.js` W46 |
| S4 | The cycle starts at the hand-over; Identity's question takes words once (`/j2/answer`) | `test_j2.py`, `test_j2_api.py` |
| S5 | Proposal for every kind; Priority's grant, refusal and counter on the board; refusal and bound go to Identity; one conflict ask; Root's check and registration on `dept["workflows"]`; engines held until then | `test_j2.py`: 11 tests, one a branch |
| S6 | Slot, run, artifact, finding and `goal.reached` events from the runtime; Stop and Start agree; one cycle under 8 parallel starts; ordered activity; the J2 card in plain words | `test_j2.py`, `test_dept.js` |

Acceptance (section 5), run over HTTP on a local server: 13 of 13 offline; live model 7 of 7 (items 1 to 6; item 7 is not model-dependent).

### Decided differently from the page, and why

| Item | The page | Built | Why |
|---|---|---|---|
| The helper's shown name | "The screen will say Sutra" (S-20, B5) | Still **Root**, held in one constant (`WB_HELPER` in `22-website.js`) | The J1 contract of 2026-10-05 says "The UI name remains Root" and the shipped test W45 asserts "J1 does not alias Root as Sutra". That is a later decision than the page's; changing one word flips it. **Founder, 2026-10-07: "For now it should show as root."** |
| Root's check | Checks against Sutra's standards | The runtime's line check (`_root_check`) | The standards list is a placeholder on the page (J2.4). |
| Who runs Root's check | Root | Code in the department's process, recorded with actor Root | Root is another department; a cross-department round trip adds a hop and a failure mode for a check that is code today. |

### Found while building, and fixed

- A second organic department, offline, shaped a line with names the Library already had; its check refused it and the cycle sat at step 2 unsaid. The draft now takes free names, and a shaping that fails is tried again twice, then said.
- "yes, free" as an answer to Sutra's question was read as a stamp.

## 7. Not in this build

- J2.8 (the goal moves), marked open on the page.
- B3 and B4 (required engines, Adaptation's overlay at every birth), marked later.
- S-30 (verification templates per outcome kind) and the standards list for Root's check, both placeholders on the page; Root's check is the runtime's `validate`.
- Born templates still ship to the record home's Library for the organic kind until S-25 is ruled; registration on the department record is added beside it.
