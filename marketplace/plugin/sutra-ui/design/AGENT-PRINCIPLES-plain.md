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

There are only two places to put a behaviour: in the instructions, or in the code.
Instructions are a request. The AI usually follows them, and usually is not a
guarantee. Code is a fact, because there is no other way for it to go. Three of
ours, and how they turned out:

| What we wanted | Where we put it | What happened |
|---|---|---|
| Show you the draft before saving | code. Showing you always stops the job | worked every time |
| Never make up a number | code. It compares the numbers before and after an edit and rejects new ones | caught two made-up figures on the live run, redid it, passed |
| Tell you it was saved | instructions only | the AI said "Saved. It's in the Library" when nothing was saved. We moved it into code |

**The test for anything you build.** If the AI ignored this instruction, would
anything stop it? If not, and the rule matters, it is not a rule yet.

---

## The loop

The loop is the manager. The AI is the worker. Everything the agent is allowed to
do goes through here, and there is no AI inside it. About a hundred lines of
ordinary code: read where we are, ask, do one thing, write it down, ask again. The
manager never asks the worker whether a rule applies. It just enforces it.

### What one pass does, in order

1. **Read where it got to.** If the job is not running, stop right there.
2. **Read the conversation so far.** Every message and every result, in order.
3. **Check the step count.** 25 real steps in a row without checking in and it asks
   whether to carry on. It never kills the job. The counter starts at zero every
   pass, so answering a checkpoint resets it. 25 is a runaway guard between
   check-ins, not a budget for the whole job. Normal work uses about 6.
4. **Ask the AI.** It gets three things: its instructions, the conversation, and the
   list of tools. It answers with some words and zero or more tool calls.
5. **Write down how long the AI took.** We added this after one run had an
   unexplained hour between two turns and nobody could work out why.
6. **If it called no tools, the job is done.** Save its message, mark it finished.
7. **Write down what the AI decided, before doing any of it.** If the machine dies
   mid-step, the record already says what it was about to do.
8. **Do each tool call, one at a time**, by the table below.
9. **Hand the results back**, save everything, and start again from 1.

### The five kinds of tool call

This table is the whole permission system. There is nothing else.

| The AI asks for | What the loop does | Counts toward 25 |
|---|---|---|
| a question for you | writes the question down, stops, returns | no |
| to show you something | a checkpoint. Writes, stops, returns | no |
| to narrate a step | writes a note in the log and carries on. Free | no |
| to save a rule you gave | stores it and carries on. Free | no |
| anything else | real work. Starts it, runs it, records how it ended | yes |

There is no row for "skip the checkpoint" or "do it twice". The rows are the only
things that can happen. Narration and saving rules are free on purpose, so an agent
that explains itself well is not punished for it.

**One honest gap.** Showing you something always stops the job: that is code. But
*deciding* to show you after research comes from the AI's instructions. A confused
AI could in theory skip ahead. It never has, and you would see the stage jump on
screen, but that one checkpoint is an instruction pretending to be a rule. Fixing it
is about ten lines, if you want it.

### The important trick: waiting is not waiting

- Most systems would hold a process open while they wait for you.
- Ours does not. It writes a note saying "waiting, and here is what for", and then
  the code **stops and exits**.
- Nothing is running. No thread, no timer, no open connection. You can shut the
  laptop.
- When you answer, a separate piece of code wakes up, reads the whole job back off
  the disk, and slots your answer in **as the answer to the thing the AI asked for**.
- So from the AI's side: it asked to show you the brief, and got back "approved". It
  cannot tell whether that took two seconds or eight hours.

### The three files, and who reads which

"The log" is really three files with three different readers. Sizes are from the
real article run.

| File | Size | Who reads it | What it holds |
|---|---|---|---|
| the conversation | 84 KB | the AI | every message, every request, every result |
| the run log | 44 KB | you, on screen | steps, sub-steps, notes, questions, answers |
| the bookmark | 4 KB | the code | where it got to, and what it is waiting on |

- The AI never reads the run log. That log exists only to show you the work.
- You never read the conversation. It is raw and full of machine detail.
- The code only needs the bookmark to find its place again.
- Step 7 above is the one thing written to two places at once: to the conversation
  so the AI remembers, and to the log so you see the step begin.

### One real run, start to finish

| The AI asked for | What happened | Stopped? |
|---|---|---|
| research | 11 minutes, 327 facts gathered | |
| show me the brief | written, stopped | waiting for you |
| | you approve, the job is read back off disk and carries on | |
| build the plan | 6 sections kept from 20 of those 327 facts | |
| show me the plan | written, stopped | waiting for you |
| ask you a question | the AI had noticed the plan lost the main section, and asked before a 40-minute write | waiting for you |
| write the article | 8 sections. The editing pass slipped in two made-up numbers, was rejected, and passed on the retry | |
| show me the draft | written, stopped | waiting for you |
| | you approve, the code saves it to the Library, then tells the AI | |
| nothing | closing message, job done | finished |

### The rules this enforces

1. **Code drives, the AI chooses.** The AI picks from a list. It cannot invent a
   step, skip a checkpoint, or run something twice because it forgot.

2. **Stopping for you is a note, not a held door.** As above. Close the app mid-run
   and lose nothing.

3. **The AI cannot see the files. Tell it.** A new chat starts blank. If setup is
   already done, the instructions say so in one sentence with the numbers, or it
   redoes an hour of work. We learned this by watching it happen.

4. **The AI only knows what the code tells it.** It never announces something the
   code did not report. Saving to the Library happens in code when you approve, and
   the AI is told afterwards. Before that fix it once said "Saved" when nothing was.

5. **A hiccup is not a failure.** An overloaded AI, a slow website, a rate limit:
   wait, try again, say so in the log. Only a wrong password is a wrong password.

6. **Too many steps without you and it asks.** Twenty-five, as above.

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

19. **The folder is the whole truth.** The three files are described under "The
    loop" above. Next to them sit the outputs you review, and every in-between file,
    one per step. You can point at anything in the output and name the step that
    made it.

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
