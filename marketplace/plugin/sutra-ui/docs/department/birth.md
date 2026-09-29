# Birth: an organisation, its Root, a department

| Field | Value |
|---|---|
| **status** | v1, 2026-09-29, RECORD of the code (Sutra Desktop v2.306.19-desktop; the organisation row from v2.306.20) |
| Code | `website_api.py` (`/found`, `/{ref}/ask`, `/{ref}/asks/{aid}`), `founding.py` (`found_structure`, the spawn), `engine_runtime.py` (`request`, `FRONT`, `identity_gate`, `setup_read`, `p_setup_shape`, `d_setup_shape`, `setup_make`, `identity_file`), `engine_defs/website.json` (`kinds`) |

## The organisation and its Root

- `POST /api/native/found {org, first}` (the New organisation sheet's Found button, `wbFoundGo` in `22-website.js`) calls `founding.found_structure(org_name, owner)`: one organisation node and one department of kind `root`, On. If `first` words came with it, they go to Root as its first request (`W.owner_ask(root, first)`).
- Root's goal on its record: "{name}: makes, changes and ends this organisation's departments from the Library's templates; its authority ends at the owner" (`kinds.root.goal`). Root's line is one engine, `Setup`; its artifacts are `Request` and `Department`.
- Root's rules at birth: "A new department is stamped by the owner"; "A child's rules can only tighten this one's"; "Set up what the owner asked for, from the Library's templates".
- On the screen the organisation's row is Root's chat and Root is not drawn; founding lands on that row; the departments Root makes sit under the organisation in the tree and on the chart (`chat.md`, "The organisation row").

## The front door

- Words said to Root arrive as a board post from `Owner` to `Identity` with the word `front` (`request`: `front = d.get("kind") == "root"`). Words said inside a department arrive with the word `request`; said in a function's chat they carry `about = {"fn": <name>}`; said from a department's chat to Root they carry `about = {"dept": <ref>}` (the chip).
- Root's Identity files the words as a `Request` version and asks the owner (`identity_gate`, engine `Setup`): the ask's text is "Set up a department for: " + the first sentence of the words, cut at 120 characters; kind `setup`.
- Short front words are read by code first (`FRONT`): a line starting with stamp / yes / approve / ok is a stamp, refuse / no / reject a refusal, stop a Stop, start / resume a Start, and "start | set up | create | make | found … department" a setup request.

## Setup

| Step | Id | Rung at birth | Does |
|---|---|---|---|
| Read the request | `setup.read` | code | the words, the Library's kinds with each one's use case, the names this Root already has (`setup_read`) |
| Shape the department | `setup.shape` | improvised call (a model call) | returns `{name, kind, goal}`; the prompt lists each kind's use case and the existing names (`p_setup_shape`); the offline draft picks `website` and names "<org> Website" (`d_setup_shape`) |
| Make it | `setup.make` | code | `founding` spawns the department of that kind with that goal; a name that already exists is not made again: the words are handed to the existing department and the owner is told (`setup_make`) |
| File | `setup.file` | code | the `Department` artifact names the child's ref |

The child's functions are born from the kind's `functions_template` (`founding`: `product-build` for a website, `default` otherwise); a template picked later on a function's Settings tab is what `card()` reads (`function_templates.picked(ref)`).

## The kinds

| Kind | Use case (`kinds.<kind>.use_case`) | Line | Artifacts | Rules at birth |
|---|---|---|---|---|
| website | a live website: pages planned, written, checked and published | Plan, Write, Check, Publish | Brief, Site plan, Pages, Build, Live site | plan, write and check inside the record; ask the owner before the first publish; never publish a build whose check failed |
| root | the one root of an organisation: sets up its departments from the Library | Setup | Request, Department | as above |
| default | any goal the Library has no kind for: one Do engine answers each ask as a written Result | Do | Brief, Result | work inside the record; ask the owner before anything reaches outside |

`library_kinds()` reads them from `engine_defs/website.json`; the record carries the kind, its `engines` and its `artifacts` at birth (`website_dept.create`), and `engines_of` / `artifacts_of` read the record, never the kind again.

## The first words in the child

- The child's Identity takes the first words (`identity_file`, `first = facts.first`: no Brief yet).
- If the take says `thin` (the words name no subject and no purpose to build from), Identity says "Say what the site is for and about whom or what, and I will start: your words name nothing to build from yet." and files nothing; the next words are taken as the goal (`identity_file`, the `thin` branch).
- Otherwise the words are filed as the Brief's first version ("the owner's goal", `_file_words`) and the line starts on it. What the owner said they were not sure of (`unsure`) is written into the Brief as "Not confirmed (…)" and asked about at once (`ask_unsure`).

provenance: {author: claude, session: 17842ce0, date: 2026-09-29, inputs: [engine_runtime.py: request, FRONT, identity_gate, setup_read, p_setup_shape, d_setup_shape, setup_make, identity_file; founding.py; website_api.py; engine_defs/website.json kinds], review: none by a second model, confidence: high}
