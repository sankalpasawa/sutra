# HANDOFF-PROGRESS — "Check for changes" now says what it is doing

**written**: 2026-09-10 · **covers**: `agents_api.py` (`/knowledge/refresh*`),
`static/js/17-agents.js` (the site-catalogue card), `static/agents.css`, `test_agents.js`,
`test_agents_api.py`

The bug: `api_knowledge_refresh` built its context as
`{"chat_id": "knowledge", "run_id": "refresh", "emit": lambda **kw: None}`, so every line
`refresh_site` said went into a no-op, and the route then blocked until the whole run came back.
The card had one FIXED sentence to draw ("Asking the site for its current list…"), which it would
have drawn for ever whatever the engine was doing. A run that sat in six minutes of firewall
cooldowns therefore looked exactly like a hang, and exactly like a finish.

The work was always right. Only the telling was missing.

---

## 1. What changed, in one line

`POST /knowledge/refresh` now starts the tool on a thread and returns; the engine's own lines are
recorded as they arrive; `GET /knowledge/refresh` is the one read the card polls, on the same
cadence and in the same shape as the workspace job beside it.

| Route | Does |
|---|---|
| `POST /knowledge/refresh` | starts it (`preview` / real), returns `{started, job}`; 409 if one is already running |
| `GET  /knowledge/refresh` | `{job}` — the lines so far, whether it is waiting, and the counts or the reason when it stops |
| `POST /knowledge/refresh/dismiss` | forgets a job that has STOPPED (409 while it runs) |

The job carries `label` from `registry.LABELS["refresh_site"]` ("Catching up on what changed"), so
the button reports as the tool it is rather than as an anonymous button.

---

## 2. What this depends on inside `seo_agent/` — NOT edited, and worth knowing

**a. The wait state is read out of fetch.py's own sentence.** `fetch.py` line ~457 emits
`("The site's firewall pushed back", "waiting 120s before trying <url> again, …")` BEFORE it
sleeps. `agents_api._KN_WAIT` (`/waiting\s+(\d+)\s*s\b/i`) reads the number out of that note and
marks the job `waiting: {seconds, since}`, which is what lets the card draw a held dot and
"Waiting on the site · 30s of 2m" instead of a spinner that claims work.

That is a coupling on a sentence. **If that wording changes, the wait state silently stops
working** and a cooldown goes back to looking like a working step — no test in `seo_agent/` would
catch it. The clean fix, whenever someone owns that file: have the emitter carry the wait as a
field (`emit(..., waiting_s=120)`) and let `_KN_WAIT` become a fallback. Nothing else in the
progress path guesses at anything; this is the only inference.

**b. The long silent stretch is already covered, and should stay that way.**
`reconcile._fetch_pass` emits "Still reading pages · N of M fetched" periodically. That line is
now the thing keeping the card alive through the expensive part of a real refresh. Please do not
drop it.

**c. `ctx` is `{chat_id, run_id, step_id, emit}`.** `step_id="refresh_site"` is passed so
`sh.reporter`/`sh.substep` parent their substeps the same way they do inside a run.

---

## 3. The rule the card is built to

Every word of progress on screen was said by the engine. The labels and notes are shown verbatim
and are never reworded on the client — two wordings of the same step would drift, and the version
this replaced was exactly a sentence the client had made up. The only text the card adds is about
itself: how long since the last line arrived, and whether it is still hearing from the app.

Four states and no fifth: working · waiting · done (the counts land where the spinner was) ·
stopped (the reason, and nothing spinning). A running job whose worker thread has gone is
reported as failed by `_kn_get_job`, because a spinner left over a stopped run is the bug.
