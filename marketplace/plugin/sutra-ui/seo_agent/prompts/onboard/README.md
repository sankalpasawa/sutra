# prompts/onboard — the setup interview, one file per question

One question per file, never inline in a .py. `tools/onboard.py` owns the order and where each
answer is filed; these files own the wording.

The format is three blocks, each opened by its name alone on a line:

    QUESTION      what the user is asked, in the chat. One line.
    WHY           why it matters, and what happens if they skip. One or two lines.
    HEADING       the heading the answer is filed under in its brand file.

`{{BRAND}}` is filled from the company record before the question is asked.

The wording is ported from the original workflow's own "ask the team" sections, so a question
here should read like the seed it came from:

| File | Ported from |
|---|---|
| `numbers.md`        | `0-brand-facts/templates/stats.md`, "Seeds to mine (ask the team)" |
| `origin-story.md`   | `0-brand-facts/templates/stories.md`, "The interview", origin story |
| `lesson-learned.md` | `0-brand-facts/templates/stories.md`, "The interview", a lesson learned |
| `byline.md`         | `6-voices/voices.workflow.md`, Step 1, the default company byline |
| `founder-voice.md`  | `6-voices/voices.workflow.md`, Step 2, the founder / leadership voice |
| `competitors.md`    | `02-asset-engine/1-competitor-study`, Step A4, the user's sign-off |
