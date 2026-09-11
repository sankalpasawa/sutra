#!/usr/bin/env node
/* test_goal_live.js -- two corrections found by the live UI run of
   2026-09-11 (goal g-d804849d1400).

   ISSUE 1  the card stamped `contains_artifact` on EVERY check line --
            Shadow's proposed tiers and the founder's own typing alike --
            so the python-side tier contract would have been overwritten
            the moment the founder pressed Create. contains_artifact is a
            literal substring test; a criterion DESCRIPTION can never match
            it. The rule here mirrors shadow_protocol.tier_for.

   ISSUE 2  the workspace fetched ONCE per open. The mission ran two turns,
            evaluated its checks and blocked in 107s while the screen kept
            showing "WORKING, turn 0/20, 0 of 2" taken at Start.

   Run: node test_goal_live.js */
"use strict";
const fs=require("fs"), path=require("path"), vm=require("vm"), assert=require("assert");
const L=f=>fs.readFileSync(path.join(__dirname,"static","js",f),"utf8");
const overlay=L("15-shadow-overlay.js"), home=L("16-shadow-home.js"), src=L("18-goal-workspace.js");

function fresh(opts){
  opts=opts||{};
  const posts=[],fetches=[],timers=[];
  const ctx={ console,Date,
    /* a CONTROLLABLE clock: every setTimeout is captured, never fired by
       wall time, so "does a slow read overlap?" is decidable rather than raced */
    setTimeout(fn,ms){ const t={fn,ms,id:timers.length+1,live:true};
      timers.push(t); return t.id; },
    clearTimeout(id){ const t=timers.find(x=>x.id===id); if(t) t.live=false; },
    requestAnimationFrame(f){(ctx.rafs=ctx.rafs||[]).push(f);},
    esc:x=>String(x==null?"":x).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"),
    SCREENS:{},TITLES:{},S:{ui:{dest:"focus"}},DESTS:["now","focus","chats"],
    scheduleRender(){ctx.renders=(ctx.renders||0)+1;},
    render(){ctx.renders=(ctx.renders||0)+1;},
    renderShadowCard(){},
    openScreen(id){ctx.S.screen=id;},goDest(d){ctx.dest=d;},
    showNudge(){},submitTurn(){},
    fetch(u){ fetches.push(u);
      const b=(opts.responses||{})[u];
      if (opts.hang && opts.hang(u)) return new Promise(()=>{});   /* never settles */
      if (b===undefined) return Promise.resolve({ok:false,status:404,json:()=>Promise.resolve({})});
      const body = typeof b==="function" ? b() : b;
      return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve(body)});},
    document:{addEventListener(){},createElement(){return{setAttribute(){},remove(){},dataset:{},classList:{add(){}}};},
      body:{appendChild(){},classList:{add(){}}},querySelector(){return null;}},
    posts,fetches,timers };
  ctx.window=ctx; ctx.globalThis=ctx; ctx.__SHADOW_NO_AUTOBOOT=true;
  vm.createContext(ctx);
  vm.runInContext(overlay,ctx); vm.runInContext(home,ctx);
  ctx.shadowPost=(url,body)=>{posts.push({url,body});
    return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve({})});};
  vm.runInContext(src,ctx);
  return ctx;
}
const pending = ctx => ctx.timers.filter(t=>t.live);
const fire = async ctx => { const t=pending(ctx).pop(); if(!t) return false;
  t.live=false; await t.fn(); return true; };
const detail = o => Object.assign({ id:"g-1", state:"working",
  outcome:"the chat picks a language", target_session:"d5740ce7",
  checks_label:"0 of 2 checks", turn_label:"turn 0/20", turns_used:0,
  max_turns:20, attempt:1, block_reason:null, unmet:["x"], checks:[],
  attempts:[], learned:[], founder_guidance:[], blockers:[], history:[] }, o);
let n=0; const ok=m=>console.log("ok "+(++n)+" "+m);

/* ======================= ISSUE 1 -- the tier contract ==================== */
const SEMANTIC="An explicit winner named as the final choice — the word "
  +"'Python' or 'Go' stated as the pick, not a 'depends' hedge";

/* 1. the literal case is untouched */
{
  const ctx=fresh();
  assert.strictEqual(ctx.goalTierFor("Final choice:","contains_artifact"),
    "contains_artifact","a marker stays machine-checkable");
  assert.strictEqual(ctx.goalTierFor("BUILD GREEN","contains_artifact"),
    "contains_artifact");
  ok("literal contains_artifact is unchanged");
}
/* 2. the live flight's own check */
{
  const ctx=fresh();
  assert.strictEqual(ctx.goalTierFor(SEMANTIC,"contains_artifact"),
    "founder_confirm","a criterion description can never substring-match");
  assert.strictEqual(ctx.goalTierFor(
    "Three distinct concrete reasons listed for that pick","contains_artifact"),
    "founder_confirm");
  ok("semantic contains_artifact becomes founder_confirm");
}
/* 3/4/5. missing, verify, unknown */
{
  const ctx=fresh();
  assert.strictEqual(ctx.goalTierFor("anything",undefined),"founder_confirm");
  assert.strictEqual(ctx.goalTierFor("anything",null),"founder_confirm");
  assert.strictEqual(ctx.goalTierFor("run the test","verify"),"founder_confirm");
  for (const junk of ["telepathy","CONTAINS_ARTIFACT","contains-artifact",7])
    assert.strictEqual(ctx.goalTierFor("x",junk),"founder_confirm",String(junk));
  assert.strictEqual(ctx.goalTierFor(SEMANTIC,"founder_confirm"),"founder_confirm");
  ok("missing / verify / unknown all resolve to founder_confirm");
}
/* 6. the card no longer flattens every line to contains_artifact */
{
  const ctx=fresh();
  const rows=ctx.goalCriteriaToChecks("Final choice:\n"+SEMANTIC,
    { "Final choice:":"contains_artifact", [SEMANTIC]:"contains_artifact" });
  assert.strictEqual(rows.map(r=>r.tier).join(","),
    "contains_artifact,founder_confirm",
    "each line is judged on its own shape");
  assert.strictEqual(rows.map(r=>r.check).join("|"),
    "Final choice:|"+SEMANTIC,"and the wording is preserved, never dropped");
  ok("the proposal card stops flattening tiers");
}
/* 7. what the founder types by hand gets the same honest treatment */
{
  const ctx=fresh();
  const rows=ctx.goalCriteriaToChecks("exit code 0\nthree distinct reasons");
  assert.strictEqual(rows.map(r=>r.tier).join(","),
    "contains_artifact,founder_confirm");
  ok("founder-typed lines are judged by the same rule");
}
/* 8. the card SHOWS the resulting tier */
{
  const ctx=fresh();
  ctx.S.shadowChat="d5740ce7";
  const html=ctx.goalProposalHtml({ outcome:"pick a language",
    target_session:"d5740ce7",
    done_when:[{tier:"contains_artifact",check:"Final choice:"},
               {tier:"contains_artifact",check:SEMANTIC}] });
  assert(/Shadow checks this/.test(html),"the machine-checked one says so");
  assert(/you confirm this/.test(html),"and the other says who must judge it");
  assert(!/contains_artifact/.test(html),"no raw tier id reaches the founder");
  assert(html.indexOf("Shadow checks this")<html.indexOf("you confirm this"),
    "in the order the checks were given");
  ok("the card exposes each check's resulting tier");
}
/* 9. Create writes exactly the tiers the card displayed */
{
  const ctx=fresh({ responses:{} });
  const p={ outcome:"pick a language", target_session:"d5740ce7",
    done_when:[{tier:"contains_artifact",check:"Final choice:"},
               {tier:"contains_artifact",check:SEMANTIC}] };
  ctx.S.shadowThread=[{who:"shadow",goalProposal:p}];
  ctx.goalProposalHtml(p);                      /* seeds the draft */
  const key=ctx.goalProposalKey(p);
  ctx.goalCreateFromProposal(key);
  const post=ctx.posts.find(x=>x.url==="/api/shadow/goals");
  assert(post,"it POSTed");
  assert.strictEqual(post.body.done_when.map(c=>c.tier).join(","),
    "contains_artifact,founder_confirm",
    "what was shown is what is written");
  ok("Create persists the displayed tiers");
}

/* ======================= ISSUE 2 -- the live workspace =================== */
const open = (ctx,d) => { ctx.S.goalDetail={ "g-1": d };
  ctx.S.goalSel="g-1"; ctx.S.screen="goal"; };

/* 10. polling starts for working */
{
  const ctx=fresh();
  open(ctx,detail({state:"working"}));
  ctx.goalSyncPoll("g-1");
  assert.strictEqual(pending(ctx).length,1,"one armed timer");
  ok("polling starts for a working assignment");
}
/* 11. polling starts for verifying */
{
  const ctx=fresh();
  open(ctx,detail({state:"verifying"}));
  ctx.goalSyncPoll("g-1");
  assert.strictEqual(pending(ctx).length,1);
  ok("polling starts for a verifying assignment");
}
/* 12. and for no state at all yet (first paint, nothing fetched) */
{
  const ctx=fresh();
  ctx.S.goalDetail={}; ctx.S.goalSel="g-1"; ctx.S.screen="goal";
  ctx.goalSyncPoll("g-1");
  assert.strictEqual(pending(ctx).length,1,"an unknown state is not terminal");
  ok("polling starts before the first detail lands");
}
/* 13. terminal and holding states never poll */
{
  for (const st of ["draft","blocked","done","stopped"]){
    const ctx=fresh();
    open(ctx,detail({state:st}));
    ctx.goalSyncPoll("g-1");
    assert.strictEqual(pending(ctx).length,0,st+" must not poll");
  }
  ok("draft / blocked / done / stopped never poll");
}
/* 14. a running goal that blocks stops on the very next paint */
{
  const ctx=fresh();
  open(ctx,detail({state:"working"}));
  ctx.goalSyncPoll("g-1");
  assert.strictEqual(pending(ctx).length,1);
  ctx.S.goalDetail["g-1"]=detail({state:"blocked",block_reason:"ping_pong"});
  ctx.goalSyncPoll("g-1");
  assert.strictEqual(pending(ctx).length,0,"the loop cannot move it any more");
  ok("the poll stops the moment the assignment blocks");
}
/* 15. leaving the screen stops it */
{
  const ctx=fresh();
  open(ctx,detail({state:"working"}));
  ctx.goalStartPoll("g-1");
  assert.strictEqual(pending(ctx).length,1);
  ctx.closeGoal();
  assert.strictEqual(pending(ctx).length,0,"closeGoal disarms it");
  ok("leaving the workspace stops polling");
}
/* 16. and a tick that wakes on another screen disarms itself */
{
  const ctx=fresh();
  open(ctx,detail({state:"working"}));
  ctx.goalStartPoll("g-1");
  ctx.S.screen="chats";                       /* navigated away */
  fire(ctx).then(()=>{
    assert.strictEqual(pending(ctx).length,0,"no re-arm off-screen");
    assert.strictEqual(ctx.fetches.length,0,"and no request was made");
    ok("a tick on another screen disarms instead of fetching");
  });
}
/* 17. a slow request cannot create overlapping polls */
{
  const ctx=fresh({ hang:u=>u.indexOf("/api/shadow/goals/")===0 });
  open(ctx,detail({state:"working"}));
  ctx.goalStartPoll("g-1");
  fire(ctx).then(()=>{});                      /* tick 1: hangs forever */
  setImmediate(()=>{
    assert.strictEqual(pending(ctx).length,0,
      "nothing is re-armed until the in-flight read returns");
    assert.strictEqual(ctx.fetches.filter(u=>u.indexOf("/api/shadow/goals/")===0).length,1,
      "exactly one in-flight request");
    ok("a slow read cannot stack overlapping polls");
  });
}
/* 18. starting twice for the same goal does not double-arm */
{
  const ctx=fresh();
  open(ctx,detail({state:"working"}));
  ctx.goalStartPoll("g-1"); ctx.goalStartPoll("g-1"); ctx.goalSyncPoll("g-1");
  assert.strictEqual(pending(ctx).length,1,"idempotent");
  ok("re-arming is idempotent");
}
/* 19. refreshed progress actually reaches the screen */
{
  let turn = 0;
  const ctx=fresh({ responses:{
    "/api/shadow/goals/g-1": () => { turn += 1;
      return detail({ state: turn < 2 ? "working" : "blocked",
        block_reason: turn < 2 ? null : "ping_pong",
        checks_label: turn+" of 2 checks", turn_label:"turn "+turn+"/20" }); },
    "/api/sessions/d5740ce7": { messages: [] } } });
  open(ctx,detail({state:"working"}));
  assert(/turn 0\/20/.test(ctx.goalWorkspaceHtml()),"the stale snapshot");
  ctx.goalStartPoll("g-1");
  fire(ctx).then(async () => {
    const html = ctx.goalWorkspaceHtml();
    assert(/turn 1\/20/.test(html),"the refreshed turn is rendered: "+
      (html.match(/turn \d+\/20/)||[])[0]);
    assert(/1 of 2 checks/.test(html),"and the refreshed progress");
    assert(pending(ctx).length===1,"still live, so still polling");
    await fire(ctx);
    const h2 = ctx.goalWorkspaceHtml();
    assert(/blocked/.test(h2),"and the terminal state lands too");
    assert.strictEqual(pending(ctx).length,0,"which stops the poll");
    ok("refreshed state and progress actually render, then polling stops");
  });
}
/* 20. the transcript scroll position survives a poll */
{
  const ctx=fresh({ responses:{
    "/api/shadow/goals/g-1": detail({state:"working",turn_label:"turn 3/20"}),
    "/api/sessions/d5740ce7": { messages: [] } } });
  open(ctx,detail({state:"working"}));
  /* a transcript scroller parked away from the bottom */
  const el={ scrollTop:120, scrollHeight:2000, clientHeight:400,
             dataset:{gwsid:"d5740ce7"}, addEventListener(){}, __gwBound:true };
  ctx.document.querySelector = sel => sel===".gwturns" ? el : null;
  ctx.S.goalUserScrolled={ "d5740ce7": true };
  const before = ctx.goalScrollState();
  assert.strictEqual(before.pinned,false,"the founder had scrolled away");
  ctx.goalStartPoll("g-1");
  fire(ctx).then(()=>{
    ctx.goalRestoreScroll(before);
    assert.strictEqual(el.scrollTop,120,
      "a poll must not yank the founder back to the tail");
    assert.strictEqual(ctx.S.goalUserScrolled["d5740ce7"],true,
      "and their parked intent is remembered");
    ok("the transcript scroll position is preserved across a poll");
  });
}
/* 21. no socket, no synthetic progress, no new endpoint */
{
  /* comments FIRST: the poll's own doc-comment says the words "setInterval"
     and "socket" while explaining why it uses neither (same fold as the
     anti-pulse assertion in the slice-11 suite) */
  const code = src.replace(/\/\*[\s\S]*?\*\//g,"").replace(/^\s*\/\/.*$/gm,"");
  assert(!/new WebSocket|EventSource/.test(code),"no socket was introduced");
  assert(!/setInterval/.test(code),"chained setTimeout only");
  const body = src.slice(src.indexOf("function goalStartPoll"),
                         src.indexOf("function goalSyncPoll"));
  assert(/loadGoal\(gid\)/.test(body),"it reuses the existing loader");
  assert(!/fetch\(/.test(body),"and adds no endpoint of its own");
  ok("no socket, no new endpoint, no synthetic progress");
}
/* ============== ISSUE 3 -- the RHS target chat, live ====================
   The founder must be able to WATCH the Shadow <-> chat turns accumulate.
   goalMessages preferred the pane's `turns` array whenever it was
   non-empty; that array is live only while the pane is OPEN, and an
   Assignment's target has no pane open (Shadow drives it headlessly). So a
   frozen snapshot beat the transcript refetched every few seconds, and the
   RHS looked static while the two were talking. */
const TURNS = n => Array.from({length:n},(_,i)=>({
  text:"[Shadow · mission m-1] say "+i, response:"chat reply "+i }));
const MSGS  = n => { const o=[]; for(let i=0;i<n;i++){
  o.push({role:"user",text:"[Shadow · mission m-1] say "+i});
  o.push({role:"assistant",text:"chat reply "+i}); } return o; };

/* 22. a CLOSED pane's stale snapshot no longer shadows the fresh fetch */
{
  const ctx=fresh();
  ctx.S.openPanes=[];                                  /* no pane open */
  ctx.S.sessions=[{id:"d5740ce7",turns:TURNS(1)}];      /* frozen at 1 turn */
  ctx.S.goalTranscript={ "d5740ce7": MSGS(3) };         /* the poll has 3 */
  const msgs=ctx.goalMessages("d5740ce7");
  assert.strictEqual(msgs.length,6,"the fetched transcript wins: "+msgs.length);
  assert(/say 2/.test(JSON.stringify(msgs)),"including the newest turn");
  ok("a closed pane's snapshot no longer hides live transcript data");
}
/* 23. an OPEN pane still owns its turns (its socket is writing them) */
{
  const ctx=fresh();
  ctx.S.openPanes=["d5740ce7"];
  ctx.S.sessions=[{id:"d5740ce7",turns:TURNS(3)}];
  ctx.S.goalTranscript={ "d5740ce7": MSGS(1) };         /* the file lags */
  assert.strictEqual(ctx.goalMessages("d5740ce7").length,6,
    "the live pane array wins over a lagging file read");
  ok("an open pane still owns its own turns");
}
/* 24. exactly ONE source -- never merged, so nothing is duplicated */
{
  const ctx=fresh();
  ctx.S.openPanes=[];
  ctx.S.sessions=[{id:"d5740ce7",turns:TURNS(2)}];
  ctx.S.goalTranscript={ "d5740ce7": MSGS(2) };
  const msgs=ctx.goalMessages("d5740ce7");
  assert.strictEqual(msgs.length,4,"4, not 8");
  const texts=msgs.map(m=>m.text);
  assert.strictEqual(new Set(texts).size,texts.length,"no duplicate rows");
  ok("one source is chosen, never merged");
}
/* 25. nothing fetched yet still beats an empty screen */
{
  const ctx=fresh();
  ctx.S.openPanes=[]; ctx.S.sessions=[{id:"d5740ce7",turns:TURNS(1)}];
  ctx.S.goalTranscript={};
  assert.strictEqual(ctx.goalMessages("d5740ce7").length,2,
    "a stale snapshot beats 'Reading the chat…'");
  ctx.S.sessions=[];
  assert.strictEqual(ctx.goalMessages("d5740ce7"),undefined,
    "and with nothing at all the reading state is honest");
  ok("the first paint degrades sensibly");
}
/* 26. the session stream refreshes the watched chat */
{
  const ctx=fresh({ responses:{ "/api/sessions/d5740ce7":{messages:MSGS(2)} } });
  ctx.S.screen="goal"; ctx.S.goalSel="g-1"; ctx.S.openPanes=[];
  ctx.S.goalDetail={ "g-1": detail({state:"working"}) };
  assert.strictEqual(ctx.goalWatchedSession(),"d5740ce7");
  assert.strictEqual(ctx.goalTranscriptChanged("d5740ce7"),true,"it fetched");
  assert(ctx.fetches.indexOf("/api/sessions/d5740ce7")>=0,
    "through the EXISTING transcript endpoint");
  ok("a transcript write refreshes the watched chat");
}
/* 27. and only that chat, only that screen */
{
  const ctx=fresh();
  ctx.S.screen="goal"; ctx.S.goalSel="g-1"; ctx.S.openPanes=[];
  ctx.S.goalDetail={ "g-1": detail({state:"working"}) };
  assert.strictEqual(ctx.goalTranscriptChanged("somebody-else"),false,
    "another chat's write is not ours");
  ctx.S.screen="chats";
  assert.strictEqual(ctx.goalTranscriptChanged("d5740ce7"),false,
    "and neither is ours once the workspace is closed");
  assert.strictEqual(ctx.fetches.length,0,"nothing was fetched");
  ok("only the watched chat, only while the workspace is open");
}
/* 28. an open pane is left to 09-tail.js -- one GET per write, not two */
{
  const ctx=fresh();
  ctx.S.screen="goal"; ctx.S.goalSel="g-1";
  ctx.S.goalDetail={ "g-1": detail({state:"working"}) };
  ctx.S.openPanes=["d5740ce7"];
  assert.strictEqual(ctx.goalTranscriptChanged("d5740ce7"),false);
  assert.strictEqual(ctx.fetches.length,0,"the pane path already re-reads it");
  ok("no double fetch when the chat is also an open pane");
}
/* 29. the 1s throttle -- a running turn rewrites the file many times a sec */
{
  const ctx=fresh({ responses:{ "/api/sessions/d5740ce7":{messages:[]} } });
  ctx.S.screen="goal"; ctx.S.goalSel="g-1"; ctx.S.openPanes=[];
  ctx.S.goalDetail={ "g-1": detail({state:"working"}) };
  assert.strictEqual(ctx.goalTranscriptChanged("d5740ce7"),true);
  for (let i=0;i<20;i++) ctx.goalTranscriptChanged("d5740ce7");
  assert.strictEqual(
    ctx.fetches.filter(u=>u==="/api/sessions/d5740ce7").length,1,
    "21 writes, one read");
  ok("the transcript refresh is throttled like the pane path");
}
/* 30. turns accumulate across a run, and Shadow's are labelled as Shadow's */
{
  const ctx=fresh();
  ctx.S.openPanes=[]; ctx.S.sessions=[];
  const d=detail({state:"working"});
  ctx.S.goalTranscript={ "d5740ce7": MSGS(1) };
  let html=ctx.goalTranscriptHtml(ctx.goalMessages("d5740ce7"),d);
  assert.strictEqual((html.match(/gwturn /g)||[]).length,2,"one exchange");
  ctx.S.goalTranscript={ "d5740ce7": MSGS(3) };        /* the run continued */
  html=ctx.goalTranscriptHtml(ctx.goalMessages("d5740ce7"),d);
  assert.strictEqual((html.match(/gwturn /g)||[]).length,6,
    "Shadow -> chat -> Shadow -> chat -> Shadow -> chat");
  assert.strictEqual((html.match(/gwturn-shadow/g)||[]).length,3);
  assert.strictEqual((html.match(/gwturn-chat/g)||[]).length,3);
  assert(!/\[Shadow · mission/.test(html),"the tag is stripped for display");
  ok("multiple Shadow/chat turns accumulate and stay attributed");
}
/* 31. a refresh does not yank a founder who scrolled up */
{
  const ctx=fresh();
  const el={ scrollTop:100, scrollHeight:3000, clientHeight:400,
             dataset:{gwsid:"d5740ce7"}, addEventListener(){}, __gwBound:true };
  ctx.document.querySelector = sel => sel===".gwturns" ? el : null;
  ctx.S.goalUserScrolled={ "d5740ce7": true };
  const before=ctx.goalScrollState();
  assert.strictEqual(before.pinned,false);
  ctx.S.goalTranscript={ "d5740ce7": MSGS(5) };        /* new content lands */
  ctx.goalRestoreScroll(before);
  assert.strictEqual(el.scrollTop,100,"their position is kept");
  ok("a live refresh respects a manually scrolled reader");
}
/* 32. ...and keeps a pinned reader pinned to the newest turn */
{
  const ctx=fresh();
  const el={ scrollTop:2600, scrollHeight:3000, clientHeight:400,
             dataset:{gwsid:"d5740ce7"}, addEventListener(){}, __gwBound:true };
  ctx.document.querySelector = sel => sel===".gwturns" ? el : null;
  ctx.S.goalUserScrolled={};
  const before=ctx.goalScrollState();
  assert.strictEqual(before.pinned,true,"they were at the tail");
  el.scrollHeight=3600;                                 /* a turn arrived */
  ctx.goalRestoreScroll(before);
  assert.strictEqual(el.scrollTop,3600,"and they follow it");
  ok("a pinned reader follows the newest turn");
}
/* 33. no second transcript store, no socket, no backend endpoint added */
{
  const code=src.replace(/\/\*[\s\S]*?\*\//g,"").replace(/^\s*\/\/.*$/gm,"");
  assert(!/new WebSocket|EventSource/.test(code),"no socket here");
  const body=code.slice(code.indexOf("function goalTranscriptChanged"));
  assert(/loadGoalTranscript\(sid\)/.test(body.slice(0,700)),
    "it reuses the existing loader");
  assert(!/fetch\(/.test(body.slice(0,700)),"and adds no endpoint");
  const tail=fs.readFileSync(path.join(__dirname,"static","js","09-tail.js"),"utf8");
  assert(/typeof goalTranscriptChanged === "function"/.test(tail),
    "the stream hook is typeof-guarded");
  assert(/goalTranscriptChanged\(s\.id\)/.test(tail));
  ok("no socket, no second store, no new endpoint");
}
setTimeout(()=>console.log("test_goal_live.js: all green"),60);
