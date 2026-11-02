"""Independent ranking fixtures: never sum a member union as if it were a top-20 list."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

spec = importlib.util.spec_from_file_location('source_rank_fallback', Path(__file__).resolve().parents[1] / 'scripts/source_rank_fallback.py')
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


def records():
    common = {'SECURITY_CODE': 'I2701', 'SECUCODE': 'I2701.DCE', 'TRADE_DATE': '2026-10-30 00:00:00', 'TYPE': '0'}
    return [{**common, 'ORG_CODE': 'A', 'MEMBER_NAME_ABBR': 'Alpha', 'LPRANK': 1, 'SPRANK': 2,
             'LONG_POSITION': 101, 'SHORT_POSITION': 92, 'LP_CHANGE': 10, 'SP_CHANGE': -2},
            {**common, 'ORG_CODE': 'B', 'MEMBER_NAME_ABBR': 'Beta', 'LPRANK': 2, 'SPRANK': 1,
             'LONG_POSITION': 111, 'SHORT_POSITION': 54, 'LP_CHANGE': 11, 'SP_CHANGE': 7},
            {**common, 'ORG_CODE': 'C', 'MEMBER_NAME_ABBR': 'Outside', 'LPRANK': 9999, 'SPRANK': 9999,
             'LONG_POSITION': 999999, 'SHORT_POSITION': 999999, 'LP_CHANGE': 999999, 'SP_CHANGE': 999999}]


def market():
    return {'code': 'i', 'exchange': 'DCE', 'main': {'contract': 'i2701', 'date': '2026-10-30', 'close': 675},
            'history': [{'date': '2026-10-30', 'close': 675}], 'ranks': [],
            'rankSource': {'name': 'Official unavailable', 'official': True, 'date': '2026-10-30'}}


class RankingTests(unittest.TestCase):
    def test_independent_sides_and_unranked_member_exclusion(self):
        ranks = source.normalize(records(), 'i2701', '2026-10-30', 'DCE')
        self.assertEqual([r['longName'] for r in ranks], ['Alpha', 'Beta'])
        self.assertEqual([r['shortName'] for r in ranks], ['Beta', 'Alpha'])
        self.assertEqual(sum(r['long'] for r in ranks), 212)
        self.assertEqual(sum(r['short'] for r in ranks), 146)
        self.assertEqual(sum(r['longChange'] - r['shortChange'] for r in ranks), 16)

    def test_identity_date_venue_totals_and_gaps_fail_closed(self):
        mutations = [{'SECURITY_CODE': 'I2612'}, {'SECUCODE': 'I2701.SHFE'},
                     {'TRADE_DATE': '2026-10-29'}, {'TYPE': '2'}, {'LPRANK': 3},
                     {'LONG_POSITION': -1}, {'LONG_POSITION': float('nan')}, {'ORG_CODE': 'B'}]
        for change in mutations:
            rows = records()
            rows[0].update(change)
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                source.normalize(rows, 'i2701', '2026-10-30', 'DCE')

    def test_missing_change_is_unknown_not_zero(self):
        rows = records()
        rows[0]['LP_CHANGE'] = None
        ranks = source.normalize(rows, 'i2701', '2026-10-30', 'DCE')
        self.assertIsNone(ranks[0]['longChange'])

    def test_official_data_is_preserved_and_prices_are_unchanged(self):
        official = market()
        official['code'] = 'official'
        official['ranks'] = [{'rank': 1, 'long': 20, 'short': 10}]
        value = market()
        before = copy.deepcopy(value)
        data = {'asOf': '2026-10-30', 'markets': [official, value], 'exchangeSources': [{'exchange': 'DCE'}]}
        def fetch(m, day):
            self.assertEqual(m['code'], 'i')
            return source.normalize(records(), m['main']['contract'], day, 'DCE'), source.API
        summary = source.enrich_snapshot(data, fetcher=fetch)
        self.assertEqual(summary['filled'], 1)
        self.assertEqual(official['ranks'], [{'rank': 1, 'long': 20, 'short': 10}])
        for key in ['main', 'history']:
            self.assertEqual(value[key], before[key])
        self.assertFalse(value['rankSource']['official'])
        self.assertEqual(value['rankSource']['provider'], 'eastmoney')
        self.assertEqual(value['rankPrimarySource'], before['rankSource'])
        self.assertEqual(data['exchangeSources'][0]['rankingFallbackCount'], 1)

    def test_empty_and_network_failure_remain_missing(self):
        for fail in [False, True]:
            data = {'asOf': '2026-10-30', 'markets': [market()]}
            def fetch(*_):
                if fail:
                    raise source.requests.Timeout('temporary outage')
                return [], source.API
            summary = source.enrich_snapshot(data, fetcher=fetch)
            self.assertEqual(summary['filled'], 0)
            self.assertEqual(data['markets'][0]['ranks'], [])

    def test_incomplete_pagination_is_rejected_without_cache(self):
        response = Mock()
        response.json.return_value = {'success': True, 'result': {'count': 4, 'pages': 1, 'data': records()}}
        with tempfile.TemporaryDirectory() as cache, patch.object(source.requests, 'get', return_value=response):
            with self.assertRaisesRegex(ValueError, 'Incomplete member union'):
                source.fetch_rankings(market(), '2026-10-30', cache=cache)
            self.assertEqual(list(Path(cache).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
