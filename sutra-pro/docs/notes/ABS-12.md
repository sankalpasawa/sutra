# ABS-12 as built

`ops/import_old.py`, registered as the command `sutra-pro import-old-chats [--source DIR] [--apply]` (`ops/cli.OPTIONAL_MODULES` gained `import_old`; `docs/OPERATIONS.md` documents it because `scripts/check_docs.py` requires every command and flag to be written down; `__main__.py` needed no change).
Dry run by default (counts, what is flattened, what is not imported). `--apply`: instance lock must be free, backup first when a database exists, one transaction per chat, idempotent by `src_ref` (`old:<id>:<index>`, notes `...:tools`). Mapping as in design section 4. Sessions are created by direct INSERT after `GATE.check("chat_session")` (the chat store has no session creator by design); `chat_search` indexes them through its triggers.
Measured shape of the real old store (structure only, no content read into the repository): 49 chat files plus `_index.json`; every message has `blocks`, today only `text` blocks; ids are 32 hex characters, so `cs_old_<12 hex>` fits `SessionId`.
Tests use fixture trees; a test proves the old folder is byte-identical after `--apply`.
Tool blocks and thinking are handled by the mapping and tested on fixtures; the real store has none of either, so those paths are fixture-proven only.
