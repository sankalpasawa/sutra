# House decisions — [Company]

Decisions a human made that **cannot be worked out from the source files**. These outrank everything.

Keep this short. Where two source files simply disagree with each other, the build resolves it on its own
using the rules in `prompts/assemble-brief.md`. A row belongs here only when the answer is a **choice
somebody made**, not a conflict somebody could read off the page.

Copy this file to `projects/[company]/01-brand-context/writer-brief-rulings.md` and fill it in. It is
optional: with no file there, the build resolves everything itself.

| # | Decision | Why it is not derivable |
|---|---|---|
| 1 | [the decision, stated as an instruction] | [what the source files say, and why choosing between them is a judgment rather than a reading] |

## What tends to need a row

- **The byline**, when the voices file offers several and the company has settled on one.
- **A term with an exception**, when the company would rather lose the exception than keep the ambiguity.
- **A position the company has changed** since the source documents were written.
