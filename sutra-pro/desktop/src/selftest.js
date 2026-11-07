'use strict';
/* The app proving itself (D120). With SUTRA_PRO_SELFTEST=1 the real window, the real server and the real page run as usual and, once the page is
   up, the app asks the page a few questions, saves a picture of the window, writes selftest.json and selftest.png to SUTRA_PRO_SELFTEST_DIR (default
   <data folder>/selftest), prints one SELFTEST line and quits through the normal path, which stops the server. The exit status is 0 only when every
   answer was right. The release workflows run it on the packaged app, on a runner, before anything is uploaded.

   A page that is merely loaded is not a page that works, so the questions are about what a person would see: the page finished loading, it is the
   server's own, it carries the boot block the server injects, it drew something, and /api/health answers from inside the page. */
const fs = require('node:fs');
const path = require('node:path');

const SETTLE_MS = 400;
const POLL_MS = 500;
const GIVE_UP_MS = 30000;

const PROBE = `(async () => {
  const health = await fetch('/api/health', { cache: 'no-store' }).then((response) => response.json()).catch(() => null);
  const text = (document.body && document.body.innerText) || '';
  return {
    href: location.href, title: document.title, readyState: document.readyState,
    elements: document.getElementsByTagName('*').length, textLength: text.trim().length,
    hasBoot: Boolean(document.getElementById('sutra-boot')), health,
  };
})()`;

/* The verdict on one probe, as data: { ok, failures }. */
function judge({ probe, owned, origin, expectVersion, windowTitle }) {
  const failures = [];
  if (windowTitle !== undefined && windowTitle !== 'Sutra Pro') failures.push(`the window is titled ${JSON.stringify(windowTitle)}, not "Sutra Pro"`);
  if (!owned) failures.push('the app did not start its own server (it attached to one that was running)');
  if (!probe) {
    failures.push('the page did not answer the probe');
    return { ok: false, failures };
  }
  if (probe.readyState !== 'complete') failures.push(`the page is ${probe.readyState}, not complete`);
  let pageOrigin = null;
  try {
    pageOrigin = new URL(probe.href).origin;
  } catch {
    // reported below
  }
  if (!origin || pageOrigin !== origin) failures.push(`the window shows ${probe.href}, not the server (${origin})`);
  if (!probe.title) failures.push('the page has no title');
  if (!probe.hasBoot) failures.push("the page has no boot block: it is not the server's own page");
  if (!(probe.elements >= 50)) failures.push(`the page drew ${probe.elements} elements`);
  if (!(probe.textLength >= 20)) failures.push(`the page shows ${probe.textLength} characters of text`);
  if (!probe.health || probe.health.ok !== true) failures.push('/api/health does not say ok from inside the page');
  else if (expectVersion && probe.health.version !== expectVersion) failures.push(`the server is ${probe.health.version}, the build is ${expectVersion}`);
  return { ok: failures.length === 0, failures };
}

/* A picture of the window, written to selftest.png. Chromium refuses a capture now and then (UnknownVizError) when the window has just been
   shown or is not in front, so the window is brought forward and the capture retried for a few seconds. A missing picture is reported, never a
   failed test: what the page does is the verdict, the picture is for the person who reads the run. */
async function takePicture({ win, outDir, log, sleep, attempts = 12 }) {
  let last = '';
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      if (!win.isVisible()) win.show();
      win.focus();
      const image = await win.webContents.capturePage();
      const png = image.toPNG();
      if (png.length > 0) {
        const size = image.getSize();
        fs.mkdirSync(outDir, { recursive: true });
        fs.writeFileSync(path.join(outDir, 'selftest.png'), png);
        return { bytes: png.length, width: size.width, height: size.height, attempt };
      }
      last = 'an empty picture';
    } catch (error) {
      last = error.message;
    }
    await sleep(500);
  }
  log(`selftest: no picture after ${attempts} attempts: ${last}`);
  return null;
}

async function runSelftest({ win, supervisor, outDir, expectVersion, log, now = Date.now, sleep = (ms) => new Promise((r) => setTimeout(r, ms)) }) {
  const contents = win.webContents;
  const probeOnce = async () => {
    try {
      return await contents.executeJavaScript(PROBE, true);
    } catch (error) {
      log(`selftest: the probe failed: ${error.message}`);
      return null;
    }
  };
  const give = now() + GIVE_UP_MS;
  let probe = await probeOnce();
  const judged = () => judge({ probe, owned: supervisor.owned, origin: supervisor.origin, expectVersion, windowTitle: win.getTitle() });
  let verdict = judged();
  while (!verdict.ok && now() < give) {          // the page draws after it loads: ask again until it has, or time is up
    await sleep(POLL_MS);
    probe = await probeOnce();
    verdict = judged();
  }
  await sleep(SETTLE_MS);
  const picture = await takePicture({ win, outDir, log, sleep });
  return record({
    outDir, log, result: {
      ok: verdict.ok, failures: verdict.failures, probe, picture, owned: supervisor.owned, url: supervisor.url, windowTitle: win.getTitle(),
      platform: process.platform, arch: process.arch, electron: process.versions.electron,
    },
  });
}

/* The outcome, in the two places a reader looks: selftest.json in the output folder (a GUI program on Windows may have no usable standard output,
   so the proof reads the file) and one SELFTEST line on standard output. Used for a failed start too, so every end of a self-test leaves both. */
function record({ outDir, log, result }) {
  try {
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(path.join(outDir, 'selftest.json'), `${JSON.stringify(result, null, 2)}\n`);
  } catch (error) {
    log(`selftest: no result file: ${error.message}`);
  }
  process.stdout.write(`SELFTEST ${JSON.stringify({ ok: result.ok, failures: result.failures, url: result.url || null, picture: result.picture || null })}\n`);
  return result;
}

module.exports = { judge, runSelftest, record, PROBE };
