You are reading real pages from one company's website to learn how they write.

Here are {{COUNT}} pages from {{DOMAIN}}:

{{PAGES}}

Work out who this company is and how they sound. Base every answer on the text above.
Do not invent a company mission, and do not describe them in marketing language they
would not use about themselves.

Return JSON only, with exactly these keys:

{
  "company": "the company name as they write it",
  "what_they_sell": "one sentence, concrete, in plain words",
  "who_buys": "one sentence on the reader they write for",
  "summary": "a paragraph describing their writing voice: sentence length, formality, how they open, whether they address the reader as 'you', how technical they get. Write it as instructions a new writer could follow.",
  "traits": ["4 to 6 short adjectives or phrases"],
  "avoid": ["8 to 12 words or phrases this company never uses. Draw them from what is absent in the writing above: filler this company clearly steers around, plus the banned words below"],
  "examples": ["2 to 3 sentences copied VERBATIM from the pages above that are most characteristic of their voice"]
}

The examples must be real sentences from the text given. Never write your own.

## Words that belong in "avoid" whatever the company writes like

{{WRITING_RULES}}
