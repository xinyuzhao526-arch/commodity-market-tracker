const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const DATA=JSON.parse(fs.readFileSync(__dirname+'/../dist/data.json','utf8'));
const built=fs.readFileSync(__dirname+'/../dist/app.js','utf8');
assert(built.indexOf('function overviewExportRows(){')<built.indexOf('const trendContextTableBase=table;'),
 'overview must load before trend wrappers so existing continuous context is preserved');
const nodes={'#market-body':{innerHTML:''},'#table-count':{textContent:''}};
const state={exchange:'全部',sector:'全部',favorites:[],search:'',sort:'volume',order:-1};
const fmt=v=>v==null?'—':String(v);
const context=vm.createContext({DATA,state,$:s=>nodes[s],$$:()=>[],num:fmt,signed:fmt,compact:fmt,
 esc:String,color:()=>'',decimals:()=>0,spark:()=>'',trend:()=>({name:'test',class:''}),
 sourceOf:()=>({url:'https://example.com'}),heading:()=>'',stat:(l,v,u,n)=>`${l}: ${v}; ${n}`,
 chartPanel:()=>'',rankPanel:()=>'',exLabel:()=>'',exchangeNames:{}});
for(const f of ['open_interest_ui.js','overview_ui.js'])vm.runInContext(fs.readFileSync(__dirname+'/'+f,'utf8'),context);
function metric(m,field){context.market=m;context.field=field;return vm.runInContext('marketSampleMetric(market,field)',context)}
const bar=(contract,volume,oiChange,date=DATA.asOf)=>({contract,volume,oi:100,oiChange,date});
const fixture={contracts:[bar('x2701',10,5),bar('x2702',0,-2),bar('x2703',999,999,'2000-01-01')]};
assert.equal(metric(fixture,'volume').value,10);assert.equal(metric(fixture,'oiChange').value,3);
assert.equal(metric({...fixture,contracts:[bar('x2701',0,0)]},'volume').value,0);
assert.equal(metric({...fixture,contracts:[bar('x2701',-1,1)]},'volume'),null);
assert.equal(metric({...fixture,contracts:[bar('x2701',null,1)]},'volume'),null);
assert.equal(metric({...fixture,contracts:[bar('x2701',null,1)]},'oiChange').value,1);
assert.equal(metric({...fixture,contracts:[bar('x2701',10,null)]},'volume').value,10);
assert.equal(metric({...fixture,contracts:[bar('x2701',10,null)]},'oiChange'),null);
assert.equal(metric({...fixture,contracts:[bar('x2701',1,1),bar('X2701',2,2)]},'volume'),null);
const sourceSum=(m,field)=>{
 const rows=m.contracts.filter(r=>r.date===DATA.asOf);
 return rows.length&&rows.every(r=>Number.isFinite(r[field]))?rows.reduce((s,r)=>s+r[field],0):null;
};
for(const [sort,field] of [['volume','volume'],['oiChange','oiChange']])for(const order of [-1,1]){
 state.sort=sort;state.order=order;vm.runInContext('table()',context);
 const codes=Array.from(nodes['#market-body'].innerHTML.matchAll(/data-row="([^"]+)"/g),m=>m[1]);
 const expected=[...DATA.markets].sort((a,b)=>{const x=sourceSum(a,field),y=sourceSum(b,field);return x==null?(y==null?0:1):y==null?-1:(x-y)*order});
 assert.deepEqual(codes,expected.map(m=>m.code),'rendered sort matches signed sample values');
 for(const row of nodes['#market-body'].innerHTML.matchAll(/<tr[^>]*data-row="([^"]+)"[^>]*>(.*?)<\/tr>/g)){
  const m=DATA.markets.find(m=>m.code===row[1]);
  const cells=Array.from(row[2].matchAll(/<td[^>]*>(.*?)<\/td>/g),m=>m[1]);
  assert.equal(cells[5].split('<small')[0],fmt(sourceSum(m,'volume')));
  assert.equal(cells[6].split('<small')[0],fmt(sourceSum(m,'oiChange')));
 }
}
const exported=vm.runInContext('overviewExportRows()',context);
assert.equal(new Set(exported[0]).size,exported[0].length,'unique CSV headers');
for(let i=0;i<DATA.markets.length;i++){
 assert.equal(exported[i+1].length,exported[0].length);
 assert.equal(exported[i+1][9],sourceSum(DATA.markets[i],'volume'));
 assert.equal(exported[i+1][11],sourceSum(DATA.markets[i],'oiChange'));
}
const original=DATA.markets;DATA.markets=original.map(m=>({...m,contracts:[]}));
const empty=vm.runInContext('overview()',context);
assert(empty.includes('样本成交量: —'));assert(empty.includes('样本持仓量变化: <span class="">—</span>'));
DATA.markets=original;
console.log('PASS: sample volume/OI display, ascending/descending sort, independent missing fields, real zero, CSV alignment and empty summary guards.');
