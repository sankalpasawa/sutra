# _craft — the per-format wrapper rules

One file per format archetype. They hold the rules for how an article of that format OPENS and
CLOSES: the intro, the TL;DR, the close and takeaways, the FAQ. The files in the parent `formats/`
folder are about the BODY (which sections, in what order, carrying what evidence) and go to the
architect. These go to the wrapper step.

## Status in Sutra: PRESENT BUT NOT YET READ

The owner wired these into his own `wrapper.py` on 2026-09-05, injecting `_craft/<archetype>.md`
into `prompts/wrapper.md` as a FORMAT_CRAFT placeholder. Before that date every article got the same wrap
whatever its format, which is what the review round flagged: same shape on every article.

Sutra's `seo_agent/write/wrapper.py` does not pass an archetype and does not fill that token yet,
so `prompts/wrapper.md` deliberately carries no FORMAT_CRAFT or ARCHETYPE placeholder. Adding
the token without the fill would ship an unfilled placeholder to the model, which
`tests/test_write.py` refuses. These files were brought across on 2026-09-09 so the content is not
lost a second time; wiring them is a two-line change in `wrapper.py` plus the matching block in
`wrapper.md`, and it belongs to whoever owns that file.

## The fixed headings

Every file uses the same four, in this order, and says "nothing specific" where a format has no
rule:

1. **Intro** — what the opening must do for this format
2. **TL;DR** — anything format-specific about the takeaway block
3. **Close and takeaways** — how the article ends
4. **FAQ** — anything format-specific about the questions

A file may end with a *Publishing note*. That line is for the publish step, not the wrapper.

## Coverage

Six of the eight archetypes have a file: answer-bait-definitional, comparison-rankings,
data-benchmark-report, glossary, how-to-guide, listicle. `common-spine` and `template-resource`
have none, so a reader of these rules falls back to the general shapes in `wrapper.md`.
