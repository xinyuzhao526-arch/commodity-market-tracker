// Render real repair-tracking rows, which have an episode but no active watch.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/research_ui.js','utf8');
const DATA=JSON.parse(fs.readFileSync(__dirname+'/../dist/data.json','utf8'));
// Always exercise this boundary even on later snapshots with no repair episodes.
const fixture=JSON.parse(JSON.stringify(DATA.markets[0]));
fixture.code='test-repair';fixture.name='Repair regression fixture';
fixture.analysis.deviationWatch=null;
fixture.analysis.deviationEpisode={side:'below',label:'下方偏离后修复',focus:'关注反弹可能',
 phase:'阈值内修复',sessionsAfterHit:1,retracing:true,rangeReentry:false,priceCue:'当日反弹',
 observations:[],caveat:'Test-only boundary',gapContractionPct:20};
DATA.markets.push(fixture);
const results={innerHTML:''};
const context=vm.createContext({DATA,$:s=>s==='#deviation-results'?results:null,$$:()=>[],
 esc:String,num:v=>String(v??'—'),signed:v=>String(v??'—')});
vm.runInContext(source.slice(0,source.indexOf('function research(){')),context);
const repairs=DATA.markets.filter(m=>m.analysis.deviationEpisode&&!m.analysis.deviationWatch);
assert(repairs.length,'Episode-only regression fixture missing');
for(const filter of ['全部','上方偏离','下方偏离','修复跟踪','已有反向收盘']){
 context.filter=filter;
 vm.runInContext('deviationState.filter=filter;deviationState.expanded=true;deviationRows()',context);
 assert(!results.innerHTML.includes('undefined'),filter);
 if(filter==='修复跟踪')for(const m of repairs){
   if(m.analysis.deviationEpisode.sessionsAfterHit>0)
     assert(results.innerHTML.includes(`data-deviation-code="${m.code}"`),m.code);
 }
}
for(const market of DATA.markets){
 context.market=market;
 assert.equal(typeof vm.runInContext('deviationDetail(market.analysis)',context),'string');
}
console.log('PASS: real-snapshot deviation filters, episode-only repair rows and all product details render.');
