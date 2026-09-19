#!/usr/bin/env node
/*
 * test_shadow_compose_focus.js -- the "Talk to Shadow" box keeps the caret.
 *
 * FOUNDER, 2026-09-18: "sometimes when you are typing in it, the focus from
 * that field is going." Two textareas carry that placeholder and each lost
 * focus for its own reason:
 *
 *   [data-shhomecompose]  the workspace composer. render() saved it only
 *                         across a #scBody rebuild, and that snapshot is
 *                         taken AFTER `panesEl.innerHTML = panesHtml` -- so
 *                         any render that also rebuilt the panes row had
 *                         already detached the textarea and moved
 *                         activeElement to <body>. _focusedInputSelector(),
 *                         which runs at the TOP of render() before anything
 *                         is replaced, did not know the attribute.
 *
 *   [data-shcompose]      the corner card. renderShadowCard() removes the
 *                         wrapper and rebuilds it wholesale with no
 *                         preservation at all, and four callers repaint it
 *                         from the background.
 *
 * BOTH OF THOSE ARE SNAPSHOT FIXES, and a snapshot can only save what was
 * focused when the render it belongs to began. The workspace composer also
 * rendered EMPTY every time and kept the typed text nowhere but the DOM node
 * being replaced -- so any detach in an EARLIER tick (a repaint that does not
 * go through render(), two renders in a row) left nothing to snapshot, and the
 * draft, the caret and the focus were gone before render() ever looked.
 * Blocks 3 and 4 cover that: the draft and "who has the caret" are now state
 * in S, read back on every pass, which is what every other typed field in
 * 16-shadow-home.js already did.
 *
 * Run: node test_shadow_compose_focus.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const JS = path.join(__dirname, "static", "js");
let n = 0;
const ok = (m) => console.log("ok " + (++n) + " " + m);

/* -- 1. the workspace composer is saved before #panes is replaced --------- */
{
  const src = fs.readFileSync(path.join(JS, "06-render.js"), "utf8");

  /* the real function, lifted whole -- this runs it, it does not grep it */
  const m = /function _focusedInputSelector\(\)\{[\s\S]*?\n\}/.exec(src);
  assert(m, "_focusedInputSelector must still exist in 06-render.js");

  const focused = (el) => {
    const ctx = { document: { activeElement: el } };
    vm.createContext(ctx);
    vm.runInContext(m[0] + "\n_r = _focusedInputSelector();", ctx);
    return ctx._r;
  };
  const stub = (tag, attrs) => ({
    tagName: tag, id: "",
    hasAttribute: (k) => Object.prototype.hasOwnProperty.call(attrs, k),
    getAttribute: (k) => attrs[k],
  });

  assert.strictEqual(
    focused(stub("TEXTAREA", { "data-shhomecompose": "1" })),
    '[data-shhomecompose="1"]',
    "the Talk to Shadow box must be saved at the top of render(), before "
    + "#panes is rebuilt -- otherwise a streaming session pane detaches it "
    + "and the caret, the focus and the draft are gone");

  /* the guarantee is only worth anything if the restore actually re-focuses */
  assert(/if \(prior\) \{[\s\S]*?el\.focus\(\);/.test(src),
    "render() must restore focus to the saved field");

  /* unrelated fields must not have been swept up by the change */
  assert.strictEqual(focused(stub("DIV", { "data-shhomecompose": "1" })), null,
    "only inputs are tracked");
  assert.strictEqual(focused(stub("TEXTAREA", { "data-nothing": "1" })), null,
    "an untracked field still returns null");
  ok("workspace composer survives a #panes rebuild");
}

/* -- 2. the corner card carries its composer across the wholesale swap ---- */
{
  const src = fs.readFileSync(path.join(JS, "15-shadow-overlay.js"), "utf8");

  function run(activeBox){
    const box = { tagName: "TEXTAREA", dataset: { shcompose: "1" },
                  value: "", focused: false, range: null,
                  focus(){ box.focused = true; },
                  setSelectionRange(a, b){ box.range = [a, b]; } };
    const wrap = { dataset: {}, innerHTML: "",
                   addEventListener(){}, remove(){},
                   querySelector: (s) => (s === "[data-shcompose]" ? box : null) };
    const existing = { removed: false, remove(){ existing.removed = true; },
                       contains: (el) => el === activeBox };
    const ctx = {
      console, Date,
      esc: (x) => String(x == null ? "" : x),
      escAttr: (x) => String(x == null ? "" : x),
      validChips: () => [],
      shadowMsgHtml: () => "",
      missionCardHtml: () => "",
      S: { shadowCardOpen: true, shadowThread: [] },
      document: {
        activeElement: activeBox,
        querySelector: (s) => (s === "[data-shcardwrap]" ? existing : null),
        createElement: () => wrap,
        body: { appendChild(){} },
        addEventListener(){},
      },
    };
    ctx.__SHADOW_NO_AUTOBOOT = true;
    vm.createContext(ctx);
    vm.runInContext(src, ctx);
    ctx.renderShadowCard();
    return { box, existing };
  }

  /* typing, then a background repaint lands */
  const typing = { tagName: "TEXTAREA", dataset: { shcompose: "1" },
                   value: "ship the refer", selectionStart: 14, selectionEnd: 14 };
  const a = run(typing);
  assert(a.existing.removed, "the card is still replaced wholesale");
  assert.strictEqual(a.box.value, "ship the refer",
    "the half-typed draft must survive the repaint");
  assert.strictEqual(a.box.focused, true,
    "focus must come back to the Talk to Shadow box");
  assert.deepStrictEqual(a.box.range, [14, 14],
    "and the caret must come back where it was, not at the end");

  /* Enter clears the box before it sends, so the snapshot is already "" on
     that path. Asserted so a future restore cannot start resurrecting a sent
     line -- NOT a special case in the code, which restores unconditionally. */
  const sent = { tagName: "TEXTAREA", dataset: { shcompose: "1" },
                 value: "", selectionStart: 0, selectionEnd: 0 };
  const b = run(sent);
  assert.strictEqual(b.box.value, "",
    "a sent line must not be re-inserted after the repaint");
  /* THE ONE OBSERVABLE CHANGE ON THE SEND PATH, recorded on purpose: before
     this fix Enter left focus on <body>. It is the focus fix reaching a
     repaint that send happens to trigger, not a change to what send does. */
  assert.strictEqual(b.box.focused, true,
    "focus stays in the composer after sending");

  /* a repaint while the founder is NOT in the box must not steal focus */
  const elsewhere = { tagName: "BUTTON", dataset: {} };
  assert.strictEqual(run(elsewhere).box.focused, false,
    "the card must not grab focus the founder never gave it");
  ok("corner-card composer survives renderShadowCard()");
}

/* -- 3. the workspace composer's draft and caret are STATE, not DOM ------- */
{
  const overlay = fs.readFileSync(path.join(JS, "15-shadow-overlay.js"), "utf8");
  const src = fs.readFileSync(path.join(JS, "16-shadow-home.js"), "utf8");

  function boot(){
    const ctx = {
      console, Date,
      /* the leave decision is deferred one tick -- captured so each block can
         run it deliberately, which is the only way to assert both outcomes */
      setTimeout: (fn) => { ctx.timers.push(fn); return ctx.timers.length; },
      timers: [],
      esc: (x) => String(x == null ? "" : x)
        .replace(/[&<>"]/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;",
                                      '"': "&quot;" }[m])),
      SCREENS: {}, TITLES: {}, S: {}, listeners: {},
      document: {
        addEventListener(t, fn){ ctx.listeners[t] = fn; },
        createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
        body: { appendChild(){} }, querySelector(){ return null; },
        activeElement: null,
      },
    };
    ctx.__SHADOW_NO_AUTOBOOT = true;
    ctx.flush = () => ctx.timers.splice(0).forEach((f) => f());
    vm.createContext(ctx);
    vm.runInContext(overlay, ctx);
    vm.runInContext(src, ctx);
    return ctx;
  }

  const box = () => ({
    tagName: "TEXTAREA", dataset: { shhomecompose: "1" }, isConnected: true,
    value: "", focused: false, range: null,
    focus(){ this.focused = true; },
    setSelectionRange(a, b){ this.range = [a, b]; },
  });

  /* the box RENDERS what is in the store -- this is what makes the draft
     survive a repaint that nothing snapshotted */
  {
    const ctx = boot();
    ctx.S.shadowComposeDraft = 'ship the <refer> & "co"';
    const h = ctx.shadowStageHtml(true);
    assert(/placeholder="Talk to Shadow…"/.test(h), "still the same box");
    assert(h.includes('ship the &lt;refer&gt; &amp; &quot;co&quot;'),
      "the stored draft must be rendered back into the textarea, escaped");
    assert(!ctx.shadowStageHtml(true).includes("undefined"),
      "an empty store renders an empty box, not the word undefined");
  }

  /* typing fills the store; nothing re-renders per keystroke */
  {
    const ctx = boot();
    ctx.listeners.input({ target: { dataset: { shhomecompose: "1" },
                                    value: "half a brie", selectionStart: 6 } });
    assert.strictEqual(ctx.S.shadowComposeDraft, "half a brie");
    assert.strictEqual(ctx.S.shadowComposeCaret, 6);
  }

  /* WHO HAS THE CARET IS STATE TOO, and a DETACH IS NOT A LEAVE.
     Driven in Chrome 2026-09-18, replacing #scBody under the focused box
     fires `focusout` with isConnected STILL TRUE and relatedTarget null --
     indistinguishable from a click-away at that instant. These blocks
     reproduce that event shape exactly, which the first version of this test
     did not: it fed isConnected=false and so passed against code that lost
     focus on every real repaint. */
  {
    /* a rebuild: focusout looks like a leave, but the node is gone a tick later */
    const ctx = boot();
    const b = box();
    ctx.listeners.focusin({ target: b });
    assert.strictEqual(ctx.S.shadowComposeFocus, true);

    b.selectionStart = 7;
    ctx.listeners.focusout({ target: b, relatedTarget: null });   /* connected */
    ctx.document.activeElement = { tagName: "BODY", dataset: {} };
    b.isConnected = false;                       /* the swap completes */
    ctx.flush();
    assert.strictEqual(ctx.S.shadowComposeFocus, true,
      "a rebuild detaching the node must NOT read as the founder leaving -- "
      + "that is exactly the 'sometimes' case the founder reported");
    assert.strictEqual(ctx.S.shadowComposeCaret, 7, "the caret is kept from it");
  }
  {
    /* dead space: same event, but the node is still there a tick later */
    const ctx = boot();
    const b = box();
    ctx.listeners.focusin({ target: b });
    b.selectionStart = 4;
    ctx.listeners.focusout({ target: b, relatedTarget: null });
    ctx.document.activeElement = { tagName: "BODY", dataset: {} };
    ctx.flush();
    assert.strictEqual(ctx.S.shadowComposeFocus, false,
      "clicking onto something unfocusable still gives the focus up");
    assert.strictEqual(ctx.S.shadowComposeCaret, 4);
  }
  {
    /* a click into another focusable needs no deferral at all */
    const ctx = boot();
    ctx.listeners.focusin({ target: box() });
    ctx.listeners.focusin({ target: { tagName: "INPUT", dataset: { sask: "s1" } } });
    assert.strictEqual(ctx.S.shadowComposeFocus, false,
      "focus that landed somewhere else says so immediately");
    assert.strictEqual(ctx.timers.length, 0, "and nothing was deferred");
  }

  /* the restore: draft always, focus only when it was given */
  {
    const ctx = boot();
    const b = box();
    ctx.document.querySelector = (s) => (s === "[data-shhomecompose]" ? b : null);
    ctx.S.shadowComposeDraft = "the outcome I want";
    ctx.S.shadowComposeCaret = 7;

    ctx.shadowRestoreCompose();
    assert.strictEqual(b.value, "the outcome I want",
      "the draft comes back on every pass, focused or not");
    assert.strictEqual(b.focused, false,
      "focus the founder never gave must never be grabbed");

    ctx.S.shadowComposeFocus = true;
    ctx.shadowRestoreCompose();
    assert.strictEqual(b.focused, true, "focus lost in an earlier tick comes back");
    assert.deepStrictEqual(b.range, [7, 7], "and lands where the caret was");

    /* a caret past the end of a shorter draft is clamped, never thrown */
    ctx.S.shadowComposeCaret = 999;
    ctx.shadowRestoreCompose();
    assert.deepStrictEqual(b.range, [18, 18]);

    /* on another screen there is no box, and that is not an error */
    ctx.document.querySelector = () => null;
    ctx.shadowRestoreCompose();
  }

  /* EVERY write to the box goes through the store. A programmatic
     `el.value = ...` fires no input event, so a node written directly would
     be overwritten by whatever the store still held on the next repaint --
     which would empty a line a failed send had just handed back. */
  {
    const ctx = boot();
    const b = box();
    b.value = "typed and sent";
    ctx.S.shadowComposeDraft = "typed and sent";

    ctx.shadowComposeSet(b, "");
    assert.strictEqual(ctx.S.shadowComposeDraft, "",
      "sending must empty the store, or the next repaint pastes the sent "
      + "line straight back in");
    assert.strictEqual(b.value, "");

    ctx.shadowComposeSet(b, "the send that did not land");
    assert.strictEqual(b.value, "the send that did not land");
    assert.strictEqual(ctx.S.shadowComposeDraft, "the send that did not land",
      "a refused send hands the line back through the store, so the repaint "
      + "it triggers cannot take it away again");
    assert.strictEqual(ctx.S.shadowComposeCaret, 26);

    /* Scoped to the paths that are actually HANDED the home composer:
       shadowSubmitCompose's two sends and shadowTalkSend's hand-back.
       shadowSayToShadow writes `el` the same way and is deliberately left
       alone -- it has no callers left (the box stopped using it on
       2026-09-17) and never receives this element. */
    const talk = /async function shadowTalkSend\(mid, el\)\{[\s\S]*?\n\}/
      .exec(src);
    assert(talk, "shadowTalkSend must still exist");
    assert(!/el\.value = text;/.test(talk[0]),
      "a refused send must hand the line back through the store");
    assert(!/\n      el\.value = "";\n      shadowTalkSend/.test(src)
        && !/\n    el\.value = "";\n    sendToShadow/.test(src),
      "neither send may empty the composer node behind the store's back");
  }

  /* -- THE THREE WAYS shadowRestoreCompose() COULD MISBEHAVE --------------
     It runs at the END OF EVERY render(), on every screen, whatever has
     focus. These are the cases where doing anything at all would be wrong. */
  {
    /* (a) the box is not on this screen: touch nothing, throw nothing */
    const ctx = boot();
    ctx.document.querySelector = () => null;
    ctx.S.shadowComposeDraft = "left on the Shadow screen";
    ctx.S.shadowComposeFocus = true;
    let focused = 0;
    ctx.document.activeElement = { tagName: "INPUT", focus(){ focused++; } };
    ctx.shadowRestoreCompose();
    assert.strictEqual(focused, 0,
      "with no composer on screen the restore must be a no-op");
    assert.strictEqual(ctx.S.shadowComposeDraft, "left on the Shadow screen",
      "and it must not clear the draft the founder can come back to");
  }
  {
    /* (b) ANOTHER INPUT HAS FOCUS. The founder typed, a repaint detached the
       box (so focusout never fired and the flag is stale-true), then they
       clicked into a different field. The restore must leave them there. */
    const ctx = boot();
    const b = box();
    ctx.document.querySelector = (q) =>
      (q === "[data-shhomecompose]" ? b : null);

    ctx.listeners.focusin({ target: b });               /* typing in the box */
    ctx.listeners.focusout({ target: b, relatedTarget: null });
    b.isConnected = false;                             /* detached by render */
    ctx.flush();
    assert.strictEqual(ctx.S.shadowComposeFocus, true, "a detach is not a leave");
    b.isConnected = true;

    const other = { tagName: "INPUT", dataset: { cwdinput: "1" } };
    ctx.listeners.focusin({ target: other });           /* clicked elsewhere */
    ctx.document.activeElement = other;
    ctx.shadowRestoreCompose();
    assert.strictEqual(b.focused, false,
      "the box must NOT pull focus out of a field the founder just clicked "
      + "into -- a stale flag from an earlier detach is exactly how that "
      + "would happen");
  }
  {
    /* (c) THE FLOATING CORNER CARD IS OPEN and has the caret. It is a second
       composer, on the same screen, with its own attribute -- the workspace
       box must not reach across and take the founder out of it. */
    const ctx = boot();
    const b = box();
    ctx.document.querySelector = (q) =>
      (q === "[data-shhomecompose]" ? b : null);
    ctx.listeners.focusin({ target: b });
    ctx.listeners.focusout({ target: b, relatedTarget: null });
    b.isConnected = false;
    ctx.flush();
    b.isConnected = true;

    const card = { tagName: "TEXTAREA", dataset: { shcompose: "1" } };
    ctx.listeners.focusin({ target: card });
    ctx.document.activeElement = card;
    ctx.shadowRestoreCompose();
    assert.strictEqual(b.focused, false,
      "the corner card keeps the caret it was given");
    assert.strictEqual(ctx.S.shadowComposeFocus, false);
  }
  {
    /* (d) already focused and mid-sentence: no write, no caret move. This is
       the common case -- it runs on EVERY render while the founder types. */
    const ctx = boot();
    const b = box();
    b.value = "a sentence in progress";
    ctx.S.shadowComposeDraft = "a sentence in progress";
    ctx.S.shadowComposeFocus = true;
    ctx.S.shadowComposeCaret = 5;
    ctx.document.querySelector = (q) =>
      (q === "[data-shhomecompose]" ? b : null);
    ctx.document.activeElement = b;
    b.focused = false; b.range = null;
    ctx.shadowRestoreCompose();
    assert.strictEqual(b.focused, false, "no redundant focus() on the common path");
    assert.strictEqual(b.range, null,
      "the caret of someone who is TYPING must never be set from the store -- "
      + "the store lags the live selection by design");
  }
  ok("the restore is inert unless the box itself lost the caret");

  ok("workspace composer's draft, caret and focus survive in S");
}

/* -- 4. render() actually calls the restore ------------------------------- */
{
  const src = fs.readFileSync(path.join(JS, "06-render.js"), "utf8");
  const body = /function render\(\)\{[\s\S]*?\n\}/.exec(src);
  assert(body, "render() must still exist");
  assert(/typeof shadowRestoreCompose === "function"\) shadowRestoreCompose\(\)/
    .test(body[0]),
    "render() must call the state restore -- a store nothing reads back is "
    + "not a fix");
  /* and AFTER its own snapshot restore, which is the more precise of the two */
  assert(body[0].indexOf("shadowRestoreCompose") > body[0].indexOf("if (prior) {"),
    "the snapshot path must still win when it fired");
  ok("render() reads the composer store back on every pass");
}

console.log("\n" + n + " blocks passed -- the Talk to Shadow box keeps the caret");
