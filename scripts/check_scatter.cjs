// Check the chart's data boundary and ranges without a browser or dependencies.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync(path.join(__dirname,'research_ui.js'),'utf8');
const ctx=vm.createContext({});
vm.runInContext(src.slice(src.indexOf('const scatterState='),src.indexOf('function scatter(){')),ctx);
const layout=(rows,mode)=>{ctx.rows=rows;ctx.mode=mode;return vm.runInContext('scatterLayout(rows,mode)',ctx)};
const point=(code,price,oi)=>({code,analysis:{return5:price,oiReturn5:oi}});
const rows=[point('small-base',-2.5,1200),point('normal',1,20),point('negative',1.5,-40),point('missing',-3,null),point('invalid',NaN,100),point('upper',0,100),point('lower',0,-100),point('above',0,100.01),point('below',0,-100.01)];
const focused=layout(rows,'focus'),all=layout(rows,'all');
assert.equal(focused.valid.length,7);assert.equal(focused.shown.length,4);
assert.equal(focused.large.length,3);assert.equal(focused.yMin,-100);assert.equal(focused.yMax,100);
assert(focused.shown.some(m=>m.code==='upper'));assert(focused.shown.some(m=>m.code==='lower'));
assert(!focused.shown.some(m=>m.code==='small-base'));
assert.equal(new Set([...focused.shown,...focused.large].map(m=>m.code)).size,focused.valid.length);
assert.equal(all.shown.length,7);
for(const m of all.shown){assert(m.analysis.oiReturn5>=all.yMin&&m.analysis.oiReturn5<=all.yMax);assert(Math.abs(m.analysis.return5)<=all.xLimit)}
assert(all.yTicks.includes(0));assert(all.yMin<0&&all.yMax>1200);
// A large OI change must not appear as a positive price return.
assert(all.shown.find(m=>m.code==='small-base').analysis.return5<0);
const empty=layout([],'focus');assert.equal(empty.shown.length,0);assert(Number.isFinite(empty.xLimit));
const m={name:'paper',main:{contract:'op2701'},analysis:{asOf:'2026-10-30',return5Start:'2026-10-23'},history:[{date:'2026-10-23',contract:'op2612',oi:999999},{date:'2026-10-23',contract:'op2701',oi:1314,close:3682},{date:'2026-10-30',contract:'op2701',oi:17006,close:3588}]};
ctx.m=m;const endpoints=vm.runInContext('scatterEndpoints(m)',ctx);
assert.equal(endpoints.start.oi,1314);assert.equal(endpoints.end.oi,17006);
assert.equal(endpoints.start.close,3682);assert.equal(endpoints.end.close,3588);
console.log('PASS: linear focus/all ranges, outlier disclosure, inclusive boundaries, missing values, negative price with positive OI and fixed-contract endpoints.');
