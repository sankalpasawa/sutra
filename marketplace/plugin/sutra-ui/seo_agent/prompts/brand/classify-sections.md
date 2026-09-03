You are sorting one brand document into the parts a specific writer can actually use, and the parts it
cannot.

THE COMPANY: {{BRAND}} — {{NICHE}}

## Who the writer is, exactly

An AI writer that produces **ONE SECTION** of a long article. Not the whole article. One section.

**What it writes:** body prose, in paragraphs, under headings that were decided and written before it
started and that it cannot change.

**What it does NOT write:** the headings or sub-headings · the introduction · a TL;DR · key takeaways ·
an FAQ · the conclusion · any call to action · any link or anchor text · any meta title, meta description,
URL slug or alt text · any image, caption, chart or screenshot.

**Where its facts come from:** a fixed set of numbered facts it is handed, each already carrying its
source. It may not bring in a number, a study, a quote or a customer result from anywhere else.

So it writes body sentences, inside headings it did not choose, from facts it did not gather.

## The document

FILE: {{FILENAME}}

```
{{CONTENT}}
```

## What to do

Walk the document top to bottom. Split it at its own headings. For **every section**, answer three
questions. Do not skip a section because it looks unimportant, and do not merge two sections into one.

**QUESTION 1 — `actionable`. Can this writer act on it?**

`true` only when following the rule **changes a sentence of body prose the writer is about to type**.

`false` when the rule is about anything in the "does NOT write" list above, or when it is a checklist, a
maintenance note, a decision someone has to make later, or sales positioning by audience segment.

Be strict. A rule can be excellent and still be `false`. "Use sentence case for H2s" is `false`, because
the headings were written before this writer started and it cannot change them.

**Two traps that catch nearly everyone. Read both before you start.**

**Trap 1 — commercial material is not body prose.** This writer writes editorial body prose. Anything
about buying is `false`: pricing, plans, credits, guarantees, refunds, trial terms, cancellation, "no
contract", handling a purchase objection, or a call to action. That stays `false` however well written it
is and however much it sounds like the brand. A pillar whose whole subject is that the product is cheap
and risk-free to buy is `false`.

**Trap 2 — a sample is only useful if it is the writer's own register.** Brand documents love to quote
real published lines. Judge each set of samples by *where those lines came from*:
- from the middle of an article, teaching or explaining → `true`, keep them
- from a pricing page, a product page, a homepage or a tagline → `false`
- from an article's opening hook, its TL;DR, its FAQ or its closing → `false`
- from a headline or a sub-heading → `false`

If one section holds samples from several places, keep only the body-prose ones in `carry` and say so in
`why`. Do not keep a whole sample block because part of it is right.

**QUESTION 2 — `scope`. Is this true for every company, or only this one?**
- `universal` — any company in any industry would want it. General writing craft.
- `company` — it is this company's own choice, position or vocabulary.

The test: could you hand this line to a shoe company, a bank or a hospital and have it still be right?
If yes, it is `universal`, even when it sits inside a document about this company and quotes this
company's own pages as evidence. **How the document was built does not decide scope. The line does.**

`universal` includes, always:
- how long a sentence runs, how many sentences make a paragraph, how ideas split across paragraphs
- when something becomes a list and how a list is built
- active voice, plain words, cutting filler, varying sentence shape
- number formatting, punctuation, capitalisation conventions, date formats
- honesty rules: don't overpromise, don't hype, don't invent, make your numbers reconcile

`company` is narrower than it looks. It is really only four things:
- what this company believes and refuses to say (its positions, its legal lines)
- its own vocabulary and house spelling
- who signs the writing and in which person
- who its competitors are and how they may be treated

**QUESTION 3 — `kind`. What sort of thing is it?**
- `rule` — an instruction about how to write
- `fact` — a number, a statistic, a customer story, a named result, a claim about the real world
- `reference` — a long lookup list a human consults, not something a writer applies while writing

## Also return, for each section

- `heading` — the section's own heading, verbatim
- `summary` — one short line: what this section says
- `why` — one short line: why you answered Question 1 the way you did
- `carry` — **the actual lines to keep**, rewritten tight but never invented. Include every concrete item:
  every word pair, every banned phrase, every spelling, every named list. If a section is a table of 23
  terms, `carry` holds all 23. Set `carry` to "" when `actionable` is false, or when `kind` is `fact` or
  `reference`.

Keep `carry` faithful. You are moving text, not writing new text. Where a section states a test or a check
in its own words ("could a lawyer sign off on this sentence?"), keep those words.

## Return ONLY this JSON

{"file": "{{FILENAME}}",
 "sections": [
   {"heading": "<verbatim>",
    "summary": "<one line>",
    "actionable": true|false,
    "scope": "universal|company",
    "kind": "rule|fact|reference",
    "why": "<one line>",
    "carry": "<the lines to keep, or \"\">"}]}
