# Pre-Ship Checklist — Plugin Releases

*Run every item before pushing a new plugin version to `sankalpasawa/sutra` main.*

## 1. Version + metadata

- [ ] `plugin.json` version bumped per SemVer (see `VERSIONING.md`)
- [ ] `CHANGELOG.md` entry added with Added / Changed / Removed / Migration / Rationale
- [ ] `ARCHITECTURE.yaml` updated if components/flows changed

## 2. Validation

- [ ] `jq empty plugin.json` passes
- [ ] `jq empty .claude-plugin/marketplace.json` passes (in repo root)
- [ ] `claude plugin validate .` passes (validates marketplace + plugin manifests)
- [ ] `bash scripts/leak-audit.sh` PASSES (no `asawa`/`holding/` brand strings)

## 3. Smoke test (the step that caught v1.6.0's broken userConfig)

- [ ] **`claude plugin install core@sutra` actually succeeds** on this machine
- [ ] `claude plugin list` shows the new version installed
- [ ] `/core:start` runs end-to-end + emits the activation banner
- [ ] If the release touches a hook: run the hook in a scratch dir — `CLAUDE_PROJECT_DIR=/tmp/test bash hooks/<changed>.sh`

## 4. Stable channel promotion (optional)

If the release is stable-quality (portfolio-validated, no known blockers):

- [ ] `git push origin main:stable` — fast-forward stable branch
- [ ] `git tag -a vX.Y.Z -m "..."` + `git push origin vX.Y.Z`
- [ ] Announce in FEEDBACK-LOG.md

## 5. Post-push verification

- [ ] `claude plugin marketplace update sutra` on a clean machine (or after removing the local marketplace cache) → install pulls the new version
- [ ] Live users' Claude Code auto-updates on next session (silent; update-banner hook announces version change)

## Why this list exists

v1.6.0 shipped with an invalid `userConfig` schema (missing required `type` + `title` fields). `claude plugin validate` did NOT catch it because that command only validates the marketplace manifest — not the plugin's own userConfig. The bug only surfaced when running `claude plugin install` for real.

Item **#3 smoke test** is the specific guard added after that miss. 30 seconds of real install catches whole classes of schema bugs that validators miss.
