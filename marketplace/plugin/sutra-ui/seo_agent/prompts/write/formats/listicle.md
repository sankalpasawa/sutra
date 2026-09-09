# listicle

Two consumers. The **Structure** section below becomes `{{FORMAT_STRUCTURE}}` in the architect's shape
step. The **The rewrite** section at the foot becomes `{{FORMAT_RULE}}` in the readability rewrite.
Rules about the intro, the close and the FAQ live in `_craft/listicle.md` and are NOT injected here.

## Structure (the format's signature)
- [ ] **Body = the N parallel items** (80%+ of the article), **kept flat — no nested sub-lists inside items.**
- [ ] All supporting blocks (definitions, buying guide, pros/cons, data) go **below the items**, never in front.

## The rewrite

Injected into the readability rewrite (`readable.py`) as `{{FORMAT_RULE}}`. Only formats that need a
rule for that step carry this section; the rest inject nothing and the rewrite gets the format's name
and no more.

THIS IS A LIST ARTICLE. THE ITEMS ARE THE ARTICLE.

The general permission to merge, reorder and delete sections does NOT apply to the items. It applies
to everything around them.

You MAY:
  · shorten any item, hard — this is where the words come from
  · turn an item's supporting detail into a table or a list
  · cut an item's weakest lines, and any figure the item does not lean on
  · merge, reorder or delete the SUPPORTING sections (the explainer, the how-we-chose, the what-next)

You MAY NOT:
  · merge two items into each other
  · collapse the items into one table of rows
  · drop an item to save words

Every item keeps its own heading. If the headline promises a count, hand back that many items. Twelve
short items is right; eight good ones and a table is not, however much better it reads.

THE SHAPE OF ONE ITEM, and every item gets the same one:
  · One or two short paragraphs of prose: what the thing is, and how it handles the ONE dimension
    this article ranks on. Plain, easy language — a listicle is read faster and less formally than
    an explainer, though the register stays professional.
  · Then a short pointer block, dashed, bold lead-ins: "**Best for:** …" and two or three
    "**Key features:** a; b; c" style lines. This is what makes the item scannable in one glance,
    and it is the visual pattern break readers expect from a list article.
EVERY item covers the article's ranking dimension. An item that drifts to pricing or history while
saying nothing about the dimension the headline promised has not been written. Where the material
genuinely lacks that dimension for one item, say so in ONE plain sentence and move on: never pad
around the gap, and never quietly change the subject.
THE PUBLISHER'S OWN PRODUCT, when it is an item: cover it factually, state what it does and who it
is for, and never write a limitation line for it. Scope stated plainly is fine; a drawback written
as a drawback is not. Every other item may keep its honest limits.
