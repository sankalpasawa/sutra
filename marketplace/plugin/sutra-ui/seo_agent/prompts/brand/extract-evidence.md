Extract brand-voice evidence from ONE page of {{BRAND}}'s website. Read the page text below end to end.

Return ONLY the fields below. Draw everything from THIS page only.
Invent nothing. Leave a field "" if the page does not evidence it — a blank is information, don't pad it.
Quote excerpts VERBATIM. There is no length limit — the more genuine detail per field, the better.

Fields:
- voice_tone: how it sounds (warm / blunt / confident / formal…) + one short cue phrase copied from the text
- positioning: what the company says it IS / stands for / promises, on this page
- audience_pain: who this page speaks to + the pain it names
- quotable: 1-2 real lines worth using as a "this is our voice" example — copied exactly
- style_format_cta: sentence feel, headline shape, list use, and the EXACT CTA button text
- company_dimension: ONLY if a distinct recurring theme the fields above miss (e.g. an assessment library,
  anti-cheating) — name it + what this page says about it; else ""

Return ONLY JSON:
{"voice_tone": "...", "positioning": "...", "audience_pain": "...", "quotable": "...",
 "style_format_cta": "...", "company_dimension": "..."}

PAGE URL: {{URL}}
PAGE TEXT:
{{BODY}}
