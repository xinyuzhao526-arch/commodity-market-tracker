"""Vendor boundaries: fixed months, signed quantities and provenance."""
import copy
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import source_eastmoney as em


class EastmoneyTests(unittest.TestCase):
    def packet(self):
        # Fields and actual Nov 4/5 cu2612 observations verified against the
        # previous published official snapshot; turnover in Eastmoney yuan.
        return {'data': {'code': 'cu2612', 'market': 113, 'klines': [
            '2026-11-04,106400,106170,107160,105350,170590,90613268480,200081,106230,200081,9294,107230',
            '2026-11-05,106640,106410,107230,105480,133785,71122366464,195846,106320,195846,-4235,106230']}}

    def parse(self, packet=None):
        return em.parse_bars(packet or self.packet(), 'cu2612', 113, 'SHFE', '2026-11-01', '2026-11-05')

    def test_signed_change_settlement_and_turnover_units(self):
        rows = self.parse()
        self.assertEqual(rows[-1]['oiChange'], -4235)
        self.assertEqual(rows[-1]['oi'] - rows[-2]['oi'], -4235)
        self.assertEqual(rows[-1]['prevSettle'], rows[-2]['settle'])
        self.assertAlmostEqual(rows[-1]['changePct'], (106410 / 106230 - 1) * 100)
        self.assertEqual(rows[-1]['turnoverUnit'], '元')
        self.assertEqual(rows[-1]['turnover'], 71122366464)

    def test_never_treat_continuous_as_delivery(self):
        for symbol in ['cu0', 'cu9999', 'cu888', 'cu2613', 'cu']:
            self.assertIsNone(em.contract_code(symbol, 'SHFE'))
        self.assertEqual(em.contract_code('MA2701', 'CZCE'), ('ma', 'ma701'))

    def test_wrong_contract_wrong_venue_and_duplicate_date_rejected(self):
        for key, value in [('code', 'cu2701'), ('market', 114)]:
            doc = self.packet(); doc['data'][key] = value
            with self.assertRaises(ValueError):
                self.parse(doc)
        doc = self.packet(); doc['data']['klines'].append(doc['data']['klines'][0])
        with self.assertRaises(ValueError):
            self.parse(doc)

    def test_future_bar_not_used(self):
        doc = self.packet()
        doc['data']['klines'].append(doc['data']['klines'][-1].replace('2026-11-05', '2026-11-06'))
        self.assertEqual(len(self.parse(doc)), 2)

    def test_wrong_field_mapping_and_invalid_bounds_rejected(self):
        for before, after in [('-4235', '104.42'), ('105480', '107500')]:
            doc = self.packet(); doc['data']['klines'][-1] = doc['data']['klines'][-1].replace(before, after)
            with self.assertRaises(ValueError):
                self.parse(doc)

    def test_pagination_must_be_complete_and_unique(self):
        first = {'data': {'total': 2, 'diff': [{'f12': 'cu2612', 'f13': 113}]}}
        with patch.object(em, 'get_json', side_effect=[first, copy.deepcopy(first)]):
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                em.listings()

    def test_historical_gaps_keep_original_source_without_cross_contract_fill(self):
        old = {'history': [{'date': '2026-11-03', 'contract': 'cu2612', 'close': 106090, 'turnover': 10},
                           {'date': '2026-11-02', 'contract': 'cu2701', 'close': 1}],
               'quoteSource': {'url': 'https://www.shfe.com.cn/report'}}
        result = em.preserve_history(self.parse(), old, 'cu2612', '2026-11-01', '2026-11-05')
        self.assertEqual([r['date'] for r in result], ['2026-11-03', '2026-11-04', '2026-11-05'])
        self.assertEqual(result[0]['sourceUrl'], old['quoteSource']['url'])
        self.assertEqual(result[0]['turnover'], 10)
        self.assertEqual(result[0]['provider'], 'previous-validated-source')


if __name__ == '__main__':
    unittest.main()
