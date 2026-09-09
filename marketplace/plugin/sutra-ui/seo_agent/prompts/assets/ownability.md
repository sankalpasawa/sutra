You are judging whether a company can credibly OWN an asset idea. One verdict per idea.

# What this company is, and is not

{{SCOPE}}

# The competitor set

{{COMPETITORS}}

# The test

An idea is OWNABLE when a reader who knows nothing about this company would, on seeing the
finished asset, think "of course they made this". It rests on something the company actually has:
its own data, its own customers, its product, or a subject it already has standing in.

It is NOT ownable when any company could have made it, or when making it would imply the company
does something it does not do.

Also tag the fit:
- CORE        the subject sits inside the scope above
- TRANSPLANT  the FORMAT comes from another industry but the subject is in scope. Name the industry.
- ADJACENT    same audience, next to the scope rather than inside it. Defensible but not central.

# Before you reject anything, try to rescue it

An idea whose subject is OUT of scope is not finished with. Ask one more question: could a
linkable format be pointed at an IN-SCOPE subject and keep what made this idea interesting?

You must answer that question for every idea you are about to reject, and record the answer
whichever way it goes. "No rescue: the interesting part IS the out-of-scope subject" is a complete
answer and a useful one. Silence is not.

This is the original's own rule, restored 2026-09-09: it demands a recorded verdict for every
out-of-scope idea, including a recorded "no transplant", so a person reading the drops later can
see that each one was considered rather than waved away.

# The ideas

{{IDEAS}}

# Return

JSON only. One object per idea, using the SAME id it was given. No idea left out, no id invented.

[{"id": "a0001", "verdict": true, "brand_fit": "CORE", "transplant_from": "",
  "why": "one short sentence naming what the company has that makes this theirs",
  "rescue": ""}]

`rescue` is REQUIRED on every idea you set `verdict: false` on: either the in-scope subject the
format could be pointed at instead, or a plain statement that there is none and why. Leave it
empty only when the verdict is true.
