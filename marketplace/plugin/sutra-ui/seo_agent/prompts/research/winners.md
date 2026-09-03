You are writing the "What the winners cover" section of a research doc for a {{BRAND}} article on
{{PRIMARY_KEYWORD}}.

CONTEXT
- Distinct angle (what THIS article covers, to spot the gaps): {{DISTINCT_ANGLE}}
- Standing rules from the user:
{{MEMORY}}

INPUT — headings + word counts from the top ranking pages (JSON: url → {word_count, headings[]}):
{{PARSED_PAGES}}

DO THIS (descriptive, not prescriptive — report what the field DOES, not a must-have list):
- Confirm the dominant format from the real page structure (how-to / listicle / comparison / definitional).
- State depth: the deepest / typical winner word counts.
- Roll up the Common H2s most competitors share (deduped).
- Note where any winner DRIFTS off the article's topic (a pivot into an adjacent audience/topic), if any.
- Name the Gaps we can own — sub-topics thin or missing across winners, judged against the distinct angle
  (this is where the article's angle beats the incumbents).
- If the heading parse is clearly capped (only ~15/page) and misses later sections, note it as a read caveat.

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
- <gap tied to the distinct angle>
- <gap>
- ...

*<one italic line on any read caveat, e.g. heading-parse cap or a page swap; omit if none>*
