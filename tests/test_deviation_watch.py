"""Verify symmetric deviation screens without hindsight or seat dependence."""
import copy
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from analyze_markets import derive, deviation_watch


class DeviationWatchTest(unittest.TestCase):
    def market(self, prices):
        days=[(dt.date(2026,1,1)+dt.timedelta(days=i)).isoformat() for i in range(len(prices))]
        hist=[dict(date=d,contract='x2606',close=p,high=p+1,low=p-1,volume=100,oi=1000+i)
              for i,(d,p) in enumerate(zip(days,prices))]
        return dict(code='x',sector='test',main=hist[-1],history=hist,ranks=[]),days

    def test_above_and_below_have_symmetric_distance_and_different_focus(self):
        high,days=self.market([100]*24+[140])
        low,_=self.market([100]*24+[60])
        a,b=derive(high,days),derive(low,days)
        # MA20=102/98 and ATR=(13*2+41)/14=67/14 respectively.
        self.assertAlmostEqual(a['distanceAtr20'],38/(67/14))
        self.assertAlmostEqual(b['distanceAtr20'],-38/(67/14))
        self.assertEqual(a['deviationWatch']['side'],'above')
        self.assertEqual(b['deviationWatch']['side'],'below')
        self.assertEqual(a['deviationWatch']['focus'],'关注回调风险')
        self.assertEqual(b['deviationWatch']['focus'],'关注反弹可能')
        self.assertFalse(a['deviationWatch']['retracing'])
        self.assertFalse(b['deviationWatch']['retracing'])
        self.assertIsNone(a['seatDifference'])

    def test_day_retrace_is_not_a_trend_reversal(self):
        m,days=self.market([100]*23+[150,140])
        m['main']['high']=152
        a=derive(m,days)
        self.assertEqual(a['trendDirection'],1)
        self.assertTrue(a['deviationWatch']['retracing'])
        self.assertTrue(a['deviationWatch']['rangeReentry'])
        self.assertEqual(a['deviationWatch']['priceCue'],'当日回落')
        m,days=self.market([100]*23+[50,60])
        m['main']['low']=48
        b=derive(m,days)
        self.assertEqual(b['trendDirection'],-1)
        self.assertTrue(b['deviationWatch']['retracing'])
        self.assertTrue(b['deviationWatch']['rangeReentry'])
        self.assertEqual(b['deviationWatch']['priceCue'],'当日反弹')

    def test_missing_or_zero_range_is_unavailable(self):
        m,days=self.market([100]*24+[140])
        m['history'].pop(-2)
        a=derive(m,days)
        self.assertIsNone(a['distanceAtr20'])
        self.assertIsNone(a['deviationWatch'])
        m,days=self.market([100]*25)
        for bar in m['history']:bar.update(high=100,low=100)
        a=derive(m,days)
        self.assertEqual(a['atr14'],0)
        self.assertIsNone(a['deviationWatch'])

    def test_threshold_is_symmetric_and_future_bars_do_not_change_screen(self):
        for distance, included in [(-2,True),(-1.999,False),(1.999,False),(2,True)]:
            self.assertEqual(deviation_watch({'distanceAtr20':distance},None) is not None,included)
        # Modest deviation amid wide trading ranges stays below the gate.
        for direction in (1,-1):
            m,days=self.market([100]*24+[100+direction*4])
            for bar in m['history']:bar.update(high=bar['close']+5,low=bar['close']-5)
            self.assertIsNone(derive(m,days)['deviationWatch'])
        m,days=self.market([100]*24+[140])
        a=derive(m,days)
        future=copy.deepcopy(m['main']);future.update(date='2027-01-01',close=1,high=2,low=0)
        m['history'].append(future)
        self.assertEqual(derive(m,days+['2027-01-01'])['deviationWatch'],a['deviationWatch'])

    def test_repair_retained_after_threshold_and_expires_after_five_sessions(self):
        m,days=self.market([100]*24+[60]+[95]*6)
        m['main']=m['history'][25]
        a=derive(m,days)
        self.assertIsNone(a['deviationWatch'])
        e=a['deviationEpisode']
        self.assertEqual(e['firstAt'],days[24])
        self.assertEqual(e['peakAt'],days[24])
        self.assertEqual(e['phase'],'阈值内修复')
        self.assertEqual(e['sessionsAfterHit'],1)
        self.assertGreater(e['gapContractionPct'],80)
        # Future rows are already present but must not affect the past episode.
        prefix=copy.deepcopy(m);prefix['history']=prefix['history'][:26]
        self.assertEqual(derive(prefix,days[:26])['deviationEpisode'],e)
        m['main']=m['history'][29]
        self.assertIsNotNone(derive(m,days)['deviationEpisode'])
        m['main']=m['history'][30]
        self.assertIsNone(derive(m,days)['deviationEpisode'])

    def test_repair_is_symmetric_and_atr_expansion_is_not_price_recovery(self):
        m,days=self.market([100]*24+[140,105])
        a=derive(m,days)
        self.assertEqual(a['deviationEpisode']['side'],'above')
        self.assertEqual(a['deviationEpisode']['phase'],'阈值内修复')
        m,days=self.market([100]*24+[60,60])
        m['history'][-1].update(high=300,low=1)
        a=derive(m,days)
        self.assertIsNone(a['deviationWatch'])
        # ATR has ballooned, but the price/MA gap has barely contracted.
        self.assertLess(a['deviationEpisode']['gapContractionPct'],10)
        self.assertFalse(a['deviationEpisode']['retracing'])

    def test_missing_history_breaks_episode_and_liquidity_is_separate(self):
        m,days=self.market([100]*24+[60,95])
        m['history'].pop(-2)
        a=derive(m,days)
        self.assertIsNone(a['deviationEpisode'])
        self.assertTrue(a['liquidity']['low'])
        m,days=self.market([100]*24+[60,95])
        m['main']['volume']=2000;m['main']['oi']=2000
        self.assertFalse(derive(m,days)['liquidity']['low'])


if __name__=='__main__':unittest.main()
