// Describe the moving-average state, daily price action and distance separately.
// A rebound is an observed close-to-close move, not a trend reversal forecast.
function trendContextMarkup(m){
 const t=trend(m),a=m.analysis||{},day=a.return1,d=a.deviationWatch;
 const meanLabel={bull:'均线偏多',bear:'均线偏空',mixed:'均线分化'}[t.id]||t.name;
 const dayLabel=!Number.isFinite(day)?'昨收比较缺失':day===0?'当日持平':day>0?(t.id==='bear'?'当日反弹':'当日上涨'):(t.id==='bull'?'当日回落':'当日下跌');
 const dayText=dayLabel+(Number.isFinite(day)?' '+signed(day,2)+'% · 较昨收':'');
 const distance=Number.isFinite(a.distanceAtr20)?`距 MA20 ${signed(a.distanceAtr20,2)} ATR`:'均值偏离样本不足';
 return `<div class="trend-context" aria-label="${esc(m.name)}均线与短线观察"><span class="badge ${t.class}" title="${esc(a.asOf||m.main.date)}：收盘价与MA5相对MA20的位置；不预测下一交易日">${esc(meanLabel)}</span><strong class="trend-day ${Number.isFinite(day)?color(day):''}">${esc(dayText)}</strong>${d?`<span class="trend-distance">${esc(d.label)} ${esc(signed(a.distanceAtr20,2))} ATR · ${esc(d.focus)}</span><small class="metric-note">偏离不代表必然反转</small>`:`<span class="trend-distance">${esc(distance)}</span>`}</div>`;
}
const trendContextTableBase=table;
table=function(){
 trendContextTableBase();
 const markets=new Map(DATA.markets.map(m=>[m.code,m]));
 document.querySelectorAll('#market-body [data-row]').forEach(row=>{const m=markets.get(row.dataset.row);if(m&&row.cells[7])row.cells[7].innerHTML=trendContextMarkup(m)});
};
const trendContextShellBase=tableShell;
tableShell=function(){return trendContextShellBase().replace('<th>趋势状态</th>','<th>均线 / 短线观察</th>').replace('红涨绿跌 · 点击品种查看价格与席位结构','日涨跌幅较昨结；短线观察较昨收 · 点击品种查看详情')};
const trendContextViewBase=trends;
trends=function(){return trendContextViewBase().replace("趋势偏多","均线偏多").replace("趋势偏空","均线偏空").replace('这里的趋势标签是本站透明规则的计算结果：使用当前代表合约的历史收盘价，短周期 MA5、中周期 MA20。它并非实际 CTA 基金仓位，也不是参考站的专有模型。','均线状态只描述收盘价、MA5与MA20的位置；短线观察独立显示当日反弹或回落。偏离MA20达到2 ATR时另列反弹或回调观察，尚未达到门槛也会显示实际偏离。反弹不等于趋势反转，均线偏空也不代表排除反弹。表格日涨跌幅采用昨结算价，短线观察采用昨收盘价，两个基准分别展示。')};
