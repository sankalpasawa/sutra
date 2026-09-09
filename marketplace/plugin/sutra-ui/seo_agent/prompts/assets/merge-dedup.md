You are de-duplicating a CLUSTER of content-asset ideas for {{BRAND}} that a similarity search flagged as
possibly the same. These ideas came from THREE different methods (competitor-study, model-other-niches,
study-trends), so the SAME idea can appear worded quite differently. Be CONSERVATIVE: when unsure, keep
them separate.

## The cluster (each: id, the methods that found it, title, format, angle)
{{CLUSTER}}

## Your THREE actions

**1. SAME, they are the same asset to build**, just surfaced by different methods or worded differently
("State of Skills-Based Hiring report" from the competitor study and "annual hiring-trends report" from
study-trends are the same build). NOT merely the same topic. When SAME: pick the id whose entry is
clearest and richest to KEEP; the others merge into it. Do not edit any text. Their method tags and their
proof get pooled automatically, so an idea two methods found records that it came from both. That is a
stronger bet, not a discarded copy.

**2. COMBINE, two DIFFERENT but complementary ideas that built as ONE make a richer asset.** Across methods
this is powerful: a proven FORMAT from model-other-niches plus a timely TENSION from study-trends on one
topic can fuse into a stronger asset than either alone. Write a new `new_title` and `new_angle`. Use
sparingly, only when the fused asset is clearly stronger than both.

**3. SEPARATE, genuinely different builds.** This is the default. Most pairs, even across methods, are
SEPARATE.

## Output, strict JSON only

```
{"groups": [
   {"action": "same",    "ids": ["<id>", "<id>"], "keep": "<id>"},
   {"action": "combine", "ids": ["<id>", "<id>"], "new_title": "<title>", "new_angle": "<one-line angle>"}
]}
```

List a group ONLY for ids you act on. Any id you do not list stays separate. `keep` must be one of that
group's own ids. Every id in a group must come from the cluster above; never invent one. When unsure,
choose SEPARATE: keep more, not less.
