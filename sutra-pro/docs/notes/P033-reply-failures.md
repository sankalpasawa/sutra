# P033: why function replies failed `reply-valid` (D158)

`reply-valid` runs `ReplyParser` on the reply of each model call of a function turn. The layer only observes: a refusal fails the atom (attempt 1 at the reply, attempt 2 at the turn end of the same call) and abandons it; it re-asks nothing. The models were never shown to the model: J2's own prompts (vendored) set the reply shape.

## Fixed
| Cause | Reply as it failed | Fix |
|---|---|---|
| Audit rubric ids | `rubric.0.id: String should match pattern '^[RD]-[0-9]{1,3}$'` for `PJ-1`..`PJ-5` | `RubricRow`, `RubricResult`: `^[A-Z]{1,4}-...`; `ConditionResult`: `^[A-Z]{1,4}[0-9]+$` (PJ1..PJ3 of `data/project.json` were refused by the stored record too). A test walks every registered output's rubric and conditions. |
| Free text over its cap | `to_agents: String should have at most 600 characters` (every capped `str` without a pattern: `say` 4000, `reason`, `to_requester`, `clause`, `instruction`, `question`, `evidence`, `criterion`, `read`, charter `statement`/`done_when`/`facts`/`audience`, `questions[]`, `lessons[]`, `analysis`, `certainty` texts, `factors`, `stages`, ...) | `clip_text=True` in `reply-valid`: cut, closes `RECOVERED: text over its limit, read cut to it: <path> (<n> > <cap>)`. |
| `verification[].template: Field required` | J2's prompt words a corrected check `{text, type, target, expect}` for an atom verdict; `AtomVerdict` held `Check` (`template`, `args`) | `AtomVerdict.read_wire` reads J2's shape with the same reader as workflow atoms. The turn is kind `atom_failed` (its atom shows the generic goal; the failing path is `atom_verdict`'s). Test feeds `EXAMPLE_WORKFLOW`'s checks, the example the prompt shows. |

## Found by reading, not fixed (reproduced on main; likelihood in brackets)
- Workflows (propose, respond, price): texts inside J2-shaped `atoms` are not cut (the walker does not read `atoms`): `goal_gap`/`completion_check` over 400, `how.steps` over 2000, `context[]` over 200, `dependencies[]` named by workflow name over 40 [occasional]. Follow-up: convert J2's atom dict to plain fields before the tolerant pass.
- Same path: behavior item without `target` (`workflows.0.target: Field required`) [likely]; `facts-present` target with more than 8 strings (`args`, atom.py) [occasional]; `how.kind` "ai", check `type` or expected `kind` in other case [occasional]; numbers as floats/strings in `estimated_resources`, `envelope` [rare]; a non-list `atoms` raises `TypeError` (exit 127) [rare]; paths read `workflows.0.target`, not which atom.
- GRANT echoing workflows without `atoms` (`workflows.0.steps: Field required`) [likely]; GRANT with `money_limit` null/0 or empty `workflows` [occasional].
- `null` for an optional list/str/bool field (strict models) in every kind [occasional]. J2 reads `or []`.
- Identity: `goal` with keys the model does not declare (`open_inputs`, `criterion`) [occasional on re-intake]; `core` of the wrong length; `site_name` omitted; `facts` over 60; `ruling` given with `resolved=false`; `clause` omitted or over 300; `next` "user"; `needs_decision` with `next` Requester; options over 4.
- Adaptation: PROPOSE with no workflows; POLICY_QUESTION with the question only in `say`; ACCEPT/PARK echoing workflows; BUILD_WRONG without `affordable`; bare atom id `a1`.
- Audit: rubric verdict BLOCKED_BY_EVIDENCE or POLICY_CONCERN, finding id outside `F-...`, severity/confidence "none", `next` Adaptation [occasional].
- Coordination: `rule` empty, hold without `missing`, ids not exactly `W-n` [rare].
- Mapping: the identity `audit` turn also makes the limit call (`{say}`), judged as `done` (`done`/`next` required) on every limit path [likely]; priority `ruling` has no `next` in J2's format (fixes=1 only); priority `envelope` declares no `reply-valid` (work hint bash); `lesson` has no task kind. Each needs a new reply class or a spec change that moves the function-node goldens (D150): not in this brief.
- List caps (`questions` 4, `findings` 120, `workflows` 20) are counts, not text: not cut.
