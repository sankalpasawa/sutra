You are correcting an article section after a source check. Some sentences cite a page that does not
state what they claim. Your job is to make those sentences honest without inventing anything.
{{FAILURE}}
THE SECTION: {{HEADING}}

THE PARAGRAPHS THAT CONTAIN THE PROBLEM SENTENCES (each is numbered; return each one in full):
{{PARAGRAPHS}}

THE SENTENCES TO FIX, AND WHAT THE CITED PAGE ACTUALLY SAYS:
{{SENTENCES}}

For EACH listed sentence, apply the first rule that fits, in this order:
1. CORRECT. If the page states the figure differently for the SAME subject (the quote above shows it),
   change the number to what the page says. Keep the sentence and its [c...] tag.
2. SOFTEN. Otherwise remove the exact figure and keep only what the page does support. "Cost per hire
   was $4,700" becomes "cost per hire runs into thousands of dollars" only if the page says that; if the
   page supports nothing about it, do not soften, remove. Keep the [c...] tag only if the page supports
   what is left.
3. REMOVE. If the sentence existed only for that figure, delete it. If the paragraph then needs a bridge,
   build it from words and facts ALREADY IN THE PARAGRAPH. Do not add a sentence.

THE RULES YOU CANNOT BREAK (code checks every one and rejects the answer):
- Change ONLY the listed sentences. Every other sentence in the paragraph must stay as it is, apart
  from a connective word or two where a removed sentence leaves a gap.
- NEVER introduce a new figure, number, date, percentage or amount. The only new number allowed is
  the one the page's quote states, for a CORRECT.
- Never add a new fact, a new source, a new [c...] tag or a new sentence.
- Return every listed paragraph in full, even if you removed its only problem sentence.
- Plain, neutral prose. No note about what you did inside the text.

Return ONLY this JSON, nothing else:
{"paragraphs": [{"n": <paragraph number>, "text": "<the whole paragraph as it should now read, [c...] tags kept where they still apply>"}],
 "sentences": [{"sentence": "<the listed sentence, exactly as given>", "action": "correct" | "soften" | "remove", "why": "<one short line>"}]}
