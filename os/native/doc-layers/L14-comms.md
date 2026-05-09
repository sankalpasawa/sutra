---
part-id: L14
bucket: doc-layers
template: L13-release-note-style
parity-source: STUB
parity-source-sha256: STUB-PENDING-PHASE-A-REMAINDER
status: DRAFT v1
authored: 2026-05-09
---

# L14: Comms / Site / One-pager (external-facing artifacts)

> **DOC LAYER STUBBED IN v1** — Native instance NOT YET AUTHORED in canon; pending Phase A remainder per `sutra/os/native/MIGRATION-PLAN.md` context. This part-file defines the layer contract (producer/consumer/cadence/ratification/Native target location); the Native realization at `holding/website/native/` will be authored in Phase A continuation per holding/PRODUCT-DOC-STANDARD.md §5 mapping (L14 → `holding/website/native/`). Per D54 fold: `holding/website/native/` is OUTSIDE D54 forbidden paths (not `holding/research/*native*` or `holding/plans/native-*`), so this layer's home stays under `holding/` not under `sutra/os/engines/NATIVE-ENGINE.md`. Auto-publish to GitHub on edit per memory `feedback_native_html_auto_publish`.

## Purpose (what this layer answers)

External-facing artifacts: public website, investor brief, press one-pager, landing page. Per holding/PRODUCT-DOC-STANDARD.md §3 / L14: "external-facing artifacts. Public website, investor brief, press one-pager. Common spine: hero · problem · solution · proof · CTA."

Native's comms target audience: prospective T4 fleet operators (self-onboard via plugin) + T3 paying clients + investors + press.

## Producer

Founder + designer. Per holding/PRODUCT-DOC-STANDARD.md §3 / L14 (`Owner: Founder + designer`).

## Consumer

- Prospective T4 fleet operators (first-touch surface; landing decides install)
- T3 paying clients evaluating outcome-based pricing
- Investors / partners / press (per L7 PRFAQ audience cross-ref)
- Founder (positioning forcing-function — if site copy doesn't sing, positioning isn't sharp)

## Cadence

Per launch / per public communication. Per holding/PRODUCT-DOC-STANDARD.md §3 / L14 (`Cadence: per launch / per public communication`).

## Ratification rules

- DRAFT → RATIFIED requires founder direct ratification per holding/PRODUCT-DOC-STANDARD.md §7.
- Common spine required per L14 spec: hero · problem · solution · proof · CTA.
- Auto-publish on edit per memory `feedback_native_html_auto_publish`: any commit under `holding/website/native/` autonomously commits (`docs(native): ...`) + pushes to origin/main; no founder gate per D52 autonomous-push.
- IP locality per memory `feedback_ip_locality`: Native = sutra-os.vercel.app (Sutra IP venue); Asawa holding-co identity stays on asawa-inc.vercel.app — pick venue by product ownership, not by which site was edited last.
- L7 PRFAQ + L14 Comms travel together — repositioning triggers BOTH rewrite.
- Native website is OUTSIDE D54 forbidden paths (forbidden = `holding/research/*native*` + `holding/plans/native-*`); `holding/website/native/` is permitted per D54 + holding/PRODUCT-DOC-STANDARD.md §5 Native-exception table.

## Native instance (where this layer lives in canon)

PENDING — target directory: `holding/website/native/` (per holding/PRODUCT-DOC-STANDARD.md §5 Native exception mapping). When authored, structure will include: `holding/website/native/index.html` (hero · problem · solution · proof · CTA spine) · `holding/website/native/prfaq.html` (L7 surface) · `holding/website/native/one-pager.pdf` (investor brief). Auto-publish workflow: edit → commit `docs(native): ...` → push origin/main (no gate per memory `feedback_native_html_auto_publish` + D52).

## References

- holding/PRODUCT-DOC-STANDARD.md §3 (15-layer pipeline) + §3 L14 specification + §4 tier-inheritance + §5 Native exception (D54 canon discipline) + §7 status rules + §8 maintenance cadence
- `holding/website/native/` (PENDING — directory exists per memory `feedback_native_html_auto_publish`; Native landing-page content TBA in Phase A remainder)
- NATIVE-ENGINE.md §15 PRFAQ (PENDING — L7 feeds L14 hero copy)
- NATIVE-ENGINE.md §13.3 competitive positioning — feeds L14 "why us" section
- NATIVE-ENGINE.md §11.4 5-year winning picture — feeds L14 aspirational copy
- D52 autonomous push (memory `feedback_autonomous_git_push`) + D53 (n/a) + memory `feedback_native_html_auto_publish` + memory `feedback_ip_locality`
- Landing-page best practice + pitch-deck conventions per holding/PRODUCT-DOC-STANDARD.md §2 anchors
