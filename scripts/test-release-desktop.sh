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

# ---- 9. what a desktop release may and may not carry ----------------------
# `release` starts from the dirty release-prep state, so the protection moved
# from "the tree must be clean" to "everything in it must be something a
# desktop release carries". These pin both halves.
yes_ in_release_scope "marketplace/plugin/sutra-ui/app.py"
yes_ in_release_scope "marketplace/plugin/.claude-plugin/plugin.json"
yes_ in_release_scope ".github/workflows/release-dmg.yml"
yes_ in_release_scope "CURRENT-VERSION.md"
yes_ in_release_scope ".claude-plugin/marketplace.json"
yes_ in_release_scope "scripts/release-desktop.sh"
no_  in_release_scope "holding/FOUNDER-DIRECTIONS.md"
no_  in_release_scope ".github/workflows/plugin-release-gate.yml"   # a different contract
no_  in_release_scope "README.md"
no_  in_release_scope ""

# Machine state and signing material, whatever the scope says.
yes_ is_never_commit ".enforcement/md-standard.jsonl"
yes_ is_never_commit "marketplace/plugin/sutra-ui/.enforcement/completion-protocol.jsonl"
yes_ is_never_commit ".claude/sessions/abc/placement-registered"
yes_ is_never_commit "certs/developer-id.p12"
yes_ is_never_commit "notary.p8"
no_  is_never_commit "marketplace/plugin/sutra-ui/app.py"
no_  is_never_commit ""

# ---- 10. the dirty tree, classified ---------------------------------------
PORC="$(printf ' M marketplace/plugin/sutra-ui/app.py\n?? scripts/x.sh\n M holding/notes.md\n M .enforcement/a.jsonl')"
CLS="$(classify_dirty "$PORC")"
is "in-scope modification included" "$(printf '%s\n' "$CLS" | grep -c '^include marketplace/plugin/sutra-ui/app.py$')" "1"
is "in-scope untracked included"    "$(printf '%s\n' "$CLS" | grep -c '^include scripts/x.sh$')" "1"
is "out-of-scope path blocked"      "$(printf '%s\n' "$CLS" | grep -c '^block holding/notes.md$')" "1"
is "machine state blocked"          "$(printf '%s\n' "$CLS" | grep -c '^block .enforcement/a.jsonl$')" "1"
is "every line classified"          "$(printf '%s\n' "$CLS" | grep -c .)" "4"
is "empty tree classifies to nothing" "$(classify_dirty "" | grep -c . || true)" "0"
# a rename reports "old -> new"; the NEW path is what gets committed
is "rename judged on its new path" \
   "$(classify_dirty "$(printf 'R  holding/old.md -> marketplace/plugin/new.md')")" \
   "include marketplace/plugin/new.md"
# scope does not rescue a denied path that sits inside it
is "denylist beats scope" \
   "$(classify_dirty "$(printf ' M marketplace/plugin/sutra-ui/.enforcement/x.jsonl')")" \
   "block marketplace/plugin/sutra-ui/.enforcement/x.jsonl"

# ---- 11. the generated entry ----------------------------------------------
# The contract: every bullet is a commit subject, verbatim. Nothing here reads
# a diff and decides what it MEANS -- that is how a changelog starts claiming
# features nobody built.
SUBJ="$(printf 'Shadow: talk to a task\nrelease prep: wire the suites')"
BODY="$(notes_body "v1.2.3-desktop..HEAD" "$SUBJ" "18 file(s), +1874/-27" "test_a.js test_b.py")"
is "entry names the range"        "$(printf '%s\n' "$BODY" | grep -c 'v1.2.3-desktop..HEAD')" "1"
is "entry counts the commits"     "$(printf '%s\n' "$BODY" | grep -c '2 commit(s)')" "1"
is "entry says the lines are quoted, not summarised" \
   "$(printf '%s\n' "$BODY" | grep -c 'quoted, not a summary')" "1"
is "subject 1 verbatim"           "$(printf '%s\n' "$BODY" | grep -c '^  - Shadow: talk to a task$')" "1"
is "subject 2 verbatim"           "$(printf '%s\n' "$BODY" | grep -c '^  - release prep: wire the suites$')" "1"
is "diffstat is arithmetic"       "$(printf '%s\n' "$BODY" | grep -c '18 file(s), +1874/-27')" "1"
is "new suites listed"            "$(printf '%s\n' "$BODY" | grep -c 'test_a.js test_b.py')" "1"
# one bullet per subject, plus the header, the stat and the tests line
is "no bullet beyond what it was given" "$(printf '%s\n' "$BODY" | grep -c '^  - ')" "2"
# optional fields stay absent rather than being filled with a guess
B2="$(notes_body "r" "$(printf 'only one')" "" "")"
is "no diffstat line when unknown"  "$(printf '%s\n' "$B2" | grep -c '^- Changed:')" "0"
is "no test line when none added"   "$(printf '%s\n' "$B2" | grep -c '^- New test suites:')" "0"
is "single subject still quoted"    "$(printf '%s\n' "$B2" | grep -c '^  - only one$')" "1"

# ---- 12. the entry is markdown the CHANGELOG accepts ----------------------
printf '# Changelog\n\n**status**: active\n## 9.9.9 (2026-01-01)\n\n- old\n' > "$TMP/CH2.md"
printf '%s\n' "$BODY" > "$TMP/gen.txt"
python3 "$HERE/_release_edit.py" changelog "$TMP/CH2.md" 9.9.10 2026-09-17 "$TMP/gen.txt"
is "generated entry lands first"   "$(grep -m1 -oE '^## [0-9.]+' "$TMP/CH2.md")" "## 9.9.10"
is "generated entry keeps bullets" "$(grep -c '^  - Shadow: talk to a task$' "$TMP/CH2.md")" "1"
is "older entry survives"          "$(grep -c '^## 9.9.9' "$TMP/CH2.md")" "1"
# The edit is NARROW: it moves the marker off the version it was told about
# and touches nothing else. CURRENT-VERSION.md in this repo already carries a
# second, stale HEAD marker on v2.257.0 from some earlier release; going
# hunting for it would mean rewriting history this release was not asked
# about, so the function leaves it exactly where it is.
printf '# C\n\n## v1.0.2 (2026-01-02, HEAD)\n\nbody\n\n## v0.9.0 (2025-01-01, HEAD)\n' > "$TMP/CV2.md"
python3 "$HERE/_release_edit.py" current "$TMP/CV2.md" 1.0.2 1.0.3 2026-09-17
is "stale marker elsewhere is left alone" "$(grep -c '^## v0.9.0 (2025-01-01, HEAD)$' "$TMP/CV2.md")" "1"
is "the named version loses its marker"   "$(grep -c '^## v1.0.2 (2026-01-02)$' "$TMP/CV2.md")" "1"
is "the new version gains one"            "$(grep -c '^## v1.0.3 (2026-09-17, HEAD)$' "$TMP/CV2.md")" "1"
# ---- 8. the constants the release contract depends on ---------------------
is "five panel runs (check 6)" "$PANEL_RUNS" "5"
is "four required assets"      "$(printf '%s' "$REQUIRED_ASSETS" | wc -w | tr -d ' ')" "4"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" = 0 ]
