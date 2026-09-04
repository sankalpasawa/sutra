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

There are two places to put a behaviour: the prompt, or the code. The prompt is a
request that is usually honoured, and usually is not a guarantee. The code is a
fact, because no other path exists. Three of ours, and how they went:

| The behaviour | Where it lived | What happened |
|---|---|---|
| Show the draft before saving it | code: `show_artifact` cannot run without pausing | held every time |
| Never invent a number | code: the coherence pass diffs the numbers before and after and rejects the edit | caught two invented figures on the live run, retried, passed |
| Tell the user it was saved | prompt only | the model announced "Saved. It's in the Library" when nothing had been. Moved into the loop |

**The test to apply to anything you build.** If the model ignored this instruction,
would anything stop it? If the answer is no, and the rule matters, it is not a rule
yet.

---

## The loop

The loop is the manager. The model is the worker. Everything the agent is allowed
to do passes through here, and there is no model inside it: about a hundred lines
of ordinary code that read state, ask, run, record, repeat. The manager never asks
the worker whether a rule applies. It settles that with an if-statement.

### One pass, in order

1. **Read the state from disk.** Status, stage, current step. If the status is not
   `running`, return at once.
2. **Read the conversation so far.** Every message and every tool result, in order.
3. **Check the move counter.** 25 real steps in a row without checking in and it
   asks whether to continue. It never kills the run. The counter lives in memory and
   starts at zero on every pass, so answering a checkpoint resets it: 25 is a
   runaway guard between check-ins, not a budget for the job.
4. **Ask the model.** It is sent three things: the system prompt, the conversation,
   and the tool list. It replies with text and zero or more tool calls.
5. **Record how long the model took.** `model_turn` with the milliseconds. The one
   number nobody can reconstruct later; the first live run had an unexplained hour
   between two turns.
6. **No tool calls means the job is over.** Write the message, mark the run done,
   emit `run_finished`, return.
7. **Write down what the model decided, before running any of it.** If the machine
   dies mid-step the record already says what it was about to do.
8. **Run each tool call in turn**, by the branch table below.
9. **Hand the results back** as the next message, save to disk, and go to 1.

### The five branches, which are the whole permission model

| The call | What the loop does | Counts toward 25 |
|---|---|---|
| `ask_user` | Writes the question, stops, returns. Nothing else in the batch runs. | no |
| `show_artifact` | A checkpoint. Writes, stops, returns. | no |
| `log_step` | Writes a note into the log and carries on. Free. | no |
| `save_memory` | Stores the rule and carries on. Free. | no |
| anything else | Real work: emit `step_started`, import the module, run it, emit `step_finished` or `step_failed`. | yes |

There is no branch for "skip the checkpoint" or "run it twice because I forgot".
The list of branches is the list of things that can happen. Narration and memory
are free on purpose, so an agent that explains itself well is not punished for it.

**The honest edge.** Calling `show_artifact` always stops: that is code. Deciding
to call it after research is the prompt. A confused model could in principle run
`build_blueprint` without showing the brief first. It never has, and the stage bar
would show it, but until the loop refuses a stage whose predecessor was not
approved, that particular checkpoint is a prompt rule wearing a code rule's coat.

### Waiting is not waiting

When the agent needs the person, the process does not sleep.

- `_wait()` writes `status="waiting"` and a `waiting_on` block saying what for,
  emits one `waiting` event, and **returns**. The call stack unwinds to nothing.
- No thread, no timer, no held connection. The machine can be shut down.
- The answer arrives later at `resume()`, which reads the run back from disk and
  drops the answer in **as the return value of the tool call that paused**.
- So from the model's side: it called `show_artifact` and the call returned
  `{"approved": true}`. It cannot tell whether that took two seconds or eight hours.

### The three files, and who reads which

"The log" is three files with three different readers. Sizes are from the live
article run on 2026-09-04.

| File | Size | Read by | Holds |
|---|---|---|---|
| `chats/<chat>/messages.json` | 84 KB | the model | the conversation: every message, tool call and tool result |
| `runs/<run>/events.jsonl` | 44 KB | the person, through the screen | the run log: steps, sub-steps, notes, questions, answers. Append only |
| `runs/<run>/state.json` | 4 KB | the code | the bookmark: status, stage, current step, what it waits on |

The model never reads the run log. The person never reads the conversation. The
code needs only the bookmark to find its place. Step 7 above is the one thing
written to two of them at once: into the conversation so the model remembers what
it asked for, and into the log so the person sees the step begin.

### One real run, traced

The article run of 2026-09-04, through the branches above:

| The model called | The loop did | Where it stopped |
|---|---|---|
| `run_research` | ran it: 11 minutes, 327 evidence cards | |
| `show_artifact` (brief) | wrote, stopped, returned | waiting |
| | `resume` on approval, answer handed back as the call's result | |
| `build_blueprint` | ran it: 6 sections from 20 of 327 cards | |
| `show_artifact` (plan) | wrote, stopped, returned | waiting |
| `ask_user` | the model had spotted the plan losing the formula section, and asked before a 40-minute write | waiting |
| `write_article` | ran it: 8 sections, the coherence edit rejected once for two invented numbers, passed on retry | |
| `show_artifact` (draft) | wrote, stopped, returned | waiting |
| | on approval the loop saved to the Library itself, then told the model | |
| (no tool calls) | closing message, status done | finished |

### The rules this enforces

1. **Code drives, the model chooses.** The loop owns the sequence. The model picks
   from a list. It cannot invent a step, skip a checkpoint, or repeat one because
   it forgot.

2. **A checkpoint is a write, not a wait.** See above. The app can be closed
   mid-run and nothing is lost.

3. **The model cannot see the disk. Tell it.** A fresh conversation starts with no
   idea what Knowledge holds. If setup is finished the system prompt says so in one
   sentence, with the numbers, or the model redoes an hour of work. Any state that
   should stop it redoing something has to be written into the prompt.
   (`loop._knowledge_block()`; found live on 2026-09-04.)

4. **The model only learns what happened from tool results.** It never announces an
   outcome the code did not report. Saving to the Library is done by the loop on
   approval and appears in the tool result; the model may say "saved" only after it
   sees that. (Found live: it said "Saved" after an approval that saved nothing.)

5. **Recoverable is not fatal.** An overloaded model, a 429, a slow page: retry with
   backoff and say so in the log. Only a login failure is a login failure.

6. **A cap on unattended moves asks, it does not kill.** Twenty-five, as above.

---

## The tools

### What a tool is

A tool is a function: `run(ctx, **kw) -> {"summary", ...}`. It takes inputs, does a
job, returns a short summary, and while it works it emits sub-steps with a plain
label and a note, so the run log reads like a person describing their work
("Reading the site catalogue, 400 pages with text").

The seven work tools of the SEO Writer. Nothing else is a tool:

| Tool | What it does |
|---|---|
| `index_site` | Reads every page of the site: CMS API, sitemaps, web archive, crawl, with coverage gates |
| `build_page_index` | Turns those pages into meaning vectors, one per title and many per body |
| `learn_brand` | Builds the brand files from those pages, twelve builders |
| `suggest_topics` | Proposes what to write about |
| `run_research` | Researches one topic into a brief plus evidence cards |
| `build_blueprint` | Turns the research into a plan: filter, cluster, name, order, attach links |
| `write_article` | Writes the draft, edits it, places internal links, assembles it |

Beside them sit four the loop handles itself and never counts as work: ask the
person a question, show them an artifact, narrate a step, save a memory rule.

### Where the rules live: three different things called "rule"

| Kind | Lives in | About | Example |
|---|---|---|---|
| Loop rules | `loop.py`, one file | the sequence | stop on a checkpoint; count the moves; save after every step |
| Tool rules | inside each tool | the work itself | the coverage gates in `index_site`; the invented-number check in `write_article`; the PROTECT list in `build_blueprint` |
| Memory rules | text, not code | the person's standing preferences | "British spelling" |

A rule that would apply to any agent belongs in the loop. A rule about this
particular work belongs inside that particular tool. The loop neither knows nor
cares what a tool does inside itself.

### The rules

8. **The registry is the truth about tools, and the Tools screen is the registry.**
   Every tool has a `plain` row: what it does, when it runs, what it needs, how
   long it takes. The model sees name, description and inputs, never cost or gate.
   The person sees the plain row. One list, two audiences, no second copy to drift.

9. **Every step that touches the network goes through one helper.** The SEO Writer
   learned to read a site behind a bot wall in its crawler and still failed in two
   other readers that fetched on their own, so every own-site source in the article
   came back unreadable on a site we had already read. One fetch helper, one
   fallback, called from everywhere. The same holds for one paid-API client and one
   model caller.

10. **Paid steps check the balance first and say plainly when they skipped.** No
    credit gates, no approvals for money. The pre-flight is code; the message is
    plain English; the run continues with whatever the step could do. On the live
    run the balance was below zero, so the numbers came from demo data, labelled
    demo at every step that touched them, and the article still finished.

11. **Nothing is invented. Code counts, an AI judges, a source backs every number.**
    - Code counts: word counts, link counts, similarity scores, page lists. Never
      ask a model to count; it approximates.
    - An AI judges: relevance, quality, fit. Once, with the criteria in front of it.
    - Sources back numbers: any figure in the output traces to a page a tool read,
      or it is cut.
    - And a guard on top: after an editing pass the code diffs the numbers before
      and after, and an edit that introduced one is rejected and retried. It fired
      on the live run (invented 14,000 and 4,000), and the retry was clean.

12. **Filter at the smallest unit, and protect what carries hard value.** The
    blueprint's card filter is the worked example, and it is a step inside
    `build_blueprint`, not a tool of its own:
    - The unit is one card, one fact. Never a section: a good fact hides inside a
      bad section, and cutting the section takes it too.
    - The AI scores each card 0 to 5 against one question, does this serve the
      spine, and marks it protected or not. **The code does the cutting**: score at
      or below the threshold and not protected means dropped.
    - PROTECT overrides the score entirely: a number, a percentage, a threshold, a
      statistic, a sample item, or a card the earlier steps tagged `gap` or
      `competitor`. Eight cards were protected on the live run.
    - An unscored card is KEPT. Silence never deletes.
    - A scorer that crashes ABORTS the step (fail closed). It must never default to
      keeping everything: a broken run that kept all 327 cards would produce a
      bloated plan indistinguishable from a good one.
    - Every drop goes to an audit file with its reason, and dropping more than 60%
      raises a flag. The live run dropped 93.9%, flagged, and the audit showed the
      filter was right: every dropped card was demo text, all 20 kept were real.

---

## Knowledge

Knowledge is what the agent learned about this company once and keeps. It is
distinct from Memory, which is what the person told it to do.

13. **Setup runs once per company and is resumable.** Setup is expensive: about an
    hour for a 400-page site. Every stage writes its own named file (the sitemap
    list, the archive list, the settled page list, the extracted text), and a rerun
    checks for that file first, reuses it, and says "reused from the last run". A
    crash costs only the stage that was running. A rebuild is an explicit request,
    never a side effect of a new conversation.

14. **Knowledge is built from the company's own material by the same process every
    time.** The brand files are not written from the model's general knowledge; they
    are built by twelve builders reading the catalogued pages. Each is a file the
    person can open, read and edit in the app, and the edited version is the truth
    from then on. Nothing overwrites a file a person has touched.

15. **Meaning is indexed, not matched by words.** Anything the agent must find "the
    right one of" (a page to link, a passage to cite, a product to name) is embedded
    once and searched by vector, then re-ranked on the full text. Word overlap was
    measured in the original workflow and thrown out: "work sample test" matched a
    job-simulation page, which is a different product. For Testlify: 400 pages,
    1,050 body passages. The live article searched 31 candidate pages by meaning and
    placed 6, each shown with its match score.

16. **Knowledge is visible.** The company record the person can edit, the catalogue
    with its coverage gates and a search box, the index and its map, and every built
    file. If the agent knows it, the person can open it. There is no hidden state.

---

## Memory

17. **Memory is a short list of standing rules, and it reaches the work.** A rule
    the person saves once ("never open with a question", "British spelling") is
    rendered into the system prompt and into every prompt that shapes or writes
    prose, and into the research prompts that decide topic, angle, persona and which
    facts survive. The easy mistake is to put it in the chat prompt only: the model
    then knows the rule while chatting, and the section-writing call, which is a
    separate model call, has never heard of it. A rule that only reaches the chat is
    not a rule.

18. **Memory is toggled, never silently dropped.** The list is visible, each rule
    can be switched off, and only active rules are rendered.

### How a saved rule actually reaches a prompt, and what that mechanism is not

Be straight about this one: **there is no routing. It is paste-everywhere into a
hand-picked list of prompts.**

- Saving appends one line to `memory.jsonl`: id, timestamp, text, `active: true`.
  Nothing is categorised or tagged.
- `sh.memory_block()` collects every active rule as a bulleted list.
- That one list is substituted for `{{MEMORY}}` in **38 of the 117 prompts**. All
  rules go into all 38. No rule is ever matched to a particular step.
- The 38 were chosen by hand: everything that writes or shapes prose, plus the
  research steps that decide topic, angle, persona and card relevance. The other 79
  are data-shaped steps (classify a page type, parse a sitemap, pull keyword
  numbers) where a writing rule means nothing.
- Placement is the one piece of real design. The block sits near the end under
  "THE USER'S STANDING RULES ... they win over any rule above that they contradict",
  so the person's rules explicitly outrank the prompt's own instructions.

**What is missing, and worth knowing before relying on it:**

- No scoping: a spelling rule is pasted into the keyword scorer as well as the
  writer.
- No conflict detection: two contradictory rules are both pasted.
- No verification: nothing checks afterwards that the rule was followed. By this
  document's own first rule that makes it a suggestion, not a rule.
- It does not scale: three rules is nothing, fifty rules in every prompt is noise
  the model starts skimming.
- It has never run live. The plumbing has tests; no real user rule has been through
  a real article.

**The two upgrades, if it matters later:** tag each rule on save (writing /
research / both) and paste only the relevant ones; and for rules a machine can
check (banned words, spelling variant), add a code check after the writing pass, the
way the invented-number check works. That is what turns it into a real rule.

---

## The run folder

19. **The folder is the whole truth.** The three files are in "The loop" above;
    beside them sit `artifacts/` (the outputs the person reviews) and
    `artifacts/_work/` (every intermediate, one named file per step). Anyone can
    point at any output and name the step that made it.

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
