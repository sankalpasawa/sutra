'use strict';
/* Which permissions the window grants (D118). The page is the server's own and asks for nothing the app needs, so the answer is no, with one exception:
   writing plain text to the clipboard, which is what the Copy buttons of the artifacts pane do. A browser grants that to a page that was clicked on;
   Electron grants nothing unless asked, and a refusal makes `navigator.clipboard.writeText` throw ("Copy failed"). Reading the clipboard, the camera,
   the location and notifications stay refused, and so does everything to a page that is not the server's own. */
const { isInternal } = require('./urls');

const ALLOWED = new Set(['clipboard-sanitized-write']);

/* True when `permission` is one the window grants and `url` (the page that asks) is on the server's own `origin`. */
function permissionAllowed(permission, url, origin) {
  return ALLOWED.has(permission) && isInternal(url, origin);
}

/* The two handlers of the session, shaped as Electron calls them: a request (`callback` takes the answer) and a check (`requestingOrigin`, and the
   address in `details` when the origin is empty). `getOrigin` is asked each time: the server's port is known only once it has started. */
function permissionHandlers(getOrigin) {
  return {
    request(_contents, permission, callback, details) {
      callback(permissionAllowed(permission, details && details.requestingUrl, getOrigin()));
    },
    check(_contents, permission, requestingOrigin, details) {
      return permissionAllowed(permission, requestingOrigin || (details && details.requestingUrl), getOrigin());
    },
  };
}

module.exports = { permissionAllowed, permissionHandlers, ALLOWED };
