# Engines and the Library

| Field | Value |
|---|---|
| **status** | v1, 2026-09-29, RECORD of the code (Sutra Desktop v2.306.19-desktop; the line shaped on the fly from v2.306.21) |
| Code | `engine-templates/*.json`, `engine_runtime.py` (`engine_templates`, `user_templates_dir`, `defs`, `validate`, `engine_def`, `missing_engines`, `born_template`, `engine_from_shape`, `add_engine` in `website_dept.py`, `call_model`, `do_read`, `p_do_need`, `p_do_make`, `do_file`, `born_table`, `p_adapt_line`, `c_line_is_engines`, `adapt_line_offer`, `identity_line`, `identity_apply`, `identity_gate`, `_goes_out`, `_writes_site`), `website_dept.py` (`MODEL_TOOLS`, `model_json`, `engines_of`, `map_view`) |

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

## The line shaped on the fly (the organic kind; founder 2026-09-30: "each of the adaptations doesn't do any kind of template. It creates engines on the fly")

- A department of the kind `organic` (`engine_defs/website.json` kinds: `line: []`, artifacts Brief only, functions template product-build, rules "Work inside the record" and "Ask the owner before anything reaches outside") is born with no work engines; `born_table` keeps its Coordination line empty (an empty record line is a line, not "no line given").
- On its first words (`identity_file`, verdict go, first): Identity posts a request with the word `line` to Adaptation and tells the owner "Adaptation is shaping the engines your words need; you will be asked to stamp the line before anything runs" (a thread of its own: the request's thread closed on "filed in the Brief").
- Adaptation's handler "Shape the line" runs `adapt.hearline` (code), `adapt.line` (prompt `p_adapt_line`: the words, the names the Library already uses, the artifacts that go out (`_out_artifacts`: the templates with `counts_after: stamp`), the department's rules; it returns two to five engines {name, does, reads, writes, internet}; the check `c_line_is_engines`: one to six, each named once and not as the Library names one, the first reads the Brief, each reads the Brief or what one before it wrote, each writes something not yet written; the offline draft `d_adapt_line` is Facts → Site) and `adapt.lineoffer` (a propose post to Identity with the word `line`).
- Identity's handler "a line proposed" (`identity_line`) puts the whole line to the owner as one ask of kind `line`: "Set up the line A -> B? A does …; B does …. Stamp to add them and start, Refuse to say what to change."
- The stamp (`identity_apply`, kind line) first runs `_line_faults` on the whole line (the same code as the shape step's check, plus the slug each template file would take against the shipped and the record home's templates); a line with a fault is refused whole and the owner told "The line could not be set up: ...; say the words again" (DeepSeek P2, 2026-09-30). Then `W.add_engine` per engine in order with its shape (use case and instruction from `does` and the words, `needs: ["internet"]` when the agent marked it, reads, writes); each is born into the record home's Library from Do (Born engines above); the owner is told "Added the line A -> B; the first starts on your words now" (an engine that still could not be born is named under "Not added"). The first engine starts on the Brief version that exists; each next one on what the one before it writes. Priority prices nothing here (one stamp for the line); the idea → engine path keeps its pricing.

## A born engine's input, and pages

- `do_read` hands every born engine what is new in its input since the version it last read (`changed`: the lines not in the earlier version), and `p_do_make` / `p_do_pages` show it as "NEW IN THE <artifact> SINCE YOUR LAST RUN ... carry every line of it through" (found on the Beta 2026-09-30, finding 63: Vetting dropped Facts v2's new food section).
- The need step weighs the owner's words; `born_template` gives it only to an engine that reads the Brief. An engine that reads another engine's filing runs on every new version of it, which is its trigger (finding 62: Launch judged new pages "not needed").
- An engine whose artifact is pages (`_writes_pages`: the template's kind site, pages or build) plans its pages in one small call (`<slug>.plan`, prompt `p_do_pages`: index.html first, two to twelve, keep what still holds from the last version's files, add what the input asks for; check `pages_are_named`) and writes one page per call, four side by side (`<slug>.page`, `each` over the plan, prompt `p_do_page`: a whole HTML document with a nav over the site's pages, each fact with its source as a link; check `page_is_html`: a body of 20+ words under the planned file name); `do_file` gathers the pages (findings 60, 63: one answer for every page trimmed a growing site).

## What goes out

`identity_gate` asks the owner before the first version of any artifact the Library counts after a stamp (`_goes_out`: the template's `counts_after == "stamp"`, the Live site), Publish's included: the ask reads "<engine>: go live for the first time, served from <host> unless you say where else" and may read the engine's input. A born engine whose artifact is a site (`_writes_site`: the template's kind `site`) is asked by `p_do_make` for whole pages ({"files": {"index.html": …, "<page>.html": …}}, index.html first, the others linked from it, each fact with its source as a link) instead of one answer; `do_file` writes the files, applies the artifact's own checks from the Library (`artifacts.check(writes, files, default=True)`: Pages wants html files, the Live site its index.html), and marks a site version `publish`; `run_engine` puts it on the host (`W._publish_files`) only once the version row is written, so the record and the host never disagree (DeepSeek P1, 2026-09-30); `c_result_is_text` accepts a files dict. `map_view.live` is true for any department whose artifacts hold a Live site version, whatever its kind.

## The need step (Do and every born engine)

`do_read` returns the Brief and what the engine filed last (`previous`, `previous_v`). `do.need` runs only when something was filed before (`only_if: <slug>.read.previous`) and asks the engine's own agent whether the newest words ask for its work again; an answer `run: false` ends the run ok with the row's `what` "not needed: <why>" and files nothing (`run_engine`, `may_end`), so the line reads the last filing. `p_do_make` shows the last result under "WHAT YOU FILED LAST TIME" with "keep what still holds, add what is new, and list under a line 'Dropped' what you removed and why".

## The model's tools

`call_model` hands every prompt step the model's web tools unless the step's own list narrows them: `W.model_json(prompt, timeout, tools=step.get("tools") or list(W.MODEL_TOOLS))`; `MODEL_TOOLS = ("WebSearch", "WebFetch")`; `model_json` runs `claude -p … --tools <t> --allowedTools <t>` and drops any name outside the list. `_has_web(d)` is true. The take carries no needs and no ask names the internet (founder, 2026-09-29: "Internet is given"). The idea → engine path stays for a new capability.

## What Plan and Write build from

`_context_block(ref)` is the latest text of every artifact on the record that the kind's own line did not name (what the engines the owner added have filed), handed to Plan and Write as "WHAT THE DEPARTMENT'S OWN ENGINES FILED (build from it; say on the page where each fact came from)", and to Audit's judge. A bare address in a page's text becomes a link (`_link_addresses` in `write_file`).

provenance: {author: claude, session: 17842ce0, date: 2026-09-29, inputs: [engine-templates/*.json; engine_runtime.py: engine_templates, user_templates_dir, defs, validate, missing_engines, born_template, do_read, p_do_need, p_do_make, call_model, _context_block, _link_addresses; website_dept.py: create, engines_of, add_engine, model_json, MODEL_TOOLS], review: none by a second model, confidence: high}
