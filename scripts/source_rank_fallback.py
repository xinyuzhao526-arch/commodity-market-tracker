"""Fill missing contract rankings from Eastmoney; never replace existing official ranks."""
import argparse
import datetime as dt
import json
import math
from pathlib import Path
import time
import requests

ROOT = Path(__file__).resolve().parents[1]
API = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
PAGE = 'https://data.eastmoney.com/futures/dl/data.html'
VENUES = {'DCE': {'DCE'}, 'SHFE': {'SHFE', 'SHF'}, 'CZCE': {'CZCE', 'CZC', 'ZCE'},
          'INE': {'INE'}, 'GFEX': {'GFEX', 'GFE'}}


def integer(value, *, nonnegative=False):
    if isinstance(value, bool) or value is None:
        raise ValueError('Expected integer.')
    number = float(value)
    if not math.isfinite(number) or number != int(number) or (nonnegative and number < 0):
        raise ValueError('Invalid integer quantity.')
    return int(number)


def normalize(records, contract, day, exchange):
    """The API returns a union of members; rebuild long and short lists independently."""
    sides = {'long': {}, 'short': {}}
    members = set()
    for row in records:
        if str(row.get('SECURITY_CODE') or '').upper() != contract.upper():
            raise ValueError('Ranking contract mismatch.')
        stamp = str(row.get('TRADE_DATE', ''))
        if dt.datetime.fromisoformat(stamp).date().isoformat() != day:
            raise ValueError('Ranking date mismatch.')
        code, _, venue = str(row.get('SECUCODE', '')).rpartition('.')
        if code.upper() != contract.upper() or venue.upper() not in VENUES[exchange]:
            raise ValueError('Ranking exchange mismatch.')
        if str(row.get('TYPE')) != '0':
            raise ValueError('Aggregate rows cannot supply member rankings.')
        name = str(row.get('MEMBER_NAME_ABBR') or '').strip()
        member = str(row.get('ORG_CODE') or name)
        if not name or member in members:
            raise ValueError('Missing or duplicate member identity.')
        members.add(member)
        for side, rank_key, position_key, change_key in [
            ('long', 'LPRANK', 'LONG_POSITION', 'LP_CHANGE'),
            ('short', 'SPRANK', 'SHORT_POSITION', 'SP_CHANGE')
        ]:
            rank = integer(row.get(rank_key), nonnegative=True)
            if not 1 <= rank <= 20:
                continue
            if rank in sides[side]:
                raise ValueError('Duplicate independent rank.')
            sides[side][rank] = (name, integer(row.get(position_key), nonnegative=True),
                                 integer(row[change_key]) if row.get(change_key) is not None else None)
    if not records:
        return []
    for side, rows in sides.items():
        if not rows or set(rows) != set(range(1, max(rows) + 1)):
            raise ValueError(f'Incomplete {side} rank sequence.')
    result = []
    for rank in range(1, max(max(v) for v in sides.values()) + 1):
        record = {'rank': rank}
        for side in sides:
            name, position, change = sides[side].get(rank, ('', None, None))
            record.update({side + 'Name': name, side: position, side + 'Change': change})
        result.append(record)
    return result


def fetch_rankings(market, day, *, cache=ROOT / 'data/raw/eastmoney-ranks', refresh=False):
    contract = market['main']['contract']
    params = {'reportName': 'RPT_FUTU_DAILYPOSITION', 'columns': 'ALL',
              'filter': f'(SECURITY_CODE="{contract.upper()}")(TRADE_DATE=\'{day}\')(TYPE="0")',
              'sortColumns': 'LPRANK', 'sortTypes': 1, 'pageSize': 200,
              'pageNumber': 1, 'source': 'WEB', 'client': 'WEB'}
    cache = Path(cache)
    path = cache / f'{day}-{contract.lower()}.json'
    public_url = requests.Request('GET', API, params=params).prepare().url
    if path.exists() and not refresh:
        packet = json.loads(path.read_text(encoding='utf-8'))
        return normalize(packet['records'], contract, day, market['exchange']), public_url
    records, pages, count = [], 1, None
    page = 1
    while page <= pages:
        params['pageNumber'] = page
        for attempt in range(3):
            try:
                response = requests.get(API, params=params, timeout=(8, 20),
                                        headers={'User-Agent': 'Mozilla/5.0', 'Referer': PAGE})
                response.raise_for_status()
                document = response.json()
                break
            except (requests.RequestException, ValueError):
                if attempt == 2:
                    raise
                time.sleep(.5 * (attempt + 1))
        if document.get('success') is not True:
            if page == 1 and document.get('message') == '返回数据为空':
                return [], public_url
            raise ValueError('Eastmoney query failed or lost a page.')
        result = document.get('result') or {}
        current_count = integer(result.get('count'), nonnegative=True)
        current_pages = integer(result.get('pages'), nonnegative=True)
        if page == 1:
            count, pages = current_count, current_pages
            if not 1 <= pages <= 10 or count <= 0:
                raise ValueError('Unexpected ranking pagination.')
        elif current_count != count or current_pages != pages:
            raise ValueError('Ranking pagination changed during retrieval.')
        batch = result.get('data')
        if not isinstance(batch, list) or not batch:
            raise ValueError('Missing ranking page.')
        records.extend(batch)
        page += 1
    if len(records) != count:
        raise ValueError('Incomplete member union; refusing partial rankings.')
    ranks = normalize(records, contract, day, market['exchange'])
    cache.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps({'records': records}, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    temp.replace(path)
    return ranks, public_url


def enrich_snapshot(data, *, fetcher=fetch_rankings):
    day = data['asOf']
    attempts = []
    filled = 0
    for market in data['markets']:
        if market.get('ranks'):
            continue
        attempt = {'code': market['code'], 'contract': market['main']['contract'], 'date': day}
        try:
            ranks, url = fetcher(market, day)
            if ranks:
                previous_source = market.get('rankSource')
                if previous_source:
                    market['rankPrimarySource'] = previous_source
                market['ranks'] = ranks
                market['rankSource'] = {'name': '东方财富·合约会员持仓龙虎榜（备用）',
                                        'provider': 'eastmoney', 'url': url, 'landing': PAGE,
                                        'date': day, 'contract': market['main']['contract'],
                                        'official': False, 'fallback': True}
                market['rankingStatus'] = 'available-fallback'
                market['rankingNote'] = '官方排名未取得；采用东方财富同日、同合约独立多空排名，最多各前20名，不代表全市场净持仓。'
                market['rankingFallbackNote'] = ''
                attempt['status'] = 'filled'
                filled += 1
            else:
                attempt['status'] = 'empty'
                market['rankingFallbackNote'] = '东方财富备用查询也未返回同日、同合约排名。'
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            attempt.update(status='unavailable', reason=str(exc)[:240])
            market['rankingFallbackNote'] = '东方财富备用排名未通过读取或校验，未填入数据。'
        attempts.append(attempt)
    for source in data.get('exchangeSources', []):
        markets = [m for m in data['markets'] if m['exchange'] == source['exchange']]
        fallback = [m for m in markets if m.get('rankSource', {}).get('provider') == 'eastmoney']
        official = [m for m in markets if m.get('ranks') and m.get('rankSource', {}).get('official') is True]
        source['rankingStatus'] = f"{sum(bool(m.get('ranks')) for m in markets)} / {len(markets)} 个品种"
        source['rankingOfficialCount'] = len(official)
        source['rankingFallbackCount'] = len(fallback)
        source['rankingSourceNote'] = f'官方排名 {len(official)} 个；东方财富备用排名 {len(fallback)} 个。备用来源单独标识，不改变行情来源。'
        if fallback:
            source['rankUrl'] = PAGE
        if source['exchange'] == 'DCE':
            source['note'] = ('行情使用已注明的新浪具体合约日线或经核验的盘后快照，仅为代表合约口径。'
                              '会员排名按同日、同合约从东方财富补充；未返回有效记录的合约仍留空。')
    summary = {'date': day, 'requested': len(attempts), 'filled': filled,
               'checkedAt': dt.datetime.now(dt.timezone.utc).isoformat(),
               'available': sum(bool(m.get('ranks')) for m in data['markets']),
               'remaining': sum(not m.get('ranks') for m in data['markets']), 'attempts': attempts}
    data['rankingFallback'] = summary
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'dist/data.json')
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--only-if-filled', action='store_true', help='Leave a published snapshot unchanged if no new ranks arrive.')
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8'))
    summary = enrich_snapshot(data, fetcher=lambda m, day: fetch_rankings(m, day, refresh=args.refresh))
    # Provenance and failed-query notes are published even when a query is empty.
    if summary['filled'] or not args.only_if_filled:
        from analyze_markets import analyze
        from refresh_daily import validate_snapshot
        analyze(data)
        validate_snapshot(data, data['asOf'])
        temp = args.input.with_suffix('.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')
        temp.replace(args.input)
    print(json.dumps(summary, ensure_ascii=True), flush=True)
    import os
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
            output.write(f"changed={str(summary['filled'] > 0).lower()}\n")


if __name__ == '__main__':
    main()
