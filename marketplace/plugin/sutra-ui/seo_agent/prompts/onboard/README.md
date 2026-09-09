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
| `competitors.md`    | `02-asset-engine/1-competitor-study`, Step A4, the user's sign-off |

`byline.md` and `founder-voice.md` were here, ported from `6-voices/voices.workflow.md`. Deleted
2026-09-09 with the rest of the byline feature, on the owner's word: "remove completely everything
about the byline questions, everything from Sutra for now." There is nowhere for those answers to
go any more.
