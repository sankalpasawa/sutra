#!/bin/bash
# parse-manifest-registry.sh — Canonical parser for MANIFEST-v*.md Client registry
#
# Exposes one function: parse_manifest_registry <path_to_MANIFEST.md>
#
# Prints one client name per line (lowercased, whitespace-trimmed, blanks filtered).
#
# Why this exists:
#   Originally upgrade-clients.sh and verify-policy-coverage.sh each carried
#   their own registry resolver. upgrade-clients.sh used an awk range
#     /^## .*[Cc]lient [Rr]egistry/,/^## /
#   pinned to MANIFEST-v1.9.md. "Client registry (v1.9 targets)" is the LAST
#   `## ` heading in that file, so the range degenerated to the header row
#   alone — parsed registry was empty, and the hardcoded fallback
#   `REGISTRY=(dayflow maze ppr billu sutra)` silently took over. The
#   portfolio had 9 declared clients; only 5 ever got walked. Filed in
#   sutra/feedback/2026-04-17-sutra-to-holding-v1.9-propagation-gaps.md as
#   Bug 1. verify-policy-coverage.sh carried a matching hardcoded 5-element
#   array (Bug 2) that contradicted MANIFEST-as-source-of-truth.
#
# The fix is a state-machine awk that stays inside the registry section until
# it sees the NEXT `## ` heading OR EOF — surviving the case where the
# registry is the last section of the manifest. Both scripts now source this
# file so there is one canonical resolver.
#
# Usage (sourced):
#   source "$(dirname "$0")/lib/parse-manifest-registry.sh"
#   mapfile -t CLIENTS < <(parse_manifest_registry "$MANIFEST")
#
# Exit behavior: the function itself has no exit code contract beyond stdout.
# Callers MUST check array emptiness and fail loud — do NOT silently fall
# back to a hardcoded list.

parse_manifest_registry() {
  local manifest="$1"
  if [ -z "$manifest" ] || [ ! -f "$manifest" ]; then
    return 0
  fi
  # State machine: flip inreg=1 on the registry heading, flip off on the
  # next `## ` heading. Only emit rows that look like numbered table entries
  # (leading `| <digits>`) — header and separator rows skip.
  awk '/^## .*[Cc]lient [Rr]egistry/{inreg=1; next}
       inreg && /^## /{inreg=0}
       inreg && /^\| *[0-9]+/' "$manifest" \
    | awk -F'|' '{gsub(/^[ \t]+|[ \t]+$/,"",$3); print tolower($3)}' \
    | grep -vE '^(#|name)$' \
    | grep -v '^$'
}
