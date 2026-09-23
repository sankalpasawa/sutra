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
no_  is_desktop_tag v2.282.3-beta.1-desktop  # a beta is its own form (is_beta_tag), never a stable
is "version_from_tag stable" "$(version_from_tag v2.282.3-desktop)" "2.282.3"
is "version_from_tag beta"   "$(version_from_tag v2.282.3-beta.2-desktop)" "2.282.3"

# ---- 13. BETA FIRST (D80): the beta tag form, and the gate ----------------
# A stable tag needs a beta of the same version before it. The tag list is
# injected (all_desktop_tags is overridden below), so no git runs here.
is "beta_tag_for default N" "$(beta_tag_for 2.290.0)" "v2.290.0-beta.1-desktop"
is "beta_tag_for N"         "$(beta_tag_for 2.290.0 3)" "v2.290.0-beta.3-desktop"
yes_ is_beta_tag v2.290.0-beta.1-desktop
no_  is_beta_tag v2.290.0-desktop
no_  is_beta_tag v2.290.0-beta.1
no_  is_beta_tag v2.290.0-beta.x-desktop
TAGS="$(printf 'v2.289.9-desktop\nv2.290.0-beta.1-desktop\nv2.290.0-beta.3-desktop\nv2.290.10-beta.1-desktop\nv2.291.0-desktop')"
yes_ has_beta 2.290.0 "$TAGS"
no_  has_beta 2.289.9 "$TAGS"                  # a stable with no beta
no_  has_beta 2.290.1 "$TAGS"
no_  has_beta 2.290.0 ""
is "latest beta is the highest N, not the last line" "$(latest_beta_tag 2.290.0 "$TAGS")" "v2.290.0-beta.3-desktop"
is "next N after betas"      "$(next_beta_n 2.290.0 "$TAGS")" "4"
is "next N when none"        "$(next_beta_n 2.289.9 "$TAGS")" "1"
is "2.290.0 does not match 2.290.10" "$(next_beta_n 2.290.1 "$TAGS")" "1"
is "betas_of is exact on the version" "$(betas_of 2.290.1 "$TAGS" | grep -c .)" "0"

# the gate itself, on the injected list: refuse, allow after a beta, skip with a reason
all_desktop_tags() { printf '%s\n' "$TAGS"; }
# BETA is set explicitly on EVERY call: the gate's first branch reads it, and a
# value left over from one case must never decide the next (review, 2026-09-21).
_fails=0; BETA=0; TAG=v2.289.9-desktop
gate_beta_first 2.289.9 v2.289.9-desktop >/dev/null
is "no beta -> refused"            "$_fails" "1"
_fails=0; BETA=0; gate_beta_first 2.290.0 v2.290.0-desktop >/dev/null
is "beta exists -> allowed"        "$_fails" "0"
_fails=0; BETA=0; RELEASE_SKIP_BETA=1 RELEASE_SKIP_BETA_REASON="" gate_beta_first 2.289.9 v2.289.9-desktop >/dev/null
is "skip without a reason -> refused" "$_fails" "1"
_fails=0; BETA=1; TAG=v2.289.9-beta.1-desktop
gate_beta_first 2.289.9 v2.289.9-desktop >/dev/null
is "cutting the beta itself -> allowed" "$_fails" "0"
BETA=0; TAG=""
# the audited skip writes its row somewhere we can throw away
BT="$(mktemp -d)"
( cd "$BT" && _fails=0 && BETA=0 && RELEASE_SKIP_BETA=1 RELEASE_SKIP_BETA_REASON="hotfix, founder on the call" gate_beta_first 2.289.9 v2.289.9-desktop >/dev/null \
  && [ "$_fails" = 0 ] && grep -q '"reason": *"hotfix, founder on the call"' .enforcement/release-beta-skips.jsonl ) \
  && pass=$((pass+1)) || { fail=$((fail+1)); printf 'FAIL skip with a reason must pass and be audited\n'; }
rm -rf "$BT"
unset -f all_desktop_tags

# ---- 13b. STABLE AT THE BETA'S COMMIT (D82): what was smoked is what ships --
# The two git reads are injected (beta_commit_of, head_commit), like the tag
# list above, so no git runs here.
all_desktop_tags() { printf '%s\n' "$TAGS"; }
beta_commit_of() { case "$1" in v2.290.0-beta.3-desktop) printf 'cafe0003' ;; v2.290.0-beta.1-desktop) printf 'cafe0001' ;; *) printf '' ;; esac; }
head_commit() { printf '%s' "${HEADSHA:-}"; }
_fails=0; BETA=0; TAG=v2.290.0-desktop; HEADSHA=cafe0003
gate_stable_at_beta 2.290.0 v2.290.0-desktop >/dev/null
is "HEAD at the last beta -> allowed"                "$_fails" "0"
_fails=0; BETA=0; HEADSHA=cafe0001
gate_stable_at_beta 2.290.0 v2.290.0-desktop >/dev/null
is "HEAD at an OLDER beta -> refused (the last one was smoked)" "$_fails" "1"
_fails=0; BETA=0; HEADSHA=deadbeef
gate_stable_at_beta 2.290.0 v2.290.0-desktop >/dev/null
is "main moved past the beta -> refused"             "$_fails" "1"
_fails=0; BETA=0; HEADSHA=deadbeef
gate_stable_at_beta 2.289.9 v2.289.9-desktop >/dev/null
is "no beta at all -> refused"                       "$_fails" "1"
_fails=0; BETA=1; TAG=v2.290.0-beta.4-desktop; HEADSHA=deadbeef
gate_stable_at_beta 2.290.0 v2.290.0-desktop >/dev/null
is "cutting a beta itself -> allowed"                "$_fails" "0"
_fails=0; BETA=0; TAG=v2.290.0-desktop; HEADSHA=deadbeef
RELEASE_SKIP_BETA=1 RELEASE_SKIP_BETA_REASON="hotfix" gate_stable_at_beta 2.290.0 v2.290.0-desktop >/dev/null
is "the audited D80 skip covers the commit pin too"  "$_fails" "0"
BETA=0; TAG=""; unset HEADSHA
unset -f all_desktop_tags beta_commit_of head_commit
# the smoke's pure helpers, sourced with nothing else running
BETA_SMOKE_LIB=1 . "$HERE/beta-smoke.sh"
is "smoke arch arm64"   "$(smoke_arch arm64)" "arm64"
is "smoke arch aarch64" "$(smoke_arch aarch64)" "arm64"
is "smoke arch x86_64"  "$(smoke_arch x86_64)" "x86_64"
no_ smoke_arch i386
is "smoke asset name"   "$(smoke_asset_for x86_64)" "Sutra-x86_64.dmg"
is "smoke version of a beta tag" "$(smoke_version_of v2.291.1-beta.2-desktop)" "2.291.1"
is "smoke refuses a stable tag"  "$(smoke_version_of v2.291.1-desktop)" ""
is "smoke installs into /Applications when writable" "$(smoke_install_dir yes /Users/x)" "/Applications"
is "smoke falls back to ~/Applications"              "$(smoke_install_dir no /Users/x)" "/Users/x/Applications"
is "smoke walks the Shadow surfaces" "$(printf '%s\n' $SMOKE_ROUTES | grep -c '/api/shadow/')" "4"
is "smoke opens the panel itself"    "$(printf '%s\n' $SMOKE_ROUTES | grep -cx '/')" "1"

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

# ---- 6. the six assets a shippable release carries (Mac + Windows, D83) ----
WIN="Sutra-Setup-x64.exe Sutra-Setup-x64.exe.sha256"
ALL="$(printf 'Sutra-arm64.dmg\nSutra-arm64.dmg.sha256\nSutra-x86_64.dmg\nSutra-x86_64.dmg.sha256\nSutra-Setup-x64.exe\nSutra-Setup-x64.exe.sha256')"
is "complete release"    "$(missing_assets "$ALL")" ""
is "mac only"            "$(missing_assets "$(printf 'Sutra-arm64.dmg\nSutra-arm64.dmg.sha256\nSutra-x86_64.dmg\nSutra-x86_64.dmg.sha256')")" \
   "$WIN"
is "arm64 only"          "$(missing_assets "$(printf 'Sutra-arm64.dmg\nSutra-arm64.dmg.sha256')")" \
   "Sutra-x86_64.dmg Sutra-x86_64.dmg.sha256 $WIN"
is "dmg without checksum" "$(missing_assets "$(printf 'Sutra-arm64.dmg\nSutra-x86_64.dmg')")" \
   "Sutra-arm64.dmg.sha256 Sutra-x86_64.dmg.sha256 $WIN"
is "empty release"       "$(missing_assets "")" \
   "Sutra-arm64.dmg Sutra-arm64.dmg.sha256 Sutra-x86_64.dmg Sutra-x86_64.dmg.sha256 $WIN"
# a near-miss name must not satisfy a requirement
is "prefix is not a match" "$(missing_assets "$(printf 'Sutra-arm64.dmg.sha256sum')")" \
   "Sutra-arm64.dmg Sutra-arm64.dmg.sha256 Sutra-x86_64.dmg Sutra-x86_64.dmg.sha256 $WIN"

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
# D82: the pipeline's OWN audit rows -- untracked files on a never-commit path
# (the smoke's beta-smoke.jsonl, the D80 skip's release-beta-skips.jsonl) --
# are ignored, not a reason to stop; a TRACKED never-path that changed still blocks
is "untracked audit row is ignored" \
   "$(classify_dirty "$(printf '?? .enforcement/beta-smoke.jsonl')")" \
   "ignore .enforcement/beta-smoke.jsonl"
is "tracked never-path still blocks" \
   "$(classify_dirty "$(printf ' M .enforcement/beta-smoke.jsonl')")" \
   "block .enforcement/beta-smoke.jsonl"
is "ignored rows are neither block nor include" \
   "$(classify_dirty "$(printf '?? .enforcement/beta-smoke.jsonl\n?? scripts/y.sh')" | grep -cE '^(block|include) ')" "1"

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
is "six required assets"       "$(printf '%s' "$REQUIRED_ASSETS" | wc -w | tr -d ' ')" "6"
# ---- 9. D83: --beta goes to production, --beta-only stops at the beta -----
is "--beta runs the auto path"      "$(grep -c -- '--beta|--auto) AUTO=1; BETA=1' "$HERE/release-desktop.sh")" "1"
is "--beta-only is the opt-out"     "$(grep -cE -- '--beta-only\)[[:space:]]+BETA=1; shift' "$HERE/release-desktop.sh")" "1"
is "auto waits for the windows leg" "$(grep -c 'release-dmg.yml release-windows.yml' "$HERE/release-desktop.sh")" "1"
# ---- 10b. a stable leg already on origin/main is tagged as is, never rebased --
# (2026-09-23: a peer pushed during the beta build; the stable leg refused to
# rebase and nothing shipped. Rebasing would also have moved it off the smoked commit.)
is "already-pushed HEAD skips the rebase" "$(grep -c 'if git merge-base --is-ancestor HEAD origin/main; then' "$HERE/release-desktop.sh")" "1"
SB="$(mktemp -d)"; ( cd "$SB" && git init -q --bare origin.git && git clone -q origin.git w 2>/dev/null && cd w \
  && git commit -q --allow-empty -m beta && git push -q origin HEAD:main && git commit -q --allow-empty -m peer \
  && git push -q origin HEAD:main && git reset -q --hard HEAD~1 && git fetch -q origin \
  && git merge-base --is-ancestor HEAD origin/main ) >/dev/null 2>&1
is "a beta commit behind a peer push counts as on origin/main" "$?" "0"
rm -rf "$SB"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" = 0 ]
