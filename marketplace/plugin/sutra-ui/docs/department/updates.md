# Updates: what lives where, and what an update keeps

| Field | Value |
|---|---|
| **status** | v1, 2026-09-29, RECORD of the code (Sutra Desktop v2.306.19-desktop) |
| Code | `engine_runtime.py` (`TEMPLATES_DIR`, `user_templates_dir`, `engine_templates`, `defs`, `missing_engines`), `website_dept.py` (`home`), the app bundle (`/Applications/Sutra.app`, `/Applications/Sutra Beta.app`, `Contents/Resources/payload/plugin/sutra-ui/`) |

## In the bundle (replaced by an update)

The code, `engine_defs/website.json` (with its `def_version`), the shipped `engine-templates/`, the `artifact-templates/`, the `function-templates/`, the screens. Nothing a person made is written here.

## With the records (kept by an update)

The records home (`home()`: `~/.sutra-ui/native` stable, `~/.sutra-ui-beta/native` Beta): every department's directory, the boards, the runs, the versions, the served sites, and the Library's other half, `_library/`, where born engines live (`born_template`, `user_templates_dir`).

## What happens on an update

- The definitions are read again from the new bundle with the record home's born templates merged in (`engine_templates`, `defs`); a record's `engines` list is read as it is.
- An engine a record names that the new bundle and the record home do not define is Missing: its card says so, the Library health line names it and says "say its idea again to shape it anew", it has no trigger, and the rest of the line runs (`missing_engines`, `ready`, `engine_view`, `health`).
- A department born before the record carried `engines` and `artifacts` takes the kind's line (`engines_of`, `artifacts_of`).
- A record whose `runtime` is not 2 keeps the first build's four engines and five artifacts (`ENGINES`, `ARTIFACTS`).

## The two apps

The stable app serves the panel on 8330 with `~/.sutra-ui`; the Beta on 8331 with `~/.sutra-ui-beta`; each has its own updates folder named from the bundle (finding 18, `updates.py`). A record is never shared between them.

provenance: {author: claude, session: 17842ce0, date: 2026-09-29, inputs: [engine_runtime.py: TEMPLATES_DIR, user_templates_dir, engine_templates, defs, missing_engines, ready; website_dept.py: home, engines_of, artifacts_of, engine_view, health; the Beta's record home read on 2026-09-29], review: none by a second model, confidence: high on the code; moderate on the updates folder, which is finding 18's record, not read again today}
