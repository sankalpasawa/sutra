---
description: Ask Billu (founder's CLI layer) for a judgment call. Pass the question and any relevant context.
---

You are about to delegate a decision to Billu, the founder's CLI orchestrator.

Run the helper:

    bash .claude/hooks/billu-session-bundle/ask-billu.sh "$ARGUMENTS"

Then STOP and wait. Billu will inject the answer into your next prompt automatically (the UserPromptSubmit hook handles this). Do not act on the question until you see the answer.
