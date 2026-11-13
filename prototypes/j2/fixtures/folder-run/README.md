# Fixture: a run whose output is a folder of files

`j2-20261113-090000/` is a hand-written run folder, not a saved run: the records a run keeps (goal.json, workflows.json,
artifacts.json, summary.json, chat.jsonl) for one workflow that wrote a folder, `script/`, with a small "copy files
between folders" script, its test and a README.

Its type, `script`, is not in `artifacts/types.json`. The run records it itself, in its `artifacts.json` row
(`"form": "script"`, `"output": "folder"`, `"folder": "script"`), which is where `j2_template_lib.type_data` reads a
type that types.json does not have. The shape follows the folder form on branch `agent-tools`.

Used by `j2_flow_test.py folder_reuse`: the run is saved as a run template, and a second mock run reuses it.
