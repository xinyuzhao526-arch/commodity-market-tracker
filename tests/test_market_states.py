import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from analyze_markets import describe_market_state


class MarketStatesTest(unittest.TestCase):
    def state(self, trend=-1, daily=1, oi=-10, **extra):
        return describe_market_state(dict(trendDirection=trend, seatDifference=10, seatDeltaDifference=1, **extra),
                                     dict(return1=daily, fixedOiChange=oi))

    def test_direction_and_daily_move_are_separate(self):
        for trend, daily, phase in [(-1, 1, '偏空中的反弹'), (-1, -1, '偏空同向下行'),
                                    (1, -1, '偏多中的回落'), (1, 1, '偏多同向上涨'),
                                    (0, 1, '均线分化·当日上涨'), (0, -1, '均线分化·当日下跌')]:
            with self.subTest(trend=trend, daily=daily):
                self.assertEqual(self.state(trend, daily)['phase'], phase)

    def test_zero_and_missing_are_not_conflated(self):
        zero = self.state(daily=0, oi=0)
        self.assertEqual(zero['phase'], '当日持平')
        self.assertEqual(zero['position'], '持仓持平')
        missing = self.state(daily=None, oi=None)
        self.assertEqual(missing['phase'], '当日涨跌缺失')
        self.assertEqual(len(missing['missing']), 2)
        self.assertEqual(self.state(trend=None)['phase'], '趋势样本不足')

    def test_seat_checks_do_not_change_price_phase(self):
        base = self.state()
        checked = self.state(seatTrendConflict=True, seatMarginalConflict=True, liquidity={'low': True})
        self.assertEqual(checked['phase'], base['phase'])
        self.assertEqual(len(checked['checks']), 3)
        self.assertFalse(checked['strictAlignment'])
        self.assertTrue(self.state(status='多维同向')['strictAlignment'])

    def test_missing_seats_do_not_remove_known_trend(self):
        state = describe_market_state({'trendDirection': 1}, {'return1': 1, 'fixedOiChange': 1})
        self.assertEqual(state['trend'], '均线偏多')
        self.assertEqual(state['missing'], ['席位样本缺失'])

    def test_seat_delta_missing_is_disclosed_separately(self):
        state = describe_market_state({'trendDirection': 1, 'seatDifference': 0},
                                      {'return1': 1, 'fixedOiChange': 1})
        self.assertEqual(state['missing'], ['席位增减项缺失'])
