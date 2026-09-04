---
type: principles (plain English)
reusable: yes
reads: AGENT-PRINCIPLES.md is the same document with the file names and code in it
produces: the rules we follow when we build any agent, and how we check them
last_updated: 2026-09-04
---

# How we build an agent, in plain English

This is the short version. Same headings, same order as `AGENT-PRINCIPLES.md`, so
if you want the code behind anything here, look for the same heading there.

It was written from one agent we built and ran to the end, the SEO Writer. But
nothing in it is about SEO. The same shape builds an agent for research, support,
bookkeeping, anything.

---

## What an agent is

Think of a careful new employee. You give them a job that takes an hour by hand.
They do it in named steps, out loud, and at four or five moments they stop and
show you the work before going on.

An agent is made of seven parts. Most important first:

| Part | What it is |
|---|---|
| The loop | The manager. Asks the AI what to do next, does that one thing, writes down the result, asks again. The loop enforces every rule. |
| The tools | The only things the agent can do. Each one has a plain description you can read on the Tools screen. |
| Knowledge | What the agent learned about your company once and keeps. The list of your pages, the index of what they mean, the brand files. |
| Memory | Standing rules you gave it. Short, few, and applied to every piece of work. |
| The run folder | The complete record of one job. What happened, in what order, and every file it made. |
| Checkpoints | The moments it stops and shows you the work. |
| The screen | A window onto the run folder. It remembers nothing itself. |

The AI is the eighth thing, and last on purpose. It chooses which tool to run next
and writes the words. It never decides whether a rule applies.

---

## The one rule above the others

**A rule you ask the AI to follow is a suggestion. A rule the code enforces is a
rule.**

Everything below is that sentence applied to each part. If a rule matters, it is in
the code and there is a test for it. The instructions to the AI may repeat it, but
the instructions are never what makes it true.

---

## The loop

1. **Code drives, the AI chooses.** The loop runs the sequence. The AI picks the
   next tool from a list. It cannot invent a step, skip a checkpoint, or run
   something twice because it forgot.

2. **Stopping for you is a note, not a held door.** When the agent needs you, it
   writes down where it got to and stops. Nothing sits open. When you answer, it
   picks up from the note. You can close the app mid-run and lose nothing.

3. **The AI cannot see the files. Tell it.** A new chat starts blank. If setup is
   already done, the agent's instructions say so in one sentence with the numbers,
   or it redoes an hour of work. We learned this by watching it happen.

4. **The AI only knows what the code tells it.** It never announces something the
   code did not report. Saving to the Library happens in code when you approve, and
   the AI is told afterwards. Before that fix it once said "Saved" when nothing was.

5. **A hiccup is not a failure.** An overloaded AI, a slow website, a rate limit:
   wait, try again, say so in the log. Only a wrong password is a wrong password.

6. **Too many steps without you and it asks.** Twenty-five real steps without a
   checkpoint and the agent asks whether to keep going. It does not stop dead.

---

## The tools

7. **A tool does one thing and reports as it goes.** While it works, it writes
   short lines into the log: what it did and what it found. The log reads like a
   person describing their work.

8. **The Tools screen is the tool list.** Every tool has a plain row: what it does,
   when it runs, what it needs, how long it takes. That row is the only description
   anywhere.

9. **Anything that touches the internet goes through one door.** We fixed a
   blocked website in the crawler and it was still blocked in two other places that
   fetched pages on their own. Now there is one helper and everything uses it. Same
   for paid services and for calling the AI.

10. **Paid steps check the balance first and say when they skipped.** No stopping
    to ask about credits. The check is code, the message is plain English, and the
    job carries on with what it could do.

11. **Nothing is made up. Code counts, the AI judges, a source backs every
    number.** Word counts, link counts and page lists come from code. The AI decides
    what is relevant or good, once, with the criteria in front of it. Every number in
    the output traces to a page the agent read, or it is cut. If an edit slips in a
    number that was not there before, the edit is rejected and redone.

12. **Cut at the smallest piece and protect the valuable ones.** Drop single facts,
    not whole sections. A statistic or a number is never dropped for being
    "off-topic". Every drop is written to an audit file with the reason.

---

## Knowledge

13. **Setup runs once per company and picks up where it left off.** Each stage
    writes a file. Run it again and it reuses what exists and says so. Rebuilding is
    something you ask for, never a side effect.

14. **Knowledge comes from your own material, the same way every time.** The brand
    files are built by reading your pages. They are files you can open, read and
    edit in the app, and your edits are the truth from then on.

15. **Find things by meaning, not by matching words.** Whenever the agent has to
    pick "the right one" (a page to link to, a passage to quote) it searches by
    meaning and then double-checks on the full text. Matching words was tried and
    measured and it was wrong too often.

16. **You can see everything the agent knows.** The company record, the page list
    with its coverage checks, the index and its map, every built file.

---

## Memory

17. **Memory is a short list of rules, and the rules reach the work.** Save a rule
    once ("British spelling", "never say leverage") and it goes into every step
    that writes or shapes output, and into the research steps that pick the topic.
    A rule that only reaches the chat is not a rule.

18. **Rules are switched off, never quietly dropped.** The list is visible, each rule
    has a toggle, and the agent says which rules it applied.

---

## The run folder

19. **The folder is the whole truth.** The status. Every event in order. The outputs
    you review. Every in-between file, one per step. You can point at anything in
    the output and name the step that produced it.

20. **Files are written safely.** Write to a temp file, then rename. A file that
    exists is complete. That is what lets a run resume without repeating work.

21. **The outputs are what you review and what we test.** The screen shows them. The
    tests render them from a real run we saved. If the screen needs a field the
    output does not have, the test fails.

---

## Checkpoints

22. **Few, fixed, enforced.** Setup has one: the brand files. Each job has four: the
    topic, the research brief, the plan, the draft. The AI cannot add or skip one.

23. **Approve, edit, or send back, right there.** Edit the work in the panel and
    approve, and the agent continues from your version. "Ask for changes" sends your
    words back as its next instruction.

24. **It may ask one question when it sees a real problem.** Our agent noticed its
    plan had lost the main section and asked before a forty-minute write. That is a
    good question. "Which of these five formats would you like?" is not. Smart and
    few.

25. **Approving does something.** Approve the draft and it is saved to the Library
    by the code. The AI is told afterwards.

---

## The screen

26. **The screen shows the folder and keeps nothing.** Refresh, close, reopen: same
    picture.

27. **Plain English wherever you read.** Step names, tool rows, errors, questions.
    "The site refused the crawler, so I am reading it through the app's browser"
    rather than an error code.

28. **Honest numbers, clearly labelled.** Demo data says demo at every step. A check
    that could not run says "not checked" and why, instead of pretending.

---

## The checks: how we know the rules held

None of the above counts until it is checked. In the order we run them:

| Check | What it proves |
|---|---|
| Engine tests with the AI switched off | Every rule in the code holds with no AI at all: the checkpoints, the safe writes, the filters, the link checks, the "setup is done" note, the save-on-approve. Eleven suites, over five hundred checks. |
| Route tests | The web layer checks ids, hides passwords, returns the right answers, saves to the Library once. |
| Screen tests, two levels | First, the screen's reading of events matches the engine's exactly. Second, the rendered page shows every field the output carries. Both run on a real run we saved. |
| The full app test gate, against a baseline | Nothing else broke. Failures are compared by name to the known list, never by count. A count of 21 can hide a new failure behind a fixed one. |
| One real run, watched to the end | The whole chain works on a real website with a real AI. We answer every checkpoint ourselves and open every output. |
| Screenshots, light and dark | Every view renders, nothing spills over, the panel opens at each checkpoint. |
| Findings written down | Every bug the run exposed is in the history file with what we did about it. Every limit is listed under "Not done". |
| Release guard | The build refuses a version tag that does not match both version files. |

The bugs that matter only show up in the real run. The AI claiming a save that never
happened, a fresh chat redoing setup, a fix applied in one of three places. No unit
test finds those. Running it to the end, yourself, does.

---

## Things that only running it taught us

- The website refused every ordinary request. Reading it through the app's own
  hidden browser window fixed the crawl. Two other page readers stayed broken until
  they used the same helper.
- A fresh chat redid the whole setup because nothing told the AI it was done.
- The AI said "Saved. It's in the Library." The Library was empty.
- The research brief said "angle missing" one step before the angle was written.
- The editing pass slipped in two numbers the article never had. The integrity check
  caught it, and the retry passed.
- Demo data named pages that do not exist and a check "failed" on every demo run.
  "Not checked: demo data" is the honest answer.
- The plan filter dropped 307 of 327 facts. That was right: every dropped fact was
  demo text, and the 20 kept were real. The audit file is how we knew.

---

## Where to go next

- To build one, step by step: `NEW-AGENT-plain.md`.
- To see what happened when the SEO Writer ran: `seo_agent/HISTORY.md`.
- For the version with the code and file names: `AGENT-PRINCIPLES.md`.
