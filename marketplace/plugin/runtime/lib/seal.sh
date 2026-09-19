#!/bin/sh
# seal.sh - sealed runtime evidence (adherence row 6, brief s3.5, D-A14).
#
# The lane verdicts (<turn>.review.json, <turn>.tests.json) are written by the
# runtime, not by the model, but they live in a directory the model can write.
# A seal is an HMAC-SHA256 over the canonical JSON (keys sorted, seal removed)
# with a per-box key at ~/.sutra-runtime/seal.key (0600, created on first use;
# the path is runtime-owned, so no tool call may name or read it). A file with
# no seal, a wrong seal, or a seal the box cannot verify is NOT evidence.
#
# SECURITY-NOTE (brief s3.5, founder call 4; DeepSeek row-6 P1-2): this is
# NOT a security boundary on one shared box. The model runs shell commands on
# the same box as the key; R9 refuses every tool call that names the key dir
# (test-adherence case 15, test-gate-rules case 6), so a forgery needs an
# obfuscated read of the key plus an HMAC - a deliberate, ledgered act, never
# an accident. A box-external verifier is the only real seal; it is a separate
# program. What the seal does buy: a stray, stale or hand-edited verdict file
# is never evidence, and forging one leaves a refusal row.
#
# POSIX sh (sourced by the detached lane subshells and by bash steps). HOME
# unset (hermetic / corpus runs) -> no key, nothing signed, nothing verifies.
# openssl missing -> same: fail closed, never fail open.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/lib/seal.sh

sutra_seal_key() {
  [ -n "${HOME:-}" ] || return 1
  command -v openssl >/dev/null 2>&1 || return 1
  _sk_dir="$HOME/.sutra-runtime"; _sk_file="$_sk_dir/seal.key"
  if [ ! -s "$_sk_file" ]; then
    mkdir -p "$_sk_dir" 2>/dev/null || return 1
    ( umask 077; openssl rand -hex 32 > "$_sk_file" ) 2>/dev/null || return 1
    chmod 600 "$_sk_file" 2>/dev/null
  fi
  cat "$_sk_file" 2>/dev/null
}

# sutra_seal_sign <json-text> -> prints the hex HMAC of the canonical form
sutra_seal_sign() {
  _ss_key="$(sutra_seal_key)" || return 1
  [ -n "$_ss_key" ] || return 1
  _ss_canon="$(printf '%s' "$1" | jq -cS 'del(.seal)' 2>/dev/null)" || return 1
  [ -n "$_ss_canon" ] || return 1
  printf '%s' "$_ss_canon" | openssl dgst -sha256 -hmac "$_ss_key" 2>/dev/null | sed 's/^.*= *//'
}

# sutra_seal_file <file>: rewrite the file with its seal (atomic). Silent no-op
# when the box cannot sign; the file then simply never counts as evidence.
sutra_seal_file() {
  [ -f "$1" ] || return 1
  _sf_sig="$(sutra_seal_sign "$(cat "$1")")" || return 1
  [ -n "$_sf_sig" ] || return 1
  jq -c --arg s "$_sf_sig" '.seal = $s' "$1" > "$1.sealtmp" 2>/dev/null && mv -f "$1.sealtmp" "$1"
}

# sutra_seal_verify <file> -> 0 when the file carries a seal this box made
sutra_seal_verify() {
  [ -f "$1" ] || return 1
  _sv_have="$(jq -r '.seal // empty' "$1" 2>/dev/null)"
  [ -n "$_sv_have" ] || return 1
  _sv_want="$(sutra_seal_sign "$(cat "$1")")" || return 1
  [ -n "$_sv_want" ] && [ "$_sv_have" = "$_sv_want" ]
}
