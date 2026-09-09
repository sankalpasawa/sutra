# comparison-rankings

Two consumers. The **Structure** section becomes `{{FORMAT_STRUCTURE}}` in the architect's shape
step. The **The rewrite** section at the foot becomes `{{FORMAT_RULE}}` in the readability rewrite.
Rules about the intro, the close and the FAQ live in `_craft/comparison-rankings.md` and are NOT injected here.

## Structure (verdict-first)
- [ ] **Criteria / methodology block before the picks:** the dimensions scored, whether tested hands-on, how many options considered, the inclusion criteria.
- [ ] **At-a-glance comparison table immediately after the intro**, before the deep dives.
- [ ] **The table carries ONE ROW PER OPTION — every option, no exceptions.** If the publisher's own
      product is one of the options, it is scored in the grid like the rest. Any count stated in a
      heading or in the prose ("all 12 platforms") must equal the number of rows actually there.
- [ ] **Per-option deep dives** — one identical block per option (~200-300 words each).
- [ ] **"Best for X" constraint verdicts** (use-case-segmented, not one blanket winner).
- [ ] Supporting blocks (buying guide, definitions, data) below the items; close with "pick A if…, pick B if…".
- [ ] Number item headings; carry ≥8 items only where the category honestly supports it.
- [ ] **"A vs B" branch = its own fixed sequence:** what is A → what is B → differences → similarities → head-to-head → pros/cons A → pros/cons B → verdict by use case → FAQ.

## The rewrite

Injected into the readability rewrite (`readable.py`) as `{{FORMAT_RULE}}`.

THIS IS A RANKING. THE PER-OPTION DEEP DIVES ARE THE ARTICLE.

The general permission to merge, reorder and delete sections does NOT apply to the options. It
applies to everything around them. Never merge two options, never collapse them into one table of
rows, never drop one to save words. The at-a-glance table stays.

THE SHAPE OF ONE DEEP DIVE, and every option gets the same one:
  · One or two short paragraphs of prose: what the tool is, and how it handles the ONE dimension
    this article scores on. Every option covers that dimension — an option whose paragraphs drift
    to pricing or company history while saying nothing about the scored dimension has not been
    written. Where the material genuinely lacks it, say so in ONE plain sentence and move on.
  · Then a short pointer block, dashed, bold lead-ins: "**Best for:** …" plus two or three
    "**Key features:**"-style lines. That pointer block is what makes the page scannable, and it
    breaks the visual monotony of nine identical prose blocks.

THIS IS A BLOG POST, NOT A REPORT. Never write "the findings", "the documentation lists", "the
public record goes quiet", or any sentence that reads as an audit memo. Say what the tool does and
does not do, in plain professional prose, as a person advising a colleague would.

THE PUBLISHER'S OWN PRODUCT, when it is one of the options: cover it factually, state what it does
and who it is for, and never write a limitation line for it. Scope stated plainly is fine; a
drawback written as a drawback is not. Every other option keeps its honest limits.
