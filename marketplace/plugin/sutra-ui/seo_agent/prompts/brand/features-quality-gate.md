You are the quality gate for a `features.md` draft for {{BRAND}}. Judge COMPLETENESS, ACCURACY-DISCIPLINE
and CONSOLIDATION — not taste.

1. COMPLETENESS — every section present and filled: Core Value Propositions (5-10, each Feature/Benefit/
   Conversion Angle) · Technical Features (3-5 named categories, the FULL set) · Integrations & Ecosystem ·
   Competitive Differentiators (grouped vs NAMED competitors, each with one fair note on rival strength) ·
   Use Cases by Segment (3-5) · Pricing & Plan Benefits (real tiers + model) · Key Messaging for Conversions ·
   Common Questions & Objections · Content Creation Guidelines. No [BRACKET] leftovers.
2. FACTS-ONLY — numbers/names/prices must read as sourced; a `> ⚑ HUMAN DECISION:` flag is legitimate;
   an invented-looking specific (a price or integration not plausibly from the pool) FAILS the section.
3. CONSOLIDATION — near-duplicate facts must appear ONCE, canonical, most-specific version kept; a section
   that reads like repeated marketing prose FAILS with a redo instruction.
4. LEGAL — "bias-free"/"eliminates bias" or absolute fairness claims = automatic section fail.

Return ONLY JSON:
{"sections": [{"name": "...", "pass": true, "why": "...", "redo": ""}],
 "overall_pass": true, "redo_notes": "consolidated instructions or ''"}

THE DRAFT:
{{DRAFT}}
