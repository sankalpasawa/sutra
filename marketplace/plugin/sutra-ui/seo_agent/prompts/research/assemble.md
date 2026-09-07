You are writing TWO short synthesis blocks for a {{BRAND}} research brief. Everything ELSE in the brief is lifted
verbatim from the research by code — you do NOT reproduce those. You ONLY write the Verdict and the Build spec.

ANCHORS
- Article title: {{ASSET_TOPIC}}
- Distinct angle: {{DISTINCT_ANGLE}}
- Standing rules from the user:
{{MEMORY}}

CONTEXT — read to write the Verdict (do NOT reproduce these; they already appear in the brief):
--- KEYWORDS ---
{{KEYWORDS}}
--- SERP SNAPSHOT ---
{{SERP_SNAPSHOT}}
--- WHAT THE WINNERS COVER ---
{{WINNERS}}

BUILD-SPEC SOURCE — the SEO/AEO/GEO checklist (derive the Build spec from this + the confirmed content format):
{{CHECKLIST}}

WRITE:
- VERDICT: 3-5 bullets grounded only in the context above — **Play** (traffic vs authority — is the head big or
  modest?) · **Beatable — head** (who holds it, how hard) · **Beatable — long-tail** (the low-KD secondary cluster)
  · **The opening** (the one gap the winners leave that this angle owns).
- BUILD SPEC: **Word band** (for the confirmed content type, as two whole numbers) · **Structure** (primary in H1
  ≤60 chars · in first 100 words · in 2-3 H2s · in conclusion · 4-7 H2s · ≥50% question-phrased H2s · each section
  leads with a 40-60 word liftable answer) · **Featured-snippet target** (a 40-60 word answer in the SERP snapshot's
  open format) · **Primary sources to cite** (2-4 authoritative external sources fit for THIS topic) · **Close**
  (forward next step + ONE {{BRAND}} CTA tied to the angle, not a recap).

RETURN JSON only:
{ "verdict": ["<bullet>", "<bullet>", ...],
  "build_spec": {
    "word_band": {"min": <int>, "max": <int>},
    "structure": ["<rule>", ...],
    "featured_snippet_target": "<one line>",
    "primary_sources": ["<source>", ...],
    "close": "<one line>" } }
