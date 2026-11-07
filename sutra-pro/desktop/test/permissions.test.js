'use strict';
/* Which permissions the window grants: the server's own page may write text to the clipboard (its Copy buttons), and nothing else is granted. */
const assert = require('node:assert/strict');
const { test } = require('node:test');
const { permissionAllowed, permissionHandlers, ALLOWED } = require('../src/permissions');

const ORIGIN = 'http://127.0.0.1:8781';

test('the one permission granted is the plain-text clipboard write, to the server\'s own origin', () => {
  assert.deepEqual([...ALLOWED], ['clipboard-sanitized-write']);
  assert.equal(permissionAllowed('clipboard-sanitized-write', `${ORIGIN}/d/web/`, ORIGIN), true);
  assert.equal(permissionAllowed('clipboard-sanitized-write', `${ORIGIN}/`, `${ORIGIN}`), true);
  assert.equal(permissionAllowed('clipboard-sanitized-write', `${ORIGIN}/`, null), false, 'with no server there is no own origin');
});

test('every other permission is refused, even for the server\'s own page', () => {
  for (const permission of ['clipboard-read', 'media', 'mediaKeySystem', 'geolocation', 'notifications', 'midi', 'midiSysex', 'display-capture', 'fullscreen',
    'openExternal', 'pointerLock', 'idle-detection', 'window-management', 'unknown', '', undefined, null]) {
    assert.equal(permissionAllowed(permission, `${ORIGIN}/`, ORIGIN), false, String(permission));
  }
});

test('another page is refused the clipboard write: another origin, a look-alike, a data page, no address', () => {
  for (const url of ['http://127.0.0.1:8782/', 'http://127.0.0.1:8781.evil.example/', 'http://localhost:8781/', 'https://127.0.0.1:8781/', 'https://example.org/',
    'data:text/html,hi', 'file:///etc/passwd', 'about:blank', 'not a url', '', undefined, null]) {
    assert.equal(permissionAllowed('clipboard-sanitized-write', url, ORIGIN), false, String(url));
  }
});

test('the handlers the window installs answer as Electron asks: a request with a callback, a check with the origin', () => {
  let origin = null;
  const { request, check } = permissionHandlers(() => origin);
  const ask = (permission, requestingUrl) => {
    let answer;
    request(null, permission, (granted) => { answer = granted; }, { requestingUrl });
    return answer;
  };
  assert.equal(ask('clipboard-sanitized-write', `${ORIGIN}/`), false, 'the server is not up yet');
  assert.equal(check(null, 'clipboard-sanitized-write', ORIGIN, { requestingUrl: `${ORIGIN}/` }), false);
  origin = ORIGIN;
  assert.equal(ask('clipboard-sanitized-write', `${ORIGIN}/page`), true);
  assert.equal(ask('clipboard-sanitized-write', 'https://example.org/'), false);
  assert.equal(ask('geolocation', `${ORIGIN}/`), false);
  assert.equal(ask('notifications', `${ORIGIN}/`), false);
  assert.equal(ask('clipboard-sanitized-write', undefined), false, 'a request with no details is refused');
  assert.equal(check(null, 'clipboard-sanitized-write', `${ORIGIN}/`, {}), true, 'the origin may carry a trailing slash');
  assert.equal(check(null, 'clipboard-sanitized-write', 'https://example.org', {}), false);
  assert.equal(check(null, 'clipboard-read', ORIGIN, {}), false);
  assert.equal(check(null, 'clipboard-sanitized-write', '', { requestingUrl: `${ORIGIN}/` }), true, 'no origin given: the details name the address');
  assert.equal(check(null, 'clipboard-sanitized-write', undefined, undefined), false);
});
