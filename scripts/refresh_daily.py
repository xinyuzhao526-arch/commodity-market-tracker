"""Refresh all exchanges in isolation; promote only a validated common-date snapshot."""
import argparse
import collections
import datetime as dt
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SHANGHAI = dt.timezone(dt.timedelta(hours=8))
EXCHANGES = {'SHFE', 'INE', 'DCE', 'CZCE', 'GFEX'}


def target_day(now, requested=None):
    if requested:
        day = dt.date.fromisoformat(requested)
        if day > now.date() or (day == now.date() and now.hour < 15):
            raise ValueError('Requested day has not closed in Asia/Shanghai.')
        return day
    day = now.date() - dt.timedelta(days=now.hour < 15)
    while day.weekday() >= 5:
        day -= dt.timedelta(days=1)
    return day


def official_report_available(day, cache):
    """A 404 means no published report, not proof of a trading holiday."""
    filename = f'kx{day:%Y%m%d}.dat'
    url = 'https://www.shfe.com.cn/data/tradedata/future/dailydata/' + filename
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'CommodityMarketTracker/1.0'})
            with urllib.request.urlopen(request, timeout=25) as response:
                raw = response.read()
            doc = json.loads(raw)
            if doc.get('report_date') != day.strftime('%Y%m%d') or not doc.get('o_curinstrument'):
                raise ValueError('SHFE preflight returned an invalid or wrong-date report.')
            cache.mkdir(parents=True, exist_ok=True)
            (cache / filename).write_bytes(raw)
            return True
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            if attempt == 2:
                raise
        except (OSError, ValueError):
            if attempt == 2:
                raise
        time.sleep(2 * (attempt + 1))


def validate_snapshot(data, day, previous=None, history_start=None):
    """Fail closed on mixed dates, corrupted bars, or a large coverage regression."""
    if data.get('schema') != 'domestic-v1' or data.get('asOf') != day:
        raise ValueError('Snapshot schema/date mismatch.')
    markets = data.get('markets', [])
    counts = collections.Counter(m['exchange'] for m in markets)
    if set(counts) != EXCHANGES:
        raise ValueError(f'Incomplete exchange coverage: {dict(counts)}')
    codes = [m['code'] for m in markets]
    if len(set(codes)) != len(codes):
        raise ValueError('Duplicate product codes.')
    if previous:
        prior_counts = collections.Counter(m['exchange'] for m in previous['markets'])
        for ex, n in prior_counts.items():
            if counts[ex] < math.ceil(n * .8):
                raise ValueError(f'{ex} coverage fell from {n} to {counts[ex]}; review required.')
    previous_markets = {m['code']: m for m in previous['markets']} if previous else {}
    history_start = history_start or (dt.date.fromisoformat(day) - dt.timedelta(days=120)).isoformat()
    for m in markets:
        main, bars = m['main'], m['history']
        if main['date'] != day or not bars or bars[-1]['date'] != day:
            raise ValueError(f"{m['code']}: incomplete current-date history.")
        dates = [b['date'] for b in bars]
        if dates != sorted(set(dates)):
            raise ValueError(f"{m['code']}: duplicate/unsorted historical dates.")
        prior = previous_markets.get(m['code'])
        prior_cont=prior.get('continuous') if prior else None
        if prior_cont and prior_cont.get('history'):
            current_cont=m.get('continuous') or {}
            count=len(prior_cont['history'])
            if current_cont.get('history',[])[:count]!=prior_cont['history']:
                raise ValueError(f"{m['code']}: published continuous history lost or rebased.")
            if current_cont.get('rollovers',[])[:len(prior_cont.get('rollovers',[]))]!=prior_cont.get('rollovers',[]):
                raise ValueError(f"{m['code']}: published roll records changed.")
            if any(current_cont.get(k)!=prior_cont.get(k) for k in ('baseDate','baseContract','basePrice','schema')):
                raise ValueError(f"{m['code']}: continuous base changed.")
        if prior and previous['asOf'] == day and prior['main']['contract'].lower() == main['contract'].lower() and prior.get('ranks') and not m.get('ranks'):
            raise ValueError(f"{m['code']}: lost previously validated same-day rankings.")
        if prior and prior['main']['contract'].lower() == main['contract'].lower():
            known_dates = {b['date'] for b in prior['history'] if history_start <= b['date'] <= day}
            missing_known = known_dates - set(dates)
            if missing_known:
                raise ValueError(f"{m['code']}: lost {len(missing_known)} previously validated historical observations.")
        for bar in bars:
            if bar['date'] > day or bar['contract'].lower() != main['contract'].lower():
                raise ValueError(f"{m['code']}: future or mixed-contract observation.")
            if not isinstance(bar.get('close'), (int, float)) or not math.isfinite(bar['close']) or bar['close'] <= 0:
                raise ValueError(f"{m['code']}: invalid close.")
        if bars[-1]['close'] != main['close']:
            raise ValueError(f"{m['code']}: main/history close mismatch.")
        if m.get('quoteSource', {}).get('date') != day:
            raise ValueError(f"{m['code']}: quote provenance date mismatch.")
        if m['ranks'] and m.get('rankSource', {}).get('date') != day:
            raise ValueError(f"{m['code']}: ranking provenance date mismatch.")
        if 'analysis' not in m:
            raise ValueError(f"{m['code']}: research factors absent.")
    if any(s.get('date') != day for s in data.get('exchangeSources', [])):
        raise ValueError('Exchange source dates disagree.')
    # This also rejects infinity/NaN buried in optional raw or derived fields.
    json.dumps(data, allow_nan=False)
    return dict(counts)


def run_script(stage, name, *args):
    print(f'Running {name}', flush=True)
    subprocess.run([sys.executable, str(stage / 'scripts' / name), *args],
                   cwd=stage, check=True, timeout=2400)


def build_candidate(stage, day, start, run=run_script):
    # Keep the already-published base/roll history before source scripts replace data.json.
    previous_research=stage/'dist/previous-research.json'
    shutil.copy2(stage/'dist/data.json',previous_research)
    run(stage, 'probe_sources.py', '--as-of', day)
    for script, extra in [
        ('update_domestic.py', []), ('source_czce.py', []),
        ('source_dce.py', ['--refresh', '--skip-official-probe']), ('source_gfex.py', [])
    ]:
        run(stage, script, '--as-of', day, '--start', start, *extra)
    dce = json.loads((stage / 'data/dce-markets.json').read_text(encoding='utf-8'))
    if dce.get('coverage', {}).get('errors'):
        raise ValueError('Some DCE products failed; refusing a partial publication: ' +
                         json.dumps(dce['coverage']['errors'], ensure_ascii=False))
    for name in ['merge_exchanges.py', 'source_rank_fallback.py']:
        run(stage, name)
    run(stage,'source_continuous.py','--previous',str(previous_research))
    for name in ['analyze_markets.py','check_analysis.py','check_continuous.py']:
        run(stage,name)
    return json.loads((stage / 'dist/data.json').read_text(encoding='utf-8'))


def refresh(root, day, start, *, rebuild=False, preflight=official_report_available, builder=build_candidate):
    published = root / 'dist/data.json'
    previous = json.loads(published.read_text(encoding='utf-8'))
    if day < previous['asOf'] or (day == previous['asOf'] and not rebuild):
        return {'status': 'up-to-date', 'asOf': previous['asOf'], 'changed': False}
    if not preflight(dt.date.fromisoformat(day), root / 'data/raw'):
        return {'status': 'no-published-report', 'requestedDate': day,
                'asOf': previous['asOf'], 'changed': False}
    with tempfile.TemporaryDirectory(prefix='.refresh-', dir=root) as temp:
        stage = Path(temp)
        shutil.copytree(root / 'scripts', stage / 'scripts', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(root / 'dist', stage / 'dist', ignore=shutil.ignore_patterns('market-tracker.html'))
        (stage / 'data').mkdir()
        cached = root / 'data/raw'
        if cached.exists():
            shutil.copytree(cached, stage / 'data/raw')
        try:
            candidate = builder(stage, day, start)
            counts = validate_snapshot(candidate, day, previous, start)
            # A failed exporter also must leave the published data intact.
            run_script(stage, 'export_html.py', '--output', str(stage / 'dist/market-tracker.html'))
            (root / 'data').mkdir(exist_ok=True)
            for packet in stage.glob('data/*-markets.json'):
                shutil.copy2(packet, root / 'data' / packet.name)
            if (stage / 'data/shfe-base.json').exists():
                shutil.copy2(stage / 'data/shfe-base.json', root / 'data/shfe-base.json')
            # Single atomic data promotion is the commit point. GitHub only pushes after success.
            incoming = published.with_suffix('.incoming')
            shutil.copy2(stage / 'dist/data.json', incoming)
            os.replace(incoming, published)
        finally:
            # Reuse successful dated downloads even if a different source failed.
            if (stage / 'data/raw').exists():
                shutil.copytree(stage / 'data/raw', cached, dirs_exist_ok=True)
    return {'status': 'updated', 'asOf': day, 'changed': True, 'byExchange': counts}


def report(result):
    print(json.dumps(result, ensure_ascii=False), flush=True)
    (ROOT / '.refresh-status.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as out:
            out.write(f"changed={str(result.get('changed', False)).lower()}\nas_of={result.get('asOf', '')}\n")
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as out:
            out.write(f"### 商品市场追踪盘后更新\n\n状态：`{result['status']}`\n\n最新完整快照：**{result.get('asOf', '未改变')}**\n\n")
            if result['status'] == 'no-published-report':
                out.write('目标日期尚无可读取的上期所正式报告（可能休市或尚未发布）；保留上一份快照。\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', help='Optional YYYY-MM-DD; defaults to the latest closed weekday in Shanghai.')
    parser.add_argument('--start', help='Optional history window start; defaults to 120 calendar days before target.')
    parser.add_argument('--rebuild', action='store_true', help='Revalidate the same published day; never permits rollback.')
    parser.add_argument('--provider', choices=['eastmoney', 'exchanges'], default='eastmoney',
                        help='Default: Eastmoney public fixed-contract data. Legacy sources are opt-in.')
    args = parser.parse_args()
    now = dt.datetime.now(SHANGHAI)
    day = target_day(now, args.as_of)
    start = dt.date.fromisoformat(args.start) if args.start else day - dt.timedelta(days=120)
    if start > day - dt.timedelta(days=30):
        raise ValueError('History window must cover at least 30 calendar days.')
    try:
        options = {}
        if args.provider == 'eastmoney':
            from source_eastmoney import build
            options = {'preflight': lambda *_: True, 'builder': build}
        report(refresh(ROOT, day.isoformat(), start.isoformat(), rebuild=args.rebuild, **options))
    except Exception as exc:
        report({'status': 'failed', 'changed': False, 'error': str(exc),
                'asOf': json.loads((ROOT / 'dist/data.json').read_text(encoding='utf-8'))['asOf']})
        raise


if __name__ == '__main__':
    main()
