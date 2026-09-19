#!/usr/bin/env node
/*
 * test_shadow_delegate_focus.js -- the + Delegate compose box is MOUNTED,
 * and no render may remove it.
 *
 * FOUNDER, 2026-09-18: "When we are typing, it goes out of focus, and you
 * have to put the cursor in again" -- then, on the fix: "the fix has to live
 * at the re-render source, and no setTimeout, autoFocus or programmatic
 * refocus may remain in the path that types into the compose field."
 *
 * WHAT USED TO BLOW THE NODE AWAY. render() rebuilds two things wholesale:
 * `panesEl.innerHTML = panesHtml` and `scBody.innerHTML = html`. #scBody is
 * the browse pane's body, so it sits INSIDE #panes and either swap destroys
 * every node on the screen -- including the textarea being typed into. A
 * destroyed textarea is a blurred textarea, and only a programmatic focus()
 * could bring the caret back.
 *
 * SO THE TEST IS ABOUT NODE IDENTITY, not about a caret being restored. The
 * contract is that the SAME textarea object survives every render; if that
 * holds, focus and caret were never lost in the first place and there is
 * nothing to restore.
 *
 * BLOCK 2 IS THE PROOF THAT THIS TEST FAILS ON THE PRE-FIX BEHAVIOUR. It
 * runs the old mechanism (`host.innerHTML = nextHtml`) against the same tree
 * and the same assertion, and shows the node identity is lost -- then runs
 * shadowPatchInto() and shows it is kept. Revert the fix and block 3 onward
 * fail; the functions they call stop existing.
 *
 * Run: node test_shadow_delegate_focus.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const JS = path.join(__dirname, "static", "js");
let n = 0;
const ok = (m) => console.log("ok " + (++n) + " " + m);

/* ── a DOM small enough to read, real enough to patch ──────────────────────
   The patch functions need: nodeType, tagName, attributes, dataset, id,
   childNodes, outerHTML, cloneNode, appendChild, replaceChild, remove. They
   never parse HTML themselves -- they hand a string to innerHTML -- so the
   shim resolves a string through TREES, and every test controls both sides. */
const TREES = {};

function el(tag, attrs, kids){
  const node = {
    nodeType: 1, tagName: tag.toUpperCase(), childNodes: [], parentNode: null,
    attributes: [], dataset: {}, id: "",
    getAttribute(k){ const a = node.attributes.find(x => x.name === k);
      return a ? a.value : null; },
    setAttribute(k, v){
      const a = node.attributes.find(x => x.name === k);
      if (a) a.value = String(v); else node.attributes.push({ name: k, value: String(v) });
      if (k === "id") node.id = String(v);
      if (k.indexOf("data-") === 0) node.dataset[dkey(k)] = String(v);
    },
    removeAttribute(k){
      const i = node.attributes.findIndex(x => x.name === k);
      if (i >= 0) node.attributes.splice(i, 1);
      if (k === "id") node.id = "";
      if (k.indexOf("data-") === 0) delete node.dataset[dkey(k)];
    },
    appendChild(c){ c.parentNode = node; node.childNodes.push(c); return c; },
    removeChild(c){ const i = node.childNodes.indexOf(c);
      if (i >= 0) node.childNodes.splice(i, 1);
      c.parentNode = null; return c; },
    replaceChild(nw, old){
      const i = node.childNodes.indexOf(old);
      if (i < 0) return old;
      nw.parentNode = node; node.childNodes[i] = nw; old.parentNode = null;
      return old;
    },
    remove(){ const p = node.parentNode; if (!p) return;
      const i = p.childNodes.indexOf(node);
      if (i >= 0) p.childNodes.splice(i, 1);
      node.parentNode = null; },
    cloneNode(){ const c = el(tag, attrsOf(node), node.childNodes.map(k => k.cloneNode(true)));
      return c; },
    /* enough of querySelector for the selectors the source uses:
       comma-separated "#id" and "[attr]", plus the one DESCENDANT pair
       ("[data-shnewhost] [data-shnewtalk]"), matched against descendants */
    querySelector(sel){
      const parts = String(sel).split(",").map(s => s.trim()).filter(Boolean);
      const one = (p, x) => x.nodeType === 1 && (p[0] === "#"
        ? x.id === p.slice(1)
        : x.getAttribute(p.replace(/^\[|\]$/g, "")) !== null);
      const hit = (x) => parts.some(p => {
        const steps = p.split(/\s+/);
        if (steps.length === 1) return one(p, x);
        if (!one(steps[steps.length - 1], x)) return false;
        for (let a = x.parentNode; a; a = a.parentNode)
          if (one(steps[0], a)) return true;          /* two steps is enough */
        return false;
      });
      const walk = (x) => {
        for (const k of (x.childNodes || [])){
          if (hit(k)) return k;
          const r = walk(k); if (r) return r;
        }
        return null;
      };
      return walk(node);
    },
    closest(sel){
      const attr = String(sel).replace(/^\[|\]$/g, "");
      for (let x = node; x; x = x.parentNode)
        if (x.nodeType === 1 && x.getAttribute && x.getAttribute(attr) !== null) return x;
      return null;
    },
    get firstChild(){ return node.childNodes[0] || null; },
    get firstElementChild(){
      return node.childNodes.find(k => k.nodeType === 1) || null; },
    get outerHTML(){ return ser(node); },
    get innerHTML(){ return node.childNodes.map(ser).join(""); },
    set innerHTML(html){
      node.childNodes.forEach(k => { k.parentNode = null; });
      node.childNodes = [];
      const make = TREES[html];
      if (!make) throw new Error("test shim: no registered tree for html:\n" + html);
      make().forEach(k => node.appendChild(k));
    },
  };
  Object.keys(attrs || {}).forEach(k => node.setAttribute(k, attrs[k]));
  (kids || []).forEach(k => node.appendChild(k));
  return node;
}
const dkey = (k) => k.slice(5).replace(/-([a-z])/g, (m, c) => c.toUpperCase());
const attrsOf = (nd) => nd.attributes.reduce((o, a) => (o[a.name] = a.value, o), {});
const txt = (s) => ({ nodeType: 3, nodeValue: s, parentNode: null,
  remove(){ const p = this.parentNode; if (!p) return;
    const i = p.childNodes.indexOf(this); if (i >= 0) p.childNodes.splice(i, 1); },
  cloneNode(){ return txt(this.nodeValue); } });
function ser(nd){
  if (nd.nodeType === 3) return nd.nodeValue;
  const a = nd.attributes.map(x => ` ${x.name}="${x.value}"`).join("");
  const t = nd.tagName.toLowerCase();
  return `<${t}${a}>${nd.childNodes.map(ser).join("")}</${t}>`;
}
const find = (root, attr) => {
  if (root.nodeType === 1 && root.dataset && root.dataset[attr] !== undefined) return root;
  for (const k of (root.childNodes || [])){ const r = find(k, attr); if (r) return r; }
  return null;
};

/* the real screen's shape, down to the nesting that matters:
   #scBody > .shwork > [.shwleft(task list), .shwright > host > panel > textarea] */
function screenTree(taskLabel){
  return [el("div", { class: "shwork" }, [
    el("aside", { class: "shwleft" }, [
      el("div", { class: "shtasks" }, [txt(taskLabel)]),
    ]),
    el("section", { class: "shwright" }, [
      el("header", { class: "shwhead" }, [txt("New task")]),
      el("div", { class: "shnewhost", "data-shnewhost": "1" }, []),
    ]),
  ])];
}
function mountedPanel(){
  return el("div", { class: "shnewchat" }, [
    el("div", { class: "shwcomp" }, [
      el("textarea", { class: "shcompose", "data-shnewtalk": "1" }, []),
      el("button", { class: "shsend", "data-shnewsend": "1" }, [txt("↑")]),
    ]),
  ]);
}

function boot(){
  const overlay = fs.readFileSync(path.join(JS, "15-shadow-overlay.js"), "utf8");
  const src = fs.readFileSync(path.join(JS, "16-shadow-home.js"), "utf8");
  const ctx = {
    console, Date, setTimeout: (f) => f,
    esc: (x) => String(x == null ? "" : x),
    escAttr: (x) => String(x == null ? "" : x),
    SCREENS: {}, TITLES: {}, S: {}, listeners: {},
    document: {
      addEventListener(t, f){ ctx.listeners[t] = f; },
      createElement(tag){ return el(tag, {}, []); },
      body: { appendChild(){} }, querySelector(){ return null; },
      activeElement: null,
    },
  };
  ctx.__SHADOW_NO_AUTOBOOT = true;
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(src, ctx);
  return ctx;
}

/* ── 1. which nodes are frozen ─────────────────────────────────────────── */
{
  const ctx = boot();
  assert.strictEqual(typeof ctx.shadowKeepNode, "function",
    "shadowKeepNode must exist -- the fix is the frozen node, not a restore");
  const ta = el("textarea", { "data-shnewtalk": "1" }, []);
  assert.strictEqual(ctx.shadowKeepNode(ta), true, "the textarea is frozen");
  assert.strictEqual(ctx.shadowKeepNode(el("div", { "data-shnewhost": "1" }, [])), true,
    "so is the host it is mounted into");
  assert.strictEqual(ctx.shadowKeepNode(el("div", { id: "scBody" }, [])), true,
    "and #scBody -- panesHtml renders it EMPTY, so a panes rebuild that "
    + "recreated it would throw the whole screen away to no purpose");
  assert.strictEqual(ctx.shadowKeepNode(el("div", { class: "shtasks" }, [])), false,
    "nothing else is frozen");

  const holder = el("section", {}, [el("div", {}, [ta])]);
  assert.strictEqual(ctx.shadowHoldsKeep(holder), true,
    "an ancestor of the textarea must be recursed into, never replaced");
  assert.strictEqual(ctx.shadowHoldsKeep(el("div", {}, [el("p", {}, [])])), false);
  ok("the frozen nodes are the textarea, its host and #scBody");
}

/* ── 2. THE CONTRAST: the old swap loses the node, the patch keeps it ──── */
{
  const ctx = boot();
  const nextHtml = "SCREEN/after";
  TREES[nextHtml] = () => screenTree("2 running");

  /* (a) the PRE-FIX mechanism, run against the same tree and the same
         assertion -- this is what made the founder re-place the cursor */
  {
    const scBody = el("div", { id: "scBody" }, screenTree("1 running"));
    find(scBody, "shnewhost").appendChild(mountedPanel());
    const before = find(scBody, "shnewtalk");
    before.value = "ship the referral flow";
    assert(before, "the box is mounted to begin with");

    scBody.innerHTML = nextHtml;                    /* what render() used to do */

    const after = find(scBody, "shnewtalk");
    assert.strictEqual(after, null,
      "PRE-FIX: the wholesale innerHTML swap removes the textarea outright -- "
      + "in a browser that is the blur, and the founder's lost cursor");
    assert.notStrictEqual(after, before);
  }

  /* (b) the fix: same tree, same new html, node kept */
  {
    const scBody = el("div", { id: "scBody" }, screenTree("1 running"));
    find(scBody, "shnewhost").appendChild(mountedPanel());
    const before = find(scBody, "shnewtalk");
    before.value = "ship the referral flow";

    const ran = ctx.shadowPatchInto(scBody, nextHtml);
    assert.strictEqual(ran, true, "the patch reports that it handled the write");

    const after = find(scBody, "shnewtalk");
    assert.strictEqual(after, before,
      "the SAME textarea object must still be in the tree -- identity is the "
      + "whole contract: a node that was never removed was never blurred");
    assert.strictEqual(after.value, "ship the referral flow",
      "and it still holds what was typed, because nothing rewrote it");

    /* the rest of the screen still updated, or the patch is just a no-op */
    assert.strictEqual(find(scBody, "shnewhost").parentNode.tagName, "SECTION");
    assert(scBody.innerHTML.indexOf("2 running") >= 0,
      "the task list around it must still re-render -- the panel is frozen, "
      + "the screen is not");
  }
  ok("the pre-fix swap loses the node; the patch keeps the same object");
}

/* ── 3. an unchanged subtree is not touched at all ─────────────────────── */
{
  const ctx = boot();
  const html = "SCREEN/same-left";
  TREES[html] = () => screenTree("1 running");

  const scBody = el("div", { id: "scBody" }, screenTree("1 running"));
  find(scBody, "shnewhost").appendChild(mountedPanel());
  const leftBefore = scBody.childNodes[0].childNodes[0];

  /* only the header text differs this pass */
  TREES[html] = () => { const t = screenTree("1 running");
    t[0].childNodes[1].childNodes[0].childNodes[0].nodeValue = "New task · draft";
    return t; };
  ctx.shadowPatchInto(scBody, html);

  assert.strictEqual(scBody.childNodes[0].childNodes[0], leftBefore,
    "a subtree whose markup did not change must be left alone entirely -- "
    + "replacing it would be the same needless churn innerHTML was");
  ok("unchanged subtrees are never replaced");
}

/* ── 4. closing + Delegate really does tear the panel down ─────────────── */
{
  const ctx = boot();
  const shut = "SCREEN/panel-closed";
  TREES[shut] = () => [el("div", { class: "shwork" }, [
    el("aside", { class: "shwleft" }, [el("div", { class: "shtasks" }, [txt("1 running")])]),
    el("section", { class: "shwright" }, [el("header", { class: "shwhead" }, [txt("Shadow")])]),
  ])];

  const scBody = el("div", { id: "scBody" }, screenTree("1 running"));
  find(scBody, "shnewhost").appendChild(mountedPanel());
  assert(find(scBody, "shnewtalk"), "mounted first");

  ctx.shadowPatchInto(scBody, shut);
  assert.strictEqual(find(scBody, "shnewtalk"), null,
    "a frozen node must not be immortal: when the slot genuinely goes away "
    + "the panel goes with it, or + Delegate could never be closed");
  ok("the panel is torn down when its slot disappears");
}

/* ── 5. mounted once, then updated in place ────────────────────────────── */
{
  const ctx = boot();
  ctx.S.shadowNewChat = { thread: [], busy: false, err: null, text: "" };
  const panelHtml = ctx.shadowNewTaskChatHtml();
  TREES[panelHtml] = () => [mountedPanel()];

  const host = el("div", { class: "shnewhost", "data-shnewhost": "1" }, []);
  ctx.document.querySelector = (q) => (q === "[data-shnewhost]" ? host : null);

  ctx.shadowMountNewTalk();                       /* first pass: build it */
  const box = find(host, "shnewtalk");
  assert(box, "the panel is built into the host on the first pass");
  box.value = "half a line";

  ctx.shadowMountNewTalk();                       /* every later pass */
  ctx.shadowMountNewTalk();
  assert.strictEqual(find(host, "shnewtalk"), box,
    "later passes must patch around the box, never rebuild it");
  assert.strictEqual(box.value, "half a line",
    "and must never write its value -- the DOM node is the draft now");
  ok("the box is built once and never rebuilt");
}

/* ── 6. render() is wired to all three points ──────────────────────────── */
{
  const src = fs.readFileSync(path.join(JS, "06-render.js"), "utf8");
  const body = /function render\(\)\{[\s\S]*?\n\}/.exec(src);
  assert(body, "render() must still exist");

  assert(/shadowPatchInto\(panesEl, panesHtml\)/.test(body[0]),
    "the PANES rebuild must step around a mounted box -- #scBody is inside "
    + "#panes, so that swap destroys the screen too");
  assert(/shadowPatchInto\(scBody, html\)/.test(body[0]),
    "and so must the screen rebuild");
  assert(/typeof shadowMountNewTalk === "function"\) shadowMountNewTalk\(\)/.test(body[0]),
    "render() must mount the panel after the screen pass");
  /* both swaps must still be reachable for every other screen */
  assert(/panesEl\.innerHTML = panesHtml/.test(body[0])
      && /scBody\.innerHTML = html/.test(body[0]),
    "every other screen must still take the original innerHTML path -- this "
    + "is one screen's fix, not a new renderer");
  ok("render() gates both swaps and mounts the panel");
}

/* ── 7. nothing re-places the cursor in the compose path ───────────────── */
{
  const home = fs.readFileSync(path.join(JS, "16-shadow-home.js"), "utf8");
  const render = fs.readFileSync(path.join(JS, "06-render.js"), "utf8");

  assert(!/shadowRestoreNewTalk/.test(home) && !/shadowRestoreNewTalk/.test(render),
    "the caret-restore written for this box must be gone -- a mounted node "
    + "has nothing to restore, and the founder ruled the restore out");
  assert(!/data-shnewtalk/.test(render),
    "render() must not track the box for focus restoration any more");
  assert(!/shadowNewTalkCaret|shadowNewTalkFocus/.test(home),
    "no caret or focus state is kept for this box");

  /* the mount path itself must contain no focus or selection call */
  const mount = /function shadowMountNewTalk\(\)\{[\s\S]*?\n\}/.exec(home);
  const patch = /function shadowPatchInto\([\s\S]*?\n\}/.exec(home);
  assert(mount && patch, "the mount and the patch must exist");
  [mount[0], patch[0]].forEach((fn) => {
    assert(!/\.focus\(/.test(fn), "no focus() in the mount path");
    assert(!/selectionStart|setSelectionRange/.test(fn), "no caret writes");
    assert(!/setTimeout/.test(fn), "no deferred anything");
  });
  ok("no refocus, no caret write, no timer in the compose path");
}

/* ── 8. CHURN MAY NOT DO WHAT CLOSING DOES ────────────────────────────────
   Block 4 proves a slot that goes away takes the panel with it. That is right
   for + Delegate being shut and wrong for everything else, and by position
   alone the two are the same event: a list that got shorter because a stray
   row stopped rendering looked exactly like a close, and removed the textarea
   the founder was mid-sentence in. The discriminator is the INCOMING markup
   -- it still carries a host here, so the panel is still open. */
{
  const ctx = boot();
  const html = "SCREEN/shorter-but-still-open";
  /* new markup: same screen, one fewer child under .shwright, host KEPT */
  TREES[html] = () => [el("div", { class: "shwork" }, [
    el("section", { class: "shwright" }, [
      el("header", { class: "shwhead" }, [txt("New task")]),
      el("div", { class: "shnewhost", "data-shnewhost": "1" }, []),
    ]),
  ])];

  /* old tree: an extra row sits BEFORE the host, so dropping it shortens the
     list and the host lands in the trailing slot the removal loop clears */
  const scBody = el("div", { id: "scBody" }, [el("div", { class: "shwork" }, [
    el("section", { class: "shwright" }, [
      el("header", { class: "shwhead" }, [txt("New task")]),
      el("div", { class: "shtip" }, [txt("a row that stopped rendering")]),
      el("div", { class: "shnewhost", "data-shnewhost": "1" }, [mountedPanel()]),
    ]),
  ])]);
  const before = find(scBody, "shnewtalk");
  before.value = "half a sentence";

  ctx.shadowPatchInto(scBody, html);

  assert.strictEqual(find(scBody, "shnewtalk"), before,
    "a child list that merely got SHORTER is churn, and churn may not remove "
    + "the box -- only markup that has stopped asking for a host may");
  assert.strictEqual(before.value, "half a sentence");
  ok("a shorter child list does not count as closing the panel");
}

/* ── 9. nor does a slot that changed TAG ──────────────────────────────── */
{
  const ctx = boot();
  const html = "SCREEN/retagged";
  TREES[html] = () => [el("div", { class: "shwork" }, [
    /* the same slot, rendered as a DIV this pass instead of a SECTION */
    el("div", { class: "shwright" }, [
      el("header", { class: "shwhead" }, [txt("New task")]),
      el("div", { class: "shnewhost", "data-shnewhost": "1" }, []),
    ]),
  ])];

  const scBody = el("div", { id: "scBody" }, [el("div", { class: "shwork" }, [
    el("section", { class: "shwright" }, [
      el("header", { class: "shwhead" }, [txt("New task")]),
      el("div", { class: "shnewhost", "data-shnewhost": "1" }, [mountedPanel()]),
    ]),
  ])]);
  const before = find(scBody, "shnewtalk");

  ctx.shadowPatchInto(scBody, html);

  assert.strictEqual(find(scBody, "shnewtalk"), before,
    "a tag change around the box is a wholesale replaceChild, which is the "
    + "blur again -- the old subtree must be left standing instead");
  ok("a retagged ancestor does not take the box with it");
}

/* ── 10. and a duplicate host may not start a second box ──────────────── */
{
  const ctx = boot();
  ctx.S.shadowNewChat = { thread: [], busy: false, err: null, text: "" };
  const panelHtml = ctx.shadowNewTaskChatHtml();
  TREES[panelHtml] = () => [mountedPanel()];

  /* what block 9 can leave behind for one pass: the live host, and a fresh
     EMPTY one cloned in beside it */
  const empty = el("div", { class: "shnewhost", "data-shnewhost": "1" }, []);
  const live = el("div", { class: "shnewhost", "data-shnewhost": "1" }, []);
  const root = el("section", {}, [empty, live]);
  ctx.document.querySelector = (q) => root.querySelector(q);

  ctx.shadowMountNewTalk();                    /* nothing mounted yet: first */
  const box = find(root, "shnewtalk");
  assert(box, "the first pass builds into whichever host it found");
  box.value = "half a sentence";

  ctx.shadowMountNewTalk();                    /* now one host holds a box */
  assert.strictEqual(find(root, "shnewtalk"), box,
    "the mount must follow the host that HOLDS the box, not document order -- "
    + "an empty host means 'build it', and building it again is the blur");
  assert.strictEqual(box.value, "half a sentence");
  assert.strictEqual(root.innerHTML.split("data-shnewtalk").length - 1, 1,
    "and exactly one box exists, never two");
  ok("a duplicate host never starts a second box");
}

console.log("\n" + n + " blocks passed -- the + Delegate box is mounted, not re-rendered");
