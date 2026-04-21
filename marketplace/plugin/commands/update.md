---
name: update
description: Update the Sutra plugin to the latest version from the marketplace. Shortcut for `claude plugin marketplace update sutra && claude plugin update sutra@sutra`.
disable-model-invocation: true
---

# /sutra:update — Pull the latest Sutra version

!sutra update

## What this does

Refreshes the Sutra marketplace cache, then applies any version bump to the installed plugin. Equivalent to:

```
claude plugin marketplace update sutra
claude plugin update sutra@sutra
```

Most Claude Code sessions auto-update on startup. Run this mid-session if you want the latest without waiting for a restart.
