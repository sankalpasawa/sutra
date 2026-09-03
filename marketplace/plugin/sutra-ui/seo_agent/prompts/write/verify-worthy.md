You are picking which of an article's evidence cards carry a FACTUAL, CITABLE NUMBER that must have a
verifiable published source.

CARDS (id · text):
{{CARDS}}

Mark a card VERIFY when its number is a real-world statistic, benchmark, price, percentage, study result,
survey figure, or dollar amount a reader would expect a citation for.

ALSO mark VERIFY, even with no number at all:
- a claim that attributes a finding to a NAMED study, report, journal, or organisation
- a claim that characterises a NAMED third-party product or company (its pricing, limits, market position,
  or what it lacks) — publishing that unchecked is a public claim about someone else's product.
- a claim that states what a NAMED law, statute, regulation, regulator, or court ruling requires, permits
  or forbids — getting a legal obligation wrong in public is the most expensive error on this list, and it
  is never excused by the claim carrying no number.

Do NOT mark:
- years used as dates ("in 2026", "the 2022 figure")
- step / serial / list-count numbers ("step 3", "10 questions", "part 2")
- generic durations or policy defaults ("a 30-day notice period", "a 5-minute test")
- version numbers, page numbers, or numbers that are part of the article's own structure
- numbers inside a quote that is opinion rather than a measured fact

Return ONLY this JSON, nothing else:
{"verify": [<card ids that need source verification>]}
