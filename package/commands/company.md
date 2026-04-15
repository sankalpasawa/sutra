---
name: company
description: "CEO of {Company} — Start a session for any Sutra client company"
argument-hint: "<company-name>"
---

# STOP — Wrong Directory

Company sessions **must** run from the submodule directory, not from `asawa-holding/`.

Physical isolation — the session literally cannot see other companies' files.

## What to do

Tell the user:

```
Company sessions run from their own directory for isolation.

To start a {company-name} session:

  1. Open a new terminal
  2. cd {company-name}/
  3. Start Claude Code there

This gives {company-name} its own .claude/settings.json, its own hooks,
and physically cannot access other companies, Sutra source, or holding docs.

You're currently in asawa-holding/ (the CEO of Asawa workspace).
To work on {company-name} from here with full access, just say so —
but for isolated company work, use the submodule directory.
```

Do NOT set an active-role file. Do NOT load company files from the holding root.
**Company sessions don't run here.**

## If the user insists on working from holding root

They're CEO of Asawa — they have full access. Load the company files as CEO of Asawa (no role file needed).
