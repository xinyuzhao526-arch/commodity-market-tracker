// BEGIN TERMINAL UI
const terminalPrefs={ready:false,previousView:null,commandIndex:0,commandMarkets:[],lastFocus:null};
function terminalSafeRead(key,fallback){try{return localStorage.getItem(key)||fallback}catch{return fallback}}
function terminalSave(key,value){try{localStorage.setItem(key,value)}catch{}}
function closeInspector(){document.body.classList.remove('inspector-open');$('#research-detail')?.setAttribute('aria-hidden','true')}
function terminalInspector(){
 const target=$('#research-detail');if(!target)return;
 target.classList.add('terminal-inspector');target.setAttribute('role','complementary');target.setAttribute('aria-label','品种证据面板');target.setAttribute('aria-hidden',document.body.classList.contains('inspector-open')?'false':'true');
 if(!target.querySelector('.inspector-controls'))target.insertAdjacentHTML('afterbegin','<div class="inspector-controls"><span>INSTRUMENT / EVIDENCE</span><div><button id="inspector-price" class="tool-button">查看价格图 ↗</button><button id="inspector-close" class="icon-button" aria-label="关闭证据面板">×</button></div></div>');
 $('#inspector-close').onclick=closeInspector;
 $('#inspector-price').onclick=()=>{closeInspector();location.hash='overview';setTimeout(()=>$('#detail')?.scrollIntoView({behavior:'smooth',block:'start'}),60)};
}
selectResearch=function(code){
 state.selected=code;$('#research-detail').innerHTML=researchDetail();bindResearchDetail();researchTable();scatter();terminalInspector();document.body.classList.add('inspector-open');$('#research-detail').setAttribute('aria-hidden','false');
};
function terminalJump(code){closeCommand();state.selected=code;if(state.view==='research')selectResearch(code);else{location.hash='research';setTimeout(()=>{if($('#research-detail'))selectResearch(code)},60)}}
function openCommand(){
 terminalPrefs.lastFocus=document.activeElement;$('#command-menu').hidden=false;$('#command-input').value='';terminalPrefs.commandIndex=0;terminalCommandResults();$('#command-input').focus();
}
function closeCommand(){$('#command-menu').hidden=true;terminalPrefs.lastFocus?.focus?.()}
function terminalCommandResults(){
 const q=$('#command-input').value.trim().toLowerCase();const ms=DATA.markets.filter(m=>`${m.name} ${m.code} ${m.main.contract} ${m.exchange}`.toLowerCase().includes(q)).slice(0,12);terminalPrefs.commandMarkets=ms;terminalPrefs.commandIndex=Math.max(0,Math.min(terminalPrefs.commandIndex,ms.length-1));
 $('#command-results').innerHTML=ms.length?ms.map((m,i)=>`<button role="option" aria-selected="${i===terminalPrefs.commandIndex}" class="command-result ${i===terminalPrefs.commandIndex?'active':''}" data-command-code="${m.code}"><span class="command-symbol">${m.code.toUpperCase()}</span><span class="command-market">${m.name}<small>${m.main.contract.toUpperCase()} · ${m.exchange}</small></span><span class="command-metric ${color(m.analysis?.return20)}">${factorPct(m.analysis?.return20)}<small>20 日收益</small></span><span class="command-enter">↵</span></button>`).join(''):'<div class="empty">没有匹配的品种。</div>';
 $$('[data-command-code]').forEach(b=>b.onclick=()=>terminalJump(b.dataset.commandCode));
}
function terminalInit(){
 if(terminalPrefs.ready)return;terminalPrefs.ready=true;
 const root=document.documentElement;root.dataset.theme=terminalSafeRead('guanlan-theme','dark');root.dataset.density=terminalSafeRead('guanlan-density','compact');
 document.body.classList.toggle('rail-collapsed',terminalSafeRead('guanlan-rail','expanded')==='collapsed');
 const theme=()=>{$('#theme-toggle').textContent=root.dataset.theme==='dark'?'浅色':'深色';$('#theme-toggle').setAttribute('aria-label',root.dataset.theme==='dark'?'切换为浅色主题':'切换为深色主题')};
 const density=()=>{$('#density-toggle').textContent=root.dataset.density==='compact'?'紧凑':'舒展';$('#density-toggle').setAttribute('aria-label','切换信息密度，当前'+$('#density-toggle').textContent)};
 theme();density();$('#theme-toggle').onclick=()=>{root.dataset.theme=root.dataset.theme==='dark'?'light':'dark';terminalSave('guanlan-theme',root.dataset.theme);theme()};
 $('#density-toggle').onclick=()=>{root.dataset.density=root.dataset.density==='compact'?'comfortable':'compact';terminalSave('guanlan-density',root.dataset.density);density()};
 $('#nav-toggle').onclick=()=>{const c=document.body.classList.toggle('rail-collapsed');terminalSave('guanlan-rail',c?'collapsed':'expanded');$('#nav-toggle').setAttribute('aria-label',c?'展开侧边导航':'收起侧边导航')};
 $('#command-open').onclick=openCommand;$('#command-close').onclick=closeCommand;$('#command-menu').onclick=e=>{if(e.target===$('#command-menu'))closeCommand()};
 $('#command-input').oninput=()=>{terminalPrefs.commandIndex=0;terminalCommandResults()};
 $('#command-input').onkeydown=e=>{if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();const n=terminalPrefs.commandMarkets.length;if(n){terminalPrefs.commandIndex=(terminalPrefs.commandIndex+(e.key==='ArrowDown'?1:n-1))%n;terminalCommandResults();$('#command-results .active')?.scrollIntoView({block:'nearest'})}}else if(e.key==='Enter'){e.preventDefault();const m=terminalPrefs.commandMarkets[terminalPrefs.commandIndex];if(m)terminalJump(m.code)}};
 document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openCommand()}if(e.key==='Escape'){if(!$('#command-menu').hidden)closeCommand();else closeInspector()}});
}
function terminalMatrix(){
 const header=$('#research-table-title');if(!header||header.closest('.matrix-workspace'))return;
 const toolbar=header.nextElementSibling,panel=toolbar?.nextElementSibling,stats=$('#app .stats-grid');if(!toolbar||!panel||!stats)return;
 const section=document.createElement('section');section.className='matrix-workspace';(document.querySelector('#deviation-watch')||stats).insertAdjacentElement('afterend',section);section.append(header,toolbar,panel);
 const table=section.querySelector('table');if(table)table.setAttribute('aria-label','横截面研究矩阵');
 const detail=$('#research-detail');if(detail)detail.classList.add('terminal-inspector');
 const methods=$('#research-method');if(methods&&!methods.closest('details')){const fold=document.createElement('details');fold.className='terminal-methods';fold.innerHTML='<summary><span>指标定义与判定规则</span><small>收益口径 / 价仓联动 / 席位边界</small><span>＋</span></summary>';methods.insertAdjacentElement('beforebegin',fold);fold.append(methods)}
 if($('#jump-research-method'))$('#jump-research-method').onclick=e=>{e.preventDefault();const fold=$('#research-method').closest('details');if(fold)fold.open=true;$('#research-method').scrollIntoView({behavior:'smooth',block:'start'})};
}
const terminalHeadingBase=heading;
heading=function(title,sub,kicker){const titles={research:'研究雷达',overview:'市场概览',trends:'趋势全景',positions:'持仓结构',sources:'数据与方法'};const subs={research:'均值偏离观察、横截面强弱与历史席位证据',overview:'收盘价格、成交与持仓变化',trends:'固定合约趋势状态与跨品种比较',positions:'会员排名、样本差与持仓集中度',sources:'数据覆盖、计算口径与可用性'};return terminalHeadingBase(titles[state.view]||title,subs[state.view]||sub,kicker)};
function terminalSync(){
 terminalInit();if(terminalPrefs.previousView!==state.view)closeInspector();terminalPrefs.previousView=state.view;
 $('#side-date').textContent=DATA.asOf;$('#terminal-date').textContent=DATA.asOf+' / 收盘';$('#terminal-date').title='数据快照日期 '+DATA.asOf+'，非实时行情';
 const ribbon=$('#market-ribbon');ribbon.innerHTML=['au','cu','rb','m','y','p','lc','i'].map(c=>DATA.markets.find(m=>m.code===c)).filter(Boolean).map(m=>`<button class="ribbon-quote" data-ribbon-code="${m.code}" aria-label="查看${m.name}证据"><span>${m.name}</span><b>${num(m.main.close,decimals(m))}</b><em class="${color(m.main.changePct)}">${signed(m.main.changePct,2)}%</em></button>`).join('');$$('[data-ribbon-code]').forEach(b=>b.onclick=()=>terminalJump(b.dataset.ribbonCode));
 $('#app').dataset.view=state.view;$('#export').innerHTML='<span>↓</span> '+(state.view==='research'?'导出研究':'导出数据');
 if(state.view==='research'){terminalMatrix();terminalInspector()}
 $$('nav [data-view]').forEach(a=>a.setAttribute('aria-current',a.dataset.view===state.view?'page':'false'));
}

const researchGroups={
 '油脂油料':['a','b','m','y','p','oi','rm','rs','pk'],
 '有色金属（含贵金属）':['cu','al','zn','pb','ni','sn','ao','ad','bc','au','ag','pt','pd','si','lc','ps'],
 '黑色':['rb','hc','ss','wr','i','j','jm','sf','sm']
};
let researchScopeReady=false;
function applyResearchScope(){
 if(researchScopeReady)return;researchScopeReady=true;
 DATA.markets=DATA.markets.filter(m=>Object.values(researchGroups).some(codes=>codes.includes(m.code)));
 DATA.markets.forEach(m=>{m.sector=Object.keys(researchGroups).find(g=>researchGroups[g].includes(m.code));if(m.analysis)m.analysis.sector=m.sector});
 DATA.research.sectors=Object.keys(researchGroups).map(sector=>{const ms=DATA.markets.filter(m=>m.sector===sector),rs=ms.map(m=>m.analysis.return20).filter(Number.isFinite).sort((a,b)=>a-b),n=rs.length;return {sector,count:ms.length,return20Count:n,positive20:rs.filter(v=>v>0).length,medianReturn20:n?(rs[Math.floor((n-1)/2)]+rs[Math.floor(n/2)])/2:null,bull:ms.filter(m=>m.analysis.trendDirection===1).length,bear:ms.filter(m=>m.analysis.trendDirection===-1).length}});
 DATA.research.aligned=DATA.markets.filter(m=>m.analysis.status==='多维同向').length;
 DATA.research.conflicts=DATA.markets.filter(m=>m.analysis.status==='存在分歧').length;
 if(!DATA.markets.some(m=>m.code===state.selected))state.selected=DATA.markets[0].code;
}
const dimensionNames=['宏观驱动','供需逻辑','库存变化','合约结构'];
const copperNotes=[
 {title:'加息预期与风险偏好',date:'2026-11-03',summary:'截图认为：美联储12月加息预期升温，叠加美国PCE数据影响，基本金属承压。',sections:[['主要宏观变化','跟踪利率预期、美元与通胀数据。截图将铜价回落解释为宏观情绪主导；这些解释尚未独立核验。'],['对铜的传导','利率预期 → 美元及风险偏好 → 金属估值；同时关注美国关税预期、跨市场价差与交仓行为。'],['后续关注','核对下一次通胀数据的实际公布日与结果，并观察宏观预期是否与库存、现货价格同向。']]},
 {title:'现货升水收窄，海外累库',date:'2026-11-02',summary:'截图记录LME铜现货结算价14,380美元/吨，较前一交易日下降69美元，现货仍处小幅升水。',sections:[['现货与基差','报价对象为LME铜现货结算价；前值14,449美元/吨（2026-10-30）。截图未提供可核验的现货升水绝对值。'],['供应端','截图列示2026-10-26 LME总库存272,950吨，其中美国169,475吨；另列全球8月精炼铜产量246.7万吨。统计日期与口径应分别核对。'],['需求端','所附截图未展示完整消费、出货或替代需求数据，暂不补写需求结论。']]},
 {title:'注册仓单增加17,225吨',date:'2026-11-02',summary:'截图列示LME注册仓单263,375吨，前值246,150吨，增加17,225吨（约7.0%）。',sections:[['库存观察','注册仓单与交易所总库存属于不同口径；跨交易所数据分别展示，不直接加总。'],['后续关注','区分注册仓单、注销仓单与总库存，进一步观察地区分布、入库出库和现货升贴水。']],table:{heads:['指标','当期 / 吨','前期 / 吨','变化 / 吨','日期'],rows:[['LME注册仓单','263,375','246,150','+17,225','2026-11-02'],['LME总库存','309,650','293,775','+15,875','2026-11-03'],['阴极铜期货库存','9,450','10,600','−1,150','2026-11-03'],['COMEX铜库存','804,356','802,686','+1,670','2026-11-02']]}},
 {title:'近月升水扩大',date:'2026-11-03',summary:'截图文字称2026年11月合约较12月、2027年1月和2月合约分别升水42.08、79.09和91.29。',sections:[['结构观察','截图认为近月强于远月，并在更远端出现结构变化。该LME曲线不能替代沪铜期限结构。'],['口径待核对','截图文字使用“近月减远月”的正值，表格却使用负值，且单位标为“元”；月差方向与报价币种存在待核对项，因此不据此绘制完整曲线。'],['两端贡献','截图称近月上涨142.11，三个远月分别上涨119.59、103.51和98.21。仅保留为截图摘录，待原始行情核验。']],table:{heads:['近月 / 远月','文字所述升水','表格月差','表格月差变化'],rows:[['2611 / 2612','42.08','−42.08','−22.52'],['2611 / 2701','79.09','−79.09','−38.60'],['2611 / 2702','91.29','−91.29','−43.90']]}}
];
function dimensionNote(m,i){
 if(m.code==='cu')return copperNotes[i];
 const oil=m.sector==='油脂油料',black=m.sector==='黑色',precious=['au','ag','pt','pd'].includes(m.code);
 const topics=oil?['汇率、进口政策、生物柴油政策与天气事件','产区种植与收获、压榨开机、进口到港、油粕消费','港口与油厂库存、库存天数、周度出入库','现货基差、油粕比、近远月价差与进口利润']:black?['地产与基建政策、钢铁产能及环保政策','铁水产量、钢厂开工、原料到货与终端成交','钢厂与社会库存、港口库存、周度去库速度','现货基差、月间价差、钢厂利润与原料比价']:precious?['实际利率、美元、央行政策与避险事件','矿产及回收供应、央行及投资需求、工业消费','交易所库存、ETF持仓与可交割库存','内外盘价差、现货升贴水与月间价差']:['美元与利率、产业政策、关税与能源成本','矿端供应、冶炼开工、进口到货与下游订单','交易所与社会库存、仓单及地区分布','现货升贴水、月间价差、进口盈亏与加工利润'];
 return {title:m.name+' · '+dimensionNames[i],date:null,summary:'尚未接入该品种的'+dimensionNames[i]+'研究资料。',sections:[['跟踪项目',topics[i]],['当前可用信息',`盘面快照为 ${DATA.asOf}，代表合约 ${m.main.contract.toUpperCase()}。下方保留已计算的价格、量仓和席位证据；这些数据不能替代本维度所需的原始资料。`]]};
}
let activeDimension=0;
function dimensionArticle(m,i){const n=dimensionNote(m,i);return `<article class="dimension-article"><div class="eyebrow">${n.date?'资料日期 '+n.date:'待补充资料'} · ${m.code==='cu'?'用户截图摘录 / 未独立核验 / LME铜':'研究跟踪清单'}</div><h3>${esc(n.title)}</h3><p class="dimension-summary">${esc(n.summary)}</p>${n.table?`<div class="table-wrap"><table class="market-table"><thead><tr>${n.table.heads.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${n.table.rows.map(row=>`<tr>${row.map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:''}${n.sections.map(([h,t])=>`<h4>${esc(h)}</h4><p>${esc(t)}</p>`).join('')}${m.code==='cu'?'<p class="dimension-provenance">来源：本次提供的研究截图（原图标注AI生成）。LME资料日期与本站境内行情快照分别展示，尚未接入自动更新。</p>':''}</article>`}
const dimensionDetailBase=researchDetail;
researchDetail=function(){const m=selected();return `<section class="dimension-workspace"><div class="panel-top"><div><div class="eyebrow">PRODUCT RESEARCH / ${esc(m.sector)}</div><h2>${esc(m.name)} · 研究维度</h2><p>${m.code==='cu'?'LME铜资料参考 · 境内沪铜盘面另见下方':'选择维度查看资料与跟踪项目'}</p></div></div><div class="dimension-tabs" role="tablist" aria-label="研究维度">${dimensionNames.map((n,i)=>`<button role="tab" id="dimension-tab-${i}" aria-controls="dimension-content" aria-selected="${i===activeDimension}" tabindex="${i===activeDimension?0:-1}" data-dimension="${i}">${n}<small>${m.code==='cu'?'截图资料':'待补资料'}</small></button>`).join('')}</div><div id="dimension-content" role="tabpanel" aria-labelledby="dimension-tab-${activeDimension}">${dimensionArticle(m,activeDimension)}</div></section>`+dimensionDetailBase()};
const dimensionBindBase=bindResearchDetail;
bindResearchDetail=function(){dimensionBindBase();$$('[data-dimension]').forEach(b=>{b.onclick=()=>{activeDimension=Number(b.dataset.dimension);$$('[data-dimension]').forEach(t=>{const yes=t===b;t.setAttribute('aria-selected',String(yes));t.tabIndex=yes?0:-1});$('#dimension-content').setAttribute('aria-labelledby',b.id);$('#dimension-content').innerHTML=dimensionArticle(selected(),activeDimension)};b.onkeydown=e=>{if(['ArrowRight','ArrowLeft','Home','End'].includes(e.key)){e.preventDefault();const n=e.key==='Home'?0:e.key==='End'?3:(Number(b.dataset.dimension)+(e.key==='ArrowRight'?1:3))%4;const next=$(`[data-dimension="${n}"]`);next.click();next.focus()}}})};
function productResearchHome(){
 const host=document.createElement('section');host.className='product-research-home';host.innerHTML=`<div class="section-header"><h2 class="section-title">品种研究<span class="section-sub">选择产品，展开四个研究维度</span></h2></div><div class="product-sector-grid">${Object.keys(researchGroups).map((g,i)=>`<article class="panel product-sector"><div class="panel-top"><div><div class="eyebrow">0${i+1} / ${DATA.markets.filter(m=>m.sector===g).length} PRODUCTS</div><h3>${esc(g)}</h3></div></div><div class="product-buttons">${DATA.markets.filter(m=>m.sector===g).map(m=>`<button data-product="${m.code}"><strong>${esc(m.name)}</strong><small>${m.main.contract.toUpperCase()}</small><span class="${color(m.main.changePct)}">${factorPct(m.main.changePct)}</span></button>`).join('')}</div></article>`).join('')}</div><p class="chart-note">盘面：${DATA.asOf} 收盘快照。铜研究资料：2026-11-02 至 11-03 用户截图。相对强度分位仍以原始全市场样本计算。</p>`;
 const anchor=$('#app .page-heading');if(anchor)anchor.insertAdjacentElement('afterend',host);else $('#app').prepend(host);
 $$('[data-product]').forEach(b=>b.onclick=()=>{activeDimension=0;selectResearch(b.dataset.product)});
}

const terminalRenderBase=render;
render=function(){applyResearchScope();terminalRenderBase();terminalSync();if(state.view==='research')productResearchHome()};
// END TERMINAL UI
