#!/usr/bin/env bash
# =============================================================================
# release-desktop.sh -- one command for the macOS desktop release
# =============================================================================
# THE PROCESS THIS REPLACES. Cutting a desktop release meant doing, by hand and
# in order: bump four files, run the checklist's gates, commit, fetch, rebase,
# re-run the gates, push main, tag, push the tag, then verify the DMGs. Every
# step was recoverable and one of them -- check 2 -- had already gone stale
# unnoticed, so a build shipped without testing the code it shipped.
#
# WHAT IT IS NOT. This is the DESKTOP path only: git + the four version
# surfaces + release-dmg.yml. plugin-release-gate.yml is a different workflow
# on a different trigger (push to main under marketplace/plugin/**) and is
# deliberately NOT part of this path -- the desktop release contract, in
# release-checklist.md, never names it.
#
# THE CONTRACT IT ENFORCES is release-checklist.md's, not one of its own. Every
# gate below cites the check it implements, and where the checklist and this
# script disagree the checklist wins and this script is wrong.
#
# Usage:
#   scripts/release-desktop.sh check   [--beta] [--bump patch|minor] [--version X.Y.Z]
#   scripts/release-desktop.sh release [--beta] [--bump patch|minor] [--version X.Y.Z]
#                                      [--notes FILE] [--yes]
#   scripts/release-desktop.sh verify  [TAG]
#
# `check` is read-only and safe to run at any time. `release` refuses to start
# unless `check` passes, and stops at the first failed gate.
#
# BETA FIRST (founder D80, 2026-09-21: "we first produce the app to beta; in
# beta I see those features, and then I put it into production"). A release
# is two tags on the same version:
#   1. `release --beta`   cuts vX.Y.Z-beta.N-desktop; the pipeline builds the
#                         coexisting "Sutra Beta" app as a GitHub prerelease.
#   2. `release`          cuts vX.Y.Z-desktop, and is REFUSED unless a beta
#                         of that same X.Y.Z already exists AND HEAD is that
#                         beta's commit (D82: what was smoked is what ships).
# NO HUMAN IN BETWEEN (founder D82, 2026-09-21: "I don't want any manual look
# ... do that automatically in beta and then push out to main as well. No
# human involvement"). One command does both tags and the look:
#   `release --auto`      beta -> wait for the GitHub build -> scripts/beta-smoke.sh
#                         on this Mac (fetch, checksum, staple, launch, walk,
#                         quit) -> stable. Stops, named, at the first failure.
# Founder skip, never the default and always audited to
# .enforcement/release-beta-skips.jsonl:
#   RELEASE_SKIP_BETA=1 RELEASE_SKIP_BETA_REASON='<why>' scripts/release-desktop.sh release
# =============================================================================
set -uo pipefail

# --- where things live, all verified against the repo ------------------------
# Two of these are compared against the tag by the workflow's `guard` job and
# fail the release; two are documentation the checklist calls "the ones that get
# missed". PLUGIN_JSON is the source of truth for "what version are we on",
# because it is the first thing guard reads.
PLUGIN_JSON="marketplace/plugin/.claude-plugin/plugin.json"   # guard
MARKET_JSON=".claude-plugin/marketplace.json"                 # guard (core)
CHANGELOG="marketplace/plugin/CHANGELOG.md"                   # checklist
CURRENT_VERSION="CURRENT-VERSION.md"                          # checklist
WORKFLOW=".github/workflows/release-dmg.yml"
UI="marketplace/plugin/sutra-ui"
CHECKLIST="$UI/release-checklist.md"

#: The four assets `verify` requires. A one-architecture release is not
#: shippable (release-checklist.md check 3).
REQUIRED_ASSETS="Sutra-arm64.dmg Sutra-arm64.dmg.sha256 Sutra-x86_64.dmg Sutra-x86_64.dmg.sha256"

#: WHAT A DESKTOP RELEASE MAY CARRY. `release` can start from a dirty tree --
#: that is the normal release-prep state -- but only for paths a desktop
#: release legitimately touches. Anything else is an UNEXPECTED change and
#: blocks, named, rather than being swept into a release commit. This is the
#: protection check 1 used to give by demanding a clean tree; the tree may now
#: be dirty, and what may be in it is enumerated instead.
RELEASE_SCOPE="marketplace/plugin/ .github/workflows/release-dmg.yml CURRENT-VERSION.md .claude-plugin/marketplace.json scripts/"

#: NEVER, whatever the scope says. Machine state churns on every tool call and
#: signing material IS the identity -- neither belongs in a release commit, and
#: a path matching one of these blocks even when it sits inside the scope above.
RELEASE_NEVER=".enforcement/ .claude/sessions/ .claude/heartbeats/ .sutra/ holding/state/ .p12 .p8 .certSigningRequest .env"
#: How many times check 6 wants test_panel.js run. Five, because the flake
#: class it guards is intermittent: four green and one red still means racing.
PANEL_RUNS=5

# =============================================================================
# PURE LOGIC -- no git, no network, no filesystem writes. Everything below this
# banner is unit-tested by scripts/test-release-desktop.sh, which sources this
# file with RELEASE_DESKTOP_LIB=1 so main() never runs.
# =============================================================================

# A version is three dot-separated integers and nothing else. Deliberately
# strict: a leading `v`, a `-beta.N` suffix or a stray space is a mistake worth
# refusing, not normalising.
is_semver() {
  printf '%s' "${1:-}" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'
}

# THE TWO TAG FORMS THE GUARD JOB ACCEPTS. vX.Y.Z-desktop is the stable
# release; vX.Y.Z-beta.N-desktop is the beta of the SAME version (guard strips
# the -beta.N before it compares against the manifests). Since D80 this script
# cuts both: N is not guessed, it is the next number after the betas that
# already exist for that version (next_beta_n).
tag_for() {
  printf 'v%s-desktop' "${1:-}"
}
beta_tag_for() {
  printf 'v%s-beta.%s-desktop' "${1:-}" "${2:-1}"
}

is_desktop_tag() {
  printf '%s' "${1:-}" | grep -qE '^v[0-9]+\.[0-9]+\.[0-9]+-desktop$'
}
is_beta_tag() {
  printf '%s' "${1:-}" | grep -qE '^v[0-9]+\.[0-9]+\.[0-9]+-beta\.[0-9]+-desktop$'
}

# The betas of one version, out of a newline-separated tag list (the caller
# supplies `git tag` + `ls-remote` output, so these stay pure and testable).
betas_of() {                                   # betas_of <version> <taglist>
  local v; v="$(printf '%s' "${1:-}" | sed 's/\./\\./g')"
  printf '%s\n' "${2:-}" | grep -E "^v${v}-beta\.[0-9]+-desktop$" || true
}
has_beta() {                                   # has_beta <version> <taglist>
  [ -n "$(betas_of "$1" "${2:-}")" ]
}
latest_beta_tag() {                            # highest N, or nothing
  betas_of "$1" "${2:-}" | sed -E 's/^(.*-beta\.)([0-9]+)(-desktop)$/\2 \1\2\3/' | sort -n | tail -1 | awk '{print $2}'
}
next_beta_n() {                                # 1 when none exists
  local last n
  last="$(latest_beta_tag "$1" "${2:-}")"
  if [ -z "$last" ]; then printf '1'; return 0; fi
  n="$(printf '%s' "$last" | sed -E 's/^.*-beta\.([0-9]+)-desktop$/\1/')"
  case "$n" in ''|*[!0-9]*) printf '1'; return 0 ;; esac   # never arithmetic on a non-number
  printf '%s' "$((n + 1))"
}

# The version a tag claims, which is what guard compares against the manifests.
version_from_tag() {
  local t="${1:-}"
  t="${t#v}"; t="${t%-desktop}"; t="${t%-beta.*}"
  printf '%s' "$t"
}

# BUMPING IS NOT ASSUMED, IT IS ASKED FOR. This repo's history shows patch
# increments inside a minor (2.281.0 -> .1 -> .2) and a minor bump for a
# feature set (2.281.2 -> 2.282.0); nothing in the tree encodes which a given
# change deserves. So the caller says, `patch` is the default because it is the
# commoner of the two, and `--version` exists for anything else.
bump_version() {
  local cur="$1" kind="${2:-patch}"
  is_semver "$cur" || { printf 'bad version: %s\n' "$cur" >&2; return 2; }
  local major minor patch
  major="${cur%%.*}"; local rest="${cur#*.}"
  minor="${rest%%.*}"; patch="${rest#*.}"
  case "$kind" in
    patch) patch=$((patch + 1)) ;;
    minor) minor=$((minor + 1)); patch=0 ;;
    *) printf 'bad bump kind: %s (want patch|minor)\n' "$kind" >&2; return 2 ;;
  esac
  printf '%s.%s.%s' "$major" "$minor" "$patch"
}

# WHETHER A BUMP IS NEEDED AT ALL, and this is the part a naive script gets
# wrong. The manifests can already be ahead of the last tag: 2.282.0 and
# 2.282.1 were released as plugin versions and never carried a desktop tag. So
# if the CURRENT version has no tag yet, the release IS the current version and
# nothing needs bumping. Only when the current version is already tagged does a
# new release require a new number.
#
# derive_target <current> <bump-kind> <tag-exists:yes|no> [explicit-version]
#   -> "<target-version> <commit-required:yes|no>"
derive_target() {
  local cur="$1" kind="${2:-patch}" tagged="${3:-no}" explicit="${4:-}"
  if [ -n "$explicit" ]; then
    is_semver "$explicit" || { printf 'bad --version: %s\n' "$explicit" >&2; return 2; }
    if [ "$explicit" = "$cur" ]; then printf '%s no' "$explicit"; else printf '%s yes' "$explicit"; fi
    return 0
  fi
  if [ "$tagged" = "no" ]; then
    printf '%s no' "$cur"          # the manifests are already the release
    return 0
  fi
  local next
  next="$(bump_version "$cur" "$kind")" || return 2
  printf '%s yes' "$next"
}

# CHECK 2, as the checklist states it: the workflow's explicit list and the
# suites on disk must be the same number. Two arguments rather than one because
# a single hardcoded count is exactly what went stale here before.
counts_agree() {
  [ "${1:-x}" = "${2:-y}" ]
}

# Every asset the release must carry, given what the release actually has.
# Prints what is missing; empty output means complete.
missing_assets() {
  local have="$1" want miss=""
  for want in $REQUIRED_ASSETS; do
    printf '%s\n' "$have" | grep -qx "$want" || miss="$miss $want"
  done
  printf '%s' "${miss# }"
}

# Does this path sit inside the desktop release scope? Prefix match, because
# the scope is expressed as directories and exact files.
in_release_scope() {
  local path="${1:-}" pre
  [ -n "$path" ] || return 1
  for pre in $RELEASE_SCOPE; do
    case "$path" in "$pre"*) return 0 ;; esac
  done
  return 1
}

# Machine state or signing material: never committed, scope notwithstanding.
# Matched anywhere in the path, so a nested .enforcement/ is caught too.
is_never_commit() {
  local path="${1:-}" pat
  [ -n "$path" ] || return 1
  for pat in $RELEASE_NEVER; do
    case "$path" in *"$pat"*) return 0 ;; esac
  done
  return 1
}

# Split `git status --porcelain` into what a release may carry and what it may
# not. Prints one line per path, prefixed `include ` or `block `, so the caller
# can show the founder exactly what is about to be committed and why anything
# else stopped the release. Pure: it reads the text it is given, not the tree.
classify_dirty() {
  local porcelain="${1:-}" line path
  [ -n "$porcelain" ] || return 0
  # `printf %s`, not `printf '%s\n'`, DROPS THE LAST LINE: `read` needs the
  # terminator, so a one-path tree classified to nothing and the final path of
  # any tree was silently unjudged -- an unexpected change could have ridden
  # into a release commit precisely because it was last. Caught by the unit
  # tests, which is what they are for.
  printf '%s\n' "$porcelain" | while IFS= read -r line; do
    [ -n "$line" ] || continue
    path="$(printf %s "$line" | cut -c4-)"
    path="${path##* -> }"          # a rename reports "old -> new"; judge the new
    if is_never_commit "$path"; then printf "block %s\n" "$path"
    elif in_release_scope "$path"; then printf "include %s\n" "$path"
    else printf "block %s\n" "$path"; fi
  done
}

# THE RELEASE ENTRY, BUILT FROM WHAT THE RANGE ACTUALLY CONTAINS. Every bullet
# is a commit subject, verbatim -- text a human wrote about a change that is in
# the diff by construction. Nothing here reads a diff and decides what it
# MEANS: a generated summary of code it cannot understand is how a changelog
# starts claiming features that were never built. The footer is arithmetic.
#
# notes_body <range-label> <subjects, one per line> <diffstat-line> <new-tests>
notes_body() {
  local range="${1:-}" subjects="${2:-}" stat="${3:-}" tests="${4:-}"
  local n; n="$(printf '%s\n' "$subjects" | grep -c . || true)"
  printf -- "- Released from %s: %s commit(s). Each line below is a commit subject from that range, quoted, not a summary of the code.\n" \
    "$range" "${n:-0}"
  printf '%s\n' "$subjects" | while IFS= read -r line; do   # see classify_dirty
    [ -n "$line" ] || continue
    printf -- "  - %s\n" "$line"
  done
  [ -n "$stat" ] && printf -- "- Changed: %s\n" "$stat"
  [ -n "$tests" ] && printf -- "- New test suites: %s\n" "$tests"
  return 0
}
# =============================================================================
# REPORTING
# =============================================================================
_fails=0
ok()   { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; _fails=$((_fails + 1)); }
note() { printf '        %s\n' "$1"; }
head_() { printf '\n\033[1m%s\033[0m\n' "$1"; }
die()  { printf '\033[31merror:\033[0m %s\n' "$1" >&2; exit 2; }

# =============================================================================
# GATES -- each cites the checklist check it implements
# =============================================================================

gate_tree_clean() {                       # check 1
  # CHECK 1 SAYS "commit or revert each before tagging", and that is what this
  # enforces -- but `release` is now the thing that commits them, so a dirty
  # tree is not automatically a failure. What matters is whether every dirty
  # path is one a desktop release may carry. An UNEXPECTED path still blocks,
  # by name, which is the protection check 1 actually exists to give: nothing
  # reaches a release commit that nobody looked at.
  local dirty; dirty="$(git status --porcelain)"
  if [ -z "$dirty" ]; then ok "check 1: working tree clean"; return; fi
  local classified blocked included
  classified="$(classify_dirty "$dirty")"
  blocked="$(printf '%s\n' "$classified" | grep '^block ' | sed 's/^block //')"
  included="$(printf '%s\n' "$classified" | grep '^include ' | sed 's/^include //')"
  if [ -n "$blocked" ]; then
    bad "check 1: the tree carries change a desktop release must not sweep in"
    printf '%s\n' "$blocked" | sed 's/^/        out of scope: /'
    note "commit, revert or stash these yourself -- release will not decide for you"
  fi
  if [ -n "$included" ]; then
    ok "check 1: $(printf '%s\n' "$included" | grep -c .) in-scope change(s), which release will commit"
    printf '%s\n' "$included" | sed 's/^/        /'
  fi
}

gate_versions_aligned() {                 # check 4
  local p m c
  p="$(jq -r .version "$PLUGIN_JSON" 2>/dev/null)"
  m="$(jq -r '.plugins[] | select(.name=="core") | .version' "$MARKET_JSON" 2>/dev/null)"
  c="$(grep -m1 -oE '[0-9]+\.[0-9]+\.[0-9]+' "$CURRENT_VERSION" 2>/dev/null)"
  if [ "$p" = "$m" ] && [ "$p" = "$c" ]; then ok "check 4: version aligned across three surfaces ($p)"
  else bad "check 4: versions disagree -- plugin.json=$p marketplace(core)=$m CURRENT-VERSION=$c"; fi
  if grep -qE "^## ${p//./\\.} " "$CHANGELOG"; then ok "check 4: CHANGELOG has an entry for $p"
  else bad "check 4: CHANGELOG has no '## $p' entry"; fi
}

gate_guard_simulation() {                 # the workflow's own guard job
  # WHAT THE GUARD WILL SEE, NOT WHAT IS THERE NOW. `release` commits the bump
  # before it tags, so at tag time both manifests read $TARGET. Comparing the
  # tag against the PRE-bump value would report BLOCKED on every bumped release
  # for a gate that is going to pass -- the one way a correct gate still lies.
  local tag="$1" target="$2" want p m
  want="$(version_from_tag "$tag")"
  is_desktop_tag "$tag" || is_beta_tag "$tag" || { bad "guard: '$tag' is not vX.Y.Z[-beta.N]-desktop"; return; }
  if [ "$want" != "$target" ]; then
    bad "guard: tag $tag claims $want but the target version is $target"; return
  fi
  p="$(jq -r .version "$PLUGIN_JSON" 2>/dev/null)"
  m="$(jq -r '.plugins[] | select(.name=="core") | .version' "$MARKET_JSON" 2>/dev/null)"
  if [ "$want" = "$p" ] && [ "$want" = "$m" ]; then
    ok "guard: $tag validates against both manifests, as they stand"
  else
    ok "guard: $tag will validate once the bump is committed (manifests read $p today)"
    note "guard compares the tag against plugin.json and marketplace.json(core) at tag time"
  fi
}

gate_workflow_integrity() {
  [ -f "$WORKFLOW" ] || { bad "workflow: $WORKFLOW is missing"; return; }
  if grep -q 'fail-fast: false' "$WORKFLOW"; then ok "workflow: fail-fast:false on the dmg matrix (an Intel failure must not delete the arm64 build)"
  else bad "workflow: fail-fast:false is absent -- one leg failing would discard the other"; fi
  # Both labels carry a trailing comment, so this must not anchor on end of
  # line. It matches the label followed by whitespace-or-end, which is what
  # distinguishes `macos-15` from `macos-15-intel`.
  local runners=0
  grep -qE 'runner: macos-15([[:space:]]|$)' "$WORKFLOW" && runners=$((runners+1))
  grep -qE 'runner: macos-15-intel([[:space:]]|$)' "$WORKFLOW" && runners=$((runners+1))
  if [ "$runners" = 2 ]; then ok "workflow: both arch legs have a runner label"
  else bad "workflow: expected two runner labels, found $runners -- a retired label HANGS rather than fails"; fi
  local want miss=""
  for want in $REQUIRED_ASSETS; do grep -q "$want" "$WORKFLOW" || miss="$miss $want"; done
  if [ -z "$miss" ]; then ok "workflow: verify job names all four required assets"
  else bad "workflow: verify job does not name:$miss"; fi
}

gate_shadow_wiring() {                    # check 2
  local listed disk commented
  listed="$(grep -c 'node test_shadow_.*\.js' "$WORKFLOW" 2>/dev/null || echo 0)"
  disk="$(find "$UI" -maxdepth 1 -name 'test_shadow_*.js' | wc -l | tr -d ' ')"
  if counts_agree "$listed" "$disk"; then ok "check 2: Shadow suites wired ($listed of $disk)"
  else
    bad "check 2: workflow lists $listed, disk has $disk -- the difference is invisible to the DMG build"
    local t
    for t in $(find "$UI" -maxdepth 1 -name 'test_shadow_*.js' -exec basename {} \; | sort); do
      grep -q "node $t" "$WORKFLOW" || note "not wired: $t"
    done
  fi
  # A comment containing the counted pattern inflates the first number and makes
  # the check lie in the safe-looking direction.
  commented="$(grep 'node test_shadow_.*\.js' "$WORKFLOW" 2>/dev/null | grep -c '^\s*#' || true)"
  if [ "${commented:-0}" = 0 ]; then ok "check 2: the counted pattern appears in no comment"
  else bad "check 2: $commented commented occurrence(s) of the counted pattern -- the count is inflated"; fi
}

gate_panel_step() {
  # Run exactly what the Panel step runs, in its order, under `bash -e` -- the
  # shell CI uses, where the first red aborts the leg before a DMG is built.
  local suites; suites="$(sed -n '/name: Panel tests/,/^$/p' "$WORKFLOW" | grep -oE 'node test_[a-z0-9_]*\.js' | sed 's/^node //')"
  [ -n "$suites" ] || { bad "panel step: could not read the suite list from $WORKFLOW"; return; }
  local n; n="$(printf '%s\n' "$suites" | wc -l | tr -d ' ')"
  if ( cd "$UI" && for s in $suites; do node "$s" >/dev/null 2>&1 || exit 1; done ); then
    ok "panel step: all $n commands green (the DMG leg's own gate)"
  else
    bad "panel step: a suite is red -- the dmg leg would abort here, before any DMG is built"
    ( cd "$UI" && for s in $suites; do node "$s" >/dev/null 2>&1 || note "red: $s"; done )
  fi
}

gate_all_js() {                           # check 5
  local red=""
  local t
  for t in $(cd "$UI" && ls test_*.js 2>/dev/null); do
    ( cd "$UI" && node "$t" >/dev/null 2>&1 ) || red="$red $t"
  done
  local n; n="$(cd "$UI" && ls test_*.js 2>/dev/null | wc -l | tr -d ' ')"
  if [ -z "$red" ]; then ok "check 5: all $n sutra-ui JS suites green"
  else bad "check 5: red:$red"; fi
}

gate_panel_repeat() {                     # check 6
  # The flake class that cost v2.274.0 its Intel build: an assertion reading the
  # clock it is testing against. Five runs, because one red in five is the whole
  # signal.
  local i green=0
  for i in $(seq 1 $PANEL_RUNS); do
    ( cd "$UI" && node test_panel.js >/dev/null 2>&1 ) && green=$((green + 1)) || note "run $i: RED"
  done
  if [ "$green" = "$PANEL_RUNS" ]; then ok "check 6: test_panel.js green $green/$PANEL_RUNS consecutive"
  else bad "check 6: $green/$PANEL_RUNS green -- the assertion is still racing and the Intel runner will find it"; fi
}

gate_python() {
  local out
  out="$(cd "$UI" && ./run-tests.sh $(ls test_shadow_*.py 2>/dev/null | tr '\n' ' ') test_app.py 2>&1)" || true
  local passed failed
  passed="$(printf '%s\n' "$out" | grep -c ' PASS ' || true)"
  failed="$(printf '%s\n' "$out" | grep -c ' FAIL' || true)"
  if [ "${failed:-0}" = 0 ] && [ "${passed:-0}" -gt 0 ]; then ok "python: $passed Shadow/app lanes green"
  else bad "python: $failed lane(s) red of $((passed + failed))"; printf '%s\n' "$out" | grep ' FAIL' | sed 's/^/        /'; fi
}

# THE SUITE THAT HAS TAKEN DOWN FOUR RELEASES, and which this script did not
# run until 2.287.1. `Engine + importer tests` is a dmg-leg step, so a red one
# aborts the leg before a DMG exists -- exactly like the Panel step gate_panel_step
# already simulates -- yet `check` printed READY for v2.286.1 and v2.287.0 and
# both died there. It is pinned to the export checked into website/domains/, so
# the thing that breaks it is never a code change: it is an unattended regen of
# that export (bb66966, 7973d6c, c991193b, 33b7be5f). Run the workflow's exact
# command, not an approximation of it.
gate_engine_importer() {
  local out rc
  out="$(python3 -m unittest discover -s marketplace/plugin/lib/tests -p 'test_*.py' 2>&1)"; rc=$?
  local ran; ran="$(printf '%s\n' "$out" | grep -oE '^Ran [0-9]+ tests?' | grep -oE '[0-9]+' | head -1)"
  if [ "$rc" = 0 ]; then ok "engine + importer: ${ran:-?} tests green (the dmg leg's other gate)"
  else
    bad "engine + importer: red -- the dmg leg would abort here, before any DMG is built"
    printf '%s\n' "$out" | grep -E '^(FAIL|ERROR):' | sed 's/^/        /'
    note "pinned to website/domains/ -- an unattended regen of that export is the usual cause"
  fi
}

gate_main_synced() {
  git fetch origin --quiet 2>/dev/null || { bad "sync: could not fetch origin"; return; }
  local counts behind ahead
  counts="$(git rev-list --left-right --count origin/main...HEAD)"
  behind="$(printf '%s' "$counts" | awk '{print $1}')"
  ahead="$(printf '%s' "$counts" | awk '{print $2}')"
  if [ "$behind" = 0 ] && [ "$ahead" = 0 ]; then ok "sync: local main == origin/main"
  elif [ "$behind" = 0 ]; then ok "sync: $ahead commit(s) to push, 0 behind"
  else bad "sync: $behind behind / $ahead ahead -- rebase before releasing"; fi
}

gate_tag_free() {
  local tag="$1"
  if [ -n "$(git tag -l "$tag")" ]; then bad "tag: $tag already exists locally -- a release tag is never overwritten"
  elif [ -n "$(git ls-remote --tags origin "$tag" 2>/dev/null)" ]; then bad "tag: $tag already exists on origin"
  else ok "tag: $tag is free, locally and on origin"; fi
}

# Every desktop tag, local and on origin, one per line. The one impure input
# the beta gate reads; tests override this function with a fixed list.
all_desktop_tags() {
  { git tag -l 'v*-desktop'
    git ls-remote --tags origin 'v*-desktop' 2>/dev/null | awk '{print $2}' | sed 's#^refs/tags/##; s#\^{}$##'
  } | sort -u
}

#: BETA FIRST (founder D80, 2026-09-21). A stable tag is refused unless a beta
#: of the same version already exists: the founder sees the features in the
#: Beta app, then puts them into production. The skip is the founder's, named
#: and audited; it is never the default and a bare skip without a reason fails.
gate_beta_first() {                         # gate_beta_first <version> <stable-tag>
  local version="$1" tag="$2" tags last
  if [ "${BETA:-0}" = 1 ]; then ok "beta: cutting $TAG -- the stable $tag comes after you have seen it (D80)"; return; fi
  tags="$(all_desktop_tags)"
  if has_beta "$version" "$tags"; then
    last="$(latest_beta_tag "$version" "$tags")"
    ok "beta: $last went before $tag (D80)"
  elif [ "${RELEASE_SKIP_BETA:-0}" = 1 ]; then
    if [ -z "${RELEASE_SKIP_BETA_REASON:-}" ]; then
      bad "beta: RELEASE_SKIP_BETA=1 needs RELEASE_SKIP_BETA_REASON='<why>' -- a skip without a reason is not a founder decision"
      return
    fi
    mkdir -p .enforcement
    printf '{"ts":"%s","tag":"%s","version":"%s","actor":"%s","reason":%s}\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$tag" "$version" "$(git config user.name 2>/dev/null || echo unknown)" \
      "$(printf '%s' "$RELEASE_SKIP_BETA_REASON" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' 2>/dev/null || printf '"%s"' "$RELEASE_SKIP_BETA_REASON")" \
      >> .enforcement/release-beta-skips.jsonl
    ok "beta: SKIPPED by founder -- $RELEASE_SKIP_BETA_REASON (audited: .enforcement/release-beta-skips.jsonl)"
  else
    bad "beta: no v$version-beta.N-desktop exists -- cut it first (release --auto does the beta, the smoke and the stable in one run; D80/D82). Founder skip: RELEASE_SKIP_BETA=1 RELEASE_SKIP_BETA_REASON='<why>'"
  fi
}

#: STABLE AT THE BETA'S COMMIT (founder D82, 2026-09-21). What ships is exactly
#: what was smoked: a stable tag is refused when main has moved past the last
#: beta of the same version. The fix is a new beta, which `release --auto`
#: cuts by itself. Skipped for a beta tag; the audited D80 skip covers it.
#: The two impure reads are functions so the tests can inject them.
beta_commit_of() {                          # beta_commit_of <tag> -> sha, or nothing
  local sha
  sha="$(git rev-parse -q --verify "${1:-}^{commit}" 2>/dev/null)" && { printf '%s' "$sha"; return 0; }
  git ls-remote origin "refs/tags/${1:-}^{}" 2>/dev/null | awk '{print $1}' | head -1
}
head_commit() { git rev-parse HEAD 2>/dev/null; }
gate_stable_at_beta() {                     # gate_stable_at_beta <version> <stable-tag>
  local version="$1" tag="$2" tags last want have
  if [ "${BETA:-0}" = 1 ]; then ok "beta commit: $TAG is a beta; the stable of $version is cut at a beta's commit (D82)"; return; fi
  if [ "${RELEASE_SKIP_BETA:-0}" = 1 ] && [ -n "${RELEASE_SKIP_BETA_REASON:-}" ]; then ok "beta commit: covered by the audited D80 skip"; return; fi
  tags="$(all_desktop_tags)"
  last="$(latest_beta_tag "$version" "$tags")"
  [ -n "$last" ] || { bad "beta commit: no beta of $version to pin $tag to"; return; }
  want="$(beta_commit_of "$last")"; have="$(head_commit)"
  if [ -n "$want" ] && [ "$want" = "$have" ]; then
    ok "beta commit: HEAD == $last ($(printf '%s' "$have" | cut -c1-8)) -- what was smoked is what ships (D82)"
  else
    bad "beta commit: HEAD $(printf '%s' "$have" | cut -c1-8) is not the last beta $last ($(printf '%s' "${want:-?}" | cut -c1-8)) -- main moved after the smoke; cut a new beta (release --auto does)"
  fi
}

# =============================================================================
# COMMANDS
# =============================================================================

read_state() {
  CUR="$(jq -r .version "$PLUGIN_JSON" 2>/dev/null)"
  is_semver "$CUR" || die "could not read a version from $PLUGIN_JSON (got '${CUR:-}')"
  CUR_TAG="$(tag_for "$CUR")"
  if [ -n "$(git tag -l "$CUR_TAG")" ] || [ -n "$(git ls-remote --tags origin "$CUR_TAG" 2>/dev/null)" ]; then
    CUR_TAGGED=yes
  else
    CUR_TAGGED=no
  fi
  local derived
  derived="$(derive_target "$CUR" "$BUMP" "$CUR_TAGGED" "$EXPLICIT")" || die "could not derive the next version"
  TARGET="$(printf '%s' "$derived" | awk '{print $1}')"
  NEEDS_COMMIT="$(printf '%s' "$derived" | awk '{print $2}')"
  STABLE_TAG="$(tag_for "$TARGET")"
  # A beta of the target version: beta.1 when none exists, else the next N.
  # The version surfaces bump exactly as for a stable, so beta and stable of
  # one version read the same X.Y.Z, which is what guard checks.
  if [ "${BETA:-0}" = 1 ]; then TAG="$(beta_tag_for "$TARGET" "$(next_beta_n "$TARGET" "$(all_desktop_tags)")")"
  else TAG="$STABLE_TAG"; fi
}

cmd_check() {
  read_state
  head_ "RELEASE PLAN"
  printf '  Current version:  %s\n' "$CUR"
  printf '  Next version:     %s%s\n' "$TARGET" \
    "$( [ "$NEEDS_COMMIT" = no ] && printf '   (unchanged -- %s was never tagged)' "$CUR" )"
  printf '  Desktop tag:      %s%s\n' "$TAG" "$( [ "${BETA:-0}" = 1 ] && printf '   (beta -- Sutra Beta app, prerelease)' )"
  printf '  Commit required:  %s\n' "$NEEDS_COMMIT"
  local counts
  counts="$(git rev-list --left-right --count origin/main...HEAD 2>/dev/null || echo '? ?')"
  printf '  Main status:      %s behind / %s ahead of origin/main\n' \
    "$(printf '%s' "$counts" | awk '{print $1}')" "$(printf '%s' "$counts" | awk '{print $2}')"

  head_ "RELEASE GATES"
  gate_tree_clean
  gate_versions_aligned
  gate_guard_simulation "$TAG" "$TARGET"
  gate_tag_free "$TAG"
  gate_beta_first "$TARGET" "$STABLE_TAG"
  gate_stable_at_beta "$TARGET" "$STABLE_TAG"
  gate_main_synced
  gate_workflow_integrity
  gate_shadow_wiring
  if [ "${FAST:-0}" = 1 ]; then
    note "skipped (FAST=1): panel step, check 5, check 6, python lanes, engine + importer"
  else
    gate_panel_step
    gate_all_js
    gate_panel_repeat
    gate_python
    gate_engine_importer
  fi

  head_ "VERDICT"
  if [ "$_fails" = 0 ]; then
    printf '  \033[32mREADY\033[0m -- %s can be cut from %s\n\n' "$TAG" "$(git rev-parse --short HEAD)"
    note "checks 3 and 7 run by scripts/beta-smoke.sh inside 'release --auto' (D82): no manual step."
    return 0
  fi
  printf '  \033[31mBLOCKED\033[0m -- %d gate(s) failed\n\n' "$_fails"
  return 1
}

apply_version() {
  local from="$1" to="$2" notes="${3:-}"
  local today; today="$(date +%Y-%m-%d)"

  # The two guard reads first: jq rewrites them, so a malformed manifest fails
  # here rather than in CI. --arg, never sed -- marketplace.json's `description`
  # field quotes dozens of past version strings and a text replace would hit one.
  jq --arg v "$to" '.version = $v' "$PLUGIN_JSON" > "$PLUGIN_JSON.tmp" \
    && mv "$PLUGIN_JSON.tmp" "$PLUGIN_JSON" || die "could not write $PLUGIN_JSON"
  jq --arg v "$to" '(.plugins[] | select(.name=="core") | .version) = $v' "$MARKET_JSON" > "$MARKET_JSON.tmp" \
    && mv "$MARKET_JSON.tmp" "$MARKET_JSON" || die "could not write $MARKET_JSON"

  # THE PROSE IS NEVER INVENTED. With --notes the file's contents become the
  # entry; without it, cmd_release has already refused unless the entry exists.
  if [ -n "$notes" ]; then
    python3 "$LIBDIR/_release_edit.py" changelog "$CHANGELOG" "$to" "$today" "$notes" \
      || die "could not write the CHANGELOG entry"
  fi

  # CURRENT-VERSION.md carries the HEAD marker on exactly one heading. Move it
  # to the new version and leave the old heading otherwise untouched.
  python3 "$LIBDIR/_release_edit.py" current "$CURRENT_VERSION" "$from" "$to" "$today" \
    || die "could not update $CURRENT_VERSION"
}
# The release entry, from the range about to be released. Writes a notes file
# and prints its path. IMPURE by necessity (it reads git); the FORMATTING is
# notes_body, which is pure and unit-tested.
#
# THE RANGE IS THE LAST DESKTOP TAG TO HEAD, because that is exactly what this
# release adds to the app: plugin versions that never carried a desktop tag
# are still in it, and dating the range from the last CHANGELOG entry would
# silently drop them.
generate_notes() {
  local out="$1" last range subjects stat tests files ins del
  last="$(git tag --sort=-v:refname | grep -- "-desktop$" | head -1)"
  if [ -n "$last" ]; then range="$last..HEAD"; else range="HEAD"; fi
  subjects="$(git log --no-merges --format=%s "$range" 2>/dev/null)"
  if [ -z "$subjects" ]; then
    # Nothing to describe. Say that, rather than inventing a reason to ship.
    printf -- "- No commits since %s; released to rebuild the app from the same tree.\n" \
      "${last:-the start of history}" > "$out"
    return 0
  fi
  files="$(git diff --name-only "$range" 2>/dev/null | grep -c . || true)"
  ins="$(git diff --shortstat "$range" 2>/dev/null | grep -oE "[0-9]+ insertion" | grep -oE "[0-9]+" || true)"
  del="$(git diff --shortstat "$range" 2>/dev/null | grep -oE "[0-9]+ deletion" | grep -oE "[0-9]+" || true)"
  stat="$(printf "%s file(s), +%s/-%s" "${files:-0}" "${ins:-0}" "${del:-0}")"
  tests="$(git diff --diff-filter=A --name-only "$range" 2>/dev/null \
    | grep -E "/test_[a-zA-Z0-9_]+\.(js|py)$" | xargs -n1 basename 2>/dev/null | sort | tr "\n" " " | sed "s/ $//")"
  notes_body "${last:-the start of history}..HEAD" "$subjects" "$stat" "$tests" > "$out"
  return 0
}
cmd_release() {
  [ "${FAST:-0}" = 1 ] && die "FAST=1 skips gates; it is for 'check' only, never for a release"
  read_state
  # THE ENTRY IS NO LONGER SOMETHING YOU MUST HAVE WRITTEN FIRST. Requiring it
  # made `release` a two-command workflow whose first command was "go and write
  # prose", which is the thing this script exists to remove. Without --notes and
  # without an existing entry, the entry is BUILT from the range being released
  # (generate_notes below) -- commit subjects, quoted, plus arithmetic. --notes
  # still wins when it is given, for a release that deserves written prose.
  printf 'Releasing %s as %s\n' "$TARGET" "$TAG"
  if [ "${ASSUME_YES:-0}" != 1 ]; then
    printf 'Proceed? [y/N] '; read -r a; [ "$a" = y ] || die "aborted"
  fi

  # STEP 0: the release-prep state. Everything dirty is classified; anything a
  # desktop release may not carry stops the release by name. The rest is shown
  # and committed as its own commit, before the version moves, so the release
  # commit stays exactly the four version surfaces.
  local dirty; dirty="$(git status --porcelain)"
  if [ -n "$dirty" ]; then
    head_ "0. release-prep changes"
    local classified blocked included
    classified="$(classify_dirty "$dirty")"
    blocked="$(printf '%s\n' "$classified" | grep '^block ' | sed 's/^block //')"
    included="$(printf '%s\n' "$classified" | grep '^include ' | sed 's/^include //')"
    if [ -n "$blocked" ]; then
      printf '%s\n' "$blocked" | sed 's/^/  out of scope: /'
      die "the tree carries change a desktop release must not sweep in -- commit, revert or stash it yourself"
    fi
    printf '%s\n' "$included" | sed 's/^/  including: /'
    if [ "${ASSUME_YES:-0}" != 1 ]; then
      printf 'Commit these as release prep? [y/N] '; read -r a; [ "$a" = y ] || die "aborted"
    fi
    printf '%s\n' "$included" | while IFS= read -r f; do [ -n "$f" ] && git add -- "$f"; done
    git commit -m "release prep for $TAG" -- $(printf '%s ' $included) || die "release-prep commit failed"
    ok "release prep committed as $(git rev-parse --short HEAD)"
  fi

  if [ "$NEEDS_COMMIT" = yes ]; then
    head_ "1. version"
    local notes="$NOTES"
    if [ -z "$notes" ] && ! grep -qE "^## ${TARGET//./\\.} " "$CHANGELOG"; then
      notes="$(mktemp)"; generate_notes "$notes"
      note "entry generated from the release range:"
      sed 's/^/        /' "$notes"
    fi
    apply_version "$CUR" "$TARGET" "$notes"
    [ -z "$NOTES" ] && [ -n "$notes" ] && rm -f "$notes"
    git --no-pager diff --stat
    head_ "2. gates, after the bump"
    _fails=0; gate_versions_aligned; gate_guard_simulation "$TAG" "$TARGET"; gate_beta_first "$TARGET" "$STABLE_TAG"; gate_stable_at_beta "$TARGET" "$STABLE_TAG"; gate_shadow_wiring
    gate_panel_step; gate_all_js; gate_panel_repeat; gate_python; gate_engine_importer
    [ "$_fails" = 0 ] || die "a gate failed after the bump -- nothing committed"
    head_ "3. commit"
    git add -- "$PLUGIN_JSON" "$MARKET_JSON" "$CHANGELOG" "$CURRENT_VERSION"
    git commit -m "release $TARGET: version surfaces for $TAG" \
      -- "$PLUGIN_JSON" "$MARKET_JSON" "$CHANGELOG" "$CURRENT_VERSION" || die "commit failed"
  else
    head_ "1-3. version already at $TARGET, nothing to commit"
    # The beta gates run here too: the bumped path ran them under "2. gates".
    _fails=0; gate_beta_first "$TARGET" "$STABLE_TAG"; gate_stable_at_beta "$TARGET" "$STABLE_TAG"
    [ "$_fails" = 0 ] || die "beta first, at the beta's commit (D80/D82) -- nothing tagged"
  fi

  head_ "4. sync"
  git fetch origin || die "fetch failed"
  local behind; behind="$(git rev-list --count HEAD..origin/main)"
  if [ "$behind" != 0 ]; then
    [ -z "$(git status --porcelain)" ] || die "behind origin/main with a dirty tree -- refusing to rebase"
    printf 'rebasing %s commit(s) from origin/main\n' "$behind"
    git rebase origin/main || die "rebase stopped on a conflict -- resolve it, then re-run"
    head_ "5. gates, after the rebase"
    _fails=0; gate_panel_step; gate_all_js; gate_python
    [ "$_fails" = 0 ] || die "a gate failed after rebasing -- nothing pushed"
  fi

  head_ "6. push main"
  git push origin main || die "push failed"
  git fetch origin --quiet
  [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || die "origin/main is not at HEAD after the push"
  ok "origin/main is at $(git rev-parse --short HEAD)"

  head_ "7. tag"
  gate_tag_free "$TAG"; [ "$_fails" = 0 ] || die "tag exists -- a release tag is never overwritten"
  git tag -a "$TAG" -m "Sutra Desktop $TARGET$( [ "${BETA:-0}" = 1 ] && printf ' beta' )" || die "tag failed"
  git push origin "$TAG" || die "tag push failed"
  local peeled; peeled="$(git ls-remote origin "refs/tags/$TAG^{}" | awk '{print $1}')"
  [ "$peeled" = "$(git rev-parse HEAD)" ] || die "the remote tag does not point at HEAD"
  ok "$TAG on origin -> $(git rev-parse --short HEAD)"

  head_ "WHAT HAS AND HAS NOT HAPPENED"
  note "main pushed: yes    tag pushed: yes"
  note "GitHub build: NOT YET -- the workflow has only just started"
  note "DMGs published: unknown.  Mac app verified: no."
  note "Run: scripts/release-desktop.sh verify $TAG"
  if [ "${BETA:-0}" = 1 ] && [ "${AUTO:-0}" != 1 ]; then
    note "THIS IS THE BETA. No human look (D82): run scripts/release-desktop.sh release --auto"
    note "to smoke it on this Mac and cut production, or by hand: verify $TAG,"
    note "scripts/beta-smoke.sh $TAG, then scripts/release-desktop.sh release"
  fi
}

# =============================================================================
# release --auto (founder D82, 2026-09-21): beta -> build -> smoke on this Mac
# -> stable, in one run, with no human step. Stops, named, at the first
# failure; a stable tag is never cut past a smoke that did not pass.
# =============================================================================
wait_for_run() {                            # wait_for_run <tag> -> 0 when that tag's workflow run succeeded
  local tag="$1" id="" i
  for i in $(seq 1 30); do                  # the run appears a few seconds after the tag push
    id="$(gh run list --workflow release-dmg.yml --branch "$tag" --limit 1 --json databaseId -q '.[0].databaseId' 2>/dev/null)"
    [ -n "$id" ] && [ "$id" != null ] && break
    sleep 10
  done
  if [ -z "$id" ] || [ "$id" = null ]; then bad "build: no workflow run appeared for $tag"; return 1; fi
  note "run $id: https://github.com/sankalpasawa/sutra/actions/runs/$id"
  if gh run watch "$id" --interval 30 --exit-status >/dev/null 2>&1; then ok "build: run $id succeeded"; return 0; fi
  bad "build: run $id did not succeed"; return 1
}

cmd_auto() {
  command -v gh >/dev/null 2>&1 || die "gh is required for --auto (it waits for the build and fetches the beta)"
  [ -x "$LIBDIR/beta-smoke.sh" ] || die "scripts/beta-smoke.sh is missing or not executable"
  ASSUME_YES=1
  head_ "AUTO 1/4: the beta"
  BETA=1; read_state
  local beta_tag="$TAG" version="$TARGET"
  cmd_release
  head_ "AUTO 2/4: the GitHub build of $beta_tag"
  _fails=0; wait_for_run "$beta_tag" || die "the build of $beta_tag did not succeed -- nothing promoted"
  _fails=0; cmd_verify "$beta_tag" || die "the beta release is incomplete -- nothing promoted"
  head_ "AUTO 3/4: the look, by script, on this Mac"
  "$LIBDIR/beta-smoke.sh" "$beta_tag" || die "the beta smoke FAILED -- the stable tag is not cut (D82)"
  head_ "AUTO 4/4: the stable tag for $version"
  BETA=0; _fails=0; read_state
  cmd_release
  note "production build started; verify with: scripts/release-desktop.sh verify $(tag_for "$version")"
}

cmd_verify() {
  local tag="${1:-}"
  [ -n "$tag" ] || { read_state; tag="$TAG"; [ -n "$(git tag -l "$tag")" ] || tag="$(tag_for "$CUR")"; }
  command -v gh >/dev/null 2>&1 || die "gh is not installed -- cannot verify the release. Install it, or check https://github.com/sankalpasawa/sutra/releases/tag/$tag by hand."
  head_ "RELEASE $tag"
  local assets
  assets="$(gh release view "$tag" --json assets --jq '.assets[].name' 2>/dev/null)" \
    || die "no GitHub release for $tag (the workflow may still be running, or it failed)"
  printf '%s\n' "$assets" | sed 's/^/  /'
  local miss; miss="$(missing_assets "$assets")"
  if [ -z "$miss" ]; then ok "all four assets present"
  else bad "missing:$miss -- a one-architecture release is not shippable"; fi
  local state; state="$(gh release view "$tag" --json isDraft,isPrerelease --jq '"draft=\(.isDraft) prerelease=\(.isPrerelease)"' 2>/dev/null)"
  note "$state"
  head_ "VERDICT"
  if [ "$_fails" = 0 ]; then
    printf '  \033[32mDMGs PUBLISHED\033[0m\n'
    note "Install:  https://github.com/sankalpasawa/sutra/releases/download/$tag/Sutra-arm64.dmg  (Apple Silicon)"
    note "          https://github.com/sankalpasawa/sutra/releases/download/$tag/Sutra-x86_64.dmg (Intel)"
    note "Latest:   https://github.com/sankalpasawa/sutra/releases/latest"
    note "NOT YET VERIFIED, and this script cannot do it: shasum -c, xcrun stapler validate,"
    note "and launching the app (release-checklist.md checks 3 and 7)."
    return 0
  fi
  printf '  \033[31mINCOMPLETE\033[0m -- the Mac app is NOT released\n'
  return 1
}

# =============================================================================
main() {
  local cmd="${1:-check}"; shift || true
  BUMP=patch; EXPLICIT=""; NOTES=""; ASSUME_YES=0; BETA=0; AUTO=0
  local rest=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --beta)    BETA=1; shift ;;
      --auto)    AUTO=1; BETA=1; ASSUME_YES=1; shift ;;
      --bump)    BUMP="${2:-}"; shift 2 ;;
      --version) EXPLICIT="${2:-}"; shift 2 ;;
      --notes)   NOTES="${2:-}"; shift 2 ;;
      --yes|-y)  ASSUME_YES=1; shift ;;
      -h|--help) sed -n '1,30p' "$0"; exit 0 ;;
      *)         rest="$rest $1"; shift ;;
    esac
  done
  [ -n "$NOTES" ] && [ ! -f "$NOTES" ] && die "--notes file not found: $NOTES"
  LIBDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cd "$(git rev-parse --show-toplevel 2>/dev/null)" || die "not inside a git repository"
  command -v jq >/dev/null 2>&1 || die "jq is required"
  command -v node >/dev/null 2>&1 || die "node is required"
  [ -f "$CHECKLIST" ] || die "release-checklist.md not found -- is this the sutra repo?"
  case "$cmd" in
    check)   cmd_check ;;
    release) if [ "${AUTO:-0}" = 1 ]; then cmd_auto; else cmd_release; fi ;;
    verify)  cmd_verify ${rest:-} ;;
    *) die "unknown command '$cmd' (want: check | release [--beta|--auto] | verify)" ;;
  esac
}

[ "${RELEASE_DESKTOP_LIB:-0}" = 1 ] || main "$@"
