"""Derive separately dated continuous-price research and actual-contract evidence.

No forecasts, modelled fund flows, invented interpolation or future bars. Continuous
research prices have explicit fixed-base ratio factors and auditable roll dates.
"""
import collections, datetime as dt, json, math, pathlib, statistics
ROOT=pathlib.Path(__file__).resolve().parents[1]

def finite(x):
    return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)

def positive(x): return finite(x) and x>0
def sign(x): return None if not finite(x) else (1 if x>0 else -1 if x<0 else 0)
def avg(a): return statistics.mean(a) if a else None
def change(now,before): return (now/before-1)*100 if finite(now) and positive(before) else None

def percentile(value, sample):
    """Midrank empirical percentile; tied observations share one rank."""
    a=[v for v in sample if finite(v)]
    if not finite(value) or not a: return None
    return (sum(v<value for v in a)+.5*sum(v==value for v in a))/len(a)*100

def chain_sector(m):
    if m['code'] in ('lc','si','ps'): return '新能源材料'
    if m['code']=='lg': return '林产品'
    if m['sector'] in ('黑色金属','黑色建材'): return '黑色 / 建材'
    return m['sector']

def deviation_watch(a, last):
    """A descriptive screen, independent of seat availability or trend alignment."""
    distance=a.get('distanceAtr20')
    if not finite(distance) or abs(distance)<2:
        return None
    above=distance>0
    day=a.get('return1')
    retracing=finite(day) and (day<0 if above else day>0)
    boundary=a.get('priorHigh20' if above else 'priorLow20')
    reentry=bool(last and finite(boundary) and finite(last.get('high' if above else 'low')) and
                 (last['high']>boundary and last['close']<boundary if above else
                  last['low']<boundary and last['close']>boundary))
    observations=[]
    if retracing: observations.append('当日收盘低于昨收' if above else '当日收盘高于昨收')
    if reentry: observations.append('盘中越过前20日高点后收回区间' if above else '盘中越过前20日低点后收回区间')
    return {'side':'above' if above else 'below',
            'label':'上方偏离' if above else '下方偏离',
            'focus':'关注回调风险' if above else '关注反弹可能',
            'retracing':retracing,'rangeReentry':reentry,'observations':observations,
            'priceCue':('当日回落' if above else '当日反弹') if retracing else
                       '昨收比较缺失' if not finite(day) else '暂未出现反向收盘',
            'caveat':'偏离可能通过横盘或均线移动收敛；尚不能确认趋势反转。'}


def deviation_episode(history, dates):
    """Track observed excursions; retain five sessions after the last threshold hit.

    Each point uses only its own trailing MA20/ATR14. Missing sessions break the
    episode. Gap contraction measures price-minus-MA, not returns or probability.
    """
    episode=None
    for i,date in enumerate(dates):
        rows=[history.get(d) for d in dates[max(0,i-19):i+1]]
        if len(rows)<20 or any(not r or any(not finite(r.get(k)) for k in ('close','high','low')) for r in rows):
            episode=None
            continue
        ma=avg([r['close'] for r in rows]);last=rows[-1]
        tr=[max(rows[j]['high']-rows[j]['low'],abs(rows[j]['high']-rows[j-1]['close']),abs(rows[j]['low']-rows[j-1]['close'])) for j in range(6,20)]
        atr=avg(tr)
        if not positive(atr):
            episode=None
            continue
        gap=last['close']-ma;distance=gap/atr;side='above' if distance>0 else 'below'
        if abs(distance)>=2:
            if not episode or side!=episode['side']:
                episode={'side':side,'firstAt':date,'peakAt':date,'peakDistance':distance,'peakGap':abs(gap)}
            episode['lastHitAt']=date;episode['lastHitIndex']=i
            if abs(distance)>abs(episode['peakDistance']):
                episode.update(peakAt=date,peakDistance=distance,peakGap=abs(gap))
        if not episode:
            continue
        if i-episode['lastHitIndex']>5:
            episode=None
            continue
        crossed=gap==0 or side!=episode['side']
        previous=episode.get('latestDistance')
        phase=('越过均线' if crossed else '阈值内修复' if abs(distance)<2 else
               '偏离扩大' if previous is not None and abs(distance)>abs(previous) else
               '偏离收敛' if previous is not None and abs(distance)<abs(previous) else '偏离持续')
        previous_close=rows[-2]['close'];day=change(last['close'],previous_close)
        above=episode['side']=='above';retracing=day<0 if above else day>0
        episode.update(latestAt=date,latestDistance=distance,phase=phase,
                       sessionsAfterHit=i-episode['lastHitIndex'],
                       gapContractionPct=max(0,min(100,(1-(0 if crossed else abs(gap))/episode['peakGap'])*100)),
                       label=('上方' if above else '下方')+('偏离' if abs(distance)>=2 and not crossed else '偏离后修复'),
                       focus='均值跨越后跟踪' if crossed else '关注回调风险' if above else '关注反弹可能',retracing=retracing,rangeReentry=False,
                       priceCue=('当日回落' if above else '当日反弹') if retracing else '当日未向均值方向收盘',
                       observations=[('当日收盘低于昨收' if above else '当日收盘高于昨收')] if retracing else [],
                       caveat='价均差收敛可来自价格、均线移动；不是收益率或反转概率。')
    if episode:
        episode.pop('lastHitIndex',None)
    return episode


def derive(m, calendar):
    end=m['main']['date']; dates=[d for d in calendar if d<=end]
    history={h['date']:h for h in m['history'] if h.get('contract')==m['main']['contract'] and positive(h.get('close')) and h['date']<=end}
    def row(back): return history.get(dates[-1-back]) if len(dates)>back else None
    def window(n,back=0,fields=('close',)):
        days=dates[-n-back:len(dates)-back if back else None]
        if len(days)!=n: return None
        a=[history.get(d) for d in days]
        if any(h is None or any(not finite(h.get(f)) for f in fields) for h in a): return None
        return a
    last=row(0); prev=row(1)
    a={'sector':chain_sector(m),'asOf':end,'contract':m['main']['contract'],'historyCount':len(history),'referenceDayCount':len(dates),'missingRecent20':sum(d not in history for d in dates[-20:]),'basis':'fixed-contract / close-to-close / reference exchange trading calendar'}
    for n in (1,5,20):
        past=row(n)
        a['return'+str(n)]=change(last['close'],past['close']) if last and past else None
        a['oiReturn'+str(n)]=change(last.get('oi'),past.get('oi')) if last and past else None
        a['return'+str(n)+'Start']=dates[-1-n] if len(dates)>n else None
    w5,w20=window(5),window(20)
    a['ma5']=avg([h['close'] for h in w5]) if w5 else None
    a['ma20']=avg([h['close'] for h in w20]) if w20 else None
    old20=window(20,5)
    oldma=avg([h['close'] for h in old20]) if old20 else None
    a['ma20Slope5']=change(a['ma20'],oldma)
    a['deviation20']=change(last['close'],a['ma20']) if last else None
    a['trendDirection']=None
    if last and finite(a['ma5']) and finite(a['ma20']):
        a['trendDirection']=1 if last['close']>a['ma20'] and a['ma5']>a['ma20'] else -1 if last['close']<a['ma20'] and a['ma5']<a['ma20'] else 0
    a['trendLabel']={1:'趋势偏多',-1:'趋势偏空',0:'方向分化',None:'价格样本不足'}[a['trendDirection']]
    prev20=window(20,1,('close','high','low','volume'))
    a['volumeRatio20']=last['volume']/avg([h['volume'] for h in prev20]) if last and finite(last.get('volume')) and prev20 and positive(avg([h['volume'] for h in prev20])) else None
    a['priorHigh20']=max(h['high'] for h in prev20) if prev20 else None
    a['priorLow20']=min(h['low'] for h in prev20) if prev20 else None
    a['breakout']=('突破前20日高点' if last['close']>a['priorHigh20'] else '跌破前20日低点' if last['close']<a['priorLow20'] else None) if last and prev20 else None
    a['breakoutDirection']=1 if a['breakout']=='突破前20日高点' else -1 if a['breakout'] else 0
    w21=window(21)
    returns=[math.log(w21[i]['close']/w21[i-1]['close']) for i in range(1,21)] if w21 else None
    a['volatility20']=statistics.stdev(returns)*math.sqrt(252)*100 if returns else None
    a['atr14']=None
    w15=window(15,fields=('close','high','low'))
    if w15:
        tr=[max(w15[i]['high']-w15[i]['low'],abs(w15[i]['high']-w15[i-1]['close']),abs(w15[i]['low']-w15[i-1]['close'])) for i in range(1,15)]
        a['atr14']=avg(tr)
    a['natr14']=a['atr14']/last['close']*100 if last and finite(a['atr14']) else None
    a['distanceAtr20']=(last['close']-a['ma20'])/a['atr14'] if last and positive(a['atr14']) and finite(a['ma20']) else None
    a['deviationWatch']=deviation_watch(a,last)
    a['deviationEpisode']=deviation_episode(history,dates)
    volume=last.get('volume') if last else None;open_interest=last.get('oi') if last else None
    a['liquidity']={'low':finite(volume) and volume<1000 or finite(open_interest) and open_interest<1000,
                    'volume':volume,'oi':open_interest,'rule':'当日代表合约成交量或持仓量低于1000手，仅作流动性提示，非预测阈值'}
    a['fixedOiChange']=last['oi']-prev['oi'] if last and prev and finite(last.get('oi')) and finite(prev.get('oi')) else None
    p,oi=sign(a['return1']),sign(a['fixedOiChange'])
    quadrant={(1,1):'涨价增仓',(-1,1):'跌价增仓',(1,-1):'涨价减仓',(-1,-1):'跌价减仓'}
    a['quadrant']=quadrant.get((p,oi),'价仓持平' if p is not None and oi is not None else '价仓数据不足')
    a['participationDirection']=p if oi==1 and p in (-1,1) else None
    ranks=m.get('ranks',[])
    l=[r for r in ranks if finite(r.get('long'))];s=[r for r in ranks if finite(r.get('short'))]
    a['seatLong']=sum(r['long'] for r in l) if l else None
    a['seatShort']=sum(r['short'] for r in s) if s else None
    a['seatDifference']=a['seatLong']-a['seatShort'] if l and s else None
    a['seatDifferencePctOi']=a['seatDifference']/last['oi']*100 if last and positive(last.get('oi')) and a['seatDifference'] is not None else None
    ld=[r.get('longChange') for r in l];sd=[r.get('shortChange') for r in s]
    a['seatDeltaDifference']=sum(ld)-sum(sd) if l and s and all(finite(v) for v in ld+sd) else None
    a['seatLongTop5Share']=sum(r['long'] for r in l[:5])/a['seatLong']*100 if positive(a['seatLong']) else None
    a['seatShortTop5Share']=sum(r['short'] for r in s[:5])/a['seatShort']*100 if positive(a['seatShort']) else None
    a['seatDirection']=sign(a['seatDifference'])
    a['seatMarginalConflict']=a['seatDirection'] in (-1,1) and sign(a['seatDeltaDifference']) in (-1,1) and a['seatDirection']!=sign(a['seatDeltaDifference'])
    a['longContributors']=[{'name':r['longName'],'change':r.get('longChange')} for r in sorted(l,key=lambda r:abs(r.get('longChange') or 0),reverse=True)[:3]]
    a['shortContributors']=[{'name':r['shortName'],'change':r.get('shortChange')} for r in sorted(s,key=lambda r:abs(r.get('shortChange') or 0),reverse=True)[:3]]
    td=a['trendDirection'];pd=a['participationDirection'];sd=a['seatDirection']
    a['seatTrendConflict']=td in (-1,1) and sd in (-1,1) and td!=sd
    a['priceTrendConflict']=td in (-1,1) and p in (-1,1) and td!=p
    a['dimensionsAvailable']=int(td is not None)+int(p is not None and oi is not None)+int(sd is not None)
    a['alignedDimensions']=int(td in (-1,1))+int(td in (-1,1) and pd==td)+int(td in (-1,1) and sd==td and not a['seatMarginalConflict'])
    a['status']='多维同向' if td in (-1,1) and pd==td and sd==td and not a['seatMarginalConflict'] else '存在分歧' if a['seatTrendConflict'] or a['seatMarginalConflict'] or a['priceTrendConflict'] else '证据缺失' if a['dimensionsAvailable']<3 else '待进一步确认'
    a['flags']=[]
    if a['seatTrendConflict']: a['flags'].append('趋势与席位样本差反向')
    if a['seatMarginalConflict']: a['flags'].append('席位存量与增减项反向')
    if a['priceTrendConflict']: a['flags'].append('当日价格与均线趋势反向')
    if positive(a['volumeRatio20']) and a['volumeRatio20']>=1.5:a['flags'].append('成交量≥前20日均量1.5倍')
    if finite(a['volumeRatio20']) and a['volumeRatio20']<.7:a['flags'].append('成交量低于前20日均量0.7倍')
    if a['breakout']:a['flags'].append(a['breakout'])
    if finite(a['distanceAtr20']) and abs(a['distanceAtr20'])>=2:a['flags'].append('偏离MA20至少2个ATR')
    if not ranks:a['flags'].append('缺少当日席位排名')
    if a['missingRecent20']:a['flags'].append('近20交易日存在无有效价格日')
    a['evidence']=[];a['counterEvidence']=[];a['unknowns']=[]
    if td in (-1,1):a['evidence'].append(f"收盘价与MA5均{'高于' if td==1 else '低于'}MA20；20交易日收益{a['return20']:+.2f}%。" if finite(a['return20']) else a['trendLabel']+'；20交易日收益端点缺失。')
    elif td==0:a['counterEvidence'].append('收盘位置与短、中均线未形成一致方向。')
    else:a['unknowns'].append('近20交易日价格不完整，不生成均线趋势。')
    if a['fixedOiChange'] is not None:
        txt=f"同一代表合约当日{a['quadrant']}，持仓变化{a['fixedOiChange']:+,.0f}手。"
        (a['evidence'] if pd is not None and pd==td else a['counterEvidence']).append(txt)
    else:a['unknowns'].append('缺少相邻交易日同合约持仓，不能判定价仓象限。')
    if sd is not None:
        txt=f"当日买卖排名样本差{a['seatDifference']:+,.0f}手；相当于该合约持仓的{a['seatDifferencePctOi']:+.1f}%。" if finite(a['seatDifferencePctOi']) else f"买卖排名样本差{a['seatDifference']:+,.0f}手。"
        (a['evidence'] if sd==td and td in (-1,1) else a['counterEvidence']).append(txt)
        if a['seatMarginalConflict']:a['counterEvidence'].append(f"样本存量差与当日增减项之差反向：增减项差{a['seatDeltaDifference']:+,.0f}手。")
    else:a['unknowns'].append('缺少当日席位排名，不能形成三维证据。')
    if finite(a['volumeRatio20']) and (a['volumeRatio20']<.7 or a['volumeRatio20']>=1.5):
        (a['counterEvidence'] if a['volumeRatio20']<.7 or a['priceTrendConflict'] else a['evidence']).append(f"代表合约成交量为前20个交易日均量的{a['volumeRatio20']:.2f}倍。")
    a['unknowns'].append('固定合约的量仓变化可能受移仓换月影响，不能等同品种总持仓增减或真实资金流。')
    a['unknowns'].append('盘面标签未纳入库存、仓单和供需数据；已取得资料在独立交叉核对区展示。现货基差、连续订单与需求证据仍不完整；日行情不能识别开平仓方。')
    return a

PRICE_FIELDS=('return1','return5','return20','return1Start','return5Start','return20Start',
              'ma5','ma20','ma20Slope5','deviation20','trendDirection','trendLabel',
              'priorHigh20','priorLow20','breakout','breakoutDirection','volatility20',
              'atr14','natr14','distanceAtr20','deviationWatch','deviationEpisode','historyCount','missingRecent20')

def continuous_research(m,calendar,fixed):
    c=m['continuous'];points=c.get('history',[]);a=dict(fixed)
    ready=c.get('status')=='ready' and points and points[-1]['date']==m['main']['date']
    p=None
    if ready:
        symbol=m['code']+'.POST'
        bars=[{**r,'contract':symbol,'volume':None,'oi':None} for r in points if r['date']<=m['main']['date']]
        study_calendar=sorted(set(calendar)|{r['date'] for r in bars})
        p=derive({'code':m['code'],'sector':m['sector'],'main':bars[-1],'history':bars,'ranks':[]},study_calendar)
    for k in PRICE_FIELDS:a[k]=p.get(k) if p else None
    a['trendLabel']='连续均线偏多' if a['trendDirection']==1 else '连续均线偏空' if a['trendDirection']==-1 else '连续均线分化' if a['trendDirection']==0 else '连续研究样本不足'
    a['priceBasis']={'type':'ratio-post-adjusted-continuous','available':bool(ready),
                     'baseDate':c.get('baseDate'),'latest':c.get('latest'),'contract':points[-1]['contract'] if points else None,
                     'factor':points[-1]['factor'] if points else None,'provider':c.get('provider'),
                     'error':c.get('error'),'rollCount':len(c.get('rollovers',[]))}
    a['basis']='continuous research prices / actual representative-contract volume, OI and seats'
    td=a['trendDirection'];pd=a['participationDirection'];sd=a['seatDirection']
    a['seatTrendConflict']=td in (-1,1) and sd in (-1,1) and td!=sd
    a['priceTrendConflict']=td in (-1,1) and sign(fixed['return1']) in (-1,1) and td!=sign(fixed['return1'])
    a['dimensionsAvailable']=int(td is not None)+int(pd is not None or fixed['fixedOiChange'] is not None and fixed['return1'] is not None)+int(sd is not None)
    a['alignedDimensions']=int(td in (-1,1))+int(td in (-1,1) and pd==td)+int(td in (-1,1) and sd==td and not a['seatMarginalConflict'])
    a['status']='多维同向' if td in (-1,1) and pd==td and sd==td and not a['seatMarginalConflict'] else '存在分歧' if a['seatTrendConflict'] or a['seatMarginalConflict'] or a['priceTrendConflict'] else '证据缺失' if a['dimensionsAvailable']<3 else '待进一步确认'
    a['evidence']=[];a['counterEvidence']=[]
    if td in (-1,1):a['evidence'].append('比例后复权连续收盘与MA5均'+('高于' if td==1 else '低于')+'MA20；研究对应合约 '+c['history'][-1]['contract'].upper()+'。')
    else:a['counterEvidence'].append(a['trendLabel']+'；不以固定合约均线默替连续研究指标。')
    if fixed['fixedOiChange'] is not None:
        (a['evidence'] if pd==td and td in (-1,1) else a['counterEvidence']).append('真实代表合约 '+m['main']['contract'].upper()+' 当日'+fixed['quadrant']+f"，持仓变化{fixed['fixedOiChange']:+,.0f}手；此处价格变化按该合约昨收。")
    if sd is not None:
        (a['evidence'] if sd==td and td in (-1,1) else a['counterEvidence']).append(f"真实代表合约当日买卖排名样本差{a['seatDifference']:+,.0f}手。")
    if a['seatMarginalConflict']:a['counterEvidence'].append('席位存量差与当日增减项差反向。')
    if finite(a['volumeRatio20']) and a['volumeRatio20']>=1.5:a['evidence' if not a['priceTrendConflict'] else 'counterEvidence'].append(f"真实代表合约量比{a['volumeRatio20']:.2f}倍，未对成交量复权。")
    a['unknowns']=fixed['unknowns']+['连续序列为固定基准比例后复权研究价，不是当前可成交价格或策略实际收益；量仓、席位、月差和库存价格核对仍使用真实合约。']
    a['flags']=[]
    if a['seatTrendConflict']:a['flags'].append('连续趋势与席位样本差反向')
    if a['seatMarginalConflict']:a['flags'].append('席位存量与增减项反向')
    if a['priceTrendConflict']:a['flags'].append('真实合约当日价格与连续均线趋势反向')
    if finite(a['volumeRatio20']) and a['volumeRatio20']>=1.5:a['flags'].append('真实合约成交量≥前20日均量1.5倍')
    if finite(a['volumeRatio20']) and a['volumeRatio20']<.7:a['flags'].append('真实合约成交量低于前20日均量0.7倍')
    if a['breakout']:a['flags'].append('后复权连续'+a['breakout'])
    if finite(a['distanceAtr20']) and abs(a['distanceAtr20'])>=2:a['flags'].append('后复权连续偏离MA20至少2个ATR')
    if not m.get('ranks'):a['flags'].append('缺少当日席位排名')
    if not ready:a['flags'].append('后复权连续序列未覆盖当前行情日')
    return a

def describe_market_state(a, fixed):
    """Describe price facts separately from seat checks and unavailable data."""
    td = a.get('trendDirection')
    daily = fixed.get('return1')
    p = sign(daily) if finite(daily) else None
    trend = {1: '均线偏多', -1: '均线偏空', 0: '均线分化'}.get(td, '趋势样本不足')
    if td not in (-1, 0, 1):
        phase = '趋势样本不足'
    elif p is None:
        phase = '当日涨跌缺失'
    elif p == 0:
        phase = '当日持平'
    elif td == -1:
        phase = '偏空中的反弹' if p > 0 else '偏空同向下行'
    elif td == 1:
        phase = '偏多同向上涨' if p > 0 else '偏多中的回落'
    else:
        phase = '均线分化·当日上涨' if p > 0 else '均线分化·当日下跌'
    oi = fixed.get('fixedOiChange')
    position = '持仓变化缺失' if not finite(oi) else '当日增仓' if oi > 0 else '当日减仓' if oi < 0 else '持仓持平'
    checks = []
    if a.get('seatTrendConflict'): checks.append('席位样本差与均线反向')
    if a.get('seatMarginalConflict'): checks.append('席位存量差与增减项差反向')
    if (a.get('liquidity') or {}).get('low'): checks.append('低流动性')
    missing = []
    if td is None: missing.append('连续均线样本不足')
    if p is None: missing.append('真实合约昨收涨跌缺失')
    if not finite(oi): missing.append('真实合约持仓变化缺失')
    if not finite(a.get('seatDifference')): missing.append('席位样本缺失')
    elif not finite(a.get('seatDeltaDifference')): missing.append('席位增减项缺失')
    return {'version': 'market-state-v1', 'trend': trend, 'phase': phase,
            'dailyReturn': daily, 'position': position, 'checks': checks,
            'missing': missing, 'strictAlignment': a.get('status') == '多维同向'}


def analyze(data):
    calendar=sorted({h['date'] for m in data['markets'] if m['exchange'] in ('SHFE','INE') for h in m['history'] if h['date']<=data['asOf']})
    for m in data['markets']:
        fixed=derive(m,calendar)
        if 'continuous' in m:
            m['fixedAnalysis']=fixed
            m['analysis']=continuous_research(m,calendar,fixed)
        else:m['analysis']=fixed
        m['analysis']['marketState']=describe_market_state(m['analysis'],fixed)
    eligible=[m['analysis']['return20'] for m in data['markets'] if finite(m['analysis']['return20'])]
    vol=[m['analysis']['volatility20'] for m in data['markets'] if finite(m['analysis']['volatility20'])]
    for m in data['markets']:
        a=m['analysis'];a['strengthPercentile20']=percentile(a['return20'],eligible);a['strengthPeerCount']=len(eligible)
        a['volatilityPercentile20']=percentile(a['volatility20'],vol)
    sectors=[]
    for sector in sorted({m['analysis']['sector'] for m in data['markets']}):
        ms=[m for m in data['markets'] if m['analysis']['sector']==sector];v=[m['analysis']['return20'] for m in ms if finite(m['analysis']['return20'])]
        sectors.append({'sector':sector,'count':len(ms),'return20Count':len(v),'positive20':sum(x>0 for x in v),'medianReturn20':statistics.median(v) if v else None,'bull':sum(m['analysis']['trendDirection']==1 for m in ms),'bear':sum(m['analysis']['trendDirection']==-1 for m in ms)})
    data['research']={'version':'evidence-v1','asOf':data['asOf'],'calendar':calendar,'sectors':sectors,'strengthPeerCount':len(eligible),'volatilityPeerCount':len(vol),'aligned':sum(m['analysis']['status']=='多维同向' for m in data['markets']),'conflicts':sum(m['analysis']['status']=='存在分歧' for m in data['markets']),'rules':{'volumeExpansion':1.5,'volumeContraction':.7,'distanceAtr':2,'annualization':252,'breakoutLookback':20,'atrMethod':'14-day simple mean of true range','basis':'Price research uses fixed-base ratio-post-adjusted continuous OHLC where available; missing continuous research is not replaced by fixed-contract returns. Volume/OI, seats and the price/OI map retain actual contracts. Research previous-close returns differ from overview previous-settlement returns. Seats are current-date independent lists.'}}
    return data

if __name__=='__main__':
    path=ROOT/'dist/data.json';data=analyze(json.loads(path.read_text(encoding='utf-8')))
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8');tmp.replace(path)
    print(json.dumps({'markets':len(data['markets']),'aligned':data['research']['aligned'],'conflicts':data['research']['conflicts'],'return20Peers':data['research']['strengthPeerCount'],'volatilityPeers':data['research']['volatilityPeerCount']}))
