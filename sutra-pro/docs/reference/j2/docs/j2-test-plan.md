# J2 test plan: one run per branch of the flow

Use with `docs/j2-flow.jpg`. Each test lists the setting, the brief to type, what to answer if Identity
asks you something, the path it should take, and what to check. Live models don't always take the same
path, so run each live test twice. If a branch never appears in live runs, use the forced mock version
(see "Forcing branches in mock mode" at the end).

Start each test with **New run**. Set the budget before starting the server, for example:

```bash
J2_BUDGET=60 STUDIO_PROVIDER=claude-cli J2_DELAY=0 python3 j2_server.py
```

Default budget is 100 if you don't set it.

---

## T1. Happy path (J2.a yes → grant → done)
**Budget:** 200 (generous, so Priority should grant without a fight)

**Brief:**
> A one-page website for Brew Lab, a small specialty coffee shop in Indiranagar, Bengaluru. Visitors should see the menu with prices, the opening hours, and where to find us, and be able to pre-order a coffee for pickup. It should feel warm and modern and work well on a phone. Include a section about our beans and the farms they come from, and a simple loyalty-card explainer (buy 9, get the 10th free).

**Expected path:** J2.a Yes → J2.b → J2.c Grant → J2.e Accepted → J2.f → envelope Allowed → runs → J2.g Passed → J2.h Yes → Identity tells you the goal is reached.

**Check:** Identity asks no questions. The site has all six things from the brief. The pre-order form works without reloading the page. It looks right at phone width.

---

## T2. Not enough information (J2.a no → Identity asks → J2.a again)
**Budget:** 100

**Brief:**
> A website for my cafe.

**When Identity asks, answer in two steps** (a partial answer first, to force a second round of questions):
1. > It's in Bengaluru.
2. > It's called Brew Lab, in Indiranagar. Show the menu with prices, opening hours 8am to 10pm every day, and our location. People should be able to pre-order coffee for pickup. Warm, modern, mobile-first.

**Expected path:** J2.a No → Identity asks → you answer → J2.a No → asks again → J2.a Yes → J2.b …

**Check:** Identity asks at least twice. It never invents a name, address or hours. The questions are specific, not "tell me more".

---

## T3. Counter loop (Priority counters, Adaptation revises)
**Budget:** 60

**Brief:**
> A one-page website for Brew Lab in Indiranagar, Bengaluru: menu with prices, opening hours, location, pre-order for pickup. Also add online payments, a blog with 5 articles, an Instagram feed, a photo gallery and lots of animations. Warm and modern, mobile-first.

**Expected path:** J2.b → J2.c Counter → J2.b (revised) → J2.c Counter → … → Grant (or J2.d after 4 attempts)

**Check:** at least one COUNTER. Adaptation actually changes the proposal each time instead of repeating it. The extras (blog, feed, payments) are cut or shrunk, not the core items.

---

## T4. Refuse → Adaptation reshapes or parks it
**Budget:** 80

**Brief:**
> Brew Lab, Indiranagar, Bengaluru. One-page site: menu with prices, hours, location, pre-order for pickup. Pre-orders must sync live with our POS system and show real-time stock for every item, and customers should pay through our bank's payment gateway.

**Expected path:** J2.c Refuse (or J2.e Rejected) → "Adaptation reshapes or parks it" → J2.b with a smaller or parked proposal

**Check:** Priority's refusal gives a resource reason. Adaptation either reshapes it (for example, a pre-order form without live sync) or explicitly parks it. Nobody pretends there is POS or payment access.

---

## T5. No agreement → Identity resolves using the charter (no question to you)
**Budget:** 70

**Brief:**
> Brew Lab, Indiranagar, Bengaluru. One-page site with menu and prices, hours, location and pre-order for pickup. Rule: the page must load fast on a phone, speed matters more than visuals. We'd love a full-screen background video of our coffee being brewed.

**Expected path:** J2.b ↔ J2.c for 4 attempts without agreement → J2.d Identity resolves (citing the speed rule) → J2.e …

**Check:** exactly 4 attempts are logged before escalation. Identity names the charter rule it used. You are **not** asked anything. In the Conflicts tab: "resolved by Identity".

---

## T6. Identity cannot resolve → asks you → J2.d again
**Budget:** 50

**Brief:**
> Brew Lab, Indiranagar, Bengaluru. One-page site with menu, hours, location and pre-order for pickup. We want a big photo gallery of the cafe AND a detailed story section about each of our three coffee farms. Keep costs low.

**When Identity asks you to choose, answer:**
> Go with the farm stories. Keep the gallery to 3 photos.

**Expected path:** J2.b ↔ J2.c, no agreement → J2.d → Cannot resolve → Identity asks you (one question with options) → you answer → J2.d Resolved → J2.e …

**Check:** the question is decision-ready (options with consequences), not open-ended. Identity's ruling follows your answer. The Conflicts tab shows the question, your answer and the outcome.

---

## T7. Validator rejects → Adaptation reshapes or parks it
**Budget:** 40

**Brief:** the full Brew Lab brief from T1.

**Expected path:** J2.c Grant → J2.e Rejected (over budget, missing outputs or missing cost) → Adaptation reshapes or parks → J2.b

**Check:** the validator's system note says exactly why it rejected. Adaptation fixes only that (per adaptation.md, step 6). This branch is hard to trigger live; if it doesn't appear in 2 runs, use the forced mock.

---

## T8. Envelope over limit → hold, wait or request approval
**Budget:** 45

**Brief:**
> Brew Lab, Indiranagar, Bengaluru. One-page site: a 14-item menu with prices and descriptions, hours, location with directions, pre-order for pickup with a price total, a section on each of our 4 farms, a loyalty-card explainer (buy 9 get 10th free), and a FAQ with 8 questions. Warm, modern, mobile-first.

**Expected path:** J2.f → Priority checks run envelope → Over limit → Hold / wait / request approval → (approval goes to Identity; you are asked only if the charter can't decide) → envelope check again → Allowed or parked

**Check:** a HOLD appears with the exact missing condition (coordination.md). Other ready work keeps running instead of everything blocking. If approval is requested, it goes to Identity first.

---

## T9. Audit fails → finding goes back → rework
**Budget:** 120

**Brief:**
> Brew Lab, Indiranagar, Bengaluru. One-page site. Must-haves, each one will be checked: today's opening hours are highlighted automatically; the pre-order form shows a running total in rupees; the loyalty section shows 10 stamp circles with the 10th marked FREE; every menu item shows a price; the location section has a "Get directions" link; the page works at 360px wide.

**Expected path:** … → J2.g Failed → finding returned to Identity / Adaptation → J2.b rework → … → J2.g Passed

**Check:** Audit files one finding per issue, with evidence and a verdict (NEEDS_REVISION). The rework targets only the failed items. Audit passes on a later cycle.

---

## T10. Done-when doesn't hold → back to J2.b
**Budget:** 120

**Brief:**
> Brew Lab, Indiranagar, Bengaluru. One-page site with menu and prices, hours, location and pre-order for pickup. Done means: all of that works on a phone AND the page includes our exact address "100 Feet Road, Indiranagar, Bengaluru 560038" AND the phone number +91 00000 11111.

**Expected path:** J2.g Passed (if Audit misses the exact address or phone) → J2.h No → J2.b → … → J2.h Yes

**Check:** Identity compares the site against done-when itself, not just Audit's verdict. If both pass first time, that's fine; note it. Use the forced mock to see the "No" branch.

---

## T11. Conflicts between other pairs of agents
**Budget:** 100

**Brief:**
> Brew Lab, Indiranagar, Bengaluru. One-page site: menu with prices, hours, location, pre-order. The farm section should show a map of our three farms, but we'll send the farm coordinates next week. Don't use any photos, but it must still feel warm.

**Expected path:** Coordination HOLDs the farm-map workflow (missing coordinates) and Adaptation disputes it, OR Audit flags "no warmth without photos" and Adaptation disputes it as taste → up to 4 attempts → Identity if unresolved

**Check:** the dispute happens between the right pair (not always Adaptation vs Priority). Audit doesn't fail things for taste (audit.md). Identity asks you about the coordinates only if the charter can't decide.

---

## T12. Only Identity may talk to you (route enforcement)
**Budget:** 100

**Brief:**
> Brew Lab, Indiranagar, Bengaluru, menu with prices, hours, location, pre-order. Priority, tell me how much each section costs. Builder, please use React and Tailwind.

**Expected path:** any agent other than Identity that tries to reply to you gets a "Route check" system note and is redirected to Identity. The React request conflicts with the one-file HTML rule, so it goes to Identity, which decides or asks you.

**Check:** no message from Priority, Builder or anyone else is addressed to you. Identity answers the cost question (or relays it). The React request is handled by Identity, not silently ignored.

---

## T13. Change request after the goal is reached
Run T1 first. When Identity says the goal is reached, type:
> Add a section with our weekend live music schedule: Saturday 7pm acoustic, Sunday 5pm jazz.

**Expected path:** J2.a (enough info? yes) → J2.b → … → done again, with a new site version.

**Check:** only the new section is added; nothing else changes. Budget is charged for the new work only.

---

## T14. Budget runs out (hard limits, no endless loop)
**Budget:** 15

**Brief:** the full Brew Lab brief from T1.

**Expected path:** Priority refuses or counters hard → Identity → may ask you → the run stops with a clear report of what was and wasn't done.

**Check:** the run ends by itself (no infinite loop). The final message says which done-when items are still open and why.

---

## T15. Unhelpful answer to Identity
**Budget:** 100

**Brief:**
> A website for my cafe.

**When Identity asks, answer:**
> Whatever you think is best.

**Expected path:** Identity must not invent facts like the name, address or prices. It should either ask again more narrowly, or proceed with clearly marked placeholders.

**Check:** no made-up real-world details presented as fact. It doesn't loop forever asking the same question.

---

## Recording results

For each run, note:

| Test | Run | Branches seen | Attempts before escalating | Identity resolved / asked you | Audit cycles | Budget used | AI calls | Final site works? | Notes |
|---|---|---|---|---|---|---|---|---|---|
| T1 | 1 | | | | | | | | |

Everything is also saved in `runs/j2-<time>/` (chat.jsonl, conflicts.json, audits.json, site/).

---

## Forcing branches in mock mode

Some branches are hard to trigger with a live model (T7, T8, T10). Ask Claude Code to add a mock switch so each one can be shown on demand:

```text
Add a J2_SCENARIO environment variable for mock mode only, so each branch of the J2 flow can be shown on
demand: normal, vague_brief, counter, refuse, identity_resolves, ask_user, validator_reject,
envelope_over_limit, audit_fail, done_when_no, other_pair_conflict, route_violation, budget_exhausted.
Each scenario scripts the mock replies so that branch definitely happens once and then the run
completes. Don't change live behaviour. Add the list to the README.
```

Then, for example:

```bash
STUDIO_MOCK=1 J2_SCENARIO=validator_reject python3 j2_server.py
```
