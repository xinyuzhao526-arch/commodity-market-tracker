import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from continuous_prices import construct,delivery
from analyze_markets import analyze,derive

def bar(contract,close,oi):return {'contract':contract,'open':close,'high':close+1,'low':close-1,'close':close,'volume':100,'oi':oi,'sourceUrl':'https://example.com/official'}

class ContinuousTests(unittest.TestCase):
    def setUp(self):
        self.days=['2026-01-05','2026-01-06','2026-01-07']
        self.frames={d:{'x2605':bar('x2605',p,100),'x2609':bar('x2609',q,oi)} for d,p,q,oi in zip(self.days,[100,101,102],[200,204,208],[90,120,130])}
    def test_lagged_selection_ratio_and_no_artificial_roll_return(self):
        c=construct(self.frames,self.days,self.days[-1]);p=c['history'];r=c['rollovers'][0]
        self.assertEqual([x['contract'] for x in p],['x2605','x2605','x2609'])
        self.assertAlmostEqual(r['factorAfter'],101/204)
        self.assertAlmostEqual(p[-1]['close']/p[-2]['close']-1,208/204-1)
        self.assertNotIn('volume',p[-1]);self.assertEqual(p[0]['factor'],1)
    def test_append_is_identical_to_full_build_and_does_not_rebase(self):
        old=construct(self.frames,self.days,self.days[1]);saved=copy.deepcopy(old)
        c=construct(self.frames,self.days,self.days[-1],old)
        self.assertEqual(old,saved);self.assertEqual(c['history'][:2],old['history'])
        self.assertEqual(c,construct(self.frames,self.days,self.days[-1]))
    def test_future_prices_and_oi_do_not_rewrite_past_points(self):
        old=construct(self.frames,self.days,self.days[1]);self.frames[self.days[-1]]['x2609'].update(close=9999,oi=999999)
        self.assertEqual(old,construct(self.frames,self.days,self.days[1]))
    def test_missing_bridge_stops_without_zero_or_rebase(self):
        self.frames[self.days[1]]['x2609']['close']=None
        c=construct(self.frames,self.days,self.days[-1]);self.assertEqual(c['status'],'stale')
        self.assertEqual(len(c['history']),2);self.assertFalse(c['rollovers'])
    def test_missing_session_and_backwards_roll_are_rejected(self):
        del self.frames[self.days[1]]
        c=construct(self.frames,self.days,self.days[-1]);self.assertEqual(len(c['history']),1)
        with self.assertRaises(ValueError):construct(self.frames,self.days,self.days[0],{'schema':'bad','history':[]})
    def test_czce_year_and_bad_month(self):
        self.assertEqual(delivery('oi701','2026-11-04'),2027*12+1)
        self.assertIsNone(delivery('oi700','2026-11-04'))

    def test_research_prices_do_not_adjust_real_contract_quantities(self):
        import datetime as dt
        days=[(dt.date(2026,1,1)+dt.timedelta(days=i)).isoformat() for i in range(25)]
        history=[{'date':d,'contract':'x2605','close':100-i,'open':100-i,'high':101-i,'low':99-i,'volume':5000,'oi':1000+i} for i,d in enumerate(days)]
        m={'code':'x','sector':'test','exchange':'SHFE','main':history[-1],'history':history,'ranks':[]}
        original=copy.deepcopy(m)
        points=[{'date':d,'contract':'x2609','factor':.5,'open':100+i,'high':101+i,'low':99+i,'close':100+i} for i,d in enumerate(days)]
        m['continuous']={'status':'ready','history':points,'rollovers':[],'baseDate':days[0],'latest':days[-1],'provider':'test'}
        a=analyze({'asOf':days[-1],'markets':[m]})['markets'][0]
        self.assertGreater(a['analysis']['return20'],0)
        self.assertLess(a['fixedAnalysis']['return20'],0)
        self.assertEqual(a['analysis']['oiReturn5'],derive(original,days)['oiReturn5'])
        self.assertEqual(a['history'],original['history'])
        m['continuous']['status']='stale'
        a=analyze({'asOf':days[-1],'markets':[m]})['markets'][0]
        self.assertIsNone(a['analysis']['return20'])
        self.assertIsNone(a['analysis']['trendDirection'])

if __name__=='__main__':unittest.main()
