'use strict';
/* Which addresses the window may show and which go to the user's browser (D118). The window shows the local server and nothing else: the page
   renders repository text and agent output, so a link in it is not trusted input. */

function parse(url) {
  try {
    return new URL(url);
  } catch {
    return null;
  }
}

/* True when `url` is on exactly this origin (scheme, host and port). A prefix test would accept http://127.0.0.1:8780.example.org. */
function isInternal(url, origin) {
  const parsed = parse(url);
  return parsed !== null && Boolean(origin) && parsed.origin !== 'null' && parsed.origin === origin;
}

/* Only web addresses are handed to the operating system: a file:, smb: or custom-protocol address would let page content mount a share or start a
   registered handler. */
function isSafeExternal(url) {
  const parsed = parse(url);
  return parsed !== null && (parsed.protocol === 'https:' || parsed.protocol === 'http:');
}

module.exports = { isInternal, isSafeExternal };
