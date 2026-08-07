#!/usr/bin/env bash
# notarize-setup.sh -- get this machine ready to ship a NOTARIZED Sutra.dmg.
#
# THE PROBLEM THIS SOLVES
# -----------------------
# A downloaded, ad-hoc-signed app is refused by Gatekeeper on every Mac but the
# one that built it:
#
#     "Sutra" Not Opened
#     Apple could not verify "Sutra" is free of malware that may harm your Mac
#     or compromise your privacy.                    [ Done ]  [ Move to Bin ]
#
# Note the buttons: on current macOS there is no "Open Anyway" in that dialog.
# The only cures are (a) the user digging into System Settings > Privacy &
# Security, or (b) NOTARIZATION. (b) is the product answer.
#
# WHAT NOTARIZATION ACTUALLY REQUIRES -- all three, no substitutes:
#
#   1. A PAID Apple Developer Program membership ($99/yr).
#      An "Apple Development" certificate is NOT enough and never becomes
#      enough: it is a development identity. It cannot be notarized, and
#      Gatekeeper rejects it off the build machine. This machine has exactly
#      that and nothing else, which is why the DMG is blocked.
#
#   2. A "Developer ID Application" certificate in the login keychain.
#      This is the distribution identity. It is what makes the code
#      requirement stable across rebuilds (which also fixes the TCC re-prompt
#      that made chat hang -- see install.sh).
#
#   3. notarytool credentials, stored as a keychain profile.
#
# THIS SCRIPT NEVER HANDLES YOUR SECRETS. `notarytool store-credentials`
# prompts for them itself and writes them to your login keychain; nothing is
# echoed, logged, or written into the repo. Steps 1 and 2 happen in a browser
# and in Keychain Access, and the script tells you exactly what to click rather
# than pretending it can do them for you.
#
# Usage:
#   ./notarize-setup.sh            # check what is present and what is missing
#   ./notarize-setup.sh --store    # run the interactive credential setup
#   ./notarize-setup.sh --verify   # prove the stored credentials work
set -uo pipefail

PROFILE="${SUTRA_NOTARY_PROFILE:-sutra}"
ok()   { printf '  \033[32mok\033[0m    %s\n' "$*"; }
bad()  { printf '  \033[31mMISSING\033[0m %s\n' "$*"; }
info() { printf '        %s\n' "$*"; }
head_() { printf '\n\033[1m%s\033[0m\n' "$*"; }

DEV_ID="$(security find-identity -v -p codesigning 2>/dev/null \
  | sed -n 's/.*"\(Developer ID Application: [^"]*\)".*/\1/p' | head -1)"
APP_DEV="$(security find-identity -v -p codesigning 2>/dev/null \
  | sed -n 's/.*"\(Apple Development: [^"]*\)".*/\1/p' | head -1)"
TEAM="$(printf '%s' "${DEV_ID:-$APP_DEV}" | sed -n 's/.*(\([A-Z0-9]\{10\}\)).*/\1/p')"

case "${1:-}" in
--store)
  head_ "storing notarytool credentials"
  if [ -z "$DEV_ID" ]; then
    echo "Refusing: there is no Developer ID Application certificate yet."
    echo "Credentials without a distribution certificate cannot notarize anything."
    echo "Run this script with no arguments for the steps."
    exit 2
  fi
  echo "notarytool will now prompt you. Two supported answers:"
  echo
  echo "  A) App Store Connect API key (recommended -- no password, revocable):"
  echo "       Issuer ID  and  Key ID  from appstoreconnect.apple.com > Users and"
  echo "       Access > Integrations > App Store Connect API, plus the .p8 file."
  echo
  echo "  B) Apple ID + an APP-SPECIFIC password from appleid.apple.com"
  echo "     (never your real Apple ID password), plus Team ID ${TEAM:-<team>}."
  echo
  echo "Nothing you type is visible to this script; notarytool writes it straight"
  echo "into your login keychain under the profile name '$PROFILE'."
  echo
  exec xcrun notarytool store-credentials "$PROFILE"
  ;;
--verify)
  head_ "verifying stored credentials"
  if xcrun notarytool history --keychain-profile "$PROFILE" >/dev/null 2>&1; then
    ok "profile '$PROFILE' works -- Apple accepted the credentials"
    xcrun notarytool history --keychain-profile "$PROFILE" 2>/dev/null | head -12
    echo
    echo "You are ready. Build a notarized DMG with:"
    echo "    SUTRA_NOTARY_PROFILE=$PROFILE ./make-dmg.sh"
    exit 0
  fi
  bad "profile '$PROFILE' does not authenticate"
  info "re-run: ./notarize-setup.sh --store"
  exit 1
  ;;
esac

# ---------------------------------------------------------------- status ----
head_ "what this machine has"
[ -n "$APP_DEV" ] && ok "Apple Development certificate  ($APP_DEV)" \
                 || bad "Apple Development certificate"
if [ -n "$DEV_ID" ]; then
  ok "Developer ID Application certificate  ($DEV_ID)"
else
  bad "Developer ID Application certificate   <-- THE BLOCKER"
  info "This is the distribution identity. Without it the DMG can only ever be"
  info "ad-hoc signed, and every downloader sees \"Apple could not verify\"."
fi
if xcrun notarytool history --keychain-profile "$PROFILE" >/dev/null 2>&1; then
  ok "notarytool credentials (profile '$PROFILE')"
else
  bad "notarytool credentials (profile '$PROFILE')"
fi
[ -n "$TEAM" ] && info "team identifier: $TEAM"

if [ -n "$DEV_ID" ] && xcrun notarytool history --keychain-profile "$PROFILE" >/dev/null 2>&1; then
  head_ "ready"
  echo "    SUTRA_NOTARY_PROFILE=$PROFILE ./make-dmg.sh"
  echo
  echo "make-dmg.sh will sign with the Developer ID, submit to Apple, wait, and"
  echo "staple the ticket. The result opens with a normal double-click anywhere."
  exit 0
fi

# ------------------------------------------------------------- what to do ---
head_ "what to do, in order"
cat <<'STEPS'
  1. CONFIRM THE MEMBERSHIP IS PAID.
       https://developer.apple.com/account  ->  Membership
     "Apple Developer Program" with an expiry date = paid, you can continue.
     If it offers to ENROLL, the account is a free one: Developer ID
     certificates are not available on free accounts, and no amount of local
     configuration substitutes. Enrolment is $99/yr and takes 24-48h to
     approve.

  2. CREATE THE DEVELOPER ID APPLICATION CERTIFICATE.
       https://developer.apple.com/account/resources/certificates/list
       "+"  ->  Software  ->  "Developer ID Application"  ->  Continue
     It asks for a Certificate Signing Request. Make one locally:
       Keychain Access  ->  menu Keychain Access  ->  Certificate Assistant
       ->  Request a Certificate From a Certificate Authority
       email: your Apple ID   |   Common Name: anything   |   Saved to disk
     Upload the .certSigningRequest, download the .cer, double-click to install.
     Then re-run this script -- it should show the certificate as present.

  3. CREATE NOTARYTOOL CREDENTIALS.
       ./notarize-setup.sh --store
     Prefer an App Store Connect API key over an Apple ID password: it is
     revocable on its own and is not your account password.

  4. VERIFY, THEN BUILD.
       ./notarize-setup.sh --verify
       SUTRA_NOTARY_PROFILE=sutra ./make-dmg.sh
STEPS

head_ "meanwhile, for anyone who already downloaded the blocked DMG"
cat <<'WORKAROUND'
  The dialog with [Done] [Move to Bin] has no "Open Anyway". Either:
      System Settings > Privacy & Security > scroll down > "Open Anyway"
  or, in a terminal:
      xattr -d com.apple.quarantine /Applications/Sutra.app
  Both are one-time, per machine. Neither is a substitute for notarizing, and
  neither should appear in download instructions aimed at a normal user.
WORKAROUND
