'use strict';
/* The desktop app updating itself (gap package autoupdate, D34's sibling: Sutra Pro's own app, never the provider CLIs). Everything here is a pure
   function or takes its input and output as arguments, so `node --test` runs it on every system without Electron, a network or a signed app.

   WHAT HAPPENS, IN ORDER (the page has no part in it: the dialogs are Electron's own and the app talks to the local server like the window does)
     1. A timer (a minute after launch, then every 6 hours) asks the local server for a plan: POST /api/ops/update-plan. The server makes the ONE
        request, to GitHub's list of releases, and reads versions, channels and assets (ops/update_check.py is the only implementation of that).
     2. The answer is untrusted text. planFromAnswer() accepts it only if every field has exactly the expected shape; the download address is
        built here from the version and a fixed asset name and must equal what the server said, so no text from the feed ever becomes a path or an
        argument. A copy of the app that cannot tell who signed it (ad hoc, unsigned, a source checkout) only TELLS: it never downloads or installs.
     3. The asset and its .sha256 are downloaded into <data>/updates/<version>/ (HTTPS, GitHub hosts only, at most 1 GiB, a part file renamed when
        complete), hashed through ONE open handle, and verified: macOS mounts the DMG read-only and checks the app's seal, Team Identifier, bundle
        id, version and Gatekeeper verdict against the RUNNING app; Windows checks the installer's Authenticode signature and its publisher.
        Anything that fails is deleted.
     4. A dialog asks: Restart Now, Install on Quit, or Later. Only the first two touch anything, and only after the app's own quit path has
        stopped its server: macOS runs a small constant script that swaps the bundle and rolls back if the new app does not answer, Windows runs the
        verified installer (per user, no prompt). The data folder is never touched.

   A step that fails leaves the installed app exactly as it was, and says so in one sentence. */
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const REPO = 'sankalpasawa/sutra';
const RELEASES_PAGE = `https://github.com/${REPO}/releases?q=sutra-pro`;
const APP_BUNDLE_NAME = 'Sutra Pro.app';
const ASSET_NAMES = Object.freeze({ 'darwin/arm64': 'Sutra-Pro-arm64.dmg', 'darwin/x64': 'Sutra-Pro-x86_64.dmg', 'win32/x64': 'Sutra-Pro-Setup-x64.exe' });
const MAX_DOWNLOAD_BYTES = 1024 * 1024 * 1024;           // 1 GiB
const MAX_CHECKSUM_BYTES = 4096;
const MAX_REDIRECTS = 5;
const FIRST_CHECK_MS = 60 * 1000;
const EVERY_MS = 6 * 60 * 60 * 1000;
const KEEP_VERSIONS = 2;
const HELPER_WAIT_S = 90;                                // how long the macOS helper waits for the new app to answer before it puts the old one back
const USER_AGENT = 'sutra-pro-update';

const CODESIGN = '/usr/bin/codesign';
const SPCTL = '/usr/sbin/spctl';
const HDIUTIL = '/usr/bin/hdiutil';
const DITTO = '/usr/bin/ditto';
const PLUTIL = '/usr/bin/plutil';

class UpdateError extends Error {
  constructor(code, sentence) {
    super(sentence);
    this.name = 'UpdateError';
    this.code = code;
    this.sentence = sentence;
  }
}

// control characters and the two line separators, written as escapes in a string so no raw separator sits in this file
const CONTROL = new RegExp('[\\u0000-\\u001f\\u007f-\\u009f\\u2028\\u2029]+', 'g');

/* One plain line from any text: control characters gone, runs of white space folded, cut at `max`. */
function cleanSentence(value, max = 240) {
  return String(value === undefined || value === null ? '' : value).replace(CONTROL, ' ').replace(/\s+/g, ' ').trim().slice(0, max);
}

function parseBool(value) {
  return ['1', 'true', 'yes', 'on'].includes(String(value === undefined || value === null ? '' : value).trim().toLowerCase());
}

// ---------------------------------------------------------------- versions (the server's rules, kept as a safety net: nothing is installed unless it is strictly newer)

const NUM = '(?:0|[1-9][0-9]{0,8})';                      // at most 9 digits, like ops/update_check.py
const STRICT_VERSION = new RegExp(`^(${NUM})\\.(${NUM})\\.(${NUM})(?:-beta\\.(${NUM}))?$`);
const LOOSE_VERSION = new RegExp(`^(${NUM})\\.(${NUM})\\.(${NUM})(?:(?:-beta\\.|b)(${NUM}))?$`);     // the running app may spell a beta the PEP 440 way

/* "0.2.0" or "0.2.0-beta.1" -> { major, minor, patch, beta, text }, else null. `loose` also reads 0.2.0b1. */
function parseVersion(text, { loose = false } = {}) {
  if (typeof text !== 'string' || text.length > 40) return null;
  const found = (loose ? LOOSE_VERSION : STRICT_VERSION).exec(text);
  if (!found) return null;
  const beta = found[4] === undefined ? null : Number(found[4]);
  const stable = `${found[1]}.${found[2]}.${found[3]}`;
  return { major: Number(found[1]), minor: Number(found[2]), patch: Number(found[3]), beta, text: beta === null ? stable : `${stable}-beta.${beta}` };
}

/* -1, 0 or 1. A beta is older than its own stable release. */
function compareVersions(a, b) {
  for (const key of ['major', 'minor', 'patch']) {
    if (a[key] !== b[key]) return a[key] < b[key] ? -1 : 1;
  }
  const rank = (v) => (v.beta === null ? Number.POSITIVE_INFINITY : v.beta);
  if (rank(a) === rank(b)) return 0;
  return rank(a) < rank(b) ? -1 : 1;
}

/* A stable install is offered stables only; a beta install is offered betas and stables. */
function channelAllows(running, candidate) {
  return candidate.beta === null || running.beta !== null;
}

// ---------------------------------------------------------------- addresses

function assetFor(platform, arch) {
  return ASSET_NAMES[`${platform}/${arch}`] || null;
}

function downloadUrl(version, name) {
  return `https://github.com/${REPO}/releases/download/sutra-pro-v${version}/${name}`;
}

/* GitHub serves a release asset from github.com, which redirects to a githubusercontent.com host. Nothing else is followed. */
function isAllowedHost(hostname) {
  const host = String(hostname || '').toLowerCase();
  return host === 'github.com' || host === 'githubusercontent.com' || host.endsWith('.githubusercontent.com');
}

function isAllowedUrl(text) {
  let url;
  try {
    url = new URL(text);
  } catch {
    return false;
  }
  return url.protocol === 'https:' && !url.username && !url.password && (url.port === '' || url.port === '443') && isAllowedHost(url.hostname);
}

const SAFE_PAGE = /^https:\/\/github\.com\/[A-Za-z0-9._~%/+@:=,;&?#-]{0,300}$/;
function safeReleasePage(url) {
  return typeof url === 'string' && SAFE_PAGE.test(url) ? url : RELEASES_PAGE;
}

// ---------------------------------------------------------------- the server's answer

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);

/* The answer of POST /api/ops/update-plan, judged. Returns
     { ok: true, version, notesUrl, asset: { name, url, size, sha256Url } }                 an update to download
     { ok: false, kind: 'current' }                                                         nothing newer
     { ok: false, kind: 'tell', version, notesUrl, why }                                    newer, but this computer has no automatic download
     { ok: false, kind: 'error', sentence }                                                 the server could not ask, or the answer is not believable */
function planFromAnswer(answer, { running, platform, arch }) {
  const bad = (sentence) => ({ ok: false, kind: 'error', sentence });
  if (!isObject(answer)) return bad('The answer of the update check could not be read.');
  if (typeof answer.error === 'string' && answer.error !== '') return bad(cleanSentence(answer.error));
  if (answer.newer !== true) return { ok: false, kind: 'current' };
  const have = typeof running === 'string' ? parseVersion(running, { loose: true }) : running;
  const latest = parseVersion(answer.latest);
  if (!have || !latest) return bad('The answer of the update check had a version that could not be read.');
  if (compareVersions(latest, have) <= 0 || !channelAllows(have, latest)) return bad('The answer of the update check did not agree with the installed version, so it was ignored.');
  const notesUrl = safeReleasePage(answer.notes_url);
  const name = assetFor(platform, arch);
  if (!name) return { ok: false, kind: 'tell', version: latest.text, notesUrl, why: 'There is no automatic update for this kind of computer.' };
  const asset = answer.asset;
  const url = downloadUrl(latest.text, name);
  if (answer.tag !== `sutra-pro-v${latest.text}` || !isObject(asset) || asset.name !== name || asset.url !== url || asset.sha256_url !== `${url}.sha256`
    || !Number.isSafeInteger(asset.size) || asset.size < 1 || asset.size > MAX_DOWNLOAD_BYTES || !isAllowedUrl(asset.url) || !isAllowedUrl(asset.sha256_url)) {
    return bad('The download that the update check named did not look right, so nothing was downloaded.');
  }
  return { ok: true, version: latest.text, notesUrl, asset: { name, url, size: asset.size, sha256Url: asset.sha256_url } };
}

/* A published <hex>  <name> line (shasum / sha256sum), for exactly this asset; null for anything else. */
function parseChecksum(text, name) {
  if (typeof text !== 'string' || text.length > MAX_CHECKSUM_BYTES) return null;
  const line = text.split(/\r?\n/).find((l) => l.trim() !== '');
  const found = line ? /^([0-9a-fA-F]{64}) [ *]([^\r\n]+)$/.exec(line.trim()) : null;
  return found && found[2] === name ? found[1].toLowerCase() : null;
}

// ---------------------------------------------------------------- where things are

/* <data>/updates/<version>/ and the files in it. A version or an asset name that is not one of ours throws: no text from outside becomes a path. */
function stagingPaths(dataDir, version, name) {
  if (!parseVersion(version) || !Object.values(ASSET_NAMES).includes(name)) throw new Error('not a staging name of ours');
  const root = path.join(dataDir, 'updates');
  const dir = path.join(root, version);
  const file = path.join(dir, name);
  return { root, dir, file, part: `${file}.part`, sum: `${file}.sha256`, app: path.join(dir, APP_BUNDLE_NAME) };
}

/* "/Applications/Sutra Pro.app/Contents/MacOS/Sutra Pro" -> "/Applications/Sutra Pro.app", else null. */
function bundleOf(execPath) {
  const text = String(execPath || '').replace(/\\/g, '/');
  const at = text.lastIndexOf(`/${APP_BUNDLE_NAME}/Contents/MacOS/`);
  if (at < 0 || text.slice(at + `/${APP_BUNDLE_NAME}/Contents/MacOS/`.length).includes('/')) return null;
  return String(execPath).slice(0, at + 1 + APP_BUNDLE_NAME.length);
}

function installPaths(bundle) {
  return { app: bundle, dir: path.dirname(bundle), newApp: `${bundle}.new`, oldApp: `${bundle}.old`, badApp: `${bundle}.bad` };
}

// ---------------------------------------------------------------- the commands (always a file and an argument list, never a shell string)

const macAttachArgs = (dmg, mountpoint) => ['attach', '-nobrowse', '-readonly', '-noverify', '-noautoopen', '-mountpoint', mountpoint, dmg];
const macDetachArgs = (mountpoint, force) => ['detach', mountpoint, ...(force ? ['-force'] : [])];
const codesignVerifyArgs = (app) => ['--verify', '--deep', '--strict', app];
const codesignDisplayArgs = (app) => ['-dv', '--verbose=2', app];
const spctlArgs = (app) => ['--assess', '--type', 'execute', app];
const dittoArgs = (from, to) => [from, to];
const plistArgs = (plist, key) => ['-extract', key, 'raw', '-o', '-', plist];

/* Windows: Get-AuthenticodeSignature. The script text is a constant; the file to look at reaches it through the environment (SUTRA_PRO_VERIFY_PATH),
   so no path is ever part of a command line that PowerShell parses. */
const WIN_SIGNATURE_SCRIPT = '$ErrorActionPreference = \'Stop\'; $s = Get-AuthenticodeSignature -LiteralPath $env:SUTRA_PRO_VERIFY_PATH; '
  + '$c = $s.SignerCertificate; ConvertTo-Json -Compress -InputObject @{ status = [string]$s.Status; subject = $(if ($c) { $c.Subject } else { \'\' }) }';

function powershellPath(env = process.env) {
  const root = env.SystemRoot || env.SYSTEMROOT || '';
  return root ? path.win32.join(root, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe') : 'powershell.exe';
}

function winSignatureCommand(env = process.env) {
  return { file: powershellPath(env), args: ['-NoProfile', '-NonInteractive', '-Command', WIN_SIGNATURE_SCRIPT], envName: 'SUTRA_PRO_VERIFY_PATH' };
}

/* The installer's real switches (scripts/windows/sutra-pro-desktop.iss): per user (PrivilegesRequired=lowest), so no prompt appears. /SILENT shows only
   a progress window; /CLOSEAPPLICATIONS and /RESTARTAPPLICATIONS are the installer's own Restart Manager switches; /NORESTART never reboots the computer;
   /SutraRelaunch=1 is read by the installer's [Run] section to start the app again (the app has already quit, so there is nothing for the Restart
   Manager to restart). */
function winInstallerArgs() {
  return ['/SILENT', '/CLOSEAPPLICATIONS', '/RESTARTAPPLICATIONS', '/NORESTART', '/SP-', '/SutraRelaunch=1'];
}

/* The macOS helper's arguments: the script, then the process number of this app, the installed app, its three neighbours, the data folder, the log and
   the seconds to wait for the new app. Each is one argument, so a path with spaces stays one path. */
function macHelperArgs({ script, pid, app, newApp, oldApp, badApp, dataDir, logFile, waitSeconds = HELPER_WAIT_S }) {
  return [script, String(pid), app, newApp, oldApp, badApp, dataDir, logFile, String(waitSeconds)];
}

/* The macOS swap helper. A CONSTANT: nothing is interpolated into it, no text from the feed or the owner is in it, and every path it uses arrives as an
   argument and is used only inside double quotes. It refuses anything but <app>.new / .old / .bad beside an app named Sutra Pro.app. It waits for the app
   (and the server the app started) to be gone, moves the old app aside, moves the new one in, starts it, and removes the old one only after the new one
   answered /api/health. If anything fails it puts the old one back. */
const MAC_SWAP_SCRIPT = String.raw`#!/bin/sh
# Sutra Pro update helper (macOS). Written by the app and run detached after the app has quit. It holds no text from the update feed or from the owner:
# every path arrives as an argument and is used only inside double quotes.
#   apply-update.sh <app pid> <installed app> <new app> <old app> <bad app> <data folder> <log file> <seconds to wait for the new app>
PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PATH
pid="$1"; app="$2"; new="$3"; old="$4"; bad="$5"; data="$6"; log="$7"; limit="$8"

say() { printf '%s desktop: update helper: %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$1" >> "$log" 2>/dev/null; }
die() { say "$1"; case "$2" in 2) exit 2 ;; *) exit 1 ;; esac; }

case "$pid" in ''|*[!0-9]*) die "the process number is not a number: nothing was changed" 2 ;; esac
case "$limit" in ''|*[!0-9]*) limit=90 ;; esac
for p in "$app" "$new" "$old" "$bad" "$data" "$log"; do
  case "$p" in /*) ;; *) die "a path is not absolute: nothing was changed" 2 ;; esac
done
[ "$(basename "$app")" = "Sutra Pro.app" ] || die "the installed app is not named Sutra Pro.app: nothing was changed" 2
{ [ "$new" = "$app.new" ] && [ "$old" = "$app.old" ] && [ "$bad" = "$app.bad" ]; } || die "the staging names do not belong to the installed app: nothing was changed" 2

spid="$(head -n 1 "$data/app.pid" 2>/dev/null | cut -d' ' -f1)"
case "$spid" in ''|*[!0-9]*) spid="" ;; esac

n=0
while kill -0 "$pid" 2>/dev/null; do
  n=$((n + 1))
  [ "$n" -le 600 ] || { rm -rf "$new"; die "Sutra Pro did not quit within two minutes: the installed app was not touched"; }
  sleep 0.2
done
n=0
while [ -n "$spid" ] && [ "$n" -lt 50 ] && kill -0 "$spid" 2>/dev/null; do n=$((n + 1)); sleep 0.2; done
say "Sutra Pro has quit"

mine() {
  real="$(cd "$app" 2>/dev/null && pwd -P)"
  ps -axww -o pid=,command= | while read -r p c; do
    case "$c" in "$app/Contents/MacOS/"*) echo "$p" ;; esac
    [ -n "$real" ] && case "$c" in "$real/Contents/MacOS/"*) echo "$p" ;; esac
  done
}
healthy() {
  port="$(head -n 1 "$data/app.pid" 2>/dev/null | cut -d' ' -f2)"
  case "$port" in ''|*[!0-9]*) return 1 ;; esac
  curl -fsS --max-time 2 --noproxy '*' "http://127.0.0.1:$port/api/health" 2>/dev/null | grep -Eq '"ok"[[:space:]]*:[[:space:]]*true'
}
back() {
  for p in $(mine); do kill "$p" 2>/dev/null; done
  n=0
  while [ -n "$(mine)" ] && [ "$n" -lt 20 ]; do n=$((n + 1)); sleep 0.5; done
  for p in $(mine); do kill -9 "$p" 2>/dev/null; done
  [ -e "$app" ] && mv "$app" "$bad" 2>/dev/null
  if mv "$old" "$app"; then
    say "the old app is back"
    rm -rf "$bad"
    open "$app"
  else
    say "the old app could not be put back: it is still beside the app with the name ending in .old"
  fi
}

[ -d "$new" ] || die "the staged copy is gone: nothing was changed"
rm -rf "$old" "$bad"
if ! mv "$app" "$old"; then
  rm -rf "$new"
  open "$app"
  die "could not move the installed app aside: nothing was changed"
fi
if ! mv "$new" "$app"; then
  mv "$old" "$app"
  rm -rf "$new"
  open "$app"
  die "could not move the new app into place: the old one is back"
fi
say "the new app is in place: starting it"
open "$app" || say "the system could not start the new app"
n=0
while [ "$n" -lt "$limit" ]; do
  if healthy; then
    rm -rf "$old"
    say "the new app answered: the old one is removed and the update is done"
    exit 0
  fi
  n=$((n + 1))
  sleep 1
done
say "the new app did not answer within $limit seconds: putting the old one back"
back
exit 1
`;

function macSwapScript() {
  return MAC_SWAP_SCRIPT;
}

// ---------------------------------------------------------------- what a command printed

/* `codesign -dv` writes to standard error: Identifier=..., TeamIdentifier=ABCDE12345 or "not set", Signature=adhoc for an ad hoc seal. */
function parseCodesignDisplay(text) {
  const own = String(text || '');
  const pick = (key) => {
    const found = new RegExp(`^${key}=(.*)$`, 'm').exec(own);
    return found ? found[1].trim() : '';
  };
  const team = pick('TeamIdentifier');
  return {
    identifier: pick('Identifier'), teamId: /^[A-Z0-9]{10}$/.test(team) ? team : null,
    adhoc: pick('Signature') === 'adhoc' || /^CodeDirectory .*flags=0x[0-9a-f]+\(.*adhoc/m.test(own),
  };
}

/* The one JSON line of WIN_SIGNATURE_SCRIPT -> { valid, subject }. */
function parseWinSignature(stdout) {
  const line = String(stdout || '').split(/\r?\n/).map((l) => l.trim()).filter(Boolean).pop() || '';
  try {
    const parsed = JSON.parse(line);
    return { valid: parsed.status === 'Valid' && typeof parsed.subject === 'string' && parsed.subject !== '', subject: typeof parsed.subject === 'string' ? parsed.subject : '' };
  } catch {
    return { valid: false, subject: '' };
  }
}

// ---------------------------------------------------------------- files

/* Hash a file through ONE open handle (no second look at the path between reading and the answer); a link is refused. */
async function hashFile(file) {
  const flags = fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW || 0);
  const handle = await fs.promises.open(file, flags);
  try {
    const stat = await handle.stat();
    if (!stat.isFile()) throw new UpdateError('file', 'The downloaded file is not a regular file.');
    const hash = crypto.createHash('sha256');
    let bytes = 0;
    const buffer = Buffer.allocUnsafe(1 << 20);
    for (;;) {
      const { bytesRead } = await handle.read(buffer, 0, buffer.length, null);
      if (bytesRead === 0) break;
      hash.update(buffer.subarray(0, bytesRead));
      bytes += bytesRead;
    }
    return { sha256: hash.digest('hex'), size: bytes };
  } finally {
    await handle.close();
  }
}

const REDIRECTS = new Set([301, 302, 303, 307, 308]);

/* GET `url`, following redirects only to allowed https hosts. `get(url) -> Promise<{ status, headers, stream }>` is the transport. The 200 response. */
async function openFollowing(get, url, maxRedirects = MAX_REDIRECTS) {
  let current = url;
  for (let hop = 0; ; hop += 1) {
    if (!isAllowedUrl(current)) throw new UpdateError('host', 'The update points somewhere that is not GitHub, so it was not downloaded.');
    const response = await get(current);
    if (REDIRECTS.has(response.status)) {
      if (response.stream && typeof response.stream.destroy === 'function') response.stream.destroy();
      const where = response.headers && response.headers.location;
      if (hop >= maxRedirects || typeof where !== 'string') throw new UpdateError('redirect', 'GitHub redirected the download too many times.');
      try {
        current = new URL(where, current).toString();
      } catch {
        throw new UpdateError('redirect', 'GitHub sent a download address that could not be read.');
      }
      continue;
    }
    if (response.status !== 200) {
      if (response.stream && typeof response.stream.destroy === 'function') response.stream.destroy();
      throw new UpdateError('http', `GitHub answered ${response.status} for the download.`);
    }
    return response;
  }
}

/* The small checksum file as text, never more than `limit` bytes. */
async function fetchSmall(get, url, limit = MAX_CHECKSUM_BYTES) {
  const response = await openFollowing(get, url);
  const chunks = [];
  let total = 0;
  try {
    for await (const chunk of response.stream) {
      total += chunk.length;
      if (total > limit) throw new UpdateError('size', 'The checksum file was larger than expected.');
      chunks.push(chunk);
    }
  } catch (error) {
    if (response.stream && typeof response.stream.destroy === 'function') response.stream.destroy();
    throw error;
  }
  return Buffer.concat(chunks).toString('utf8');
}

/* Download `url` to `dest` (a .part path): at most min(maxBytes, expectBytes) bytes, exactly expectBytes when it is given. A file that goes wrong is deleted. */
async function downloadTo({ get, url, dest, maxBytes = MAX_DOWNLOAD_BYTES, expectBytes = null }) {
  const response = await openFollowing(get, url);
  const cap = Math.min(maxBytes, expectBytes === null ? maxBytes : expectBytes);
  const declared = Number(response.headers && response.headers['content-length']);
  if (Number.isFinite(declared) && declared > cap) {
    if (response.stream && typeof response.stream.destroy === 'function') response.stream.destroy();
    throw new UpdateError('size', 'The download is larger than it should be, so it was stopped.');
  }
  let handle = null;
  let bytes = 0;
  try {
    handle = await fs.promises.open(dest, 'w', 0o600);
    for await (const chunk of response.stream) {
      bytes += chunk.length;
      if (bytes > cap) throw new UpdateError('size', 'The download is larger than it should be, so it was stopped.');
      await handle.write(chunk);
    }
    await handle.sync();
    await handle.close();
    handle = null;
    if (expectBytes !== null && bytes !== expectBytes) throw new UpdateError('size', 'The download ended early, so it was not used.');
    return { bytes };
  } catch (error) {
    if (response.stream && typeof response.stream.destroy === 'function') response.stream.destroy();
    if (handle) await handle.close().catch(() => {});
    fs.rmSync(dest, { force: true });
    throw error;
  }
}

/* Keep the newest `keep` staged versions (and `protect`), delete the rest and any stray part file. */
function pruneStaged(root, { keep = KEEP_VERSIONS, protect = [] } = {}) {
  let names = [];
  try {
    names = fs.readdirSync(root);
  } catch {
    return [];
  }
  const versions = names.map((name) => ({ name, parsed: parseVersion(name) })).filter((x) => x.parsed).sort((a, b) => compareVersions(b.parsed, a.parsed));
  const gone = [];
  versions.forEach((entry, index) => {
    if (index >= keep && !protect.includes(entry.name)) {
      fs.rmSync(path.join(root, entry.name), { recursive: true, force: true });
      gone.push(entry.name);
    }
  });
  return gone;
}

function canWrite(dir) {
  try {
    fs.accessSync(dir, fs.constants.W_OK);
    return true;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------- the controller

const WHY = {
  checkout: 'This copy of Sutra Pro runs from a source checkout, so it does not update itself.',
  unsigned: 'This copy of Sutra Pro is not signed with a developer certificate, so it cannot check who made an update and will not install one by itself.',
};

/* options (everything that touches the world is an argument):
     platform, arch, version (the running app), packaged, env, execPath, pid, dataDir, tmpDir, log(line), now
     api.plan({ auto, platform, arch }) -> answer (rejects with .code 'offline' / 'update_off' for the server's refusals); setting() -> bool (the switch)
     report(state, version, message) -> Promise (tells the server what to show in Settings, About; best effort)    install(can, why) -> Promise (can this copy install, or only tell)
     get(url) -> { status, headers, stream }    run(file, args, { envName, envValue }) -> { code, stdout, stderr }    spawnDetached(file, args)
     ask({ message, detail, buttons, defaultId, cancelId }) -> index    info({ message, detail })    reveal(path)    openExternal(url)    quit()    isQuitting()
     isWritable(dir), timers, firstCheckMs, everyMs */
function createUpdater(options) {
  const o = {
    platform: process.platform, arch: process.arch, version: '0.0.0', packaged: false, env: {}, execPath: process.execPath, pid: process.pid, tmpDir: os.tmpdir(),
    log() {}, now: Date.now, isWritable: canWrite, isQuitting: () => false, firstCheckMs: FIRST_CHECK_MS, everyMs: EVERY_MS,
    timers: { setTimeout, clearTimeout, setInterval, clearInterval }, ...options,
  };
  const log = (line) => o.log(`update: ${line}`);
  let first = null;
  let every = null;
  let stopped = false;
  let busy = false;
  let capability = null;
  let staged = null;
  let prepared = null;
  let installOnQuit = false;
  const offered = new Set();
  const told = new Set();

  const report = async (state, version, message) => {
    try {
      await o.report(state, version || null, cleanSentence(message));
    } catch (error) {
      log(`could not tell the server (${state}): ${error && error.message}`);
    }
  };

  function offline() {
    return parseBool(o.env.SUTRA_OFFLINE) || String(o.env.SUTRA_CONNECTOR || '').trim().toLowerCase() === 'stub';
  }

  /* The timer runs only in a packaged app, on a computer that has a download for it, outside offline mode, the stub connector and the self-test. */
  function autoEligible() {
    if (parseBool(o.env.SUTRA_PRO_SELFTEST)) return 'self-test';
    if (offline()) return 'offline';
    if (!o.packaged) return 'not packaged';
    if (!assetFor(o.platform, o.arch)) return 'no download for this computer';
    return '';
  }

  /* Whether this copy can tell who signed an update: { ok, why, identity }. Computed once. */
  async function canVerify() {
    if (capability) return capability;
    capability = await (async () => {
      if (!o.packaged) return { ok: false, why: WHY.checkout };
      if (o.platform === 'darwin') {
        const bundle = bundleOf(o.execPath);
        if (!bundle) return { ok: false, why: WHY.checkout };
        const shown = await o.run(CODESIGN, codesignDisplayArgs(bundle));
        const seal = parseCodesignDisplay(`${shown.stderr}\n${shown.stdout}`);
        const id = await o.run(PLUTIL, plistArgs(path.join(bundle, 'Contents', 'Info.plist'), 'CFBundleIdentifier'));
        const bundleId = cleanSentence(id.stdout, 200);
        if (shown.code !== 0 || !seal.teamId || !bundleId) return { ok: false, why: WHY.unsigned };
        return { ok: true, identity: { bundle, teamId: seal.teamId, bundleId } };
      }
      if (o.platform === 'win32') {
        const sig = await windowsSignature(o.execPath);
        return sig.valid ? { ok: true, identity: { subject: sig.subject } } : { ok: false, why: WHY.unsigned };
      }
      return { ok: false, why: 'There is no automatic update for this kind of computer.' };
    })();
    return capability;
  }

  async function windowsSignature(file) {
    const command = winSignatureCommand(o.env);
    const result = await o.run(command.file, command.args, { envName: command.envName, envValue: file });
    return result.code === 0 ? parseWinSignature(result.stdout) : { valid: false, subject: '' };
  }

  async function plistValue(app, key) {
    const result = await o.run(PLUTIL, plistArgs(path.join(app, 'Contents', 'Info.plist'), key));
    return result.code === 0 ? cleanSentence(result.stdout, 200) : '';
  }

  /* Mount the DMG read-only in a private folder, hand the one Sutra Pro.app in it to `fn`, and always unmount. */
  async function withMountedApp(dmg, fn) {
    const mountpoint = fs.mkdtempSync(path.join(o.tmpDir, 'sutra-pro-update-'));
    let attached = false;
    try {
      const mounted = await o.run(HDIUTIL, macAttachArgs(dmg, mountpoint));
      if (mounted.code !== 0) throw new UpdateError('mount', 'The downloaded disk image could not be opened.');
      attached = true;
      const found = fs.readdirSync(mountpoint).filter((name) => name.toLowerCase() === APP_BUNDLE_NAME.toLowerCase());      // the volume may not tell cases apart
      const app = path.join(mountpoint, APP_BUNDLE_NAME);
      if (found.length !== 1 || found[0] !== APP_BUNDLE_NAME || !fs.lstatSync(app).isDirectory()) throw new UpdateError('bundle', 'The downloaded disk image does not hold exactly one Sutra Pro app.');
      return await fn(app);
    } finally {
      if (attached) {
        const detached = await o.run(HDIUTIL, macDetachArgs(mountpoint, false));
        if (detached.code !== 0) await o.run(HDIUTIL, macDetachArgs(mountpoint, true));
      }
      try {
        fs.rmdirSync(mountpoint);
      } catch {
        // still mounted or already gone: the system's temporary folder is cleaned up anyway
      }
    }
  }

  /* A Sutra Pro.app is acceptable only if its seal holds and it is the same maker and app as the running one, and newer. */
  async function verifyBundle(app, version, identity) {
    const sealed = await o.run(CODESIGN, codesignVerifyArgs(app));
    if (sealed.code !== 0) throw new UpdateError('signature', 'The downloaded app\'s signature did not check out.');
    const shown = await o.run(CODESIGN, codesignDisplayArgs(app));
    const seal = parseCodesignDisplay(`${shown.stderr}\n${shown.stdout}`);
    if (shown.code !== 0 || !seal.teamId || seal.teamId !== identity.teamId) throw new UpdateError('team', 'The downloaded app was not signed by the same developer as this one.');
    if ((await plistValue(app, 'CFBundleIdentifier')) !== identity.bundleId) throw new UpdateError('bundle', 'The downloaded app is not the same app as this one.');
    const theirs = parseVersion(await plistValue(app, 'CFBundleShortVersionString'), { loose: true });
    const mine = parseVersion(o.version, { loose: true });
    const named = parseVersion(version);
    if (!theirs || !mine || !named || compareVersions(theirs, mine) <= 0 || theirs.major !== named.major || theirs.minor !== named.minor || theirs.patch !== named.patch) {
      throw new UpdateError('version', 'The downloaded app is not a newer version than this one.');
    }
    const assessed = await o.run(SPCTL, spctlArgs(app));
    if (assessed.code !== 0) throw new UpdateError('gatekeeper', 'macOS would not accept the downloaded app.');
  }

  async function verifyDownloaded(file, version, identity) {
    if (o.platform === 'darwin') {
      await withMountedApp(file, (app) => verifyBundle(app, version, identity));
      return;
    }
    const sig = await windowsSignature(file);
    if (!sig.valid) throw new UpdateError('signature', 'The downloaded installer is not validly signed.');
    if (sig.subject !== identity.subject) throw new UpdateError('team', 'The downloaded installer was not signed by the same publisher as this app.');
  }

  function discard(paths) {
    try {
      fs.rmSync(paths.dir, { recursive: true, force: true });
    } catch (error) {
      log(`could not delete ${paths.dir}: ${error.message}`);
    }
  }

  /* The verified file of this version: one already staged (a launch ago), else downloaded now. Throws UpdateError after deleting what failed. */
  async function ensureStaged(plan, identity) {
    const { version, asset } = plan;
    const paths = stagingPaths(o.dataDir, version, asset.name);
    fs.mkdirSync(paths.root, { recursive: true, mode: 0o700 });
    if (fs.existsSync(paths.file) && fs.existsSync(paths.sum)) {
      try {
        const want = parseChecksum(fs.readFileSync(paths.sum, 'utf8'), asset.name);
        const have = await hashFile(paths.file);
        if (want && have.sha256 === want && have.size === asset.size) {
          await verifyDownloaded(paths.file, version, identity);
          log(`${version} was already downloaded and still checks out`);
          return { version, name: asset.name, file: paths.file, digest: have.sha256, notesUrl: plan.notesUrl, paths };
        }
        log(`the earlier download of ${version} no longer checks out (it does not match its checksum): deleting it`);
      } catch (error) {
        log(`the earlier download of ${version} no longer checks out (${error.message}): deleting it`);
      }
    }
    discard(paths);
    fs.mkdirSync(paths.dir, { recursive: true, mode: 0o700 });
    try {
      await report('downloading', version, `Downloading Sutra Pro ${version}.`);
      const want = parseChecksum(await fetchSmall(o.get, asset.sha256Url), asset.name);
      if (!want) throw new UpdateError('checksum', `The published checksum for Sutra Pro ${version} could not be read, so nothing was installed.`);
      log(`downloading ${asset.name} (${asset.size} bytes) for ${version}`);
      await downloadTo({ get: o.get, url: asset.url, dest: paths.part, expectBytes: asset.size });
      fs.renameSync(paths.part, paths.file);                                  // renamed only when complete
      const have = await hashFile(paths.file);
      if (have.size !== asset.size || have.sha256 !== want) {
        throw new UpdateError('checksum', `The download of Sutra Pro ${version} did not match its published checksum, so it was deleted and nothing was installed.`);
      }
      fs.writeFileSync(paths.sum, `${want}  ${asset.name}\n`, { mode: 0o600 });
      await verifyDownloaded(paths.file, version, identity);
      log(`${version} is downloaded and verified`);
      pruneStaged(paths.root, { protect: [version] });
      return { version, name: asset.name, file: paths.file, digest: have.sha256, notesUrl: plan.notesUrl, paths };
    } catch (error) {
      discard(paths);
      throw error;
    }
  }

  /* One plain sentence for a download or a check that failed. */
  const failSentence = (version, error) => {
    if (error instanceof UpdateError) return error.code === 'checksum' ? error.sentence : `${error.sentence} It was deleted and nothing was installed.`;
    return `Sutra Pro ${version} could not be downloaded and checked, so nothing was installed.`;
  };

  async function tellOnly(plan, why) {
    const message = `Sutra Pro ${plan.version} is out. ${why} Download it from the release page.`;
    log(`${plan.version} is out; this copy only tells: ${why}`);
    await report('tell_only', plan.version, message);
    if (told.has(plan.version) && !plan.manual) return { state: 'tell_only' };
    told.add(plan.version);
    const choice = await o.ask({ message: `Sutra Pro ${plan.version} is out.`, detail: `${why} Open the release page to download it.`, buttons: ['Open the Release Page', 'Later'], defaultId: 0, cancelId: 1 });
    if (choice === 0) o.openExternal(plan.notesUrl);
    return { state: 'tell_only' };
  }

  async function runCheck(manual) {
    if (!manual) {
      const why = autoEligible();
      if (why) {
        log(`no automatic check (${why})`);
        return { state: 'skipped' };
      }
      if (!(await o.setting())) {
        log('the automatic check is switched off in Settings');
        return { state: 'skipped' };
      }
    } else if (offline()) {
      await o.info({ message: 'Updates are not available offline.', detail: 'Offline mode makes no request to the internet.' });
      return { state: 'offline' };
    }
    let answer;
    try {
      answer = await o.api.plan({ auto: !manual, platform: o.platform, arch: o.arch });
    } catch (error) {
      if (error && (error.code === 'offline' || error.code === 'update_off')) {
        log(`the server declined the check (${error.code})`);
        return { state: 'skipped' };
      }
      log(`the update check failed: ${error && error.message}`);
      if (manual) await o.info({ message: 'The update check did not work.', detail: cleanSentence(error && error.message) || 'Try again later.' });
      return { state: 'error' };
    }
    const plan = planFromAnswer(answer, { running: o.version, platform: o.platform, arch: o.arch });
    if (!plan.ok && plan.kind === 'current') {
      log('up to date');
      if (manual) await o.info({ message: 'You are up to date.', detail: `Sutra Pro ${o.version} is the newest version.` });
      return { state: 'current' };
    }
    if (!plan.ok && plan.kind === 'error') {
      log(`the answer was not used: ${plan.sentence}`);
      if (manual) await o.info({ message: 'The update check did not work.', detail: plan.sentence });
      return { state: 'error' };
    }
    if (!plan.ok) return tellOnly({ ...plan, manual }, plan.why);
    const can = await canVerify();
    if (!can.ok) return tellOnly({ ...plan, manual }, can.why);
    log(`${plan.version} is out (this is ${o.version}): downloading it to check it`);
    try {
      staged = await ensureStaged(plan, can.identity);
    } catch (error) {
      log(`${plan.version} was not used: ${error && error.message}`);
      await report('failed', plan.version, failSentence(plan.version, error));
      if (manual) await o.info({ message: 'The update was not installed.', detail: failSentence(plan.version, error) });
      return { state: 'failed' };
    }
    await report('ready', plan.version, `Sutra Pro ${plan.version} is downloaded and checked. Restart to install it.`);
    if (!manual && offered.has(plan.version)) return { state: 'ready' };         // asked once this session: Later means "at the next launch"
    offered.add(plan.version);
    return offer(can.identity);
  }

  async function offer(identity) {
    const choice = await o.ask({
      message: `Sutra Pro ${staged.version} is ready.`, detail: 'Restart now to update, or choose Later. Your data folder is not touched by an update.',
      buttons: ['Restart Now', 'Install on Quit', 'Later'], defaultId: 0, cancelId: 2,
    });
    if (choice === 0) return applyNow(identity);
    if (choice === 1) return installOnQuitChoice(identity);
    log(`${staged.version}: later (it is offered again at the next launch)`);
    return { state: 'later' };
  }

  /* Get everything ready for the swap while the app still runs, so a failure is told now and the installed app is untouched. */
  async function prepare(identity) {
    const { version, file } = staged;
    if (o.platform !== 'darwin') {
      prepared = { mode: 'installer' };
      return { ok: true };
    }
    const paths = installPaths(identity.bundle);
    try {
      if (!o.isWritable(paths.dir)) {
        const kept = staged.paths.app;
        fs.rmSync(kept, { recursive: true, force: true });
        await withMountedApp(file, async (app) => {
          const copied = await o.run(DITTO, dittoArgs(app, kept));
          if (copied.code !== 0) throw new UpdateError('copy', 'The new app could not be copied.');
        });
        await verifyBundle(kept, version, identity);
        o.reveal(kept);
        log(`${paths.dir} is not writable: the verified app is at ${kept}`);
        return { ok: false, sentence: `Sutra Pro ${version} was downloaded and checked, but ${paths.dir} is not writable by you, so it was not installed. Drag the Sutra Pro that just opened in Finder into that folder yourself.` };
      }
      fs.rmSync(paths.newApp, { recursive: true, force: true });
      await withMountedApp(file, async (app) => {
        const copied = await o.run(DITTO, dittoArgs(app, paths.newApp));
        if (copied.code !== 0) throw new UpdateError('copy', 'The new app could not be copied next to the installed one.');
      });
      await verifyBundle(paths.newApp, version, identity);
      prepared = { mode: 'swap', ...paths };
      return { ok: true };
    } catch (error) {
      fs.rmSync(paths.newApp, { recursive: true, force: true });
      log(`could not prepare ${version}: ${error && error.message}`);
      return { ok: false, sentence: `Sutra Pro ${version} could not be prepared (${cleanSentence(error && (error.sentence || error.message), 160)}), so nothing was changed.` };
    }
  }

  async function applyNow(identity) {
    const made = await prepare(identity);
    if (!made.ok) {
      await o.info({ message: 'The update was not installed.', detail: made.sentence });
      return { state: 'not_installed' };
    }
    installOnQuit = true;
    log(`${staged.version}: restarting to install it`);
    await report('installing', staged.version, `Sutra Pro ${staged.version} is installing now.`);
    o.quit();
    return { state: 'restarting' };
  }

  async function installOnQuitChoice(identity) {
    const made = await prepare(identity);
    if (!made.ok) {
      await o.info({ message: 'The update was not installed.', detail: made.sentence });
      return { state: 'not_installed' };
    }
    installOnQuit = true;
    log(`${staged.version}: it will install when the app quits`);
    await report('ready', staged.version, `Sutra Pro ${staged.version} is downloaded and checked. It installs when you quit Sutra Pro.`);
    return { state: 'on_quit' };
  }

  /* Called by main.js once the app's own quit path has stopped the server, just before the process ends. Starts the helper (macOS) or the verified
     installer (Windows), detached. Never throws; true when something was started. */
  async function applyOnQuit() {
    if (!installOnQuit || !prepared || !staged) return false;
    try {
      if (prepared.mode === 'swap') {
        const script = path.join(staged.paths.root, 'apply-update.sh');
        const scratch = `${script}.tmp`;
        fs.rmSync(scratch, { force: true });
        fs.writeFileSync(scratch, macSwapScript(), { mode: 0o700, flag: 'wx' });
        fs.renameSync(scratch, script);
        fs.chmodSync(script, 0o700);
        const logFile = path.join(o.dataDir, 'logs', 'desktop.log');
        const args = macHelperArgs({ script, pid: o.pid, app: prepared.app, newApp: prepared.newApp, oldApp: prepared.oldApp, badApp: prepared.badApp, dataDir: o.dataDir, logFile });
        log(`starting the swap helper for ${staged.version}`);
        o.spawnDetached('/bin/sh', args);
        return true;
      }
      const have = await hashFile(staged.file);                                          // the verified file, unchanged since it was verified
      if (have.sha256 !== staged.digest) throw new UpdateError('checksum', 'The installer changed after it was checked.');
      const sig = await windowsSignature(staged.file);
      if (!sig.valid || !capability || !capability.identity || sig.subject !== capability.identity.subject) throw new UpdateError('signature', 'The installer\'s signature no longer checks out.');
      log(`starting the installer for ${staged.version}`);
      o.spawnDetached(staged.file, winInstallerArgs());
      return true;
    } catch (error) {
      log(`the update was not applied: ${error && error.message}`);
      return false;
    }
  }

  async function checkNow({ manual = false } = {}) {
    if (stopped || o.isQuitting()) return { state: 'quitting' };
    if (busy) {
      if (manual) await o.info({ message: 'Sutra Pro is already checking for updates.', detail: '' });
      return { state: 'busy' };
    }
    busy = true;
    try {
      return await runCheck(manual);
    } catch (error) {
      log(`the update check stopped: ${error && error.stack ? error.stack : error}`);
      return { state: 'error' };
    } finally {
      busy = false;
    }
  }

  /* The first check after `firstCheckMs`, then every `everyMs`. Never keeps the program alive. Returns whether the timer was started. */
  function start() {
    if (first || every || stopped) return false;
    const why = autoEligible();
    if (why) {
      log(`no automatic check (${why})`);
      return false;
    }
    const tick = () => {
      checkNow({ manual: false }).catch((error) => log(`the update check stopped: ${error && error.message}`));
    };
    first = o.timers.setTimeout(() => {
      first = null;
      tick();
      if (!stopped) {
        every = o.timers.setInterval(tick, o.everyMs);
        if (every && typeof every.unref === 'function') every.unref();
      }
    }, o.firstCheckMs);
    if (first && typeof first.unref === 'function') first.unref();
    return true;
  }

  /* Once the server is up: say (in Settings, About) whether THIS copy can install an update itself or only tells. Never throws, makes no outside request. */
  async function announce() {
    if (stopped || parseBool(o.env.SUTRA_PRO_SELFTEST) || typeof o.install !== 'function') return null;
    try {
      const can = await canVerify();
      log(can.ok ? 'this copy can check who signed an update, so it can install one' : `this copy only tells about updates: ${can.why}`);
      await o.install(can.ok, can.ok ? '' : can.why);
      return can.ok;
    } catch (error) {
      log(`could not say whether this copy installs updates: ${error && error.message}`);
      return null;
    }
  }

  /* Quit: no more timers, no more dialogs. */
  function stop() {
    stopped = true;
    if (first) o.timers.clearTimeout(first);
    if (every) o.timers.clearInterval(every);
    first = null;
    every = null;
  }

  return {
    start, stop, checkNow, applyOnQuit, autoEligible, announce,
    pending: () => installOnQuit && prepared !== null,
    staged: () => staged && { version: staged.version, file: staged.file },
  };
}

module.exports = {
  createUpdater, parseVersion, compareVersions, channelAllows, planFromAnswer, parseChecksum, assetFor, downloadUrl, isAllowedHost, isAllowedUrl, safeReleasePage,
  stagingPaths, bundleOf, installPaths, macAttachArgs, macDetachArgs, codesignVerifyArgs, codesignDisplayArgs, spctlArgs, dittoArgs, plistArgs,
  winSignatureCommand, winInstallerArgs, macHelperArgs, macSwapScript, parseCodesignDisplay, parseWinSignature, hashFile, openFollowing, fetchSmall, downloadTo,
  pruneStaged, cleanSentence, parseBool, UpdateError,
  ASSET_NAMES, MAX_DOWNLOAD_BYTES, MAX_CHECKSUM_BYTES, FIRST_CHECK_MS, EVERY_MS, KEEP_VERSIONS, HELPER_WAIT_S, APP_BUNDLE_NAME, RELEASES_PAGE, USER_AGENT, WIN_SIGNATURE_SCRIPT,
};
