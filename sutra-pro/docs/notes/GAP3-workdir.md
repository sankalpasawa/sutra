# GAP3-workdir as built: one working folder that chats may read, read-only

Package key `workdir` of the third gap review. Branch `feat/sutra-pro-gap3-workdir`, cut from the merged 0.2.0 line. Nothing is pushed; no
`DECISIONS.md` row is added (the merge step numbers them); the proposed decision text is at the end of this note. No J2 file, prompt, route
or golden is touched, and the engine's department runs are exactly what they were.

The owner said: "The chat is not able to figure out where it needs to look when I am telling it that it is actually in the desktop development
directory ... A setting for directory structure, like how we have in Claude, is not present." and "I don't see a setting of the working directory."

Before this, every chat ran the `claude` or `codex` CLI with its working directory set to a private empty session folder and with no tools
(`tool_profile "none"`), so the model could not see one file of the owner. Now the owner chooses one folder in Settings and a chat can read it.

## What the owner sees

- Settings, under Connectors, a **Working folder** group: a text field (a full path; a leading `~` is the home folder), Save, Clear, one line
  that says what is in use (or that none is set, or that the stored folder cannot be used now and why), and under **What the model can see**
  the top level of the folder: folders first, then files, at most 60 names, with "Showing 60 of 213 entries. The model can see all of them."
  Names only, never a file's contents. A refusal is a red sentence beside the field with the reason.
- The plain words in the group: it is read-only (the model can open and search the files but cannot create, change or delete one or run a
  command); it applies to chats only (the engine's department runs are unchanged); what the model reads goes to your own Claude or Codex like
  any message you type, and Sutra's scrub covers what Sutra sends, not the contents of your files.
- A change applies to the **next message** of any chat, with no restart: the folder is read from its file on every turn.
- With a folder set, a chat knows where to look: its grounding says "Working folder: <path>", that its file tools are read-only and to look
  there first. With none set, the grounding says no folder is set, that the model cannot see the owner's files, and where to set one
  (Settings, Connectors, Working folder), so the question "where do I look" always has an answer.

## Where

| What | File |
|---|---|
| The store, the checks, the preview, the model's words | `sutra_app/connectors/workdir.py` (new) |
| `GET` (open), `PUT` and `DELETE` (token-gated) `/api/connectors/workdir` | `sutra_app/connectors/api.py` |
| The store on the router, one reading per turn | `sutra_app/connectors/factory.py` (`router.folders`), `router.py` (`chat_folder`) |
| The folder as the child's cwd and the read-only tools | `base.py` (`TurnPlan.folder`), `claude.py`, `codex.py` |
| A changed folder starts a new provider session | `router.py` (`_chat_turn`), `base.py` (`_turn`), `models.py` (`SessionState.work_folder`) |
| The grounding | `orchestrator/chat_ground.py` (the words come from `workdir.grounding_text`) |
| The group | `ui/static/js/settings_view.js` (`workdirHtml`, `loadWorkdir`, `saveWorkdir`, `clearWorkdir`), glue in `ui/static/js/home.js`, host `<div id="set-workdir">` in `ui/pages/home.html`, a small block in `ui/static/css/sutra-shell.css` |

### The file and its checks

`<data>/connectors/workdir.json` is `{"version": 1, "path": "<realpath>"}`, written atomically (temp file in the same folder, `oslayer.replace`)
with mode 0600 through the same `write_private_file` the other connector files use. It sits next to `policy.json` and `bins.json`.

`PUT` checks the path when it is written and refuses, with the reason and the usual 422 envelope (`invalid_request`):
not a full path (relative, empty, a control character, over 1024 characters); no such folder; a file; the top of the disk (the filesystem
root, or a drive root on Windows); the app's **data folder or work root, or anything inside them**; a folder this account cannot read. The
path is resolved with `realpath` first, so a link into the data folder is refused after resolving and a link to a folder is stored as the folder
it leads to. A refusal writes nothing and keeps the old choice.

`get()` is what a chat turn reads. It gives the stored folder only while it is still a usable folder; one that has vanished, or that now lies
inside the app's own folders, is ignored (the chat then runs in its private empty folder) and `GET /workdir` still reports the stored path with
`usable: false` and the reason, so Settings can say so.

The preview (`preview_of`) lists top-level names with `os.scandir`, never opens a file, sorts folders first then by name, caps the list at 60
with the total beside it, scans at most 20,000 entries (then says "at least"), skips an entry that cannot be read (a dead link), and replaces
control characters in a name. It is only for the saved folder: there is no route that lists an arbitrary path.

### How a chat turn runs with a folder

`TurnPlan` has a new field `folder`; `workdir` is unchanged (the session's private folder holding `session.json` and `system.txt`), and
`_check_workdir` is not touched, so the integrity check keeps passing. The child's cwd is `plan.folder or plan.workdir`.

- **Claude**: `--tools Read,Glob,Grep,LS` (instead of `--tools ""`), `--restricted --allowedTools Read,Glob,Grep,LS`,
  `--disallowedTools Bash,PowerShell,Edit,MultiEdit,Write,NotebookEdit,WebFetch,WebSearch,Task,Agent,TodoWrite`, `--permission-mode dontAsk
  --permission-prompts none`. `--restricted` also confines the file tools to the working directory. The existing `--strict-mcp-config
  --disable-slash-commands --setting-sources ""` stay. With the MCP `tools` profile as well, the allowed list is the two lists joined.
  `--disallowedTools` is added to `PROBED_FLAGS`.
- **Codex**: `-s read-only -C <folder>` whatever the policy's `sandbox` says (a policy of `workspace-write` is overridden for a folder turn);
  on `exec resume`, which takes no `-s` or `-C`, `-c sandbox_mode="read-only"` and the process cwd.
- Without a folder nothing changes: the argv and the cwd are byte for byte what they were (tests assert it).

Who gets the folder: the **direct chats** (`Router._chat_turn`, every provider attempt) and the **org chat agent** (`Router._json_call` when
the call's function is `chat_agent`; it also gets the grounding text added to its system text). A team's run, J2's engine calls, `ask()` and
`complete()` never read the store.

### A changed folder and resume

Claude stores and resumes a session per working directory, so `--resume <id>` from another folder would fail. `SessionState` gets
`work_folder` (default `""`, so old `session.json` files load): the folder the provider session began in, written after each turn. The Router
resumes only when it equals this turn's folder; otherwise it starts a new provider session with the carry-over it already writes for a switch
or a lost session (`_new_session`), announces `connector.switch` with the reason "working folder changed", and calls the session hook so the
chat row follows the new provider session id. The chat's transcript is the app's own and is never touched. The connector base also refuses to
resume into another folder when it is used directly. Tested: no folder, then folder A (new), A again (resumed), folder B (new), cleared (new),
for Claude and for Codex.

## Tests

- `tests/connectors/test_workdir.py` (47): validation, the private file, a change seen by the next read, a vanished folder, a corrupt file, the
  preview (order, 60 cap and total, no contents, dead links, control characters), the model's words, and the three routes (token, 422 with
  the reason, preview in the answer, `chat_folder` follows).
- `tests/connectors/test_workdir_chat.py` (15): the argv and cwd for both CLIs with the folder and without (fake CLIs, no network), the
  session files staying private, resume after a folder change (and the mutation check: with the new rule removed four of these fail), the
  org agent's call versus a team's and the engine's, offline.
- `tests/orchestrator/test_chat_ground.py` (+7): the folder paragraph and the no-folder sentence, order before the rules, never pushed out
  by a long record, a failing source, scrub of the path, and the direct route writing it into the session's system text.
- `tests/ui/js/settings_workdir.test.js` (14): the group, the words, escaping, the three flows.
- `tests/ui/test_home.py` (browser, `SUTRA_BROWSER=1`): the real `home.js` in headless Chrome saves, shows a refusal, lists and clears. The
  fake backend (`tests/ui/fake_backend.py`) serves the three routes. Existing assertions changed for new routes and a new field:
  `test_api.py` (9 write routes and 7 read routes now), `test_models.py` (the design example gains `work_folder`), `test_fake_backend.py`
  (the write list), `SKELETON_IDS`.

## One real Claude call

Through the real `ClaudeConnector` (claude 2.1.308, signed in), a temporary folder holding `notes.txt` ("The project's secret word is
zorblax-7431-quince.") and an empty `src/`, the grounding text as the system text, the folder as the turn's folder. The prompt asked for the word
and then asked the model to try to create `written.txt` there.

- The CLI's init event listed its tools as `Glob`, `Grep`, `Read` and nothing else: no write tool, no shell. (This CLI has no `LS` tool, and
  an unknown name in `--tools` is silently ignored, so keeping `LS` in the list is harmless; `Glob` lists a folder.)
- The model called `Read` once with `file_path`, got the file, and answered with the word `zorblax-7431-quince`.
- It did not try to write: from the grounding it said its file tools are read-only. `written.txt` does not exist and the folder is still
  `notes.txt` and `src`. So what is proved is that the model reads the file and that the CLI offers it no tool that could write; the
  denial of a write attempt rests on the tool list (and the `--disallowedTools` and `dontAsk` flags), not on a refused attempt, which one call
  could not also show. Cost 0.016 USD.

## What was not done, and why

- A folder that **contains** the app's data folder is allowed (the spec refuses the data folder and what is inside it, not its parents). The
  home folder, for instance, contains the data folder on a Mac, and a chat could then read it with the read tools. The preview shows what is
  in the folder, and the owner chose it; a deny rule on the data folder's path (`Read(<data>/**)`) is the follow-up, not added because the rule
  syntax for absolute paths could not be proved with the one call allowed.
- **Claude reads the folder's own `CLAUDE.md`** (and a parent's) as it does in the terminal; `--setting-sources ""` only drops settings files.
  That is what "like in Claude" means, and the file is the owner's, but it is text from the folder that shapes the model: said here, not hidden.
- The org chat agent's path (a one-shot call with `--json-schema` and the read tools together) was proved by its argv and cwd with the fake
  CLI, not by a real call: the one real call went through the direct-chat path.
- Codex has its own file tools inside a read-only sandbox; its reads were not exercised with a real call (only its argv and cwd, with the
  fake). The grounding names no tool, so it is true for both.
- No line in `docs/TROUBLESHOOTING.md` or `GETTING-STARTED.md`: the checker (GAP-DOCS) owns their structure (one entry per failure code and per
  doctor check), so "the chat cannot see my files: set a Working folder in Settings, Connectors" is a line for the merge step to place.
- No path picker (a browse button): the page has a text field, as the CLI-file box does. A native dialog is a desktop-shell change.
- The forgotten Claude session of the old folder is not purged (`claude purge`), as it is not on a lost session; it is the CLI's own cache.
- The org chat agent's one-shot JSON calls with tools may take longer than its 120 s call timeout when the model reads many files; the
  timeout is unchanged.
- The browser tests of the Settings page fail at baseline on the fake's missing `/api/notes` route (every one of them; with the base commit
  too). The new browser test announces that failure like the existing ones announce theirs; the route is not added here.

## Proposed decision text

## D12x — One working folder that chats may read, read-only; the engine's runs are unchanged
- Sources: owner: "The chat is not able to figure out where it needs to look ... A setting for directory structure, like how we have in Claude, is not present." and "I don't see a setting of the working directory."; D34 (the app installs nothing and never runs the owner's shell); the egress design (the scrub covers what Sutra sends).
- Decided: Settings, Connectors has a Working folder: ONE folder, stored in `<data>/connectors/workdir.json` (0600, atomic) and read on every chat turn. It is checked when written (a full path, `~` expanded, an existing readable folder, resolved with realpath; never the disk root, the app's data folder or work root, or anything inside them). A direct chat turn and the org chat agent's call then run the CLI with that folder as the child's working directory and file tools that only read (Claude: Read, Glob, Grep and LS, everything that writes, runs a command or reaches the network denied by name, `--restricted`; Codex: a read-only sandbox, whatever the policy says). The session's own state stays in its private folder (`TurnPlan.folder` is separate from `workdir`). A provider session belongs to the folder it began in: another folder starts a new one with the carry-over, and the transcript is untouched. The chat grounding states the folder and that the tools are read-only, or that none is set and where to set one. A team's run and J2's engine calls never get the folder.
- Why: a chat that cannot see the owner's files cannot answer the one question the owner asks first; one folder, read-only, chosen by the owner, shown as the names the model will see, is the smallest thing that answers it. The file contents the model reads go to the owner's own CLI like any prompt, and the setting says so.
- Rejected: a folder per chat or per team (the owner asked for one setting, and a per-team folder invites the engine's runs into it); write tools or a shell (a chat is for reading; a write needs the owner's own review path); letting the model pick any folder; resuming a provider session into another folder (Claude would not find it); an environment variable (an app opened from Finder cannot be given one).
- Diagram: key label "chats read one folder, read-only", pill on the Chat connector box.
