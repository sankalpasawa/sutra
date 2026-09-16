#!/usr/bin/env bash
# =============================================================================
# test-release-desktop.sh -- the parsing and guard logic of release-desktop.sh
# =============================================================================
# WHAT IS TESTED HERE and what deliberately is not. The pure functions are:
# version parsing, the bump, the tag form, the target derivation, the count
# comparison and the asset check. Those are where a release goes wrong quietly
# -- a version inferred by adding 0.0.1 without asking, a tag that guard will
# reject, a count that agrees with itself. They run with no git, no network and
# no writes, by sourcing the script with RELEASE_DESKTOP_LIB=1 so main() never
# fires.
#
# The gates are NOT unit-tested: each one is three lines wrapping a real
# command, and a fake `git`/`node` on PATH would test the fake. They are
# exercised for real every time `check` runs.
#
# The two markdown edits ARE tested, against copies in a temp dir, because they
# splice into a document by position and that is worth pinning.
#
# Run: scripts/test-release-desktop.sh
# =============================================================================
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RELEASE_DESKTOP_LIB=1 . "$HERE/release-desktop.sh"

pass=0; fail=0
is()   { if [ "$2" = "$3" ]; then pass=$((pass+1)); else fail=$((fail+1)); printf 'FAIL %s\n  want: %s\n  got : %s\n' "$1" "$3" "$2"; fi; }
yes_() { if "$@" >/dev/null 2>&1; then pass=$((pass+1)); else fail=$((fail+1)); printf 'FAIL (expected true): %s\n' "$*"; fi; }
no_()  { if "$@" >/dev/null 2>&1; then fail=$((fail+1)); printf 'FAIL (expected false): %s\n' "$*"; else pass=$((pass+1)); fi; }

# ---- 1. a version is three integers, and nothing else ----------------------
yes_ is_semver 2.282.3
yes_ is_semver 0.0.0
yes_ is_semver 10.200.3000
no_  is_semver v2.282.3
no_  is_semver 2.282
no_  is_semver 2.282.3-beta.1
no_  is_semver ""
no_  is_semver "2.282.3 "

# ---- 2. the tag form the guard job accepts ---------------------------------
is "tag_for"        "$(tag_for 2.282.3)" "v2.282.3-desktop"
yes_ is_desktop_tag v2.282.3-desktop
no_  is_desktop_tag v2.282.3                 # no suffix: guard refuses
no_  is_desktop_tag 2.282.3-desktop          # no v
no_  is_desktop_tag v2.282.3-beta.1-desktop  # valid for CI, but not cut here
is "version_from_tag stable" "$(version_from_tag v2.282.3-desktop)" "2.282.3"
is "version_from_tag beta"   "$(version_from_tag v2.282.3-beta.2-desktop)" "2.282.3"

# ---- 3. the bump, which is asked for and never assumed ---------------------
is "patch"          "$(bump_version 2.282.3 patch)" "2.282.4"
is "patch rollover" "$(bump_version 2.282.9 patch)" "2.282.10"
is "minor"          "$(bump_version 2.282.3 minor)" "2.283.0"
is "minor zeroes patch" "$(bump_version 2.281.7 minor)" "2.282.0"
no_ bump_version 2.282.3 major               # not a kind this script offers
no_ bump_version not-a-version patch

# ---- 4. the derivation, including the case a naive script gets wrong -------
# The manifests can already be AHEAD of the last tag: 2.282.0 and 2.282.1 were
# real plugin versions that never carried a desktop tag. Releasing then means
# tagging what is already there, with nothing to commit.
is "untagged current releases as-is" "$(derive_target 2.282.3 patch no)"  "2.282.3 no"
is "tagged current needs a bump"     "$(derive_target 2.282.3 patch yes)" "2.282.4 yes"
is "tagged current, minor"           "$(derive_target 2.282.3 minor yes)" "2.283.0 yes"
is "explicit version wins"           "$(derive_target 2.282.3 patch yes 2.290.0)" "2.290.0 yes"
is "explicit == current needs no commit" "$(derive_target 2.282.3 patch no 2.282.3)" "2.282.3 no"
no_ derive_target 2.282.3 patch yes not-a-version

# ---- 5. check 2's comparison -----------------------------------------------
yes_ counts_agree 19 19
no_  counts_agree 11 19
no_  counts_agree "" 19

# ---- 6. the four assets a shippable release carries ------------------------
ALL="$(printf 'Sutra-arm64.dmg\nSutra-arm64.dmg.sha256\nSutra-x86_64.dmg\nSutra-x86_64.dmg.sha256')"
is "complete release"    "$(missing_assets "$ALL")" ""
is "arm64 only"          "$(missing_assets "$(printf 'Sutra-arm64.dmg\nSutra-arm64.dmg.sha256')")" \
   "Sutra-x86_64.dmg Sutra-x86_64.dmg.sha256"
is "dmg without checksum" "$(missing_assets "$(printf 'Sutra-arm64.dmg\nSutra-x86_64.dmg')")" \
   "Sutra-arm64.dmg.sha256 Sutra-x86_64.dmg.sha256"
is "empty release"       "$(missing_assets "")" \
   "Sutra-arm64.dmg Sutra-arm64.dmg.sha256 Sutra-x86_64.dmg Sutra-x86_64.dmg.sha256"
# a near-miss name must not satisfy a requirement
is "prefix is not a match" "$(missing_assets "$(printf 'Sutra-arm64.dmg.sha256sum')")" \
   "Sutra-arm64.dmg Sutra-arm64.dmg.sha256 Sutra-x86_64.dmg Sutra-x86_64.dmg.sha256"

# ---- 7. the two markdown edits, on copies ---------------------------------
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
printf '# Changelog\n\n**status**: active\n## 2.282.3 (2026-09-16)\n\n- old\n' > "$TMP/CH.md"
printf 'notes body line\n' > "$TMP/notes.txt"
python3 "$HERE/_release_edit.py" changelog "$TMP/CH.md" 2.282.4 2026-09-17 "$TMP/notes.txt"
is "changelog: new entry is first"  "$(grep -m1 -oE '^## [0-9.]+' "$TMP/CH.md")" "## 2.282.4"
is "changelog: body is verbatim"    "$(grep -c 'notes body line' "$TMP/CH.md")" "1"
is "changelog: old entry survives"  "$(grep -c '^## 2.282.3' "$TMP/CH.md")" "1"
python3 "$HERE/_release_edit.py" changelog "$TMP/CH.md" 2.282.4 2026-09-17 "$TMP/notes.txt"
is "changelog: idempotent"          "$(grep -c '^## 2.282.4' "$TMP/CH.md")" "1"
printf 'empty\n' > "$TMP/blank.txt"; : > "$TMP/blank.txt"
python3 "$HERE/_release_edit.py" changelog "$TMP/CH.md" 2.282.5 2026-09-17 "$TMP/blank.txt" 2>/dev/null
is "changelog: refuses a blank entry" "$(grep -c '^## 2.282.5' "$TMP/CH.md")" "0"

printf '# Current\n\n## v2.282.3 (2026-09-16, HEAD)\n\nbody\n\n## v2.282.2 (2026-09-16)\n' > "$TMP/CV.md"
python3 "$HERE/_release_edit.py" current "$TMP/CV.md" 2.282.3 2.282.4 2026-09-17
is "current: HEAD moved to the new version" "$(grep -c '^## v2.282.4 (2026-09-17, HEAD)' "$TMP/CV.md")" "1"
is "current: old heading kept, HEAD dropped" "$(grep -c '^## v2.282.3 (2026-09-16)$' "$TMP/CV.md")" "1"
is "current: exactly one HEAD marker"        "$(grep -c 'HEAD)' "$TMP/CV.md")" "1"
python3 "$HERE/_release_edit.py" current "$TMP/CV.md" 2.282.3 2.282.4 2026-09-17
is "current: idempotent"                     "$(grep -c '^## v2.282.4' "$TMP/CV.md")" "1"

# ---- 8. the constants the release contract depends on ---------------------
is "five panel runs (check 6)" "$PANEL_RUNS" "5"
is "four required assets"      "$(printf '%s' "$REQUIRED_ASSETS" | wc -w | tr -d ' ')" "4"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" = 0 ]
