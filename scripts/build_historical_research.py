"""Build a small public aggregate from local research outputs, not raw Parquet."""
import argparse,csv,json,statistics,collections
from pathlib import Path

def build(folder):
    source=json.loads((folder/'分析结果.json').read_text(encoding='utf-8'))
    groups=collections.defaultdict(list)
    with (folder/'偏离事件样本.csv').open(encoding='utf-8-sig',newline='') as handle:
        for row in csv.DictReader(handle):groups[(row['code'],row['side'],row['period'])].append(row)
    events=[]
    for (code,side,period),rows in sorted(groups.items()):
        for n in (5,10,20):
            values=[float(r[f'fwd{n}']) for r in rows]
            events.append(dict(code=code,side=side,period=period,horizon=n,count=len(values),
                median=statistics.median(values),positivePct=sum(v>0 for v in values)/len(values)*100,
                meanMaxDown=statistics.mean(float(r[f'maxDown{n}']) for r in rows),
                meanMaxUp=statistics.mean(float(r[f'maxUp{n}']) for r in rows)))
    metrics={m['code']:m for m in source['metrics']}
    return dict(schema='historical-research-v1',asOf=source['asOf'],
                source='用户提供的Parquet商品日线 / 独立历史研究版本',
                method='T−1持仓选择，远月超过1.1倍才换月，比例后复权；缺桥接分段，不跨段计算。',
                percentileWindow=1260,minimumObservations=252,eventThresholdAtr=2,
                eventSpacing=21,minimumVolumeOi=1000,
                products=metrics,events=events,notes=source['notes'])

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path)
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'dist/historical-research.json')
    args=parser.parse_args();data=build(args.folder)
    args.output.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
    print(json.dumps({'asOf':data['asOf'],'products':len(data['products']),'eventGroups':len(data['events'])}))
