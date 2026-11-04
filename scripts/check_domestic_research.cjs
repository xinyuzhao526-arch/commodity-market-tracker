// Validate provenance and financial-data boundaries without browser dependencies.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.join(__dirname,'..');
const packet=JSON.parse(fs.readFileSync(path.join(__dirname,'domestic_research.json'),'utf8'));
const snapshot=JSON.parse(fs.readFileSync(path.join(root,'dist/data.json'),'utf8'));
const expected='a b m y p oi rm rs pk cu al zn pb ni sn ao ad bc au ag pt pd si lc ps rb hc ss wr i j jm sf sm'.split(' ');
assert.deepEqual(Object.keys(packet.profiles).sort(),expected.sort());
assert.equal(packet.schema,'domestic-research-v1');
const iso=d=>/^\d{4}-\d{2}-\d{2}$/.test(d);
assert(iso(packet.reviewedAt));
for(const [key,s] of Object.entries(packet.sources)){
 assert(/^https?:\/\//.test(s.url),key);
 assert(s.published===null||iso(s.published)&&s.published<=packet.reviewedAt,key);
}
for(const [key,f] of Object.entries(packet.facts)){
 assert(packet.sources[f.source],key);assert(f.value&&f.period&&f.kind&&f.note,key);
 assert(packet.sources[f.source].type!=='待接入入口',key);
}
for(const [code,p] of Object.entries(packet.profiles)){
 assert(snapshot.markets.some(m=>m.code===code),code);
 for(const key of ['supply','demand','inference','overseas','missing','inventory','macro'])assert(p[key],code+' '+key);
 for(const id of [...p.supplyFacts,...p.demandFacts,...p.inventoryFacts])assert(packet.facts[id],code+' '+id);
 for(const id of [...p.links,p.exchangeSource])assert(packet.sources[id],code+' '+id);
}
// Prevent sector templates from silently replacing commodity-specific macro research.
const mechanisms=new Set(),titles=new Set();
for(const [code,p] of Object.entries(packet.profiles)){
 const r=p.macroResearch;assert(r,code+' macro configuration');
 assert(r.title&&r.counter&&r.paths.length>=2&&r.watch.length>=3,code);
 assert(!titles.has(r.title),code+' duplicate macro title');titles.add(r.title);
 const chain=r.paths.map(p=>p.chain).join(';');assert(!mechanisms.has(chain),code+' duplicate macro mechanism');mechanisms.add(chain);
 for(const p of r.paths)assert(p.label&&p.chain.includes('→'),code);
 for(const id of r.facts)assert(packet.facts[id],code+' macro evidence '+id);
}
assert(!packet.profiles.au.macroResearch.facts.includes('pmi'));
assert(packet.profiles.m.macroResearch.facts.includes('pigs'));
assert(packet.profiles.rb.macroResearch.facts.includes('property'));
assert.notDeepEqual(packet.profiles.al.macroResearch,packet.profiles.ao.macroResearch);
const source=fs.readFileSync(path.join(__dirname,'domestic_research_ui.js'),'utf8');
const macroContext=vm.createContext({DOMESTIC_RESEARCH:packet,DATA:snapshot,
 esc:s=>String(s),domesticPeriodNotice:()=>'',domesticFactCards:ids=>ids.join(','),domesticSourceFoot:()=>'',legacyDimensionArticle:()=>''});
vm.runInContext('function domesticProfile(m){return DOMESTIC_RESEARCH.profiles[m.code]}'+source.slice(source.indexOf('function domesticMacroIds('),source.indexOf('function domesticInventoryArticle(')),macroContext);
for(const code of expected){
 macroContext.market=snapshot.markets.find(m=>m.code===code);
 const html=vm.runInContext('domesticMacroArticle(market)',macroContext),r=packet.profiles[code].macroResearch;
 assert(html.includes(r.title)&&html.includes(r.counter),code+' rendered macro');
 for(const p of r.paths)assert(html.includes(p.chain),code+' missing transmission');
 for(const [other,p] of Object.entries(packet.profiles))if(other!==code)assert(!html.includes(p.macroResearch.title),code+' stale commodity content');
 assert(html.includes('跟踪变量 · 非实时读数')&&html.includes('统计期和发布日'),code+' evidence boundaries');
}
const functions=source.slice(source.indexOf('function domesticDelivery('),source.indexOf('function domesticCurveSvg('));
const ctx=vm.createContext({});vm.runInContext(functions,ctx);
const rows=(m,date='2026-10-30')=>{ctx.market=m;ctx.date=date;return vm.runInContext('domesticCurveRows(market,date)',ctx)};
const good=(contract,extra={})=>({code:'cu',contract,date:'2026-10-30',settle:100,volume:5,oi:8,...extra});
const result=rows({code:'cu',contracts:[good('cu2701',{settle:80}),good('cu2612',{settle:90}),good('cu2611'),good('cu2610',{date:'2026-10-29'}),good('cu2702',{settle:null}),good('cu2703',{volume:0}),good('cu2704',{code:'al'}),good('cu2609'),good('cu2713'),good('cu2611',{settle:999})]});
assert.equal(result.map(c=>c.contract).join(','),'cu2611,cu2612,cu2701');
assert.equal(result[0].settle-result[1].settle,10);
assert.equal(rows({code:'m',contracts:[{...good('m2701'),code:'m'}]}).length,1);
ctx.contract='oi701';ctx.date='2026-10-30';assert.equal(vm.runInContext('domesticDelivery(contract,date)',ctx),2027*12);
ctx.contract='sf001';ctx.date='2029-10-30';assert.equal(vm.runInContext('domesticDelivery(contract,date)',ctx),2030*12);
ctx.contract='cu2700';assert.equal(vm.runInContext('domesticDelivery(contract,date)',ctx),null);
// The standalone HTML must contain the research packet and no second request.
const app=fs.readFileSync(path.join(root,'dist/app.js'),'utf8');
assert.equal((app.match(/const DOMESTIC_RESEARCH=/g)||[]).length,1);
const report=expected.map(code=>{const m=snapshot.markets.find(m=>m.code===code);return {code,validMonths:rows(m,snapshot.asOf).length}});
console.log('PASS: 34 profiles, fact/source references and dates; monthly curve sorting, same-day isolation, missing settlement, zero volume, duplicate/invalid months, CZCE decade rollover.');
console.log(JSON.stringify({curves:report.filter(r=>r.validMonths>=2).length,insufficient:report.filter(r=>r.validMonths<2).map(r=>r.code)}));
