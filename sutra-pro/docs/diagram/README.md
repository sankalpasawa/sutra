# Architecture diagram

`gen.py` draws the architecture figure as one inline SVG page (`python3 docs/diagram/gen.py` writes `arch.html` next to it;
the page needs only a browser). The figure is published as a Claude artifact (figure only; same link for every version):
https://claude.ai/artifact/HweydYv8jVVoZBA9SkuxVB

| Version | What it added |
|---|---|
| v1-v2 | Owner's draw.io page 3 plus everything in the J2 prototype, and the Claude / Codex connector layer |
| v3 | ONE global org chart that tasks reuse, add to or rearrange (never one chart per workflow) |
| v4 | The five J2 functions as agentic graph nodes with goal, task, context, work atom, verify and constraints (`docs/design/function-nodes-spec.json`) |
| v5 | As-built wording from the settled design (FunctionNode / Atom / AtomView names, `1 turn = 1 atom`, refuse logged, one row per call by atom, the Codex login text) and the 87 decisions: a pill of D-numbers on every box they concern and a key of all of them at the bottom (`decisions.json`, built from `docs/design/decision-index.json` and D1-D12) |
| v6 | As-built additions and all 97 decisions (D88-D97 new): a Console page box (usage and cost, Atom log, health and diagnostics), an Operator box in the server column (doctor, status, stop, config, backup, restore, export, prune, one instance per data folder, logs), a Stub connector box with the offline demo reply book, "each run keeps its own copy" on the Template library box; pills for D90, D92, D94, D95, D97. The Experience band gained a row (`XP`) and the connector band a row (`SH`); lower groups move down by them |

The helpers at the top of `gen.py` (`box`, `line`, `badge`, `label`, `band`, `node`) draw every element; `EX` is the extra height
of the department runtime band, and everything below it moves down by `EX` inside one `<g transform>` group.

`decisions.json` holds the id, the short label and the box each decision is drawn on (`anchor`; `null` = key only). `PLACE` in `gen.py` moves a pill row off an arrow or badge.
