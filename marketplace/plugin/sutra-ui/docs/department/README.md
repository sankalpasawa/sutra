# The department, as built: the logic in one set of files

| Field | Value |
|---|---|
| **status** | v1, 2026-09-29, session 17842ce0; RECORD of the code as shipped in Sutra Desktop v2.306.19-desktop (sutra 0e1651be) |
| Code | `engine_runtime.py`, `website_dept.py`, `website_api.py`, `founding.py`, `artifacts.py`, `engine_defs/website.json` (def_version 10), `engine-templates/*.json`, `artifact-templates/*.json`, `static/js/22-website.js` (all in `sutra-ui/`) |
| Rule | every claim names the function or file it was read from; nothing here is proposed or designed (founder, 2026-09-29: "Don't add anything new. Just add whatever is there in the logic.") |
| Native | the design this builds toward is `sutra/os/engines/NATIVE-ENGINE.md` and the ADRs; this set is Core, built |

## The files

| File | Holds |
|---|---|
| [birth.md](birth.md) | an organisation and its Root; the front door; Setup; the kinds and what each is born with; thin first words |
| [functions.md](functions.md) | the five functions: what each hears, its steps, its gates, its rules; Identity's take |
| [engines-and-library.md](engines-and-library.md) | the engine templates, the record's engines, born engines and the record home's Library, the need step, the model's tools |
| [line.md](line.md) | how anything starts: triggers, blockers, Coordination's table, one run at a time, the run row and the working line |
| [asks-and-rules.md](asks-and-rules.md) | every kind of ask, what a stamp does, rules on the record and as checks |
| [chat.md](chat.md) | the one chat through Root, a department's own turns, a function's chat, the tells and their buttons |
| [record.md](record.md) | the record on disk: artifacts, versions, runs, step rows, the map, health |
| [updates.md](updates.md) | what lives in the app bundle and what lives with the records; what an update keeps |

## How a department works, in one paragraph

A person founds an organisation: one Root is born (`founding.found_structure`) and the first words go to Root's Identity (`engine_runtime.request`, word `front`). Root asks the owner in one line; on the stamp Root's Setup engine shapes a department from the Library's kinds and spawns it (`setup_make`). The child's Identity takes the words (`identity_file`) and files them as the Brief; the kind's line of engines runs on new versions (`next_due` → `coord_pick` → `ready`), each engine's start held by its blockers (`blocked`); what an engine files is a version with its check (`W.add_version`); the person is told in the chat (`_tell`), asked to stamp what reaches outside (`identity_gate`, `_rule_ask`, `identity_finding`), and reads the result on the map (`W.map_view`). Every agent step runs on a rung (person, improvised call, checklist, code: `RUNG_NAME`) and writes a step row (`run_step`).

## What this set does not say

The screens' layout (`static/js/22-website.js` and the design pages under `holding/website/native/`), the release lane (`sutra/scripts/release-desktop.sh`), and the Human Simulation program (`qa/sim/AGENT.md`).

provenance: {author: claude, session: 17842ce0, date: 2026-09-29, inputs: [the code named above at sutra 0e1651be, read function by function during the fix units of 2026-09-29; the closed lists extracted from engine_defs/website.json, engine-templates/*.json and artifact-templates/*.json], review: none by a second model, confidence: high on every claim that names a function; the set is a record, not a design}
