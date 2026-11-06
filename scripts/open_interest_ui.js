// Keep incomplete contract coverage separate from confirmed all-contract totals.
function openInterestObservation(m,basis='sample'){
 if(basis==='all')return m.aggregateScope==='all-contracts'&&m.main?.date===DATA.asOf&&Number.isFinite(m.totalOiChange)?{market:m,value:m.totalOiChange,count:null}:null;
 const rows=(m.contracts||[]).filter(r=>r.date===DATA.asOf);
 if(!rows.length||rows.some(r=>!r.contract||!Number.isFinite(r.oiChange))||new Set(rows.map(r=>r.contract.toLowerCase())).size!==rows.length)return null;
 return {market:m,value:rows.reduce((sum,r)=>sum+r.oiChange,0),count:rows.length};
}
rankPanel=function(){return `<section class="panel"><div class="panel-top"><div><div class="panel-title">增减仓观察</div><div class="panel-kicker">OPEN INTEREST / 跨品种排行 · ${DATA.asOf}</div></div><div class="tabs"><button class="chip ${state.rankMode==='increase'?'active':''}" data-rank="increase">增仓</button><button class="chip ${state.rankMode==='decrease'?'active':''}" data-rank="decrease">减仓</button></div></div><div class="filters" role="group" aria-label="增减仓统计口径"><button class="filter-btn" data-oi-basis="sample">已取得合约样本</button><button class="filter-btn" data-oi-basis="all">全合约合计</button></div><div class="chart-note" id="oi-coverage"></div><div class="ranking" id="ranking"></div><div class="chart-note">单位：手。已取得合约样本不代表交易所全合约；两个口径分别排行。<br>持仓增减不等同方向性资金流。本栏比较当前覆盖品种，不随单个合约选择变化。</div></section>`};
ranking=function(){
 const basis=state.rankBasis||'sample',eligible=DATA.markets.map(m=>openInterestObservation(m,basis)).filter(Boolean);
 const rows=eligible.filter(r=>state.rankMode==='increase'?r.value>0:r.value<0).sort((a,b)=>state.rankMode==='increase'?b.value-a.value:a.value-b.value).slice(0,6);
 const max=Math.max(...rows.map(r=>Math.abs(r.value)),1),scope=basis==='all'?'全合约合计':'已取得合约样本';
 $('#oi-coverage').textContent=`${scope} · 可计算 ${eligible.length} / ${DATA.markets.length} 个品种；缺失或重复合约不补零。`;
 $('#ranking').innerHTML=rows.length?rows.map((r,i)=>{const m=r.market;return `<button class="rank-row" data-select="${esc(m.code)}" title="${scope}${r.count==null?'':' · '+r.count+' 个同日合约'}"><span class="rank-number">0${i+1}</span><span class="rank-name">${esc(m.name)}${r.count==null?'':`<small class="metric-note">${r.count} 个合约</small>`}</span><span class="rank-track"><span style="width:${Math.abs(r.value)/max*100}%;background:${r.value>0?'#c78b77':'#8ea68b'}"></span></span><span class="rank-val ${color(r.value)}">${r.value>0?'+':''}${compact(r.value)}</span></button>`}).join(''):`<p class="empty">${!eligible.length?(basis==='all'?'本次未取得可核实的全合约持仓变化；可切换“已取得合约样本”查看。':'本次缺少可计算的同日合约持仓变化。'):`可计算的 ${eligible.length} 个品种中，暂无${state.rankMode==='increase'?'增仓':'减仓'}样本。`}</p>`;
 $$('[data-oi-basis]').forEach(b=>{const active=b.dataset.oiBasis===basis;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));b.onclick=()=>{state.rankBasis=b.dataset.oiBasis;ranking()}});
 bindSelection($('#ranking'));
};
