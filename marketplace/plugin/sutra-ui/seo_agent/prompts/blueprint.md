Build the structure for one article. Not the article, the plan for it.

## The research

Topic: {{TOPIC}}
Primary keyword: {{PRIMARY}}
Secondary keywords: {{SECONDARY}}
Questions searchers ask: {{PAA}}

What every page ranking for this already covers:
{{COVERED}}

The gap:
{{GAP}}

The angle we are taking:
{{ANGLE}}

## How this company writes and what they sell

{{VOICE}}

## Pages on this site you may link to

These are the only URLs that exist. Copy them exactly. If none of them fit a section,
give that section an empty internal_links list. Never write a URL that is not on this list.

{{LINK_CANDIDATES}}

## Your job

Plan {{SECTIONS_HINT}} sections that total about {{TARGET_WORDS}} words. The word budget
must add up to roughly that number.

Rules:
- The structure has to deliver the angle above. If the outline could have been written
  without reading the gap, it is the wrong outline.
- Headings say what the section gives the reader. No one-word headings, no "Introduction",
  no "Conclusion".
- covers is a brief for the writer: the specific points that section makes, and in what
  order. Two or three sentences. Not a restatement of the heading.
- Put the primary keyword in the title, in the first section's brief, and nowhere it would
  read as forced.
- Internal links go where they genuinely help the reader, roughly one per section at most.
  The anchor is the real sentence text a reader would click, not the page title.

{{WRITING_RULES}}

Reply with JSON only:

{"title": "the article title, under 65 characters",
 "meta_description": "under 155 characters, says what the reader gets",
 "keyword_placement": "two or three sentences on where the primary and secondary keywords go",
 "sections": [{
   "id": "s1",
   "heading": "the H2",
   "covers": "the brief for the writer",
   "words": 250,
   "internal_links": [{"url": "an exact URL from the list", "anchor": "the clickable text"}]
 }]}
