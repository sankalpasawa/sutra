You are checking whether a web page genuinely supports a factual claim.

THE CLAIM (both lines are part of it — the first names WHAT/WHO it is about):
{{GLOSS}}
{{VERBATIM}}

THE PAGE:
URL: {{URL}}
TEXT:
{{PAGE}}

Answer YES only if this page states this fact ABOUT THE SAME SUBJECT — the same named company, product,
study or organisation. A page that states the same number about a DIFFERENT subject, or about the market
or category in general, is NOT support: answer NO.
If the page attributes the figure to someone else ("according to X", "per Y data"), say so in "note" —
the original is the better source.

Return ONLY this JSON, nothing else:
{"supports": true|false, "quote": "<the sentence from the page that states it, empty if none>", "note": "<one short line>"}
