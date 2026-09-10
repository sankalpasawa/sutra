# Handoff — the agent's opening screen (the guide)

**written**: 2026-09-10 · **built in**: `static/js/17-agents.js`, `static/agents.css`, `test_agents.js`

## Nothing is needed in `seo_agent/`

The guide's two real values both came off routes that already existed:

- the domain — `GET /knowledge` (`company.domain`, then `site_index.domain`), with `GET /knowledge/cta`'s
  bare host as the last fallback. Read in one place, `agSiteDomain`.
- the tool count — `GET /tools`, which is `registry.for_screen()`. `agents_api.py` was not touched; the
  only change was that `agBootLoad` now reads that route on boot rather than waiting for the Tools tab.

## What is still open

1. **The Sutra mark underlay on the marketplace was cut, not built.** The mark is drawn and waiting at
   `/tmp/ag-mark.svg` (six-fold rosette, 18 paths, every stroke and gradient stop `var(--acc)`, so it
   follows the theme picker with no per-theme code). It was cut because a watermark that has not been
   tuned against text in every theme is worse than the white space it replaces. Whoever picks it up:
   inline it (it needs the CSS variable, so it cannot be an `<img>`), `pointer-events:none`, behind and
   slightly right of the card, one container opacity per theme following `panel.css`'s three-block
   pattern, and no rotation.

2. **There is no way back to the guide inside a session.** The door is the marketplace: All agents →
   SEO Writer. Once you are in a chat or a tab, the guide is not reachable again without going out and
   back in. Deliberately not solved here — the fix would be a sidebar entry, and the guide's tab table
   has to match the sidebar exactly, so adding one changes the copy. Worth a decision.

3. **The introduction (`agIntroHtml`) and the hero (`agHeroHtml`) still exist** and are still what an
   EMPTY CHAT shows — reached with the New chat button, not by opening the agent. On a fresh install
   somebody can now meet both the guide and the introduction. They say different things (the guide is
   what the agent does, the introduction is what it needs — DataForSEO, Voyage), so neither was cut,
   but the owner may want them collapsed into one.

## The one place the copy could not be built as written

`design/AGENT-GUIDE-COPY.md` says, for the command to type:

    Set up <the domain, if we know it; otherwise: yourcompany.com>

and the build brief says, twice, that a value which is not known is dropped rather than given a
placeholder, and that a fresh install has no domain and the sentence must still read correctly. The
two cannot both hold. The brief won: with a domain it reads `Set up northwind.co.uk`; with none it
reads `Set up`, and no stand-in domain is ever printed. `test_agents.js` holds that in both directions
and also asserts no stand-in domain is anywhere in the JS or the CSS.
