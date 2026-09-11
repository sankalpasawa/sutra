#!/usr/bin/env node
/* test_shadow_briefing.js -- V5 slice 11: Shadow Home V2, "The Briefing".
   One vertical spine; every band from the existing goal list. Each goal
   appears in EXACTLY one band; empty bands render nothing.
   Run: node test_shadow_briefing.js */
"use strict";
const fs=require("fs"), path=require("path"), vm=require("vm"), assert=require("assert");
const css=fs.readFileSync(path.join(__dirname,"static","panel.css"),"utf8");
const L=f=>fs.readFileSync(path.join(__dirname,"static","js",f),"utf8");
const overlay=L("15-shadow-overlay.js"), home=L("16-shadow-home.js"), gw=L("18-goal-workspace.js");

function fresh(){
  const posts=[],fetches=[],nudges=[];
  const ctx={ console,Date,setTimeout:f=>({f}),requestAnimationFrame(f){(ctx.rafs=ctx.rafs||[]).push(f);},
    esc:x=>String(x==null?"":x).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"),
    SCREENS:{},TITLES:{},S:{ui:{dest:"focus"}},DESTS:["now","focus","chats"],
    scheduleRender(){},render(){},renderShadowCard(){},
    openScreen(id){ctx.opened=id;ctx.S.screen=id;},goDest(d){ctx.dest=d;},
    showNudge(t){nudges.push(t);},submitTurn(){},
    fetch(u){fetches.push(u);return Promise.resolve({ok:false,status:404,json:()=>Promise.resolve({})});},
    document:{addEventListener(t,f){(ctx.handlers[t]=ctx.handlers[t]||[]).push(f);},
      createElement(){return{setAttribute(){},remove(){},dataset:{},classList:{add(){}}};},
      body:{appendChild(){},classList:{add(){}}},querySelector(){return null;}},
    handlers:{},posts,fetches,nudges };
  ctx.window=ctx; ctx.globalThis=ctx; ctx.__SHADOW_NO_AUTOBOOT=true;
  vm.createContext(ctx); vm.runInContext(overlay,ctx); vm.runInContext(home,ctx);
  ctx.shadowPost=(u,b)=>{posts.push({url:u,body:b});
    return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve({})});};
  vm.runInContext(gw,ctx);
  ctx.S.shadowHomeDark=false; ctx.S.shadowThreads={global:[]}; ctx.S.shadowChat="global";
  ctx.S.goals=[]; ctx.S.shadowWatching=[]; ctx.S.shadowMemory=[];
  return ctx;
}
const G=(o)=>Object.assign({ id:"g-w", outcome:"Configure referral workflow",
  state:"working", target_session:"01a081", checks_met:2, checks_total:3,
  checks_label:"2 of 3 checks", turn_label:"turn 11/20", turns_used:11, max_turns:20,
  block_reason:null, attempt:1, unmet:["EHR configuration"] }, o);
const WORKING=G({});
const VERIFYING=G({id:"g-v",outcome:"Prepare insurance intake",state:"verifying",
  checks_label:"3 of 4 checks",turn_label:"turn 7/15",unmet:["founder signs off"]});
const BLOCKED=G({id:"g-b",outcome:"Referral workflow",state:"blocked",attempt:2,
  block_reason:"budget_exhausted",checks_label:"2 of 3 checks",turn_label:"turn 20/20",
  unmet:["final submission verified"]});
const DONE=G({id:"g-d",outcome:"Deployment preparation",state:"done",
  checks_label:"3 of 3 checks",unmet:[]});
const STOPPED=G({id:"g-s",outcome:"Insurance configuration",state:"stopped",unmet:["x"]});
const DRAFT=G({id:"g-q",outcome:"EHR integration",state:"draft",turns_used:0,
  checks_label:"0 of 2 checks",turn_label:null,unmet:["schema mapped"]});
let n=0; const ok=m=>console.log("ok "+(++n)+" "+m);
const H=ctx=>ctx.shadowHomeHtml();
const click=(ctx,ds)=>ctx.handlers.click.forEach(f=>f({target:{dataset:ds,
  closest:sel=>sel==="[data-goalopen]"&&ds.goalopen?{dataset:ds}:null}}));

/* 1. CALM */
{
  const ctx=fresh();
  const h=H(ctx);
  assert(/Nothing needs you right now\./.test(h),"the calm greeting");
  assert(!/Everything is handled/.test(h),
    "and it never claims Shadow FINISHED everything it oversees");
  /* `shbrief` keeps every shipped rule and every assertion that names it;
     `shbrief2` is the hook the visual pass hangs its own rules off. */
  assert(/class="shbrief shbrief2 shcalm"/.test(h),
    "the calm spine is composed, not top-loaded");
  assert(!/shdeck/.test(h),"no work section at all with nothing delegated");
  assert(!/shasg/.test(h),"and not one assignment card");
  assert(!/shchattabs/.test(h),"no session tabs");
  assert(/Tell Shadow what outcome you want/.test(h),"delegation composer");
  /* APPROVED DESIGN: the composer is the centrepiece in EVERY state, so
     there is no longer a hero/quiet split -- the stage is always the stage. */
  assert(/shstage/.test(h),"the composer stage leads the page");
  assert(/What should I take on\?/.test(h),"with its ask");
  /* still compact in what it SAYS -- the growth is inline svg for the four
     nav icons and the target/send affordances, not content. Counted by
     stripping svg markup, which is what the original figure was about. */
  const words=h.replace(/<svg[\s\S]*?<\/svg>/g,"");
  assert(words.length<2600,"the calm page is compact ("+words.length+" chars)");
  assert(!/8B4A6B/.test(h),"no attention styling when calm");
  ok("calm state: one sentence and a hero composer");
}
/* 2. state-derived greeting */
{
  const ctx=fresh();
  const g=()=>ctx.shadowGreeting();
  assert.strictEqual(g(),"Nothing needs you right now.");
  ctx.S.goals=[BLOCKED];
  assert.strictEqual(g(),"One goal needs you.");
  ctx.S.goals=[BLOCKED,WORKING,VERIFYING];
  assert.strictEqual(g(),"One goal needs you. Two goals are running.");
  ctx.S.goals=[BLOCKED,{...BLOCKED,id:"b2"},{...BLOCKED,id:"b3"},WORKING];
  assert.strictEqual(g(),"Three goals need you. One goal is running.");
  /* the remainder clause appears ONLY when there is a remainder, and it
     claims nothing about completion either */
  ctx.S.goals=[BLOCKED,DONE,DRAFT];
  assert.strictEqual(g(),"One goal needs you. Nothing else needs you.");
  ctx.S.goals=[DONE,STOPPED];
  assert.strictEqual(g(),"Nothing needs you right now.","nothing live = calm");
  assert(!/morning|afternoon|evening|Good /i.test(H(ctx)),"never a clock greeting");
  ok("greeting is derived from goal state only");
}
/* 3/4. NEEDS YOU appears only when blocked; never empty */
{
  const ctx=fresh(); ctx.S.goals=[WORKING,DONE];
  assert(!/shstatus-blocked/.test(H(ctx)),"absent with nothing blocked");
  ctx.S.goals=[BLOCKED,WORKING];
  const h=H(ctx);
  assert(/shstatus-blocked/.test(h),"present when blocked");
  assert(/Referral workflow/.test(h),"the outcome");
  assert(/the turn budget ran out/.test(h),"human blocker");
  /* the meta row is separate spans now (the design separates them with
     space, not a middot) -- both facts are still stated */
  assert(/2 of 3 checks/.test(h) && /attempt 2/.test(h),
    "progress and attempt");
  /* assert the CARDS, not the count legend -- "Needs you" also appears
     there, earlier in the document, which is not what this is about */
  assert(h.indexOf("Referral workflow")<h.indexOf("Configure referral"),
    "and a blocked assignment leads the Active group");
  ok("Needs You renders only when something is blocked");
}
/* 5/6. WORKING includes working AND verifying, excludes the rest */
{
  const ctx=fresh(); ctx.S.goals=[WORKING,VERIFYING,BLOCKED,DONE,STOPPED,DRAFT];
  const h=H(ctx);
  /* Active holds blocked + working + verifying; the terminal states sit in
     their own groups below. Same states, same data -- grouped, not filtered. */
  const band=h.slice(h.indexOf(">Active<"),h.indexOf("Recently completed"));
  assert(/Configure referral workflow/.test(band),"working goal");
  /* APPROVED DESIGN: the state is a pill, the turn sits beside it and the
     checks are the meta row -- the same three facts, no longer one joined
     string. Priority is outcome, then state, then supporting metadata. */
  assert(/shstatus-working/.test(band) && /2 of 3 checks/.test(band)
    && /turn 11\/20/.test(band), "its state, checks and turn");
  assert(/Prepare insurance intake/.test(band),"verifying goal");
  assert(/shstatus-verifying/.test(band) && /3 of 4 checks/.test(band)
    && /turn 7\/15/.test(band), "its state, checks and turn");
  /* Active is what Shadow is CARRYING: blocked belongs here too -- it is
     live work waiting on the founder, not finished work. The terminal and
     idle states have their own groups below. */
  assert(/Referral workflow</.test(band),"blocked is live work, so it IS here");
  assert(!/Deployment preparation/.test(band),"done is NOT here");
  assert(!/Insurance configuration/.test(band),"stopped is NOT here");
  assert(!/EHR integration/.test(band),"draft is NOT here");
  ok("Active holds blocked + working + verifying only");
}
/* 7/8/9. GOALS holds the remainder, exactly once, with readable states */
{
  const ctx=fresh(); ctx.S.goals=[WORKING,VERIFYING,BLOCKED,DONE,STOPPED,DRAFT];
  const h=H(ctx);
  const band=h.slice(h.indexOf("Recently completed"));
  assert(/Deployment preparation/.test(band)&&/Verified/.test(band),
    "done listed under Recently completed");
  const idle=h.slice(h.indexOf(">Not running<"));
  assert(/EHR integration/.test(idle)&&/Draft/.test(idle),"draft listed");
  assert(/Insurance configuration/.test(idle)&&/Stopped/.test(idle),
    "stopped listed");
  assert(!/Configure referral workflow/.test(band),"working not duplicated");
  assert(!/Prepare insurance intake/.test(band),"verifying not duplicated");
  assert(!/the turn budget ran out/.test(band),"blocked not duplicated");
  /* each goal exactly once across the whole page */
  for(const [id,name] of [["g-w","Configure referral workflow"],
      ["g-v","Prepare insurance intake"],["g-b","Referral workflow<"],
      ["g-d","Deployment preparation"],["g-s","Insurance configuration"],
      ["g-q","EHR integration"]]){
    const c=(h.match(new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g,"\\$&"),"g"))||[]).length;
    assert.strictEqual(c,1,name+" appears exactly once (saw "+c+")");
  }
  ok("Goals holds the remainder; every goal appears exactly once");
}
/* 10. clicks open the existing workspace */
{
  const ctx=fresh(); ctx.S.goals=[BLOCKED,WORKING,DONE];
  const h=H(ctx);
  assert(/data-goalopen="g-b"/.test(h)&&/data-goalopen="g-w"/.test(h)
    &&/data-goalopen="g-d"/.test(h),"every band row is clickable");
  click(ctx,{goalopen:"g-w"});
  assert.strictEqual(ctx.S.goalSel,"g-w"); assert.strictEqual(ctx.opened,"goal");
  ok("goal clicks open the existing workspace");
}
/* 11/12. WATCHING is a compact count; hundreds are never rendered on Home */
{
  const ctx=fresh(); ctx.S.goals=[WORKING];
  ctx.S.shadowWatching=Array.from({length:470},(_,i)=>"s-"+i);
  const h=H(ctx);
  assert(/Watching · 470/.test(h),"the count");
  assert(!/data-shwatch=/.test(h),"not one session row on Home");
  assert(!/Stop watching/.test(h),"nor its controls");
  /* VISUAL PASS: the nav rail now sits between the composer and the work
     deck (identity -> handover -> where else to look -> workload), so the
     foot precedes the bands. What made Watching "secondary" was never its
     position -- it is that 470 sessions are a COUNT here and never rows,
     which the two assertions above pin directly. */
  assert(h.indexOf("Watching · 470")<h.indexOf("Shadow\u2019s Work"),
    "nav sits above the work deck");
  assert(h.indexOf("shcompose")<h.indexOf("Watching · 470"),
    "and the composer leads the page");
  click(ctx,{shwatching:"1"});
  assert.strictEqual(ctx.opened,"shadowwatching","it opens its own surface");
  assert(typeof ctx.SCREENS.shadowwatching==="function","which is registered");
  ctx.S.shadowWatching=["s-1"];
  const screen=ctx.SCREENS.shadowwatching();
  assert(/data-shwatch=/.test(screen),"reusing the EXISTING plane");
  assert(/Stop watching/.test(screen),"with its existing controls");
  ok("Watching is a compact count that opens the existing surface");
}
/* 13. MEMORY is compact and reveals the existing surface */
{
  const ctx=fresh(); ctx.S.goals=[WORKING];
  ctx.S.shadowMemory=[{id:"i-1",text:"outcome first",precedence:"d_ledger",confirmed:true}];
  const h=H(ctx);
  assert(/Memory · 1/.test(h),"the count");
  assert(!/outcome first/.test(h),"collapsed by default");
  click(ctx,{shmemopen:"1"});
  const open=H(ctx);
  assert(/outcome first/.test(open)&&/shmemory/.test(open),
    "opens the EXISTING memory list");
  ok("Memory is a compact disclosure");
}
/* 14/15. session tabs gone; conversations + settings still reachable */
{
  const ctx=fresh(); ctx.S.goals=[WORKING];
  const h=H(ctx);
  assert(!/shchattabs/.test(h),"no tab strip");
  assert(!/shchattab\b/.test(h.replace(/shchattabs/g,"")),"no tab pills");
  assert(/data-shchats/.test(h),"Conversations is in the foot");
  assert(/data-shscreen="shadowsettings"/.test(h),"Settings stays reachable");
  click(ctx,{shchats:"1"});
  assert.strictEqual(ctx.dest,"chats","using the EXISTING chats destination");
  ok("session tabs removed; conversations and settings reachable");
}
/* 16/17/18. composer: delegation copy, slice 8 compatible, hero when calm */
{
  const ctx=fresh();
  assert(/Tell Shadow what outcome you want/.test(H(ctx)),"delegation copy");
  assert(/shstage/.test(H(ctx)),"the stage is present when calm");
  ctx.S.goals=[WORKING];
  const busy=H(ctx);
  assert(/shstage/.test(busy),"and present when there is active work too");
  assert(/data-shhomecompose/.test(busy),"but still there");
  /* slice 8: the proposal still renders, and the scope still rides the turn */
  ctx.S.shadowChat="01a081";
  assert(/data-shscope="01a081"/.test(H(ctx)),"the composer carries its scope");
  ctx.S.shadowThreads={"01a081":[{who:"shadow",goalProposal:{ts:1,outcome:"o",
    done_when:[{tier:"contains_artifact",check:"c"}],target_session:"01a081"}}]};
  const withProp=H(ctx);
  assert(/Set a goal for this chat\?/.test(withProp),"slice 8 card intact");
  assert(/data-gwpropcreate/.test(withProp),"with its Create action");
  ok("composer: delegation copy, hero when calm, slice 8 intact");
}
/* 19. the activity line is never fabricated */
{
  const ctx=fresh();
  assert.strictEqual(ctx.shadowActivityLine(G({unmet:["X"]})),"Waiting on: X");
  assert.strictEqual(ctx.shadowActivityLine(G({state:"verifying",unmet:["Y"]})),
    "Waiting on your sign-off: Y");
  assert.strictEqual(ctx.shadowActivityLine(G({unmet:[],turns_used:0})),"Started");
  assert.strictEqual(ctx.shadowActivityLine(G({unmet:[],turns_used:5})),"",
    "nothing honest to say -> no line");
  assert.strictEqual(ctx.shadowActivityLine(null),"");
  ctx.S.goals=[G({unmet:[],turns_used:5})];
  const h=H(ctx);
  assert(!/shasgsub/.test(h),"and the element is omitted entirely");
  assert(!/working hard|making progress|thinking/i.test(h),"no narration");
  ok("activity is derived or absent, never generated");
}
/* 20. Needs You uses the existing actions */
{
  const ctx=fresh(); ctx.S.goals=[BLOCKED];
  const h=H(ctx);
  assert(/data-goalact="resume"/.test(h)&&/data-goalact="extend"/.test(h)
    &&/data-goalact="stop"/.test(h),"the existing three");
  assert(/Answer &amp; resume/.test(h)&&/Extend budget/.test(h)&&/Stop/.test(h));
  assert.strictEqual(ctx.goalActions("blocked",BLOCKED).map(a=>a.act).join(","),
    "resume,extend,stop","from the existing action table");
  ok("Needs You reuses the existing goal actions");
}
/* 21/22. no new alert system, no percentage */
{
  const ctx=fresh();
  for(const set of [[],[WORKING],[BLOCKED],[WORKING,VERIFYING,BLOCKED,DONE,STOPPED,DRAFT]]){
    ctx.S.goals=set; const h=H(ctx);
    assert(!/%/.test(h),"no percentage with "+set.length+" goals");
    assert(!/badge|alert-|notification/i.test(h),"no new alert framework");
  }
  const block=css.slice(css.indexOf("slice 11")).replace(/\/\*[\s\S]*?\*\//g,"");
  assert(!/animation|@keyframes/i.test(block),"no pulse");
  assert(!/#e5484d/.test(block),"no red");
  assert(/#8B4A6B/.test(block)&&/#B8945F/.test(block),"v10 colours reused");
  const stray=block.replace(/#B8945F|#2D5A3E|#8B4A6B|#4A6B8B|#8B6B4A/g,"");
  assert(!/#[0-9a-fA-F]{6}/.test(stray),"nothing outside the v10 set");
  ok("no new alert system and no percentage progress");
}
/* 23. layout: one centred spine, narrow-safe, no 30/70 on Home */
{
  assert(/\.shbrief\{[^}]*max-width:620px/.test(css),"a readable spine width");
  assert(/\.shbrief\{[^}]*margin:0 auto/.test(css),"centred");
  assert(/@media \(max-width:760px\)\{\s*\.shbrief\{ max-width:100%/.test(css),
    "and full width when narrow");
  assert(!/\.shbrief[^{]*\{[^}]*flex-direction:row/.test(css),
    "the spine is never a row");
  ok("single centred spine, narrow-safe");
}
/* 24/25. the Goal workspace and the rest of Shadow are intact */
{
  const ctx=fresh();
  ctx.S.goalSel="g-b";
  ctx.S.goalDetail={"g-b":Object.assign({},BLOCKED,{checks:[],unmet:[],attempts:[],
    learned:[],founder_guidance:[],blockers:[],history:[]})};
  ctx.S.goalTranscript={"01a081":[{role:"assistant",text:"still failing"}]};
  const wsHtml=ctx.goalWorkspaceHtml();
  assert(/gwcols/.test(wsHtml),"the workspace keeps its 30/70 shell");
  assert.strictEqual((wsHtml.match(/gwturns/g)||[]).length,1,"one transcript");
  ctx.S.goals=[BLOCKED,WORKING];
  const h=H(ctx);
  assert.strictEqual((h.match(/gwturns/g)||[]).length,0,"Home renders no transcript");
  assert(!/gwcols/.test(h),"and no second workspace");
  assert(typeof ctx.SCREENS.shadow==="function","the shadow screen still exists");
  assert(typeof ctx.SCREENS.shadowsettings==="function","and settings");
  assert(typeof ctx.shadowPlaneHtml==="function","the plane is untouched");
  assert(typeof ctx.shadowMemoryHtml==="function","and the memory renderer");
  ok("Goal workspace and existing Shadow surfaces intact");
}
/* 26. many goals stay compact and link out */
{
  const ctx=fresh();
  ctx.S.goals=Array.from({length:20},(_,i)=>G({id:"g"+i,state:"done",
    outcome:"Outcome "+i}));
  const h=H(ctx);
  const rows=(h.match(/shasg shasg-/g)||[]).length;
  assert(rows<=8,"the Home scan stays compact ("+rows+" rows)");
  assert(/more — open all goals/.test(h),"and links to the existing list");
  click(ctx,{shgoals:"1"});
  assert.strictEqual(ctx.opened,"goals","which is the existing goals screen");
  ok("many goals stay compact and link out");
}
/* 27. escaping */
{
  const ctx=fresh();
  ctx.S.goals=[G({outcome:'<img src=x onerror=alert(1)>'})];
  const h=H(ctx);
  assert(!/<img/.test(h)&&/&lt;img/.test(h),"escaped");
  ok("output is escaped");
}
/* ---- polish pass: the composer's chat picker ---------------------------- */
/* The picker used to be built from the watching store, so it offered raw ids
   the app does not list as chats. It is a menu now, not an inventory. */
const SESS=(id,title,ms)=>({id,title,updated_ms:ms,created_ms:ms});
function picker(ctx){
  ctx.S.shadowScopeOpen=true;
  const h=H(ctx);
  const m=h.match(/<div class="shscopelist">([\s\S]*?)<\/div>/);
  return m?m[1]:"";
}
/* 28. fixture / dead / unlistable ids are never offered */
{
  const ctx=fresh();
  ctx.S.sessions=[SESS("01a081","Referral workflow build",300),
                  SESS("77bb22","Insurance intake",200)];
  /* exactly what the founder saw: the watch store holds ids with no chat */
  ctx.S.shadowWatching=["ds-own","dead-0","01a081","77bb22","fake-99999"];
  const list=picker(ctx);
  assert(/Referral workflow build/.test(list),"a real chat is offered");
  assert(/Insurance intake/.test(list),"and so is the other one");
  assert(!/session ds-own/.test(list),"the fixture id is not offered");
  assert(!/session dead-0/.test(list),"nor the dead one");
  assert(!/fake-99999/.test(list),"nor the harness id");
  assert(!/session /.test(list),
    "nothing in the menu is an unnamed raw id at all");
  ok("the picker offers only chats the app itself lists");
}
/* 29. legitimate conversations are preserved, newest first */
{
  const ctx=fresh();
  ctx.S.sessions=[SESS("a1","Oldest chat",100),SESS("b2","Newest chat",900),
                  SESS("c3","Middle chat",500)];
  const list=picker(ctx);
  for (const t of ["Oldest chat","Newest chat","Middle chat"])
    assert(list.indexOf(t)>=0,t+" is preserved");
  assert(list.indexOf("Newest chat")<list.indexOf("Middle chat")
      && list.indexOf("Middle chat")<list.indexOf("Oldest chat"),
    "ordered by the app's own recency");
  assert(/no chat — just talk/.test(list),'"no chat" is kept');
  ok("real conversations are preserved and ordered by recency");
}
/* 30. the chats Shadow is engaged in lead, and the store is never touched */
{
  const ctx=fresh();
  ctx.S.sessions=[SESS("a1","Old chat",100),SESS("b2","Newest chat",900),
                  SESS("c3","Driven chat",200)];
  ctx.S.shadowMissions=[{id:"m1",state:"running",target_session:"c3"}];
  const before=ctx.S.shadowWatching.slice();
  const list=picker(ctx);
  assert(list.indexOf("Driven chat")<list.indexOf("Newest chat"),
    "a live mission's chat leads even though it is not the newest");
  assert.deepStrictEqual(ctx.S.shadowWatching,before,
    "the watching store is untouched -- this is a UI filter, not a delete");
  assert.strictEqual(ctx.posts.length,0,"and nothing was written");
  ok("engaged chats lead; no store is modified");
}
/* 31. picking still sets the scope Slice 8 binds a goal to */
{
  const ctx=fresh();
  ctx.S.sessions=[SESS("01a081","Referral workflow build",300)];
  ctx.S.shadowScopeOpen=true;
  click(ctx,{shchat:"01a081"});
  assert.strictEqual(ctx.S.shadowChat,"01a081","the scope is set");
  assert.strictEqual(ctx.S.shadowScopeOpen,false,"and the picker closes");
  const h=H(ctx);
  assert(/data-shscope="01a081"/.test(h),"the composer carries it");
  assert(/Referral workflow build/.test(h),"and the chip shows its name");
  ok("picking a chat still scopes the composer (slice 8 intact)");
}
/* 32. the Watching plane is an inventory and still names ids honestly */
{
  const ctx=fresh();
  ctx.S.sessions=[]; ctx.S.shadowWatching=["ds-own"];
  const plane=ctx.shadowPlaneHtml(ctx.S.shadowWatching,[],"watching");
  assert(/session ds-own/.test(plane),
    "Watching still shows what it is really watching -- unchanged");
  ok("the Watching inventory is unchanged by the picker fix");
}
/* 33. calm composition is CSS, not content */
{
  const ctx=fresh();
  const h=H(ctx);
  assert(!/shdeck/.test(h),"no work section was added to fill the space");
  assert(!/[0-9]+%/.test(h),"and still no percentage anywhere");
  const sec=css.slice(css.indexOf("slice 11"),
                      css.indexOf("the Watching screen reuses"));
  const rule=sec.slice(sec.indexOf(".shbrief.shcalm"));
  assert(/justify-content:center/.test(rule.slice(0,200)),
    "the calm spine centres what it holds");
  assert(/min-height:100%/.test(rule.slice(0,200)),
    "filling the pane it is given, so the centring is against real space");
  assert(!/\.shbrief\{[^}]*justify-content/.test(sec),
    "and a busy briefing is untouched");
  ok("calm reads as composed without inventing content");
}
setTimeout(()=>console.log("test_shadow_briefing.js: all green"),40);
