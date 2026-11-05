// Guard the economic meaning of dated cross-checks, not just their markup.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const ctx=vm.createContext({DATA:{asOf:'2026-11-04'},researchDetail:()=>'',researchTable:()=>'',
 liveInventory:()=>ctx.series,liveSupply:()=>[],esc:String,num:String,signed:v=>String(v),liveSource:()=>'',domesticProfile:()=>null,
 LIVE_FUNDAMENTALS:{checkedAt:'2026-11-05'}});
vm.runInContext(fs.readFileSync(__dirname+'/research_quality_ui.js','utf8'),ctx);
ctx.market={name:'test',main:{contract:'x2701'},history:[
 {date:'2026-10-30',contract:'x2701',close:100},{date:'2026-11-04',contract:'x2701',close:110},
 {date:'2026-11-04',contract:'x2702',close:999},{date:'2026-11-05',contract:'x2701',close:1}]};
ctx.series=[{metric:'stock',scope:'single exchange',provider:'test',unit:'tonnes',history:[
 {date:'2026-10-30',value:100},{date:'2026-11-04',value:90},{date:'2026-11-05',value:999}]}];
const result=()=>vm.runInContext('researchInventoryChecks(market)',ctx)[0];
assert.equal(result().delta,-10);assert(Math.abs(result().priceReturn-10)<1e-10);
assert(result().observation.includes('方向相容'));assert.equal(result().last.date,'2026-11-04');
ctx.series[0].metric='receipt';assert(result().observation.includes('不能直接判定供需方向'));
ctx.series[0].metric='stock';ctx.series[0].history[1].date='2026-11-03';assert.equal(result().priceReturn,null);
ctx.series[0].history=[{date:'2026-11-04',value:0}];assert.equal(result().delta,null);assert.equal(result().last.value,0);
ctx.series[0].history=[{date:'2026-11-05',value:1}];assert.equal(vm.runInContext('researchInventoryChecks(market).length',ctx),0);
ctx.series=[];
const html=vm.runInContext('researchFundamentalCheck(market)',ctx);
assert(html.includes('部分证据')&&html.includes('不是三份独立证据')&&html.includes('没有可与行情日期对齐'));
assert(html.includes('采集时间不是发布时间'));
console.log('PASS: same-contract/date matching, future exclusion, receipt/stock distinction, missing endpoints, real zero and partial evidence boundaries.');
