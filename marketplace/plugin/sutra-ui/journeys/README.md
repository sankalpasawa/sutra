# journeys/ -- the user journeys as data

PRD amendment A3.6: a user journey is a template at the top level (L0). The base class is the interface's `DEFS['journey']`
(`layer_schema.py`); a journey file is a child that conforms to it. The files here say what a person goes through, step by
step and edge by edge, bind each row to the code and the tests that prove it, and keep what the site's journey page says.
What a row has earned is never written in a file: it is computed from the tests it lists.

"J2 view" is the prototype's department page in the app, and it is not a journey. A journey is data under this folder; the
J2 view neither reads nor shows it (the API below gives it to a screen as data only).

## What is in the folder

| Path | What it is |
|---|---|
| `J1.json` ... `J7.json` | one journey each (the content packages write them) |
| `functions/<function>.json` | `{"journeys": [...]}`: a function's own journeys, which are declared |
| `status/<id>.json` | one computed document per journey that is not declared; written by the runner, never by hand |
| `__init__.py` | `load()`, `rows()`, `row_key()`, `definitions_sha()`, `view()` |
| `status.py` | `resolve_code`, `resolve_test`, `row_state`, `journey_state`, `compute` |
| `site.py` | reads the saved copy of the site's own data file |
| `contract.py` | the twelve cases JC-1 to JC-12 |
| `walk.py` | `trace` and `follows`: did a run of the real flows follow the journey? |
| `../qa/journey_status.py` | the runner: `--static`, `--check [--no-run]`, `--write [id]` |

A file that does not parse, fits no definition or repeats an id refuses the whole load, naming the file, as a bad engine template
does (`the journey file J3.json is refused: ...`).

## A journey file

A journey has an `id` (J1, FI2 ...), a `title`, a `kind` (person, system or function), a `goal`, its `lanes`, its `steps` and its
`edges`. A **step** is a thing that happens on the path you want; an **edge** is a way it goes wrong, hung under the step it
branches from (`at`). Both carry the site's own words verbatim beside the author's: `site_says` and `site_code` for a step,
`site.text` for an edge, so that what the site claims is kept and can be compared. `{helper}` stands for the word Sutra on the
site and is said as the screen says it (Root, for now). `was` keeps the site's earlier version of a flow as history: it has no
state and no tests. `site_ids` lists every row the site lists. `declared: true` says a journey is a design that is not built:
nothing is computed for it.

Every row says one of two things. Either it is **built**: it names the code it runs through (`code`), the acts, steps and events it
is (`binds`) and the tests that prove it (`tests`). Or it is **wanted**: it has no code, and a `backlog` entry that some journey
defines names its smallest behaviour. A built edge also says in `code_does` what the code does, in a sentence the listed tests
assert. A row the owner marks `disposition: drop` stays in the file (a row leaves only by that mark) and counts for nothing.
`same_as` makes a row the same row as one of another journey and takes its state.

### The grammar of `code` and `tests`

- `code` is a list of names. A bare name (`setup_say`, `wbFoundGo`) is found if any code root defines it: the Python files of the
  plugin folder except `test_*.py`, the files under `layers/`, and the scripts of `static/js`. `module.name` (`website_dept.create`)
  is found if a file whose stem is `module` defines `name`; use it when a bare name is ambiguous. A row stays valid when a package
  moves a body into its layer module, because names are found, not addressed.
- `tests` is a list of: `file.py::test`, `file.py::Class::test` (a function at the top of a file, or a method of a class at its
  top), or `js:file.js#W45` (every test of the node file whose name begins `W45:` or `W45 ` must pass, and at least one must
  exist). A parametrised pytest test is named without its bracket and all its cases must pass.
- `binds` are of six kinds: `act` (sender, act, word, receiver: a row of the interface's sends table), `step` (an engine step id),
  `event` (a ledger action), `api` (a method and a route of the app), `ui` (a script symbol) and `person` (the owner's own act).
  `optional: true` marks a bind on a branch the walk does not take.

## How a row's state is computed, and why it cannot be edited

A state comes from two inputs: the row as defined and the result of the last run of the tests it lists (`passed`, `failed` or
`missing`). `journeys/status.py::row_state` is a pure function of them:

| State | Rule |
|---|---|
| `dropped` | the row's `disposition` is `drop` |
| (another row's) | the row has `same_as`: it takes that row's state |
| `wanted` | no code, a backlog entry, no tests |
| `fault` | no code and no backlog entry, or a wanted row lists tests |
| `unproven` | code and no tests |
| `failing` | a listed test failed, or the run did not find it |
| `partly` | every listed test passed, and the row names a backlog entry for the part not built |
| `proven` | every listed test passed, and there is no backlog entry |
| `unknown` | (the read model only) a listed test has no result: the status file is stale |

A journey is `declared`; else `failing` if any row is; else `fault` if any row is a fault or unproven; else `partly` if any row is
partly or wanted; else `proven`. The site's words follow: proven is "built", partly is "partly built", wanted is "wanted".
**Drift** lists the rows where the site's word and the state disagree (the site says wanted and the row is proven). It is a report
and never a fault: it is the evidence for re-marking the site.

A state cannot be edited because it is not in the file. It changes only when a test a row lists changes its result, or when a
package changes the row. The status document of a journey carries the hash of the journey file it was computed for; the read model
and the API mark a journey `stale` when that hash is not the file's now, and then read `unknown` for every row that lists tests.
A review rule goes with it: each test a row lists must assert the effect the row's `code_does` states. A test that only runs
through the path is not listed.

### One row, as data

```json
{
  "id": "J4.1",
  "at": "2",
  "short": "The rule is already there",
  "trigger": "The rule is already on the record.",
  "site": {"status": "built", "text": "Built: said back, not added twice."},
  "code_does": "identity_file says the department already has the rule and files nothing.",
  "outcome": {"kind": "tell", "voice": "Identity", "golden": "the department already has this rule"},
  "binds": [{"kind": "act", "src": "Identity", "act": "inform", "word": "request", "dst": "Owner"}],
  "code": ["_rule_answered", "identity_file"],
  "tests": ["test_layer_journey_j4.py::TestJ4Edges::test_j4_1_a_rule_the_department_already_has_is_said_back_and_not_added"]
}
```

`J4.1` hangs under step 2 of J4. Its sentence is what the owner is told, and the test it lists asserts that sentence. The edge is
proven while that test passes.

## Add a row

1. Write the row in the journey file, with the site's words if the site lists it (`python3 -I` the saved site file, below, to see
   what it says). Give an edge its `at`.
2. Name the `code` that does it and the `binds` that trace it, or, if it is not built, a `backlog` entry that says its smallest
   behaviour and no tests.
3. Write or name the test that asserts what the row says, and list it.
4. Run `python qa/journey_status.py --static`: the cases name the journey and the row that is wrong.
5. Run `python qa/journey_status.py --write <id>`, and commit the journey and its status file together.

## The runner

```
python qa/journey_status.py --static            # the cases that need no run (JC-1 to JC-7, JC-9 to JC-12); seconds
python qa/journey_status.py --check             # the gate's lane: static, then the run, then the status files
python qa/journey_status.py --check --no-run    # static, and each status file's staleness by hash; no test is run
python qa/journey_status.py --write [id]        # the same as --check, then writes the status file of one journey (or all)
```

`--check` exits 1 on a static fault, a failing row, an unproven or fault row in a journey that is not declared, and a status file
that is missing, stale (its hash is not its journey's), different from what the tests give now, or of no journey. It prints one line
per problem and ends with `journeys: <n> rows, <p> proven, <w> wanted, <f> faults`.

The run lists the tests of the journeys that are not declared and runs each Python file once (`pytest -q -p no:cacheprovider
--junitxml ...`, on a registry of its own) and each node file once. A listed test that no result mentions is missing, and a missing
test is a failing row. The documents are deterministic: sorted keys, indent 1, a final newline, no clock.

### The gate

`qa/walks/suites.sh` has one line for the runner after the `test_layer_*` loop. Its cost: with the 21 journeys of the A3 specs (126
listed tests, about 40 of them in `test_engine_runtime.py`) one full run took 167 seconds on a machine busy with other builds, and
the static cases and the staleness check take a few seconds. The budget is three minutes added to the gate on the integrator's
machine. If the lane goes over it, change the line to `--check --no-run` and run the full `--check` before each merge that touches
`journeys/`.

### Who regenerates a status file

Whoever changes a journey file, or renames a test a journey lists, runs `qa/journey_status.py --write <id>` and commits
`journeys/status/<id>.json` with the change. Each journey has a status file of its own so that two packages never conflict on one. A conflict in a status file
is resolved by regenerating it, never by hand.

## The cases

| Id | What it holds |
|---|---|
| JC-1 | shape: every file fits the interface; a step is in a lane the journey lists |
| JC-2 | ids: unique, and an edge's or sub-journey's id begins with its journey's (`was` is a namespace of its own) |
| JC-3 | places: `inside`, `children`, `child`, `serves`, `sub` and `at` resolve; a function journey is bound, a user journey is not |
| JC-4 | binds: every act, step, event, screen symbol and route exists; a step of a journey that is not declared binds something |
| JC-5 | code: every name in `code` is defined |
| JC-6 | tests: every test listed exists |
| JC-7 | wanted or proven: code, tests and (for an edge) a sentence on what the code does; or no code, a backlog entry and no tests |
| JC-8 | the run: the state of each row from the results, and each status file equal to it (the runner, not a static case) |
| JC-9 | fidelity: against the saved copy of the site's file, every row is there, under the same step, in the site's words |
| JC-10 | golden leads: what an edge says to the owner is in the code that says it, and in a test file the journey lists |
| JC-11 | screen words: a golden lead and a reword hold none of the screen's banned words |
| JC-12 | function journeys: bound to one of the five functions; `same_as` resolves to a row that is not itself a `same_as`; declared, or every row proven |

## The saved site file

`test_fixtures/journeys/site-journeys-2.4.json` is the site's own data file (`system/journeys.json`, version 2.4 of 2026-10-01),
saved whole. JC-9 holds a journey to it and never to the journey data: a row deleted from a journey and from its `site_ids` is
still found, because the site still lists it. Read it only with `python3 -I`, and copy it, never edit it. When the owner publishes
version 2.5, the new file replaces the saved copy in the same commit as the journey data that follows it, and the drift list is the
to-do.

## The API

`GET /api/native/journeys` and `GET /api/native/journeys/{id}` (in `website_api.py`, before the routes that begin with `/{ref}`)
give the list and one journey as data for a screen: the definition without its code and tests, and for each row its state, the
tests that proved it by name, the site's word and the drift. A read writes nothing. A journey that is not one is
404 `UNKNOWN_JOURNEY`. There is no screen for them and none in `static/`.
