---
type: recipe (plain English)
reusable: yes
reads: NEW-AGENT-plan.md is the same document with the code in it
produces: one new agent, running inside the Sutra app
last_updated: 2026-09-03
---

# Building another agent inside Sutra, in plain English

This is the readable version. It has the same sections in the same order as
`NEW-AGENT-plan.md`, so if you want the code for anything here, look for the same
heading there.

One agent exists today: the SEO Writer, shipped in version 2.239.0. Everything
below is what building it actually taught us.

---

## What this does

You take a job someone would otherwise do by hand over an hour, and you turn it
into an agent that does the work in front of them. Named steps. A running log.
Moments where the person looks at the work and either approves it or sends it
back before the next step runs.

An agent is four things, in order of how much they matter:

1. **A loop that enforces the rules in code.** Not a prompt that asks nicely.
2. **A list of tools** where each one carries the rule for when it runs, and a plain
   description a person can read on the Tools screen.
3. **A folder on disk** that is the complete truth about what happened.
4. **A screen** that just shows that folder. The screen remembers nothing itself.

---

## The one rule that governs everything

**A rule you ask the model to follow is a suggestion. A rule the code enforces is
a rule.**

So the model is never told what a step costs. It is never told which steps need
permission. And it never gets the chance to skip a checkpoint, because the code
stops it, not the instructions.

There is a second half to this. When the agent needs you, it does not sit there
waiting with a process held open. It writes down where it got to, and stops. When
you answer, it picks the folder back up and carries on. That is why you can close
the app mid-run and nothing is lost.

---

## Two ways in: pick one before you write anything

**Option A: another agent inside the Agents tab.** This is the intended path. Your
agent joins the list in the left column next to the SEO Writer. The catch is that
the screen currently assumes there is only one agent, so the first person to take
this path has to spend a day making that a proper list first.

**Option B: a whole new tab in the left rail.** This is what the SEO Writer did.
More registration steps, but no refactoring of anyone else's work.

Pick A if the job is agent-shaped: steps, checkpoints, something to review. Pick B
only if the surface is genuinely not a conversation with a review panel.

---

## What you end up with

One named thing per step, listed up front so nothing gets invented later.

| Step | What comes out of it |
|---|---|
| 1 | A plan document: the layout, the checkpoints, how you will check it works |
| 2 | The engine folder, with its memory, its loop, its tool list and its model caller |
| 3 | Every tool written down with its price and whether it needs permission |
| 4 | The tools themselves, one file each |
| 5 | The prompts, one file per model call |
| 6 | The engine's own tests, passing |
| 7 | The web routes so the app can talk to the engine |
| 8 | Tests for those routes |
| 9 | The screen and its stylesheet |
| 10 | A saved copy of a real run, to test the screen against |
| 11 | Tests for the screen |
| 12 | Small edits to six shared files so it loads and ships |
| 13 | The full test gate, green |
| 14 | Screenshots, a real run, and a written note of what that changed |
| 15 | Version bumped, changelog written, pushed, tagged, released |

---

## What you need before starting

- The job, described the way the person describes it. Not the way a system would.
- The four to six moments where a human has to see the work before it continues.
- Every step that costs money or takes more than a minute, with the number.
- Any logins the job needs. They get stored owner-only and never shown back on
  screen.
- One example of the finished output, made by hand, so you have something to judge
  quality against.

---

## The steps

### 1. Write the plan before the code

Fix the shape first, so building is assembly rather than discovery.

Copy the section list from the SEO Writer's plan document. The two tables that
matter most are the run log (what each kind of event looks like on screen) and the
checkpoints (what each review panel shows and what its buttons do).

If you cannot fill in the checkpoints table, the job is not agent-shaped yet. Stop
and describe the job again. The SEO Writer has five checkpoints: the brand pack after
setup, then for every article the topics, the research, the plan and the draft.

### 2. Build the engine on its own

The engine is a folder that knows nothing about the Sutra app. That is deliberate.
You can build it and test it completely on its own, then drop it in. The only
connection back to the app is one environment variable telling it where the
`claude` command lives.

Four things inside it.

**Memory.** Nothing lives in RAM. A run is a folder. One file says where we are.
One file lists everything that happened, one line per event. The conversation is
saved per chat, not per run, which is what lets one chat hold several runs that
remember each other.

Two details that look small and are not. The folder path is worked out fresh every
time it is asked for, never once at startup, because the installed app is
read-only and tests need their own folder. And every save writes to a temporary
file first, then swaps it into place. Otherwise a crash halfway through a write
leaves a half-written file that looks complete, and the next run trusts it.

Credentials get owner-only permissions. Always.

**The model caller.** It tries the `claude` command first, and only falls back to
an API key if there is no command. That order is what keeps everything on your
subscription instead of billing per token. The API key path exists for standalone
use and is switched off inside Sutra.

Two things learned the hard way here. The prompt goes in through standard input,
never on the command line. And when running inside another Claude session, you
have to strip the parent session's environment variables out, or the command
thinks your call is a child of it and behaves oddly. The API key gets stripped too,
so the command can never quietly bill the API.

When Anthropic is overloaded, that is weather, not a fault. Wait five seconds,
then fifteen, then forty, and say so in the log. Do not report it as "you are not
signed in". That bug shipped once.

**The loop.** It asks the model what to do, does it, hands back the result, and
asks again. Four rules live here and nowhere else.

Free steps do not count toward the limit. If the model narrates what it is doing,
that is a good habit and should not use up its budget.

The money check reads the current state fresh from disk at the moment of checking,
and reads the price from the tool list, never from anything the model said. Once
you approve a paid step, that approval sticks for the rest of the run, so it does
not nag you twice for the same thing.

There is a cap of twenty-five steps without checking in. Hitting it does not kill
the run. It asks you whether to keep going.

**Memory reaches the work, not just the chat.** A rule you save once is handed to every
step that shapes or writes prose: the plan, the headings, each section, the edits, the
intro and the close. It is also handed to the research steps that decide the topic and
the angle.

Credits are counted after a step succeeds, never before.

**Approval runs the step immediately.** When you say yes, the code runs the exact
call you approved, right then, and hands back the real result. It does not go back
to the model and hope it asks again. That wastes a turn, and worse, it gives the
model a chance to change its mind about something you just paid for.

When you say no, the step never runs, and the model is told plainly: they said no,
do not retry, offer something cheaper or ask what they would prefer.

**A tool that fails does not kill the run.** The error goes back to the model with
a note saying "tell the user what failed and what you will try instead". Failures
that the agent can recover from show amber. Failures that end the run show red.
Getting that backwards makes every hiccup look fatal.

### 3. Write down every tool with its price

Prices and permissions live in one file, out of the model's reach. The model sees
only three things per tool: the name, the description, and what inputs it takes.
There is a test that checks the price never leaks into what the model sees.

Three permission levels exist in the code. The SEO Writer uses only the first, because
you asked for no credit stops. Paid steps check the DataForSEO balance first and say
plainly when they skipped something.

| Level | Meaning |
|---|---|
| Automatic | just run it |
| Ask first | stop and ask before the tool runs |
| Always ask | stop every single time, for something that cannot be undone |

The description is not a definition. It is a rule. "Run this after the site index
exists" beats "researches a keyword". That description is the only lever you have
on which tool the model picks, so write it as an instruction.

One trap to know about: there is a function in the tool list that says whether a
tool pauses, and the loop never actually calls it. Pausing is hardwired by tool
name. If you add a new pausing tool, you have to add it to the loop by hand.

### 4. Write the tools

One file per tool. Each one takes a bit of context and returns a summary of what
it did.

Two things worth doing every time. Emit progress as you go, because a tool that
takes three minutes and says nothing looks like a hang. And write the fallback
before you need it: the SEO Writer indexes a site from search data when the site
blocks the crawler outright, which happens more often than you would think.

Present as a browser, not as a crawler. A polite user agent that announced itself
as a bot got blocked on the very first request from a real site.

### 5. Put every prompt in its own file

Never build a prompt inside the code. One file per model call. That way you can
read them, diff them, and tune them without touching logic. When several prompts
share a rule, that rule goes in its own fragment file and gets included, so there
is one copy of it.

### 6. Get the engine green before touching the app

Six test files is the shape that worked: the loop, each tool, one whole run end to
end, the behaviour rules, the editing, and the model caller.

The behaviour tests are the ones that earn their keep. They check that the step
cap really stops at twenty-five, that a declined tool really never runs, and that
recoverable failures are marked differently from fatal ones.

They all run against a throwaway folder with the real model switched off. No test
ever touches your actual data or spends anything.

### 7. Add the web routes

Every route is thin. Read a file, or start the loop. No logic lives here.

Three things to copy exactly.

Ids get validated with a strict pattern, so nobody can walk out of the data folder
by putting slashes or dots in a URL.

Work runs on a background thread, one per run, and any crash inside it lands in
that run's own log instead of disappearing silently.

Secrets are never sent back. The route that reads your saved logins returns true
or false for each one, never the value. And the route that saves them deletes any
API key on every save, whether or not you mentioned it, because Sutra bills the
subscription and never the API. There is a test that fails you if you break that.

Most of this file is generic and copies straight across to a second agent. What
changes is the URL prefix, which engine it imports, and the parts that are about
your specific job.

### 8. Test the routes

Two setup lines carry all the pain here, and both are non-obvious.

The test client has to pretend it is on localhost, or the app's own security
middleware rejects every single request as coming from an untrusted host.

And every write request needs the panel's security token in a header, the same one
the real screen sends.

Beyond that, test the obvious things: bad ids rejected, the right error codes, and
secrets never coming back out.

### 9. Build the screen

The app repaints screens constantly, whenever anything anywhere changes. So the
screen cannot be a normal screen. It returns an empty box that never changes, and
a watcher notices the empty box and builds the real thing inside it. Because the
box never changes, the repaint never touches it.

Everything the screen knows lives in one shared state object, never in the page
itself. That is what makes a rebuild free: your scroll position and your half-typed
message come back exactly as they were.

It checks for updates once a second while something is running, once every four
seconds otherwise, and not at all while the window is hidden.

Four habits that matter.

**Escape every string.** All of them. There is a test that feeds a run a title
containing an image tag with an attack in it and checks it comes out harmless.

**Never invent a number.** No percentages, no estimated time remaining. Elapsed
time is measured between the first and last event and nothing more precise than
"1m 12s" is ever shown.

**A step still spinning in a run that already ended was interrupted.** Say so.
Otherwise the screen spins forever on a dead run.

**Approve buttons only appear when this exact thing is what the agent is actually
waiting on.** Reopening yesterday's draft shows no approve button. A saved article
opens read-only.

For the styling: every colour and font comes from the app's existing tokens. The
whole stylesheet has one literal colour in three hundred lines, and no dark mode
rules at all, because dark mode is inherited for free. Borrow the app's existing
buttons, pills and rows rather than making new ones.

**If you take option A**, six places in the current screen assume one agent and
need to become a list first: the API address, the stage names, the review panel
titles, the welcome screen text, the left column, and the panel dispatcher. Do
that as its own change, with the existing tests still passing, before you add the
second agent. Everything else in that file is already generic.

**If you take option B**, there are eight small registrations: the destination
list, its layout, its default screen, its label, its icon name, the icon itself,
the screen and title entries, and the two lines in the page template. Then three
places in the navigation test pin the number of destinations and all three have to
move together. One of them hides inside a test about a different tab, and the
number is written out in words in its failure message too.

### 10. Save a real run to test against

Run the agent for real once. Save what happened, with a note recording when,
against what model, and how it ended.

The rule is that test data is captured, never invented. Hand-typing what you think
an event looks like tests your imagination, not the system. Made-up examples are
fine only for small specific edge cases, where the edge is the point.

### 11. Test the screen twice

Once on the logic: given this saved run, does it produce the right list of steps.
Once on the output: does the HTML actually contain what it should.

Both tests load the real shipped file, not a copy. Which means the file has to
survive being loaded with no browser around it at all, so every place it touches
the page has to be guarded.

The six cases that caught real bugs:

- the empty box really is identical every time
- a hostile title comes out escaped
- an answered approval shows the decision and no buttons
- a step in a failed run is marked interrupted, not left spinning
- the approve button stays disabled until you choose something
- the connections screen shows dots and "(set)", never the actual password

### 12. Wire it in

Six small edits to shared files. Each one has a specific failure if you skip it.

| File | What it does | If you forget |
|---|---|---|
| The app's route list | mounts your routes | everything returns 404 |
| The asset version function | busts the cache | a stylesheet change serves the old file |
| The page template | loads your files | nothing loads at all |
| The dependency list | pins what you need | the build fails |
| The bundle check | proves it imports | the dependency ships unverified |
| The test config | excludes your engine's scripts | the whole test run dies |

The dependency rule is stricter than it looks. Because the app builds for both
Intel and Apple Silicon, and cross-building cannot compile anything, every
dependency has to ship a ready-made package for both. The nasty part is that this
never fails on an Apple Silicon machine. It fails on the Intel build, in the
cloud, forty minutes in. Test that specific case before you pin anything.

### 13. Run the full gate

Five JavaScript suites, the Python suite, the engine's own suite, then the two
lanes that drive the real app.

The rule: the code tests are code truth, the app tests are production truth, and
the visual sweep is design truth. It ships when all three agree.

Compare test failures by name against a baseline you took before you started, not
by count. Same names in and out means you broke nothing.

One thing to know: the automated build does not run the Python tests or the agent
screen tests. This gate is the only place they run. If you only trust the build,
your route tests never execute.

### 14. Run it for real and look at it

This step is not optional and it is where the real bugs are.

Everything on this list came from running the SEO Writer, and none of it came from
reading the code:

- a class name quietly picked up an unrelated style from elsewhere
- the panel shrank to 385 pixels wide next to an open chat, four words across
- the crawler got blocked on its first request for announcing itself
- an overloaded API was reported to the user as "not signed in"
- the test runner aborted entirely, for a reason that pointed nowhere near the change
- the screenshot tool waited forever, because the app keeps a live connection open

Write down what you proved and what you did not. Three lists: what shipped and how
you checked it, what running it found, and what you deliberately left for later.

### 15. Release it

The installed app runs its own copy of everything, sealed inside the app bundle.
Editing the code changes nothing for an installed app. Only a new build moves it.

1. Bump the version in two files. They have to match exactly, and there is a check
   that fails the build in seconds if they do not.
2. Write the changelog entry. Bold first sentence per point, in plain user
   language, then a few lines expanding it. Last point is the engineering one,
   naming the engine, the routes, the screen and any new dependency.
3. Write the current-version entry, one tight paragraph, and move the HEAD marker.
4. Commit and push.
5. Tag it and push the tag. That is what actually triggers the build. About seven
   minutes for both architectures.
6. Check the release exists with both files attached before telling anyone.

One thing that confuses people. The plugin and the app update on different tracks.
The plugin pulls from the repository and moves the next time you start a session.
The app only moves when a build is published. Seeing a new plugin version and an
old app version is normal in between.

---

## Where each step comes from

Every step above was taken from a real file, not from memory. The detailed version
of this document lists the exact file and line for each one, in a table with the
same step numbers.

---

## The other documents worth reading

- **PUBLISH-CHECK.md** — the gate, and the rules about what counts as tested.
- **GAME-PLAN-agents.md** — the SEO Writer's own plan, and the template for yours.
- **seo_agent/README.md** — how to drive the engine from outside the app.
- **seo_agent/HISTORY.md** — what was tried, what broke, what got decided.

---

## Things that will bite you

1. Two screens claiming the same name. The second one silently wins.
2. Forgetting to register a screen title. It is not a blank header, it is a crash
   that makes the click look ignored.
3. Adding a tool that should pause. The pause is hardwired by name, so a flag
   alone does nothing.
4. A dependency that only builds on your Mac. You find out forty minutes into the
   Intel build.
5. Trusting the automated build. It does not run the Python tests or the agent
   screen tests.
6. Test requests failing with a wrong-looking error, because the test client
   pretends to be a host the app refuses.
7. Calling the server directly from the screen instead of through the app's helper.
   Every write gets rejected.
8. Adding a stylesheet without registering it. Your changes serve stale from cache.
9. Engine tests that quit the process. They take the whole test run with them.
10. Progress rows without a parent. They float loose instead of nesting under
    their step.
11. Recoverable and fatal failures marked the wrong way round. Every hiccup looks
    like a disaster.
12. Testing your code against the installed app. It runs its own sealed copy and
    ignores yours.

---

## The checklist

- [ ] Plan written: layout, run log, checkpoints, how you will verify
- [ ] Engine folder built, knowing nothing about the app
- [ ] Memory: folder-per-run, safe writes, owner-only credentials, path resolved fresh
- [ ] Loop: money check reads from disk, step cap asks rather than kills, approval runs immediately
- [ ] Model caller: command first, prompt on standard input, parent session stripped, overload retried visibly
- [ ] Tool list: every tool has a price and a permission level, and the model sees neither
- [ ] Tools written, each reporting progress as it goes
- [ ] Prompts in files, none inside the code
- [ ] Engine tests green, in a throwaway folder, with the model switched off
- [ ] Routes added, ids validated, secrets returned as yes-or-no only, API keys refused
- [ ] Route tests green
- [ ] Screen: unchanging shell, watcher mounts it, all state outside the page, everything escaped
- [ ] Screen loads with no browser around it, so tests can read it
- [ ] Styling from existing tokens only, no new colours, no dark mode rules
- [ ] A real run captured, with a note saying when and how it ended
- [ ] Screen tests green, on both the logic and the output
- [ ] Six shared files edited
- [ ] Gate steps added to the publish checklist
- [ ] Full gate run, failures compared by name against a baseline
- [ ] Run for real, screenshots in both themes, findings written down
- [ ] Version bumped in both files, to the same number
- [ ] Changelog and current-version written
- [ ] Committed, pushed, tagged
- [ ] Release confirmed with both builds attached
