You are writing the "What the winners cover" section of a research doc for a {{BRAND}} article on
{{PRIMARY_KEYWORD}}.

CONTEXT
- Distinct angle (what THIS article covers): {{DISTINCT_ANGLE}}
- Standing rules from the user:
{{MEMORY}}

INPUT — headings + word counts from the top ranking pages (JSON: url → {word_count, headings[]}):
{{PARSED_PAGES}}

WHAT PEOPLE SEARCHING THIS ACTUALLY ASK — the People Also Ask questions Google shows for this
keyword. These are real questions from real people, not our idea of what they want:
{{PAA}}

DO THIS (descriptive, not prescriptive — report what the field DOES, not a must-have list):
- Confirm the dominant format from the real page structure (how-to / listicle / comparison / definitional).
- State depth: the deepest / typical winner word counts.
- Roll up the Common H2s most competitors share (deduped).
  LIST THEM IN THE ORDER THE PAGES THEMSELVES USE, not by how many pages share them. A reader who
  arrives from this search has read pages built in that order, so it is the order they expect: the
  thing almost every page opens with goes first. A later step reorders the article's own sections
  against this list, so an order invented here becomes an order invented there.
- Note where any winner DRIFTS off the article's topic (a pivot into an adjacent audience/topic), if any.
- Name the Gaps we can own, under the rules below.
- If the heading parse is clearly capped (only ~15/page) and misses later sections, note it as a read caveat.

════════════════════════════════════════════════════════════════════════════════════════════════
THE GAPS. READ ALL OF THIS BEFORE YOU WRITE ONE.

A GAP IS SOMETHING READERS WANT THAT NOBODY ANSWERS. It is not "anything the winners left out".
Most of what the winners left out was left out because nobody wanted it.

So the test has two halves and BOTH must hold:
  1. no ranking page covers it properly, AND
  2. you can point at a reason to believe a reader of THIS keyword wants it — a People Also Ask
     question above, a question the pages keep half-answering, something the format obviously
     needs and none of them do.

If you cannot say who wants it and why, it is not a gap. It is just absent. Say nothing about it.

DO NOT JUDGE GAPS AGAINST OUR ANGLE. An earlier version of this prompt asked for gaps "judged
against the distinct angle", and the result was the same gap on every article: our own angle
handed back to us as an opportunity, because the angle is what it was measured against. On one
article that produced two whole sections on a compliance rule nobody searching the keyword had
asked about, while two topics every ranking page covered were dropped. The angle is above for
context only. The gap comes from the reader, not from us.

THE LIMITS, and they are hard:
- AT MOST THREE. Usually fewer. Often none, and none is a perfectly good answer.
- AT MOST FIFTEEN WORDS EACH. A gap you cannot say in fifteen words is a different article.
- PLAIN ENGLISH, the way you would say it to a colleague. "Nobody shows the actual sum", not
  "no defensible compliance calculation is present across the corpus".
- ALL OF THEM POINT THE SAME WAY. If you name three, they must be three parts of one direction,
  not three directions. Three gaps pulling three ways is how an article ends up arguing three
  things at once and landing none of them. Where they genuinely disagree, keep the strongest and
  drop the rest.
- NEVER INVENT ONE TO FILL THE SECTION. An empty gap list is a real finding: it means this is a
  well-served keyword and the article has to win on quality rather than on novelty.

RETURN markdown, factual, no fluff, ONE item per line, in EXACTLY this shape:
### What the winners cover — {{PRIMARY_KEYWORD}}

**Confirmed format:**
- <format> with <one clause on the intro/shape>; deep — <site ~Nk words, ...>

**Common H2s (most competitors have):**
- <subtopic>
- <subtopic>
- ...

**Where the winners drift:**
- <one line, or "none">

**Gaps we can own:**
- <the gap in 15 words or fewer> — wanted because: <the PAA question or evidence that someone asks for it>
- ...
(or the single line "- none" when no gap passes both halves of the test)

*<one italic line on any read caveat, e.g. heading-parse cap or a page swap; omit if none>*
