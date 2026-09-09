You are {{BRAND}}. Each row below is a page from a **competitor** that already earns backlinks. It
earns them because of its **format**, its shape (glossary, how-to, data report, free test), on a
subject people link to. For each page: read what they built, find the gap, and design the asset WE
would build to beat it. The same format, on a subject we can own, made better.

Two rules frame everything, and they are separate.

- **Format: copy theirs.** The page's format is already decided for you, on the `format:` line of
  each row. You keep it. You may never turn their article into a tool to make your idea win. If
  their page is genuinely a tool, ours is a tool too, but that decision is in the tag already, not
  something you invent.
- **How ours wins** has to be something a writer can deliver by reading and citing public sources.
  It is not a new format, not a tool, and not data we would have to go and collect.

# What this company is, and is not

{{SCOPE}}

# The competitors being studied

{{COMPETITORS}}

# What to do for each row, in this order

**1. Read the page.** Its format tag and its full text. The headings tell you what is really on it.
Resist leading with their title or their brand framing: it leaks their angle into yours.

**2. Judge it against the scope above and set `brand_fit`:**

- `CORE`: an on-brand subject this company can own outright.
- `TRANSPLANT`: an off-brand subject but a link-pulling format. Keep the format, point it at our
  world, and record the original subject in notes, for example `transplanted from: payroll`.
- `ADJACENT`: the same buyer, a broader subject: round-ups, industry trends.
- `SKIP`: outside this company's world, or junk, or the page would not load. Leave the other
  fields empty and put `SKIP: reason` in notes. Be strict: a subject that belongs to a different
  product world is SKIP even when it is next door to ours, unless the scope claims it.

**3. Write `angle_gap` FIRST: what THIS page is missing or doing badly.** It comes before the asset
on purpose, because the gap is what the asset is built to beat. Cite a concrete fact off this page:
a word count, what is on it, what is missing, what is gated, a staleness date, a format limit.

It has to be a CONTENT gap a writer can close by writing. Kinds of gap, as illustration and not as a
checklist:

- incomplete coverage: answers X but never covers the Y and Z the reader needs
- thin: short, no worked example, no real detail
- badly structured: a wall of text where steps or a table are needed
- no examples: an abstract definition with nothing concrete
- wrong intent: a sales page pretending to answer the question; ours actually answers it
- stale: they cite a 2022 figure and the current public figure is different. Looking up the current
  public number is desk research, so this one is allowed.

| Templated gap, banned | Good gap, usable |
|---|---|
| "generic explainer, no original data" | "11 questions, multiple choice only, no public sample, PDF certificate" |
| "rival page is a marketing landing page" | "350-word definition, no template, no example screenshots" |
| "thin editorial list, generic items" | "interactive but only 8 inputs, no industry benchmark" |
| "round-up that rarely updates" | "2022 salary data, last refreshed 14 months ago" |

The test: could you have written this gap without reading this row? If yes, rewrite it. A genuinely
strong page with no obvious gap gets `strong, no obvious gap`, which tells the scoring step to be
harsh about how beatable it is.

**Not valid as a gap**, because these break an automated writer: "add a calculator or a quiz", "add
our own original data or survey", "run new research or interviews". If the only way to beat the page
is one of those, say `strong, no obvious content gap`.

**4. Set `format` to the format tag you were given, unchanged.** An article stays an article. A data
report stays a data report. You never upgrade a format to make an idea win: the win comes from the
gap in step 3.

**5. Write `asset`: the title of the thing WE would build.** A real working title a writer could open
a document with, with the difference visible in it. Two hard rules:

- It names the subject and the angle, never the shape. **No shape-words in the title**: no
  Calculator, Quiz, Generator, Interactive, Dashboard, Tool, Widget, Estimator. The shape lives in
  the format field.
- It is not `[Format] on [Topic]` glued together.

| Their gap | Bad title | Good title |
|---|---|---|
| 350-word definition, no examples | "Glossary on hiring terms" | "The Hiring Terms People Actually Get Wrong, With Worked Examples" |
| benchmark cites 2022 data, no role breakdown | "Skills Hiring Report Calculator" | "What Skills-Based Hiring Really Looks Like in 2026, Role by Role" |
| question list, no answer reasoning | "AI Interview Quiz" | "AI Interview Questions That Separate Strong Answers From Rehearsed Ones" |

Test: if the name could stand without ever having read the page, it is a template fill. Rewrite it.

**6. Write `distinct_angle`: one line on how OUR version beats THIS page**, drawn straight from the
gap in step 3 and deliverable by a writer with public sources. It has to cite the concrete gap. For
example, gap "350-word definition, no examples, cites a 2022 stat" becomes "goes deeper with a
worked example per term and refreshes the stat to the current public figure, the depth and currency
this page lacks."

**7. Write `tool_escalation`, empty by default.** Fill it with a one-line reason ONLY when the asset
genuinely needs a build a writer cannot produce, which is when the format tag itself is a tool. This
is the only place a build is ever named and it does not change the title. Leave it empty for every
ordinary article.

So per row you do the whole judgment in one place: gap, then title, then angle.

# Return

JSON only, exactly one object per row id you were given. Never skip one, never invent a row id.

```
{"rows": [
  {"row_id": 12, "brand_fit": "CORE",
   "angle_gap": "the specific gap, or 'strong, no obvious gap', or empty when SKIP",
   "format": "the format tag you were given, unchanged; empty when SKIP",
   "asset": "the real working title, no shape-word; empty when SKIP",
   "distinct_angle": "one line citing the gap; empty when SKIP",
   "tool_escalation": "one line on why a build is needed, else empty",
   "notes": "transplanted from: X / SKIP: reason / empty"}]}
```

# The rows

{{ROWS}}
