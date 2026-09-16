You are checking whether a web page genuinely supports a factual claim.

THE CLAIM, AS THE ARTICLE STATES IT:
{{CLAIM}}

THE EVIDENCE CARD BEHIND IT (both lines are part of it; the first names WHAT/WHO it is about):
{{GLOSS}}
{{VERBATIM}}

THE PAGE:
URL: {{URL}}
TEXT:
{{PAGE}}

Answer YES only if this page states this fact ABOUT THE SAME SUBJECT: the same named company, product,
study or organisation. A page that states the same number about a DIFFERENT subject, or about the market
or category in general, is NOT support: answer NO.
Citation markers like [11] were removed from the card before you saw it; a number that is missing from
the card is never a reason to answer NO. A figure written differently ("4.7k", "four in ten", "51 percent")
still counts if it is the same figure.
If the page states the figure DIFFERENTLY for the same subject (the claim gives one figure and the page
gives another for the same thing), answer NO, put the page's own sentence in "quote" and say so in "note":
the fix step uses that quote to correct the article.
If the page attributes the figure to someone else ("according to X", "per Y data"), say so in "note";
the original is the better source.

Return ONLY this JSON, nothing else:
{"supports": true|false, "quote": "<the sentence from the page that states it, or that states the figure differently; empty if none>", "note": "<one short line>"}
