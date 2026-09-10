/* Dumps the current week straight out of the app's own engine.
   Previews render from this; no figure is ever typed by hand. */
import {readFileSync} from 'fs';
const html = readFileSync('index.html','utf8');
const blocks = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
const seed  = blocks.find(b=>b.includes('const SEED='));
const core  = blocks.filter(b=>b.includes('function computeWeek')||b.includes('function simulate'));
const UI_STUB = 'var UI={strategy:"custom",extra:null};';
// localStorage does not exist here; the engine only needs S in memory
globalThis.localStorage = {getItem:()=>null,setItem(){},removeItem(){}};
globalThis.document = {addEventListener(){},querySelector:()=>null,documentElement:{style:{}}};
globalThis.window = {addEventListener(){}};
const src = seed.replace('boot();','') + '\n'
  + core.join('\n').replace(/"use strict";/g,'')
  + `\nreturn {SEED, migrate, computeWeek, weekLabel, weekLong, KIND_DEBT, n0,
      debtSnapshot, simulate, stepFireWeek, weeksToMonths, monthsLabel, longDate,
      dateAfterWeeks, addWeeks, shortMY, r2, weekKeys, thisWeek, md, liveAccounts,
      get S(){return S}, set S(v){S=v}};`;
const app = new Function(src)();
const {SEED, migrate, computeWeek, weekLabel, weekLong, KIND_DEBT, n0,
       debtSnapshot, simulate, stepFireWeek, weeksToMonths, monthsLabel, longDate,
       dateAfterWeeks, addWeeks, shortMY, r2:R2, weekKeys, thisWeek, md,
       liveAccounts} = app;
app.S = JSON.parse(JSON.stringify(SEED)); migrate();
const S = app.S;

const k = '2026-09-04';
const C = computeWeek(k), T = C.totals;
const r2 = n => Math.round(n*100)/100;
const rows = C.rows.filter(r=>!r.isRollup && r.a.kind!=='income');

const GROUPS_ = [['checking','Checking'],['buckets','Buckets & sinking funds'],
                 ['savings','Savings'],['loans','Loans'],['cards','Credit cards']];
const grid=[]; const seen=new Set();
for (const [gid,label] of GROUPS_){
  const rs = C.rows.filter(r=>(r.a.group||'buckets')===gid);
  if(!rs.length) continue;
  grid.push({sect:label});
  const emit=(r,child)=>{ if(seen.has(r.a.id))return; seen.add(r.a.id);
    grid.push({name:r.a.name, child:!!child, rollup:!!r.isRollup, income:r.a.kind==='income',
      debt:KIND_DEBT(r.a.kind), limit:n0(r.a.limit), apr:n0(r.a.apr),
      balance:r.balance, usage:r.usage ?? null, minAmt:r.minAmt,
      close:r.close||'', due:r.due||'', min:r.min, attack:r.attack, other:r.other,
      total:r.total, interest:r.weekInterest, after:r.after,
      usageAfter:r.usageAfter ?? null, availAfter:r.availAfter ?? null, sixMo:r.sixMo ?? null}); };
  for(const r of rs){ emit(r); if(r.a.rollup) for(const cid of r.a.rollup){const c=C.byId[cid]; if(c) emit(c,1);} }
}
const cards = C.rows.filter(r=>r.a.kind==='card');
const sum = f => r2(cards.reduce((s,r)=>s+n0(r[f]),0));

/* Stamp what this was generated from. index.html is gitignored, so a commit hash
   alone would miss uncommitted engine edits — which is the usual state while a
   restyle is in flight. The content hash is the real guard; HEAD is recorded so a
   stale preview can be traced to a commit. */
import {createHash} from 'crypto';
import {execSync} from 'child_process';
let head='unknown';
try{ head=execSync('git rev-parse HEAD',{encoding:'utf8'}).trim(); }catch{}

/* ── Attack + Payoff, from the same engine ───────────────────────── */
const debts = debtSnapshot(k);
const floor = R2(debts.reduce((s,d)=>s+d.weeklyMin,0));
const budget = Math.max(T.debtPaid, floor);
const steps = S.plan.steps;
const rankIx = Object.fromEntries((S.plan.order||[]).map((id,i)=>[id,i]));
const sims = Object.fromEntries(['avalanche','snowball','custom','current'].map(st =>
  [st, simulate(debts, {strategy:st, budget, fromWeek:k, steps})]));
const flat = simulate(debts, {strategy:'custom', budget, fromWeek:k, steps:[]});
const plus50 = simulate(debts, {strategy:'custom', budget:budget+50, fromWeek:k, steps});

const slim = d => ({id:d.id, name:d.name, kind:d.kind, balance:d.balance, limit:d.limit,
  apr:d.nominalApr, weekInterest:d.weekInterest, weeklyMin:d.weeklyMin,
  grace:d.grace, graceDue:d.graceDue||'', current:d.current});
const simOut = s => ({weeks:s.weeks===Infinity?null:s.weeks, months:s.weeks===Infinity?null:R2(weeksToMonths(s.weeks)),
  monthsLabel:monthsLabel(weeksToMonths(s.weeks)), totalInterest:s.totalInterest,
  debtFree:s.debtFreeDate?longDate(s.debtFreeDate):null, endBudget:s.endBudget,
  fired:s.fired.map(f=>({id:f.id,label:f.label,weekly:f.weekly,week:f.week,
    lands:longDate(addWeeks(k,f.week))})),
  debts:s.debts.map(d=>({name:d.name, paidOff:d.paidOff,
    clears:d.paidOff==null?null:longDate(addWeeks(k,d.paidOff)), interest:R2(d.interest)}))});

function attackData(){
  const grace = debts.filter(d=>d.grace), live = debts.filter(d=>!d.grace);
  const order = st => [...live].sort((a,b)=>
    st==='snowball' ? a.balance-b.balance
    : st==='custom' ? ((rankIx[a.id]??999)-(rankIx[b.id]??999))
    : (b.apr-a.apr || b.balance-a.balance));
  return {budget, attackOnTable:T.attack,
    weeklyBleed:R2(live.reduce((s,d)=>s+d.weekInterest,0)),
    monthlyBleed:R2(live.reduce((s,d)=>s+d.weekInterest,0)*52/12),
    ranked:Object.fromEntries(['avalanche','snowball','custom'].map(st=>[st, order(st).map(slim)])),
    grace:grace.map(slim),
    attackedThisWeek:C.rows.filter(r=>KIND_DEBT(r.a.kind)&&r.attack>0).map(r=>r.a.name),
    sims:Object.fromEntries(Object.entries(sims).map(([st,s])=>[st, simOut(s)]))};
}
function payoffData(){
  const sim = sims.custom;
  const every = Math.max(1, Math.ceil(sim.series.length/90));
  return {budget, floor, debtBalance:T.debtBalance, accounts:debts.length,
    sim:simOut(sim), flat:simOut(flat), plus50:simOut(plus50),
    compare:Object.fromEntries(['avalanche','snowball','custom'].map(st=>[st, simOut(sims[st])])),
    steps:steps.map(st=>({id:st.id, label:st.label, note:st.note||'', weekly:st.weekly,
      trigger:st.trigger.type, fireWeek:stepFireWeek(st,k),
      fired:!!sim.fired.find(f=>f.id===st.id),
      lands:(sim.fired.find(f=>f.id===st.id)||{}).week!=null
        ? longDate(addWeeks(k,sim.fired.find(f=>f.id===st.id).week)) : null})),
    series:sim.series.filter((_,i)=>i%every===0||i===sim.series.length-1)
      .map(p=>({w:p.w, total:p.total, x:shortMY(addWeeks(k,p.w)),
                t:longDate(addWeeks(k,p.w)), months:monthsLabel(weeksToMonths(p.w))}))};
}

function historyData(){
  const ks=weekKeys();
  const per=ks.map(w=>{const c=computeWeek(w),t=c.totals;
    return {k:w, x:md(w), t:weekLong(w), planned:w>thisWeek(),
      debt:t.debtBalance, cards:t.cardBalance, util:t.usage,
      paid:t.debtPaid, attack:t.attack, income:t.income,
      allocated:t.allocated, unallocated:t.unallocated};});
  const cards=liveAccounts().filter(a=>a.kind==='card');
  const spark=cards.map(a=>{
    const pts=ks.map(w=>{const c=computeWeek(w); return R2(n0((c.byId[a.id]||{}).balance));});
    const now=pts[pts.length-1], then=pts[0];
    return {name:a.name, pts, now, delta:R2(now-then), limit:n0(a.limit),
      used:a.limit?R2(now/a.limit):null};});
  const drift=R2(ks.reduce((s,w)=>{const c=computeWeek(w);
    return s+c.rows.reduce((t,r)=>t+(r.drift&&r.drift>0?r.drift:0),0);},0));
  const first=per[0], last=per[per.length-1];
  return {weeks:per, spark, drift,
    span:{from:weekLabel(ks[0]), to:weekLabel(ks[ks.length-1]), n:ks.length},
    totals:{paidAll:R2(per.reduce((s,p)=>s+p.paid,0)),
            attackAll:R2(per.reduce((s,p)=>s+p.attack,0))},
    change:{debt:R2(last.debt-first.debt), from:first.debt, to:last.debt}};
}
function planData(){
  const P=S.plan, today=k;
  const byId=Object.fromEntries(debts.map(d=>[d.id,d]));
  const cal=[...P.calendar].sort((a,b)=>a.d.localeCompare(b.d));
  const acct=id=>S.accounts.find(a=>a.id===id);
  return {source:P.source||'',
    order:(P.order||[]).filter(id=>acct(id)).map(id=>{
      const a=acct(id), d=byId[id];
      return {id, name:a.name, clear:!d,
        balance:d?d.balance:0, apr:d?d.nominalApr:n0(a.apr),
        weekInterest:d?d.weekInterest:0, kind:a.kind, limit:d?d.limit:n0(a.limit)};
    }),
    missing:debts.filter(d=>!(P.order||[]).includes(d.id)&&!d.grace).map(d=>({id:d.id,name:d.name})),
    open:P.open.map(o=>({t:o.t, n:o.n||'', done:!!o.done})),
    calendar:cal.map(c=>({d:c.d, t:c.t, n:c.n||'', done:!!c.done,
      overdue:!c.done&&c.d<today, soon:!c.done&&c.d>=today&&c.d<addWeeks(today,4)})),
    ref:P.ref&&P.ref.show?{asOf:P.ref.asOf, rows:Object.entries(P.ref.rows).map(([id,v])=>{
      const a=acct(id), r=C.byId[id];
      return a&&r?{name:a.name, sheet:r.balance, handoff:v, delta:R2(v-r.balance)}:null;
    }).filter(Boolean)}:null,
    minsToVerify:(P.minsToVerify||[]).map(m=>({name:(acct(m.acct)||{}).name||m.acct,
      est:m.est, when:m.when, n:m.n}))};
}
function accountsData(){
  const GK={income:'checking',cash:'buckets',savings:'savings',loan:'loans',card:'cards'};
  const GL=[['checking','Checking'],['buckets','Buckets & sinking funds'],
            ['savings','Savings'],['loans','Loans'],['cards','Credit cards']];
  return {groups:GL.map(([gid,label])=>({label,
    rows:S.accounts.filter(a=>!a.archived&&(a.group||GK[a.kind])===gid)
      .sort((x,y)=>x.order-y.order)
      .map(a=>({id:a.id, name:a.name, kind:a.kind, limit:n0(a.limit),
        apr:n0(a.apr), minAmt:n0(a.minAmt), weeklyOutflow:n0(a.weeklyOutflow),
        grace:!!a.grace, target:a.target?a.target.amount:null}))})).filter(g=>g.rows.length),
    archived:S.accounts.filter(a=>a.archived).map(a=>({name:a.name, kind:a.kind}))};
}

console.log(JSON.stringify({
  _meta:{generatedAt:new Date().toISOString(),
    appHash:createHash('sha256').update(html).digest('hex').slice(0,16), gitHead:head},
  week:k, label:weekLabel(k), dateline:weekLong(k),
  income:T.income, allocated:T.allocated, unallocated:T.unallocated,
  alloc:{Attack:T.attack, 'Other debt':T.otherDebt, Minimums:T.minPaid, 'Buckets & savings':T.savingsIn},
  strip:{debtBalance:T.debtBalance, cardBalance:T.cardBalance,
    loanBalance:r2(T.debtBalance-T.cardBalance), usage:T.usage, usageAfter:T.usageAfter,
    availAfter:T.availAfter, weekInterest:T.weekInterest, monthlyInterest:r2(T.weekInterest*52/12)},
  checks:C.checks,
  funds:C.rows.filter(r=>r.a.target&&!r.isRollup).map(r=>({name:r.a.name, after:r.after,
    target:r.a.target.amount, pct:r2(r.targetPct*100), short:r.targetShort,
    by:r.a.target.by||'', frees:r.a.target.frees??null, done:r.targetDone,
    weeks:r.targetWeeks===Infinity?null:r.targetWeeks})),
  grid,
  cardTotals:{limit:T.limit, balance:T.cardBalance, usage:T.usage, min:sum('min'),
    attack:sum('attack'), other:sum('other'), total:sum('total'),
    interest:sum('weekInterest'), after:T.cardAfter, usageAfter:T.usageAfter, availAfter:T.availAfter},
  accountNames:S.accounts.map(a=>a.name),
  incomeAccount:(S.accounts.find(a=>a.kind==='income')||{}).name||'Checking',
  attack:attackData(), payoff:payoffData(),
  plan:planData(), accounts:accountsData(), history:historyData()
}, null, 1));
