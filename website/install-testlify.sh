#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Sutra — Testlify onboarding installer (browser UI).
#
#   curl -fsSL https://sankalpasawa.github.io/sutra/install-testlify.sh | bash
#
# Thin fork of the public installer: runs the SAME install.sh with --ui, so the
# install ends by opening Sutra in the browser — no terminal needed. The public
# installer (install.sh) stays terminal-default and is NOT changed by this fork;
# this just flips the one opt-in flag for the Testlify cohort.
#
# Pass extra flags through, e.g.:
#   curl -fsSL .../install-testlify.sh | bash -s -- -d ~/work/foo
# -----------------------------------------------------------------------------
set -euo pipefail

BASE="${SUTRA_INSTALL_BASE:-https://sankalpasawa.github.io/sutra}"

# Fetch the canonical installer and run it with --ui prepended. `_` becomes $0;
# --ui and any extra args become the positional args install.sh's parse_args reads.
exec bash -c "$(curl -fsSL "${BASE}/install.sh")" _ --ui "$@"
