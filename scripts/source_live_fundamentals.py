"""Download dated physical warehouse data; preserve last good series on failures.

Official SHFE/INE HTML, CZCE XLSX and GFEX JSON come first. DCE challenges are
not solved: Eastmoney's dated warehouse-receipt series is an explicit fallback.
Every output point keeps its source. Quantities are never converted to tonnes.
"""
import argparse
import concurrent.futures
import datetime as dt
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
import subprocess
import shutil
import urllib.parse
import requests
from bs4 import BeautifulSoup
import openpyxl

ROOT = Path(__file__).resolve().parents[1]
SHANGHAI = dt.timezone(dt.timedelta(hours=8))
EM = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
CODES = set('a b m y p oi rm rs pk cu al zn pb ni sn ao ad bc au ag pt pd si lc ps rb hc ss wr i j jm sf sm'.split())
SHFE_NAMES = {'铜':'cu','铜(BC)':'bc','铝':'al','锌':'zn','铅':'pb','镍':'ni','锡':'sn','氧化铝':'ao','铸造铝合金':'ad','黄金':'au','白银':'ag','螺纹钢':'rb','线材':'wr','热轧卷板':'hc','不锈钢':'ss'}
MARKET_CODES = {'DCE':'069001007','CZCE':'069001008','SHFE':'069001005','INE':'069001016','GFEX':'069001021'}


def number(v, signed=False):
    if v is None or isinstance(v, bool):
        raise ValueError('missing numeric value')
    try:
        n = float(str(v).replace(',', '').strip())
    except (ValueError, TypeError):
        raise ValueError('invalid numeric value')
    if not math.isfinite(n) or (not signed and n < 0):
        raise ValueError('nonfinite/negative quantity')
    return n


def valid_day(s):
    day = dt.date.fromisoformat(str(s)[:10])
    if day.isoformat() != str(s)[:10]:
        raise ValueError('invalid report date')
    return day.isoformat()


def grid(table):
    """Expand HTML row/column spans, retaining headers as real columns."""
    spans, result = {}, []
    for tr in table.find_all('tr'):
        row, col = [], 0
        cells = iter(tr.find_all(['th','td'], recursive=False))
        while True:
            if col in spans:
                text, left = spans[col]
                row.append(text)
                if left == 1: del spans[col]
                else: spans[col] = (text,left-1)
                col += 1
                continue
            cell = next(cells, None)
            if cell is None: break
            text = cell.get_text(' ', strip=True)
            width, height = int(cell.get('colspan',1)), int(cell.get('rowspan',1))
            for offset in range(width):
                row.append(text)
                if height > 1: spans[col+offset] = (text,height-1)
            col += width
        result.append((tr,row))
    return result


def dated_html(raw, day):
    soup = BeautifulSoup(raw.decode('utf-8'), 'html.parser')
    dates = re.findall(r'20\d{2}-\d{2}-\d{2}',soup.get_text(' ',strip=True)[:600])
    if not dates or set(dates) != {day}:
        raise ValueError('official HTML report date mismatch')
    return soup


def make_series(code, metric, unit, scope, day, value, change, url, provider, previous=None):
    value, change = number(value), number(change, signed=True)
    if previous is not None and abs(value-number(previous)-change)>0.001:
        raise ValueError('current/previous/change arithmetic mismatch')
    if value-change < -0.001:
        raise ValueError('negative implied previous quantity')
    return {'id':f'{provider}:{code}:{metric}:{scope}', 'code':code,'metric':metric,
            'unit':unit,'scope':scope,'provider':provider,'sourceUrl':url,
            'frequency':'weekly' if metric=='stock' else 'daily',
            'history':[{'date':valid_day(day),'value':value,'change':change,
                        'previous':previous,'sourceUrl':url}]}


def parse_shfe(raw, day, url, weekly=False):
    soup, out = dated_html(raw,day), []
    for table in soup.find_all('table'):
        title_row = table.find('tr',class_='special_row_type')
        if title_row is None: continue
        title = title_row.get_text(' ',strip=True)
        m = re.fullmatch(r'(.+?)\s*单位[：:]\s*(吨|千克)',title)
        if not m: continue
        name, unit = m.groups()
        scope = '厂库' if '(厂库)' in name else '仓库'
        name = name.replace('(厂库)','').replace('(仓库)','')
        code = SHFE_NAMES.get(name)
        if not code: continue
        rows = grid(table)
        headers = [r for tr,r in rows if tr.find('th')]
        data = [r for tr,r in rows if tr is not title_row and not tr.find('th')]
        if not headers or not data: raise ValueError('empty official product table')
        # Prefer one grand total; never sum leaf rows together with subtotals.
        totals = [r for r in data if '总计' in r[:2]]
        if not totals: totals = [r for r in data if any(x.endswith('商品总计') for x in r[:2])]
        if not totals: totals = [r for r in data if '合计' in r[:2]]
        if not totals and code=='au': totals = data
        if len(totals)!=1:
            # No unambiguous total: preserve this missing section rather than guess.
            continue
        row = totals[0]
        if weekly:
            header = headers[0]
            if '本周库存' not in header: continue  # '本周期货' is a receipt, not total stock.
            i = header.index('本周库存')
            if len(headers)>1 and headers[1][i]!='小计' and code!='au': continue
            prior, current, delta = i-(2 if code!='au' else 1), i, i+(2 if code!='au' else 1)
            out.append(make_series(code,'stock',unit,scope,day,row[current],row[delta],url,'SHFE官方',number(row[prior])))
        else:
            header = headers[0]
            col = '期货' if '期货' in header else '本日数量'
            i = header.index(col)
            out.append(make_series(code,'receipt',unit,scope,day,row[i],row[header.index('增减')],url,'SHFE官方'))
    if len(out)<8: raise ValueError('SHFE coverage unexpectedly small')
    return out


def parse_czce(raw, day, url):
    wb = openpyxl.load_workbook(BytesIO(raw),read_only=True,data_only=True)
    rows = list(wb.active.values)
    if day not in str(rows[0][0]): raise ValueError('CZCE date mismatch')
    out, section = [], None
    for row in rows:
        first = str(row[0] or '').strip()
        if first.startswith('品种'):
            match = re.search(r'([A-Z]{2})\s+单位[：:]\s*(\S+)',first)
            if not match: raise ValueError('unknown CZCE product/unit')
            section = {'code':match[1].lower(),'unit':match[2], 'header':None,
                       'forecast':'每张预报' in first,'date':day in first}
        elif section and any(str(v or '').strip()=='仓单数量' for v in row):
            section['header'] = [str(v or '').strip() for v in row]
        elif section and first=='总计' and not section['forecast'] and section['code'] in CODES:
            if not section['date'] or not section['header']: raise ValueError('CZCE incomplete section')
            h = section['header']
            i = h.index('仓单数量')
            delta = next((h.index(k) for k in ['当日增减','增减'] if k in h),None)
            if delta is None: raise ValueError('CZCE no change column')
            unit = section['unit']
            if unit!='张': raise ValueError('CZCE unknown receipt unit')
            out.append(make_series(section['code'],'receipt',unit,'交易所合计',day,row[i],row[delta],url,'CZCE官方'))
    if len({r['code'] for r in out})<5: raise ValueError('CZCE receipt coverage unexpectedly small')
    return out


def parse_gfex(raw, day, url):
    doc = json.loads(raw)
    if str(doc.get('code'))!='0' or doc.get('param',{}).get('gen_date')!=[day.replace('-','')]:
        raise ValueError('GFEX response/request date mismatch')
    groups = {}
    for r in doc.get('data',[]):
        code = r.get('varietyOrder','').lower()
        if code not in CODES or not str(r.get('whAbbr') or '').strip(): continue
        key = (code,r['whAbbr'],r.get('trademarkName',''))
        if key in groups: raise ValueError('duplicate GFEX warehouse row')
        value, prior, change = number(r['wbillQty']),number(r['lastWbillQty']),number(r['diff'],True)
        if abs(value-prior-change)>0.001: raise ValueError('GFEX row arithmetic mismatch')
        groups[key] = (value,prior,change)
    out = []
    for code in sorted({k[0] for k in groups}):
        values = [v for k,v in groups.items() if k[0]==code]
        # Official response has no unit field. Keep raw count explicitly unconverted.
        out.append(make_series(code,'receipt','接口计数','仓库明细合计',day,sum(v[0] for v in values),sum(v[2] for v in values),url,'GFEX官方',sum(v[1] for v in values)))
        out[-1]['dateValidation']='接口gen_date回显，逐仓数量和增减校验'
        out[-1]['unitNote']='接口未给出单位；保留仓单原始计数，不折算吨。'
    if len(out)<3: raise ValueError('GFEX receipt coverage unexpectedly small')
    return out


def em_rows(doc, code, exchange, as_of):
    result = doc.get('result')
    if doc.get('success') is not True or not result or not result.get('data'):
        raise ValueError('empty/failed fallback response')
    rows, seen, unit = [], set(), None
    for r in result['data']:
        if str(r.get('SECURITY_CODE','')).lower()!=code or r.get('TRADE_MARKET_CODE')!=MARKET_CODES[exchange]:
            raise ValueError('fallback product/exchange mismatch')
        day = valid_day(r['TRADE_DATE'])
        if day>as_of: raise ValueError('future fallback record')
        if day in seen: raise ValueError('duplicate fallback date')
        seen.add(day)
        u = str(r.get('UNIT') or '').strip()
        if u not in {'吨','千克','手','张'} or unit and unit!=u: raise ValueError('unknown/mixed fallback unit')
        unit = u
        value, change = number(r['ON_WARRANT_NUM']),number(r['ADDCHANGE'],True)
        if value-change<0: raise ValueError('fallback negative implied prior')
        rows.append({'date':day,'value':value,'change':change,'previous':None,'sourceUrl':'https://data.eastmoney.com/ifdata/kcsj.html'})
    rows.sort(key=lambda r:r['date'])
    return {'id':f'东方财富备用:{code}:receipt:转载口径','code':code,'metric':'receipt','unit':unit,'scope':'转载口径',
            'provider':'东方财富备用','sourceUrl':'https://data.eastmoney.com/ifdata/kcsj.html','frequency':'daily','history':rows,
            'note':'原字段ON_WARRANT_NUM（仓单数量），不作为社会库存；与官方系列不拼接。'}


def request_raw(root, key, url, method='GET', params=None, data=None, body=None, refresh=False):
    cache = root/'data/raw/fundamentals';cache.mkdir(parents=True,exist_ok=True)
    path = cache/(key+'.bin')
    if path.exists() and not refresh: return path.read_bytes(),path
    raw = http_raw(url,method,params,data,body)
    if len(raw)>12_000_000: raise ValueError('unexpected response size')
    return raw,path


def http_raw(url, method='GET', params=None, data=None, body=None):
    try:
        response=requests.request(method,url,params=params,data=data,json=body,timeout=18,headers={'User-Agent':'Mozilla/5.0'})
        response.raise_for_status()
        return response.content
    except requests.exceptions.SSLError:
        # Windows' standard HTTPS client can reach several government hosts which
        # fail Python's TLS handshake. Certificate verification remains enabled.
        curl=shutil.which('curl.exe') or shutil.which('curl')
        if not curl:raise
        if params:url+='?'+urllib.parse.urlencode(params)
        args=[curl,'--silent','--show-error','--fail','--location','--max-time','25',url]
        if body is not None:args+=['-H','Content-Type: application/json','--data-binary',json.dumps(body)]
        elif data is not None:args+=['--data',urllib.parse.urlencode(data)]
        result=subprocess.run(args,capture_output=True,check=True,timeout=30)
        return result.stdout


def fetch_official(root, source, day, refresh=False):
    ymd=day.replace('-',''); weekly=source=='shfe-weekly'
    if source.startswith('shfe'):
        url=f'https://www.shfe.com.cn/data/tradedata/future/stockdata/{"weeklystock" if weekly else "dailystock"}_{ymd}/ZH/all.html'
        raw,path=request_raw(root,source+'-'+day,url,refresh=refresh)
        parsed=parse_shfe(raw,day,url,weekly)
    elif source=='czce':
        url=f'https://www.czce.com.cn/cn/DFSStaticFiles/Future/{ymd[:4]}/{ymd}/FutureDataWhsheet.xlsx'
        raw,path=request_raw(root,source+'-'+day,url,refresh=refresh)
        parsed=parse_czce(raw,day,url)
    elif source=='gfex':
        url='http://www.gfex.com.cn/u/interfacesWebTdWbillWeeklyQuotes/loadList'
        raw,path=request_raw(root,source+'-'+day,url,'POST',data={'gen_date':ymd},refresh=refresh)
        parsed=parse_gfex(raw,day,url)
    else: raise ValueError('unknown official source')
    path.write_bytes(raw)
    return parsed


def fetch_em(root, code, exchange, as_of, start):
    symbol=code if exchange=='GFEX' else code.upper()
    params={'reportName':'RPT_FUTU_STOCKDATA','columns':'ALL','filter':f'(SECURITY_CODE="{symbol}")(TRADE_DATE>=\'{start}\')(TRADE_DATE<=\'{as_of}\')',
            'pageSize':100,'pageNumber':1,'sortColumns':'TRADE_DATE','sortTypes':'-1','source':'WEB','client':'WEB'}
    raw,path=request_raw(root,f'em-{code}-{start}-{as_of}',EM,params=params,refresh=True)
    doc=json.loads(raw)
    series=em_rows(doc,code,exchange,as_of)
    if doc['result']['pages']!=1: raise ValueError('fallback query incomplete pagination')
    path.write_bytes(raw)
    return [series]


def merge_series(existing,incoming,as_of):
    """Keep old points on failed fetches; never mix providers, units or scopes."""
    merged={s['id']:json.loads(json.dumps(s)) for s in existing}
    for s in incoming:
        prior=merged.get(s['id'])
        if prior and any(prior[k]!=s[k] for k in ['unit','metric','scope','code','provider']):
            raise ValueError('series identity/unit changed')
        points={p['date']:p for p in prior['history']} if prior else {}
        for p in s['history']:
            if valid_day(p['date'])>as_of: raise ValueError('future point')
            number(p['value']);number(p['change'],True)
            points[p['date']]=p
        merged[s['id']]={**s,'history':[points[d] for d in sorted(points) if d<=as_of][-180:]}
    return list(merged.values())


def refresh(root, as_of, history_days=18):
    output=root/'dist/fundamentals.json'
    old=json.loads(output.read_text(encoding='utf-8')) if output.exists() else {'inventories':[],'supplies':[]}
    if old.get('asOf','')>as_of: raise ValueError('refusing fundamentals rollback')
    end=dt.date.fromisoformat(as_of);start=(end-dt.timedelta(days=history_days)).isoformat()
    days=[(end-dt.timedelta(days=i)).isoformat() for i in range(history_days+1) if (end-dt.timedelta(days=i)).weekday()<5]
    jobs=[(source,day) for source in ['shfe-daily','czce','gfex'] for day in days]
    jobs += [('shfe-weekly',day) for day in days if dt.date.fromisoformat(day).weekday()==4]
    def job(item):
        source,day=item
        try:return source,day,fetch_official(root,source,day,refresh=day==as_of),None
        except Exception as e:return source,day,[],f'{type(e).__name__}: {str(e)[:180]}'
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:results=list(pool.map(job,jobs))
    incoming=[s for _,_,ss,_ in results for s in ss]
    statuses=[]
    for source in ['shfe-daily','shfe-weekly','czce','gfex']:
        rs=[r for r in results if r[0]==source];good=[r[1] for r in rs if r[2]];errors=[{'date':r[1],'error':r[3]} for r in rs if r[3]]
        statuses.append({'source':source,'status':'ok' if good and not errors else 'partial' if good else 'failed','latest':max(good) if good else None,'errors':errors[:6]})
    # DCE public endpoint may return an access challenge; record it, never execute it.
    try:
        r=requests.post('http://www.dce.com.cn/dcereport/publicweb/dailystat/wbillWeeklyQuotes',json={'tradeDate':as_of.replace('-',''),'varietyId':'all'},timeout=15)
        statuses.append({'source':'dce-official','status':'unavailable','error':f'HTTP {r.status_code}; 官方字段尚未完成日期/单位验证，使用独立备用系列。'})
    except requests.RequestException as e:statuses.append({'source':'dce-official','status':'failed','error':type(e).__name__})
    markets=json.loads((root/'dist/data.json').read_text(encoding='utf-8'))['markets']
    covered={s['code'] for s in incoming if s['metric']=='receipt' and s['history'][-1]['date']==as_of}
    fallback=[m for m in markets if m['code'] in CODES and m['code'] not in covered]
    def backup(m):
        try:return m['code'],fetch_em(root,m['code'],m['exchange'],as_of,start),None
        except Exception as e:return m['code'],[],f'{type(e).__name__}: {str(e)[:150]}'
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for code,ss,error in pool.map(backup,fallback):
            incoming.extend(ss);statuses.append({'source':'em-'+code,'status':'failed' if error else 'ok','error':error})
    merged=merge_series(old.get('inventories',[]),incoming,as_of)
    from source_supply import refresh_supplies
    supplies,supply_status=refresh_supplies(root,as_of,old.get('supplies',[]))
    packet={'schema':'fundamentals-v1','asOf':as_of,'checkedAt':dt.datetime.now(SHANGHAI).isoformat(timespec='seconds'),
            'inventories':merged,'supplies':supplies,'statuses':statuses+supply_status}
    from check_live_fundamentals import validate
    validate(packet)  # Validation precedes the atomic promotion of the old packet.
    text=json.dumps(packet,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    tmp=output.with_suffix('.incoming');tmp.write_text(text,encoding='utf-8');os.replace(tmp,output)
    count=len({s['code'] for s in merged if s['history'] and s['history'][-1]['date']==as_of})
    print(json.dumps({'asOf':as_of,'inventoryProductsOnDate':count,'series':len(merged),
                      'supplySeries':len(supplies),'supplyProducts':len({c for s in supplies for c in s['appliesTo']}),
                      'sources':[{k:v for k,v in s.items() if k!='errors'} for s in statuses+supply_status]},ensure_ascii=False))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as f:f.write('changed=true\n')
    return packet


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--as-of');p.add_argument('--history-days',type=int,default=18);a=p.parse_args()
    day=a.as_of or json.loads((ROOT/'dist/data.json').read_text(encoding='utf-8'))['asOf']
    if valid_day(day)>dt.datetime.now(SHANGHAI).date().isoformat():raise ValueError('future target')
    refresh(ROOT,day,a.history_days)
