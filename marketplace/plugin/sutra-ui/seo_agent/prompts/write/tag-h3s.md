You are judging the sub-sections (H3s) of ONE candidate section (an H2) for an article. For EACH H3, decide
what it contributes to — its TAGS. An H3 with no tags is dead weight and will be dropped.

THE COMPANY publishing this article: {{BRAND}} — {{ABOUT}}

THE ARTICLE (what we are building):
- Asset title: {{TITLE}}
- Distinct angle (what this article is built to deliver): {{ANGLE}}
- H1: {{H1}}
- Primary keyword: {{PRIMARY_KEYWORD}}
- The spine — what this article argues, for whom, and what the reader can do at the end:
  {{SPINE}}
- What this article IS about: {{WORLD_ABOUT}}
- What this article is NOT about: {{WORLD_NOT_ABOUT}}

────────────────────────────────────────────────────────────────────────
BEFORE TAGGING ANYTHING — THE WORLD TEST.

Read the NOT ABOUT line. An H3 whose material belongs to one of those worlds gets NO TAG, whatever else it
matches. A source from a neighbouring field can genuinely cover a table-stakes topic and genuinely answer a
real question — it will match, and it will still be wrong for this reader.

Where a subject shares a WORD with another world, the card's SOURCE is often the only thing that reveals
it: a university's page about a student prize contest, a vendor selling a different product, a clinical
or academic use of the same term. Read the source, not only the words.

Wrong world is a harder no than merely untagged. When you refuse an H3 for THIS reason, begin its
"why_untagged" with the exact token `WRONG WORLD:` and then say which world it belongs to. Use that token
only for a world refusal, never for an H3 that is merely weak, thin or off-angle.

────────────────────────────────────────────────────────────────────────
WHAT COUNTS AS CONTRIBUTING — the five tag kinds. For kinds 2-5, answer with the item's ID (G1, T2, Q3, R4...):
1. "asset-angle" — the H3 directly serves the asset title + distinct angle above.
2. "gap: <ID>" — it closes one of these gaps we can uniquely own:
{{GAPS}}
3. "common-h2: <ID>" — it covers one of these table-stakes topics competitors cover:
{{COMMON_H2S}}
4. "paa: <ID>" — it answers one of these People-Also-Ask questions:
{{PAA}}
5. "related: <ID>" — it serves one of these related searches:
{{RELATED}}

OFF-ANGLE TANGENTS TO AVOID (an H3 that is ONLY this gets NO tag, even if it looks informative):
{{DRIFT}}

THE SECTION:
H2: {{H2}}

ITS H3s, each with its evidence cards (id · [type] · source · summary — full text):
{{H3S}}

Rules:
- Judge each H3 on its own content and cards, as a child of this H2.
- Use the IDs exactly as listed (G2, T1, Q4...). Never invent an ID; never write the item's text.
- EVERY TAG MUST NAME ITS PROOF. For each tag, give the card id(s) from THIS H3 whose text actually
  contains the thing the tag claims. Several cards may prove one tag — list them all. If you cannot
  point to a card, you do not have that tag: leave it off. Being on the same broad topic as a promise
  is not serving it.
- "common-h2" and "related" are the LOOSEST tags — they are topic matches, not judgments about worth.
  Before giving either, ask whether a reader who came for the SPINE would want this H3. If the answer is
  no, the match is a coincidence of words, not a contribution. Leave it off.
- Most H3s honestly earn 1-3 tags. If you are about to give one H3 more than four, you are matching
  topic words rather than judging — keep only the ones a reader would agree were genuinely delivered.
- If the same tag would apply to every H3 in this section, it is a label for the whole H2, not a
  judgment about an H3. Give it only to the H3(s) that actually deliver it.
- No tags when it serves none of the five, or when it fails the world test. Then give "why_untagged":
  one short line saying why not, prefixed with `WRONG WORLD:` only when that is the reason.

Return ONLY this JSON, nothing else:
{"h3s": [{"index": <the H3's index as listed>,
          "tags": [{"tag": "asset-angle" | "gap: G2" | "common-h2: T1" | "paa: Q3" | "related: R4",
                    "cards": [<card ids from this H3 that prove it>]}, ...],
          "why_untagged": "<one short line, ONLY when tags is empty>"}, ...]}
