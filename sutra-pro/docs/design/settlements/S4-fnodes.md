# S4 function nodes: the one design

_Batch S4-fnodes · 2026-11-04 · decided by the architect for the owner, no questions asked · machine record with the exact patch instructions, work packages and diagram labels: `S4-fnodes.json` (same folder) · the design itself, read this first: `../function-nodes.md`._

**Read.** The final function-node spec (`function-nodes-spec.json`, all keys), S1-contracts-09 and 10, S2-models-03 and 05 to 11 and 14, S3-web-04, 05 and 13 and their unresolved lists, the function-node parts of library.md, engine.md, orchestrator.md and ui.md, `DECISIONS.md`, `sections.json`, `wp-union-s123.json`, `gen.py`, the draw.io page 3, the J2 code the spec cites (`ROUTES`, `call()`, `_stamp_check`, `workable`, `_check_audiences`, `_atoms_checked`, `_kept_price`, the Priority and Coordination turns, `_audit_findings`, `_audit_rubric`, `_ask_user`, `_goal_done`, `j2_realization.THRESHOLD`) and the plugin `bin/sutra-atom`. Decision order used: keep J2 byte-identical, the final spec on concepts and on what the figure promises, the settlements on structure, the fewest moving parts.

**Checked here.**
- The plan with this batch applied (46 packages plus E8 = 47, E6 re-owned and re-wired) passes `scripts/plan_tools.validate`: no file owned twice, no cycle, every dependency known. Nine waves as before; E8 sits in wave 3, E6 in wave 4; the critical path is unchanged.
- Every J2 line number in the design (`j2.py:1523, 2470, 3188, 4147, 4151, 4172, 4837, 5962, 6394, 6404, 6534, 6558, 6617, 6854, 8864, 8892, 9194`) was read at `ce2631fb`.
- A mock J2 run of the Brew Lab brief (J2's own venv, files in /tmp, the render check stubbed as `j2_flow_test.py --fast` does; nothing in the J2 repo changed) confirmed what the checks read: the message metas `stamp`, `realization`, `decision` with `exchange`, `register` with `charged`, `schedule`, `auto` with `envelope`, `audit` with `workable`, `done`; the files `goal.json`, `workflows.json`, `audits.json` (results, rubric, mechanical), `realization.json` (`plan_confidence`, `not_ready`, `rounds`); and the `ledger` pair in `calls.jsonl` inputs. It also showed that a `rejected: plan` post is J2's necessary-conditions check, not an atom rule (the design ignores it).
- Every new diagram string was counted: the Interface library box has 12 lines of at most 38 characters; the other strings are 15 to 25 characters.

**Not checked.** No real model or CLI was called (D8). The checks were designed against J2's code and mock behaviour, not against live replies. The diagram generator was not patched (not in this task's file list); the exact strings are in `function-nodes.md` section 12.

| Id | Point | In one line |
|---|---|---|
| S4-fnodes-01 | Names | Library names stand (FunctionNode, Atom, AtomView); the figure's box is redrawn; no BuilderAtom class |
| S4-fnodes-02 | VERIFY registry | 14 named pure checks (FN-11's 12 plus the 2 floors), evidence from hooks only, J2's recovery stays; new WP E8 |
| S4-fnodes-03 | Atom grain | One atom per function turn; llm, bash or manual (the owner's question); strip says `1 turn = 1 atom` |
| S4-fnodes-04 | Mode | Observe; hard = close only through checks, J2 enforces replies and routes, write scope warns and logs |
| S4-fnodes-05 | Refuse | Stored, ledgered, carded; the strip says `logged as refused` |
| S4-fnodes-06 | Sessions | One per node; a division is a lens on its department's Identity; the Identity chip opens the department chat |
| S4-fnodes-07 | Cost and ledger | Every call carries one atom id; overhead keys for the chat agent and out-of-turn calls; never NULL |
| S4-fnodes-08 | Statuses | Stored four, shown five; `verify_failed` is abandoned with a code; one function for card, log and chip |
| S4-fnodes-09 | Atom log | The `atom_ledger` table, append-only, one row per atom, builders and `verify_failed` rows included |
| S4-fnodes-10 | Chip and drawer | Exact fields and where each comes from; `stats` gains failed and total |
| S4-fnodes-11 | Tests | Registry cases, mutation of every check, layer sequences, golden run per function, server replay, drawer parse |
| S4-fnodes-12 | Voices | Prose only from Identity; Sutra is code; the chat agent's sentences are not shown; no root Identity |
| S4-fnodes-13 | Department goal | No column, no projector read: the charter is `goal.json` |
| S4-fnodes-14 | Node record | One field list for the DB body, the wire and the drawer; no `Task`, no `last_seen` |

## What the patchers apply over S1, S2 and S3
- **S2-models-06** loses its v1 check pair, 'Not in v1', the matching rejected clause and the `verify_failed` rule of `atom_display_state` (S4-fnodes-02, 08); its grain paragraph gains the manual atom and bash (S4-fnodes-03).
- **S2-models-07** keeps its event and table design; `AtomOut.state`'s `verify_failed` rule is replaced and `atoms` gains `display` (S4-fnodes-08); the ledger rule covers builders (S4-fnodes-09).
- **S2-models-09 and S3-web-04(c)**: the `stats` keys are the S4-fnodes-10 list. **S3-web-13(d)**: `refused` is a wire word.
- **S1-contracts-05, 07 and 10**: `atom_id` is never NULL for the engine and the chat agent; `context.atom_id` maps to `CallTag.atom`; `bind_atom` rebinds the run overhead key instead of clearing (S4-fnodes-07).
- **ORCH-D1 and S3-web unresolved 1 to 4** are closed by S4-fnodes-12, 06, 13 and 14.
- Spec wording only: FN-2 'one step', FN-3 and FN-16 'nothing is written', FN-6's session sentence, FN-8's root Identity. Every other FN decision stands as written.

## Work packages
- **Added:** E8 (verify registry; owns `fnodes/__init__.py`, `registry.py`, `evidence.py`, two test files and the fixtures directory; after E0, E1, L4, L5).
- **Re-owned and re-wired:** E6 (loses `fnodes/__init__.py` to E8; now also after E8).
- **Title and acceptance only:** L1, L4, L6, L10, E0, E3, E7, CN-7, ORCH-1, ORCH-3, ORCH-4, ORCH-6, ORCH-7, UI-0, UI-4, UI-6, CT-1. Each package is changed in exactly one settlement, so its last title is unambiguous.

## Unresolved (with fallbacks, none blocks development)
- Real J2 replies against the closed reply models (the floor check may fail atoms J2 accepted; loosen the classes, not the check).
- Four checks read J2's own posted strings; a golden pins them; a later P8 hook is the fallback.
- FN-8 as decided and the division lens are the two choices the owner may veto; both have a stated way back.
- Retention of atoms, cards and log rows; `Atom.effort` stays null; the diagram is not patched here.
