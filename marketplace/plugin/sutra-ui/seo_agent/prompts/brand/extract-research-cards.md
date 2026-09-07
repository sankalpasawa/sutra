You are turning a company's own research study into individual citable findings.

THE COMPANY: {{BRAND}} — {{NICHE}}

## What a finding is

One fact a writer could put in a sentence, with its number and its base attached. Not a table. Not a
summary of a table. One fact.

Good: *"44.5% of HR and TA practitioners say no one formally validates their assessments — the team goes
on gut feel (n=128)."*

Bad: *"Question 9 asked who is responsible for validating assessments."* That describes the question
instead of stating the finding.

## The study

{{STUDY_HEADER}}

## The part you are working on

{{CONTENT}}

## Which rows become findings

**Keep a row when the number itself is the point.** A share that is surprisingly high, surprisingly low,
the top answer, or one that contradicts what people assume. A row that would make a reader stop.

**Skip a row when the number is only there to make the column add up.** An option nobody picked. A
middle-of-the-pack answer that says nothing on its own. "Other". "I don't know". "None of the above",
unless the fact that so many chose it IS the story.

**Combine rows into one finding when they only mean something together.** "78.7% take four days or more"
is worth more than three separate rows. When you do this, say in the verbatim which options you added up,
so anyone can check the arithmetic.

Expect roughly two to four findings from a section of this study. Some sections deserve one. If a section
has nothing worth a sentence, return nothing for it.

## For each finding, return

- `gloss` — one short line naming the finding. This is what a planner reads when deciding where it goes.
- `verbatim` — the full statement, exactly as a writer could use it. It MUST contain:
  · the number, as it appears in the source
  · who was asked, in plain words
  · the base, written as `(n=NNN)`
  · the question number in brackets at the end, like `[Q9]`
  If you combined rows, name which ones you added.
- `topics` — three to six lowercase words or short phrases naming what this finding is ABOUT, so a
  planner can match it to a section later. Subject matter, not question wording.

## Hard rules

- **Never change a number.** Copy it exactly, decimal point and all.
- **Never invent a base.** Every finding carries the `n` its own question carried.
- **A percentage from a multi-select question is not "X% of people chose only this".** Say "named this"
  or "selected this", so the sentence stays true.
- **Open-text questions give participant COUNTS, not percentages.** Write "roughly 23 of ~119 said…" and
  never convert a count into a share.
- **Never editorialise.** State what the number says. Do not add what it means; the writer does that.

## Return ONLY this JSON

{"findings": [
  {"gloss": "<one short line>",
   "verbatim": "<the full statement, with number, who, (n=NNN) and [Qn]>",
   "topics": ["<word>", "<word>", "<word>"]}]}

An empty array is a valid answer for a section that carries nothing worth a sentence.
