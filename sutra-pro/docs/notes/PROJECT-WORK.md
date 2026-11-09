# Project work: the working folder, its access and its instructions (D125)

**Reported by the owner after beta 3.** A team told "check the details of the app, update the J2 prototype in the app and in its repo" answered "what website do you want built?" and never looked at the folder. Claude's own desktop app reads the project, follows its instructions and does the work.

## Root causes (all four were needed)
1. **Where the words went.** A team's chat message (and a task the org chat assigned) always started a document run of the engine. That engine makes a PRD, HLD, LLD or website; its first agent, Identity, asks what site is wanted when the brief is anything else. The working folder (D121) was only ever given to the direct chat ("Ask the model") and the org chat agent; the engine never asked for it.
2. **No leave to change files.** The folder tools were read-only (Read, Glob, Grep, LS); the owner asked the team to update things.
3. **The project's instructions were not read.** The CLI is started with `--setting-sources ""` and a replaced system prompt, so a project's `CLAUDE.md` never reached the model.
4. **Nothing said so.** No folder was set (the owner's data folder had no `connectors/workdir.json`), the setting was a typed path under Settings, and the team chat showed nothing about it.

## What changed
| Part | Where |
|---|---|
| Access: read and change (default for a newly chosen folder) or read only; an older file stays read only | `connectors/workdir.py` (`Folder`, `access`), `claude.py` `_folder_tools`, `codex.py`, `connectors/api.py` |
| The tools with "change": Edit, MultiEdit, Write and Bash limited to git status/diff/log/show (no write into `.git`, no git option that writes or reads outside the repository); codex `workspace-write` | same |
| The project's CLAUDE.md (else `.claude/CLAUDE.md`, else AGENTS.md) in the system text of the chats that have the folder, up to 12,000 characters, never through a link; the grounding has room for it | `workdir.instructions_of`, `chat_ground.py` |
| The page: Choose folder (desktop dialog), the access choice, the folder chip under a team's chat | `settings_view.js`, `chat_view.js` `workdirChip`, `node_panel.js`, `desktop/src/folder.js`, `desktop/src/preload.js` |

## No routing
The first version of this fix sorted the owner's words and sent a project request to a team turn in the folder instead of the engine (a routing module, a runner for queued tasks, a work persona). The owner rejected it: one engine, no rerouting. It was removed. A team's chat, a division's chat, a task from the org chat and a recurring task start the department run of the engine as they did before, whatever the words say. The first two root causes are therefore not closed by D125 alone.

**What follows.** The engine inherits the folder as a capability, so that every agent of every output can read the folder and the builders of a project output can change it within the owner's access setting, and a project is one more output the engine picks. That is designed in `docs/design/agent-sessions-and-engine-capabilities.md` and decided from D126 on.

## Checked
* Python tests: `tests/connectors/test_workdir*.py`, `test_chat_ground.py`; JS tests: `tests/ui/js/settings_workdir.test.js`, `chat_view_workdir.test.js`, `desktop/test/folder.test.js`.
* Not repeated live after the routing was removed: the live checks of the folder with the real CLI belong to the engine capability work (WP12 of the design file).

## Not done
* Codex with "change" was proved against the fake CLI only.
* Running tests or any command other than the four git reads is refused on purpose; the owner runs them.
* Teams do not use the folder yet (see "No routing").


## What the engine does now (D126 to D134)
The team's request always starts a department run of the one engine. Nothing is routed in front of it.
* **Capabilities.** The engine has a capability registry (`engine/capabilities/`). The `workspace` capability gives every agent call of every output the working folder (read; the owner's access setting caps it) and the project's CLAUDE.md. The `project` output (Project work: Findings, Changes, Confirmation, Open items, Outcome) is a normal engine output; builders do the work with tools and Audit checks it in the folder.
* **The engine chooses the output** (`auto`, the default): words about a repository, code or a folder, or a working folder with nothing else said, give project work; a named site or document gives that; a follow-up keeps its output unless the words name a repository. The owner can override in the start page, in Settings, in `engine.json` or per task. The reason is in `output.json` and in the run's chat.
* **Every agent has its own chat session** (a new one per run for the five functions, one per builder), each with its own model and effort (cascade: its own choice, the run, the team, the default), honoured by the engine at the agent's next call through `<run>/choices.json`. The owner can steer an agent from its chat; its live work streams there.
* **Checked live** (real Claude, a copy of the owner's data folder, a scratch clone of the J2 prototype): the sentence that started a website intake now starts a project run (output `project`, Identity does not ask about a website, five sections written, Audit checks the report against the folder); a v3 data folder migrated to v4; picking haiku/low for Identity made its next call `claude-haiku-5-5`.
