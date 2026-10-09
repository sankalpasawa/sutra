#!/usr/bin/env node
/* test_shadow_attachments.js -- images the founder shows Shadow
   (founder, 2026-10-08). The attach bar on every box that talks to Shadow,
   paste / drop, the upload, and each sender carrying the images: the Shadow
   composer (a task's chat or Shadow itself), + Delegate, and the form that
   answers Shadow's question. Thumbnails in the conversation and a strip of
   the task's images.

   Run: node test_shadow_attachments.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const overlay = fs.readFileSync(path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const home = fs.readFileSync(path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");

function fresh(){
  const ctx = {
    console, Date, setTimeout: (fn) => ({ fn }), setImmediate, Promise,
    esc: (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;"),
    SCREENS: {}, TITLES: {}, S: {}, listeners: {}, posts: [], renders: 0,
    document: { addEventListener(t, fn){ ctx.listeners[t] = fn; },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {}, click(){} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
      querySelectorAll(){ return []; } },
    URL: { createObjectURL: () => "blob:local", revokeObjectURL(){} },
  };
  ctx.FileReader = function(){
    const fr = this;
    fr.readAsDataURL = () => setImmediate(() => {
      fr.result = "data:image/png;base64,QUJD"; fr.onload && fr.onload(); });
  };
  ctx.scheduleRender = () => { ctx.renders++; };
  ctx.fetch = async (url, opts) => {
    const body = JSON.parse((opts && opts.body) || "{}");
    ctx.posts.push({ url, body });
    if (url === "/api/shadow/attachments")
      return { ok: true, status: 200, json: async () => (
        { id: "img-00000000000000a1", name: body.name,
          url: "/api/shadow/attachments/img-00000000000000a1" }) };
    return { ok: true, status: 200, json: async () => ({ reply: "ok" }) };
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(home, ctx);
  return ctx;
}
const settle = () => new Promise(r => setImmediate(() => setImmediate(() => setImmediate(r))));
const READY = { id: "img-00000000000000a1", name: "design.png",
                url: "/api/shadow/attachments/img-00000000000000a1" };
const postsTo = (ctx, url) => ctx.posts.filter(p => p.url === url);

(async () => {
  /* 1. thumbnails: links that open the image; nothing when there are none */
  {
    const ctx = fresh();
    const h = ctx.shadowImagesHtml([READY]);
    assert(/class="shimg" href="\/api\/shadow\/attachments\/img-00000000000000a1"/.test(h));
    assert(/<img src="\/api\/shadow\/attachments\/img-00000000000000a1"/.test(h));
    assert.strictEqual(ctx.shadowImagesHtml([]), "");
    assert.strictEqual(ctx.shadowImagesHtml(null), "");
    const said = ctx.shadowMsgHtml({ who: "founder", text: "look", images: [READY] });
    assert(/look/.test(said) && /shimg/.test(said), "a founder line carries its images");
    assert(!/shimg/.test(ctx.shadowMsgHtml({ who: "founder", text: "plain" })));
  }

  /* 2. the bar: a paperclip, thumbnails with x, errors in words */
  {
    const ctx = fresh();
    assert(/data-shattach="home"/.test(ctx.shadowAttachBarHtml("home")), "a paperclip");
    ctx.S.shadowAttach = { home: [Object.assign({}, READY),
                                  { name: "big.png", pending: true, preview: "blob:x" },
                                  { name: "doc.pdf", error: "Only images can be attached" }] };
    const h = ctx.shadowAttachBarHtml("home");
    assert(/data-shattrm="home"\s+data-shatti="0"/.test(h), "x on each thumbnail");
    assert(/shatt busy/.test(h), "an upload in flight shows");
    assert(/Only images can be attached/.test(h), "a refusal is said");
    assert(ctx.shadowAttachReady("home"));
    const took = ctx.shadowAttachTake("home");
    assert.deepStrictEqual(JSON.parse(JSON.stringify(took)), [Object.assign({ kind: "image" }, READY)].map(o => JSON.parse(JSON.stringify(Object.assign({}, READY, { kind: "image" })))), "only uploaded files go, each with its kind");
    assert.strictEqual(ctx.S.shadowAttach.home.length, 1, "the one still uploading stays");
  }

  /* 3. which bar a paste or drop belongs to */
  {
    const ctx = fresh();
    assert.strictEqual(ctx.shadowAttachKeyFor({ dataset: { shhomecompose: "1" } }), "home");
    assert.strictEqual(ctx.shadowAttachKeyFor({ dataset: { shnewtalk: "1" } }), "new");
    assert.strictEqual(ctx.shadowAttachKeyFor({ dataset: {},
      closest: () => ({ dataset: { shivmid: "m-1" } }) }), "iv:m-1");
    assert.strictEqual(ctx.shadowAttachKeyFor({ dataset: {}, closest: () => null }), null);
  }

  /* 4. paste a screenshot: uploaded, and only images are taken */
  {
    const ctx = fresh();
    let prevented = 0;
    ctx.listeners.paste({ target: { dataset: { shhomecompose: "1" } },
      preventDefault(){ prevented++; },
      clipboardData: { files: [{ name: "shot.png", type: "image/png" }] } });
    await settle();
    assert.strictEqual(prevented, 1);
    const up = postsTo(ctx, "/api/shadow/attachments");
    assert.strictEqual(up.length, 1);
    assert.strictEqual(up[0].body.content_b64, "QUJD", "the data: prefix is stripped");
    assert.strictEqual(ctx.S.shadowAttach.home[0].id, READY.id);
    ctx.listeners.paste({ target: { dataset: { shhomecompose: "1" } },
      preventDefault(){ prevented++; }, clipboardData: { files: [] } });
    assert.strictEqual(prevented, 1, "pasting text is untouched");
  }

  /* 5. a task's chat: the images ride with the line */
  {
    const ctx = fresh();
    ctx.S.shadowTalk = { live: {}, text: "like this", busy: false,
                         attachments: [READY] };
    await ctx.shadowTalkSend("m-7", null);
    const sent = postsTo(ctx, "/api/shadow/tasks/m-7/chat");
    assert.strictEqual(sent.length, 1);
    /* a task's chat is not a saved conversation: id and name, as before */
    assert.deepStrictEqual(sent[0].body.attachments, [{ id: READY.id, name: "design.png" }]);
    const live = ctx.shadowTalkLive("m-7");
    assert(live[0].images && live[0].images[0].id === READY.id, "shown in the thread");
  }

  /* 6. Shadow itself (no task): sendToShadow carries them */
  {
    const ctx = fresh();
    ctx.S.shadowThread = [];
    await ctx.sendToShadow("what is this?", { attachments: [READY] });
    const sent = postsTo(ctx, "/api/shadow/chat");
    assert.deepStrictEqual(sent[0].body.attachments, [{ id: READY.id, name: "design.png" }]);
    assert(ctx.S.shadowThread[0].images, "the founder's row keeps them");
    ctx.posts = [];
    ctx.S.shadowThread = [];
    await ctx.sendToShadow("plain");
    assert(!("attachments" in postsTo(ctx, "/api/shadow/chat")[0].body),
      "no images: the request is as it was");
  }

  /* 7. answering Shadow's question: the form has a bar and sends them */
  {
    const ctx = fresh();
    const m = { id: "m-9", state: "blocked", block_reason: "needs_founder",
      intervention: { id: "iv-1", question: "Which design?",
        fields: [{ key: "pick", type: "text", label: "Pick" }] } };
    ctx.S.shadowMissions = [m];
    const form = ctx.shadowInterventionHtml(m);
    assert(/data-shivmid="m-9"/.test(form) && /data-shattach="iv:m-9"/.test(form));
    ctx.S.shadowAttach = { "iv:m-9": [Object.assign({}, READY)] };
    if (typeof ctx.shadowIvDraft === "function")
      ctx.shadowIvDraft("m-9").values.pick = "this one";
    await ctx.shadowSendIntervention("m-9");
    const sent = ctx.posts.filter(p => /\/act$/.test(p.url));
    assert.strictEqual(sent[0].body.action, "intervene");
    assert.deepStrictEqual(sent[0].body.attachments, [{ id: READY.id, name: "design.png" }]);
  }

  /* 8. a task's images stay visible after a reload */
  {
    const ctx = fresh();
    assert.strictEqual(ctx.shadowTaskImagesHtml({ id: "m-1" }), "");
    const h = ctx.shadowTaskImagesHtml({ id: "m-1", attachments: [
      { id: READY.id, name: "design.png", source: "intake" }] });
    assert(/Files you shared/.test(h) && /shimg/.test(h));
  }

  /* 9. + Delegate: the opening line carries its images, even with no words */
  {
    const ctx = fresh();
    ctx.S.shadowThreads = {};
    ctx.S.shadowAttach = { "new": [Object.assign({}, READY)] };
    ctx.shadowNewChat().text = "";
    await ctx.shadowNewTalk();
    const sent = postsTo(ctx, "/api/shadow/chat");
    assert.strictEqual(sent.length, 1, "an image alone opens the conversation");
    assert.strictEqual(sent[0].body.intake, true);
    /* + kind (2026-10-09): the server saves it with the line, so a reload
       draws an image as an image and a PDF as a chip */
    assert.deepStrictEqual(sent[0].body.attachments,
      [{ id: READY.id, name: "design.png", kind: "image" }]);
    assert.deepStrictEqual(ctx.S.shadowAttach["new"], [], "the bar empties");
    ctx.posts = [];
    ctx.shadowNewChat().text = "";
    await ctx.shadowNewTalk();
    assert.strictEqual(postsTo(ctx, "/api/shadow/chat").length, 0,
      "no words and no images: nothing is sent");
  }

  /* 10. PDFs and text files (2026-10-08): accepted, drawn as a chip */
  {
    const ctx = fresh();
    assert.strictEqual(ctx.shadowAttachKind({ type: "application/pdf", name: "a.pdf" }), "pdf");
    assert.strictEqual(ctx.shadowAttachKind({ type: "", name: "notes.md" }), "text");
    assert.strictEqual(ctx.shadowAttachKind({ type: "image/png", name: "x.png" }), "image");
    assert.strictEqual(ctx.shadowAttachKind({ type: "application/zip", name: "a.zip" }), null);
    const chip = ctx.shadowImagesHtml([{ id: "att-00000000000000b2", name: "spec.pdf", kind: "pdf" }]);
    assert(/class="shfile"/.test(chip) && /PDF/.test(chip) && /spec\.pdf/.test(chip)
           && !/<img/.test(chip), "a PDF is a chip, not a broken thumbnail");
    ctx.S.shadowAttach = { home: [{ id: "att-00000000000000b3", name: "plan.md", kind: "text", url: "/x" }] };
    const bar = ctx.shadowAttachBarHtml("home");
    assert(/shatt doc/.test(bar) && /TXT/.test(bar) && /plan\.md/.test(bar));
    let prevented = 0;
    ctx.listeners.drop({ target: { dataset: { shhomecompose: "1" } },
      preventDefault(){ prevented++; },
      dataTransfer: { files: [{ name: "spec.pdf", type: "application/pdf" }] } });
    assert.strictEqual(prevented, 1, "a dropped PDF is taken");
    ctx.listeners.drop({ target: { dataset: { shhomecompose: "1" } },
      preventDefault(){ prevented++; },
      dataTransfer: { files: [{ name: "a.zip", type: "application/zip" }] } });
    assert.strictEqual(prevented, 1, "a zip is left alone");
  }

  console.log("test_shadow_attachments.js: all passed");
})().catch((e) => { console.error(e); process.exit(1); });
