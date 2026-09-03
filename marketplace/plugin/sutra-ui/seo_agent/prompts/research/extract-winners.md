Below is our study of the pages currently winning on Google for one keyword (the "winners"). Extract four
things from it, lifting the items VERBATIM — do not rewrite, summarise, or invent.

THE WINNERS STUDY:
{{WINNERS}}

Extract:
- format: the confirmed content format, as one short phrase lifted from the study (for example "how-to guide",
  "listicle", "comparison", "definitional guide"). Empty string if the study names none.
- gaps_to_own: the content gaps no winning page covers — our openings.
- winners_common_h2s: the headings/topics the winning pages share — the table stakes.
- winners_drift: warnings that winners drift away from the keyword's real intent.

Rules:
- Lift each item verbatim from the study. If a list is genuinely absent, return it empty. Never invent an item.

Return ONLY this JSON, nothing else:
{"format": "...", "gaps_to_own": ["..."], "winners_common_h2s": ["..."], "winners_drift": ["..."]}
