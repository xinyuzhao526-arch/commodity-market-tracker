// Verify filters and exported state columns against the published snapshot.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/research_ui.js','utf8');
const DATA=JSON.parse(fs.readFileSync(__dirname+'/../dist/data.json','utf8'));
let csv='';
const context=vm.createContext({DATA,esc:String,num:v=>String(v??'—'),signed:v=>String(v??'—'),
 sourceOf:m=>m.source||{url:''},toast:()=>{},setTimeout:()=>{},
 Blob:class{constructor(parts){csv=parts.join('')}},
 URL:{createObjectURL:()=>'',revokeObjectURL:()=>{}},
 document:{createElement:()=>({click:()=>{}})}});
vm.runInContext(source.slice(0,source.indexOf('function research(){')),context);
for(const m of DATA.markets){
 context.m=m;
 const s=m.analysis.marketState;
 assert(s&&Array.isArray(s.checks)&&Array.isArray(s.missing));
 for(const [filter,expected] of [['全部',true],['均线偏多',m.analysis.trendDirection===1],
   ['均线偏空',m.analysis.trendDirection===-1],['偏空反弹',s.phase==='偏空中的反弹'],
   ['偏多回落',s.phase==='偏多中的回落'],['严格同向',m.analysis.status==='多维同向'],
   ['席位待核对',s.checks.some(v=>v.startsWith('席位'))],['数据待补',s.missing.length>0]]){
   context.filter=filter;
   assert.equal(!!vm.runInContext('researchFilterMatch(m,filter)',context),expected,`${m.code}: ${filter}`);
 }
 const badge=vm.runInContext('researchBadge(m.analysis)',context);
 assert(!badge.includes('undefined')&&!badge.includes('存在分歧'));
 assert(badge.includes(s.phase));
}
vm.runInContext(source.slice(source.indexOf('function exportResearch(){')),context);
vm.runInContext('exportResearch()',context);
const rows=csv.replace(/^\ufeff/,'').split('\r\n').map(line=>
 Array.from(line.matchAll(/"((?:[^"]|"")*)"(?:,|$)/g),m=>m[1].replaceAll('""','"')));
assert.equal(rows.length,DATA.markets.length+1);
const headers=rows[0];
for(let i=0;i<DATA.markets.length;i++){
 const m=DATA.markets[i],row=rows[i+1],s=m.analysis.marketState;
 assert.equal(row.length,headers.length,`CSV columns: ${m.code}`);
 assert.equal(row[headers.indexOf('当日状态')],s.phase);
 assert.equal(row[headers.indexOf('均线方向')],s.trend);
 assert.equal(row[headers.indexOf('严格同向_辅助筛选')],String(s.strictAlignment));
}
console.log('PASS: descriptive states, independent filters, strict legacy conditions and CSV column alignment.');
