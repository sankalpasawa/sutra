# Engines and the Library

| Field | Value |
|---|---|
| **status** | v1, 2026-09-29, RECORD of the code (Sutra Desktop v2.306.19-desktop) |
| Code | `engine-templates/*.json`, `engine_runtime.py` (`engine_templates`, `user_templates_dir`, `defs`, `validate`, `engine_def`, `missing_engines`, `born_template`, `engine_from_shape`, `add_engine` in `website_dept.py`, `call_model`, `do_read`, `p_do_need`, `p_do_make`, `do_file`), `website_dept.py` (`MODEL_TOOLS`, `model_json`, `engines_of`) |

## The shipped templates

| Template (`id`) | Reads | Writes | Starts on | Held by (`unless`) | Steps |
|---|---|---|---|---|---|
| engine/plan | Brief | Site plan | a new Brief | identity.wait_engine, identity.gate, priority.envelope, coord.chain | plan.read (code), plan.pages (model), plan.fit (code), plan.file (code) |
| engine/write | Site plan | Pages | a new Site plan | the same | write.list (code), write.page (model, one call per page, four side by side), write.file (code) |
| engine/check | Pages | Build | new Pages | the same | check.rules_of (code), check.rules (model, only when the record has stamped rules), check.build (code) |
| engine/publish | Build | Live site | a checked Build | the same | publish.copy (code) |
| engine/setup | Request | Department | a new Request | identity.gate, priority.envelope, coord.chain | setup.read, setup.shape (model), setup.make, setup.file |
| engine/do | Brief | Result | a new Brief | the same four as Plan | do.read (code), do.need (model, only when something was filed before; may end the run), do.make (model), do.file (code) |

`engine_templates()` reads every `*.json` in the shipped `engine-templates/` and then in the record home's Library (`user_templates_dir()` = `<record home>/_library`); a file that is not a template (no id, name or use case), or a name already taken, refuses the load. `defs()` assembles them into the definitions with the functions from `engine_defs/website.json` and validates the whole (`validate`: every step names a check that exists, a template names a use case, a kind names a functions template every function has, tools only from `MODEL_TOOLS`). The cache is per record home.

## The record's engines

`website_dept.create` writes the kind's line onto the record as `engines` and its artifacts as `artifacts`; `engines_of(d)` reads the record (name, reads, writes, runs as model or code). `missing_engines(d)` names any engine on the record that no template defines; such an engine has no trigger of its own (`ready` returns None for it), its card says Missing, and the Library health line names it (record.md).

## Born engines

An idea the owner floats becomes an engine when the owner stamps it (functions.md, Adaptation): `identity_apply` (kind `engine`) calls `W.add_engine(ref, name, shape, by, before)`, which writes the engine and its artifact onto the record with an envelope and a window, grows Coordination's line (`grow_line`: before Plan when it reads the Brief), and for an engine shaped on the fly writes a template into the record home's Library (`born_template`): Do's steps under the engine's own ids (`<slug>.read`, `<slug>.need`, `<slug>.make`, `<slug>.file`; a step's `only_if` follows the ids), its use case and instruction from the idea, `reads` Brief, `writes` its own name, `made_by` (the department and the idea), and tools on its prompt steps when the shape named a need (`NEEDS`: internet → WebSearch, WebFetch; `timeout_s` 600). A template that fails validation is unlinked.

## The need step (Do and every born engine)

`do_read` returns the Brief and what the engine filed last (`previous`, `previous_v`). `do.need` runs only when something was filed before (`only_if: <slug>.read.previous`) and asks the engine's own agent whether the newest words ask for its work again; an answer `run: false` ends the run ok with the row's `what` "not needed: <why>" and files nothing (`run_engine`, `may_end`), so the line reads the last filing. `p_do_make` shows the last result under "WHAT YOU FILED LAST TIME" with "keep what still holds, add what is new, and list under a line 'Dropped' what you removed and why".

## The model's tools

`call_model` hands every prompt step the model's web tools unless the step's own list narrows them: `W.model_json(prompt, timeout, tools=step.get("tools") or list(W.MODEL_TOOLS))`; `MODEL_TOOLS = ("WebSearch", "WebFetch")`; `model_json` runs `claude -p … --tools <t> --allowedTools <t>` and drops any name outside the list. `_has_web(d)` is true. The take carries no needs and no ask names the internet (founder, 2026-09-29: "Internet is given"). The idea → engine path stays for a new capability.

## What Plan and Write build from

`_context_block(ref)` is the latest text of every artifact on the record that the kind's own line did not name (what the engines the owner added have filed), handed to Plan and Write as "WHAT THE DEPARTMENT'S OWN ENGINES FILED (build from it; say on the page where each fact came from)", and to Audit's judge. A bare address in a page's text becomes a link (`_link_addresses` in `write_file`).

provenance: {author: claude, session: 17842ce0, date: 2026-09-29, inputs: [engine-templates/*.json; engine_runtime.py: engine_templates, user_templates_dir, defs, validate, missing_engines, born_template, do_read, p_do_need, p_do_make, call_model, _context_block, _link_addresses; website_dept.py: create, engines_of, add_engine, model_json, MODEL_TOOLS], review: none by a second model, confidence: high}
