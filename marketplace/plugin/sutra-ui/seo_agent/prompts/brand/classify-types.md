You are looking at the page-type list of {{BRAND}}'s website ({{NICHE}}), from its site catalogue.
Every CMS names its types differently ("successstory" vs "case-studies" vs "customers") — so job one of
any tool that works across companies is to work out what THIS company's types actually hold.

For each type below you get: its name, how many pages, and a few sample titles + URLs.
Classify every type into the roles it serves (a type can serve several, or none):

- "story": pages that tell a real customer/company anecdote — success stories, case studies,
  customer testimonials, press releases, podcast/interview episodes about real people.
- "stat": pages where the company states ITS OWN numbers — homepage-style marketing pages,
  product/feature pages, certification/trust pages, "why us" pages.
- "commercial": positioning and money pages — pricing, plan comparison, competitor/"vs"/"alternatives",
  product, integrations, "why us". (Used to make sure the brand-voice shortlist sees them.)
- "editorial": articles/blog/glossary/guides — the company's educational writing.
- "machine": types that are navigation, media, authors, language-duplicates, or CMS internals — no role.

Also name every type as a person would say it out loud, in "display_names": the slug turned into
plain English, capitalised as the company itself capitalises it. "test-library" -> "Test library",
"hr-glossary" -> "HR glossary", "successstory" -> "Customer stories". Two to three words, no
punctuation, no explanation. Every type in the table gets one, including the ones with no role.

Rules:
- judge from the SAMPLES, not the type's name — names lie across CMSs
- a language-duplicate type (same content translated) = "machine" (we read the primary language)
- when unsure, leave the type out of the role rather than guessing it in

Return ONLY JSON:
{"stat_types": ["..."], "story_types": ["..."], "commercial_types": ["..."], "editorial_types": ["..."],
 "display_names": {"<type>": "<what a person calls it>"},
 "notes": "one line on anything surprising"}

THE TYPE TABLE:
{{TYPES}}
