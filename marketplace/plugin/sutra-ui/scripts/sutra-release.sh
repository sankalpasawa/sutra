#!/usr/bin/env bash
# sutra-release.sh -- the ONE way to cut a beta and to promote it to stable.
#
# It exists so the release footgun cannot recur: on two separate releases the
# manifests (plugin.json + marketplace.json core) were left out of step with the
# tag and the CI `guard` job rejected the build. This script bumps all three
# version files together, verifies them, and cuts the tag -- for everyone, the
# same way. Releases are still built by CI (release-dmg.yml on a v* tag); this
# only creates the tag, never a local DMG.
#
# The dev flow (see CONTRIBUTING.md):
#   1. On your feature branch:   ./sutra-release.sh beta
#        -> cuts vX.Y.Z-beta.N-desktop  (prerelease; builds the coexisting
#           "Sutra Beta" app). Install that DMG to verify the flow.
#   2. Good?  Open a PR, get it merged to main.
#   3. On main, at the merge commit:   ./sutra-release.sh promote
#        -> bumps the manifests to X.Y.Z, commits, and cuts vX.Y.Z-desktop
#           (stable). CI publishes it as latest; every app auto-updates on its
#           next restart, and your local is already on main.
#
# NEVER build or install a local desktop bundle to test -- cut a beta instead.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UI="$(cd "$HERE/.." && pwd)"                     # marketplace/plugin/sutra-ui
ROOT="$(cd "$UI/../../.." && pwd)"               # repo root
PLUGIN_JSON="$ROOT/marketplace/plugin/.claude-plugin/plugin.json"
MARKET_JSON="$ROOT/.claude-plugin/marketplace.json"
CURRENT_MD="$ROOT/CURRENT-VERSION.md"

die(){ printf 'sutra-release: %s\n' "$*" >&2; exit 1; }
have(){ command -v "$1" >/dev/null 2>&1 || die "need '$1' on PATH"; }
have jq; have git

base_version(){ jq -r '.version' "$PLUGIN_JSON"; }
market_version(){ jq -r '.plugins[] | select(.name=="core") | .version' "$MARKET_JSON"; }

# Manifests must already agree with each other; the guard compares BOTH to the tag.
manifests_agree(){ [ "$(base_version)" = "$(market_version)" ]; }

set_version(){                                   # $1 = new X.Y.Z
  local v="$1" tmp
  tmp="$(mktemp)"; jq --arg v "$v" '.version=$v' "$PLUGIN_JSON" > "$tmp" && mv "$tmp" "$PLUGIN_JSON"
  tmp="$(mktemp)"; jq --arg v "$v" '(.plugins[] | select(.name=="core") | .version) |= $v' "$MARKET_JSON" > "$tmp" && mv "$tmp" "$MARKET_JSON"
}

clean_tree(){ [ -z "$(git -C "$ROOT" status --porcelain --untracked-files=no)" ]; }

next_beta_n(){                                   # highest existing beta.N for a base +1
  local base="$1" n=0 t
  git -C "$ROOT" fetch -q origin --tags 2>/dev/null || true
  for t in $(git -C "$ROOT" tag -l "v${base}-beta.*-desktop"); do
    local this="${t#v${base}-beta.}"; this="${this%-desktop}"
    case "$this" in ''|*[!0-9]*) continue ;; esac
    [ "$this" -gt "$n" ] && n="$this"
  done
  echo $((n + 1))
}

cmd="${1:-}"
case "$cmd" in
  beta)
    manifests_agree || die "plugin.json ($(base_version)) and marketplace.json ($(market_version)) disagree -- fix before cutting a beta"
    clean_tree || die "commit or stash your changes first (a beta is built from a pushed branch commit)"
    branch="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)"
    [ "$branch" != "main" ] || die "cut betas from a feature branch, not main"
    base="$(base_version)"
    n="$(next_beta_n "$base")"
    tag="v${base}-beta.${n}-desktop"
    echo "Cutting BETA $tag from $branch (base $base)."
    git -C "$ROOT" push -q origin "HEAD:$branch"
    git -C "$ROOT" tag -a "$tag" -m "$base beta.$n" HEAD
    git -C "$ROOT" push origin "$tag"
    echo "Pushed $tag -> CI builds the coexisting 'Sutra Beta' app (prerelease)."
    echo "Watch:  gh run list --repo sankalpasawa/sutra --workflow release-dmg.yml"
    ;;
  promote)
    [ "$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)" = "main" ] || die "promote from main (merge your PR first)"
    git -C "$ROOT" fetch -q origin
    [ "$(git -C "$ROOT" rev-parse HEAD)" = "$(git -C "$ROOT" rev-parse origin/main)" ] || die "local main is not level with origin/main -- pull first"
    target="${2:-$(base_version)}"
    case "$target" in [0-9]*.[0-9]*.[0-9]*) ;; *) die "give a version: ./sutra-release.sh promote X.Y.Z" ;; esac
    tag="v${target}-desktop"
    git -C "$ROOT" rev-parse "$tag" >/dev/null 2>&1 && die "$tag already exists"
    if [ "$(base_version)" != "$target" ] || [ "$(market_version)" != "$target" ]; then
      echo "Bumping manifests -> $target"
      set_version "$target"
      git -C "$ROOT" add "$PLUGIN_JSON" "$MARKET_JSON" "$CURRENT_MD" 2>/dev/null || git -C "$ROOT" add "$PLUGIN_JSON" "$MARKET_JSON"
      git -C "$ROOT" commit -q -m "$target: bump manifests for release"
      git -C "$ROOT" push -q origin main
    fi
    manifests_agree || die "manifests still disagree after bump -- refusing to tag"
    git -C "$ROOT" tag -a "$tag" -m "$target" HEAD
    git -C "$ROOT" push origin "$tag"
    echo "Pushed $tag -> CI publishes it as the latest stable release."
    ;;
  *)
    cat >&2 <<EOF
usage:
  ./sutra-release.sh beta                 # from a feature branch: cut vX.Y.Z-beta.N-desktop
  ./sutra-release.sh promote [X.Y.Z]      # from main: bump manifests + cut vX.Y.Z-desktop (stable)

current base version (plugin.json): $(base_version 2>/dev/null || echo '?')
EOF
    exit 2 ;;
esac
