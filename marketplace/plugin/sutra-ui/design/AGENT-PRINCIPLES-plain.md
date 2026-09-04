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

### What a tool is

A tool is a function. It takes some inputs, does one job, and hands back a short
summary. While it works it writes short lines into the log, like "reading the site
catalogue, 400 pages with text". That is why the log reads like a person talking
instead of a progress bar.

The seven tools of the SEO Writer. Nothing else is a tool:

| Tool | What it does |
|---|---|
| Read the website | Every page: the CMS, the sitemaps, the web archive, a crawl, with coverage checks |
| Index by meaning | Turns those pages into numbers that capture meaning |
| Learn the brand | Builds the brand files from those pages |
| Suggest topics | Proposes what to write about |
| Research | Researches one topic and gathers the facts |
| Build the plan | Turns the research into an outline with links attached |
| Write the article | Writes it, edits it, places the internal links |

Next to those are four things the loop handles itself, which never count as work:
ask you a question, show you something, narrate a step, save a rule you gave.

### Where rules live: three different things get called "rule"

| Kind | Lives in | About | Example |
|---|---|---|---|
| Loop rules | the loop, one file | the order of things | stop at a checkpoint, count the steps, save after each one |
| Tool rules | inside each tool | the work itself | the coverage checks when reading a site, the made-up-number check when writing, the protect list when filtering |
| Your rules | plain text, not code | your standing preferences | "British spelling" |

A rule that would apply to any agent goes in the loop. A rule about this particular
job goes inside that particular tool. The loop does not know or care what a tool
does inside itself.

### The rules

8. **The tool list is the Tools screen.** Every tool has a plain row: what it does,
   when it runs, what it needs, how long it takes. That row is the only description
   of it anywhere. The AI gets a shorter view with no mention of cost. One list,
   two audiences, nothing to drift out of date.

9. **Anything that touches the internet goes through one door.** We fixed a blocked
   website in the crawler and it stayed broken in two other places that fetched
   pages on their own, so every source in the article came back unreadable on a site
   we had already read successfully. Now there is one helper and everything uses it.
   Same for anything paid, and for calling the AI.

10. **Paid steps check the balance first and say when they skipped.** No stopping to
    ask about credits. If there is not enough, the step skips that bit, says so in
    plain English, and the job carries on. On the live run the balance was below
    zero, so it used demo numbers, labelled them demo everywhere they appeared, and
    still finished the article.

11. **Nothing is made up. Code counts, the AI judges, a source backs every number.**
    - Code counts. Word counts, link counts, page lists, match scores. Never ask the
      AI to count. It approximates.
    - The AI judges. Is this relevant, is this good, does this fit. Real judgement,
      decided once, with the criteria in front of it.
    - Sources back numbers. Every figure traces to a page the agent actually read,
      or it gets cut.
    - Plus a guard: after any editing pass the code compares the numbers before and
      after, and rejects an edit that introduced a new one. It fired on the live run
      when the editor invented 14,000 and 4,000. The retry was clean.

12. **Cut the smallest piece, and protect the valuable ones.** The plan's filter is
    the example, and it is a step inside the plan-building tool, not a tool of its
    own:
    - The unit is one fact, never a section. A good fact hides inside a bad section,
      and cutting the section throws it away too.
    - The AI scores each fact 0 to 5 on one question: does this serve the article's
      argument. It also marks each one protected or not. **Then the code does the
      cutting.** Low score and not protected means gone. The AI never gets to say
      "keep this one anyway".
    - Protected beats the score every time: anything with a number, a percentage, a
      threshold or a statistic, and anything an earlier step tagged as a gap or a
      competitor. Eight facts were protected on the live run.
    - A fact the AI failed to score is kept. Silence never deletes anything.
    - If the scorer crashes, the whole step stops. It does not fall back to keeping
      everything, because a broken run that quietly kept all 327 facts would produce
      a bloated plan that looks exactly like a good one.
    - Every dropped fact is written to a file with the reason, and dropping more
      than 60% raises a flag. The live run dropped 93.9%, flagged it, and told me to
      look. I looked: every dropped fact was demo junk and all 20 kept were real.

---

## Knowledge

Knowledge is what the agent learned about your company once and keeps. Different
from Memory, which is what you told it to do.

13. **Setup runs once per company and picks up where it left off.** Setup is slow,
    about an hour for a 400-page site, so it runs once. Every stage writes its own
    file. Run it again and each stage checks whether its file is already there,
    reuses it, and says "reused from the last run". If it crashes you lose only the
    stage that was running, not the hour. Rebuilding is something you ask for out
    loud. It never happens by accident.

14. **Knowledge comes from your own material, the same way every time.** The brand
    files are not the AI writing from general knowledge. They are built by twelve
    builders reading your actual pages. Each one is a file you can open, read and
    edit in the app, and once you edit it, your version is the truth. Nothing
    overwrites it.

15. **Find things by meaning, not by matching words.** Whenever the agent has to
    pick "the right one" (a page to link to, a passage to quote) it searches by
    meaning and then double-checks against the full page text. Word matching was
    tried and measured in the original workflow and it was wrong: "work sample test"
    matched a job-simulation page, which is a different product. For Testlify that
    is 400 pages and 1,050 passages. The live article found 31 candidate pages by
    meaning and placed 6, each with its match score shown to you.

16. **You can see everything the agent knows.** The company record you can edit, the
    full page list with a search box, the coverage checks and whether they passed,
    the meaning index with a visual map, and every brand file. No hidden state.

---

## Memory

17. **Memory is a short list of your standing rules, and the rules reach the work.**
    Save a rule once ("never open with a question", "British spelling") and it goes
    into every step that writes or shapes words, and into the research steps that
    pick the topic and the angle. The easy mistake is to put your rules only in the
    chat instructions. Then the AI knows the rule while chatting, but the step that
    writes a section is a separate call to the AI, and it has never heard of it. A
    rule that only reaches the chat is decoration.

18. **Rules are switched off, never quietly dropped.** The list is on screen, each
    rule has a toggle, and only the ones switched on are used.

### How a saved rule actually reaches a prompt, and what it is not

Being straight about this one: **there is no clever routing. Every rule is pasted
into every one of a hand-picked set of prompts.**

- Saving adds one line to a file: id, time, your words, switched on. Nothing is
  categorised or tagged.
- Before each of those steps runs, the code collects every switched-on rule into a
  bulleted list.
- That same list goes into **38 of our 117 prompts**. All rules into all 38. No rule
  is ever matched to a particular step.
- Those 38 were picked by hand: everything that writes or shapes words, plus the
  research steps that choose the topic, the angle, the reader and which facts
  survive. The other 79 are data steps, like sorting page types or pulling keyword
  numbers, where a writing rule means nothing.
- The one real piece of design is where it sits. Your rules go near the end, under a
  line saying they beat any instruction above them that they contradict. So your
  rules outrank the prompt's own.

**What is missing, worth knowing before you lean on it:**

- No scoping. A spelling rule is pasted into the keyword step as well as the writer.
- No conflict check. Two contradictory rules both get pasted and the AI picks.
- No verification. Nothing checks afterwards that the rule was followed. By this
  document's own first rule, that makes it a suggestion rather than a rule.
- It does not scale. Three rules is fine. Fifty in every prompt becomes noise the AI
  starts skimming.
- It has never run for real. The plumbing is tested, but no rule of yours has ever
  been through a real article.

**The two upgrades if it ever matters:** tag each rule when you save it, so only the
relevant ones get pasted; and for rules a machine can check, like a banned word, add
a code check after the writing pass, the way the made-up-number check works. That is
what turns it into a real rule.

---

## The run folder

19. **The folder is the whole truth.** One job, one folder. Next to the three files
    described under "The loop" sit two more things. The outputs you review, like the
    brief, the plan and the draft. And every in-between file, one per step: 23 of
    them on the live run. Why keep all that? So you can point at any sentence in the
    article and trace it back. That line came from fact 221, which came from the
    evidence step, which came from reading that page. Those files are also what make
    a rerun cheap, because each step checks its own file first.

20. **Files are written safely.** Never write straight into the real file. Write a
    temp file next to it, then rename it over the top. Renaming is instant and
    cannot half-happen, so the file is either the old one or the new one, never a
    broken mix. This matters because resume trusts "the file is there, so that step
    is done". Without it, a crash mid-write leaves half a file that the next run
    reads as finished. That is silent corruption, the worst kind.

21. **The outputs are what you review and what we test.** The screen shows them, and
    the tests render them from a real run we saved. Add something to the screen that
    the output does not actually carry and the test fails straight away, instead of
    you finding a blank box in the app.

---

## Checkpoints

22. **Few, fixed, and the stop is enforced by code.** One in setup, the brand files.
    Four per article: the topic, the research, the plan, the draft. Few on purpose,
    because too many and you stop reading them, which is worse than having none.

    Where they are actually written is worth knowing, because it is split in two:
    - **The list is in the AI's instructions.** They say, in order: research, then
      show the brief; build the plan, then show it; write the article, then show the
      draft. And then: four stops per article, do not invent extra ones.
    - **The stopping is in the code.** The moment the AI asks to show you something,
      the loop writes its note and stops. Nothing can keep the job running.
    - So the stopping is guaranteed and the list is not. Making the code refuse a
      step whose previous step was never approved is about ten lines of work, and
      until that is written this rule is half instruction.

23. **Approve, edit, or send it back, right there.** When you edit something in the
    panel and approve, the code reads **the file on disk** and hands the AI that,
    not what the AI remembers writing. Your edit is the truth. If instead you ask for
    changes, your words go back as the next instruction and it redoes that step.

24. **The agent may ask one question of its own when it spots something real.** On
    the live run the plan came out with no formula section, for an article about how
    to calculate a formula. The agent noticed and asked before starting a
    forty-minute write. That is a good question: it saved real time, and nobody would
    have caught it without reading the plan closely. "Which of these five formats
    would you like?" is a bad question. That is handing its job back to you.

    The test: would answering save real work, or is it asking you to decide something
    it should be deciding?

    What happened next is worth recording. I answered it (demo run, carry on) and
    **changed no code**. The plan had lost the formula because the demo facts were
    junk, and with real facts those would have scored high. The writer then put the
    formula and the worked examples back in by itself, and the agent said so at the
    end: a good outcome that happened by accident. The gap it exposed, which is still
    not built, is that nothing checks the plan still answers the question the main
    keyword asks. The only thing that caught it was the AI noticing.

25. **Approving is an action, not a message.** If a click is meant to make something
    happen, the code does it, and the AI is told afterwards.

    The bug behind this rule: approving the draft used to just tell the AI
    "approved", and the AI reasonably replied "Saved. It's in the Library." Nothing
    had been saved. Saving was a separate button. Now the code saves it the moment
    you approve, then tells the AI it saved it and what it called it. So the AI can
    only say "saved" because the code that did the saving told it so.

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
