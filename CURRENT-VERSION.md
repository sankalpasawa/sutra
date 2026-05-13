# Sutra — Current Version

## v2.39.1 (2026-05-13, HEAD)

**Patch over v2.39.0** — cache-invalidating bump so /core:update propagates the housekeeping fixes.

Ships from v2.39.0 (same content; version field was the only thing missing):
- Anti-glaze-tone skill at `marketplace/plugin/skills/anti-glaze-tone/SKILL.md`.
- Plugin description compressed from ~14KB → ~200 chars.
- CURRENT-VERSION.md trimmed from 797 → 12 lines.
- `/core:update` prints `/reload-plugins` reminder.

Lesson: any content change in a release artifact (description, CHANGELOG, skill) requires a patch-bump even without a feature change — otherwise marketplace cache won't invalidate.

For prior release history, see `marketplace/plugin/CHANGELOG.md`.
