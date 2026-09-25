# The principles an idea is checked against

**status**: v1, 2026-09-25 · **owner**: Native Method · **read when**: step 5 of the method, or when the coach names a principle. Page paths are relative to `holding/website/native/`; each quoted phrase was found on its page on 2026-09-25.

Two tables. Native's own rules come first, because they were ruled for this system. The general laws come second, because they hold for any system that grows.

## Native's rules

| # | Principle | Page | The idea is in trouble when it |
|---|---|---|---|
| N1 | The vocabulary is closed; a new kind goes through the new-thing protocol, never a new word in code | `structure-and-terms.html`, native-builder skill set 1 | names a thing the model has no word for |
| N2 | Five functions, "no sixth slot"; templates follow the narrowing-only law, adding or tightening, never dropping | `platform/model/internal-system.html` | lets an owner add, rename or remove a function |
| N3 | "The ask is the only write path"; nothing applies without a stamp | `platform/model/running-a-department.html` | changes a record on a timer, a score or a model's judgement |
| N4 | Adaptation senses and proposes, "NEVER apply" | `platform/model/internal-system.html` | lets a learner act on what it learned |
| N5 | A check is a check, "never a score" | `platform/the-model.html`, `platform/model/evals.html` | turns a pass/fail into a number people chase |
| N6 | The app is a projection: every card is a record read; no record means the quiet empty line | native-builder skill set 5 | stores something on a screen that no record holds |
| N7 | One home per subject | native-builder section 6 | starts a second place for a thing that already has one |
| N8 | Users add at the edges; "only the core author" changes the fixed core | `the-system-simply.md` | lets a user reshape the core for their case |
| N9 | Every growth path ends at a stamp and names its brake: the budget, the refusing rule, the person | native-builder section 8 | grows by itself with no named brake |
| N10 | Few independent axes; no family outranks another | `axes.html` | adds a dial that depends on another dial |
| N11 | One rule that recurses (proposed, not built) | `axes.html` | needs a different rule at each level |
| N12 | Each part reads its own position | `axes.html` | needs a central brain to tell each part what it is |
| N13 | Default to least noise | `_consumer-product.html` | sends the person something whether or not it needs them |
| N14 | Scale is measured at ten and at a hundred, not argued | native-builder section 7 | is argued safe at scale with no timing |
| N15 | Identity is "the only function the human speaks with" | `platform/the-model.html` | has another function message the owner directly |
| N16 | Engines fire from a calendar job outside the app, because the app stops its own back end when the last window closes | native-builder skill set 4 | relies on a timer inside the app |

## General laws

| # | Law | The question it asks |
|---|---|---|
| G1 | **Falsifiability** (Popper) | What result would prove this wrong? None means it is not yet a design goal |
| G2 | **Gall's law**: a working complex system grew from a working simple one | What is the smallest version that works end to end? |
| G3 | **Reversibility**: one-way doors need a test before; two-way doors can ship to learn | If this is wrong, what does undoing it cost? |
| G4 | **Chesterton's fence** | Before removing a rule, what decision row made it, and does its reason still hold? |
| G5 | **Goodhart's law**: a measure that becomes a target stops measuring | Will people act to move this number instead of the thing it stands for? |
| G6 | **Occam** | Of the rival causes, which is simplest, and was it tested first? |
| G7 | **Build the maker** (`core:system-engineering`) | Is this the third case of the same shape? Then design what makes them |
| G8 | **YAGNI** | Which user asked for this, and what record shows it? |

## How to use the tables

1. Name only the rows the idea breaks or strains, with the page. A row that holds is not listed.
2. A broken N-row is not an automatic no. It means the idea needs a ruling to change that rule, recorded as an ADR through `core:writing-adr`, before it is built.
3. A G-row is a question to answer, not a verdict.

---
provenance: {author: claude, date: 2026-09-25, inputs: [the Native model pages grepped for each quoted phrase on 2026-09-25, native-builder v1.0.0, standard engineering literature for G1 to G8], review: none by a second model, confidence: high on N2 to N5, N8, N10 to N13, N15 (quoted and located); moderate on N1, N6 and N16, which cite the native-builder skill rather than a site page}
