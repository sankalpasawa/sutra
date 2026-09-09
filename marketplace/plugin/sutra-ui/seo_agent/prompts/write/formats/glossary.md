# glossary

Two consumers. The **Structure** section becomes `{{FORMAT_STRUCTURE}}` in the architect's shape
step. The **The rewrite** section at the foot becomes `{{FORMAT_RULE}}` in the readability rewrite.

## Structure (the format's signature)
**The whole page**
- [ ] **The section defining the core subject itself comes FIRST.** A glossary reader may know none
      of the vocabulary; nothing that leans on the subject (validity, benchmarks, costs) may come
      before the section that says what the subject is.
- [ ] **Every section is a term or a tight cluster of terms.** A glossary explains vocabulary. A
      section giving process, legal or buying advice with no term at its centre belongs to a
      different article — leave it out, however well evidenced.

**The hub page**
- [ ] One A-Z index linking to **every** entry — the crawl backbone; no entry reachable only from search.
- [ ] Order: numbers/symbols first, then A-Z. Optional category/thematic filters alongside the A-Z jump links.

**The entry (fixed order)**
- [ ] H1 = the **exact term** (the only H1).
- [ ] The concise definition comes **first**, before any heading (shared 40-60w answer-first rule — referenced, not re-taught).
- [ ] "**Why it matters**" section (the how/why, not a restated definition).
- [ ] ≥1 concrete real-world example (ideally with a number).
- [ ] Related-terms + internal-links block last. Dated/deprecated terms flag era/status (current / legacy / deprecated).

**Interlinking (the new part vs answer-bait)**
- [ ] Hub → every entry and every entry → hub, reciprocal; the entry's back-link uses keyword-rich anchor text.
- [ ] **3-5 sideways links to related entries** per entry (a network, not a loose archive).
- [ ] Every in-content mention of a defined term elsewhere on the site links to its entry.

**Length band (entry)**
- [ ] Default = the short definition entry. Expand to 600-1,000 words only where the term warrants it, broken into 200-400-word independently citable sections. Never pad.

## The rewrite

Injected into the readability rewrite (`readable.py`) as `{{FORMAT_RULE}}`.

THIS IS A GLOSSARY. THE TERM ENTRIES ARE THE ARTICLE.

Every section explains a term, and the section defining the core subject itself comes FIRST —
before anything that leans on it. If the article you were handed discusses validity or benchmarks
before it has said what the subject is, reorder it so the definition leads.

Inside each entry: the plain definition comes first, then why it matters, then the example. A
reader lands on any entry cold, from search, knowing nothing.

A section that gives process, legal or buying advice with no term at its centre is a different
article wearing this one's headline. Cut it, or cut it down to the one term it actually defines.
This is the fault human reviewers flagged hardest on the last glossary run, so look for it.
