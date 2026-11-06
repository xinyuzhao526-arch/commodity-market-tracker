const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const DATA=JSON.parse(fs.readFileSync(__dirname+'/../dist/data.json','utf8'));
const nodes={'#ranking':{innerHTML:''},'#oi-coverage':{textContent:''}},state={rankMode:'increase'};
const context=vm.createContext({DATA,state,$:s=>nodes[s],$$:()=>[],esc:String,compact:String,color:()=>'',bindSelection:()=>{}});
vm.runInContext(fs.readFileSync(__dirname+'/open_interest_ui.js','utf8'),context);
const observation=(m,basis='sample')=>{context.fixture=m;context.basis=basis;return vm.runInContext('openInterestObservation(fixture,basis)',context)};
const bar=(contract,oiChange,date=DATA.asOf)=>({contract,oiChange,date});
const market={main:{date:DATA.asOf},aggregateScope:'available-contracts',totalOiChange:null,
 contracts:[bar('x2701',10),bar('x2702',-4),bar('x2703',9000,'2000-01-01')]};
assert.equal(observation(market).value,6,'sum signed changes, exclude stale dates');
assert.equal(observation(market).count,2);
assert.equal(observation(market,'all'),null,'never call incomplete coverage all-contracts');
assert.equal(observation({...market,contracts:[bar('x2701',null)]}),null,'missing is not zero');
assert.equal(observation({...market,contracts:[bar('x2701',0)]}).value,0,'real zero remains valid');
assert.equal(observation({...market,contracts:[bar('X2701',1),bar('x2701',2)]}),null,'reject duplicates');
assert.equal(observation({...market,contracts:[]}),null);
assert.equal(observation({...market,aggregateScope:'all-contracts',totalOiChange:-20},'all').value,-20);
assert.equal(observation({...market,aggregateScope:'all-contracts',totalOiChange:-20,main:{date:'2000-01-01'}},'all'),null);
for(const basis of ['sample','all'])for(const mode of ['increase','decrease']){
 state.rankBasis=basis;state.rankMode=mode;vm.runInContext('ranking()',context);
 const expected=DATA.markets.map(m=>observation(m,basis)).filter(Boolean)
   .filter(r=>mode==='increase'?r.value>0:r.value<0)
   .sort((a,b)=>mode==='increase'?b.value-a.value:a.value-b.value).slice(0,6);
 const codes=Array.from(nodes['#ranking'].innerHTML.matchAll(/data-select="([^"]+)"/g),m=>m[1]);
 assert.deepEqual(codes,expected.map(r=>r.market.code));
 assert(!nodes['#ranking'].innerHTML.includes('undefined'));
}
// Distinguish unavailable observations from a valid sample with no increase.
const original=DATA.markets;DATA.markets=[{...market,code:'test',name:'test',contracts:[bar('x2701',-1)]}];
state.rankBasis='sample';state.rankMode='increase';vm.runInContext('ranking()',context);
assert(nodes['#ranking'].innerHTML.includes('可计算的 1 个品种中，暂无增仓样本'));
state.rankBasis='all';vm.runInContext('ranking()',context);
assert(nodes['#ranking'].innerHTML.includes('未取得可核实的全合约'));
DATA.markets=original;
console.log('PASS: signed OI sample sums, same-date isolation, missing/zero/duplicate handling, separate coverage and both ranked directions.');
