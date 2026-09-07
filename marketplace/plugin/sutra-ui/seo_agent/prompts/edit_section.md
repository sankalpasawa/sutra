Rewrite ONE section of an article blueprint. Only that section. The rest of the blueprint is
not yours to touch, and nothing else will be taken from your reply.

## The article

Title: {{TITLE}}
Primary keyword: {{PRIMARY}}

## The other sections, so you do not repeat them

{{OTHERS}}

## The section to rewrite

{{SECTION}}

## What the user asked for

{{INSTRUCTION}}

## Pages on this site you may link to

These are the only URLs that exist. Copy them exactly. If none fit, use an empty
internal_links list. Never write a URL that is not on this list.

{{LINK_CANDIDATES}}

## How this company writes

{{VOICE}}

{{WRITING_RULES}}

Reply with JSON only, the section object on its own, with exactly these keys:

{"id": "{{SECTION_ID}}",
 "heading": "the H2",
 "covers": "the brief for the writer, two or three sentences",
 "words": 250,
 "internal_links": [{"url": "an exact URL from the list", "anchor": "the clickable text"}]}
