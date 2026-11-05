function continuousStudyPlot(m){
 const c=m.continuous;if(c?.status!=='ready'||c.history.length<2)return '';
 const all=c.history,offset=Math.max(0,all.length-60),rows=all.slice(offset).map((p,i)=>({...p,
  ma5:offset+i>=4?mean(all.slice(offset+i-4,offset+i+1).map(r=>r.close)):null,
  ma20:offset+i>=19?mean(all.slice(offset+i-19,offset+i+1).map(r=>r.close)):null}));
 const W=720,H=250,p={l:65,r:20,t:25,b:40},values=rows.flatMap(r=>[r.close,r.ma5,r.ma20]).filter(Number.isFinite),lo=Math.min(...values),hi=Math.max(...values),pad=(hi-lo||1)*.1,min=lo-pad,max=hi+pad;
 const x=i=>p.l+i/(rows.length-1)*(W-p.l-p.r),y=v=>p.t+(max-v)/(max-min)*(H-p.t-p.b);
 const path=key=>rows.map((r,i)=>Number.isFinite(r[key])?`${i===0||!Number.isFinite(rows[i-1][key])?'M':'L'}${x(i)},${y(r[key])}`:'').join(' ');
 return `<svg class="continuous-study-plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(m.name)}固定基准比例后复权研究价及MA5、MA20，非实际成交报价"><title>后复权研究价：实线；MA5：橙色；MA20：虚线</title>${[min,(min+max)/2,max].map(v=>`<line x1="${p.l}" x2="${W-p.r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)"/><text x="${p.l-6}" y="${y(v)+4}" text-anchor="end">${num(v,2)}</text>`).join('')}<path d="${path('close')}" fill="none" stroke="var(--accent)" stroke-width="2"/><path d="${path('ma5')}" fill="none" stroke="var(--amber)"/><path d="${path('ma20')}" fill="none" stroke="var(--muted)" stroke-dasharray="5 4"/>${[0,rows.length-1].map(i=>`<text x="${x(i)}" y="${H-12}" text-anchor="${i?'end':'start'}">${rows[i].date}</text>`).join('')}</svg>`;
}
function continuousStudySummary(m){
 const c=m.continuous,p=m.analysis.priceBasis;
 if(!c||!p)return '';
 if(!p.available)return `<section class="continuous-study research-gap"><strong>后复权连续研究数据不足</strong><p>最近已核实 ${esc(c.latest||'未取得')}；${esc(c.error||'当前尚无可核实的连续序列')}。连续指标留空，真实合约 ${esc(m.main.contract.toUpperCase())} 的报价、持仓及席位仍可查看。</p></section>`;
 return `<section class="continuous-study"><h3>价格研究口径 · 固定基准比例后复权</h3><p>基准 ${esc(c.baseDate)} / ${esc(c.baseContract.toUpperCase())} / ${num(c.basePrice,2)}；研究对应合约 ${esc(p.contract.toUpperCase())}，当前因子 ${num(p.factor,6)}。报价及量仓对应真实代表合约 ${esc(m.main.contract.toUpperCase())}；两者分别标注。</p><p>${esc(c.provider)}。依据前日持仓，远月超过当前合约1.1倍后于下一交易日切换，不回切；新因子＝旧因子×前日旧合约收盘÷前日新合约收盘。后复权研究价不等于实际报价或策略收益。</p><details><summary>后复权连续走势图 · 最近 ${Math.min(60,c.history.length)} / ${c.history.length} 个样本</summary>${continuousStudyPlot(m)}<p>蓝线为后复权研究价，橙线为MA5，虚线为MA20；OHLC统一应用同一因子，数量不复权。</p></details><details><summary>换月记录 · ${c.rollovers.length} 次</summary><div class="table-wrap"><table class="market-table"><thead><tr><th>切换日 / 比较日</th><th>旧 → 新</th><th>前日收盘（旧 / 新）</th><th>因子（前 → 后）</th><th>原始来源</th></tr></thead><tbody>${c.rollovers.map(r=>`<tr><td>${esc(r.date)}<small>${esc(r.comparisonDate)}</small></td><td>${esc(r.from.toUpperCase())} → ${esc(r.to.toUpperCase())}</td><td>${num(r.oldClose,2)} / ${num(r.newClose,2)}</td><td>${num(r.factorBefore,6)} → ${num(r.factorAfter,6)}</td><td>${[...new Set(r.sourceUrls.filter(Boolean))].map(url=>liveSource(url,'逐合约原始数据')).join(' · ')}</td></tr>`).join('')||'<tr><td colspan="5">本段观察内尚未发生换月。</td></tr>'}</tbody></table></div></details></section>`;
}
const continuousDetailBase=researchDetail;
researchDetail=function(){const html=continuousDetailBase(),summary=continuousStudySummary(selected());return html.replace('<div class="deviation-detail',summary+'<div class="deviation-detail')};
const actualSpark=spark;
spark=function(m,cls='mini-spark'){
 if(state.view!=='trends')return actualSpark(m,cls);
 if(m.continuous?.status!=='ready')return '<small class="metric-note">连续数据待补</small>';
 const rows=m.continuous.history.slice(-24),values=rows.map(r=>r.close);if(values.length<2)return '';
 const lo=Math.min(...values),range=Math.max(...values)-lo||1;
 return `<svg class="${cls}" viewBox="0 0 100 32" preserveAspectRatio="none" role="img" aria-label="${esc(m.name)}最近${values.length}个比例后复权连续研究样本"><polyline points="${values.map((v,i)=>`${i*100/(values.length-1)},${28-(v-lo)/range*24}`).join(' ')}" fill="none" stroke="var(--accent)" stroke-width="1.6" vector-effect="non-scaling-stroke"/></svg>`;
};
const continuousShellBase=tableShell;
tableShell=function(){let html=continuousShellBase();if(state.view==='trends')html=html.replace('近 24 样本','后复权走势');return html};
const continuousViewBase=trends;
trends=function(){const ready=DATA.markets.filter(m=>m.analysis.priceBasis?.available).length;return continuousViewBase().replace('<div class="coverage">',`<div class="coverage">后复权连续覆盖 ${ready} / ${DATA.markets.length}；对应行情日 ${DATA.asOf}。研究价不作为实际成交报价。`)};
