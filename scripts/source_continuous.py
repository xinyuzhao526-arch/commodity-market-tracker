"""Build public-source continuous research prices; actual contract data is untouched."""
import argparse, concurrent.futures, datetime as dt, json, os, re
from pathlib import Path
from continuous_prices import construct
from source_live_fundamentals import http_raw
import update_domestic as shfe
import source_czce as czce
import source_gfex as gfex
import source_dce as sina

ROOT=Path(__file__).resolve().parents[1]

def official(root,exchange,day):
    date=dt.date.fromisoformat(day);ymd=day.replace('-','')
    if exchange=='SHFE':url=f'https://www.shfe.com.cn/data/tradedata/future/dailydata/kx{ymd}.dat'
    elif exchange=='CZCE':url=czce.report_url(date)
    else:url=gfex.QUOTES
    path=root/'data/raw/continuous'/f'{exchange}-{day}.raw';path.parent.mkdir(parents=True,exist_ok=True)
    existing=root/'data/raw'/f'kx{ymd}.dat' if exchange=='SHFE' else root/'data/raw/czce'/f'{ymd}-daily.txt'
    raw=path.read_bytes() if path.exists() else existing.read_bytes() if existing.exists() else http_raw(url,'POST' if exchange=='GFEX' else 'GET',data={'trade_date':ymd,'trade_type':'0'} if exchange=='GFEX' else None)
    if exchange=='SHFE':
        doc=json.loads(raw)
        if doc.get('report_date')!=ymd:raise ValueError('SHFE report date mismatch')
        rows=shfe.parse_rows({'rows':doc['o_curinstrument'],'date':day})
    elif exchange=='CZCE':
        text,_=czce.decode(raw)
        if not any(d in text for d in [day,ymd,day.replace('-','/')]):raise ValueError('CZCE report date mismatch')
        rows=czce.parse_quotes({'date':day,'text':text})
    else:
        doc=json.loads(raw)
        if str(doc.get('code'))!='0' or not isinstance(doc.get('data'),list):raise ValueError('GFEX invalid report')
        echo=doc.get('param',{}).get('trade_date')
        if echo not in (ymd,[ymd]):raise ValueError('GFEX report date not verified')
        rows=gfex.parse_quotes(doc,day)
    if not rows:raise ValueError('empty official report')
    path.write_bytes(raw)
    for r in rows:r['contract']=r['contract'].lower();r['sourceUrl']=url
    return rows

def sina_bars(root,symbol,as_of):
    path=root/'data/raw/continuous'/f'sina-{symbol}-{as_of}.json';path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():return json.loads(path.read_text(encoding='utf-8'))
    raw=http_raw(sina.DAILY+symbol).decode('utf-8');match=re.search(r'=\s*\((\[.*\]|null)\)\s*;',raw,re.S)
    if not match:raise ValueError('Sina fixed-contract response invalid')
    rows=json.loads(match[1]) or [];path.write_text(json.dumps(rows),encoding='utf-8');return rows

def acquire_dce(root,market,days):
    code=market['code']
    if market['exchange']=='DCE':
        product=next(p for p in sina.PRODUCTS if p[0]==code)
        listing=json.loads(http_raw(sina.LIST.format(product[3])))
        symbols={q['symbol'] for q in listing if re.fullmatch(code.upper()+r'\d{4}',q['symbol'])}
    else:
        symbols={r['contract'].upper() for r in market['contracts']}
    # Include expired months within the observed window; current lists omit them.
    first=dt.date.fromisoformat(days[0]);last=dt.date.fromisoformat(days[-1])
    for serial in range(first.year*12+first.month-1,last.year*12+last.month):
        year,month=divmod(serial,12);symbols.add(f'{code.upper()}{year%100:02d}{month+1:02d}')
    frames={};errors=[]
    for symbol in sorted(symbols):
        try:
            for row in sina_bars(root,symbol,days[-1]):
                if row['d'] not in days:continue
                r={'date':row['d'],'contract':symbol.lower(),'code':code,'sourceUrl':sina.DAILY+symbol,
                   **{k:sina.number(row.get(v)) for k,v in {'open':'o','high':'h','low':'l','close':'c','volume':'v','oi':'p'}.items()}}
                frames.setdefault(r['date'],{})[r['contract']]=r
        except Exception as e:errors.append(f'{symbol}: {type(e).__name__}')
    target=frames.get(days[-1],{}).get(market['main']['contract'].lower())
    if not target or any(target.get(k)!=market['main'].get(k) for k in ('open','high','low','close','volume','oi')):
        errors.append('target contract does not match validated snapshot OHLC/volume/OI')
    return frames,errors

def refresh(root,previous_path=None,workers=5):
    output=root/'dist/data.json';data=json.loads(output.read_text(encoding='utf-8'))
    previous=json.loads(previous_path.read_text(encoding='utf-8')) if previous_path else data
    old={m['code']:m.get('continuous') for m in previous['markets']}
    day=data['asOf'];calendar=sorted(d for d in data['research']['calendar'] if d<=day) if data.get('research') else sorted({r['date'] for m in data['markets'] if m['exchange'] in ('SHFE','INE') for r in m['history'] if r['date']<=day})
    frames={};errors=[]
    jobs=[]
    for exchange in ('SHFE','CZCE'):
        markets=[m for m in data['markets'] if ('SHFE' if m['exchange']=='INE' else m['exchange'])==exchange]
        starts=[(old.get(m['code']) or {}).get('latest') or calendar[0] for m in markets]
        jobs.extend((exchange,d) for d in calendar if not starts or d>=min(starts))
    def one(item):
        ex,d=item
        try:return ex,d,official(root,ex,d),None
        except Exception as e:return ex,d,[],f'{type(e).__name__}: {str(e)[:120]}'
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for ex,d,rows,error in pool.map(one,jobs):
            if error:errors.append({'source':ex,'date':d,'error':error})
            for r in rows:frames.setdefault(r['code'],{}).setdefault(d,{})[r['contract']]=r
    dce=[m for m in data['markets'] if m['exchange'] in ('DCE','GFEX')]
    def dce_one(m):
        start=(old.get(m['code']) or {}).get('latest') or calendar[0];days=[d for d in calendar if d>=start]
        try:return m['code'],*acquire_dce(root,m,days)
        except Exception as e:return m['code'],{},[f'{type(e).__name__}: {str(e)[:120]}']
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for code,ff,ee in pool.map(dce_one,dce):
            frames[code]=ff if not ee else {}
            errors.extend({'source':'Sina '+code,'error':e} for e in ee)
    for m in data['markets']:
        prior=old.get(m['code'])
        result=construct(frames.get(m['code'],{}),calendar,day,prior)
        result['provider']='新浪逐合约公开日线（目标日已与已验证快照匹配）/ 本站自建' if m['exchange'] in ('DCE','GFEX') else '交易所逐合约官方日报 / 本站自建'
        m['continuous']=result
    data['continuousStatus']={'asOf':day,'errors':errors[:30],'ready':sum(m['continuous']['status']=='ready' for m in data['markets']),'total':len(data['markets'])}
    tmp=output.with_suffix('.continuous-incoming');tmp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8');os.replace(tmp,output)
    print(json.dumps(data['continuousStatus'],ensure_ascii=True),flush=True)
    return data

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--previous',type=Path);p.add_argument('--workers',type=int,default=5);a=p.parse_args();refresh(ROOT,a.previous,a.workers)
