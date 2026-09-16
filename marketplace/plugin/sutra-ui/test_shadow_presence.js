#!/usr/bin/env node
/*
 * test_shadow_presence.js -- "Hide for this app": Presence, per app, durable.
 * Run: node test_shadow_presence.js
 *
 * THE CLAIM UNDER TEST. Enabling the row hides the Shadow Presence dot for
 * the app the founder has open, disabling it restores it, and the choice is
 * the server's (presence.json) rather than a flag that dies at reload. The
 * durability half is asserted in test_shadow_presence.py -- a fresh
 * interpreter reading the file back. This lane asserts the half that file
 * cannot: that the dot actually goes, for that app only, and comes back.
 *
 * WHY A NEW LANE rather than more of test_shadow_overlay.js: that lane is red
 * on main already, and a new assertion inside it cannot be read as a result.
 *
 * A LIVE DOT, NOT A COUNTER. The document stub below keeps the appended
 * .shdot and hands it back from querySelector, so mountShadowOverlay's own
 * "already mounted" guard and the remove paths are exercised for real. A stub
 * that only counted appendChild calls would pass while the dot stayed on
 * screen forever.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

/* vm objects have foreign prototypes, so deepStrictEqual fails on two arrays
   that are element-for-element identical (the test_shadow_overlay.js lesson).
   Compare the VALUES. */
const J = (o) => JSON.stringify(o);

const overlay = fs.readFileSync(
  path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const home = fs.readFileSync(
  path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");
const modules = fs.readFileSync(
  path.join(__dirname, "static", "js", "18-modules.js"), "utf8");

/* the id the row reads is the Apps screen's own open-app id, not a second
   notion invented for Presence. Pin the source of truth. */
assert(/modSel \(open app id\)/.test(modules),
  "18-modules.js must still document modSel as the open app id");
assert(/S\.modSel/.test(overlay),
  "the overlay must read the open app id from S.modSel");

function fresh(opts){
  opts = opts || {};
  let dot = null;
  const classes = new Set();
  const posts = [];
  const nudges = [];
  const ctx = {
    console, Date, JSON,
    setTimeout: (fn, ms) => ({ fn, ms }), clearTimeout(){},
    esc: (x) => String(x == null ? "" : x).replace(/</g, "&lt;"),
    S: {}, SCREENS: {}, TITLES: {}, listeners: {},
    scheduleRender(){}, render(){},
    panelToken: () => "tok", refreshPanelToken: async () => false,
    showNudge: (m) => nudges.push(m),
    fetch: (url, init) => {
      posts.push({ url, body: JSON.parse((init && init.body) || "{}") });
      const answer = opts.answer ? opts.answer(posts[posts.length - 1]) : null;
      if (opts.fail) return Promise.reject(new Error("offline"));
      return Promise.resolve({ ok: !!answer, status: answer ? 200 : 500,
                               json: async () => answer });
    },
    document: {
      createElement(tag){
        const el = { tagName: tag, className: "", textContent: "",
                     innerHTML: "", dataset: {}, _attrs: {},
                     setAttribute(k, v){ el._attrs[k] = v; },
                     addEventListener(){},
                     remove(){ if (dot === el) dot = null; } };
        return el;
      },
      querySelector(sel){
        if (sel === ".shdot") return dot;
        return null;
      },
      body: {
        appendChild(el){ if (/\bshdot\b/.test(el.className || "")) dot = el; },
        classList: { add: (c) => classes.add(c),
                     remove: (c) => classes.delete(c) },
      },
      addEventListener(type, fn){ ctx.listeners[type] = fn; },
    },
    _dot: () => dot,
    _gutter: () => classes.has("sh-fab-on"),
    _posts: posts,
    _nudges: nudges,
  };
  ctx.__SHADOW_NO_AUTOBOOT = true;
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(home, ctx);
  return ctx;
}

/* ------------------------------------------------------------- THE FLAG -- */

/* 1. no app open means not hidden -- anywhere that is not an app, the row has
   no subject and the dot is untouched. This is the whole difference between
   this setting and the corner-card one. */
{
  const ctx = fresh();
  ctx.S.shadowHiddenApps = ["photo-gallery"];
  ctx.S.modSel = null;
  assert.strictEqual(ctx.shadowPresenceHiddenHere(), false);
  ctx.S.modSel = undefined;
  assert.strictEqual(ctx.shadowPresenceHiddenHere(), false);
  console.log("ok 1 with no app open nothing is hidden");
}

/* 2. hidden for the open app, and ONLY the open app */
{
  const ctx = fresh();
  ctx.S.shadowHiddenApps = ["photo-gallery"];
  ctx.S.modSel = "photo-gallery";
  assert.strictEqual(ctx.shadowPresenceHiddenHere(), true);
  ctx.S.modSel = "recipe-box";
  assert.strictEqual(ctx.shadowPresenceHiddenHere(), false,
    "a hide on one app must not reach another");
  console.log("ok 2 the flag is per app");
}

/* 3. an empty / missing list hides nothing */
{
  const ctx = fresh();
  ctx.S.modSel = "photo-gallery";
  assert.strictEqual(ctx.shadowPresenceHiddenHere(), false);
  ctx.S.shadowHiddenApps = [];
  assert.strictEqual(ctx.shadowPresenceHiddenHere(), false);
  console.log("ok 3 an unconfigured install hides nothing");
}

/* ----------------------------------------------------------- THE MOUNT -- */

/* 4. THE DOT ACTUALLY GOES, and comes back when the founder leaves the app.
   Asserted through the real mount path, not through the flag. */
{
  const ctx = fresh();
  ctx.mountShadowOverlay();
  assert(ctx._dot(), "the dot must mount on an unconfigured install");
  assert(ctx._gutter(), "and reserve its gutter");

  ctx.applyAppPresence(["photo-gallery"]);
  assert(ctx._dot(), "with no app open the hide must not reach the dot");

  ctx.S.modSel = "photo-gallery";
  ctx.applyAppPresence();
  assert.strictEqual(ctx._dot(), null,
    "opening the hidden app must remove the dot");
  assert.strictEqual(ctx._gutter(), false,
    "and give the gutter back -- otherwise a blank strip is left behind");

  ctx.S.modSel = "recipe-box";
  ctx.applyAppPresence();
  assert(ctx._dot(), "moving to another app must bring the dot back");

  ctx.S.modSel = null;
  ctx.applyAppPresence();
  assert(ctx._dot(), "and leaving apps entirely must leave it there");
  console.log("ok 4 the dot goes for one app and returns for the next");
}

/* 5. the guard is INSIDE mountShadowOverlay, so nothing can mount past it --
   a caller that mounts directly (boot, the corner-card switch) is covered by
   the same line rather than by remembering to check first. */
{
  const ctx = fresh();
  ctx.S.shadowHiddenApps = ["photo-gallery"];
  ctx.S.modSel = "photo-gallery";
  ctx.mountShadowOverlay();
  assert.strictEqual(ctx._dot(), null,
    "mountShadowOverlay must refuse to mount on a hidden app");
  console.log("ok 5 the suppression is at mount time");
}

/* 6. the corner card and the per-app hide are separate choices: turning the
   card ON must not un-hide an app the founder deliberately hid. */
{
  const ctx = fresh();
  ctx.S.shadowHiddenApps = ["photo-gallery"];
  ctx.S.modSel = "photo-gallery";
  ctx.applyCornerCardPref(true);
  assert.strictEqual(ctx._dot(), null,
    "the corner-card switch must not silently clear a per-app hide");
  ctx.S.modSel = "recipe-box";
  ctx.applyCornerCardPref(true);
  assert(ctx._dot(), "and the card still comes back everywhere else");
  console.log("ok 6 corner card and per-app hide are independent");
}

/* ------------------------------------------------------------ THE SEED -- */

/* 7. the list arrives on the settings payload, and only a real list moves it:
   a failed or flag-gated read must leave the default (hidden nowhere). */
{
  const ctx = fresh();
  ctx.applyShadowPresence({ presence: { hidden_apps: ["photo-gallery"] } });
  assert.strictEqual(J(ctx.S.shadowHiddenApps), J(["photo-gallery"]));
  ctx.applyShadowPresence(null);
  assert.strictEqual(J(ctx.S.shadowHiddenApps), J(["photo-gallery"]),
    "a failed settings read must not clear the founder's hides");
  ctx.applyShadowPresence({ presence: { hidden_apps: "photo-gallery" } });
  assert.strictEqual(J(ctx.S.shadowHiddenApps), J(["photo-gallery"]),
    "a wrong-shaped payload must not be adopted");
  console.log("ok 7 the hide list is seeded from the settings payload");
}

/* -------------------------------------------------------------- THE ROW -- */

const SET = { tasks: {}, attention: {}, presence: { hidden_apps: [] } };

/* 8. with no app open the row states that rather than drawing a switch -- a
   switch whose target is null would either do nothing or hide the dot
   somewhere the founder was not looking. */
{
  const ctx = fresh();
  const h = ctx.shadowSetPresenceHtml(SET);
  const row = h.slice(h.indexOf("Hide for this app"));
  assert(/no app open/.test(row), "the row must say it has no subject: " + row);
  assert(!/data-shpresence="app"/.test(row),
    "and must not offer a switch with nothing behind it");
  console.log("ok 8 with no app open the row says so");
}

/* 9. with an app open the row is a real switch, it names the app, and it
   reads the truth */
{
  const ctx = fresh();
  ctx.modSelected = (s) => ({ id: s.modSel, name: "Photo Gallery" });
  ctx.S.modSel = "photo-gallery";
  ctx.S.shadowHiddenApps = [];
  let h = ctx.shadowSetPresenceHtml(SET);
  let row = h.slice(h.indexOf("Hide for this app"));
  assert(/data-shpresence="app"/.test(row), "the switch must be operable");
  assert(/Photo Gallery/.test(row),
    "the row must name the app it is about: " + row);
  assert(/aria-checked="false"[\s\S]{0,120}data-shpresence="app"/
    .test(row.replace(/\s+/g, " ")), "off is off: " + row);

  /* THE PAYLOAD DECIDES, not the seeded flag -- the row prefers `d` for the
     same reason the nudges row beside it does, so this is where a hide is
     stated from. */
  row = ctx.shadowSetPresenceHtml({ presence: { hidden_apps: ["photo-gallery"] } });
  row = row.slice(row.indexOf("Hide for this app")).replace(/\s+/g, " ");
  assert(/aria-checked="true"[\s\S]{0,120}data-shpresence="app"/.test(row),
    "a hidden app must read as on: " + row);

  /* and with no hide list on the payload at all it falls back to the flag the
     overlay was seeded with, rather than drawing a switch off nothing */
  ctx.S.shadowHiddenApps = ["photo-gallery"];
  row = ctx.shadowSetPresenceHtml({}).replace(/\s+/g, " ");
  row = row.slice(row.indexOf("Hide for this app"));
  assert(/aria-checked="true"[\s\S]{0,120}data-shpresence="app"/.test(row),
    "with no payload the seeded flag must still be read: " + row);
  console.log("ok 9 the row names the app and reads the truth");
}

/* ----------------------------------------------------------- THE WRITE -- */

/* 10. the switch WRITES -- verb body, keyed on the open app, and it repaints
   from the server's answer rather than from the value it sent. */
{
  (async () => {
    const ctx = fresh({ answer: (p) => ({
      app_id: "photo-gallery", hidden: "hide" in p.body,
      hidden_apps: "hide" in p.body ? ["photo-gallery"] : [] }) });
    ctx.modSelected = (s) => ({ id: s.modSel, name: "Photo Gallery" });
    ctx.S.modSel = "photo-gallery";
    ctx.S.shadowSettings = JSON.parse(JSON.stringify(SET));
    ctx.mountShadowOverlay();
    assert(ctx._dot(), "precondition: the dot is up");

    await ctx.shadowSetAppPresence();
    assert.strictEqual(ctx._posts.length, 1, "exactly one write");
    assert.strictEqual(ctx._posts[0].url, "/api/shadow/settings/presence/app");
    assert.strictEqual(J(ctx._posts[0].body), J({ hide: "photo-gallery" }),
      "the body is a verb keyed on the open app, never a whole list");
    assert.strictEqual(ctx._dot(), null, "and the dot is gone");
    assert.strictEqual(J(ctx.S.shadowSettings.presence.hidden_apps),
      J(["photo-gallery"]), "the settings doc the page reads is updated too");

    await ctx.shadowSetAppPresence();
    assert.strictEqual(J(ctx._posts[1].body), J({ show: "photo-gallery" }),
      "the second click shows it again");
    assert(ctx._dot(), "and the dot comes back");
    console.log("ok 10 the switch writes a verb and repaints from the answer");
  })().catch(e => { console.error("FAIL 10", e); process.exit(1); });
}

/* 11. a failed write puts it back. Nothing was stored, so nothing may look
   stored -- and the founder is told rather than left with a switch that
   silently disagrees with the server. */
{
  (async () => {
    const ctx = fresh({ fail: true });
    ctx.S.modSel = "photo-gallery";
    ctx.mountShadowOverlay();
    await ctx.shadowSetAppPresence();
    assert.strictEqual(J(ctx.S.shadowHiddenApps), J([]),
      "a failed write must not leave the hide standing");
    assert(ctx._dot(), "and the dot must come back");
    assert(/did not stick/.test(ctx._nudges.join(" ")),
      "the founder must be told: " + ctx._nudges.join(" "));
    console.log("ok 11 a failed write is undone and reported");
  })().catch(e => { console.error("FAIL 11", e); process.exit(1); });
}

/* 12. no app open, no write. The row does not draw the switch in that state;
   this is the second half of that guard, for a synthesised click or a
   selection that cleared between the render and the click. */
{
  (async () => {
    const ctx = fresh({ answer: () => ({ hidden_apps: [] }) });
    ctx.S.modSel = null;
    await ctx.shadowSetAppPresence();
    assert.strictEqual(ctx._posts.length, 0,
      "a click with no app open must write nothing");
    console.log("ok 12 no subject, no write");
  })().catch(e => { console.error("FAIL 12", e); process.exit(1); });
}

/* 13. THE DELEGATED CLICK reaches the writer -- the row is wired, not merely
   rendered. (2.224.1 lesson: served markup nobody handles.) */
{
  (async () => {
    const ctx = fresh({ answer: () => ({
      app_id: "photo-gallery", hidden: true,
      hidden_apps: ["photo-gallery"] }) });
    ctx.S.modSel = "photo-gallery";
    assert(ctx.listeners.click, "the home module must delegate clicks");
    ctx.listeners.click({ target: { dataset: { shpresence: "app" },
                                    closest: () => null } });
    await new Promise(r => setImmediate(r));
    assert.strictEqual(ctx._posts.length, 1,
      "the click must reach the writer: " + JSON.stringify(ctx._posts));
    assert.strictEqual(J(ctx._posts[0].body), J({ hide: "photo-gallery" }));
    console.log("ok 13 the click is wired to the write");
  })().catch(e => { console.error("FAIL 13", e); process.exit(1); });
}

/* 14. QUIET IS NOT THIS. The row used to flip S.shadowQuiet -- the nudge mute
   -- so the label named one thing and the switch did another, and the other
   died at reload. The two are independent now, in both directions. */
{
  (async () => {
    const ctx = fresh({ answer: () => ({
      app_id: "photo-gallery", hidden: true,
      hidden_apps: ["photo-gallery"] }) });
    ctx.S.modSel = "photo-gallery";
    ctx.S.shadowQuiet = false;

    await ctx.shadowSetAppPresence();
    assert.strictEqual(ctx.S.shadowQuiet, false,
      "hiding Presence for an app must not mute nudges");
    assert.strictEqual(J(ctx.S.shadowHiddenApps), J(["photo-gallery"]));

    /* and the card's own Quiet button still reaches quiet, without touching
       the hide list -- the founder keeps that control where it always was */
    ctx.listeners.click({ target: { dataset: { shpresence: "quiet" },
                                    closest: () => null } });
    assert.strictEqual(ctx.S.shadowQuiet, true, "quiet must still be reachable");
    assert.strictEqual(J(ctx.S.shadowHiddenApps), J(["photo-gallery"]),
      "muting nudges must not change which apps hide Presence");
    assert.strictEqual(ctx._posts.length, 1,
      "quiet has no store and must not have written one");
    console.log("ok 14 quiet and hide-for-this-app are independent");
  })().catch(e => { console.error("FAIL 14", e); process.exit(1); });
}

console.log("test_shadow_presence.js: all green");
