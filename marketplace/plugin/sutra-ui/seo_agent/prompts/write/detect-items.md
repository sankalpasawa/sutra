You are finding the LIST ITEMS of a listicle — the concrete things the reader came for.

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

The items come from the CONTENT of the material, not from brands or publishers. What an item IS
depends entirely on what the article promises. Examples across different subjects, so you get the
idea rather than the subject:
- "common onboarding mistakes"        -> each MISTAKE
- "best project management tools"     -> each TOOL
- "tax deductions freelancers miss"   -> each DEDUCTION
- "strategic interview questions"     -> each individual QUESTION, as it would be asked aloud
- "reasons a warehouse audit fails"   -> each REASON

Rules:
- Return at most {{MAX_ITEMS}} items. A shorter list that is fully written beats a longer list of stubs.
- STAY INSIDE OUR WORLD. Read the NOT ABOUT line. An item can appear in the material, read well, and
  still belong to a different field or a different audience. Drop it, whatever it matches.
- Two items a reader would answer the same way are ONE item. Merge near-duplicates (the same thing in
  different wording, tense, or scale) and keep the clearest phrasing.
- Keep an item ONLY if the material contains evidence about THAT item specifically — an example, a
  standard, a figure, a named case. An item mentioned only in passing inside a general box does not
  qualify.
- Every item must serve the article's angle above. Drop items that belong to a neighbouring topic
  even when the material mentions them.
- Each item must be complete and usable as it stands, never a fragment or a stub.
- Pick the true grain the article promises — the individual things, not the categories they fall into.
- Only items the material actually supports. Never invent one.
- Do NOT list the studies, publishers, research bodies, authors or data vendors the cards cite. Those
  are the sources OF the material, not items IN the article, and they appear often enough to look
  like items if you count mentions.
- Return each with a rough count of the cards supporting it.

Return ONLY this JSON, nothing else:
{"entities": [{"name": "<the list item>", "count": <supporting cards>}]}
