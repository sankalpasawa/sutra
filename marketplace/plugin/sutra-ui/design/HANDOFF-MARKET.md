# HANDOFF-MARKET — the Agents marketplace, the first-run open, and two chat-view fixes

**written**: 2026-09-10 · **covers**: `static/js/17-agents.js`, `static/agents.css`,
`agents_api.py` (tests only), `test_agents.js`, `test_agents_api.py`

Built to the owner's own words: the Agents tab becomes a marketplace, the SEO Writer stops
opening by itself, and opening an agent for the first time is an introduction rather than a form.
Two later notes on the chat view — the wasted left gutter, and the composer not reading as a
field — were done in the same pass. This file is what the work needed from files it does not
own, and the faults it found and left alone.

---

## 1. What the marketplace reads, and what it deliberately does not

No new route was added. The shelf is drawn from three routes the agent screen already used:

| Route | What the shelf takes from it |
|---|---|
| `GET /health` | model present, `site_indexed`, `page_index.built`, `brand_ready`, `chats` |
| `GET /library` | the article count (its length) |
| `GET /knowledge` | `company.brand` (the company name) and `site_index.page_count` |

**The company name is decided in exactly one place**, `agBrandName(a)` in `17-agents.js`, and both
the shelf and the agent's own sidebar now call it. It reads `knowledge.company.brand`, which is
`knowledge/brand/company.json` exactly as it was written — so a fresh install has nothing there
and the answer is `""`, which every caller draws correctly.

## 2. The one thing this needs from `seo_agent/` — NOT changed here

`seo_agent/tools/_shared.py :: company()` ends with

```python
brand = rec.get("brand") or (brand_voice().get("company") if brand_voice() else "") or dom or "this company"
```

so on an install with no company record and no site index it answers the **literal string
`"this company"`**. That value is carried into `agents_api._brand_knowledge()` as `brand`, and
from there onto `GET /knowledge → brand.brand`. Any screen that prints that field prints a
placeholder as if it were a company name.

This screen does not print it — it reads the raw record instead, and `agBrandName` additionally
drops anything that comes back reading like that fallback — so nothing is broken today. But the
fallback is still a placeholder living in a field named `brand`, and the next person to reach for
`brand.brand` will not know that. **Suggested (owner's call, engine side): have `company()` return
`""` for an unknown brand and let each caller choose its own wording**, since a prompt wanting
"this company" as filler and a UI wanting the real name are different needs currently served by
one string. `test_agents_api.py::test_29b` pins the current behaviour either way, so a change
there will show up as a failing test rather than as a silently different screen.

## 3. Done outside the lane, and why

- **`agWsCreateFormHtml`'s workspace-name placeholder was `placeholder="Testlify"`.** That is a
  real company's name shipped to every install, which is the thing the owner explicitly did not
  want ("I hope it's not there for everybody"). Changed to `Our team`. No test pinned it.
  `test_agents.js` now asserts no company name is hardcoded anywhere in `17-agents.js` or
  `agents.css`, so this cannot come back.
- **`.ag-stagebody` had `padding-left:2px`**, which put a grouped step two pixels to the right of
  a loose one on the same rail. Set to `0` while fixing the left edge.

## 4. Faults found and left alone

- **`agArtcard` runs its title into its status**: the review card renders `Topic ideasanswered`
  with no separator. Visible in every transcript screenshot. Not touched — it is outside both the
  marketplace and the two fixes, and it is one space in a renderer somebody else may be editing.
- **Returning to the Agents tab mid-session resumes the agent, it does not go back to the shelf.**
  `S.ag.screen` survives a remount on purpose: losing your place — and your view of a run in
  progress — because you looked at another tab would be worse than the shelf being one click
  away. A fresh app launch always starts on the shelf, because `S` is in memory only. Flagged
  because it is a judgement call, not an accident.
- **The shelf does not poll.** Nothing on it moves on its own, so entering the marketplace stops
  the agent's clock entirely and the three routes are read once on entry. A run finishing while
  the shelf is open will not update the article count until the shelf is re-entered.

## 5. Themes

Everything added uses only existing tokens — `--acc`, `--acc-bg`, `--line`, `--line-soft`,
`--ink`, `--muted`, `--faint`, `--inset`, `--card`, `--sepia`, `--ok`, `--warn`, `--block`, and
the three font stacks. There is not a literal colour in either new block, and `test_agents.js`
asserts it for the marketplace CSS. The accent picker at the bottom left sets `--acc` inline on
`:root` and `--acc-bg` is mixed from it per theme in `panel.css`, so the composer's focus ring
follows both the theme and the chosen accent with no second palette. Checked by rendering in
dark, light, and light with a custom accent.
