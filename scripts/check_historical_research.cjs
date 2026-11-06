// Guard dates, missing-data boundaries, contract scope and actual data rendering.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=__dirname+'/../dist/';
const hist=JSON.parse(fs.readFileSync(root+'historical-research.json','utf8'));
const data=JSON.parse(fs.readFileSync(root+'data.json','utf8'));
assert.equal(hist.schema,'historical-research-v1');assert.equal(Object.keys(hist.products).length,34);
assert(hist.asOf<=data.asOf);
for(const h of Object.values(hist.products)){
 assert(h.latest<=hist.asOf&&h.currentSegmentSamples<=h.observations);
 for(const key of ['volatilityPercentile','absDeviationPercentile']){
  const v=h[key];assert(v===null||Number.isFinite(v)&&v>=0&&v<=100);
  if(h.currentSegmentSamples<=252)assert.equal(v,null);
 }
}
for(const e of hist.events){assert([5,10,20].includes(e.horizon));assert(e.count>0);assert(e.positivePct>=0&&e.positivePct<=100);assert(Number.isFinite(e.median));}
const ctx=vm.createContext({HISTORICAL_RESEARCH:hist,DATA:data,esc:String,num:(n,d=2)=>Number(n).toFixed(d),
 factorNum:(n,d=2,s='')=>n==null?'—':Number(n).toFixed(d)+s,
 factorPct:n=>n==null?'—':Number(n).toFixed(2)+'%',researchMetric:(a,b,c)=>`<article>${a}|${b}|${c}</article>`,
 researchDetail:()=>'<div class="analysis-source">source</div>',domesticCurveArticle:()=>'<p class="dimension-provenance">source</p>',
 researchTable:()=>{},productResearchHome:()=>{},selected:()=>data.markets[0]});
const src=fs.readFileSync(__dirname+'/domestic_research_ui.js','utf8');
vm.runInContext(src.slice(src.indexOf('function domesticDelivery('),src.indexOf('function domesticCurveSvg(')),ctx);
vm.runInContext(fs.readFileSync(__dirname+'/historical_research_ui.js','utf8'),ctx);
for(const m of data.markets.filter(m=>hist.products[m.code])){
 ctx.market=m;
 const html=vm.runInContext('historicalResearchSection(market)',ctx);
 assert(html.includes(hist.asOf)&&html.includes(data.asOf));assert(!/undefined|NaN|Infinity/.test(html));
 for(const period of ['2015–2021','2022–2026']){ctx.period=period;assert(!/undefined|NaN|Infinity/.test(vm.runInContext('historicalEventTable(market,period)',ctx)));}
 const c=vm.runInContext('historicalContractMetrics(market)',ctx);
 assert(c.share===null||c.share>=0&&c.share<=100);
 if(c.far){assert(c.far.date===data.asOf&&c.main.date===data.asOf);assert(c.far.month>c.main.month);assert(c.far.oi>=1000&&c.far.volume>=1000);}
}
ctx.fake={code:'x',main:{contract:'x2701'},contracts:[
 {code:'x',contract:'x2701',date:data.asOf,settle:100,oi:4000,volume:2000},
 {code:'x',contract:'x2702',date:data.asOf,settle:110,oi:2000,volume:1000},
 {code:'x',contract:'x2703',date:'2000-01-01',settle:1,oi:999999,volume:99999}]};
const result=vm.runInContext('historicalContractMetrics(fake)',ctx);
assert.equal(result.count,2);assert(Math.abs(result.share-4000/6000*100)<1e-10);assert(Math.abs(result.spread-(100/110-1)*100)<1e-10);
ctx.fake.contracts[1].settle=null;assert.equal(vm.runInContext('historicalContractMetrics(fake).spread',ctx),null);
assert.equal(vm.runInContext('historicalPercentile(null)',ctx),'样本不足');
console.log('PASS: historical dates, 34 product details, event counts, missing percentiles, wrong-date exclusion and contract concentration/spread.');
