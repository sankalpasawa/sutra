# Impact: pulse-gmail-reader

## Task
Sutra Pulse step 1: a read-only Gmail reader for the Workspace domain, using a service account with domain-wide delegation (gmail.readonly only, `with_subject` per mailbox). Credentials come later, so step 1 must work fully in mock mode. Commands: check, fetch, find. Allowlist, required reason, audit log, retry, plain-English errors. J2 integration is NOT in this step.

## Where
New folder `prototypes/pulse/` (sibling of j2). Rejected: `prototypes/j2/pulse/` (would be vendored into Sutra Pro, J2 owners); `departments/pulse/` (documentation only).

## Files touched
| Path | Change |
|---|---|
| `prototypes/pulse/CHARTER.md` | New, first (creation guard is in hard mode) |
| `prototypes/pulse/.gitignore` | New: .env, .env.*, keys, output and audit/state folders |
| `prototypes/pulse/*.py`, `fixtures/`, `README.md`, `requirements.txt` | New |
| Anything in `prototypes/j2/` | None |
| Approval-gated files | None in this step |

## Risks
| Risk | Mitigation |
|---|---|
| Delegation can read every mailbox in the domain; Google does not limit by mailbox | Allowlist plus domain check in code, required reason, audit log, metadata-only default |
| Secrets committed (root .gitignore does not ignore .env) | Pulse's own .gitignore; key file kept outside the repo; never printed |
| Mail content committed (j2 tracks runs/; Pulse must not) | Output and audit outside the repo by default, and ignored if inside |
| Wrong mailbox read (feedback 0039) | `check` prints the profile email and refuses if it differs from the requested one |
| No CI on prototypes/** | Tests are a plain script runnable locally; CI workflow is an open question |
| Fixtures look like secrets (PROTO-004) | Synthetic fixtures only, fake names and +91 00000 numbers |

## Build and test (proposed)
- `cd prototypes/pulse && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- `PULSE_MOCK=1 .venv/bin/python pulse.py check --mailbox <allowlisted> --reason "..."`
- `python3 pulse_test.py` (mock mode imports no Google libraries)

## Open questions
1. google-api-python-client, or google-auth plus plain REST (fewer deps)?
2. Where output and audit live, and retention period.
3. Who approves allowlist entries; written purpose for reading employee mail.
4. CI workflow scoped to `prototypes/pulse/**`?
5. Root `.gitignore` rule for `**/.env`?
