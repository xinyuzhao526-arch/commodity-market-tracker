"""Validate published physical and supply series, without network requests."""
import datetime as dt
import json
from pathlib import Path
from source_live_fundamentals import number, valid_day, CODES

ROOT=Path(__file__).resolve().parents[1]


def validate(packet):
    assert packet['schema']=='fundamentals-v1'
    target=valid_day(packet['asOf']);seen=set()
    for s in packet['inventories']:
        assert s['id'] not in seen;seen.add(s['id'])
        assert s['code'] in CODES and s['metric'] in {'stock','receipt'}
        assert s['unit'] in {'吨','千克','手','张','接口计数'}
        assert s['provider'] and s['scope'] and s['sourceUrl'].startswith(('http://','https://'))
        dates=[]
        for p in s['history']:
            dates.append(valid_day(p['date']));assert p['date']<=target
            value=number(p['value']);change=number(p['change'],True)
            assert value-change>=-0.001
            if p.get('previous') is not None:assert abs(value-number(p['previous'])-change)<0.001
            assert p['sourceUrl'].startswith(('http://','https://'))
        assert dates and dates==sorted(set(dates))
    seen=set()
    for s in packet['supplies']:
        assert s['id'] not in seen;seen.add(s['id'])
        assert s['appliesTo'] and set(s['appliesTo'])<=CODES
        assert s['kind'] in {'实际统计','年度预测'} and s['unit']
        dates=[]
        for p in s['history']:
            dates.append(valid_day(p['date']));assert p['date']<=target
            number(p['value'])
            if p.get('yoy') is not None:number(p['yoy'],True)
            if p.get('revision') is not None:assert abs(p['value']-p['previous']-p['revision'])<.001
            assert p['publishedAt'] is None or valid_day(p['publishedAt'])<=target
        assert dates and dates==sorted(set(dates))
    assert packet['statuses']


if __name__=='__main__':
    p=json.loads((ROOT/'dist/fundamentals.json').read_text(encoding='utf-8'));validate(p)
    print(json.dumps({'status':'PASS','inventoryProducts':len({s['code'] for s in p['inventories']}),'inventorySeries':len(p['inventories']),
                      'supplyProducts':len({c for s in p['supplies'] for c in s['appliesTo']}),'supplySeries':len(p['supplies'])}))
