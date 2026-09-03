You are finding the OPTIONS of a comparison article — the named things this article will compare.

THE COMPANY publishing this article: {{BRAND}} — {{ABOUT}}

THE ARTICLE (what we are building):
- Asset title: {{TITLE}}
- Distinct angle (what this article is built to deliver): {{ANGLE}}
- What this article IS about: {{WORLD_ABOUT}}
- What this article is NOT about: {{WORLD_NOT_ABOUT}}

WHO THIS ARTICLE IS FOR:
{{PERSONA}}

THE MATERIAL (the planned sections — H2s, their H3s, and the evidence cards under each):
{{MATERIAL}}

Your job: list the NAMED options a reader of THIS article would actually be choosing between. What counts
as an option depends entirely on the article — it might be software products, service providers, agencies,
vendors, platforms, courses, banks, or anything else this article genuinely compares.

Examples across different domains (so you get the idea, not the domain):
- "best video interview software"        -> HireVue, Spark Hire, Willo, VidCruiter...
- "top recruiting agencies for startups" -> the named agencies
- "best coding bootcamps"                -> the named bootcamps
- "business credit cards compared"       -> the named cards

Rules:
- IT MUST BE THIS READER'S OPTION. An option aimed at the other side of the table — the
  candidate rather than the recruiter, the employee rather than the manager — is not this article's
  option, however well the material covers it.
- STAY INSIDE OUR WORLD. Read the NOT ABOUT line. An option that belongs to a neighbouring field or a
  different audience is not an option here, however often the material names it.
- An option must be something a buyer of THIS article would put on ONE shortlist against the others.
  A product from an ADJACENT category that the material merely mentions — a component, an integration,
  a supplier to the category — is not an option, however often it appears.
- NEVER list tools that produced or fetched the research itself (scrapers, search APIs, data vendors).
- Drop anything mentioned by fewer than 3 cards — one passing mention is not an option.
- Only NAMED options that genuinely appear in the material. Never invent one.
- Give each a rough count of how many cards mention it.
- Do NOT list the studies, publishers, or data sources the cards cite (SHRM, Gartner, a university) —
  those are sources, not options — unless the article genuinely compares them as options.

Return ONLY this JSON, nothing else:
{"entities": [{"name": "<option>", "count": <cards mentioning it>}]}
