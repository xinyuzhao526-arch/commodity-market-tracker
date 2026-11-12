"""Publication boundary tests: bad source data must never replace the last good close."""
import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'scripts/refresh_daily.py'
spec = importlib.util.spec_from_file_location('refresh_daily', MODULE)
daily = importlib.util.module_from_spec(spec)
spec.loader.exec_module(daily)


class TransportRetryTests(unittest.TestCase):
    def test_transport_retry_preserves_target_and_options(self):
        result = {'status': 'updated', 'changed': True}
        with patch.object(daily, 'refresh', side_effect=[daily.requests.HTTPError('502'), result]) as refresh, \
             patch.object(daily.time, 'sleep') as sleep:
            self.assertEqual(daily.refresh_with_retries(Path('test'), '2026-11-11', '2026-07-14', rebuild=True), result)
        self.assertEqual(refresh.call_args_list[0], refresh.call_args_list[1])
        sleep.assert_called_once_with(30)

    def test_exhausted_retries_still_fail(self):
        with patch.object(daily, 'refresh', side_effect=daily.requests.Timeout('timeout')) as refresh, \
             patch.object(daily.time, 'sleep') as sleep:
            with self.assertRaises(daily.requests.Timeout):
                daily.refresh_with_retries(Path('test'), '2026-11-11', '2026-07-14')
        self.assertEqual(refresh.call_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [30, 90])

    def test_validation_failure_is_not_retried(self):
        with patch.object(daily, 'refresh', side_effect=ValueError('mixed dates')) as refresh, \
             patch.object(daily.time, 'sleep') as sleep:
            with self.assertRaisesRegex(ValueError, 'mixed dates'):
                daily.refresh_with_retries(Path('test'), '2026-11-11', '2026-07-14')
        self.assertEqual(refresh.call_count, 1)
        sleep.assert_not_called()


def snapshot(day='2026-10-23'):
    markets = []
    for ex in sorted(daily.EXCHANGES):
        bar = {'date': day, 'contract': ex.lower() + '2701', 'close': 100}
        history = ([{**bar, 'date':'2026-10-23'}] if day>'2026-10-23' else []) + [dict(bar)]
        markets.append({'code': ex.lower(), 'exchange': ex, 'main': bar,
                        'history': history, 'ranks': [], 'analysis': {},
                        'quoteSource': {'date': day, 'url': 'https://example.com/public'}})
    return {'schema': 'domestic-v1', 'asOf': day, 'markets': markets,
            'exchangeSources': [{'date': day, 'exchange': ex} for ex in sorted(daily.EXCHANGES)]}


class PublicationTests(unittest.TestCase):
    def test_published_continuous_history_cannot_be_rebased(self):
        old=snapshot();new=snapshot('2026-10-26')
        old['markets'][0]['continuous']={'history':[{'date':'2026-10-23','close':100}],'rollovers':[],'baseDate':'2026-10-23'}
        new['markets'][0]['continuous']={'history':[{'date':'2026-10-23','close':99}],'rollovers':[],'baseDate':'2026-10-23'}
        with self.assertRaisesRegex(ValueError,'continuous history lost or rebased'):
            daily.validate_snapshot(new,'2026-10-26',old)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'scripts').mkdir()
        (self.root / 'dist').mkdir()
        self.published = self.root / 'dist/data.json'
        self.original = json.dumps(snapshot()).encode()
        self.published.write_bytes(self.original)

    def tearDown(self):
        self.temp.cleanup()

    def build(self, stage, day, start):
        candidate = snapshot(day)
        (stage / 'dist/data.json').write_text(json.dumps(candidate), encoding='utf-8')
        (stage / 'data/shfe-base.json').write_text('{}', encoding='utf-8')
        return candidate

    def refresh(self, **kwargs):
        return daily.refresh(self.root, '2026-10-26', '2026-07-01',
                             preflight=lambda *_: True, **kwargs)

    def test_success_promotes_common_date(self):
        with patch.object(daily, 'run_script'):
            result = self.refresh(builder=self.build)
        self.assertTrue(result['changed'])
        self.assertEqual(json.loads(self.published.read_bytes())['asOf'], '2026-10-26')

    def test_partial_source_failure_keeps_exact_old_bytes(self):
        def fail(stage, *_):
            (stage / 'dist/data.json').write_text('partially overwritten')
            raise RuntimeError('CZCE unavailable')
        with self.assertRaisesRegex(RuntimeError, 'CZCE'):
            self.refresh(builder=fail)
        self.assertEqual(self.published.read_bytes(), self.original)

    def test_export_failure_keeps_exact_old_bytes(self):
        with patch.object(daily, 'run_script', side_effect=RuntimeError('export failed')):
            with self.assertRaisesRegex(RuntimeError, 'export failed'):
                self.refresh(builder=self.build)
        self.assertEqual(self.published.read_bytes(), self.original)

    def test_history_download_loss_keeps_published_snapshot(self):
        def lose_history(*args):
            candidate = self.build(*args)
            candidate['markets'][0]['history'] = candidate['markets'][0]['history'][-1:]
            return candidate
        with self.assertRaisesRegex(ValueError, 'previously validated'):
            self.refresh(builder=lose_history)
        self.assertEqual(self.published.read_bytes(), self.original)

    def test_mixed_exchange_dates_are_rejected(self):
        def wrong_date(*args):
            candidate = self.build(*args)
            candidate['markets'][0]['quoteSource']['date'] = '2026-10-23'
            return candidate
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.refresh(builder=wrong_date)
        self.assertEqual(self.published.read_bytes(), self.original)

    def test_unpublished_report_skips_without_claiming_holiday(self):
        result = daily.refresh(self.root, '2026-10-26', '2026-07-01',
                               preflight=lambda *_: False,
                               builder=lambda *_: self.fail('must not build'))
        self.assertEqual(result['status'], 'no-published-report')
        self.assertEqual(result['asOf'], '2026-10-23')
        self.assertEqual(self.published.read_bytes(), self.original)

    def test_old_target_cannot_roll_back_publication(self):
        result = daily.refresh(self.root, '2026-10-22', '2026-07-01',
                               preflight=lambda *_: self.fail('must not fetch'))
        self.assertEqual(result['status'], 'up-to-date')
        self.assertEqual(self.published.read_bytes(), self.original)

    def test_same_day_rebuild_cannot_erase_known_rankings(self):
        previous = snapshot()
        previous['markets'][0]['ranks'] = [{'rank': 1, 'long': 10, 'short': 8}]
        with self.assertRaisesRegex(ValueError, 'same-day rankings'):
            daily.validate_snapshot(snapshot(), previous['asOf'], previous)

    def test_invalid_data_and_coverage_regression(self):
        good = snapshot()
        mutations = [lambda x: x['markets'].pop(),
                     lambda x: x['markets'][0]['history'][0].update(contract='other2701'),
                     lambda x: x['markets'][0]['history'][0].update(date='2027-01-01'),
                     lambda x: x['markets'][0]['main'].update(close=float('nan'))]
        for mutate in mutations:
            value = copy.deepcopy(good)
            mutate(value)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                daily.validate_snapshot(value, value['asOf'], good)
        prior = copy.deepcopy(good)
        prior['markets'].extend([dict(good['markets'][0])] * 4)
        with self.assertRaisesRegex(ValueError, 'coverage fell'):
            daily.validate_snapshot(good, good['asOf'], prior)

    def test_shanghai_date_selection_and_future_guard(self):
        friday = dt.datetime(2026, 10, 23, 14, tzinfo=daily.SHANGHAI)
        self.assertEqual(daily.target_day(friday).isoformat(), '2026-10-22')
        sunday = dt.datetime(2026, 10, 25, 20, tzinfo=daily.SHANGHAI)
        self.assertEqual(daily.target_day(sunday).isoformat(), '2026-10-23')
        with self.assertRaises(ValueError):
            daily.target_day(friday, '2026-10-23')


if __name__ == '__main__':
    unittest.main()
