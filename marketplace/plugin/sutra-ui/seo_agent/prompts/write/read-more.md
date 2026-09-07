You are deciding whether this article gets a "read more" pointer — a single added line inviting
the reader to a {{BRAND}} page that CONTINUES what this article started: a full, in-depth
treatment of a sub-topic this article could only cover in part. This is a stronger test than an
inline link: the target page must BUILD ON what the reader has just learned here, not merely
relate to it. The reader should finish that page knowing meaningfully more about the sub-topic
than this article alone could teach them.

THE ARTICLE, in full:

{{ARTICLE}}

THE CANDIDATE PAGES — found by meaning-similarity against {{BRAND}}'s whole site; these are the
only options. Each comes WITH ITS ACTUAL OPENING TEXT, so judge the page's real depth — a thin stub
does not qualify however good its title sounds:

{{CANDIDATES}}

────────────────────────────────────────────────────────────────────────
THE RULES:
- ONE pointer is the normal outcome. Two is the maximum. Zero is right only when the candidates
  genuinely offer nothing deeper than what this article already says.
  This is the ONLY step that may add a sentence, so it is the only way a reader ever learns that a
  full treatment exists — a calculator, a template, a complete guide — when the article never
  happens to use the words that would let a link sit over existing text. If a candidate genuinely
  continues this article, add the line. Do not hold back to seem disciplined.
- The pointer is ONE line — a natural sentence in the article's voice, any phrasing that fits
  ("We've broken down X in full here", "For a deeper look at X, see our guide", or better),
  ending with the link. Never more than one line. No heading, no box, no second sentence.
- Write the line with the link as markdown: the anchor words inside [.…](url).
- Place it where the sub-topic lives: name the section it should follow.
- SMOOTHING IS ALLOWED, SPARINGLY: if the line lands awkwardly between two existing sentences,
  you may slightly adjust the sentence immediately before and/or after it so the pointer reads as
  part of the flow. Report every such adjustment verbatim (the exact old sentence and the exact
  new one) — code applies and audits them, and an unreported change is thrown away. The
  adjustments must not touch any number, fact, or [c…] tag.
- The pointer line itself must contain NO factual claim and NO number — it is navigation, not
  content.
- The line is written in clean house style: NO em dashes (— or --), no "dive into", no "check out",
  no exclamation mark. A plain comma or a full stop does the job. This line is added AFTER the
  style-cleaning pass, so nothing downstream will fix it for you — it ships exactly as you write it.

════════════════════════════════════════════════════════════════════════
THE USER'S STANDING RULES. They were set by the person publishing this and they win over any
rule above that they contradict. "(none)" means there are none.
{{MEMORY}}

Return ONLY this JSON, nothing else:
{"pointers": [{"after_section": "<heading of the section the line follows>",
               "line": "<the one line, with [anchor](url) inside it>",
               "url": "<the target url>",
               "why": "<one line: what the reader learns there that this article could not teach>",
               "adjust_before": {"old": "<exact sentence>", "new": "<exact sentence>"} | null,
               "adjust_after":  {"old": "<exact sentence>", "new": "<exact sentence>"} | null}],
 "rejected": [{"url": "<candidate>", "why": "<one line — related is not enough; say what depth it lacks>"}]}
(pointers is [] only when nothing genuinely deepens the article — not the usual answer)
