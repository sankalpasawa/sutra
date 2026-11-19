# Sutra Pulse Charter

## Purpose
Read selected mailboxes in the company Google Workspace domain, read-only, so internal tools can work from
mail that the mailbox owner has agreed to share. Step 1 is a command-line reader with a mock mode; nothing
else consumes its output yet.

## Scope
- Service account with domain-wide delegation, OAuth scope `https://www.googleapis.com/auth/gmail.readonly` only.
- Commands: `check`, `fetch`, `find`, `purge` (see README.md).
- Only mailboxes in the configured domain and in the allowlist file are opened. Every read needs a stated reason.

## Non-goals
- Writing to Gmail (send, label, delete, mark read) or any other OAuth scope.
- Downloading attachment contents.
- OAuth user consent flow, CI workflow, J2 integration, Windows support.

## Data handled
| Data | When | Notes |
|---|---|---|
| Message metadata: ids, from, to, cc, date, subject, snippet, labels, attachment name/type/size | Every `fetch` / `find` | Subject and snippet are mail content; kept by decision DEC-2, revisit before J2 integration |
| Message body text | Only with `--full` | Capped at 20,000 characters |
| Attachment contents | Never | - |
| Audit row per run | Every run that reaches the audit step | Never holds mail fields, key contents or tokens |

Output lives outside the repo (`~/.sutra-pulse/` by default), files 0600, folders 0700.

## Retention
| Data | Kept | Enforced by |
|---|---|---|
| Mail output (`*.jsonl`) | 30 days by default (`PULSE_RETENTION_DAYS`) | `purge`, also run inside `fetch` and `find` |
| Audit log | 365 days (DEC-1) | Policy only in step 1; enforcement is a follow-up |

## Access rule (DEC-3)
The Workspace admin approves every allowlist entry, and each mailbox owner is told in writing before the
first read. This is a written rule; the tool does not enforce it.

## People (DEC-4)
| Role | Who |
|---|---|
| Owner | Kaivan Shah |
| Approver | The Workspace admin |

## Rulings
| Date | Ruling | By |
|---|---|---|
| 2026-11-19 | Q-6: `.gitignore` and `.env.example` in `prototypes/pulse/` are approved as config files for this folder. They are created normally; the creation-guard kill-switch is not used | Kaivan Shah (owner) |
