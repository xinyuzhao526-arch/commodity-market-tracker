// Independent evidence, never an extra vote in the price/position label.
function researchInventoryChecks(m){
 const price=new Map((m.history||[]).filter(p=>p.contract===m.main.contract&&p.date<=DATA.asOf&&Number.isFinite(p.close)&&p.close>0).map(p=>[p.date,p.close]));
 return liveInventory(m).map(s=>{
  const points=s.history.filter(p=>p.date<=DATA.asOf&&Number.isFinite(p.value)),last=points.at(-1),previous=points.at(-2);
  if(!last)return null;
  const delta=previous?last.value-previous.value:null,firstPrice=previous?price.get(previous.date):null,lastPrice=price.get(last.date);
  const priceReturn=firstPrice!=null&&lastPrice!=null?(lastPrice/firstPrice-1)*100:null;
  let observation=s.metric==='stock'?'同口径库存变化，不能单独区分需求与供给影响。':'仓单注册与注销不是终端消费，不能直接判定供需方向。';
  if(s.metric==='stock'&&priceReturn!=null&&delta!==null){
   observation=priceReturn>0&&delta<0?'同区间价格上涨、该口径去库：方向相容，仍需区分需求改善与供应减少。':
    priceReturn<0&&delta>0?'同区间价格下跌、该口径累库：方向相容，仍需核对到货与实际需求。':
    priceReturn>0&&delta>0?'同区间价格上涨、该口径累库：存在交叉核对线索，需检查到货、需求和预期。':
    priceReturn<0&&delta<0?'同区间价格下跌、该口径去库：存在交叉核对线索，需检查供应收缩及库存转移。':'价格或库存持平，不形成方向性对应。';
  }
  return {series:s,last,previous,delta,priceReturn,observation};
 }).filter(Boolean);
}
function researchFundamentalCheck(m){
 const checks=researchInventoryChecks(m),supplies=liveSupply(m),actual=supplies.filter(s=>s.kind==='实际统计'),forecast=supplies.filter(s=>s.kind==='年度预测');
 const inventoryHtml=checks.map(c=>{const s=c.series;return `<article class="fundamental-fact"><span class="badge">${s.metric==='stock'?'实物库存':'仓单 · 注册口径'}</span><h4>${esc(s.scope)} · ${esc(s.provider)}</h4><p>${c.previous?esc(c.previous.date)+' → ':''}${esc(c.last.date)}：${num(c.last.value,2)} ${esc(s.unit)}${c.delta!==null?'；相邻已取得样本变化 '+signed(c.delta,2)+' '+esc(s.unit):'；仅一个样本，无法计算变化'}。</p><p>${c.priceReturn!==null?'同一固定合约、相同日期的收盘变化 '+signed(c.priceReturn,2)+'%。':'缺少同日期的固定合约价格端点，不拼接其他日期或合约。'}</p><p>${esc(c.observation)}</p><p>${liveSource(c.last.sourceUrl||s.sourceUrl,s.provider)} · ${s.frequency==='weekly'?'周度':'日度'} · 仅该来源范围，不汇总不同口径。</p></article>`}).join('');
 const supplyHtml=supplies.map(s=>{const h=s.history.at(-1);return `<article class="fundamental-fact"><span class="badge">${esc(s.kind)}</span><h4>${esc(s.label)}</h4><p>${esc(h.period||h.date)}：${num(h.value,2)} ${esc(s.unit)}${h.yoy!=null?'；同比 '+signed(h.yoy,2)+'%':''}。</p><p>与本品种关系：${esc(s.appliesTo[m.code])}。${s.kind==='年度预测'?'预测修订不等于已实现产销。':'加工、终端及行业代理不能等同单品实际消费。'}</p><p>${liveSource(h.sourceUrl||s.sourceUrl,s.provider)} · 发布：${esc(h.publishedAt||'接口未提供，不能回填为当时已知信息')}</p></article>`}).join('');
 return `<section class="fundamental-crosscheck"><div class="eyebrow">INDEPENDENT EVIDENCE / 独立交叉核对</div><h3>基本面验证 · 部分证据，尚不能形成综合多空结论</h3><p>盘面标签描述后复权连续均线与真实合约价仓、席位样本，指标存在重复价格信息，不是三份独立证据。本区另行对照实物及产业资料，不将库存升降机械换算成利多或利空。</p><p class="research-date-notice">行情 ${DATA.asOf}；资料检查 ${esc(LIVE_FUNDAMENTALS.checkedAt)}。${checks.length} 条库存/仓单口径，${actual.length} 项自动采集实际统计、${forecast.length} 项年度预测。人工资料仍在供需维度按原日期展示。采集时间不是发布时间；后续采集或修订资料不能作为历史回测当时已知信息。</p><h4>库存与同区间价格</h4><div class="fundamental-facts">${inventoryHtml||'<p>没有可与行情日期对齐的实物库存或仓单样本。</p>'}</div><details><summary>产业统计与需求代理 · ${supplies.length} 项</summary><div class="fundamental-facts">${supplyHtml||'<p>自动采集的单品统计暂缺，可到供需页查看人工资料及其原日期。</p>'}</div></details><div class="research-gap"><strong>还缺什么，才能验证研究判断</strong><p>${esc(domesticProfile(m)?.missing||'同口径连续的需求、现货基差及订单资料。')}</p><p>局部交易所库存、仓单与行业产量不能构成全市场供需平衡表。基本面未完整验证时，保留分歧，不提高盘面标签的置信度。</p></div></section>`;
}
const qualityDetailBase=researchDetail;
researchDetail=function(){
 const m=selected(),a=m.analysis;
 const quality=a.liquidity?.low?`<div class="research-gap"><strong>低流动性 · 盘面结果谨慎解读</strong><p>代表合约当日成交 ${num(a.liquidity.volume)} 手、持仓 ${num(a.liquidity.oi)} 手。${esc(a.liquidity.rule)}。保留原始数据，不把稀疏成交与活跃品种的参考价值等同。</p></div>`:'';
 const html=qualityDetailBase(),marker='<div class="factor-grid">',evidence=quality+researchFundamentalCheck(m);
 return html.includes(marker)?html.replace(marker,evidence+marker):html+evidence;
};
const qualityTableBase=researchTable;
researchTable=function(){
 qualityTableBase();
 const lookup=new Map(DATA.markets.map(m=>[m.code,m]));
 document.querySelectorAll('#research-body [data-research-row]').forEach(row=>{
  const a=lookup.get(row.dataset.researchRow)?.analysis;
  if(a?.liquidity?.low)row.cells[0].insertAdjacentHTML('beforeend','<small class="research-quality-note">低流动性 · 谨慎解读</small>');
 });
};
