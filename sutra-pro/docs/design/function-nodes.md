# Function nodes: the one design
_Status: Settled · Date: 2026-11-04 · Machine record (patch lists, work packages, diagram labels): `settlements/S4-fnodes.json` and its twin `S4-fnodes.md` · Inputs: `function-nodes-spec.json` (final), S1-contracts-09/10, S2-models-05 to 10, S3-web-04/05/13, the five sections, J2 at `ce2631fb`, plugin `bin/sutra-atom`._

**Precedence.** The final spec wins on concepts and on what the diagram promises. The settlements win on structure
(packages, processes, tables, events) unless the structure cannot deliver the promise. This file wins over both where
section 11 names a superseded id; the patchers apply the S4 text. J2 stays byte-identical (prompt goldens): j2.py
changes only by the P8 hooks, no hook is added, `system_addendum` stays empty. FN-n = a spec decision, S4-n = a
settlement of batch S4-fnodes, `j2.py:n` = a line of J2 at `ce2631fb`. J2 stage letters: a Identity intake, b Adaptation
proposes, c Priority prices, d Identity resolves, e code validator, f Coordination schedules and Priority checks the run
envelope, g Audit, h Identity: is it workable.

## 1. Words (the owner's four, then the plugin's two)
| Word | On the card line | Plugin | In code |
|---|---|---|---|
| goal | GOAL: the node's standing goal, its J2 role sentence | per-atom GOAL, refused if banal | `FunctionNode.goal` (standing); `Atom.goal` (one turn, observable) |
| task | TASK: what the node does at its stage, J2's ROLE line | not an atom field | `FunctionNode.task` is a string; the live unit is `NodeDetail.task` and `AtomOut.task_id`; no `Task` class |
| context | CONTEXT: what a call is given (J2 STATE + CHAT) | `context_refs` | `FunctionNode.context` = names of the slice; `Atom.context` = the turn's references |
| work atom | WORK ATOM YIELDS: what one atom produces | GOAL + CONSTRAINTS + CONTEXT + WORK, verified | `Atom` (family `atom`, schema `work-atom/0.3`), one per function turn |
| verify | VERIFY: the checks code runs, never the node | the teeth | `Atom.verify.checks[]`, names from the registry (section 4) |
| constraints | CONSTRAINTS: what the node may not do | text, check null | `FunctionSpec.may_not` copied to `Atom.constraints` |

`step` is ambiguous (loop step J2.a-h, step node = a builder in the graph); this design says turn (one go of one
function, `TurnInfo`), and the strip caption says `1 turn = 1 atom`.

## 2. Names and record shapes
**2.1 Code names (S4-1).** The library names stand: `FunctionNode` with `IdentityNode`, `AdaptationNode`,
`PriorityNode`, `CoordinationNode`, `AuditNode`; `Atom` (+ `AtomDraft`, `Transition`, `LedgerRow`, `Card`);
`AtomView` (payload `atom_view`, J2 `atom/1`); `FunctionSpec(s)`. The spec's `AgentNode`, `WorkAtom`, `BuilderAtom` are
not code names. Builders keep J2's atom dicts (validated by `gate_record`, shown through `AtomView`): no second
stored atom model.

**2.2 FunctionNode (S4-14).** Body of a `graph_nodes` row; the wire in section 8 is its projection.
- Node base: `id` `<dept>.<kind>` · `label` (the function name) · `department_id` · `state` (idle, running, waiting,
  waiting_on_you, fault) · `detail` S(0,300) · `version` · `chat_session_id` · `edge_ids` · `ts_created`, `ts_updated`.
- FunctionNode: `kind` · `goal` S(1,600) · `task` S(1,200) · `context` [S(1,200)]<=40 · `open_atom` AtomId? ·
  `atom_count` int>=0 · `wait_on` null|`you`|function key|builder id · `stats` {calls, seconds, tokens{input,output}} ·
  `spec_version` int>=1.
- `goal`, `task`, `context` come from `FunctionSpec` (goal, role, reads) when the node is made and are refreshed when
  `spec_version` rises; no event writes them. `state`, `detail`, `wait_on`, `stats` come from the node event.
- Not stored: `constraints` (= `may_not`) and `hands_to` (= `HANDOFFS`) are read at request time; `stats.atoms_*` are
  counted from `atoms`. Dropped: `last_seen` (J2's map folds it into `detail`), the `Task` class, the atoms list, the
  provider-to-session map (the connector's `session.json` keeps provider ids). Personas are UI constants from J2.
- The spec's child extras (Identity `blind_to` and audiences, Adaptation `memory` and `planning`, Priority `rate_card` and bargain
  bounds, Coordination `write_lock`, Audit `rubric`) are not node fields: they are J2 behaviour held by `j2.py` and
  `EngineSettings`, and by `FunctionSpec.reads` and `may_not`. The record is one shape for all five functions.

**2.3 What a function atom puts in each field.**
- `node_id` `<dept>.<fn>` · `department_id` · `task_id` (S2-6) · `session_id` = sid · `goal` from the template (section 3).
- `constraints`: the first 20 of `may_not`, `check` null · `context`: the `TurnInfo.context` pairs as `kind: summary`
  (<=200 characters, <=40).
- `work`: `dispatch_kind` llm|bash|manual, `agent` the function (or `owner`), `steps` = `step_label`, `how_kind` AI for llm else code.
- `outputs`: [`FunctionSpec.yields`], the WORK ATOM YIELDS line · `touches` [] · `model` from the first call · `effort` stays null.
- `verify.checks[]`: {`template` = registry name, `args`, `text` = the check's sentence, `relevance` = that sentence}.
- New in L4 (S4-8, S4-3): `Atom.abandon_code` (`verify_failed|run_ended|replaced|manual`, only when abandoned) and
  `Seen(work, model, note)` given to `close_atom` and `abandon_atom`: when `work` differs from the declared kind the
  stored `work.dispatch_kind` is replaced and `notes` gets `declared bash, did llm`.

**2.4 Ids.** Function atom `a-<sid10>-<nn>` (S2-10). Builder atom `<run_id>:W-n.aK` on the server. Overhead key
`overhead_atom_id(owner_ref) = function_atom_id(atom_sid(owner_ref, "overhead"), 1)` with `owner_ref` = run id or
`req-<id>`; it has no `atoms` row (helper in L1, `types.py`).

## 3. Templates: what each node declares (data in `function_specs.json`, WP L10)
Declare turns `FunctionSpec` + `TurnInfo` into an `AtomDraft` before the work. Declare adds the floor checks by work
kind: llm gets `turn-posted`, and `reply-valid` when the `TaskKind` names a reply family and kind; bash gets `turn-posted`;
manual gets none. A template lists only its named checks.
A `change` turn is Adaptation's. Goal text takes `{function} {kind} {step_label} {task}` and is never a banal word.

| Node · kind · J2 | Goal | Work | Named checks |
|---|---|---|---|
| Identity · intake · a | the brief becomes a charter that passes the stamp, or the owner is asked what is missing | llm | charter-stamp, audience-split |
| Identity · audit · h | the goal is declared reached only if code finds the site workable | llm | workable, audience-split |
| Identity · requester_answered, approval, ruling_budget | the owner's answer is read and passed on | llm | audience-split |
| Identity · resolve, stage_decision, limit, send_confirm, question | generic | llm | none |
| Identity · the owner's question | the owner's answer to the first question is recorded | manual | answer-recorded |
| Adaptation · propose, respond · b | workflows are proposed whose work atoms follow the atom rules | llm | atom-rules; judge-gate on propose |
| Priority · price, ruling · c | the proposal is priced GRANT, COUNTER or REFUSE with a limit, within the budget left | llm | price-kept, within-budget |
| Priority · envelope · f | the run envelope of the workflow is checked, it runs only within its limits | bash (llm if asked) | within-budget |
| Coordination · schedule · f | registered workflows get an order and named holds | llm (bash if none is registered or held) | order-registered |
| Audit · audit · g | every done-when item has a finding with evidence | llm | finding-per-item, pass-needs-proof, code-measure-wins |
| any · dispute, atom_failed, change | The {function} answers the hand-off {kind} with a reply that follows its rules | llm | none |

Kinds are predicted from the file or the template, never from a reply: envelope is bash; schedule is bash iff
`workflows.json` at turn start has no registered or held workflow; `Seen.work` corrects a wrong guess.

## 4. The verify registry (S4-2; WP E8: `fnodes/registry.py`, `fnodes/evidence.py`)
One pure function per name: `fn(ev: Evidence, args: tuple[str, ...]) -> Outcome`, `Outcome(ok, evidence<=2000,
changed=(), na=False, waived=False)`. `Evidence` is a frozen bundle built by the layer from hook data:
`turn` (`TurnInfo`), `outcome` (`TurnOutcome`, turn phase only), `reply`, `replies` and `call` (the node's replies, `CallInfo`),
`posted` (chat messages with their meta, in order), `records` (latest data of goal, workflows, audits, realization,
conflicts as saved this turn, else read at turn start), `before` (the same at turn start), `owners` (atom id -> owner node,
from the layer's own opens and J2's builder ids), `prompt`. `args`: `reply-valid` [family, kind], `answer-recorded`
[question message id], the others none. A check has no clock, no network, no write; files only through `records` and `before`. Missing evidence is a fail
(`missing: goal.json not saved this turn`); `na` only when a property of the reply says the check does not apply.
- **Phases.** reply: judged on each node reply, a failure is a live try. turn: judged once at turn end on the whole
  turn; what J2 retried inside the turn is narrated in the evidence. event: judged when its event arrives.
- **Kinds.** gate: J2 retries a failing reply. override: J2's code corrects the reply, the check proves the outcome.
- **Closing words.** The last evidence of a closed atom may start `RECOVERED:` (J2 repaired, templated or dropped) or
  `WAIVED:` (J2 accepted a concern on record).

**`reply-valid`** (floor) · every function, every kind with a call · reply phase, gate
- reads: the reply; args `[family, kind]` (`a|b` allowed). Passes when `ReplyParser` accepts it as that family and kind;
  na when the turn made no call by this function (it is then a bash atom).
- evidence: `ok` / the first 3 violations. Tries: each reply is a try (cap 3). J2's tolerance is unchanged, so a reply
  J2 accepts and the closed model refuses ends `verify_failed` (visible, harmless to the run).

**`turn-posted`** (floor) · every function, every kind · turn phase, gate
- reads: `posted`, saved records, `outcome`. Passes when the turn posted at least one message or saved a record and
  every message of this function has `next` in `HANDOFFS` (`user` = `requester`) or is a code hand-off (`auto`, `Hand-off by code`).
- evidence: `posted 1 message to Priority` / `no message, no record`, `next=audit is no route of priority`. Tries 1; no recovery.

**`charter-stamp`** · Identity · intake · J2.a · turn phase, gate
- reads: `goal.json` saved this turn, `reply.enough`, the system posts. Passes when `enough` is false (na: the owner
  is asked), or the charter has a statement, >= 3 done_when items and none matches `NOT_CHECKABLE` outside quotes (`j2.py:4172`).
- evidence: `statement present, 7 done-when items` / J2's `why` text verbatim.
- tries and recovery: 1 per turn. J2 re-asks in the next turn (hand-off attempt 2, `:4147`), which is a new atom. A
  second failure ends in `Charter accepted after two attempts` (`:4151`): the atom closes `WAIVED: <why>`.

**`workable`** · Identity · audit · J2.h · turn phase, override
- reads: the last non-recheck record of `audits.json`, `outcome.next` and `result`, `reply.done`.
- passes when it is not true that the turn ended the goal (`next` null, not paused) while J2's own `workable(audit)`
  (`j2.py:2470`) lists problems.
- evidence: `workable (code): yes, goal reached` / `not workable: 2 problems, back to J2.b` (`done=true overridden`); fail `ended with 2 problems open`.
- tries and recovery: 1. Code wins (`:4837`): back to J2.b, or `_identity_limit` asks the owner.

**`audience-split`** · Identity · intake, audit, requester_answered, approval, ruling_budget (the calls whose format has `to_requester`) · reply + turn, gate
- reads: the reply; the posted `to_user` and agent texts. na when the reply has no `to_requester` or `enough` is false (a question).
  Passes when `AGENT_CONTENT` is absent from `to_requester`
  and `USER_CONTENT` from `to_agents` (`j2.py:1523`); at turn end the posted texts obey the same.
- evidence: `to_requester is plain` / J2's `bad` strings. Tries 2 (J2 regenerates once, `:3188`); then the bad part
  becomes the default text and the atom closes `RECOVERED: template`.

**`atom-rules`** · Adaptation · propose, respond · J2.b (the rules of J2.e) · turn phase, gate
- reads: the reply's `workflows[]` and the `Validator rejected '<name>': <reason>` posts (`:6617`) after each reply.
  Passes when the last reply drew no rejection. Posts whose meta `rejected` is `plan` are J2's necessary-conditions check, not
  atom rules, and are ignored (seen in the mock Brew Lab run, message 7).
- evidence: `3 workflows, atoms complete` / `rejected: Build menu (missing completion_check)`. Tries 2 (reply and one
  retry, `:5962`); then J2 drops the incomplete workflows: `RECOVERED: dropped <names>`.

**`judge-gate`** · Adaptation · propose · J2.b (first website plan or full re-plan) · turn phase, gate
- reads: `realization.json` saved this turn. na unless saved this turn. Passes when `plan_confidence >= 0.80`
  (`j2_realization.THRESHOLD`).
- evidence: `plan 0.86 after 2 revision rounds (0.62, 0.71, 0.86)` / `plan 0.74 < 0.80; not ready: W-a`. Tries 1; the
  judge's rounds (<= 3) are evidence, and the judge's and planner's calls are charged to this atom (FN-12, FN-13); the check
  reads a file, so it needs no time budget. Below the gate J2 does not fund the workflows: `WAIVED:` plus that text.

**`price-kept`** · Priority · price, ruling · J2.c · turn phase, override
- reads: the last reply (`decision`, `workflows`) and the posts `carried no price` (`:6558`) and `has no cost or envelope` (`:6394`).
- passes when the decision is not GRANT, or every granted workflow has a price and a money limit (its own, or the
  one code kept from the table, `_kept_price` `:6534`). A GRANT with no `workflows` grants the table, whose prices are code's: it passes.
- evidence: `GRANT priced: Build menu 12` / `price kept for X (12)`; fail `no price for X after the second ask`.
  Tries 2 (J2 asks once more); override: code keeps the table price.

**`within-budget`** · Priority · price, ruling (J2.c) and envelope (J2.f) · turn phase, override
- reads: the reply, the call's ledger input (`N left`), the posted priority message. Price: `granted_total` <= left,
  or the posted decision is REFUSE (`:6404`). Envelope: an `allowed` post only if spent <= budget.
- evidence: `GRANT 40 of 80 left` / `GRANT 120 > 80 left, posted REFUSE`; fail `posted GRANT`. Tries 1; code turns the GRANT into REFUSE.

**`order-registered`** · Coordination · schedule · J2.f · turn phase, override
- reads: `before['workflows.json']` (registered and held ids), the reply's `order` and `holds`, the posted `schedule`.
- passes when every scheduled id was registered at turn start, none repeats, and every registered id not held appears.
- evidence: `schedule W-1 > W-2; W-3 held` / `dropped W-9 (not registered); appended W-4`. Tries 1; code filters and appends (`:6854`).

**`finding-per-item`** · Audit · audit · J2.g · turn phase, override
- reads: the last audit record, `goal.json` `done_when`, `owners`. Passes when there is one result per done-when item, items 1..n once
  each, and no row names (`atom`) an atom whose owner is this department's Audit (FN-10; J2's rows carry no `atom`, so this never fires today).
- evidence: `7 items, 7 findings` / `item 3 had no finding: recorded BLOCKED_BY_EVIDENCE` (`F-missing-n`). Tries 1; code adds the row (`:8864`).

**`pass-needs-proof`** · Audit · audit · J2.g · turn phase, override
- reads: the same record. Passes when no result or rubric row with `pass` true has an empty note.
- evidence: `5 PASS rows, each with evidence` / `F-3 PASS without evidence: BLOCKED_BY_EVIDENCE` (`:8892`). Tries 1; code downgrades.

**`code-measure-wins`** · Audit · audit · J2.g · turn phase, override
- reads: the audit's `mechanical` and rubric rows. Passes when every id in `j2_check.design_problems(mechanical)` is
  NEEDS_REVISION with `Measured by code:` (`:9194`); na when `mechanical` is absent (a document).
- evidence: `R-2, R-6 measured, recorded NEEDS_REVISION` / `no render measurements`. Tries 1; code overrides.

**`answer-recorded`** · Identity · manual atom, every pause · event phase, gate
- reads: the question message id. Passes when a `user` message with a higher id is posted.
- evidence: `answer recorded as message 14: "Keep them in scope"`. Tries 1; no recovery. A run end abandons it with `run ended: <status>`.

Not observable, and what is recorded instead. J2's `_event` list (it reaches `report.json` only at run end) and `_atom_problems`
(it needs the run's state). The checks read what J2 posts or saves beside them: the `Validator rejected` posts, the two Priority
price notes, the `Charter accepted after two attempts` note, the saved records, and for `audience-split` the reply and the posted
texts. The card texts need no change.

Rules. The library `CheckTemplate` lists these 14 names (S4-2). Parity tests tie `charter-stamp`, `workable`,
`audience-split`, `code-measure-wins` and `judge-gate` to J2's own functions; the text-driven checks (`atom-rules`,
`price-kept`, `within-budget` envelope, the charter note) pin J2's strings in a golden. The five VERIFY lines of the cards are true as drawn.

## 5. Lifecycle (S4-3, S4-4, S4-5)
**5.1 Grain.** One atom per function turn (`turn_started` .. `turn_finished`). J2's re-asks are tries of the same atom.
Helper calls (planner, judge, summariser, reviewer, template spec) are charged to the open atom; they are not atoms.
Builders, the code validator and the confidence judge open no function atom. A turn that ends in a pause adds one
manual atom for the question. The cost lines of the diagram stay true: cost per atom, one ledger row per call, filed by atom.

**5.2 Hook by hook** (`FunctionNodeHooks`, a subclass of `EventHooks`; these hooks only; every body is wrapped, an
error becomes a `layer.error` trace line and never reaches J2).
1. `run_started`: bind the run overhead key (`llm.bind_atom`).
2. `turn_started(t)`, the five names only: abandon a stale open atom of the node (`replaced`); declare; `open_atom`;
   emit the `atom` event and its card. Refused: no atom this turn, the turn goes on, the overhead key stays bound.
   Opened: `bind_atom(atom.id)`.
3. `call_finished(c)`, own function and purpose agent_turn: run the reply-phase checks on `c.reply`; the first reply
   stamps `model`. A failure is `close_atom` with the results: attempt + 1, card VERIFY FAILED, event outcome
   `verify_failed`, the atom stays open; turn-phase checks answer `deferred: judged when the turn ends` (exit 0) in that try.
4. `message_posted`, `record_saved`: buffered into `posted` and `records`. A `user` message while a manual atom is
   open runs `answer-recorded` and closes it.
5. `turn_finished(t, o)`: run the turn-phase checks. All ok or na: `close_atom` (with `RECOVERED:` or `WAIVED:` when
   it applies), ledger row, card CLOSED. Otherwise `abandon_atom(code verify_failed, "verify failed: <check>:
   <evidence>")`. Then, if `o.result` is paused, open the manual atom (goal: the owner's answer to the question is
   recorded; context `question`, `pause`). Rebind the run overhead key.
6. `run_status` waiting and not paused, `run_error`, SIGTERM: abandon every open atom, `run ended: <status>` (`run_ended`);
   the server does the same for a crashed run (S1-10).
Attempts: the library caps close runs at 3. Two failed replies leave one run for the final close; a third failing
reply uses the last run and the atom is abandoned at once.

**5.3 Refuse, abandon, recover (S4-5).**
- `open_atom` refuses for the plugin's reasons: another atom open, goal missing or banal, no or unknown check, vacuous
  check, empty relevance, target outside touches, `supersedes` not abandoned.
- A refused atom is stored (state refused, attempt 0), ledgered (status refused, reason = the refusal message) and
  carded (one line, ATOM REFUSED). Production templates never refuse: a refusal is a template bug made visible.
- Abandon needs a reason, runs no check, is made only by the layer or the server (FN-17), and frees the node.
- Recover means J2's own recovery as in section 4. An unrecovered failure is `verify_failed`: cards VERIFY FAILED, then ABANDONED.

**5.4 Mode (S4-4).** `SUTRA_NODES=on|off|enforce`: `on` (default) observes; `off` selects `EventHooks`; `enforce` is
reserved and the factory raises ValueError.
- Hard means: an atom closes only through passing checks; no flag and no caller can skip a card or a ledger row;
  the closed reply models and `HANDOFFS` are the oracle of `reply-valid` and `turn-posted`.
- J2 itself enforces replies and routes (re-ask, repair, `_pick`) and keeps doing so. The layer changes no prompt,
  reply, route or outcome. Changes to J2 behaviour listed: none.
- Write scope: at `message_posted` and `record_saved`, a message by a function with no open atom, or a record outside
  `FunctionSpec.writes`, writes one `layer.touches_miss` trace line and blocks nothing. It becomes hard when the golden runs show none.

**5.5 Worked example: Identity, J2.a, a charter with two done-when items.**
1. `turn_started`: atom `a-3f9a1c2b7d-01` opens (goal: the brief becomes a charter that passes the stamp, or the owner is asked
   what is missing; checks reply-valid, turn-posted, charter-stamp, audience-split). Event outcome `opened`, card WORK ATOM OPEN.
2. `call_finished`: the reply has `enough` true and a charter. `reply-valid` and `audience-split` pass: no transition.
3. J2 saves `goal.json` and posts `Charter rejected: fewer than 3 'done when' criteria.`, then hands the turn to Identity again.
4. `turn_finished`: `charter-stamp` fails with that text. `close_atom` fails (attempt 1, card VERIFY FAILED, outcome
   `verify_failed`), then `abandon_atom(code verify_failed)` (card WORK ATOM ABANDONED). Ledger row `verify_failed`; display verify_failed.
5. The next turn opens `a-3f9a1c2b7d-02`; its charter passes: card WORK ATOM CLOSED, ledger row `closed`, display closed.
   Had it failed too, J2 posts `Charter accepted after two attempts` and the atom closes with `WAIVED: <why>`.

## 6. Events, statuses, tables, cost
**6.1 Events.** Every transition is one `atom` line in `events.jsonl` (S1-9, S2-7): `node`, `atom{id, schema, goal,
work_kind, verify_template, status, attempt, closed_by, reason, body, ts_open, ts_closed}`, `outcome`, `card`, `ledger`.
`outcome` is opened, verify_failed (a failed try, the atom stays open), closed, refused or abandoned. `body` is the
library `Atom` JSON and carries `abandon_code`. Node events carry no goal; their optional `task` and `context` are
trace-only and the Projector ignores them (S3-web-04). The Projector gates the body, accepts forward moves only,
upserts `atoms`, appends the ledger row once, posts the card to the node's own session (`src_ref
<run>#atom:<id>:<outcome>:<attempt>`), updates `open_atom` and `atom_count` in the same transaction, emits `atom.updated`.

**6.2 One status mapping** (library `atom_display_state(atom)`; used by the card, the Atom log, the chip and `AtomOut.state`):

| Stored (`state`, `abandon_code`) | Display word | Plugin card | Pill text | Log row | Chip count |
|---|---|---|---|---|---|
| open, attempt 0 | open | WORK ATOM OPEN | in progress | none | open |
| open, attempt >= 1 (J2 retries) | open | VERIFY FAILED, once per failed try | in progress, attempt n | none | open |
| closed (evidence may start RECOVERED or WAIVED) | closed | WORK ATOM CLOSED | goal reached, and checked (+ concern on record) | closed | closed |
| abandoned, code verify_failed | verify_failed | VERIFY FAILED, then WORK ATOM ABANDONED | the check did not pass, so nothing is marked done | verify_failed | failed |
| abandoned, any other code | abandoned | WORK ATOM ABANDONED | stopped on purpose, reason kept | abandoned | total only |
| refused | refused | ATOM REFUSED | not started: the refusal message | refused | total only |

`atom/1` rows keep J2's four words (open, closed, verify_failed, abandoned), which are the same display words. `refused`
is a wire word (supersedes S3-web-13(d)).

**6.3 Tables** (ORCH-1 DDL).
- `atoms`: S2-7's per-schema `state` check, plus `display TEXT NOT NULL CHECK (display IN
  ('open','verify_failed','closed','refused','abandoned'))` computed by `AtomStore.upsert` from the Checked body, and index
  `atoms_node_display(node_id, display)`.
- `atom_ledger` is the **Atom log**: `seq INTEGER PRIMARY KEY AUTOINCREMENT, atom_id TEXT NOT NULL UNIQUE, node_id TEXT
  NOT NULL, status TEXT NOT NULL CHECK (status IN ('closed','verify_failed','abandoned','refused')), body TEXT NOT NULL
  (the LedgerRow), ts INTEGER NOT NULL`; triggers abort UPDATE and DELETE; written only by `AtomStore.append_ledger` in
  the Projector transaction. Function atoms bring their row in the event; for `atom/1` the Projector appends the row the
  first time a view is terminal. Read: `GET /api/atoms/log?node_id=&after=&limit=`.
- `usage_ledger` gains `step` and `atom_id`, index `usage_atom(atom_id)` (S1-5). Cards are `chat_messages` rows of
  kind card in the function node's own session (S2-7).

**6.4 Cost, one rule (S4-7).** Every model call is charged to exactly one atom id.
1. A call inside an open function turn, helper calls included: that atom (`llm.bind_atom`).
2. A builder call: J2's `tag.atom`, stored as `<run_id>:W-n.aK`; an explicit tag wins over the binding.
3. Anything else: the overhead key. The run's for engine calls outside a turn (end-of-run review, template spec between
   turns); the request's for the chat agent (`context.atom_id` -> `CallTag.atom`).
`usage_ledger.atom_id` is never NULL for a provider row; stub rows carry it too. Tested: no NULL; sums per atom equal the
ledger total; the total with stub excluded is the provider bill. `AtomOut.usage` sums by `atom_id`.

## 7. Chats and voices (S4-6, S4-12, S4-13)
One session per graph node (S2-11 stands), so draw.io steps 5 and 7 are true for every node: `cs_org` (the root,
writable), department (writable, Identity's voice), division (a lens), function (read-only working log, five per
department), step (read-only).
- **Division = lens.** Its session keeps no conversation of its own, only notes (merged, took in). Its transcript is the
  department session filtered to tasks scoped to the division, plus the notes. A line written there goes to the
  department's Identity with `scope_node_id`. A division has no function nodes.
- **Identity.** The Identity chip and the department node open the department session, the owner's Identity chat.
  Identity's own function session is its working log (its atom cards); the drawer lists the same atoms.
- **One rule for voices.** The owner reads prose from one kind of author, an Identity, verbatim. Everything else is a
  record written by code and labelled Sutra: cards, template lines, errors, status reports. The chat agent's model
  output is structure only (decision, change, assignments); none of its sentences is shown. Org-level messages with no
  department (status, smalltalk, clarify, no fit) are answered by code; there is no root Identity (the root is not a department).
- **Org chat** `cs_org`: owner lines; per request the template line (`I set up a {name} team and gave it your
  request.`) and cards (chart_change, task, approval, choice, done, errors); `needs_you` cards are the team's Identity
  question verbatim, answered in the department session. **Department chat**: owner lines and Identity's `to_user`
  lines (J2's Simple view), no cards. The needs-you strip is unchanged.
- **Who labels** (`whoLabel`): `user` You · `sutra` Sutra · `identity` Client Lead (Identity), prefixed `<department> · `
  in the org chat and on cards · `adaptation` Strategist (Adaptation) · `priority` Prioritiser (Priority) ·
  `coordination` Scheduler (Coordination) · `audit` Quality Reviewer (Audit) · `W-n` W-n Builder · `validator` Validator ·
  `system` System. The last six show in function logs and the Detailed view only.
- **Department goal (S4-13).** There is no `departments.goal` (S2-14). The charter is `<run folder>/goal.json` (family
  `goal`); its readers are J2's routes and the nodes' `charter` context. The Projector reads no file and no event field
  for it; the closed `charter-stamp` atom is the signal that a charter exists.

## 8. UI contract (S4-10)
- **Chip** (`GraphNodeOut`, kind function): `id`; `label` = function name; `status` = `Node.state` from the node event;
  `detail` = event `detail`; `chat_session_id` = the node's own log; `meta` exactly `{stats, wait_on}`. Drawn: line 1
  persona, line 2 `Identity · 1 open · 5 closed`, J2's status outline, tooltip `12 calls · 41 s · 9,120 tokens · 1 failed`.
- **stats**: `calls, seconds, tokens_in, tokens_out` from the node event; `atoms_open, atoms_closed, atoms_failed,
  atoms_total` counted over `atoms.display` (failed = verify_failed).
- **Drawer** (`NodeDetail`: `node`, `session`, `atoms`, `usage_total`, `task`, `archived_chats`); `node.meta` =
  `goal, task, context, constraints, wait_on, hands_to, stats`. Order: head (persona and function, status chip,
  `node.detail`, usage line, counts) · Goal = `meta.goal` · Task = `meta.task`, `Working for: <title> (<status>)` from
  `NodeDetail.task`, `Waiting on you|<persona>` from `meta.wait_on` · Context, `What this function is given` ·
  Work atoms (n = `stats.atoms_total`; the open atom first, then the 20 newest; `Show all` = `GET
  /api/atoms?node_id=&limit=100&offset=`) under the strip's legend `open > work > verify, close; exits: refuse, abandon` ·
  Constraints · Hands to · the J2 block and `Go to the <function> tab` (department page only).
- **Atom card** (J2's labels): status line OPEN, CLOSED, VERIFY FAILED, ABANDONED or REFUSED with `attempt n of 3`; Goal;
  Constraints; Context; How (llm: the model, from `usage`; bash: code, no AI call; manual: you); Expected output =
  `outputs[0]`; Verification = per check its sentence and every try (`attempt 1: failed, <evidence>`); Result = the
  pill text, a `Concern on record` row for RECOVERED or WAIVED, and the cost line from `AtomOut.usage`.
- `AtomOut` = `id, schema, node_id, task_id, state` (the display word), `goal, attempt, ts_open, ts_closed, body, usage`.
- **Division click.** Chat tab: the lens, header `<Division> is part of <Department>. This is <Department>'s Identity,
  showing the work for <Division>`, link `Show everything for <Department>`, composer on. Details tab: `Functions of
  <Department>` with five chips that open the department's function panels; no goal, task or atoms.

## 9. Tests (S4-11)
- **Registry (E8).** Per check at least one pass, one fail, and the na, override, recovered and waived cases, as
  fixtures `tests/engine/fixtures/fn_registry/<check>/<case>.json` {evidence, expect}. Purity: same result on a deep
  copy, `open`, time and sockets forbidden. Parity with J2's `_stamp_check`, `workable`, the audience regexes,
  `design_problems`, `THRESHOLD`.
- **Mutation (E8).** Each check is replaced by always-ok and by always-fail; its cases must fail both ways. Outcome
  mutants must flip their check: GRANT over budget posted as GRANT, a schedule with an unregistered id, a PASS row with
  an empty note, a rubric item measured but passed, a charter that fails the stamp.
- **Layer (E6).** Hook sequences against fake J2 events: open, fail, close; refused; waived; recovered; abandon at run
  end; the manual atom; overhead binding; errors swallowed; `touches_miss` only logs.
- **Golden (E7).** Mock Brew Lab through the stub connector, layer on and `SUTRA_NODES=off`: identical `[function,
  sha(system), sha(prompt)]`. Per function at least one atom of each kind it handles (Identity intake, audit and the
  manual atom; Adaptation propose; Priority price and envelope; Coordination schedule; Audit audit). One atom per
  turn, none open at `run.ended`, every atom has a check, ledger rows = terminal atoms, no `usage` line without `atom`.
- **Server (ORCH).** Replay of the golden events: `atoms`, `display`, `atom_ledger` (once per atom, append-only, `atom/1`
  rows), cards, `open_atom` and `atom_count`, `stats`; replaying changes nothing; the org chat has no model prose.
- **UI.** `fnode_view.test.js` parses the `NodeDetail` fixture: section order, the five states and status lines, tries,
  concern row, stats line, no `Limits` label, legend. `chat_view.test.js`: the `whoLabel` table. `test_view_panel.py`:
  Identity chip with composer, the other four read-only, the division lens panel.
- **Contract (CT-1).** `atom_id` never NULL; node `meta` keys; `gen.py` holds the section 12 strings.

## 10. The fourteen answers (decision · why · rejected)
1. **Names (S4-1).** Library names; the diagram box is redrawn (section 12). Why: stores, wire and tests use them and no code
   exists to rename. Rejected: `AgentNode`/`WorkAtom`; a stored `BuilderAtom`.
2. **Registry (S4-2).** 14 named pure checks (FN-11's 12 and 2 floors), section 4. Why: the VERIFY lines become real with no
   j2.py change. Supersedes the v1 pair of S2-6. Rejected: only the generic pair; parsing J2's prompts; a new `_event` hook.
3. **Grain (S4-3).** One atom per turn; work llm, bash or manual (the question). Why: matches the strip and the cost lines;
   S2-6 plus what FN-2 asks. Rejected: an atom per router call.
4. **Mode (S4-4).** Observe. Hard = close only through checks, J2 enforces replies and routes, write scope warns and logs.
   Why: byte-identical J2. Rejected: re-asking or blocking in v1.
5. **Refuse (S4-5).** Stored, ledgered, carded (S2-10); the strip says `logged as refused`. Rejected: the plugin's silent
   refusal (FN-3, FN-16 'nothing is written').
6. **Sessions (S4-6).** One per node; division = lens; the Identity chip opens the department chat; function sessions are
   read-only logs. Why: draw.io steps 5 and 7, S2-11, ORCH-D1. Rejected: no division session (FN-6 read literally).
7. **Cost (S4-7).** One atom id on every call, overhead keys, never NULL (6.4). Why: the ledger sums to the bill.
   Rejected: NULL for the chat agent; a real overhead atom with a card.
8. **Statuses (S4-8).** Stored four, displayed five, one function (6.2). Rejected: a stored `verify_failed`; `refused` hidden.
9. **Atom log (S4-9).** The `atom_ledger` table is the box; every atom once, append-only, `verify_failed` rows included (6.3).
   Rejected: a second table; a node writing its own row.
10. **Chip and drawer (S4-10).** Section 8, each field names its source. Why: FN-15 wants the counts, S3-web-05 the J2 labels.
    Rejected: `last_seen`, a live `Task` object, atoms as dots.
11. **Tests (S4-11).** Section 9. Why: a check nobody can fail is decoration, so each is tested from both sides and by mutation.
    Rejected: a golden run alone.
12. **Voices (S4-12).** Section 7: prose only from Identity, Sutra = code. Why: FN-8 and 'Identity is the only voice' hold
    without a root Identity. Rejected: model-written org-chat replies (ORCH-D1).
13. **Department goal (S4-13).** No column, no read (section 7). Rejected: a column filled at `run.ended`.
14. **Node record (S4-14).** Section 2.2; the wire keys are its projection. Rejected: a `Task` object, stored `constraints`.

## 11. Supersession index (the patchers apply the S4 text)
- S2-6: the v1 check pair, 'Not in v1', the rejected clause on J2's named checks, the `verify_failed` rule of
  `atom_display_state`, 'a turn without a call is closed with turn-posted' (now bash).
- S2-7: 'AtomOut.state ... open at attempt 3'. S2-9: `node.meta.atom_count`. S2-8: `Task{...}` for node TASK (already by S3-web-04).
- S1-7: the context mapping (adds `atom_id`). S1-5: `atom_id` nullable. S1-10: `bind_atom(None)` at turn end (now the overhead key).
- S3-web-13(d): 'refused never leaves the API'. S3-web-04(c): the exact `stats` keys. S3-web unresolved 1, 2, 3, 4 are
  closed by S4-12, 6, 13, 14. ORCH-D1: the org-chat voice.
- Spec wording only: FN-2 'one step', FN-3 and FN-16 'nothing is written', FN-6's session sentence, FN-8's root Identity.

## 12. Diagram wording (exact strings for `gen.py`)
- Interface library box, 12 lines, lh 15.5, ly 41:
  `FunctionNode (base), children <X>Node:` · `Identity · Adaptation · Priority` · `Coordination · Audit` ·
  `Atom (base): goal, constraints,` · `context, work, verify, state` · `AtomView: J2 atom/1 (for builders)` ·
  `Departments · Goal · Evaluation` · `Org chart · Chart change` · `Also base: Workflow · Step · Template` ·
  `Artifact models + rules as data` · `closed models, checked at every write,` · `including every org chart change`.
- Strip caption line 1: `1 turn = 1 atom`. Refuse cell lines: `bad goal or check:` / `logged as refused`. The open, work,
  verify and abandon cells are unchanged and true.
- Arrow label: `every call has an atom id`. Usage ledger line 2: `one row per call, by atom`. Router lines unchanged.
- Aria-label: `every step of a node is one work atom` becomes `every turn of a node is one work atom`.
