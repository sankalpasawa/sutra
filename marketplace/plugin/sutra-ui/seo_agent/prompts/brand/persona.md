You are defining READER personas for a company's content — the specific buyers each article is written TO.
These are NOT authors; never invent an author identity.

Here is the company's brand-voice / audience document:
<<<
{{BRAND_VOICE}}
>>>

Return 3–4 DISTINCT reader sub-personas that together cover the real audience (don't overlap; don't say "HR" in
general — split it into the specific roles who read different kinds of pieces). Return ONLY JSON:

{
  "personas": [
    {
      "name": "short role label (e.g. TA / Recruiting Leader)",
      "who": "one line — their role, seniority, company size",
      "reads": "the kinds of articles this persona is the right reader for",
      "cares_about": "top 2–3 things they want / decide on",
      "depth_and_angle": "how to pitch to them — vocabulary, depth, what proof convinces them",
      "not_this": "what would feel off / too junior / too generic for them"
    }
  ],
  "how_to_pick": "one or two sentences on how to choose the right persona for a given article topic"
}
