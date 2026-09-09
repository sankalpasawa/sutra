You are tagging competitor pages by **FORMAT**: the shape of the page, never its topic.

This is the most important label in the whole study. Everything after it groups by format, to answer
which shapes earn links and therefore what {{BRAND}} should build. A wrong tag poisons that answer.

# Format means shape, not subject

- "10 Best Payroll Tools" and "10 Best CRMs" are the same format on different subjects.
- A glossary of HR terms and a glossary of legal terms are the same format.
- Ask: if I stripped the topic out, what KIND of page is this?

# The starting set

Use these where they fit. They are a starting set, not a cage.

- **Glossary or dictionary**: many short defined terms, usually an index plus term pages
- **Calculator or tool**: the reader puts something in and gets an answer back
- **Data report**: the company's own survey, study or benchmark, with figures
- **Statistics roundup**: collected stats gathered from other sources, with citations
- **Rankings or comparison**: top N tools, X versus Y, alternatives pages
- **Templates**: downloadable or copyable artefacts: emails, policies, checklists
- **Interview questions listicle**: a long list of questions for a role or a skill
- **How-to guide**: a numbered process the reader follows
- **Definitional explainer**: what X is and how it works, one concept in depth
- **Pillar guide**: a long structured hub covering a whole subject
- **Checklist or cheat sheet**: a short actionable list meant to be used while working
- **Quiz or free test**: the reader answers questions and is scored
- **Case study**: one named customer, what happened, with results
- **Jobs listing**: a directory of roles
- **Free product page**: a usable free thing the product itself provides
- **Commercial page**: a page whose job is to SELL: a product or solution overview, pricing, a book
  a demo landing page, a features tour, an integrations directory. Nobody links to it as a free
  resource, so it is not a content asset anyone can model.

If a page genuinely fits none of these, **invent a new named format**: give it a short name, use it
consistently, and set `"new_format": true`. Do not force a bad fit.

# The one boundary that matters most: a usable asset against a sales page

This is the label people get wrong, and it decides whether we build on the page or drop it. Judge by
what the page is FOR, not by who owns it.

- If the page gives the reader a usable free thing (a test they can take, a tool they can run, a
  template they can download, a glossary they can read), tag it by THAT asset. A company's own free
  skills test is a **Quiz or free test**, not a commercial page, even though the company also sells,
  because the test is the usable asset and the test is what earns the links.
- Tag **Commercial page** only when the page's whole purpose is to sell and there is no usable free
  thing on it. Tell-tales: request a demo, talk to an expert, start free trial, pricing tiers.
- When a page has both a real usable tool AND a sales pitch around it, **the asset wins**.

# Use the evidence, not the address

For each page you get the URL, the title, the H1 and H2 headings, the word count, the image count and
the outbound-link count. **The headings are the strongest signal**: they tell you the page's real
structure. The numbers help too.

- many short noun-phrase H2s: often a glossary, a listicle or a ranking
- a very high image count: often an infographic or a visual asset
- a very high outbound-link count: often a statistics roundup or a resource list
- a low word count with an interactive-sounding title: often a calculator or a tool
- numbered, step-like H2s: a how-to

**Never tag from the URL alone.** The URL is a hint; the headings are the evidence.

# Guard against the lazy bucket

"Other" is a last resort. A previous run put 26% of all pages there and found exactly one calculator
across 2,469 pages in a niche full of them. That is what failure looks like here. If you find
yourself reaching for "Other", look at the headings again and pick the real shape, or name a new one.

# Return

JSON only, one object per page, in the order you received them. Return exactly one object for every
page given, using the SAME id it was given. Never skip one.

```
{"tags": [
  {"id": "12", "format": "Glossary or dictionary", "confidence": "high",
   "why": "at most 12 words: the evidence that decided it, ideally a heading",
   "new_format": false}]}
```

# The pages

{{PAGES}}
