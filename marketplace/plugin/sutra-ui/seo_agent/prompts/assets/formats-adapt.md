Proven cross-niche link-bait format: **{{FORMAT}}** (headline template: `{{HEADLINE_TEMPLATE}}`; it earns
links through **{{WHY_LINKS}}**). Where it proved itself: **{{EXAMPLE}}**.

Give me the single strongest {{BRAND}} adaptation of this format. One idea, not five variations. Most
formats yield exactly one strong idea, and padding the list is how a filter gets defeated.

Borrow the SHAPE, not the source niche's subject. Point it at the in-scope subject the pre-screen already
picked, **{{IN_SCOPE_SUBJECT}}**, and name the specific product, data or authority that lets this company
own it.

# What this company is, and is not

{{SCOPE}}

# How they write

{{VOICE}}

# What they sell

{{FEATURES}}

# The real numbers they hold

{{STATS}}

# Two rules about the name and the build

**The `asset` name carries no shape-words.** It says the subject and the angle, never the format. Banned in
the name: Calculator, Quiz, Generator, Interactive, Dashboard, Tool, Widget, Estimator, Configurator, Index.
The shape already lives in the format label and in `what_it_would_be`; repeating it in the title is how a
whole pool of ideas turned into calculators once before, when the pages that actually earn links in most
niches are plain articles.

**Say honestly what it would take to build.** Many imported formats need a real build or data nobody has
yet. That is allowed, but it goes in `tool_escalation`, never hidden. A writer with public sources can ship
an article, a list or a guide. That same writer cannot ship a calculator, a scored quiz, a generator, an
interactive widget, an original survey, or new primary research. If the asset needs any of those, say so in
one line. Leave `tool_escalation` empty ONLY when a writer could genuinely build this from desk research.

# Return these fields in THIS order, because the order is the thinking

Work out the substance before you name the thing. The angle is the foundation: why our version wins, and
what we hold that lets it. The name only works once it can bake that angle in. Named first, the name forces
a guess you then have to justify backwards.

JSON only.

1. `our_topic` — the specific subject. Sharpen "{{IN_SCOPE_SUBJECT}}" into a precise one, grounded in what
   you were told above.
2. `distinct_angle` — one line: what makes OUR version the link magnet. It MUST name the specific product,
   data or authority that lets us own it. The test: if this line could have been written without the
   company context above, it is too generic. Rewrite it. "We are a great team" is not an angle.
3. `asset` — only now, name it. A real working title a writer could open a document with, subject plus
   angle, no shape-words. Not "[Format] on [topic]" glued together.
   Wrong: "Bad-Hire Cost Calculator". Right: "What a Bad Hire Really Costs, Per Role (on real customer data)".
4. `tool_escalation` — empty string when a writer could build this from public sources. Otherwise one line
   naming what it needs: "interactive calculator", "scored quiz", "needs our own survey data",
   "needs new primary research".
5. `headline` — the published H1 in this company's voice, built from the headline template. This is the
   marketing headline, and it is a different thing from the working title in `asset`.
6. `what_it_would_be` — one or two lines: the actual asset, concretely. Inputs, output, what ships.
7. `source_niche` — the industry this format proved itself in, read off the example: finance, real estate,
   B2B SaaS, economics.

{"our_topic": "", "distinct_angle": "", "asset": "", "tool_escalation": "", "headline": "",
 "what_it_would_be": "", "source_niche": ""}

Do NOT return a brand fit. That is decided once, later, by the Ownability test.
