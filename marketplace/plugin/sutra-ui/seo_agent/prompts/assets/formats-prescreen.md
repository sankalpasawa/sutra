You are pre-screening proven link-bait FORMATS for {{BRAND}} on brand fit. Each one is a bare shape with no
subject yet.

This is a LIGHT pre-screen. The real scored gate runs later, once each format has a real subject, so keep
most of them. Your only job here is one question per format.

# What this company is, and is not

{{SCOPE}}

# The formats

{{FORMATS}}

# The one question

> Can this format plausibly be pointed at a subject inside the scope above?

Two rules on top of it:

- **The transplant check happens BEFORE any drop, and it is not optional.** When a format's obvious subject
  is off-brand, look for an in-scope subject the same shape could serve before binning it. A celebrity-style
  quiz becomes a "what is your hiring-bias profile" quiz. The shape travels; the subject does not.
- **Drop only a format you cannot imagine pointing at ANY in-scope subject.** A format you are unsure about
  is a keep. The cut comes later, when there is something real to judge.

# Return

JSON only. One object per format above, in the same order, using the SAME `format` name you were given.

- `keep` — true or false.
- `in_scope_subject` — a nameable subject inside the scope that a writer could build on, for example
  "Cost of a bad hire". Never a vague theme like "hiring stuff". Required when `keep` is true.
- `brand_fit` — CORE, TRANSPLANT or ADJACENT. This is a ROUGH tag on a subject-less format. The real
  Ownability test sets the authoritative one later, so do not agonise over it.
- `transplant_from` — for TRANSPLANT only: the off-brand subject the shape came from, for example
  "cost-of-living". Empty otherwise.
- `drop_reason` — for `keep: false` only: why no in-scope subject exists, even after the transplant check.

[{"format": "", "keep": true, "in_scope_subject": "", "brand_fit": "CORE", "transplant_from": "",
  "drop_reason": ""}]
