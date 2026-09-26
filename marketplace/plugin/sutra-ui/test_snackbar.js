#!/usr/bin/env node
/*
 * test_snackbar.js -- one bottom-right snack bar for the app's errors.
 *
 * WHY THIS EXISTS
 * ---------------
 * Founder 2026-09-26: "any kind of error messaging: a snack bar should come in
 * the bottom right." Before this, 03-org.js and 21-library.js called a toast()
 * that was never defined, so "Could not drop" / "Could not mark done" and four
 * more messages were never shown; the Agents screen had its own centred toast;
 * uncaught errors went only to the console.
 *
 * Ruling (reversible): action failures, uncaught errors and "backend down" go
 * to the snack bar. Screen-load errors stay inside the screen that failed, and
 * field validation stays beside its field.
 *
 * Behavioural where it matters (the real snack() runs against a small DOM
 * fake), source-level for the routing.
 *
 * Run: node test_snackbar.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const js = (f) => fs.readFileSync(path.join(__dirname, "static/js", f), "utf8");
const helpers = js("02-helpers.js");
const css = fs.readFileSync(path.join(__dirname, "static/panel.css"), "utf8");

let pass = 0, fail = 0;
const test = (n, f) => { try { f(); console.log("ok   - " + n); pass++; }
                         catch (e) { console.log("FAIL - " + n + "\n       " + e.message); fail++; } };
const assert = (c, m) => { if (!c) throw new Error(m); };

/* ---- a DOM just big enough for snack() ---------------------------------- */
function el(tag) {
  return {
    tagName: tag.toUpperCase(), children: [], parentNode: null, style: {}, _attrs: {},
    className: "", textContent: "", type: "", onclick: null, id: "",
    setAttribute(k, v) { this._attrs[k] = String(v); },
    appendChild(c) { c.parentNode = this; this.children.push(c); return c; },
    insertBefore(c, ref) { c.parentNode = this; const i = this.children.indexOf(ref);
      i < 0 ? this.children.push(c) : this.children.splice(i, 0, c); return c; },
    removeChild(c) { this.children = this.children.filter(x => x !== c); c.parentNode = null; return c; },
    querySelector(sel) { const cls = sel.replace(/^\./, "");
      const walk = (n) => { for (const k of n.children) { if ((k.className || "").split(" ").includes(cls)) return k;
        const r = walk(k); if (r) return r; } return null; };
      return walk(this); },
  };
}

function load() {
  const start = helpers.indexOf("/* SNACK BAR");
  const end = helpers.indexOf("/* /SNACK BAR */");
  assert(start >= 0 && end > start, "02-helpers.js has no SNACK BAR section");
  const body = el("body");
  const listeners = {};
  const timers = [];
  const ctx = {
    document: {
      body,
      createElement: el,
      getElementById: (id) => { const f = (n) => { for (const k of n.children) { if (k.id === id) return k;
        const r = f(k); if (r) return r; } return null; }; return f(body); },
    },
    window: { addEventListener: (ev, fn) => { listeners[ev] = fn; } },
    setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
    clearTimeout: () => {},
    Array, String,
  };
  vm.createContext(ctx);
  vm.runInContext(helpers.slice(start, end) +
    "\nthis.snack = snack; this.toast = toast; this.snackError = snackError; this.snackClose = snackClose;", ctx);
  const host = () => ctx.document.getElementById("snackHost");
  const items = () => (host() ? host().children.filter(c => /\bsnack\b/.test(c.className)) : []);
  return { ctx, body, listeners, timers, host, items };
}

test("an error shows as a snack bar with its text and a close button", () => {
  const { ctx, host, items } = load();
  ctx.snack("Could not save the charter", { kind: "error" });
  assert(host(), "no #snackHost was created");
  assert(items().length === 1, "expected one snack, got " + items().length);
  const s = items()[0];
  assert(/snack-error/.test(s.className), "not styled as an error: " + s.className);
  assert(s.querySelector(".snack-t").textContent === "Could not save the charter", "text missing");
  assert(s.querySelector(".snack-x"), "no close button");
  assert(s._attrs.role === "alert", "an error is not announced as an alert");
});

test("the close button removes it", () => {
  const { ctx, items } = load();
  ctx.snack("x failed", { kind: "error" });
  items()[0].querySelector(".snack-x").onclick();
  assert(items().length === 0, "close did not remove the snack");
});

test("it dismisses itself, errors later than notices", () => {
  const { ctx, timers } = load();
  ctx.snack("saved", { kind: "info" });
  ctx.snack("broke", { kind: "error" });
  assert(timers.length === 2, "no auto-dismiss timer");
  assert(timers[1].ms > timers[0].ms, "an error leaves as fast as a notice");
  assert(timers[1].ms >= 8000, "an error is gone before it can be read: " + timers[1].ms);
});

test("the same error twice counts up instead of stacking", () => {
  const { ctx, items } = load();
  ctx.snack("offline", { kind: "error" });
  ctx.snack("offline", { kind: "error" });
  assert(items().length === 1, "duplicates stacked: " + items().length);
  assert(/2/.test(items()[0].querySelector(".snack-n").textContent), "no repeat count");
});

test("at most three are on screen", () => {
  const { ctx, items } = load();
  ["a", "b", "c", "d", "e"].forEach(m => ctx.snack(m + " failed", { kind: "error" }));
  assert(items().length === 3, "expected 3, got " + items().length);
  assert(items()[items().length - 1].querySelector(".snack-t").textContent === "e failed", "newest is not kept");
});

test("toast() exists and sorts errors from notices", () => {
  const { ctx, items } = load();
  ctx.toast("Could not drop: busy");
  ctx.toast("Filed as an ask for you to stamp.");
  assert(/snack-error/.test(items()[0].className), "'Could not ...' was not an error");
  assert(/snack-info/.test(items()[1].className), "a plain notice was shown as an error");
});

test("toast() shows escaped text as text, not entities", () => {
  const { ctx, items } = load();
  ctx.toast("Could not drop: a &lt;b&gt; &amp; c");
  assert(items()[0].querySelector(".snack-t").textContent === "Could not drop: a <b> & c",
    "entities leaked: " + items()[0].querySelector(".snack-t").textContent);
});

test("uncaught errors and rejected promises reach the snack bar", () => {
  const { listeners, items } = load();
  assert(listeners.error && listeners.unhandledrejection, "no global error net");
  listeners.unhandledrejection({ reason: new Error("socket closed") });
  assert(items().length === 1 && /socket closed/.test(items()[0].querySelector(".snack-t").textContent),
    "an unhandled rejection was not shown");
  listeners.error({ message: "ResizeObserver loop completed with undelivered notifications." });
  assert(items().length === 1, "browser noise (ResizeObserver) was shown as an error");
});

test("no module-level const in the section, so a throw earlier in the file cannot disable it", () => {
  const sec = helpers.slice(helpers.indexOf("/* SNACK BAR"), helpers.indexOf("/* /SNACK BAR */"));
  assert(!/^(const|let)\s/m.test(sec), "a top-level const/let sits in the TDZ if the file throws before it");
});

/* ---- where it sits, and who calls it -------------------------------------- */
test("the snack host sits bottom-right", () => {
  const rule = css.slice(css.indexOf("#snackHost{"), css.indexOf("}", css.indexOf("#snackHost{")));
  assert(rule.length > 10, "no #snackHost rule in panel.css");
  assert(/position:\s*fixed/.test(rule) && /bottom:/.test(rule) && /right:/.test(rule), "not fixed bottom-right: " + rule);
});

test("snacks stack above the update card, not under it", () => {
  assert(/function snackReflow/.test(helpers), "no reflow against the update card");
  assert(/snackReflow\(\)/.test(js("06-render.js")), "the update card does not reflow the snacks");
});

test("the Agents toast, backend-down and workspace failures route here", () => {
  const ag = js("17-agents.js");
  const agFn = ag.slice(ag.indexOf("function agToast"), ag.indexOf("\n}\n", ag.indexOf("function agToast")));
  assert(/\b(snack|toast)\(/.test(agFn) && !/createElement/.test(agFn), "agToast still draws its own toast");
  assert(/function backendError[\s\S]{0,400}snackError\(/.test(js("07-loaders.js")), "backend-down is not snacked");
  const ws = js("13-workspace.js");
  assert(!/catch\s*\(e\)\s*\{\s*S\.ws\.notice\s*=\s*e\.message/.test(ws), "a workspace failure still only sets a notice");
  assert((ws.match(/snackError\(/g) || []).length >= 5, "workspace failures are not snacked");
});

console.log("\n" + "-".repeat(60));
console.log(`snack bar: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
