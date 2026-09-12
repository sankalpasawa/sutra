# Apps events, the placement pin, and the done frame

Three contracts that make Apps behave like the rest of Native: every change is an event, a seeded chat files where it was told to, and the screen re-reads the folder when that chat answers.

| Field | Value |
|---|---|
| **status** | ACTIVE — program steps 26, 30, 31 |
| **updated** | 2026-09-11 |
| Log | `~/.sutra-ui/modules/.events.jsonl` (append-only, one JSON object per line) |
| Producers | `modules_api` (create, action, export, import) and the seeded-chat completion hook |

## <a id="events"></a>Events (step 26)

| Event | Producer | Payload (beyond the envelope) |
|---|---|---|
| app.created | `create_module` (chat · Shadow fence · form-less New · disk scan first sight) | `kind`, `department_ref` |
| app.edited | `apply_action` (`rename`, `mark_ready`, `set_instructions`, `restore`) and the seeded Edit chat's `done` | `version`, `changed` (field list, or `files` for a chat edit) |
| app.assigned | `apply_action("assign")` | `from_ref`, `to_ref` |
| app.archived | `apply_action("archive")` | `version` |
| app.exported | export endpoint | `sha256`, `bytes`, `publish.version` |
| app.imported | import endpoint (success) · `failed_verification` on refusal | `sha256`, `registry`, `result` (ok · failed_verification), `reason` |
| app.downgrade_blocked | `modules_pkg.import_app` under the per-id lock, before anything moves: the offered `publish.version` is lower than the installed one and `downgrade=1` was not given with `replace=1` (ADR-041 P2, Publish program ruling P-4); the app.imported refusal row follows | `installed_version`, `offered_version`, `op_id` |
| app.published | (Publish program P3) approval of an `app.publish` proposal ran export, version bump, signing and staged the entry and tarball under `~/.sutra-ui/publish/` | `publish_version`, `key_id`, `registry` |
| app.registry_refreshed | (Publish program P4) one row per `POST /api/modules/registry/refresh`, never per read | `checked`, `updates`, `incompatible` |
| app.kit_adopted | `apply_action("migrate_kit")` or `touch_app(mode="edit")` on an app that carried no framework stamp (D75 amended 2026-09-12: a task brings its framework; the panel adopts before Edit opens the chat, the touch is the fallback for edits that arrive by another client): the stamp is written with an `adopted` date and `APP.md` materializes with `not recorded` answers; a migration of an already-stamped app still appends nothing | `kind`, `version` (unchanged by the adoption), `department_ref`; `actor` is `panel` or `chat:<session_id>` |

Envelope on every event: `{"event", "app_id", "kind", "version", "department_ref", "actor" (app · shadow · chat:<session_id> · marketplace), "ts" (ISO, fixed at creation), "op_id", "key"}`.

| Rule | Detail |
|---|---|
| Idempotency key | `key = sha256(app_id | event | version | actor | ts)`; `ts` is fixed when the event is created, so a retry re-sends the same key (codex pre-consult P7). `op_id` is the caller's operation id when it has one. |
| Write | one `O_APPEND` write of one line; never a read-modify-write of the file (codex P8) |
| Read | corrupt lines are skipped and counted, never fatal (the `json_store` degrade posture) |
| Duplicate keys | the reader de-duplicates by `key`; the writer may append twice under retry |
| Never | no event is emitted by a read; listing the folder emits nothing |

## <a id="pin"></a>The placement pin (step 30)

| Rule | Detail |
|---|---|
| What | a turn may carry `pin: {"department_ref": "<ref>"}` |
| Who sets it | the seeded Edit / New chats (D-M19); the pin mirrors the ROUTING PIN line that is also the visible first line of the seed |
| Server | `/api/classify` with a pin whose ref is LIVE bypasses the classifier, files the placement under that ref with `mode: "pinned"`, still picks the department's charter, and calls `write_placement()` exactly once (codex P9) |
| Today | neither side exists: `runTurn()` posts only `{text}` (`01-state.js:605`) and `ClassifyRequest` has `text` + `session_id` only (`org_api.py:611`); program step 58 adds the optional `pin` to both and step 70 makes the seeded chats send it (codex R1b P4) |
| Not live | a pinned ref that is retired resolves through `live_destination` (successor · ancestor · root); an unknown ref falls back to normal classification and the answer says so |
| Why both | classification runs before the CLI options are sent (`02-helpers.js:502`), so the visible line protects the routing floor and the `pin` protects the server (D-M19) |

## <a id="done"></a>The done frame (step 31)

| Rule | Detail |
|---|---|
| Signal | the chat channel's `f.type === "done"` frame in `claudeChannel()` (`01-state.js:1615`) |
| Condition | the session is app-seeded: `session.app = {id, mode: "edit" | "new", department_ref}` set when Edit / New opened it |
| Action | the hook POSTs `/api/modules/<id>/touch` `{"session_id", "mode"}` — a WRITE endpoint (program step 57) that re-reads the folder, bumps `version` if the files changed, and appends `app.edited` (mode edit) or `app.created` (mode new, when the folder now parses); then the client calls `loadModules(true)`, the forced read that bypasses the query-key cache (D-M21) |
| Never from GET | listing or reading an app appends nothing; the event is written by the touch endpoint only (codex R1b P3) |
| Wiring | `session.app = {id, mode, department_ref}` is set when Edit / New opens the chat (step 70) and read by the `done` handler in `claudeChannel()` (step 72); today that handler refreshes usage and repo state only (codex R1b P5) |
| Not used | the sessions stream's `changed` event (transcript freshness, throttled; codex r2 P5) |

---
provenance: authored 2026-09-11 (session c0a2923c, atom a-c0a2923c-11) from spec §v12 D-M19/D-M21, ADR-039, the codex program review P5 and the codex pre-consult P7-P9; program steps 26, 30, 31.
