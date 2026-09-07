You are routing ONE article to a write-phase ARCHETYPE (a content-shape family). Decide by the page's
NATURE — what kind of page this article really is.

THE 8 ARCHETYPES (pick exactly one label, verbatim):
- answer-bait-definitional — defines one concept. "What is X", "how does X work", FAQ page, definitional explainer.
- how-to-guide — a task to complete (ordered steps) or a broad topic to map (pillar guide, role-skills guide, standard blog).
- listicle — a set of discrete parallel items. "N best X", interview-questions bank, tips, myths/facts, curated list.
- comparison-rankings — a reader choosing between named options. "best X", "X vs Y", "alternatives to X", rankings.
- glossary — many short term-definition entries under one A-Z hub.
- data-benchmark-report — numbers presented for citation: data study, survey, salary benchmark, statistics roundup, cost/benchmark data.
- template-resource — an article whose real value is a downloadable artifact: template, checklist, cheat sheet, toolkit, whitepaper/ebook.
- common-spine — none of the above; editorial. news, opinion/editorial, trends/predictions, framework/methodology.

OUR USUAL MAPPING TABLE (reference only):
- definitional explainer -> answer-bait-definitional
- faq page -> answer-bait-definitional
- how-to guide -> how-to-guide
- pillar guide -> how-to-guide
- role skills guide -> how-to-guide
- listicle -> listicle
- interview-questions listicle -> listicle
- tips listicle -> listicle
- myths/facts/complete-list -> listicle
- curated resource directory -> listicle
- rankings / comparison -> comparison-rankings
- comparison -> comparison-rankings
- glossary -> glossary
- statistics roundup -> data-benchmark-report
- data report / original research -> data-benchmark-report
- state-of survey -> data-benchmark-report
- salary benchmark -> data-benchmark-report
- templates / examples pack -> template-resource
- toolkit -> template-resource
- whitepaper / ebook -> template-resource
- checklist / cheat sheet -> template-resource
- news article -> common-spine
- opinion / editorial -> common-spine
- trends / predictions -> common-spine
- framework / methodology -> common-spine
- other / editorial -> common-spine

THE ARTICLE:
- Queue format label: {{FORMAT}}
- Title: {{TITLE}}
- Distinct angle (what this article is built to deliver): {{ANGLE}}

OUR WINNERS STUDY (the pages currently winning on Google for this keyword — note especially what page
format the winners confirm works; "(not available)" when the study is missing):
{{WINNERS}}

HOW TO DECIDE:
1. Weigh everything above — the queue label, the title, the angle, the winners study, and the
   mapping table — and pick the archetype that best matches what this page really is. No single input outranks
   the others by rule; use judgment.
2. ONE specific care, for "news article" and other editorial labels: if the article's core deliverable is
   numbers the reader would cite (benchmark, cost, salary, survey, rate data), it is data-benchmark-report,
   not common-spine. Numbers that are merely incidental stay editorial.
3. Return one of the 8 labels, verbatim. Never invent a new one.

Return ONLY this JSON, nothing else:
{"archetype": "<one of the 8 labels>", "why": "<one short sentence>"}
