#!/usr/bin/env node
/* test_shadow_conversation_scroll.js -- a Shadow conversation uses the whole
   pane (founder, 2026-10-09: "why's the print cut off like this").

   THE BUG. A conversation (the QUESTIONS rows) draws every message in one
   .shthread inside the pane's scroller, and `.shwright .shthread` capped that
   box at 280px with its own scrollbar -- so a long reply was read through a
   short inner window above an empty band. One scroller, as ruled 2026-09-23.

   Run: node test_shadow_conversation_scroll.js */
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8");
const home = fs.readFileSync(path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");

let n = 0;
function test(name, fn){ fn(); n++; console.log("ok   " + name); }

/* the declarations of one exact selector, last one wins */
function rule(selector){
  const esc = selector.replace(/[.*+?^${}()|[\]\\>]/g, "\\$&");
  const all = [...css.matchAll(new RegExp("(^|\\n)" + esc + "\\{([^}]*)\\}", "g"))];
  return all.length ? all[all.length - 1][2] : null;
}

test("inside the pane's scroller the thread is neither capped nor scrolling", () => {
  const r = rule(".shwright .shwscroll>.shthread");
  assert(r, "the rule exists");
  assert(/max-height:none/.test(r), "no height cap");
  assert(/overflow:visible/.test(r), "no scroller of its own");
});

test("it out-ranks the old 280px panel rule, whatever their order", () => {
  /* .shwright .shwscroll>.shthread = 3 classes; .shwright .shthread = 2 */
  assert(/max-height:280px/.test(rule(".shwright .shthread") || ""),
    "the panel rule this overrides is still the one it was written against");
  const spec = (sel) => (sel.match(/\./g) || []).length;
  assert(spec(".shwright .shwscroll>.shthread") > spec(".shwright .shthread"));
});

test("the conversation's thread is drawn INSIDE the pane's scroller", () => {
  const open = home.indexOf('<div class="shwscroll"');
  const thread = home.indexOf('<div class="shthread">${thread}</div>');
  const composer = home.indexOf("shadowStageHtml(true)");
  assert(open > 0 && thread > open && composer > thread,
    "scroller, then the thread inside it, then the composer below");
});

test("the pane's own scroller still takes the space that is left", () => {
  const r = rule(".shwscroll");
  assert(/flex:1 1 auto/.test(r) && /overflow-y:auto/.test(r));
});

console.log("test_shadow_conversation_scroll.js: " + n + " passed");
