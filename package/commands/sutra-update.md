---
name: sutra-update
description: Update Sutra OS in this folder to the latest version from github.com/sankalpasawa/sutra-os. Preserves your content; refreshes Sutra-managed files (hooks, OS docs, settings wiring).
disable-model-invocation: true
---

# /sutra-update

Tell the user "Pulling latest Sutra OS…" then run:

```!
npx -y github:sankalpasawa/sutra-os init 2>&1 | tail -20
```

After the installer completes, show the new version pin:

```!
cat .claude/sutra-version 2>/dev/null | head -1
```

Then say:

```
✓ Sutra updated.

To load the new hooks, restart Claude Code in this folder:
  (exit Claude Code, then run `claude` again)

If any files were skipped or blocked by the installer, they'll appear above.
Nothing in your own content was touched.
```

If the installer errored, surface the error + suggest:
- Check internet connection
- Verify Node.js is installed (`node -v`)
- Report the error at https://github.com/sankalpasawa/sutra-os/issues
