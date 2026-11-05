# J2 prompts: copy and paste for manual testing

For each test: stop the server (Ctrl+C), run the command, click **New run**, paste the brief,
and paste the replies when Identity asks. Checks and expected paths are in `j2-test-plan.md`.

---

## T1. Happy path
```bash
J2_BUDGET=200 STUDIO_PROVIDER=claude-cli J2_DELAY=0 python3 j2_server.py
```
Brief:
```text
A one-page website for Brew Lab, a small specialty coffee shop in Indiranagar, Bengaluru. Visitors should see the menu with prices, the opening hours, and where to find us, and be able to pre-order a coffee for pickup. It should feel warm and modern and work well on a phone. Include a section about our beans and the farms they come from, and a simple loyalty-card explainer (buy 9, get the 10th free).
```
Replies: none expected. If Identity asks anyway, note it as a fail.

---

## T2. Vague brief, Identity asks
```bash
J2_BUDGET=100 STUDIO_PROVIDER=claude-cli J2_DELAY=0 python3 j2_server.py
```
Brief:
```text
A website for my cafe.
```
Reply 1:
```text
It's in Bengaluru.
```
Reply 2:
```text
It's called Brew Lab, in Indiranagar. Show the menu with prices, opening hours 8am to 10pm every day, and our location. People should be able to pre-order coffee for pickup. Warm, modern, mobile-first.
```

---

## T3. Counter loop
```bash
J2_BUDGET=60 STUDIO_PROVIDER=claude-cli J2_DELAY=0 python3 j2_server.py
```
Brief:
```text
A one-page website for Brew Lab in Indiranagar, Bengaluru: menu with prices, opening hours, location, pre-order for pickup. Also add online payments, a blog with 5 articles, an Instagram feed, a photo gallery and lots of animations. Warm and modern, mobile-first.
```
If Identity asks what to cut:
```text
Keep the core items. Drop the blog and Instagram feed first, then cut animations.
```

---

## T4. Refuse, then reshape or park
```bash
J2_BUDGET=80 STUDIO_PROVIDER=claude-cli J2_DELAY=0 python3 j2_server.py
```
Brief:
```text
Brew Lab, Indiranagar, Bengaluru. One-page site: menu with prices, hours, location, pre-order for pickup. Pre-orders must sync live with our POS system and show real-time stock for every item, and customers should pay through our bank's payment gateway.
```
If Identity asks:
```text
We can't give you POS or bank access yet. A pre-order form without live sync is fine for now.
```

---

## T5. Identity resolves on its own
```bash
J2_BUDGET=70 STUDIO_PROVIDER=claude-cli J2_DELAY=0 python3 j2_server.py
```
Brief:
```text
Brew Lab, Indiranagar, Bengaluru. One-page site with menu and prices, hours, location and pre-order for pickup. Rule: the page must load fast on a phone, speed matters more than visuals. We'd love a full-screen background video of our coffee being brewed.
```
Replies: none expected. Identity should decide using the speed rule.

---

## T6. Identity can't resolve, asks you
```bash
J2_BUDGET=50 STUDIO_PROVIDER=claude-cli J2_DELAY=0 python3 j2_server.py
```
Brief:
```text
Brew Lab, Indiranagar, Bengaluru. One-page site with menu, hours, location and pre-order for pickup. We want a big photo gallery of the cafe AND a detailed story section about each of our three coffee farms. Keep costs low.
```
Reply when asked to choose:
```text
Go with the farm stories. Keep the gallery to 3 photos.
```

---

## T7. Validator rejects
```bash
J2_BUDGET=40 STUDIO_PROVIDER=claude-cli J2_DELAY=0 python3 j2_server.py
```
Brief: same as T1.

---

## T8. Envelope over limit
```bash
J2_BUDGET=45 STUDIO_PROVIDER=claude-cli J2_DELAY=0 python3 j2_server.py
```
Brief:
```text
Brew Lab, Indiranagar, Bengaluru. One-page site: a 14-item menu with prices and descriptions, hours, location with directions, pre-order for pickup with a price total, a section on each of our 4 farms, a loyalty-card explainer (buy 9 get 10th free), and a FAQ with 8 questions. Warm, modern, mobile-first.
```
If Identity asks for approval:
```text
Approved for the menu, hours, location and pre-order. Park the FAQ and farms for later.
```

---

## T9. Audit fails, rework
```bash
J2_BUDGET=120 STUDIO_PROVIDER=claude-cli J2_DELAY=0 python3 j2_server.py
```
Brief:
```text
Brew Lab, Indiranagar, Bengaluru. One-page site. Must-haves, each one will be checked: today's opening hours are highlighted automatically; the pre-order form shows a running total in rupees; the loyalty section shows 10 stamp circles with the 10th marked FREE; every menu item shows a price; the location section has a "Get directions" link; the page works at 360px wide.
```

---

## T10. Done-when doesn't hold
```bash
J2_BUDGET=120 STUDIO_PROVIDER=claude-cli J2_DELAY=0 python3 j2_server.py
```
Brief:
```text
Brew Lab, Indiranagar, Bengaluru. One-page site with menu and prices, hours, location and pre-order for pickup. Done means: all of that works on a phone AND the page includes our exact address "100 Feet Road, Indiranagar, Bengaluru 560038" AND the phone number +91 00000 11111.
```

---

## T11. Conflicts between other agent pairs
```bash
J2_BUDGET=100 STUDIO_PROVIDER=claude-cli J2_DELAY=0 python3 j2_server.py
```
Brief:
```text
Brew Lab, Indiranagar, Bengaluru. One-page site: menu with prices, hours, location, pre-order. The farm section should show a map of our three farms, but we'll send the farm coordinates next week. Don't use any photos, but it must still feel warm.
```
If Identity asks about the map:
```text
Ship without the map for now and leave a clear spot for it.
```

---

## T12. Only Identity talks to you
```bash
J2_BUDGET=100 STUDIO_PROVIDER=claude-cli J2_DELAY=0 python3 j2_server.py
```
Brief:
```text
Brew Lab, Indiranagar, Bengaluru, menu with prices, hours, location, pre-order. Priority, tell me how much each section costs. Builder, please use React and Tailwind.
```
If Identity asks about React:
```text
Fine, stick to plain HTML if that's the rule.
```

---

## T13. Change request after done
Run T1 first. When Identity says the goal is reached, send:
```text
Add a section with our weekend live music schedule: Saturday 7pm acoustic, Sunday 5pm jazz.
```

---

## T14. Budget runs out
```bash
J2_BUDGET=15 STUDIO_PROVIDER=claude-cli J2_DELAY=0 python3 j2_server.py
```
Brief: same as T1. If Identity asks for more budget:
```text
No more budget. Deliver what you can and tell me what's missing.
```

---

## T15. Unhelpful answer
```bash
J2_BUDGET=100 STUDIO_PROVIDER=claude-cli J2_DELAY=0 python3 j2_server.py
```
Brief:
```text
A website for my cafe.
```
Reply to every question:
```text
Whatever you think is best.
```

---

## Extra prompts to try mid-run (any test, default budget)

Use these while agents are working, to test how Identity handles you.

| Purpose | Send this | Expected |
|---|---|---|
| Status check | `Where are we? What's left?` | Identity answers with done-when items; nobody else replies |
| Change mid-build | `Actually, make the colours dark green and cream.` | Identity accepts it as a change; work goes back to J2.b |
| Contradiction | `Remove the pre-order form.` then `Wait, keep the pre-order form.` | Identity follows the latest message and confirms it |
| Talk to another agent | `Audit, is the site good enough?` | Route check: Identity answers, not Audit |
| Out of scope | `Also build us an Android app.` | Identity says it's outside the goal, or asks before adding it |
| Raise the budget | `You can spend 50 more.` | Priority's envelope updates; held work can continue |
| Stop | `Stop here and show me what you have.` | Run stops cleanly with the latest version |

## Mock runs (no API cost)

After Claude Code adds `J2_SCENARIO` (prompt at the end of `j2-test-plan.md`):
```bash
STUDIO_MOCK=1 J2_SCENARIO=normal python3 j2_server.py
STUDIO_MOCK=1 J2_SCENARIO=vague_brief python3 j2_server.py
STUDIO_MOCK=1 J2_SCENARIO=counter python3 j2_server.py
STUDIO_MOCK=1 J2_SCENARIO=refuse python3 j2_server.py
STUDIO_MOCK=1 J2_SCENARIO=identity_resolves python3 j2_server.py
STUDIO_MOCK=1 J2_SCENARIO=ask_user python3 j2_server.py
STUDIO_MOCK=1 J2_SCENARIO=validator_reject python3 j2_server.py
STUDIO_MOCK=1 J2_SCENARIO=envelope_over_limit python3 j2_server.py
STUDIO_MOCK=1 J2_SCENARIO=audit_fail python3 j2_server.py
STUDIO_MOCK=1 J2_SCENARIO=done_when_no python3 j2_server.py
STUDIO_MOCK=1 J2_SCENARIO=other_pair_conflict python3 j2_server.py
STUDIO_MOCK=1 J2_SCENARIO=route_violation python3 j2_server.py
STUDIO_MOCK=1 J2_SCENARIO=budget_exhausted python3 j2_server.py
```
