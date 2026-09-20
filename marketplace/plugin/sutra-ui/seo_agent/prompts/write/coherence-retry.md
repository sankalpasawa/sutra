Some of your fixes from the last pass were REJECTED by code before they ever touched the
article. Everything else you fixed already landed — those fixes stand, exactly as you wrote
them, and are not repeated here. Only the rejected fixes below are yours to redo.

WHY A FIX GETS REJECTED. Code applies each fix by finding your `find` text once, exactly, in
the section you named, and swapping it for `replace`. A fix is rejected when: `find` does not
appear in that section, or appears more than once (too ambiguous to know which one you mean);
`replace` drops a [c…] tag that `find` had, or adds one that was not there; `replace` invents
a number that is not already in the article and is not declared and derived in
`numbers_changed`; `replace` contains a markdown heading line; or `replace` runs far longer
than the `find` it replaces.

THE REJECTED FIXES, WITH THE REASON EACH ONE FAILED:

{{REJECTED}}

════════════════════════════════════════════════════════════════════════
FIX EACH ONE AGAIN, OR SAY WHY YOU CANNOT.

For every rejected fix above: read the exact reason it failed, then either

  - return it again with that fault corrected — `find` copied exactly, character for
    character, tags included, from the article below, and `replace` respecting every rule
    it broke last time; or
  - move it to "could_not_fix" with why not, if the fault genuinely cannot be fixed this way.

Do not touch anything that already landed; it is not shown to you again and is not yours to
revisit. Do not introduce a new fix for a fault nobody flagged here. This is your only
retry: a fix that fails again is reported, unfixed, and the rest of the article publishes
as it stands.

════════════════════════════════════════════════════════════════════════
THE ARTICLE AS IT STANDS NOW, with every fix that already landed already applied:

{{ARTICLE}}

════════════════════════════════════════════════════════════════════════
THE USER'S STANDING RULES. They were set by the person publishing this and they win over any
rule above that they contradict. "(none)" means there are none.
{{MEMORY}}

Return ONLY this JSON, covering just the fixes you were handed above:
{"fixes": [{"kind": "breaks-own-rule | own-warning | several-scales | numbers-disagree | caveat-repeated",
            "section": "<the heading it is in, or intro / quick answer / close / FAQ: the question>",
            "find": "<the sentence(s) exactly as they stand in the article, copied character for character>",
            "replace": "<what they become>",
            "why": "<one line: what it collided with, and where>",
            "numbers_changed": [{"was": "<the figure as written>", "now": "<what it became>",
                                 "derived_from": "<the figures already in the article this was computed from, or empty>"}]}],
 "could_not_fix": [{"what": "<the fault>", "where": "<section>", "why_not": "<one line>"}],
 "verdict": "<one line: is this article honest and safe to publish now?>"}
