# Coming from the old Sutra app

This page is for someone who used the old Sutra app (the coding-agent panel with Shadow, routines and a file workspace) and now uses Sutra Pro. It says what moved, what Sutra Pro already did differently, what was left behind and why, how to bring old chats over, and what is still to come. The reasoning is in [the absorption design](design/absorb-old-sutra.md) (decisions D105 to D114); what each package built is in `docs/notes/ABS-*.md`.

The J2 prototype idea is unchanged: the engine, its five agents' prompts, its views and its page are the same files, guarded by hash and golden tests. Everything below was added around it.

## What moved into Sutra Pro

| In the old app | In Sutra Pro |
|---|---|
| A chat that keeps its history when the provider changes | The chat record keeps a segment per provider (`chat_segments`); a switch carries the conversation over as deterministic text (no model summary) |
| Picking Claude or Codex for one chat | The provider pill: one choice per chat, stored with the chat, never the global default. It also governs the org chat agent and the J2 run of that team |
| Only runnable providers are offered | Same rule: a provider that cannot run is shown with the reason and cannot be picked; API-key logins are refused |
| Secrets scrubbed from what leaves for a model | Credential shapes are replaced in every chat and org-agent prompt; J2's own prompts are only observed (the audit row is written, the text is not touched). Audit: `<data>/connectors/egress.jsonl`, shape names and counts only |
| Window size per model | A lower-only budget: J2's carry-over caps stay the ceiling for every model; a model with a small window gets less, never more |
| Attachments (images, PDFs, text) | Stored once by hash under `<data>/attachments`; Claude gets images and PDFs, Codex gets images and text; a kind a provider cannot take is refused by name |
| One row for a turn's tool calls | `ChatFold`: "12 tool calls: 8 read, 4 run, 1 failed" that opens into the cards; typed blocks are stored with the message |
| Search across chats | Full-text search over titles and messages, scoped to a node, a team or everything, at most 50 rows; archived chats only on request |
| Archive | A mark, never a delete; archiving frees the node's slot |

## Where it lives in the code

`connectors/chat_port.py` is a sibling of J2's `ModelPort`: J2 keeps its one-shot calls exactly; chat sessions go through `ChatPort`; both end in the same Router, so the scrub, the budget and the choice are written once. Storage is `orchestrator/chat_v2.py` (schema version 2). Routes are in `orchestrator/api/chat_v2.py`; the browser parts are `chat_pill.js`, `chat_fold.js` and `chat_search.js`.

## Bringing your old chats over

Old chats live in `~/.sutra-ui/chats` as one file per chat. Import is explicit, one way and read only on that folder:

```bash
sutra-pro import-old-chats
```

That is a dry run: it prints the number of chats and messages and what would be flattened. To write them:

```bash
sutra-pro stop
sutra-pro import-old-chats --apply
```

`--apply` takes the usual backup first, refuses while Sutra Pro is running on the same data folder, and writes one transaction per chat. A second run adds nothing. Each old chat becomes an archived, read-only chat of kind "legacy": find it under Older chats and in search. Text is kept; tool calls and results become one note per turn (names and counts only); thinking is dropped; credential shapes are scrubbed first. Not imported: archive marks, the providers' own transcripts, the registry of departments (tell the chat agent which teams you want, it builds the chart), settings, agents, drafts and connectors.

## Already done differently in Sutra Pro

Departments and their charter, models, the function screens, the website department, the old engine and the J2 adaptor, the library shelves, goals, the tool surface and proposals, usage windows, Codex sign-in and models, the provider catalogue and process transports: Sutra Pro has one global org chart changed by the chat, five function nodes per department, closed models and one connector router. Nothing was ported from those parts of the old app.

## Left behind, and why

- **Shadow as a second brain** (a supervisor that reads worker chats and delegates): two orchestrators break "talk to one chat". Its useful parts were taken separately (attachments, scrubbing, tool kinds); "needs you" and approvals already exist.
- **Reading another application's login** (the Claude account resolver, usage windows from its token): Sutra never reads or stores either login (D34).
- **Transcript parsers and the all-sessions browser**: Sutra Pro keeps its own transcript.
- **File workspace and git pane**, **Electron shell**, **old test seeding**, **the daemon window**.

## The direct chat's composer

In a team's node panel the box has two modes, "Tell the team" (the team's plain message route, as before) and "Ask the model" (attach files, Send, a Stop button while it answers, the reply streamed under the messages and then stored with its tool calls folded into one row). On Home the same two modes are "Plan with Sutra" (the staged path, the default) and "Ask directly". The model that answers is the one the pill shows (D111). Stop ends a turn that is running; the owner then gets a line in the chat instead of a frozen box (D115).

## Not done yet

- **J2 sync.** The baseline is the prototype's `9200cf6` and the Run settings page is vendored (patch P13, page edits E14 to E18; see `docs/design/j2-sync-2.md` and sync 3). The J2 branch `build-on-run` is a design only and is not vendored.
- **The switch notice** (`ChatPill.switchNotice`) is built and tested but no page shows it: the switch is reported in the turn's result, not as an event the page subscribes to.
- **Search and archive** are on the node panel; Home's org chat has the pill only.
- **Seed templates**: `scripts/audit_old_templates.py` lists what the old seeds have that Sutra Pro lacks and can copy them aside; nothing reads the copies yet.
- **Later, when asked for:** slash-command palette, DeepSeek (needs a decision on API keys, D7), the SEO writer as a template, scheduled routines, modules and apps, an in-app updater, a chat-led import of one project folder.
