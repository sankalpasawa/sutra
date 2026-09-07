Extract product FACTS from ONE {{BRAND}} page ({{KIND}}) for a features document.
Return ONLY real facts found on THIS page — verbatim numbers, names, prices. Invent nothing;
use "" or [] where the page doesn't have it. A wrong integration name or price is worse than a blank.

Return ONLY JSON with these exact categories:
{"features": ["each feature + what it does (+ the user benefit if stated)"],
 "integrations": ["every named tool/platform it integrates with (+ category, e.g. ATS)"],
 "pricing": ["plan names, what each tier includes, the model, trial/guarantee/discount"],
 "competitive": ["advantages vs a NAMED competitor (only if this page names one) — fair"],
 "social_proof": ["real numbers: customers/teams, outcome stats, ratings, certifications"],
 "audience": ["who the page says it is for + the pains it names"],
 "ctas": ["the exact CTA button/link text"],
 "faq": ["Q → A pairs, verbatim"]}

PAGE URL: {{URL}}
PAGE TEXT:
{{BODY}}
