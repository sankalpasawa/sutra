#!/usr/bin/env node
/* test_goal_creation.js -- V5 slice 8: the goal confirmation flow.
   Run: node test_goal_creation.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const css = fs.readFileSync(path.join(__dirname,"static","panel.css"),"utf8");
const load = f => fs.readFileSync(path.join(__dirname,"static","js",f),"utf8");
const overlay = load("15-shadow-overlay.js");
const home = load("16-shadow-home.js");
const src = load("18-goal-workspace.js");

function fresh(opts){
  opts = opts || {};
  const posts = [], fetches = [], nudges = [], submits = [];
  const ctx = {
    console, Date, setTimeout:(fn)=>({fn}),
    requestAnimationFrame(fn){ (ctx.rafs=ctx.rafs||[]).push(fn); },
    esc:(x)=>String(x==null?"":x).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"),
    SCREENS:{}, TITLES:{}, S:{ ui:{dest:"focus"} }, DESTS:["now","focus","chats"],
    scheduleRender(){ ctx.renders=(ctx.renders||0)+1; },
    render(){ ctx.renders=(ctx.renders||0)+1; },
    renderShadowCard(){ ctx.cardRenders=(ctx.cardRenders||0)+1; },
    openScreen(id){ ctx.opened=id; ctx.S.screen=id; },
    goDest(d){ ctx.dest=d; },
    showNudge(t){ nudges.push(t); },
    submitTurn(text,sid){ submits.push({text,sid}); },
    fetch(url){ fetches.push(url);
      const body=(opts.responses||{})[url];
      if(body===undefined) return Promise.resolve({ok:false,status:404,json:()=>Promise.resolve({})});
      return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve(body)}); },
    document:{ addEventListener(t,fn){ (ctx.handlers[t]=ctx.handlers[t]||[]).push(fn); },
      createElement(){ return {setAttribute(){},remove(){},dataset:{},classList:{add(){}}}; },
      body:{appendChild(){},classList:{add(){}}}, querySelector(){ return null; } },
    handlers:{}, posts, fetches, nudges, submits,
  };
  ctx.window=ctx; ctx.globalThis=ctx; ctx.__SHADOW_NO_AUTOBOOT=true;
  vm.createContext(ctx);
  vm.runInContext(overlay,ctx); vm.runInContext(home,ctx);
  ctx.shadowPost=(url,body)=>{ posts.push({url,body});
    const r=(opts.postResponses||{})[url];
    if(r) return Promise.resolve(Object.assign({json:()=>Promise.resolve(r.body||{})},r));
    return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve({})}); };
  vm.runInContext(src,ctx);
  return ctx;
}
const PROP = () => ({ ts: 1000, asked:"Get this referral workflow configured and make sure it's working.",
  outcome:"get the referral workflow configured and working",
  done_when:[{tier:"contains_artifact",check:"referral webhook returns 200"},
             {tier:"verify",check:"end-to-end referral test"}],
  target_session:"01a081", needs_criteria:false, needs_target:false });
let n=0; const ok=m=>console.log("ok "+(++n)+" "+m);
const click=(ctx,dataset)=>ctx.handlers.click.forEach(f=>f({target:{dataset,closest:()=>null}}));
const input=(ctx,dataset,value)=>ctx.handlers.input.forEach(f=>f({target:{dataset,value}}));

/* 1. a natural-language ask arrives through the EXISTING shadow path */
{
  const ctx=fresh();
  ctx.S.shadowThreads={global:[]}; ctx.S.shadowChat="global";
  ctx.S.shadowThread.push({who:"shadow", goalProposal:PROP()});
  const out=ctx.shadowCardHtml();
  assert(/Set a goal for this chat\?/.test(out),"the card renders in the thread");
  assert(!/undefined/.test(out),"no undefined leaks");
  ok("proposal renders in the existing Shadow thread");
}
/* 2/3/4. outcome, done_when and target chat are all displayed */
{
  const ctx=fresh();
  const out=ctx.goalProposalHtml(PROP());
  assert(/get the referral workflow configured and working/.test(out),"outcome shown");
  assert(/referral webhook returns 200/.test(out),"check 1 shown");
  assert(/end-to-end referral test/.test(out),"check 2 shown");
  assert(/2 checks/.test(out),"check count shown");
  assert(/01a081/.test(out),"target chat shown");
  assert(/You asked/.test(out) && /make sure it's working/.test(out),
    "what the founder ASKED is kept visibly apart");
  assert(/Outcome — what Shadow will pursue/.test(out),"what Shadow believes");
  assert(/Done when — what will count as done/.test(out),"what counts as done");
  assert(/does not start a new chat/.test(out),"and it says so");
  ok("outcome, done_when, target chat and the ask are all displayed");
}
/* 5. confirm creates exactly one goal, via the existing API */
{
  const ctx=fresh({ postResponses:{ "/api/shadow/goals":{ok:true,status:200,
    body:{id:"g-new1",state:"draft",target_session:"01a081"}} },
    responses:{ "/api/shadow/goals":{goals:[]} } });
  const p=PROP(); ctx.S.shadowThreads={global:[{who:"shadow",goalProposal:p}]};
  ctx.S.shadowChat="global";
  ctx.goalCreateFromProposal(ctx.goalProposalKey(p)).then(g=>{
    const creates=ctx.posts.filter(x=>x.url==="/api/shadow/goals");
    assert.strictEqual(creates.length,1,"exactly one create POST");
    assert.strictEqual(creates[0].body.outcome,p.outcome,"the edited outcome");
    assert.strictEqual(creates[0].body.target_session,"01a081","the same chat");
    assert.strictEqual(creates[0].body.done_when.length,2,"both checks");
    assert.strictEqual(g.state,"draft","created in draft");
    assert.strictEqual(p.createdId,"g-new1","the card remembers the id");
    ok("confirm creates exactly one goal in draft");
    /* 6. it shows the created goal with the existing Start action */
    const made=ctx.goalProposalHtml(p);
    assert(/Goal created · draft/.test(made),"created state shown");
    assert(/Nothing is running yet/.test(made),"honest: not started");
    assert(/data-gwpropstart="g-new1"/.test(made),"Start offered");
    ok("created goal shows draft + the Start action");
  });
}
/* 7/8/9. start uses the existing action, re-fetches, then navigates */
{
  const ctx=fresh({ postResponses:{ "/api/shadow/goals/g-new1/act":{ok:true,status:200,body:{}} },
    responses:{ "/api/shadow/goals/g-new1":{id:"g-new1",state:"working",
      target_session:"01a081",outcome:"o",checks:[],unmet:[],attempts:[],learned:[],
      checks_label:"0 of 1 checks"}, "/api/shadow/goals":{goals:[]} } });
  ctx.goalStartCreated("g-new1").then(after=>{
    const acts=ctx.posts.filter(x=>x.url==="/api/shadow/goals/g-new1/act");
    assert.strictEqual(acts.length,1,"one act POST");
    assert.strictEqual(acts[0].body.action,"start","the EXISTING start action");
    assert(ctx.fetches.includes("/api/shadow/goals/g-new1"),
      "re-fetched the goal rather than trusting the response");
    assert(ctx.fetches.includes("/api/shadow/goals"),"and the list");
    assert.strictEqual(after.state,"working","renders the SERVER's state");
    assert.strictEqual(ctx.opened,"goal","navigated to the slice 7 workspace");
    assert.strictEqual(ctx.S.goalSel,"g-new1","on that goal");
    assert(ctx.nudges.some(t=>/Working/.test(t)),"and only then says working");
    ok("start uses the existing action, re-fetches, navigates");
  });
}
/* 8b. start does NOT claim working when the server has not said so */
{
  const ctx=fresh({ postResponses:{ "/api/shadow/goals/g-x/act":{ok:true,status:200,body:{}} },
    responses:{ "/api/shadow/goals/g-x":{id:"g-x",state:"draft",target_session:"s",
      outcome:"o",checks:[],unmet:[],attempts:[],learned:[],checks_label:"0 of 0 checks"},
      "/api/shadow/goals":{goals:[]} } });
  ctx.goalStartCreated("g-x").then(()=>{
    assert(!ctx.nudges.some(t=>/^Working/.test(t)),
      "never claims working while the server says draft");
    assert(ctx.nudges.some(t=>/real state/.test(t)),"says what it actually knows");
    ok("start never over-claims");
  });
}
/* 10/11. the existing chat is preserved and nothing is cloned */
{
  const ctx=fresh({ postResponses:{ "/api/shadow/goals":{ok:true,status:200,
    body:{id:"g-2",state:"draft"}} }, responses:{ "/api/shadow/goals":{goals:[]} } });
  const p=PROP(); ctx.S.shadowThreads={global:[{who:"shadow",goalProposal:p}]};
  ctx.S.shadowChat="global";
  ctx.goalCreateFromProposal(ctx.goalProposalKey(p)).then(()=>{
    assert.strictEqual(ctx.posts[0].body.target_session,"01a081","same chat");
    assert.strictEqual(ctx.submits.length,0,"nothing was sent into any chat");
    assert(!ctx.posts.some(x=>/session|chat/.test(x.url)),"no chat was created");
    ok("target_session preserved, no chat cloned");
  });
}
/* 12. cancel creates nothing */
{
  const ctx=fresh();
  const p=PROP(); const thread=[{who:"shadow",goalProposal:p}];
  ctx.S.shadowThreads={global:thread}; ctx.S.shadowChat="global";
  ctx.goalCancelProposal(ctx.goalProposalKey(p));
  assert.strictEqual(ctx.S.shadowThread.length,0,"the card is gone");
  assert.strictEqual(ctx.posts.length,0,"and nothing was posted");
  ok("cancel creates nothing");
}
/* 13. an incomplete proposal never fabricates criteria */
{
  const ctx=fresh();
  const vague=Object.assign(PROP(),{outcome:"make the referral thing work",
    done_when:[], needs_criteria:true});
  const out=ctx.goalProposalHtml(vague);
  assert(/could not tell what would count as done/.test(out),
    "the ambiguity is surfaced");
  assert(/it will not guess/.test(out),"and stated as a refusal to guess");
  assert(/0 checks/.test(out),"zero, not an invention");
  assert(/disabled/.test(out),"Create is blocked until the founder says");
  /* and it becomes creatable once the founder supplies one */
  const key=ctx.goalProposalKey(vague);
  ctx.S.shadowThreads={global:[{who:"shadow",goalProposal:vague}]};
  ctx.S.shadowChat="global";
  input(ctx,{gwpropcriteria:key},"referral test passes\n");
  const out2=ctx.goalProposalHtml(vague);
  assert(!/disabled/.test(out2),"the founder's own criterion unblocks it");
  assert(/1 check/.test(out2),"counted honestly");
  ok("no fabricated completion criteria");
}
/* 13b. no target chat is surfaced, not guessed */
{
  const ctx=fresh();
  const out=ctx.goalProposalHtml(Object.assign(PROP(),
    {target_session:null,needs_target:true}));
  assert(/no chat in focus/.test(out),"says there is no target");
  assert(/disabled/.test(out),"and refuses to create");
  ok("missing target chat is surfaced");
}
/* 14. an API failure is shown honestly */
{
  const ctx=fresh({ postResponses:{ "/api/shadow/goals":{ok:false,status:409,
    body:{detail:"session 01a081 already has an active goal"}} },
    responses:{ "/api/shadow/goals":{goals:[]} } });
  const p=PROP(); ctx.S.shadowThreads={global:[{who:"shadow",goalProposal:p}]};
  ctx.S.shadowChat="global";
  ctx.goalCreateFromProposal(ctx.goalProposalKey(p)).then(g=>{
    assert.strictEqual(g,null,"nothing created");
    assert(/409/.test(p.error),"the status is stated");
    assert(/already has an active goal/.test(p.error),"and the reason");
    assert(/409/.test(ctx.goalProposalHtml(p)),"and it is rendered");
    assert(!p.createdId,"no phantom id");
    ok("API failure is shown honestly");
  });
}
/* 15. editing carries into the create call */
{
  const ctx=fresh({ postResponses:{ "/api/shadow/goals":{ok:true,status:200,
    body:{id:"g-3",state:"draft"}} }, responses:{ "/api/shadow/goals":{goals:[]} } });
  const p=PROP(); const key=ctx.goalProposalKey(p);
  ctx.S.shadowThreads={global:[{who:"shadow",goalProposal:p}]}; ctx.S.shadowChat="global";
  input(ctx,{gwpropoutcome:key},"ship the referral workflow end to end");
  input(ctx,{gwpropcriteria:key},"referral webhook returns 200\nintegration test green");
  ctx.goalCreateFromProposal(key).then(()=>{
    const b=ctx.posts[0].body;
    assert.strictEqual(b.outcome,"ship the referral workflow end to end","edited outcome");
    assert.strictEqual(b.done_when.length,2,"edited criteria");
    assert.strictEqual(b.done_when[1].check,"integration test green");
    ok("founder edits are what get created");
  });
}
/* 16. the card is reachable from the click handlers, and gated states hold */
{
  const ctx=fresh({ postResponses:{ "/api/shadow/goals":{ok:true,status:200,
    body:{id:"g-4",state:"draft"}} }, responses:{ "/api/shadow/goals":{goals:[]} } });
  const p=PROP(); const key=ctx.goalProposalKey(p);
  ctx.S.shadowThreads={global:[{who:"shadow",goalProposal:p}]}; ctx.S.shadowChat="global";
  click(ctx,{gwpropcreate:key});
  assert(ctx.posts.some(x=>x.url==="/api/shadow/goals"),"click wired to create");
  ok("click handlers are wired");
}
/* 17. the home thread renders the card too (same one thread) */
{
  const ctx=fresh();
  ctx.S.shadowHomeDark=false;
  ctx.S.shadowThreads={global:[{who:"shadow",goalProposal:PROP()}]};
  ctx.S.shadowChat="global";
  assert(/Set a goal for this chat\?/.test(ctx.shadowHomeHtml()),
    "Focus > Shadow renders it as well");
  ok("one thread, both surfaces");
}
/* 18. gated: no card styling invents a new visual system */
{
  assert(/\.gwprop\{/.test(css),"the card is styled");
  assert(/#B8945F/.test(css),"the Shadow accent");
  /* scoped to slice 8's OWN section: later slices append after it, so take
     the text BETWEEN the two section markers rather than everything after */
  const from=css.indexOf("slice 8");
  const to=css.indexOf("slice 9");
  const block=css.slice(from, to === -1 ? css.length : to);
  assert(/border-radius:12px/.test(block),"12px cards");
  assert(!/#[0-9a-fA-F]{6}/.test(block.replace(/#B8945F|#2D5A3E|#8B4A6B|#8B6B4A|#4A6B8B/g,"")),
    "no colours beyond the ratified v10 set");
  ok("no new visual system");
}
/* 19. escaping */
{
  const ctx=fresh();
  const out=ctx.goalProposalHtml(Object.assign(PROP(),
    {outcome:'<img src=x onerror=alert(1)>'}));
  assert(!/<img/.test(out),"escaped"); assert(/&lt;img/.test(out),"as text");
  ok("output is escaped");
}
setTimeout(()=>console.log("test_goal_creation.js: all green"),40);
