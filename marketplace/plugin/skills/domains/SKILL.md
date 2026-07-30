---
name: domains
description: >
  The Domains module (ADR-028): on-demand MECE view of a company's domain tree
  ("departments" is the user-facing synonym — internally the word is DOMAINS,
  always). Fires on "show/give me the (various|relevant) departments|domains",
  "departments around <thing>", "publish the departments/domains page", or
  /domains. Three surfaces: in-chat view, neighborhood view, and the company's
  own published GitHub Pages page in ITS design system.
---

# domains — the company's org tree, everywhere it's asked for

## Terminology (locked, founder 2026-07-30)

Internally: **domains**, always — files, code, registry, skill names. Users may
say "departments"; treat it as a synonym on input, and pages may display
"Departments" as a label. Never introduce a third term.

## Data source (never invent)

Everything renders from the placement engine's registry ($SUTRA_NATIVE_HOME,
default `~/.sutra-native/user-kit`): domains (`tree`), `description` fields,
charters (title + purpose), counts from CURRENT.jsonl. If the registry is
empty: offer to seed (org form, operator-authored) or scan (technical form) —
and say which form the render came from. Never fabricate a domain, count,
description, or charter.

## Surface 1 — in-chat view (CLI)

STANDARD LAYOUT: two levels of depth, index on the left (D1, D1.1 ...), each
domain's one-line `description` under its name, charter title when present.
ASCII only, one screen, big groups collapsed to top-3 + count. Anchored ask
("around X") -> ancestor chain with `<== YOU ARE HERE` + siblings + children.

## Surface 2 — the published page (per company, THEIR GitHub Pages)

On "publish the domains/departments page" (or first ask about departments in a
repo with Pages):

1. Generate with the fleet generator — `<plugin>/lib/domains_page.py OUT.html
   --label Departments`. It renders: left index rail, clickable anchored
   sections, one-line description AND charter line per domain, dotted child
   blocks, two levels of depth.
2. **Design system comes from D0** (the root domain's `design` field:
   bg/card/ink/muted/line/accent/accent_bg/font + `source`). Detection order
   when D0.design is absent: detect tokens from the company's own site CSS
   (record `source`), else neutral fallback — and SAY it's the fallback.
   Write detected tokens back to D0 so the design is data.
3. Publish into THE CLIENT'S OWN repo, from inside their session (D33: the
   plugin is the only channel — never push cross-repo). Detect their Pages
   setup first: workflow-deployed (find the upload-pages-artifact path) vs
   branch-deployed (docs/ or root). Commit + push only on their explicit ask.
4. Remember the URL: write it to the D0 domain (`page_url`). Every subsequent
   "show me the departments/domains" answers with THAT URL first, then offers
   the in-chat view. Edits: change the registry (descriptions, structure via
   restructure, charters), regenerate, push — the page is never hand-edited.
5. Public-page privacy: any domain with `public_names_withheld: true` hides
   its children's names ("N entries — names withheld"). Client/third-party
   names default to withheld unless the operator says otherwise.

## Grounding (ADR-028 — the mandate)

Every unit of plugin work must ground in this registry: the per-turn PLACEMENT
resolves against it, and `placement-resolve.sh` injects the resolved domain's
CHARTER (title + purpose) into each turn's context — treat that charter text
as the frame for the turn's work and cite the domain when making
recommendations. If a turn's work contradicts its charter's purpose, say so
out loud rather than proceeding silently.

## v2 hardening (recorded, deferred by founder)

Deterministic renderer in the engine (`orgchart`) + golden tests; B4
context_scope enforcement (retrieval filtered by the charter's artifact
boundary); groundedness lint pass.

## Mode C — search ("search the domains for <terms>")

Run `python3 <plugin>/lib/placement_engine.py search <terms>` — matches domain
names, descriptions, and charter titles/purposes; present ranked hits with
their D-paths. The published page has the same feature client-side (the search
box above the index filters sections, blocks, and the nav live).
