# Vercel deploy surface — retired 2026-09-02

- **status**: archived
- **owner**: Asawa CEO (Website dept)
- **updated**: 2026-09-02
- **direction**: D65, 2026-08-08 — "Decommission everything from Vercel. Publish to GitHub." (Founder direction recorded in the private parent repo `asawa-holding` at `holding/FOUNDER-DIRECTIONS.md` §D65; not part of this repo.)
- **replaced-by**: `.github/workflows/deploy-website.yml` (GitHub Pages) → https://sankalpasawa.github.io/sutra/

## Files here {#files}

| Archived file | Original path | Role |
|---|---|---|
| `deploy-vercel.yml` | `.github/workflows/deploy-vercel.yml` | push→`website/**` deploy + alias `sutra-os.vercel.app` |
| `vercel.json` | `website/vercel.json` | rewrite `/native/install` → `install.sh` + `text/plain` headers |
| `vercel-project.json` | `website/.vercel/project.json` | Vercel org + project ids |

## Why retired {#why}

| Fact | Evidence |
|---|---|
| Workflow failed 98/98 runs 2026-04-30 → 2026-08-26 | `gh run list --workflow deploy-vercel.yml`; error `token provided via --token is not valid` |
| 1 successful run ever | 2026-04-29 |
| Pages lane deploys the same `website/` and passes | `deploy-website.yml`, 4/4 green through 2026-08-26 |
| Clean `/native/install` URL had no live consumer | 404 on every host at retirement; `install.sh:5` documents the `.sh` URL |
| Stale site source is in git history | `website/index.html` @ `79dfc88` ("agentic Chief of Staff framing", v2.37.1) |

## Do not revive {#do-not-revive}

Vercel is not a publish target for any Asawa/Sutra site (D65). Restoring these files re-creates the failing workflow. Pages is the only lane.

---
provenance: written 2026-09-02 by Claude (session f9a64264) during the D65 decommission; facts verified live via `gh` + `curl` that day.
