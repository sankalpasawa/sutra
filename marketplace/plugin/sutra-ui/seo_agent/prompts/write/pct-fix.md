Two sentences in a finished article read like rival answers to the same question, because they
carry different percentages and nothing tells the reader why. Fix ONLY this: add one clause to
whichever sentence is weaker, naming what was actually asked, of whom, and when, so a reader can
see the two numbers are not really rivals.

SENTENCE A:
{{SENTENCE_A}}
The source behind sentence A (use only these facts, nothing else):
{{CARD_A}}

SENTENCE B:
{{SENTENCE_B}}
The source behind sentence B (use only these facts, nothing else):
{{CARD_B}}

WHY THE TWO WERE FLAGGED AS RIVALS: {{WHY}}

Decide which sentence is WEAKER: the one that states its number with the least about what was
measured, of whom, or when. Add ONE short clause to that sentence only, built only from the facts
in its own source line above. Do not touch the other sentence at all.

THE RULES YOU CANNOT BREAK (code checks every one and rejects the answer):
- Never invent a number, a date, a sample size or a name that is not already in the source line for
  the sentence you are editing.
- Never remove or change the number that was already in the sentence.
- Never drop or add a [c...] source tag.
- Change nothing else about the sentence. Add the clause, keep the rest exactly as it was.

Return ONLY this JSON, nothing else:
{"edit": "a" | "b", "sentence": "<the edited sentence, in full, with its [c...] tag kept>"}
