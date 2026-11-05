"""Auditable, fixed-base ratio-post-adjusted futures prices (never quantities)."""
import copy, math, re

SCHEMA='ratio-post-continuous-v1'
RULE='T日根据T-1持仓选择；远月持仓超过当前合约1.1倍时切换；不回切；以切换前日同日收盘比率后复权'

def positive(x):
    return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) and x>0

def delivery(contract,date):
    s=re.search(r'(\d{3,4})$',contract)
    if not s:return None
    text=s[1];month=int(text[-2:])
    if not 1<=month<=12:return None
    year=2000+int(text[:2]) if len(text)==4 else int(date[:3])*10+int(text[0])
    if len(text)==3 and year<int(date[:4])-1:year+=10
    return year*12+month

def valid(r):
    return r and all(positive(r.get(k)) for k in ('open','high','low','close')) and r['low']<=min(r['open'],r['close'])<=max(r['open'],r['close'])<=r['high']

def construct(frames,calendar,as_of,previous=None):
    """Each frame maps normalized contracts to actual daily OHLC/OI/volume.

    Prior points are immutable. A missing frame or roll bridge stops extension;
    it never leads to a reset of the base or a guessed adjustment factor.
    """
    if previous and previous.get('schema')!=SCHEMA:raise ValueError('continuous schema changed')
    packet=copy.deepcopy(previous) if previous else {'schema':SCHEMA,'method':'fixed-base-ratio-post','rule':RULE,'history':[],'rollovers':[]}
    points=packet['history'];rolls=packet['rollovers']
    if points and points[-1]['date']>as_of:raise ValueError('refusing continuous rollback')
    days=sorted(d for d in set(calendar) if d<=as_of)
    current=points[-1]['contract'] if points else None;factor=points[-1]['factor'] if points else 1.0
    error=None
    for i,day in enumerate(days):
        if points and day<=points[-1]['date']:continue
        rows=frames.get(day,{})
        if current is None:
            candidates=[r for r in rows.values() if valid(r) and positive(r.get('volume')) and positive(r.get('oi')) and delivery(r['contract'],day)]
            if not candidates:continue  # No base is claimed before the first observed valid day.
            chosen=max(candidates,key=lambda r:(r['oi'],-delivery(r['contract'],day)))
            current=chosen['contract'];packet.update(baseDate=day,baseContract=current,basePrice=chosen['close'])
            selection_date=day
        else:
            if i==0 or points[-1]['date']!=days[i-1]:
                error='缺少相邻交易日，连续序列停止延伸';break
            selection_date=days[i-1];prior=frames.get(selection_date,{})
            old=prior.get(current)
            if not valid(old) or not positive(old.get('oi')) or not positive(old.get('volume')):
                error='缺少当前合约前日收盘或持仓，不能核实换月';break
            candidates=[r for r in prior.values() if positive(r.get('volume')) and positive(r.get('oi')) and delivery(r['contract'],selection_date) and delivery(r['contract'],selection_date)>delivery(current,selection_date) and r['oi']>old['oi']*1.1]
            if candidates:
                challenger=max(candidates,key=lambda r:(r['oi'],-delivery(r['contract'],selection_date)))
                if not valid(challenger):
                    error='待换月合约前日OHLC缺失，无法核实复权桥接';break
                next_contract=challenger['contract'];next_factor=factor*old['close']/challenger['close']
                if not positive(next_factor):raise ValueError('invalid post adjustment factor')
                if not valid(rows.get(next_contract)) or not positive(rows[next_contract].get('volume')):
                    error='新合约切换日OHLC缺失，不生成虚构连续价';break
                rolls.append({'date':day,'comparisonDate':selection_date,'from':current,'to':next_contract,
                              'oldClose':old['close'],'newClose':challenger['close'],'oldOi':old['oi'],'newOi':challenger['oi'],
                              'factorBefore':factor,'factorAfter':next_factor,'sourceUrls':[old.get('sourceUrl'),challenger.get('sourceUrl')]})
                current=next_contract;factor=next_factor
            chosen=rows.get(current)
        if not valid(chosen) or not positive(chosen.get('volume')):
            error='研究对应合约当日无有效成交OHLC，保留原序列';break
        points.append({'date':day,'contract':current,'selectionDate':selection_date,'factor':factor,
                       **{k:chosen[k]*factor for k in ('open','high','low','close')},
                       'rawClose':chosen['close'],'sourceUrl':chosen.get('sourceUrl')})
    packet.update(asOf=as_of,latest=points[-1]['date'] if points else None,
                  status='ready' if points and points[-1]['date']==as_of else 'stale' if points else 'unavailable',error=error)
    return packet
