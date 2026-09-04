---
type: principles (engineering)
reusable: yes
reads: seo_agent/ (the worked example) · seo_agent/CONTRACTS.md · seo_agent/HISTORY.md
produces: the rules any agent we build has to satisfy, and the checks that prove it does
plain twin: AGENT-PRINCIPLES-plain.md (same headings, same order, no code)
step-by-step recipe: NEW-AGENT-plan.md (how to build one inside Sutra)
last_updated: 2026-09-04
---

# How we build an agent: the principles

This is the short document. It says what an agent is made of, the rules each part
obeys, and how we check the rules held. It is written from one agent that exists and
was run to the end, the SEO Writer in `seo_agent/`, but nothing here is about SEO.
Swap the tools and the same shape builds a research agent, a support agent, or a
bookkeeping agent.

Two longer documents sit next to it. `NEW-AGENT-plan.md` is the step-by-step recipe
for building one inside Sutra. `seo_agent/HISTORY.md` is what running the SEO Writer
taught us, bug by bug. Read this one first.

---

## What an agent is

An agent is a job a person would do by hand over an hour, turned into named steps
that run in front of them, with a few moments where the person looks at the work
and either approves it or sends it back.

It has seven parts. In order of how much they matter:

| Part | One line | In the SEO Writer |
|---|---|---|
| The loop | Asks the model what to do next, does it, hands the result back, repeats. Enforces every rule in code. | `loop.py` |
| The tools | The only things the agent can do. Each is a function with a plain-English row. | `registry.py`, `tools/*.py` |
| Knowledge | What the agent learned about this company once and keeps: the catalogue, the index, the brand files. | `knowledge/` |
| Memory | Standing rules the user gave. Short, few, and handed to every step that shapes output. | `memory.jsonl` |
| The run folder | The complete record of one job: state, events, artifacts, working files. | `chats/<chat>/runs/<run>/` |
| Checkpoints | The four or five moments the person must see the work before the next step runs. | `show_artifact` + `_wait()` |
| The screen | Shows the run folder. Holds nothing of its own. | `static/js/17-agents.js` |

The model is the eighth thing, and it is deliberately last. It decides which tool
runs next and writes the prose. It never decides whether a rule applies.

---

## The one rule above the others

**A rule the model is asked to follow is a suggestion. A rule the code enforces is
a rule.**

Everything below is that sentence applied to one part at a time. When a rule
matters, it lives in code and has a test. The prompt may repeat it for tone, but the
prompt is never the thing that makes it true.

---

## The loop

1. **Code drives, the model chooses.** The loop owns the sequence: read state, ask
   the model, run the tool it picked, record the result, repeat. The model picks
   from a list. It cannot invent a step, skip a checkpoint, or run something twice
   because it forgot.

2. **A checkpoint is a write, not a wait.** When the agent needs the person, it
   writes `status="waiting"` and what it is waiting on, emits one event, and
   returns. No thread sits open. The answer comes back through `resume()`, which
   re-reads everything from disk. The app can be closed mid-run and nothing is lost.

3. **The model cannot see the disk. Tell it.** A fresh conversation starts with no
   idea what Knowledge holds. If setup is finished, the system prompt says so in
   one sentence, with the numbers, or the model redoes an hour of work. Any state
   that should stop the model from redoing something has to be written into the
   prompt. (`loop._knowledge_block()`; found live on 2026-09-04.)

4. **The model only learns what happened from tool results.** It never announces
   an outcome the code did not report. Saving to the Library is done by the loop on
   approval and appears in the tool result; the model may say "saved" only after
   it sees that. (Found live: the model said "Saved" after an approval that saved
   nothing.)

5. **Recoverable is not fatal.** An overloaded model, a 429, a slow page: retry with
   backoff and say so in the log. Only a login failure is a login failure.

6. **A cap on unattended moves asks, it does not kill.** Twenty-five real steps
   without a checkpoint and the agent asks whether to continue. Narration and
   memory saves are free and never count.

---

## The tools

7. **A tool is a function that returns a dict and reports its own progress.**
   `run(ctx, **kw) -> {"summary", ...}`. Inside, it emits sub-steps with a plain
   label and a note, so the run log reads like a person describing their work.

8. **The registry is the truth about tools, and the Tools screen is the registry.**
   Every tool has a `plain` row: what it does, when it runs, what it needs, how
   long it takes. The model sees name, description and inputs. The person sees the
   plain row. Nothing else is described anywhere.

9. **Every step that touches the network goes through one helper.** The SEO Writer
   learned to read a site behind a bot wall in its crawler and still failed in two
   other readers that fetched on their own. One fetch helper, one fallback, called
   from everywhere. The same holds for one paid-API client and one model caller.

10. **Paid steps check the balance first and say plainly when they skipped.** No
    credit gates, no approvals for money. The pre-flight is code; the message is
    plain English; the run continues with whatever the step could do.

11. **Nothing is invented. Code counts, an AI judges, a source backs every number.**
    Word counts, link counts, similarity scores and page lists come from code. An
    AI decides relevance, quality and fit, and it only decides once, with the
    criteria in front of it. Any number in the output traces to a source page the
    tool read, or it is cut. An edit that introduces a number the original did not
    have is rejected and retried.

12. **Filter at the smallest unit, and protect what carries hard value.** Cut
    cards, not sections. A statistic, a threshold or a user-authored tag is never
    dropped by a relevance score. Every drop goes to an audit file with its reason.

---

## Knowledge

13. **Setup runs once per company and is resumable.** Each stage writes a named
    file; a rerun reuses what exists and says "reused from the last run". A rebuild
    is an explicit request, never a side effect of a new conversation.

14. **Knowledge is built from the company's own material by the same process every
    time.** The SEO Writer's brand files come from twelve builders reading the
    catalogued pages. They are files a person can open, read and edit in the app,
    and the edited version is the truth from then on.

15. **Meaning is indexed, not matched by words.** Anything the agent must find "the
    right one of" (a page to link, a passage to cite, a product to name) is
    embedded once and searched by vector, then re-ranked on the full text. Word
    overlap was measured and thrown out.

16. **Knowledge is visible.** The person can open the company record, the
    catalogue with its coverage gates, the index and its map, and every built file.
    If the agent knows it, the person can see it.

---

## Memory

17. **Memory is a short list of standing rules, and it reaches the work.** A rule
    the person saves once ("never use the word leverage", "British spelling") is
    rendered into the system prompt and into every prompt that shapes or writes
    output, and into the research prompts that decide topic and angle. A rule that
    only reaches the chat is not a rule.

18. **Memory is toggled, never silently dropped.** The list is visible, each rule
    can be switched off, and the agent says which rules it applied.

---

## The run folder

19. **The folder is the whole truth.** `state.json` (status, stage, what it waits
    on), `events.jsonl` (every step, sub-step, note, question and answer, append
    only), `artifacts/` (the outputs the person reviews), `artifacts/_work/` (every
    intermediate, one named file per step). Anyone can point at any output and name
    the step that made it.

20. **Every write is atomic.** Temp file in the same directory, then rename. A file
    that exists is complete. Resume trusts that.

21. **Artifacts are the unit of review and the unit of testing.** The screen renders
    them. The tests render them from fixtures captured from a real run. A field the
    screen needs is a field the artifact has, or the test fails.

---

## Checkpoints

22. **Few, fixed, and enforced by the loop.** Setup has one (the brand pack). Each
    job has four (topic, brief, plan, draft). The model cannot add or skip one.

23. **Approve, edit, or send back, in the panel.** The person edits the artifact in
    place and approves; the loop hands the model what is on disk, not what the
    model remembers writing. "Ask for changes" carries the person's words back as
    the next instruction.

24. **The agent may ask one question of its own when it sees a real problem.** The
    SEO Writer noticed its plan had lost the formula section and asked before a
    forty-minute write. That is a good question. "Which of these five formats do you
    prefer?" is not. Smart and few.

25. **Approval has consequences in code.** Approving the draft saves it to the
    Library. Approving a paid step, where one exists, sticks for the run. The
    person's click does the thing; the model is told afterwards.

---

## The screen

26. **The screen projects the folder and holds no state.** All state lives in one
    object read from the API. Refresh, close, reopen: the same picture.

27. **Plain English everywhere the person reads.** Step labels, tool rows, error
    messages, checkpoint prompts. "The site refused the crawler, so I am reading it
    through the app's browser" beats "HTTP 429".

28. **Honest numbers, visibly labelled.** Demo data is marked demo at every step it
    touches. A check that could not run says "not checked: <why>" rather than
    passing or failing.

---

## The checks: how we know the rules held

None of the above counts until it is checked. The gate, in the order it runs:

| Check | What it proves | How |
|---|---|---|
| Engine suites, model switched off | Every rule in code holds without a model: gates, atomic writes, checkpoints, filters, link integrity, the Knowledge block in the prompt, save-on-approval | `tests/run_all.sh` in a throwaway data dir, `SEO_AGENT_NO_CLI=1`. Eleven suites, 500+ checks |
| Route tests | The API validates ids, hides secrets, returns the right codes, saves to the Library once | `test_<agent>_api.py` |
| Screen tests, two levels | L1: the projections from events to rows agree with the engine byte for byte. L2: the rendered DOM shows every field the artifact carries | `test_<agent>.js` on fixtures captured from a real run |
| Full test gate against a baseline | Nothing else in the app broke. Failures are compared by name against the known list, never by count alone | `pytest -q`, all `node test_*.js` |
| One real run, watched to the end | The chain works on a real site with a real model: setup, every checkpoint, the finished output, the Library entry | A watcher on the run's events; every checkpoint answered; every artifact opened |
| Screenshots, light and dark | Every view renders, nothing overflows, the panel opens at each checkpoint | `shots.py` per view |
| Findings written down | Every bug the run exposed is in HISTORY with what was done. Every limit is under "Not done" | `HISTORY.md`, the game plan's verification table |
| Release guard | Both manifests carry the tag's version or the build refuses | `release-dmg.yml` |

Two habits make the checks worth running. Compare pytest failures by name against a
saved baseline, because a count of 21 hides a new failure behind a fixed one. And
run the real run yourself, to the end, answering the checkpoints, because the bugs
that matter (the model narrating a save that never happened, a fresh chat redoing
setup, three fetchers where one had the fix) only show up when the whole thing runs.

---

## Things that only running it taught us

Each of these is a rule above. Each was learned the expensive way.

- The site refused every plain request. Reading it through the app's own hidden
  browser window fixed the crawl. Two other readers still failed until they shared
  the helper. (Rule 9.)
- A fresh chat redid the whole setup because nothing told the model it was done.
  (Rule 3.)
- The model said "Saved. It's in the Library." The Library was empty. (Rules 4, 25.)
- The brief said "angle missing" one step before the angle was written. Assemble
  after the step that settles the inputs. (Rule 19.)
- The coherence editor introduced two numbers the article never had. The integrity
  check caught it and the retry passed. (Rule 11.)
- Demo traffic named pages that do not exist, and a gate "failed" on every demo
  run. "Not checked: demo traffic" is the honest answer. (Rule 28.)
- The blueprint filter dropped 307 of 327 cards and that was right: every dropped
  card was demo text; the 20 kept were real. The audit file is how we knew. (Rule 12.)

---

## Where to go next

- To build one: `NEW-AGENT-plan.md`, the fifteen steps with the code.
- To read the contract the SEO Writer was built to: `seo_agent/CONTRACTS.md`.
- To see what happened when it ran: `seo_agent/HISTORY.md`.
- To read this without the code: `AGENT-PRINCIPLES-plain.md`.
