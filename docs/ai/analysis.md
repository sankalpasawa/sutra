# Repo analysis (focused on prototypes/, for pulse-gmail-reader)

Repo: github.com/sankalpasawa/sutra, main at eb1fd20 (2026-11-19).

## Layout that matters
- `prototypes/` holds only `j2/`. No naming convention for new prototypes.
- `departments/` is documentation only (`departments/README.md:9`), not runtime code.
- Sutra Pro vendors J2 via `git archive prototypes/j2` with a fixed file list (`sutra-pro/scripts/vendor_j2.py:47-49`). Anything inside `prototypes/j2/` can end up in that copy; a sibling folder does not.
- Creation guard is in hard mode (`.claude/creation-guard-mode` = `hard`; `marketplace/plugin/hooks/creation-guard.sh:50,74`): new files need a CHARTER.md up the tree, or a rule in `.claude/creation-guard-rules.json`.
- Add-department guidance is a preview sketch only (`os/charters/README.md:88-100`).

## Stack
- Python, version not pinned for J2 (`SETUP.md:44`). Sutra Pro needs >= 3.11 (`sutra-pro/pyproject.toml:9`). Target 3.11+.
- J2 deps: 4-line `prototypes/j2/requirements.txt` (anthropic, google-genai, python-docx, pydantic). No pyproject for J2.
- .env loading: stdlib loader, shell vars win (`prototypes/j2/llm.py:21-34`).
- No google-auth, google-api-python-client, python-dotenv, service_account or with_subject anywhere in source.

## Git ignore and tracked data
- Root `.gitignore` does NOT ignore `.env`. Only `prototypes/j2/.gitignore:1-4` does.
- J2 `runs/` is tracked on purpose (`prototypes/j2/.gitignore:12-14`).

## Tests and CI
- J2 tests are plain scripts run directly (e.g. `python template_id_field_test.py`), not pytest. pytest collection fails on them (they run on import).
- 9 GitHub workflows, all path- or tag-scoped; none run on `prototypes/**`.

## Reusable patterns
- Append-only 0600 log writes: `marketplace/plugin/sutra-ui/modules_events.py:54`, `shadow_ledger.py:191` (with file lock).
- Privacy principles: `os/charters/PRIVACY.md:14-23` (minimise, retention, fail closed).
- Secret gate PROTO-004: `os/charters/SECURITY.md:29,62`.
- Lesson: wrong Gmail account read for 2+ hours (`marketplace/feedback-inbox/0039-*.md`).
- Gmail via MCP connectors exists (`marketplace/plugin/sutra-ui/mediated_connectors.py:81`), different auth model, not reusable.

## J2 context entry points (for later; owner approval needed)
- `j2.py:4635` first user message becomes `self.request`
- `j2.py:4064` `state()`, `requester_brief` at `:4077`, Identity's reduced view `:4067`
- `j2.py:4133` `context()`, prepended in `call()` at `:4191`
- Flags read inline: `os.environ.get("J2_...")` (`j2.py:478,485,3121`)

## Ownership
No CODEOWNERS. Recent J2 authors: Disha (96 commits), Kaivan Shah (87). Approval-gated: j2.py, llm.py, j2_types.py, artifacts/types.json, conditions/, agents/j2/*.md.

## Unverified
- `bundle-runtime*.sh` not read in full (packaging likely ignores prototypes/).
- Deleted gmail-direct adapter commit `96edce8` (ADR-034:5) is not in the shallow clone.
