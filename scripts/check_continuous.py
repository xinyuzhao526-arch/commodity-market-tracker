"""Verify published adjustment arithmetic and preservation of actual quantities."""
import json,math
from pathlib import Path
from continuous_prices import SCHEMA,positive,delivery

def validate(data):
    ready=0
    for m in data['markets']:
        c=m.get('continuous')
        if not c:continue
        assert c['schema']==SCHEMA,m['code']
        points=c['history'];dates=[p['date'] for p in points]
        assert dates==sorted(set(dates)) and all(d<=data['asOf'] for d in dates)
        for p in points:
            assert positive(p['factor']) and all(positive(p[k]) for k in ('open','high','low','close','rawClose'))
            assert p['low']<=min(p['open'],p['close'])<=max(p['open'],p['close'])<=p['high']
            assert math.isclose(p['close'],p['rawClose']*p['factor'],rel_tol=1e-12)
            assert p.get('sourceUrl') and not any(k in p for k in ('oi','volume','turnover'))
            assert p['selectionDate']<p['date'] or p['date']==c['baseDate']
        if points:
            assert points[0]['date']==c['baseDate'] and points[0]['factor']==1
            assert points[0]['close']==c['basePrice']
        for r in c['rollovers']:
            assert r['comparisonDate']<r['date']<=data['asOf']
            assert delivery(r['to'],r['date'])>delivery(r['from'],r['date'])
            assert r['newOi']>r['oldOi']*1.1
            assert math.isclose(r['factorAfter'],r['factorBefore']*r['oldClose']/r['newClose'],rel_tol=1e-12)
        if c['status']=='ready':
            assert points[-1]['date']==data['asOf'];ready+=1
        if 'fixedAnalysis' in m:
            assert m['analysis']['fixedOiChange']==m['fixedAnalysis']['fixedOiChange']
            assert m['analysis']['oiReturn5']==m['fixedAnalysis']['oiReturn5']
            assert m['analysis']['seatDifference']==m['fixedAnalysis']['seatDifference']
            if not m['analysis']['priceBasis']['available']:assert m['analysis']['return20'] is None
    return ready

if __name__=='__main__':
    data=json.loads((Path(__file__).resolve().parents[1]/'dist/data.json').read_text(encoding='utf-8'))
    print(json.dumps({'status':'PASS','continuousCurrent':validate(data),'markets':len(data['markets'])}))
