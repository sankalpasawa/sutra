---
name: company
description: "Start a session for any Sutra-installed company. Usage: /company <company-name>"
argument-hint: "<company-name>"
disable-model-invocation: true
---

# /company — Start a company-scoped session

Sutra treats each company as a physically-isolated folder with its own `.claude/`, its own hooks, and its own governance state. A company session runs FROM that folder, not from a parent directory.

## Actions

Tell the user:

```
Company sessions run from their own directory for isolation.

To start a {company-name} session:

  1. Open a new terminal
  2. cd {company-name}/
  3. Start Claude Code there

This gives {company-name} its own .claude/settings.json, its own hooks,
and physically cannot access other companies' files or shared governance.
```

Do NOT set an active-role file.
Do NOT load the company's files from the current directory.
**Company sessions don't run here.**

## If the user insists on working from the current directory

Say:

```
You have full access here. For isolated company work, open the submodule
directory in a new Claude Code session. For cross-company coordination
(e.g., updating the portfolio registry), working from the parent is fine.
```

Then proceed with their request.
