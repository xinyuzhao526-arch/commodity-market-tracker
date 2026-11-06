// Independent, dated history. Never attach old percentiles to live analysis.
function historicalProduct(m){return HISTORICAL_RESEARCH.products?.[m.code]||null}
function historicalPercentile(value){return Number.isFinite(value)?num(value,1)+'%':'样本不足'}
function historicalDate(){return HISTORICAL_RESEARCH.asOf||'未取得'}
function historicalSampleNote(h){return h?`当前连续分段 ${h.currentSegmentSamples} 个样本；全历史 ${h.observations} 个，${h.segments} 段`:'未取得该品种历史'}
function historicalEventTable(m,period){
 const rows=(HISTORICAL_RESEARCH.events||[]).filter(e=>e.code===m.code&&e.period===period);
 if(!rows.length)return '<p class="research-gap">本时段没有符合条件且具有完整后续窗口的事件，不补零。</p>';
 return `<div class="table-wrap"><table class="market-table historical-event-table"><thead><tr><th>触发侧</th><th>随后交易日</th><th>事件数</th><th>收盘变动中位数</th><th>上涨占比</th><th>最大下跌均值</th><th>最大上涨均值</th></tr></thead><tbody>${rows.map(e=>`<tr><td>${esc(e.side)}</td><td>${e.horizon} 日</td><td>${e.count}${e.count<20?'<small class="metric-note">少量样本</small>':''}</td><td>${factorPct(e.median)}</td><td>${num(e.positivePct,1)}%</td><td>${factorPct(e.meanMaxDown)}</td><td>${factorPct(e.meanMaxUp)}</td></tr>`).join('')}</tbody></table></div>`;
}
function historicalResearchSection(m){
 const h=historicalProduct(m);if(!h)return '';
 const sufficient=Number.isFinite(h.volatilityPercentile)&&Number.isFinite(h.absDeviationPercentile);
 return `<section class="historical-research" aria-label="${esc(m.name)}历史位置与事件统计"><div class="historical-title"><h3>历史位置与偏离后的表现</h3><span class="badge">历史截至 ${esc(historicalDate())}</span></div><p class="historical-date-notice">当前行情 ${esc(DATA.asOf)} · 以下位置属于 ${esc(h.latest)} 的独立历史研究版本，没有与最新行情拼接。${esc(historicalSampleNote(h))}。</p><div class="historical-metrics">${researchMetric('波动历史分位',historicalPercentile(h.volatilityPercentile),`历史日20日年化波动 ${factorNum(h.rv20,2,'%')}`)}${researchMetric('绝对偏离历史分位',historicalPercentile(h.absDeviationPercentile),`历史日距MA20 ${factorNum(h.distanceAtr,2,' ATR')}`)}${researchMetric('历史样本完整性',sufficient?'满足分位门槛':'样本不足',`当前分段 ${h.currentSegmentSamples} 个；至少252个有效历史观察`)}</div><p class="metric-note">分位相对同一品种、同一完整分段内既往最多1260个有效观察计算，不是品种间强弱排名。断点分段独立，不跨段拼接；成交量、持仓不复权。</p><details class="historical-events"><summary>查看偏离后的5／10／20日分布与样本数</summary><p>固定阈值±2 ATR；同品种事件间隔至少21个交易日，触发合约量仓均≥1000手。统计截至 ${esc(historicalDate())}，只保留完整后续窗口。</p><h4>2022年至历史截止日</h4>${historicalEventTable(m,'2022–2026')}<details><summary>较早时段 · 2015–2021</summary>${historicalEventTable(m,'2015–2021')}</details><p class="research-gap">上涨占比不是未来胜率。跨品种仍可能相关；前后时段划分不等于正式样本外检验。收盘变动和期间最大涨跌相对事件日研究收盘计算，不含手续费、滑点、实际移仓与保证金影响，不是策略收益。</p></details><details><summary>数据来源与方法边界</summary><p>${esc(HISTORICAL_RESEARCH.source)}。${esc(HISTORICAL_RESEARCH.method)}</p><p>定义未知的00、001、JQ序列已排除；合约别名只有数值一致才合并，冲突日排除。部分品种因换月桥接或成交样本缺失而分段；不以长历史总数替代当前分段有效样本。</p></details></section>`;
}
function historicalContractMetrics(m){
 const rows=domesticCurveRows(m,DATA.asOf),main=rows.find(r=>r.contract.toLowerCase()===m.main.contract.toLowerCase());
 const total=rows.reduce((n,r)=>n+r.oi,0);
 const far=main&&main.volume>=1000&&main.oi>=1000?rows.filter(r=>r.month>main.month&&r.volume>=1000&&r.oi>=1000).sort((a,b)=>b.oi-a.oi)[0]:null;
 return {count:rows.length,main,share:main&&total>0?main.oi/total*100:null,far,
         spread:main&&far?(main.settle/far.settle-1)*100:null};
}
function historicalContractSection(m){
 const c=historicalContractMetrics(m);
 return `<section class="historical-contract"><h4>持仓集中度与活跃远月</h4><p class="metric-note">以下使用当前行情日 ${esc(DATA.asOf)} 的同日合约样本，独立于截至 ${esc(historicalDate())} 的历史统计。</p><div class="historical-metrics">${researchMetric('代表合约持仓占比',factorNum(c.share,1,'%'),`${c.count} 个有成交且结算有效的合约样本`)}${researchMetric('代表合约／活跃远月结算价差',factorPct(c.spread),c.far?`${c.main.contract.toUpperCase()} / ${c.far.contract.toUpperCase()}`:'合约或流动性不足，不计算')}</div><p class="metric-note">占比分母为已取得的同日、有成交且结算有效合约持仓合计，不声称交易所全市场口径。活跃远月须晚于代表合约，量仓均≥1000手，并在符合条件者中按持仓选择；价差＝代表合约结算／远月结算−1，不是现货基差或年化收益。</p></section>`;
}
const historicalDetailBase=researchDetail;
researchDetail=function(){const html=historicalDetailBase();return html.replace('<div class="analysis-source">',historicalResearchSection(selected())+'<div class="analysis-source">')};
const historicalCurveBase=domesticCurveArticle;
domesticCurveArticle=function(m){const html=historicalCurveBase(m);return html.replace('<p class="dimension-provenance">',historicalContractSection(m)+'<p class="dimension-provenance">')};
const historicalTableBase=researchTable;
researchTable=function(){
 historicalTableBase();
 const table=document.querySelector('.research-table'),head=table?.querySelector('thead tr');
 if(head&&!head.querySelector('[data-historical-column]'))head.insertAdjacentHTML('beforeend',`<th data-historical-column>历史波动分位<small>${esc(historicalDate())}</small></th><th data-historical-column>历史绝对偏离分位<small>${esc(historicalDate())}</small></th><th data-historical-column>历史有效样本<small>当前独立分段</small></th>`);
 document.querySelectorAll('#research-body [data-research-row]').forEach(row=>{
  const h=HISTORICAL_RESEARCH.products?.[row.dataset.researchRow];
  row.insertAdjacentHTML('beforeend',`<td class="historical-cell">${historicalPercentile(h?.volatilityPercentile)}</td><td class="historical-cell">${historicalPercentile(h?.absDeviationPercentile)}</td><td class="historical-cell" title="${esc(historicalSampleNote(h))}">${h?.currentSegmentSamples??'—'}<small class="metric-note">${Number.isFinite(h?.volatilityPercentile)?'可计算分位':'样本不足'}</small></td>`);
 });
 const empty=document.querySelector('#research-body .empty');if(empty)empty.colSpan=14;
};
const historicalHomeBase=productResearchHome;
productResearchHome=function(){historicalHomeBase();const host=document.querySelector('.product-research-home');if(!host||host.querySelector('.historical-notice'))return;const n=DATA.markets.filter(m=>Number.isFinite(historicalProduct(m)?.volatilityPercentile)).length;host.insertAdjacentHTML('beforeend',`<p class="historical-notice">新增历史研究 · 截至 ${esc(historicalDate())} · ${n}/${DATA.markets.length} 个品种满足历史分位门槛。研究矩阵末三列与品种详情可查看；历史日期与当前行情 ${esc(DATA.asOf)} 分开标注。</p>`)};
