"""Eastmoney public fixed-delivery futures data; no account credentials required.

Published research bases remain immutable. Never substitute a vendor continuous
symbol for a delivery contract or use an intraday quote as a completed daily bar.
"""
import concurrent.futures
import copy
import datetime as dt
import json
import math
from pathlib import Path
import re
import time
import requests

ROOT = Path(__file__).resolve().parents[1]
LIST = 'https://push2.eastmoney.com/api/qt/clist/get'
LIST_ENDPOINTS = (LIST, 'https://82.push2.eastmoney.com/api/qt/clist/get',
                  'https://push2delay.eastmoney.com/api/qt/clist/get')
KLINE = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
PAGE = 'https://quote.eastmoney.com/center/gridlist.html#futures_qh'
VENUES = {113: {'SHFE'}, 114: {'DCE'}, 115: {'CZCE'}, 142: {'INE'}, 225: {'GFEX'}}
# f64 is an unsigned change on some contracts; use the signed f67 instead.
FIELDS = 'f51,f52,f53,f54,f55,f56,f57,f63,f65,f66,f67,f69'


def get_json(url, params):
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=(8, 25),
                             headers={'User-Agent': 'Mozilla/5.0', 'Referer': PAGE})
            r.raise_for_status()
            doc = r.json()
            if doc.get('rc') != 0:
                raise ValueError('Eastmoney returned an error')
            return doc
        except (requests.RequestException, ValueError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def listings():
    # Restart pagination on another Eastmoney host after transport failure.
    # Never splice pages from different hosts or reuse a stale contract list.
    for index, endpoint in enumerate(LIST_ENDPOINTS):
        try:
            return _listings(endpoint)
        except requests.RequestException:
            if index == len(LIST_ENDPOINTS) - 1:
                raise
            print('Eastmoney contract-list endpoint unavailable; restarting on backup host.', flush=True)


def _listings(endpoint):
    result = {}
    total = None
    page = 1
    while total is None or len(result) < total:
        doc = get_json(endpoint, {'pn': page, 'pz': 100,
                             'fs': 'm:113,m:114,m:115,m:142,m:225',
                             'fields': 'f12,f13,f14', 'fltt': 2, 'np': 1})
        data = doc.get('data') or {}
        if total is None:
            total = int(data['total'])
        if int(data.get('total', -1)) != total or not 0 < total < 10000:
            raise ValueError('Contract listing changed during pagination')
        rows = data.get('diff') or []
        if isinstance(rows, dict):
            rows = list(rows.values())
        if not rows:
            raise ValueError('Missing contract listing page')
        for row in rows:
            key = f"{row['f13']}.{row['f12']}"
            if key in result:
                raise ValueError('Duplicate listing across pages')
            result[key] = row
        page += 1
    if len(result) != total:
        raise ValueError('Incomplete contract listing')
    return result


def number(x):
    if x in (None, '', '-') or isinstance(x, bool):
        return None
    value = float(x)
    if not math.isfinite(value):
        raise ValueError('Nonfinite value')
    return value


def contract_code(symbol, exchange):
    match = re.fullmatch(r'([a-zA-Z]+)(\d{3,4})', symbol)
    if not match or not 1 <= int(match[2][-2:]) <= 12:
        return None
    suffix = match[2]
    if exchange == 'CZCE' and len(suffix) == 4:
        suffix = suffix[1:]
    return match[1].lower(), match[1].lower() + suffix


def parse_bars(doc, symbol, venue, exchange, start, day):
    data = doc.get('data')
    if not data:
        return []
    if data.get('code', '').lower() != symbol.lower() or int(data['market']) != venue:
        raise ValueError('Kline contract/venue mismatch')
    code, contract = contract_code(symbol, exchange)
    rows = []
    seen = set()
    for line in data.get('klines') or []:
        values = line.split(',')
        if len(values) != len(FIELDS.split(',')):
            raise ValueError('Unexpected futures daily field count')
        stamp = dt.date.fromisoformat(values[0]).isoformat()
        if stamp in seen:
            raise ValueError('Duplicate daily date')
        seen.add(stamp)
        if not start <= stamp <= day:
            continue
        bar = dict(zip(('open', 'close', 'high', 'low', 'volume', 'turnover',
                        'oi', 'settle', 'oiCheck', 'oiChange', 'prevSettle'),
                       map(number, values[1:])))
        if bar.pop('oiCheck') != bar['oi']:
            raise ValueError('Daily position fields disagree')
        if not all(bar[k] is not None and bar[k] > 0 for k in ('open', 'close', 'high', 'low')):
            continue
        if not bar['low'] <= min(bar['open'], bar['close']) <= max(bar['open'], bar['close']) <= bar['high']:
            raise ValueError('Daily OHLC bounds invalid')
        if any(bar[k] is None or bar[k] < 0 for k in ('oi', 'volume', 'turnover')):
            raise ValueError('Daily quantity invalid')
        if any(bar[k] is not None and bar[k] != int(bar[k]) for k in ('oi', 'volume', 'oiChange')):
            raise ValueError('Noninteger futures quantity; check vendor field mapping')
        for key in ('settle', 'prevSettle'):
            if bar[key] is not None and bar[key] <= 0:
                bar[key] = None
        bar.update(code=code, contract=contract, date=stamp,
                   changePct=(bar['close'] / bar['prevSettle'] - 1) * 100 if bar['prevSettle'] else None,
                   turnoverUnit='元', sourceUrl=KLINE)
        rows.append(bar)
    return sorted(rows, key=lambda b: b['date'])


def fetch_bars(root, secid, row, exchange, start, day):
    params = {'secid': secid, 'klt': 101, 'fqt': 0, 'beg': start.replace('-', ''),
              'end': day.replace('-', ''), 'fields1': 'f1,f2,f3,f4,f5,f6', 'fields2': FIELDS}
    cache = root / 'data/raw/eastmoney-quotes-v1' / f'{secid}-{start}-{day}.json'
    if cache.exists():
        doc = json.loads(cache.read_text(encoding='utf-8'))
    else:
        doc = get_json(KLINE, params)
    bars = parse_bars(doc, row['f12'], int(row['f13']), exchange, start, day)
    source_url = requests.Request('GET', KLINE, params=params).prepare().url
    for bar in bars:
        bar['sourceUrl'] = source_url
    if bars:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
    return bars


def preserve_history(history, old, contract, start, day):
    """Retain dated, validated old bars where the new vendor has no OHLC.

    Original turnover is not silently converted or reattributed to Eastmoney.
    This never fills the new target day from a different date or contract.
    """
    indexed = {bar['date']: bar for bar in history}
    for original in old.get('history', []):
        if (original['contract'].lower() != contract.lower() or
                not start <= original['date'] < day or original['date'] in indexed):
            continue
        bar = copy.deepcopy(original)
        bar['contract'] = contract
        bar['sourceUrl'] = bar.get('sourceUrl') or (old.get('historySource') or {}).get('url') or old['quoteSource']['url']
        bar['provider'] = 'previous-validated-source'
        bar.setdefault('turnoverUnit', old.get('turnoverUnit') or '原来源单位（未转换）')
        indexed[bar['date']] = bar
    return [indexed[stamp] for stamp in sorted(indexed)]


def build(root, day, start, workers=8):
    from continuous_prices import construct
    from source_rank_fallback import fetch_rankings
    from analyze_markets import analyze
    previous = json.loads((root / 'dist/data.json').read_text(encoding='utf-8'))
    products = {m['code']: m for m in previous['markets']}
    listing = listings()
    jobs = {}
    for secid, row in listing.items():
        for exchange in VENUES.get(int(row['f13']), set()):
            normalized = contract_code(row['f12'], exchange)
            if normalized and normalized[0] in products and products[normalized[0]]['exchange'] == exchange:
                jobs[secid] = (row, exchange)
    # Delisted months may no longer be queryable. Keep their published research
    # points; construct() stops extension if their roll bridge is unavailable.
    frames = {}
    errors = []
    def one(item):
        secid, (row, exchange) = item
        return fetch_bars(root, secid, row, exchange, start, day)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, item): item[0] for item in jobs.items()}
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            try:
                for bar in future.result():
                    frames.setdefault(bar['code'], {}).setdefault(bar['date'], {})[bar['contract']] = bar
            except Exception as exc:
                errors.append({'secid': futures[future], 'error': str(exc)[:200]})
            completed += 1
            if completed % 100 == 0:
                print(f'Eastmoney daily contracts {completed}/{len(jobs)}', flush=True)
    if errors:
        raise ValueError('Incomplete Eastmoney contract downloads: ' + json.dumps(errors[:8]))
    calendar = sorted({d for code in frames for d in frames[code]})
    markets = []
    for code, old in products.items():
        ff = frames.get(code, {})
        current = list(ff.get(day, {}).values())
        active = [r for r in current if r['volume'] > 0 and r['oi'] > 0]
        if not active:
            raise ValueError(f'{code}: no completed target-day contract')
        main = max(active, key=lambda r: (r['oi'], r['contract']))
        history = [ff[d][main['contract']] for d in sorted(ff) if main['contract'] in ff[d]]
        history = preserve_history(history, old, main['contract'], start, day)
        source = {'name': '东方财富·逐合约日线', 'provider': 'eastmoney', 'url': main['sourceUrl'],
                  'landing': PAGE, 'date': day, 'official': False, 'contract': main['contract']}
        m = {k: old[k] for k in ('code', 'name', 'sector', 'unit', 'exchange')}
        m.update(main=main, history=history, contracts=sorted(current, key=lambda r: r['contract']),
                 ranks=[], quoteSource=dict(source), historySource=dict(source),
                 historyType='fixed-contract', changeBasis='previous-settlement',
                 aggregateScope='available-contracts', totalVolume=None, totalOi=None, totalOiChange=None,
                 aggregateNote='东方财富可取得的交割月样本；不声称覆盖已退市合约或交易所全市场合计。',
                 turnoverUnit='元')
        m['mainSelection'] = '东方财富可取得的当日有效成交交割月中，持仓量最大合约'
        if any(r.get('provider') == 'previous-validated-source' for r in history):
            m['historySource']['name'] += '（缺失历史保留已验证原来源，见逐条记录）'
        continuous = construct(ff, calendar, day, old.get('continuous'))
        continuous['provider'] = '东方财富逐合约日线 / 本站自建（已发布历史保留原来源）'
        m['continuous'] = continuous
        try:
            ranks, url = fetch_rankings(m, day, cache=root / 'data/raw/eastmoney-ranks')
            m['ranks'] = ranks
            m['rankSource'] = {'name': '东方财富·合约会员持仓龙虎榜', 'provider': 'eastmoney',
                               'url': url, 'date': day, 'official': False, 'fallback': False}
            m['rankingStatus'] = 'available' if ranks else 'unavailable'
            m['rankingNote'] = '同日同合约独立多空前20名样本。' if ranks else '东方财富未返回同日同合约排名。'
        except Exception as exc:
            m['rankSource'] = {'name': '东方财富·排名未取得', 'url': 'https://data.eastmoney.com/futures/dl/data.html', 'date': day, 'official': False}
            m['rankingStatus'] = 'unavailable'
            m['rankingNote'] = f'东方财富排名读取或校验失败：{type(exc).__name__}'
        markets.append(m)
    data = {'schema': 'domestic-v1', 'asOf': day,
            'fetchedAt': dt.datetime.now(dt.timezone.utc).isoformat(), 'sourceUpdated': day,
            'sources': {'landing': PAGE, 'quotes': KLINE, 'ranks': 'https://data.eastmoney.com/futures/dl/data.html'},
            'version': 'eastmoney-public-v1', 'markets': markets,
            'coverage': {'exchanges': sorted({m['exchange'] for m in markets}), 'markets': len(markets),
                         'firstDate': calendar[0], 'tradingDays': len(calendar)},
            'exchangeSources': [{'exchange': ex, 'name': ex, 'provider': 'eastmoney', 'official': False,
                                 'date': day, 'url': PAGE, 'quoteUrl': KLINE, 'quoteStatus': '已接入东方财富',
                                 'marketCount': sum(m['exchange'] == ex for m in markets),
                                 'rankingStatus': f"{sum(bool(m['ranks']) for m in markets if m['exchange'] == ex)} 个品种",
                                 'note': '东方财富转载逐合约日线；成交额单位为元，非交易所原始报告。'}
                                for ex in sorted({m['exchange'] for m in markets})],
            'continuousStatus': {'asOf': day, 'errors': [], 'total': len(markets),
                                 'ready': sum(m['continuous']['status'] == 'ready' for m in markets)}}
    analyze(data)
    (root / 'dist/data.json').write_text(json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(',', ':')), encoding='utf-8')
    return data


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--as-of', required=True)
    p.add_argument('--start', required=True)
    a = p.parse_args()
    # Use refresh_daily for staging, closed-day checks, validation and publication.
    from refresh_daily import target_day, SHANGHAI
    target_day(dt.datetime.now(SHANGHAI), a.as_of)
    from refresh_daily import refresh
    print(refresh(ROOT, a.as_of, a.start, rebuild=True, preflight=lambda *_: True, builder=build))
