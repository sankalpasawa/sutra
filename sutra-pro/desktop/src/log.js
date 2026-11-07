'use strict';
/* <data folder>/logs/desktop.log: what the app did and what the server it started printed (D122). The server's own log, app.log, sits beside it.
   The data folder holds the user's work, so it and the log folder are private (0700), as the server makes them. */
const fs = require('node:fs');
const path = require('node:path');

const MAX_BYTES = 5 * 1024 * 1024;       // past this the log is kept as desktop.log.1 and a new one starts

function createLog(folder, { now = () => new Date() } = {}) {
  const dir = path.join(folder, 'logs');
  const file = path.join(dir, 'desktop.log');
  try {
    fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
    fs.chmodSync(folder, 0o700);          // a no-op on Windows
    if (fs.existsSync(file) && fs.statSync(file).size > MAX_BYTES) fs.renameSync(file, `${file}.1`);
  } catch {
    // no log is better than no app: write() below ignores a missing folder too
  }
  return {
    file,
    dir,
    write(line) {
      try {
        fs.appendFileSync(file, `${now().toISOString()} desktop: ${line}\n`, { mode: 0o600 });
      } catch {
        // see above
      }
    },
  };
}

module.exports = { createLog, MAX_BYTES };
