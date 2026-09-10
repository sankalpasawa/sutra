# Sutra — Current Version

**status**: active · **updated**: 2026-09-10

## v2.256.2 (2026-09-10, HEAD)

**"Check for changes" gave no sign of life, and the site's own firewall was the reason it needed
one.** Two separate faults, found together on the owner's real site.

The delay: testlify.com moved off WordPress, so `/wp-json/wp/v2/types` answers 403 and always will.
`_is_block` reads any 403 as a firewall, so the probe sat out three 120-second cooldowns — **six
minutes** — before giving up on an endpoint that cannot ever exist. And the delay was the smaller
half: six minutes of retrying tripped the site's rate limiter, so the SITEMAP step that follows, the
only page list a site with no CMS API has, was refused too. **Our own retrying caused the refusal.**
A discovery probe now takes one attempt: a question about whether something exists is answered the
first time you are told no. A refusal reads as "this is not a WordPress site, the sitemaps are the
source instead", and the host is not marked as blocked, so the fetch that follows starts clean.
Timestamps from his run: WP gave up at 13:25, the sitemaps read 2 MB of URLs at 13:30.

The silence: `api_knowledge_refresh` built its context with `"emit": lambda **kw: None`, so **every
progress line the engine produced was thrown away**. The spinner he watched was a fixed label. The
card now draws only what the engine actually said, in four states — working (with a trail), waiting
(a held dot and "30s of 2m", because a cooldown must not look like work), quiet ("nothing new for
3m 20s", so silence reads as alive), and stopped (the reason, nothing spinning). A worker thread
that dies is reported as failed, which is the spinner-after-the-work-stopped bug itself.

**And the wait is a field now, not prose.** It was told apart from work by regexing "waiting 120s"
out of the engine's sentence — one rewording away from silently turning every cooldown back into
something that looks like progress, with nothing able to catch it because the sentence and the
reader live in different packages.

**`pricing.md` no longer 404s, and now reaches the team in seconds.** A brand pack built before that
form existed has no copy of it on disk, so the screen offered a door to a file nobody had created.
A typed-in file now reads as its blank form when it is missing. And it moved from the pack (minutes,
on the next rebuild) to a `brand_inputs` row on the live pipe (about a second) — it is small and a
person typed it, while `features.md` next door is 13,219 machine-written words and stays in the
pack. That needed a new table, so a workspace made earlier gets an **Update workspace** button:
`create ... if not exists` cannot add a table to a database that already has its tables, and
migrations do not run unasked. A workspace one version behind is still `ok` and everything else goes
on syncing — a newer Sutra growing a table is not a broken workspace — and `sync.push` **declines
rather than queues** a row its workspace cannot take, because the outbox retries for ever in order
and one undeliverable row would hold every idea, article and prompt edit behind it.

## v2.257.0 (2026-09-10, HEAD)

**The Agents tab is a marketplace, and opening an agent explains itself.** It used to drop straight
into the last conversation. Now the tab opens on a shelf — the company name, one card for the one
agent that exists, and no greyed-out placeholders for things nobody has built — and opening the
agent lands on a guide rather than a chat: what it does in four steps, where to type to begin, what
each of the seven tabs holds, and five doors that explain the site read, the brand pack, the asset
engine, the research and the writer, each replacing the screen in place with a way back. The copy
is short on purpose and every word of it is in `design/AGENT-GUIDE-COPY.md`, with a test pinning
distinctive sentences so a later edit cannot quietly reword them. The screen names no website at
all: it used to print `Set up <domain>` from the company record, which was correct and never
hardcoded, but a command box made a two-word instruction look like something to copy.

**Three layout faults, all mine.** Left-aligning the conversation moved the whole gutter to the
right instead of removing it; prose and structure want different widths, so paragraphs keep a
measure and step rows, cards and tables now fill the column. The composer was capped at the old
prose measure and stopped two thirds across — an input has no reading width. And the main chat
composer had `background:none;border:0`, so the most-used control in the app was placeholder text
floating on the pane; it is a real field now, with a hover and a focus ring drawn from the theme
picker's own tokens.

**Clicking a chat opened nothing, and it was a fix from the same morning.** `S.screen` stays
`"agents"` after one visit to the Agents tab, and the new Agents-opens-alone rule read that as
"paint no session panes" — everywhere, for ever. One line. It explains both halves of the report:
with panes suppressed, New chat looked dead too, because its row appeared and no pane could.

**Also:** pressing New chat while the current chat is untouched now reuses it instead of minting
another (the empties that pile up live only in the browser and clear on relaunch, so nothing is
deleted to achieve it); every artifact card stopped reading "Topic ideasanswered", two inline spans
styled as though stacked; and the shelf carries a drawn Sutra mark whose every stroke is
`var(--acc)`, so it follows the theme picker with no per-theme code, sits behind everything,
catches no clicks and never animates.

## v2.256.1 (2026-09-10)

**A setup that did not finish was forgotten entirely.** The owner created his team workspace and the
next day Connections offered him a blank Create form, as if nothing had happened. Nothing was wrong
in Supabase: the ten tables, nine triggers and the knowledge bucket were all there. Sutra had no
idea they existed, because `_ws_create_worker` returned on a false verdict before saving anything,
and the verdict had been wrong (see 2.255.2). So the bad answer did not just mislead him once; it
threw away the project details and left nothing to come back to. The URL and key are **his input
and are valid whether or not the script finished**, so they are saved as soon as the setup call
returns, before its verdict is read. An unfinished setup is now a resumable state, which is what the
screen was already drawing. `verify()` is still the only voice that says a workspace is ready: no
pack is uploaded and no link is shown until it does. Two test assertions were stale the same way and
said something weaker than they meant -- "nothing was saved: no half-made workspace" conflated
nothing half-made in Supabase, which is right, with nothing remembered on this Mac, which was the
bug.

## v2.255.2 (2026-09-09)

**The workspace was built correctly and told him it had failed.** Both bugs shipped green and
neither could have been found without running against a real Supabase project. The cupboard check
read the bucket's *record* rather than trying to *store a file*: measured live, `GET /bucket/knowledge`
answers 404 while upload, download, replace and delete all return 200, because a publishable key
cannot read `storage.buckets` even when the bucket is fine. It now writes a small object, reads it
back and deletes it -- the same round trip the real upload makes. And `verify()` believed the API the
first time it said a table was missing: PostgREST answers from a **cached** schema, so a table
created a moment ago returns the byte-identical error to one that never existed. The script now ends
with `notify pgrst, 'reload schema'`, and a "missing" verdict is slept on and re-asked before it is
reported. A healthy workspace never sleeps at all.

## v2.255.1 (2026-09-09)

**The setup script showed the SQL, not the essay about it.** 18,600 of its 33,671 characters were
developer notes -- why `clock_timestamp()` and not `now()`, why 45 MiB and not 40. Every word earns
its place in the repo; none of it earns a place in front of somebody told this takes thirty seconds.
The screen gets 326 lines instead of 565. The file on disk is untouched: it is a view, and a test
asserts that.

## v2.255.0 (2026-09-09)

**The team workspace.** Five people, one team, on the company's own Supabase project. Ten modules,
ten tables, a change log written by database **triggers** rather than by the client -- an app that
dies between writing a row and logging it would otherwise leave a change nobody ever hears about.
Three things were nearly very wrong: a routine trim would have deleted 12,000 pages from every
teammate's catalogue, because clearing rows and "these pages are gone from the site" arrive as the
same event; a change could vanish for ever, because row numbers are handed out when a write *starts*,
so a reader can record "I am up to 8" and never see 7; and the guard for that was read off the local
clock, where a fast Mac reopens the hole unreproducibly. Measurement beat the estimates: the pack is
**205 MB zipped, not the ~100 MB planned**, over a **50 MB single-object cap** that would have
refused it outright. Splitting it into a 33.6 MB core and a 171.5 MB index makes a normal refresh
2.9 s and 33.6 MB. Also: the six approved Tier-3 findings, including a source hunt costing 3.33x
what it should and a planner retry that had been a dead branch for months.

## v2.254.0 (2026-09-09)

**The audit's findings, the eight broken things, and a file only a person can write.** Two dead
buttons had the same cause and it was not the endpoints -- `agAction` had no arm for either, so the
click fell through to `default: break`. Making "Check for changes" work uncovered two worse bugs
behind it: it never actually re-read a changed page while reporting that it had, and **one broken
sitemap file could delete every page it listed**, because a child sitemap returning 500 is filed as
blocked and simply returns fewer URLs. `pricing.md` gave the brand pack a door a crawler cannot
open: facts drawn by JavaScript sit in neither the crawl nor the raw HTML, and the engine had been
reading such a file and calling it authoritative while nothing in the product could write it. A
failed catalogue gate now stops the run instead of letting a brand pack build on a catalogue that
failed its own counting.

## v2.256.0 (2026-09-10)

**Every project you have worked in is a department, and chats live under them.** A new operator
installed Sutra and the Org screen was empty -- the one surface that makes this different from a
chat client had nothing in it, while the machine already knew what they work on. `project_import.py`
reads the three stores Claude itself uses (the desktop app's session store, `~/.claude.json`, and
`~/.claude/projects`) and mints one department per project, nested by directory containment. It runs
from an app startup hook, so onboarding is plain code with no model in the loop, and a project
started later appears on the next launch. Add-only: wiping stays behind an explicit CLI flag,
because a boot path that can delete a registry is one crash-loop away from doing it repeatedly.

Reading only `~/.claude/projects` -- the obvious source -- found **12 projects where the union finds
23**. It cannot see a project whose sessions ran in the desktop app (bahi-khata, cover-letter,
lenovo-case-study) nor one the CLI merely remembers (hokage-desk, kaguya, nakama-cli-suite,
sovereign-ai). A department's identity is its **cwd, not its name**: labels change -- a project is
named after its git remote when the directory IS the repo root, which is how Claude labels them, so
`live-contest-event-leaderboard` shows as *Live Contest Event Dashboard* -- and minting by name
produced a duplicate that left two departments claiming one directory. The naive form of that rule
was wrong for 2 of the 3 projects it touched: a subdirectory reports its parent's remote, which
would have folded `sutra/marketplace/plugin/sutra-ui` into *Sutra*.

**Chats group by department, keyed on the working directory rather than turn placements.** That
axis only ever covered the subset that routed -- a terminal transcript carries `domain:null` by
design, an unread one has no turns, and `askSide` skips classification deliberately -- and it placed
0 of 400 sessions after a registry rebuild. Headings carry the department's real size, not the
number of chats on the loaded page (it read *90* for a project holding *939*), every department is
listed rather than only those with a recent chat, and groups collapse, persisted per department ref.

**The company name is derived from the machine, never a literal.** The registry root and the
identity footer read "Asawa Inc." -- so a stranger who installed Sutra was shown someone else's
company as the root of their own org and offered "CEO of Asawa Inc." as their role. The root is now
read from the account (`SUTRA_ORG_NAME`, then the account full name, then the login name), the role
label is composed from the registry root, and a superseded role is cleared rather than left in
storage naming a company the operator never had.

## v2.253.0 (2026-09-09)

**Reddit reads again, and it was blocking three things at once.** Every plain request from this
machine came back 403, and old.reddit answered a login page with a success code, which is why one
site's eighteen candidate communities all sat unverified. A real browser goes straight through:
warm the origin once, then fetch from inside the page. `research/reddit.py` is now the one place
anything asks Reddit anything, with a three-state answer that never confuses "nobody talks about
this" with "we could not look". Re-run live against the real 18: **10 kept, 8 dropped, 0
unverified, in 42 seconds.** Two bugs surfaced only by running it: a subreddit that does not exist
answers with subreddit rows instead of posts, so `r/ExperiencedRecruiter` reported "8 posts" titled
*googlejobs* and *Oil and Gas Life*. The Study Trends builder was on the same broken path and is
moved across.

**The length is one number, chosen by a person.** It was decided twice by two steps that never
spoke: the architect budgeted from the pages that actually rank, then the readable pass re-decided
it from a hardcoded 2,100 that knew nothing about them. Competitors at 3,200 words and competitors
at 1,400 both produced an article cut to 2,100. That ceiling is deleted, not softened. One question
now, asked once per run, before the expensive research: here is what the ranking pages run, here is
the average, use it or type your own. A typed number wins. Every step downstream reads that one
number, including the internal-link budget, which was the last one still measuring the draft.

`WORDS_PER_FACT` is now shared by the body writer and the rewrite instead of being one step's
private preference. The fact count follows the length rather than a fixed number.

**234 lines of the owner's own prompt writing, restored.** His edits were a week old and the app was
running older copies. The rewrite pass alone was missing "professional, not chatty", "put the basics
first", "connect the sections", and a far stronger rule about sections that wander off the
headline's promise. It was still carrying the chatty example AS ITS MODEL. A new parity suite now
fails by name when his originals drift ahead again, which is exactly how this went unnoticed.

**The three stations that only reported are now doing the work.** Enrich goes and researches what
the structure says is thin, instead of writing a note about it; nine sections on one real article
had asked and got nothing. A dead source is hunted and replaced rather than reported. And voices
from the field is built: it reads where practitioners argue in public and weaves the real arguments
in, which on the owner's own article was worth 1,273 words. All three log live. All three carry the
same honesty rule: a page that will not load is dropped, and a quote that is not really on the page
it claims is thrown away.

**A Prompts tab.** The words the agent writes by, editable without a developer: the eight format
rulebooks and the six writing prompts, with a flow at the top showing how an article actually gets
made. Edits live beside the owner's own files, so an app update never overwrites them, and Reset
puts a prompt back to what shipped. A save that loses a placeholder the code fills is refused with
the missing ones named, rather than breaking a run three steps later.

Also: the Library says what shape each article was written to · a takeaway block no longer ships
under a heading that promises a quick answer · the per-format wrapper rules the owner wrote are
wired in, so a comparison and a glossary no longer open and close alike.

## v2.252.0 (2026-09-09)

**The agent stops interrupting you.** A run used to stop five times. It now stops twice, at the two
that are decisions rather than reviews: which topic, and whether the draft is finished. The brand
pack, the research brief and the plan are written, announced in one line, and passed. The rule is
written into the code for whoever wants to add a stop later: the test is whether the agent genuinely
cannot continue without an answer, and "look at this" is not that.

**Nothing is lost, because the Library now shows the work as it is made.** A row appears the moment
an article starts and fills in piece by piece: researched, planned, the search picture, written,
edited. Each one clickable. A run that crashes leaves a row honestly showing how far it got.

The row is derived from the run, never copied out of it, so it cannot drift from what actually
happened, and a list of 300 rows with the full strip reads in 14 milliseconds. Its id is a pure
function of the run, which makes opening it idempotent by construction: two threads racing cannot
make two rows, and the rename at the end cannot move a row somebody is watching. A row whose run
folder is gone shows no strip at all rather than five empty boxes, because "we cannot know" and "it
never got that far" are different facts.

**The search picture.** One readable page of what the search results actually said: the keyword and
its numbers, who ranks, what they all cover, what none of them cover, what to avoid, the questions
worth answering, and who the article is written for. Pure assembly, no model call, so what you read
is what the steps produced rather than a summary of it. It counts both filter stages and lists the
questions that were set aside, so "22 elsewhere and 9 here" is answerable instead of looking like
things went missing.

**An article run no longer starts when it cannot measure anything.** The old balance guard sat below
the first step and behind a resume check, so a resumed run skipped it entirely and then quietly
substituted placeholder figures for every search call. That is the twenty minutes of work on numbers
nobody measured. It is now one pre-flight at the top that refuses before anything starts, naming the
balance, the floor and both ways out. It fails OPEN in every direction: no credentials, an
unreadable balance, a changed response shape, or nothing paid left to run all proceed, because a
network blip must never stop somebody writing. The floor is resolved at import, so a constant that
vanishes is an error rather than a guard that silently passes everything.

A placeholder run is still possible, but only by asking for it in so many words.

## v2.250.1 (2026-09-09)

**A sheet of ideas the workflow already produced can be loaded straight in.** Somebody who has run
the original `02-asset-engine` by hand does not have to pay for it twice: its `clubbed-ideas.csv`
loads into the Asset ideas tab in the shape a built sheet has. Columns are read by name, so their
order does not matter, and a file that is not a sheet is refused naming the column it wanted.

Two things it will not invent. The merged sheet carries no linkability score, so a loaded idea is
unscored rather than scored zero, because a zero reads exactly like a real rejection. And the fit
tag IS the outcome of the original's ownability test, so that verdict is carried rather than
guessed at.

**Three things found by loading the owner's own 1,892 ideas into it**, none of which a test would
have caught. The list drew every row at once: 41,000 elements and a page 165,000 pixels tall, which
is not a list anybody can use. It pages twenty-five at a time now, with the same control the site
catalogue already uses, so there is one idiom on that screen and not two. The summary sentence
reached the screen reading "1892 ideas from competitor-study, model-other-niches", which is right in
a file path and wrong in a sentence a person reads; there is one table of plain names now and
anything writing a line for the screen goes through it. And the ids were minted without their band,
so a loaded sheet could have collided with a built one.

## v2.250.0 (2026-09-09)

**Sutra can now work out WHAT to write, not just write it.** Layer 02 of the workflow, the asset
engine, is ported: three ways of finding ideas that never see each other's output until the end,
then a merge, then a check against pages the company already has.

Method 1 studies which competitor pages actually earn links and takes the FORMAT, never the topic.
Method 2 lifts shapes proven in other industries, from a table of nineteen copied verbatim off the
workflow rather than remembered by a model. Method 3 reads what the audience argues about in public
and turns recurring arguments into ideas. The three are kept apart on purpose: one method finds one
kind of idea, and letting them talk before the merge would collapse three independent signals into
one. They meet exactly once, where an idea all three found arrives carrying three kinds of evidence.

**All three judge with the SAME two tests, in the same words.** Ownability and Linkability live in
one file and no method may write its own. That is the original's own argument for why the pools can
be ranked against each other at the end; three paraphrases could not be. Linkability is scored out
of four by the model and the keep-or-drop line is derived in CODE, never asked.

**The engine stops twice and asks you**, through the same checkpoint every approval already uses:
the competitor shortlist and the subreddit list. A rewritten list wins over the proposal, always.
Taking the proposal anyway when somebody clearly typed something else would make the gate
decorative, which is worse than not having one. The answer lands in a file the builder checks on
its next run, so an approval survives a crash, a quit and a week off.

**A new Asset ideas tab.** The next unwritten idea sits at the top as a chip that writes the message
for you. The chip carries the idea's id as DATA and the id travels BESIDE the message, never inside
the words: it reaches the run's state before the model reads anything, so nothing has to read an id
out of prose and decide to look it up. That is a step that can quietly not happen and nobody would
know it had been skipped. The warning that the topic gate can still turn the idea down is on screen
before you send, not after.

**Ticking is provenance only.** A run that began at an idea ticks that idea when it reaches the
Library. An article you typed yourself ticks nothing, and nothing is matched by meaning. Matching
adds a whole class of wrong answers to save a rare piece of bookkeeping, and a wrong tick silently
drops an idea out of the queue where nobody would find it.

**Honest about what it could not do.** A method that ran and found nothing, and one that never ran
at all, are different facts and the screen says which. The competitor study needs DataForSEO credit
and refuses cleanly without spending; the trends method inherits the subreddit checker's rule that a
rate-limited Reddit is "unknown", never "empty".

Also: the writer brief box is capped short with an Open control that puts the whole file in the side
panel; page types carry plain-English display names; and three defects were found by building
against the shared file rather than reading it. Ids from three pools were going to collide. A
forgotten idea came back scored zero, which reads exactly like a genuine drop, so a keep-or-drop
decision was resting on a phrase in a sentence. And an idea row had nowhere to say it needs building
rather than writing, which the original added after its own engine turned 1,143 of 2,213 ideas into
calculators.

## v2.249.1 (2026-09-09)

**Two fixes found by actually opening the shipped app and running the setup interview for real.**

Installing Sutra used to copy the new app straight onto the old one. Almost every first install
goes that way, because Electron's own mover refuses a read-only source and the source is a disk
image. `ditto` merges rather than replaces, so files the new version had deleted stayed behind and
the installed app no longer matched its own signature; nothing checked what was already at the
destination, or whether it was running. It now stages beside the target and swaps with renames,
the way the updater has always done, only replaces a bundle that is the same app by its identifier,
and refuses out loud rather than half-installing. Found the hard way: verifying this release
overwrote a real install.

A drafted row in stats.md carries a hidden marker meaning the machine wrote it, and a row without
one means a person confirmed it. The cells come back from the model and were written in as they
arrived, so a quoted line break split the row and left its unmarked first half looking confirmed.
One newline made the whole file read as finished, which would have sent the next rebuild's drafts
to a side file. Four of forty-three rows split this way on a first real run.

Also: `seo_agent/CONTRACTS.md` now names both confirm-a-draft gates. The style guide's two
"confirm with marketing" fields were recorded as never ported and are in fact ported end to end;
nothing tied the template, the prompt and the builder's note together, so a test now does.

## v2.249.0 (2026-09-09)

**The Knowledge tab stops nagging and starts reading like a document.** The brand pack asked to be
confirmed in four different places at once: a yellow banner, a warning symbol on every drafted row,
a "N to confirm" pill per file, and a review list. All of it is gone. The symbol that marked a
machine draft becomes a hidden marker, so a rebuild still never touches a row someone edited, but
nothing on screen tells them off. Legacy files are migrated on their next run and a legacy row is
still read correctly until then.

That hidden marker would have shipped VISIBLE. `mdHtml` escapes every `<` and `>` before it does
anything else, which is the whole safety argument of that function, so `<!--d-->` would have
rendered as those literal characters on every row -- worse than the symbol it replaced. It is
stripped after escaping, never before: stripping raw source could splice `<sc<!---->ript>` back
into a real tag. One strip covers all three hidden markers the app now uses.

**opinions.md is deleted.** Nothing ever read it. It asked the owner to answer an interview whose
answers no step used.

**The tab is rebuilt around the one file a writer actually reads.** The writer brief is on the page
in full, and the files it was assembled from sit behind one control. The four gate chips
(`enumeration accounting`, `response integrity`, `extraction coverage`, `traffic check`) are off the
screen; they still run and still write to catalogue-report.json. The meaning-index section and its
stats are gone, and the one sentence worth keeping became the map's caption. The page list shows
five rows. A standing screen carries no nags; a live checkpoint still says what it is waiting for.

**That door lists what the builder really read, not what was assumed.** The first version claimed
features.md, which writer_brief.py excludes BY NAME with a comment giving the reason, and omitted
voices.md, which it reads as one of four classified sources. So "Who writes" is not idle after all,
and features.md moved to where it belongs: read on every article, but not a source of the brief.

**The pages a call to action may link to are now a list you edit.** The format lives in one module,
so what the screen writes is what the writer parses. A row you add survives a rebuild. A page the
crawl has never seen is accepted and says so rather than failing silently.

**A first-run interview puts the questions the workflow has always asked out loud.** Six of them, in
the chat, once, each skippable, and a skip recorded as a skip rather than as an empty answer.
voices.md was the real hole: its builder drafts nothing by design, so it shipped with seven
placeholders that nothing was ever going to fill.

**A language prefix in a URL is a language, never a kind of page.** Thirteen of one site's
thirty-nine types were language codes, and 584 pages added by a refresh had no type at all: 2,933
of 12,318 rows mis-filed. The type list drops to 25 real kinds, the translations rejoin their
English originals, and languages become their own filter with real names. Page types also gained
plain-English display names, decided in the one model call that already classifies them.

**Library editing is back.** It was built, then lost when a corrupted git store forced a fresh
clone, which left the route calling a `store.library_update` that no longer existed. Both restored.

Also fixed: the honesty contract's "what the product is NOT" slot never filled, because it demanded
a comma-separated list and the only real boundary in the pack was a single item; `.ag-editrow`,
`.ag-libedit` and `.ag-lbl` had no CSS at all, so the traffic-import form rendered unstyled; the
confidence pill's hover text leaked "enumeration accounting" onto the screen; "meaning vectors" was
still in the Connections copy; and opening a file shifted the reader's position by several hundred
pixels, because `haspanel` reflows the left column three ways at once.


## v2.248.0 (2026-09-09)

Codex is a provider you can actually chat with. Signing in has worked since 2.246.0, but the row
said so itself: there was no chat adapter, so the account sat there unusable. There is one now,
with its own runtime, readiness check and install path.

The model picker is the part that had to be built sideways. codex-cli 0.153.2 publishes no model
list at all -- re-measured on 2026-09-08, because "no model list" is the kind of claim that rots:
`codex models` is not a subcommand, `codex exec --help` documents `-m, --model <MODEL>` without
enumerating one, and the app-server schema carries no roster. Passing a name anyway is worse than
being refused: `-m gpt-5-codex` was ACCEPTED and warned that metadata was missing and had been
replaced with fallback values, which degrades the run quietly. So the authoritative source is the
operator's own configuration -- the top-level `model` in `$CODEX_HOME/config.toml`, plus any
`-p/--profile` overlay -- surfaced beside "let codex decide", which sends no flag at all.

The Usage screen reads the ChatGPT plan allowance straight from the CLI's own
`account/rateLimits/read`, costing no model turn, and states plainly that an API-key sign-in
reports no allowance rather than rendering an empty fold. Anthropic's account panel is kept off
Codex sessions for the same reason.

## v2.246.1 (2026-09-08)

The 2.246.0 build never produced a DMG, and what stopped it was worse than the signing error it
appeared to be. The packager upgrade in 2.246.0 turned every relative symlink in the bundled
runtime into an absolute one pointing at the build machine's own checkout -- nine CPython links
and both npm links -- so the app would have shipped with a dangling `python3` and a dangling
`npm` to everyone. codesign refused it, which is the only reason it was caught before release.
The payload is now copied with `ditto`, which preserves symlinks exactly, and the build refuses
to continue if any symlink in the bundle points outside it. The old check could not catch this:
it tested `python3` with `-x`, which follows the link, and on the build machine the absolute
target really was there. Developer ID signing and notarization were not exercised locally --
the fix was verified with an ad-hoc signature.

## v2.246.0 (2026-09-08)

Codex has two ways to sign in and you can now move between them without losing one. Codex keeps
exactly one credential and each method deletes the other -- measured on codex-cli 0.153.2,
switching to an API key strips the ChatGPT tokens outright -- so anyone who switched away from a
key lost it for good, and Sutra had never kept a copy. Sutra now holds the key in the login
keychain and puts either mode back on a click, reading the live state from the CLI on every open
so a sign-in done in a terminal shows as the truth rather than the stored preference. The key is
checked against OpenAI before anything is written, because codex validates nothing: it accepted a
deliberately fake key, reported success, and left every later call failing with a raw 401 nobody
would trace back to the paste. The key reaches the keychain through a child process, never an
HTTP request. Signing in still does not make Codex selectable -- there is no chat adapter yet,
and the row says so.

Alongside it, three things that were failing quietly. A staged install produced a backend that
could not start, because install.sh never copied the connectors package and its checks did not
look; it now copies it and refuses to finish unless the staged backend imports. The Electron
build had begun exiting 0 while producing nothing, so installs silently fell back to the
script bundle with no desktop bridge at all. And two steps of the publish gate could not run on
a release machine -- one aborted on duplicate test files from the build output, the other on a
space in this checkout's path.

## v2.245.0 (2026-09-07)

Sutra now brings its own Node, so entering a valid DeepSeek key is all it takes. DeepSeek is an
npm package Sutra installs and runs, and the app shipped its own Python but not Node -- so a Mac
without Node saved the key, was told to go and install Node, and could not select the provider.
The runtime now ships inside the app: used only when the Mac has none of its own, invisible to
everything else on the machine, and gone when the app is. Verified by installing and running the
CLI with the machine's own Node hidden. The download grows by about 110MB.

## v2.244.1 (2026-09-07)

A DeepSeek pane no longer dies with a Gemini error. Every session ended at "Gemini API key is
missing or not configured" -- with a valid DeepSeek key saved and the CLI installed -- because
the key reached the spawn environment and nothing told the CLI which vendor the session was
for. Left to guess, it defaults to Gemini and refuses. Sutra now authenticates the connection
as DeepSeek before creating the session, and a key the provider rejects is reported as that
rather than as a missing Gemini key. And a key the panel accepts now means the CLI install is
attempted whatever happens to the window afterwards -- it no longer depends on the browser
being alive to chain it -- with npm single-flighted so the two paths cannot race into one
folder.

## v2.244.0 (2026-09-07)

Entering a DeepSeek key now installs the DeepSeek CLI. A key is only half of what DeepSeek
needs -- the other half is its command-line tool, because Sutra answers every message by
spawning it -- and the panel supplied only the key, so a validated key was confirmed with
"saved on this Mac" directly beneath a row that correctly read "Not installed on this Mac",
with no control anywhere on the screen that could fix it. The install now runs on its own
straight after the key is saved, and a key saved earlier gets a button. It goes into a
folder Sutra owns rather than a global npm prefix, so nothing asks for a password and
nothing outside ~/.sutra-ui changes; the row flips without a restart. A Mac without Node is
told so, and told where to get it, instead of failing silently.

## v2.243.0 (2026-09-07)

DeepSeek is a provider the app signs in to, and a pane stops claiming settings it cannot
honour. Sign-in happens in a browser and the key goes to the login keychain; each provider
now brings its own model list, and DeepSeek's models actually reach the CLI. A pane knows
which provider it is on before the first message, and renders only the controls that
provider declares -- because the ones it did render were not all in force: every DeepSeek
pane displayed the operator's permission mode while the session ran in `default`, so a pane
set to plan was not read-only. The mode now travels on the method the CLI implements, and a
mode that cannot be set says so instead of being shown as chosen. Usage reports what the
provider actually has, and a context window can no longer quietly shrink. Codex signs in
and out without Electron, and its row says which credential is paying. Routines is back at
Settings -> Automation.

## v2.242.0 (2026-09-05)

The SEO Writer, audited against the workflow it was ported from and corrected. Research is
now a team of four interviewing an expert rather than a keyword lookup, and the facts are
lifted from the cited dossier they produce, so a fact can cite two sources. The catalogue
reads the whole site (a cap given once had been frozen into the cache and every coverage
check still passed); Testlify went 400 pages to 11,734, and the brand pack rebuilt on it is
richer than the original. The run log groups by stage, a research run ends in documents with
a clickable evidence trail, and the app repairs its own runtime instead of dying inside a
crawl on a missing library.

## v2.241.0 (2026-09-04)

Chat distinguishes a running turn from a queued one.

## v2.240.0 (2026-09-04)

The SEO Writer becomes a port of the whole SEO workflow: the four-source site catalogue
with coverage gates, the Voyage page index with a map, the twelve brand builders and the
writer brief, the content machine's research with the world check and evidence cards,
and the write phase with its editing passes and internal links laid in by meaning. Sites
behind a bot challenge are read through the app's own hidden window. No credit stops;
five checkpoints; memory reaches every writing step; Knowledge shows everything.

## v2.239.1 (2026-09-03)

Sutra now offers to install itself. Opening the app straight out of the DMG
window works, so nothing ever tells you it was never installed -- and a disk
image is read-only, so that copy can never update itself. It now asks once on
launch and moves itself to Applications. The update refusal was rewritten to
name the disk image rather than a permission bit, and both update paths check
before downloading 240MB instead of after.

## v2.239.0 (2026-09-03)

Agents: a new rail destination between Chats and Routines, and its first agent, the
SEO Writer. It indexes your site, learns how you write, researches a keyword, builds
an article structure and writes the draft, stopping at four checkpoints where you
edit or redirect before it continues; anything that costs credits asks first with the
number. Runs on the `claude` CLI the chat already drives (subscription, no API key);
keyword data from DataForSEO. Engine in `sutra-ui/seo_agent/`, standalone.
(2.238.0 in between: see marketplace/plugin/CHANGELOG.md.)

## v2.235.4 (2026-08-26)

Provider detection: Claude Desktop is recognised as a different product from the
Claude Code CLI (Desktop ships no `claude` binary) and the panel says what to
install; version-manager shim dirs (pnpm, mise, asdf, nodenv, fnm) are probed;
the login-shell PATH harvest gets 25s instead of 8 and explains why it failed;
and a binary path can be set from the panel instead of only through an
environment variable a Finder-launched app cannot receive.

NOTE: this file had drifted — its previous top entry was v2.226.3 while
plugin.json was already at 2.235.3. The intervening releases are in
marketplace/plugin/CHANGELOG.md; the gap below is real, not a lost entry.

## v2.226.3 (2026-08-25)

Attach-mode auto-update: the shell updates itself via its bundled sidecar CLI
(updates_cli wrapping updates.py, flock-serialised) even while a CLI/checkout
server holds 8330; feature-detected renderer lights up at the next DMG.
(2.225.2-2.226.2 in between: see marketplace/plugin/CHANGELOG.md.)

## v2.225.1 (2026-08-25)

Editor lifecycle race fixed (light-mode blocker); saved label; emphasis weights.

## v2.225.0 (2026-08-25)

Native editing: forked SB editor core vendored in-panel; iframes deleted;
sidecar retired from the app path.

## v2.224.6 (2026-08-25)

Settings > Usage opens with the Account card: who is signed in, email, plan,
subscription/billing, organization/role, tier, IDs, data age — local reads,
allow-listed, no tokens. Manifests re-synced after 2.224.5.

## v2.224.5 (2026-08-25)

Shadow interactive: dot home corner, click-to-card, card mounts and sends,
Now empty state starts a chat (changelog-only bump; manifests stayed 2.224.4).

## v2.224.4 (2026-08-25)

Rhythm hygiene: 22px content start, quiet zero-doc departments.

## v2.224.2 (2026-08-25)

Theme comment honesty (verify-floor catch).

## v2.224.1 (2026-08-25)

Closeout: theme v3 edit scale, 680/232 measure, panel token, daemon hygiene.

## v2.224.0 (2026-08-25)

S92 cutover: Workspace default-on fleet-wide; Knowledge/Files folded in.

## v2.223.1 (2026-08-25)

Workspace parity loop closed (reviewer SIGN-OFF); search top-bar swap fixed.

## v2.222.9 (2026-08-25)

Panel-native rendered READ state (iframe only behind Edit) + reviewer minors.

## v2.222.8 (2026-08-25)

Review-loop: search in-flight state + content cache, clip fix, filing join
unified, cursor/renderer one predicate, 14-row cap, stable sidecar port.

## v2.222.7 (2026-08-25)

Tree indents render (button-reset specificity); DOM-verified vs mock spec.

## v2.222.6 (2026-08-25)

Editing default-on (READ_ONLY opt-out + origin guard, dual-consulted); tree
collapses to the active path (founder structure ruling); tighter type scale.

## v2.222.5 (2026-08-25)

Settings > Updates: desktop row now tells the truth in attach mode (shell
attached to a CLI/source-checkout server) — "desktop updates unavailable" +
recovery step, instead of the false "not managed here / source checkout".

## v2.222.4 (2026-08-25)

Workspace/Files visual parity: theme v2 (SB chrome hidden, panel tokens both
themes, serif headings), search-result styling per mock 03, nativeTheme bridge.

## v2.222.3 (2026-08-24)

Workspace: openScreen loads the screen again — the per-screen dispatch line was
lost in a worktree restore, so the click path rendered an empty shell. Restored
+ pinned by a workspace-suite test.

## v2.222.2 (2026-08-24)

Optimus copy in customer voice (P0); technical detail demoted to muted; trust
gates unchanged. (2.222.1 in between: workspace flag propagation — see CHANGELOG.)

## v2.222.0 (2026-08-24)

**Optimus — the daemon, visible (Focus tab).** A window over sutra-daemon's
stores: status+PID, decision queue, routes with department/charter chips,
recent runs, ask box, route builder. Screen requests; the daemon CLI gate
decides (two-step typed approve, PID-echo stop, desktop-token mutations).

## v2.220.4 (2026-08-24)

Releases come from .github/workflows/release-dmg.yml only: make-dmg.sh now
refuses to notarize unless SUTRA_RELEASE_CI=1, which only the workflow sets.
The `fork` remote is removed -- development and pushes go to sankalpasawa/sutra,
where the update channel already pointed. Settings pane groups collapse
individually, keyed per destination, storing only what was explicitly closed.

## v2.220.3 (2026-08-24)

Chat rows in user language: 'not opened yet' (no sizes, no 'transcript'),
'opening…', "can't be opened"; workspace label only when it differentiates.


## v2.220.2 (2026-08-24)

Every connector type gets its own tile: five connectors, five tiles, each with
its own glyph, state, account line and controls. The single "Connected in
Claude" card is gone. The probe remains one CLI run for all of them, and the
Re-check tooltip says so rather than letting per-tile placement imply otherwise.

## v2.220.1 (2026-08-24)

Six vertical panes: the session surface holds up to 6 side-by-side chat
panes (FIFO eviction, no duplicates, horizontal scroll).


## v2.220.0 (2026-08-24)

Slack stops being a connector Sutra owns and becomes one it observes through
Claude, like Gmail and Drive. Sutra runs no Slack OAuth app and holds no Slack
token.

The mediated catalogue is generalised: Slack matches on display name until a
real row teaches it the host -- it has never been connected in Claude here, so
there is no host to look up, and guessing one would render "not listed" forever
and confidently. Any connector Claude reports that Sutra has no catalogue entry
for is now surfaced rather than dropped (the operator has an Atlassian Rovo
connector the old code silently ignored).

Slack is retired IN PLACE, not deleted. Deregistering it was verified by
execution to make every /api/connectors/slack/... route 404 -- including DELETE
-- which does not remove an upgrader's tokens, it removes their only way to
remove them.

## v2.119.5 (2026-08-24)

Subtitle round 3: free-form ritual (CAPS-KEY headings, metric parentheses)
trimmed from the header subtitle; the ask opens it.


## v2.119.3 (2026-08-24)

Chat header round 2: title + subtitle rows (hover for full text), department
beside the live dot ("latest filed"), aligned to the chat column; per-turn
transcript boilerplate and the pane's "transcript" tag removed.


## v2.118.3 (2026-08-24)

Ownership inversion: the desktop update channel now points at
`sankalpasawa/sutra` (the founder's repo, where CI signs and notarizes).
`tchandrakar/sutra` publishes one migration bridge and then retires as a
release channel. Pinned in `test_update_channel.py` (default, override,
and the URL the updater actually requests).


## v2.118.1 (2026-08-24)

Governance chips now render on transcript turns -- which is every real session
read from `~/.claude/projects`. Until now that branch skipped the chip while
the body strip removed the same content: Input Routing, Depth, FLOW, BLUEPRINT
and traces were invisible on real sessions. The chip is gated on an actual
capture, toggles via a real turn uid, and says **terminal** (a fact) rather
than "unresolved" (a failure that never happened). L1+L2+L3 pinned.


## v2.117.2 (2026-08-23)

The chat surface, redesigned and verified in the shipped app: every turn's
governance captured under its chip (never leaked into the reply), subagent
fan-outs visible as rows inside the turn, an openable step log, a minimal
header (what the chat is about in 45 words + close), one ⋯ composer menu
carrying every session control, Routing as a tree. Plus a two-lane publish
standard (state over CDP, then pixels) and a design-QA product.

Two hardcoded defaults replaced with what Claude already knows: the rail footer
avatar comes from the signed-in Claude account instead of a literal "TC", and
the agent's default workdir falls back to the operator's most recent Claude
workspace instead of ~/sutra-ui-workspace. Both are DEFAULTS only -- a stored
workdir still wins -- and the recent path is filtered through workdir_allowed()
before it is offered, because it becomes the agent's cwd.

## v2.117.1 (2026-08-22)

Google connector, as a MEDIATED tile: a connection Sutra observes and cannot act
on. Membership ("Added in Claude") is rendered as state; the CLI's status string
is rendered as a timestamped observation, because the same connector reported
four different statuses within one hour. The connected Google account is NOT
shown -- it is not knowable from any local store or from Claude's API, and the
nearest value to hand is the Claude account email, which would have been a
convincing wrong answer. See ADR-035.

## v2.117.0 (2026-08-22)

Carries the 2.116.x line (Teamsutra rewritten to read like a person wrote it;
Files v1.1 with folder tree + Knowledge bridge) plus three fixes:

- **Streaming text flows instead of arriving in lumps.** The reply is no longer
  re-rendered from scratch each frame -- settled paragraphs keep their DOM
  identity, so a selection made mid-stream survives -- and the per-frame
  character step is capped, so a bursty network no longer paints a lump. On a
  real 4850-char reply: 38 network chunks averaging 127 chars became 619
  display frames averaging 7.8.
- **"Not now" on the update banner dismisses it**, keyed to the staged version.
- **Connector lookups scoped by provider**, closing a cross-provider read /
  validate / disconnect path that could strand a live token in the keychain.

## v2.115.1 (2026-08-21)

"Not now" on the update banner dismisses it. Deferring previously swapped the
countdown for a message with no buttons, leaving a permanent notice on screen
until the app quit. Dismissal is keyed to the staged version so a newer build
still announces itself, and a failed or already-armed install always shows.

## v2.115.0 (2026-08-21)

**Slack connects, disconnects and reconnects from the app.** Verified against a
real workspace: bot and user tokens in separate keychain slots, both rotating,
identity keyed team_id:user_id, no token bytes anywhere in the database.

The two defects that stood between a working connector and a usable one were a
reconnect that left the account ACTIVE and invisible simultaneously, and a
validate path that still called GitHub's client method on a Slack client. Both
were found by using the installed app; neither was reachable from the test
suite. Three new tests check the class of each rather than the instance.

## v2.113.3 (2026-08-21)

**Slack could never be connected after an app restart.** An idempotent
begin_connect kept returning an open transaction whose in-process loopback
listener had died with the previous process, so every Connect click resurrected
the same unusable flow. Strategies now declare whether they can still service a
transaction; one they cannot is retired and replaced.

Found by running the connect through the installed app rather than the test
suite -- the suite never restarts a process.

## v2.113.2 (2026-08-21)

Tiles share a height again, with their action buttons pinned to the bottom edge
so a row lines up without a short tile showing dead space. Connector failures
render as a sentence plus a hint keyed to the provider's error code, instead of
printing the structured error body as raw JSON.

## v2.113.1 (2026-08-21)

**Connector tile layout fixed, including a regression it had caused on the
Updates screen.** A tile clipped its own Manage button at two-column width,
tiles stretched to the tallest instead of sizing to content, the device-code
card's button label was an entire URL and overflowed a narrow pane, and a
global `a.btn` margin added for this screen had misaligned anchor-buttons
against real buttons panel-wide.

Two new tests check the blast radius rather than the four symptoms: the
connectors CSS may not add a global margin to `a.btn`, and every selector it
adds must be scoped to a connector container.

## v2.113.0 (2026-08-21)

**Slack is the second provider, and Connectors is now a tile view.** One tile
per provider whether connected or not, each stating its auth mode, whether it
can connect on this machine, and its caveat. Slack's tile says plainly that its
flow is weaker than GitHub's: no device flow, no PKCE, a loopback port.

Slack issues two tokens from one authorization -- a bot token that posts (so
agent actions are attributable to Sutra) and a user token that reads and
searches. They live in separate credential slots and disconnect erases both.

Adding a provider is now a registry row plus a package; the service, the API
and the screen no longer know which provider they are serving.

## v2.112.5 (2026-08-21)

**Connectors screen layout fixed.** An `<a class="btn">` was `display: inline`,
so its padding overlapped the surrounding text, and the activity table was
clipped at 407px with `overflow-x: visible`, silently losing its last column.
Anchors with `.btn` are `inline-block`; tables scroll in their own container.

Both were found by driving the real panel in a browser and measuring, not by
reading the source -- which is also how the dead buttons in 2.112.4 were
confirmed fixed.

## v2.112.4 (2026-08-21)

**The Connectors buttons work.** They were inert in 2.112.0-2.112.3: the click
handlers sat inside the rail's listener, which never sees clicks in the screen
body. The screen rendered fine, which is why the defect survived a screenshot
and 152 panel tests -- those extract panel.html's inline script, and this
screen is an external file.

Handlers moved to a document-level delegate scoped to `#scBody`, plus a new
10-test suite whose main assertion is general rather than specific: every
control the markup emits must have a handler, and every handler must have a
control.

## v2.112.3 (2026-08-21)

**Discovery stops re-asking GitHub on every page view.** With no installations,
`not installations` was true on each request, so the 15-minute cache was
bypassed and every call cost ~0.85s of live GitHub. A freshness marker now
records that GitHub answered, including when the answer was none.

Ships with the 2.112.2 thread fix: the Connectors screen is correct under
concurrency (60 requests, 12-way, all 200) and no longer chatty.

## v2.112.2 (2026-08-21)

**The Connectors 500 is fixed at the root.** A single SQLite connection was
shared across FastAPI's threadpool, and `sqlite3` binds a connection to its
creating thread. First request 200, next request on another worker 500. It
looked transient because a restart reset which thread held the handle, and it
escaped 164 tests and the CLI because both are single-threaded.

`Database` now keeps one connection per thread, with `busy_timeout` for
concurrent writers and a single shared handle for in-memory databases (a memory
database lives inside its connection). Four regression tests cover it,
including the end-to-end shape: construct the service on one thread, call it
from another.

Shipped together with the 2.112.1 diagnosability fix, which is what would have
named this failure in one step instead of several.

## v2.112.1 (2026-08-21)

**Panel connector errors became diagnosable.** A 500 on `/api/connectors` had
no discoverable cause: the endpoints caught only `ConnectorError`, and
Electron buffers backend stderr in memory unless the process exits, so the
traceback existed nowhere reachable. Unexpected exceptions now log to
`~/.sutra/panel-errors.log` and come back as a structured error the screen can
render. Separately, the service cached a SQLite connection for the process
lifetime with no way to recover a broken one -- it now health-checks and
rebuilds, and never caches a failed construction.

The original fault was not reproduced. Restarting cleared it. What is fixed is
the pair of defects that made it invisible and unrecoverable.

## v2.112.0 (2026-08-20)

**The connectors screen is live, and permissions are resolved from disk.** P3
lands the permission layer over real settings files, and the panel gets its
Connectors surface back -- rebuilt rather than restored: it renders the new
connector model, not the Composio/1MCP one that was removed.

What an operator can now do in the app: connect a GitHub account through the
device flow (the code is shown large and monospaced because it is transcribed
by hand into another window), see which repositories the installation actually
covers and what each one permits, see which organizations have Sutra installed
and which merely have you as a member, read the permission rules in the order
the engine evaluates them, and read the hash-chained audit trail. The panel
never sees a credential -- it deals in connector ids and connector state only.

**Honest scope:** the agent tool gateway is not built. Nothing invokes these
capabilities yet; the screen shows what WOULD be permitted. That is P4.

## v2.111.0 (2026-08-20)

**Connector platform rewrite: P1 + P2 + the permission engine.** The layer
deleted in 96edce8 is rebuilt as a provider-agnostic module under
`marketplace/plugin/connectors/`. GitHub is the first and only provider.
Authorization is the GitHub App device flow, which needs no client secret and
has no redirect URI at all -- deleting the entire callback attack surface. The
credential lives in the macOS Keychain; the database holds a reference and
expiry timestamps and no token bytes, verified by a raw scan of the db file.
The permission model is a port of Claude Code's own: `Tool(specifier)` rules,
deny -> ask -> allow with specificity never reordering, six modes, managed
settings that no other scope can override. 138 tests, zero new dependencies.

**Honest scope:** this is a library plus a CLI. `sutra-ui` is untouched, so the
installed desktop app has no connectors screen and no connect button. Wiring is
P3+.

## v2.110.1 (2026-08-18)

**Synced with upstream main; both connector models kept side by side.** This merge brings sankalpasawa/main (25 commits: Composio tool router, the 1MCP local aggregator, the chat governance surface, Balance graduation) together with this fork's line (agentic tool output, the transcript-pane fix, the update-check fix, asset cache-busting, Test pane removal). The connectors collision was resolved by keeping **both**: upstream's Hosted (Composio) and Local (1MCP) halves are the live screen, and this fork's **Present in Claude** mirror — the one half with no upstream equivalent, and whose `/api/connectors/configured` endpoint survives because it reads Claude rather than Sutra's own store — is kept beneath them. `connectors_store.py` and its 66 tests are retained in the tree; the preset gallery and registry search they backed are not re-wired, because upstream's local half now owns those routes. Version set to 2.110.1 as the base for the next connectors rewrite. Upstream's own notes below are labelled v3.0.0/v3.1.0; their `plugin.json` read 2.99.1, so the numbering here is deliberately ahead of both.

## v2.103.0 (2026-08-18)

**Checking for updates downloads them.** "Check for updates" found a new version and staged nothing — background staging ran only on the shell's timer (90s after launch, then every six hours), leaving the blocking "Download & install" (which quits the app) as the only manual path. The panel can't stage itself: that route is token-authenticated and the token never reaches the renderer, so a third preload verb asks the shell, like apply/defer. One download at a time, shared with the scheduled path; the screen stays usable and reports what actually landed. **Test pane** — an empty scaffold wired at three sites — is out of the Organization nav. 6 new tests; 92 panel tests green.

## v2.102.0 (2026-08-18)

**"Transcript not read yet" no longer sticks.** An open pane on an idle session could sit on that message forever: `ensureTranscript()` only acts on `unread` and was called only from the sites that open a pane (the ⋮ → "open in repo" action skipped it), while the background re-read fires only on a write to the file — which an idle transcript never gets. Reproduced live (8s, no recovery), then fixed structurally: `render()` schedules the read for every open pane, idempotent like `loadRepo` beside it, so every path into `openPanes` is covered. Also, `sessionBody()` no longer claims "not read yet" for a session that WAS read (`ok` with zero turns, which the busy guard produces without parsing). 5 new tests; 86 panel tests green.

## v2.101.0 (2026-08-15)

**Connectors mirror Claude.** A "Present in Claude" section reads the operator's own connectors live from `claude mcp list` and shows each with a status badge; configuring is delegated to Claude's own `claude mcp add` / `claude mcp login` flow rather than rebuilt, so Sutra never handles an OAuth token. Read-only endpoint behind a subprocess timeout + 30s TTL cache. 66 connector tests green.

## v2.100.0 (2026-08-12)

**Agentic output is captured and shown.** The transcript reader now records, for every tool call an agent (or subagent) makes, the tool name, the actual input (command / file path / pattern / query, capped) and the returned result (capped 8 KB, error-styled when the tool failed) — not just a bare tool name. The chat replay and the subagent viewer share one renderer (`toolCallsHtml`): each call shows a name pill, its command, and a collapsible **output** toggle that reuses the live tool-row open-state. Verified: parsing a real 9,979-line session captured 1,243 tool calls, 1,236 with output (name + input + result); 81 panel tests, JS syntax clean on all four touched modules.
## v3.1.0 (2026-08-13, upstream)

**A second connector: local MCP servers, assorted, behind one aggregator.** Composio is a hosted API for cloud SaaS and structurally cannot reach `filesystem`, `git`, `playwright` or `sqlite` — so the local half is back, and aggregated rather than multiplied. `local_store.py` fronts every enabled local server with **1MCP** (`@1mcp/agent`, Apache-2.0, `serve --transport=stdio`): one process the CLI spawns per turn, no daemon, no port. MetaMCP was the other candidate and lost on shape not licence (Docker + Postgres + its own web UI); `1mcp proxy` lost because it needs a long-lived `serve` to proxy to. **Assorting is real config, not a label:** every server carries a 1MCP `tag` — Composio's category for the same slug where one exists (so `github` files under `developer-tools` in *both* connectors), else a keyword heuristic that says it guessed and is editable per server. The screen groups by tag; `--filter` narrows on the same strings. Servers come from the **open MCP Registry**, so neither connector's catalog is hand-maintained. **Auto-update grows from three mechanisms to five:** local servers resolve at spawn time via `npx -y`/`uvx` (immediate), and the aggregator's pinned version tracks npm's `latest` dist-tag on a 24h TTL — pinned because an unpinned `npx -y` could swap the process fronting every local tool between two turns of one session. Optional switch routes Composio *through* the aggregator for one connector covering everything; off by default, and when on the direct entry is omitted rather than duplicated. A session sees at most three MCP servers (`sutra`, `composio`, `local`) however much is enabled. **CHARTER v0.4.0** admits the local aggregator as a third integration pattern and adds RULE 6 (invoked never imported, pinned, no privileged config) — **PROTO-019 codex review bypassed by explicit founder direction and marked as such in the charter**. Verified: 63 new backend tests (incl. provable negatives on the pin and the derived config), 329 Python + 112 JS all green; live-checked against npm, the MCP Registry and a real derived `mcp.json`.

## v3.0.0 (2026-08-13)

**Connectors are Composio.** The hand-maintained MCP model is gone — `connectors_store.py`, its ~50-preset gallery, the open-MCP-registry search, and the `~/.claude.json` import are deleted and replaced by Composio's *current* open-source connector: a tool router session (`POST /api/v3/tool_router/session`, the SDK's own `composio.create(user_id, mcp=True)` path — **not** the deprecated `composio.mcp.*` server API). One HTTP MCP endpoint now carries however many of Composio's **1181 toolkits** the operator enables, authenticated by an `x-api-key` header; per-toolkit OAuth is handled in-browser by the session's connection manager, so no login flow ships here. `workbench` is explicitly disabled per `connectors/CHARTER.md` RULE 2. **Auto-update, three mechanisms, stated separately:** new tools inside a toolkit need no client change (the endpoint is remote); the toolkit catalog tracks `ComposioHQ/composio@next:docs/public/data/toolkits-list.json` by ETag-conditional GET, TTL-gated on screen open *and* on the Electron shell's existing update tick; the session re-provisions when the (user id, toolkits) fingerprint changes. A vendored snapshot makes first run work offline. Verified: 56 new backend tests (incl. provable negatives against the deprecated API and against re-enabling the workbench), 175 app tests, 81 panel tests, 36 others — all green. **Breaking:** local stdio MCP servers (filesystem, git, playwright, sqlite) are no longer configurable from this panel.

## v2.99.0 (2026-08-12)

**Connectors gallery.** The Connectors screen's default view expands from 6 presets to a browsable gallery of ~50 recognizable MCP connectors, grouped into 11 categories (Development, Data & Databases, Productivity, Communication, Search & Web, Browser & Automation, Payments & Business, Monitoring & Cloud, Design, AI & Models, Utility) — every config verified against the live MCP registry or a documented remote endpoint (no invented package names). The full open registry (~400 servers) remains one search away; remote connectors carry auth headers. Verified live: 50 connectors / 11 categories render grouped; 56 backend + 81 panel tests.

## v2.98.0 (2026-08-12)

**Connectors = the open MCP Registry.** The catalog is live: an empty search shows curated presets, typing searches the official open MCP Registry (~400 servers, `registry.modelcontextprotocol.io`) and a result prefills the add form. Closed the Claude-parity gaps: auth **headers** for remote (http/sse) connectors — merged into the session's `--mcp-config` — and **Import from Claude** (adds the MCP servers already in `~/.claude.json`). Verified live: registry search returns real servers (github → 12), headers appear only for remote transports, curated presets on empty search; 53 backend + 81 panel tests. *(Next: an in-panel permission popup so a spawned session can ask to run a tool instead of stalling in text.)*

## v2.97.0 (2026-08-12)

**Two live-sync flicker fixes.** (1) "Transcript not read yet" no longer flashes on an open pane: `adoptRealSessions` preserves the pane you're reading (turns + loadState) across the frequent list refreshes agent activity triggers, instead of rebuilding it as "unread". (2) The heavy flicker while agents work is gone: `applySessionChange` keeps the transcript on screen during a background refresh (no "reading transcript…" flip) and throttles re-reads + agent-fold reloads to ~1/s. Verified at the state level: an open loaded pane survives a refresh; a background re-read never hides content; a 2nd event within a second starts no re-read. Connectors re-confirmed (33 backend tests + the mcp-config merge).

## v2.96.0 (2026-08-12)

**Connectors + update-banner fix.** New Connectors screen (Runtime) to add MCP connectors — like Claude CLI's — by hand (stdio command/args/env, or a remote http/sse url) or one-click from a catalog (github, filesystem, slack, puppeteer, brave-search, linear); enabled connectors are merged into the `--mcp-config` passed to every spawned session (alongside `sutra`, keeping `--strict-mcp-config`), running under the session's permission mode. Store at `~/.sutra-ui/connectors.json`, fail-soft. Also fixes the "Restarting in nulls" update banner (a dedicated restarting state + a null-safe countdown). Verified live: the screen adds/toggles/removes connectors and an enabled connector reaches the session's MCP config; 33 backend + 81 panel tests.

## v2.95.0 (2026-08-11)

**First release published entirely through GitHub Actions.** With the signing + notarization secrets wired, pushing a `v*-desktop` tag builds both arches on native runners, signs with the Developer ID, notarizes via the App Store Connect API key, and uploads `Sutra-<arch>.dmg` — no local build. Also fixes `test_charter_filter.js`, which had failed every CI run since the panel split.

## v2.94.0 (2026-08-11)

**Native folder picker, finished.** The Browse… button opens Finder at your current folder (a tilde-expanded `defaultPath` is passed through the IPC), and a pick in the composer's working-directory control applies immediately — the old code wrote it to the input with no backing state, so a live re-render could wipe it before SET. Settings keeps the fill-a-draft-then-Save flow; the routine folder field persists to its form; the handler returns null on any dialog error. Verified end-to-end headlessly: the button renders only with the Electron bridge present, the current path is passed as the dialog default, and the pick is applied to the session.

## v2.93.0 (2026-08-11)

**Subagent viewer = Claude's agent view.** The subagent list stops being a wall of raw prompt text: each agent is a clean card (real title + agent-type badge + "N steps · tools · relative time"), and clicking one opens a readable step-by-step transcript — the task it was handed (collapsed), each assistant step with its tool calls, and the final message set apart as the result. Backend: `list_agents` joins to the parent's `Task` tool_use for the description/subagent_type and counts assistant steps (real work) instead of the always-1 user-turn count. Verified live on this session's 43 agents; kept the Sutra theme.

## v2.92.0 (2026-08-11)

**Activity: header trigger + right drawer.** The Activity panel moves from a bottom-right floating widget to a compact trigger in the chat header's top-right (a live count badge that pulses on activity) that opens a right-docked, non-modal drawer — "Running turns" + "Agents" with stopwatches — matching Claude's Background-tasks placement. Close via ×, Escape, or re-click. Verified live in the browser: the trigger renders in the header, the drawer opens/closes, the badge syncs to the running count, and this session's own turn appears with a ticking stopwatch. Plus formal evals for `/api/activity`, `head_meta`, and the picker gate.

## v2.91.0 (2026-08-10)

**Live Activity panel + native folder picker.** A floating, collapsible Activity panel (bottom-right) surfaces all running work live — in-flight chat turns and running subagents, with a count badge and per-item stopwatch — Sutra's equivalent of Claude's Background-tasks view, backed by a new read-only `/api/activity` that reuses the existing liveness logic. Plus a native macOS Finder "Browse…" button on every working-directory control (new `sutra:pick-directory` IPC), with the text field kept as an editable fallback. Built by two parallel agents on disjoint files; verified live (endpoint caught this session's own turn; 76/76 panel tests; zero console errors).

## v2.90.0 (2026-08-10)

**Notarized desktop build.** Everything in v2.81.0 — live sync, resume correctness, the running-turn strip, the subagent viewer, the per-session ⋮ menu, the panel split, and the working-directory / usage / repository controls — now Developer ID–signed and **Apple-notarized** for both arm64 and x86_64. No source change since v2.81.0; the version is realigned for a clean notarized release that supersedes the un-notarized 2.81.0-desktop DMGs.

## v2.81.0 (2026-08-09)

**The desktop panel becomes one entity with Claude.** Live sync (a chat in Claude appears and updates in Sutra as written) plus resume-in-the-right-folder so a reply from Sutra continues the same Claude conversation instead of forking; titles you set in Claude; a running-turn progress strip with a stopwatch; a subagent transcript viewer (the "N agents" badge now opens each agent's turns) and correct async-agent completion timing; a per-session ⋮ menu (Open in / Pin / Unread / Rename / Fork / Group / Archive / Delete, with rename appending Claude's own custom-title record and archive/delete moving files recoverably); a real keyboard layer; and working-directory / usage / repository controls in the composer. Architecture: panel.html split into panel.css + 9 JS modules, behaviour-preserving, so UI iteration touches one small file. Also fixes the catalog-vs-source version drift (both now 2.81.0). Verified in the running app end to end.

## v2.79.0 (2026-08-07)

**Balance screen beauty pass.** Serif greeting with the day's one-liner, insight cards as accented stat tiles, day strip in a card with hour marks, polished composer — all from existing panel tokens; visual-only.

**This file had gone stale at v2.43.0.** Thirty-six releases shipped to the fleet while `CURRENT-VERSION.md` still named v2.43.0 as HEAD — the catalog (`.claude-plugin/marketplace.json`) and the plugin manifest (`marketplace/plugin/.claude-plugin/plugin.json`) both read 2.79.0, and the plugin CHANGELOG carried every entry. Anyone reading this file to find the current version got an answer 143 commits out of date. The gap is closed here; the arcs it covered are summarized below and detailed in `marketplace/plugin/CHANGELOG.md`.

**What shipped between v2.43.0 and v2.79.0**

| Range | Arc |
|-------|-----|
| v2.44.0 – v2.47.0 | **Placement engine.** Per-turn block + warn-first gate, then the engine itself (addresses are computed, not typed), the last mile (the block is engine output), and the codex F7.1 dual-lane review folds. |
| v2.47.1 – v2.63.0 | **Domains layer.** `core:departments` MECE view, fleet page, grounding rungs, drill-down zoom pages, ledger close with on-touch minting, the charter layer (projects as charters), consumer charter pages, `charters_seed.py` / `domains_pipeline.py`, and on-the-fly hydration with fast-lane data pushes. |
| v2.53.0 – v2.53.1 | **Flow orchestrator mode v1.** D62 / ADR-029 flag-gated dispatch — contracts, matcher, factors, ledger, fixtures. Flag moved off → experimental. |
| v2.58.0 | **Markers Scheme A concurrency core.** Self-only adoption, ownership-safe reset, session-first gates. |
| v2.64.1 – v2.65.0 | **Dispatch runtime to the fleet**, plus three governance hooks that had been misfiring. |
| v2.66.0 | **Daily auto-update** at the first session of the day. |
| v2.68.0 | **Telemetry on by default** (D64) — anonymous, once daily. |
| v2.69.0 – v2.72.0 | **Desktop panel.** Permission mode moved beside the composer with effective-mode clamping, streaming rewritten to patch a single node (0 full re-renders over 40 token frames), Routines on launchd with write-capable modes unreachable by construction, staged mandatory auto-update behind a shell-minted token, dual update checks in Settings, and `verify-runner` fleet-wide as the base of the Eval Engine (ADR-031). |
| v2.73.0 – v2.79.0 | **Balance module.** Design preview → chat live on a preloaded session → real observations → v3 founder redline → human register cards (evidence-gated, tempo not emotion) → this beauty pass. |
| v2.78.0 – v2.78.2 | **Usage-guard (opt-in, dormant by default).** Warns at 70% rate-limit utilization, HARD-blocks at 80% until `sutra-usage continue`; both the session (5h) and 7-day windows shown on every surface. |

## v2.43.0 (2026-07-28)

**Removed: the H-Sutra header Stop enforcement layer.** `hooks/h-sutra-enforce.sh` is deleted and its Stop registration is gone. No profile gets a block, a warning, or a forced redo for a missing or malformed header any more. Founder direction, 2026-07-28 — the layer had produced repeated forced redos for a formatting slip that changes nothing about the work.

**What survives.** The header is still a convention: `/core:start` documents the format, `per-turn-discipline-prompt.sh` still asks for it on every turn, the `core:human-sutra` skill is untouched, and the 9-cell classification log rail (`holding/state/interaction/log.jsonl` / `.sutra/h-sutra.jsonl`) keeps recording — that rail was always written by `per-turn-discipline-prompt.sh`, never by the enforcer.

**What dies with it.** The `.enforcement/h-sutra-audit.jsonl` enforcement telemetry, and the `SUTRA_HSUTRA_ENFORCE_DISABLED=1` / `~/.h-sutra-enforce-disabled` kill-switches (nothing left to disable — the sentinel file is now inert and can be deleted).

**Stop floors that remain HARD.** `per-turn-hard-gate.sh` (Input Routing, Depth, and BLUEPRINT on mutating turns) and `flow-stop-check.sh` (Flow, `profile=company` only). `sutra-defaults.json` now records `per_turn_blocks.human_sutra_header.enforcement = convention_only`, and the `/core:start` CLAUDE.md template no longer claims the header is hard-enforced. Re-run `/core:start` after updating to regenerate the block.

Unit suites unchanged at 21/23 — `test-codex-directive-detect.sh` and `test-codex-directive-gate.sh` stay red, pre-existing and off this path.

## v2.42.0 (2026-07-28)

**Two Stop layers stop punishing correct behavior.**

1. **`blueprint-check.sh` v3 — text-first (#81).** The hook had only ever read `.claude/blueprint-registered`, while every surface told the model to *emit the block*. A model could emit a complete, correct BLUEPRINT in the response the user reads and still be HARD-blocked, with no re-emission able to help. Three incidents came from that one divergence (#68 2026-05-23; the Testlify field incident 2026-07-08, where the model escaped via a Bash + `BLUEPRINT_ACK` bypass the error text taught; a repeat 2026-07-27). v3 validates the BLUEPRINT **in the turn's response text** — the same source `per-turn-hard-gate.sh` already uses for Input Routing + Depth. The marker becomes a per-turn cache the hook writes for itself; nothing asks the model for it. PreToolUse enforcement narrows to **foundational paths**, whose globs move to `per_turn_blocks.blueprint.foundational_paths` in `sutra-defaults.json` (overridable per repo via `blueprint_foundational_paths[]` in `.claude/sutra-project.json`) — they had been hardcoded to the Asawa layout, so on every other install the "important documents" set was empty. Ordinary files are floored at Stop by a new BLUEPRINT arm in `per-turn-hard-gate.sh`, armed only when the turn actually mutated a governed file. Degrades to the legacy marker check when no transcript or python3 is available. Tests: `test-blueprint-text-first.sh` 25/25, `test-per-turn-hard-gate-blueprint.sh` 13/13, existing blueprint suites 6/6 + 6/6.

2. **`h-sutra-enforce.sh` v8/v9 + `flow-stop-check.sh` honor `.profile` (#72).** `DIRECTION·VERB` is now case-insensitive (Postel's law — emit UPPERCASE, accept any case), killing the case-error block class. Only `profile=company` gets a forced redo; `individual` / `project` / unknown get warn + log. **Fail-open by design:** no `sutra-project.json` or no `jq` → warn, never a hard block. The `Enforce: warn-only` banner is finally true for the loud layers too. Note for `project`-profile repos (including asawa-holding): H-Sutra and Flow drop from forced redo to warning — set `"profile": "company"` in `.claude/sutra-project.json` to keep the hard redo.

3. **Release hygiene.** The `marketplace.json` catalog had drifted to 2.39.20 while source read 2.41.2 — two releases of narrative the catalog never carried. Both now read 2.42.0 and `test-validate-manifest-json.sh` is green again.

Known-red suites on this release, pre-existing and untouched here: `test-codex-directive-detect.sh` (11/20) and `test-codex-directive-gate.sh` (3/12). Both fail identically on the parent commit; neither is on the blueprint or Stop-layer path.

## v2.40.0 (2026-07-20)

**D63 — per-turn stack HARD fleet-wide.** New Stop floor `per-turn-hard-gate.sh` makes Input Routing + Depth hard on no-tool turns (like Flow / H-Sutra already are); `codex-consult-gate.sh` hard at Depth ≥ 3 (degrades without codex); `/core:start` contract expanded 4 → 9 blocks; both new gates activate only post-onboarding, so enforcement never precedes the contract. Codex CHANGES-REQUIRED folded (5 fixes). New hooks: `per-turn-hard-gate.sh`, `codex-consult-gate.sh`, `codex-consult-marker.sh`.

## v2.39.20 (2026-07-08)

**Blueprint marker visibility + out-of-repo guard (Testlify field incident 2026-07-08).** A fleet client emitted a correct prose BLUEPRINT (Output + Verified-by included) and `blueprint-check.sh` still HARD-blocked Write twice — the hook reads ONLY `.claude/blueprint-registered`, and no fleet-visible surface (per-turn reminder, hook stderr) said to write it; the marker contract lived solely in the non-auto-invoked `core:blueprint` skill. The model's only advertised exit (`BLUEPRINT_ACK=1`, unusable on Write tool calls) taught a Bash+ACK bypass of the gate. Fix 1: `per-turn-discipline-prompt.sh` now states the marker contract (write the marker via the Write tool with `HAS_OUTPUT`/`HAS_VERIFY`/`HAS_PER_STEP_VERIFY`) before the first Edit/Write of each turn. Fix 2: `blueprint-check.sh` out-of-repo guard — absolute paths outside `$CLAUDE_PROJECT_DIR` (`~/.claude/**` memory files, sibling repos) are out of scope; they could never match any whitelist and were blocked by accident. Inside-repo enforcement unchanged. Tests: `test-blueprint-marker-visibility.sh` 6/6. Fix + bump ship together (self-shipping PR #80). (#78 depth-gate + error-text split ships separately; A4 text-validation via #73.)


## v2.39.19 (2026-07-06)

**#63 — /core:start documents the H-Sutra header contract it enforces.** `h-sutra-enforce.sh` HARD-blocks every response whose first line isn't a valid header, but `/core:start` wrote a CLAUDE.md governance block with zero references to that header (`grep "H-Sutra|DIRECTION|VERB"` → 0 hits) — an invisible rule that caused repeated "redo with the header" blocks. `scripts/start.sh` now writes an **"H-Sutra Header"** section (exact format, DIRECTION/VERB vocabulary, example, STAGE-1-FAIL variant) as the first documented behavior; the hook's diagnostic points to it. Verified: generated-block grep → 5 hits. The fix + this version bump ship together in this PR (self-shipping). After update, clients re-run `/core:start` to regenerate the block. (A4 block-text validation ships separately via #73.)


## v2.39.18 (2026-06-30)

**loop-budget-guard: per-turn reset + agent-orchestration exemption (fixes the session-wide hard-stop).** The guard's tool-call counter was cumulative-per-session and never reset, so a long working session crossed the 250 ceiling on ordinary Bash/Read/Write calls and hard-stopped itself ("tool-budget guard hard-stopped further file reads this session") — and the deadlock blocked the very Bash needed to update out of it. New `loopguard-turn-reset.sh` (UserPromptSubmit) truncates the counter at the start of each real user turn → budget is now **per-turn** (a 250-call runaway in one turn still blocks; synthetic turns skipped, so within-turn loop detection is intact). `Agent`/`Task`/`Workflow` dispatches are exempt from counting (a fan-out is not a loop; opt back in with `LOOP_GUARD_COUNT_AGENTS=1`). Guard suite 12/12. Also ships **A4 block-text validation** (`perturn-text-validate.sh` — validates the emitted Input Routing / Depth / Output Trace; `blueprint-text-validate.sh` detection hardening; profile-aware). D13 cascade: risk LOW, backward-compatible.


## v2.39.17 (2026-06-25)

**Loop/tool-budget guard promoted to L0 (A6).** Always-on PreToolUse hook blocks runaway agents + infinite loops before execution; fail-open. Per-session budget (250) + frequency-in-window repeat detection; kill-switches + LOOP_GUARD_ACK. 8/8 tests. D13 cascade: risk LOW.


## v2.39.13 (2026-06-14)

**Flow fires every turn like the H-Sutra header — emission_mode literal-text fix.** Root cause: Flow was the only per-turn block with `emission_mode: skill_invocation` (a Skill tool call), which the model rationalized skipping on light turns while literal-text blocks (header/routing/depth) fired reliably. Fix: fast-path now emits a literal one-line `FLOW: <type> · fast-path · <n> atom · classify->answer` block as TEXT every turn; the `core:flow` Skill is invoked only on substantive/multi-step/mutation turns. Two files: `sutra-defaults.json` `.per_turn_blocks.flow` + `hooks/per-turn-discipline-prompt.sh` FLOW ACTIVATION block (duplicate Backstop line collapsed).

## v2.39.12 (2026-06-14)

**flow-gate HARD fleet-wide.** Edit/Write to non-whitelisted path or Task/Agent dispatch without core:flow markers → exit 2.

## v2.39.11 (2026-06-14)

**Flow on EVERY input/type + 1-step fast-path for trivial; gate widened to Task/Agent.** sutra-defaults all-types + cost_model, per-turn reminder, flow-gate Task branch.

## v2.39.10 (2026-06-14)

**Flow auto-activation — core:flow fires per turn, TYPE-gated** (work-bearing turns run the spine; trivial skip). sutra-defaults.json per_turn_blocks.flow + per-turn-discipline-prompt.sh reminder + flow-gate backstop.

## v2.39.9 (2026-06-14)

**The Flow — work-resolution spine shipped as skills (core:flow + workflow-type-resolve + lens + cynefin) + SOFT flow-gate hook.** Canon ADR-026 + ADR-027. See plugin CHANGELOG.

## v2.39.6 (2026-05-31)

**Prompt-capture hook (UserPromptSubmit) — fleet L0.** Every founder prompt is appended losslessly to the project's `holding/state/prompts/<YYYY-MM>.jsonl` (ts · session_id · prompt). Non-blocking; kill via `PROMPT_CAPTURE_DISABLED=1` or `~/.prompt-capture-disabled`. Registered in `hooks/hooks.json` UserPromptSubmit. Promoted from Asawa-local L1 same day.

## v2.39.5 (2026-05-28)

**`h-sutra-enforce` hook — actionable mis-cased-header error.** Malformed (Title-case/lowercase DIRECTION·VERB) headers now report "DIRECTION·VERB must be UPPERCASE" with a canonical example, instead of the misleading "header missing". Valid-header pass/block logic unchanged (regression-tested).

## v2.39.4 (2026-05-13)

**`prd-discipline` skill v2** — REFACTOR pass plugs 5 baseline-test rationalizations.

- Skill body at `sutra/marketplace/plugin/skills/prd-discipline/SKILL.md`.
- v2 additions: §1 namespace-collision check + naming-with-alternatives · §3 scale-undershoot surface · §4 canon-typed-entity rule · §5 TODO-is-not-an-alibi.
- Baseline test at `.enforcement/skill-tests/2026-05-13-prd-discipline-baseline.md`.
- Run `/reload-plugins` to activate.

## v2.39.3 (2026-05-13)

**Add `prd-discipline` skill** — product-document writing discipline.

- New skill at `sutra/marketplace/plugin/skills/prd-discipline/SKILL.md`.
- 5 invariants: STRUCTURED · VISUAL FIRST · RESTRUCTURE-ON-BULK · CONNECTED · GAP-SURFACING.
- Composes with ADR-020 Layer-B Product Authoring Template.
- Run `/reload-plugins` to activate in-session.

## v2.39.2 (2026-05-13)

**Remove 15-min hard cap on `codex-sutra` + `deepseek` skills** (founder D2026-05-13).

- 900-s wrapper kill removed from both skills; replaced with SIGINT trap (founder Ctrl-C → SIGTERM/SIGKILL on the whole process group).
- Heartbeat warnings now fire every 10 min during long-running calls (was one-shot at 10 min). Stall warn at 5 min no-progress unchanged.
- `deepseek`: `curl --max-time 900` flag removed — DeepSeek API server-side timeout is the only network bound.
- `sutra-defaults.json`: `deepseek.limits.wall_seconds_hard_cap` is now `null`.
- Fail-closed: `Hard-cap timeout / reason=timeout / exit 124` → `Founder interrupt (Ctrl-C) / reason=interrupted / exit 130`.
- Native canon: `phase-D-codex-review.md` + `HS-7-codex-queue-stale.md` updated with amendment line. HS-7 itself unchanged (watches review-backlog health, not per-call duration).

Rationale: long-reasoning runs were being killed before completion. Founder Ctrl-C is the only interrupt path now; stall + heartbeat keep silent hangs observable.

For prior release history, see `marketplace/plugin/CHANGELOG.md`.

---

provenance: maintained by Sutra release process; newest release first, HEAD marks the shipped version.
