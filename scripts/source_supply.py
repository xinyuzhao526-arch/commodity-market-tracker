"""Auto-discover official domestic production and CASDE balance sheets.

No monthly cumulative values are differenced to invent monthly production.
Missing January/February observations stay missing. Publication dates which the
NBS data API does not expose stay unknown (the collection date is separate).
"""
import calendar
import concurrent.futures
import datetime as dt
import hashlib
import json
import re
import urllib.parse
from bs4 import BeautifulSoup
from source_live_fundamentals import http_raw, grid, number

NBS_BASE='https://data.stats.gov.cn/dg/website/publicrelease/web/external/'
NBS_PAGE='https://data.stats.gov.cn/dg/website/page.html#/pc/national/monthData'
PRODUCTS={
 '精炼铜（电解铜）':({'cu':'品种产量','bc':'国内精铜产量'},'供应'),
 '铜材':({'cu':'下游加工产量','bc':'下游加工产量'},'需求关联'),
 '原铝（电解铝）':({'al':'品种产量','ao':'下游生产代理'},'供应/需求关联'),
 '铝材':({'al':'下游加工产量'},'需求关联'),
 '铝合金':({'ad':'铝合金合计，非铸造铝合金单品'},'供应关联'),
 '氧化铝':({'ao':'品种产量'},'供应'),
 '铅':({'pb':'品种产量'},'供应'),
 '锌':({'zn':'品种产量'},'供应'),
 '铁矿石原矿':({'i':'国内原矿，不是铁金属量或进口矿'},'供应关联'),
 '生铁':({'i':'下游生产代理','j':'下游生产代理','jm':'产业链需求代理'},'需求关联'),
 '粗钢':({'ss':'钢铁行业总量，非不锈钢产量','sf':'下游生产代理','sm':'下游生产代理','ni':'钢铁行业背景，非不锈钢单品'},'行业关联'),
 '钢筋':({'rb':'钢筋统计口径，非期货交割规格'},'供应关联'),
 '线材（盘条）':({'wr':'线材统计口径，非期货交割规格'},'供应关联'),
 '中厚宽钢带':({'hc':'关联产品产量，非热卷表观消费'},'供应关联'),
 '铁合金':({'sf':'合金合计，非硅铁单品','sm':'合金合计，非锰硅单品'},'供应关联'),
 '饲料':({'m':'下游加工代理','b':'产业链需求代理','rm':'下游加工代理'},'需求关联'),
 '精制食用植物油':({'y':'植物油加工合计，非豆油单品','oi':'植物油加工合计，非菜油单品','p':'植物油加工合计，非棕榈油消费','pk':'下游加工关联，非花生压榨量'},'产业链关联'),
 '锂离子电池':({'lc':'下游生产代理'},'需求关联'),
 '太阳能电池（光伏电池）':({'si':'终端生产代理','ps':'终端生产代理','ag':'终端生产代理'},'需求关联'),
 '汽车':({'pt':'终端生产代理，需区分燃油/新能源','pd':'终端生产代理，需区分燃油/新能源'},'需求关联')}
PRODUCTS['新能源汽车']=({'lc':'终端生产代理，非锂盐实际采购'},'需求关联')


def cached_json(root,key,url,method='GET',params=None,body=None):
    cache=root/'data/raw/fundamentals';cache.mkdir(parents=True,exist_ok=True)
    path=cache/(key+'.json')
    if path.exists():return json.loads(path.read_text(encoding='utf-8'))
    doc=json.loads(http_raw(url,method,params=params,body=body))
    if doc.get('success') is not True:raise ValueError('NBS unsuccessful response')
    path.write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
    return doc


def nbs_tree(root,pid,check_day):
    return cached_json(root,'nbs-tree-'+(pid or 'root')+'-'+check_day,NBS_BASE+'new/queryIndexTreeAsync',params={'pid':pid,'code':1})['data']


def parse_nbs(doc, indicators, product, links, as_of):
    if doc.get('success') is not True:raise ValueError('NBS data failure')
    # Select names AND metadata, rather than trusting arbitrary series order.
    matches=lambda x:re.sub(r'\s+','',x.get('i_showname','')).startswith(product+'产量')
    monthly=[x for x in indicators if str(x.get('dp'))=='1' and matches(x)]
    yoy=[x for x in indicators if str(x.get('dp'))=='11' and matches(x)]
    if len(monthly)!=1 or len(yoy)!=1:raise ValueError('ambiguous NBS monthly/yoy indicator')
    item,yi=monthly[0],yoy[0];unit=item.get('du_name')
    if not unit or not re.fullmatch(r'[\u4e00-\u9fff%/]+',unit):raise ValueError('unknown NBS unit')
    history=[];seen=set()
    for p in doc.get('data',[]):
        code=p.get('code','')
        if not re.fullmatch(r'20\d{4}MM',code):raise ValueError('not an NBS monthly period')
        year,month=int(code[:4]),int(code[4:6]);date=f'{year:04d}-{month:02d}-{calendar.monthrange(year,month)[1]:02d}'
        if date>as_of:raise ValueError('future NBS period')
        vals={}
        for v in p.get('values',[]):
            if v['_id'] in vals:raise ValueError('duplicate NBS indicator')
            if v.get('da')!='000000000000':raise ValueError('not nationwide NBS data')
            vals[v['_id']]=v
        v=vals.get(item['_id'])
        if not v or v.get('value') in {None,'','--','…','...'}:continue
        if v.get('du_name')!=unit or str(v.get('dp'))!='1':raise ValueError('NBS unit/aggregation mismatch')
        if date in seen:raise ValueError('duplicate NBS monthly point')
        seen.add(date)
        y=vals.get(yi['_id'],{}).get('value')
        history.append({'date':date,'period':p['name'],'value':number(v['value']),'yoy':None if y in {None,'','--','…','...'} else number(y,True),'publishedAt':None,'sourceUrl':NBS_PAGE})
    if not history:raise ValueError('no valid NBS monthly observations')
    return {'id':'NBS:'+product,'provider':'国家统计局官方','label':product+'产量','unit':unit,'frequency':'monthly','kind':'实际统计',
            'scope':'全国规模以上工业；月度当期值','appliesTo':links,'sourceUrl':NBS_PAGE,'history':sorted(history,key=lambda p:p['date']),
            'note':'统计期末日期用于排序，不是发布日期；接口未给出发布日期。1—2月合并统计不拆分，缺值不补零；终端或加工产量不能等同于原料消费。'}


def fetch_nbs(root,as_of):
    end=dt.date.fromisoformat(as_of);check_day=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
    # Dated cache rechecks metadata and current monthly observations next day.
    roots=nbs_tree(root,'',check_day);root_id=next(x['_id'] for x in roots if x['name']=='月度数据')
    industrial=next(x['_id'] for x in nbs_tree(root,root_id,check_day) if x['name']=='工业')
    product_parent=next(x['_id'] for x in nbs_tree(root,industrial,check_day) if x['name']=='工业主要产品产量')
    catalogs={x['name']:x['_id'] for x in nbs_tree(root,product_parent,check_day)}
    # Last 12 completed months; the API leaves unpublished months blank.
    dts=[]
    serial=end.year*12+end.month-2
    for i in range(12):
        year,zero=divmod(serial-i,12);dts.append(f'{year:04d}{zero+1:02d}MM')
    def one(product):
        try:
            cid=catalogs[product]
            indicators=cached_json(root,'nbs-indicators-'+cid+'-'+check_day,NBS_BASE+'new/queryIndicatorsByCid',params={'cid':cid,'dt':'','name':''})['data']['list']
            chosen=[i for i in indicators if str(i.get('dp')) in {'1','11'}]
            body={'cid':cid,'rootId':root_id,'indicatorIds':[x['_id'] for x in chosen],'daCatalogId':'','das':[{'text':'全国','value':'000000000000'}],'showType':'1','dts':dts}
            key=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()[:18]
            doc=cached_json(root,'nbs-data-'+check_day+'-'+key,NBS_BASE+'stream/esData','POST',body=body)
            return parse_nbs(doc,indicators,product,PRODUCTS[product][0],as_of),None
        except Exception as e:return None,f'{product}: {type(e).__name__}: {str(e)[:130]}'
    out,errors=[],[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for s,e in pool.map(one,PRODUCTS):
            if s:out.append(s)
            if e:errors.append(e)
    return out,{'source':'nbs-production','status':'ok' if not errors else 'partial' if out else 'failed','errors':errors}


def parse_casde(raw,url,as_of):
    soup=BeautifulSoup(raw.decode('utf-8'),'html.parser')
    title=soup.find('h1')
    text=soup.get_text(' ',strip=True)
    match=re.search(r'日期[：:]\s*(20\d{2}-\d{2}-\d{2})',text)
    if not match or not title or '供需形势分析' not in title.get_text():raise ValueError('invalid CASDE article')
    published=match[1]
    if published>as_of:raise ValueError('CASDE not published as of target')
    out=[]
    for table in soup.find_all('table'):
        txt=table.get_text('',strip=True)
        soybean='压榨消费' in txt and '国产大豆' in txt
        oils='花生油' in txt and '棕榈油' in txt
        if not soybean and not oils:continue
        rows=[row for _,row in grid(table)]
        header=rows[0]
        if len(header)<3 or '预测' not in header[-1]:raise ValueError('CASDE unknown latest column')
        vintage=re.sub(r'\s+','',header[-1]);previous_vintage=re.sub(r'\s+','',header[-2])
        selected={'产量':('中国大豆产量',{'a':'年度国产豆预测'}),'进口':('中国大豆进口',{'b':'年度原料进口预测','m':'原料进口预测','y':'原料进口预测'}),'压榨消费':('中国大豆压榨消费',{'b':'年度压榨预测','m':'原料压榨预测','y':'原料压榨预测'}),'食用消费':('中国大豆食用消费',{'a':'年度食用需求预测'})} if soybean else {}
        oil_stage='生产'
        for row in rows[1:]:
            if len(row)<3:continue
            label=re.sub(r'\s+','',row[0]).replace('其中：','')
            if oils and label in {'进口','国内消费','生产'}:oil_stage=label
            if oils:
                if label=='豆油' and oil_stage=='生产':selected[label]=('中国豆油产量',{'y':'年度产量预测'})
                elif label=='菜籽油' and oil_stage=='生产':selected[label]=('中国菜籽油产量',{'oi':'年度产量预测','rs':'关联产品，非菜籽产量','rm':'关联产品，非菜粕产量'})
                elif label=='花生油' and oil_stage=='生产':selected[label]=('中国花生油产量',{'pk':'下游关联，非花生产量'})
                elif label=='棕榈油' and oil_stage=='进口':selected[label]=('中国棕榈油进口',{'p':'年度进口预测'})
                elif label=='国内消费':selected[label]=('中国植物油消费',{'y':'植物油合计，非单品消费','oi':'植物油合计，非单品消费','p':'植物油合计，非单品消费'})
                else:continue
            if label not in selected:continue
            name,applies=selected[label];value=number(row[-1]);prior=number(row[-2])
            if oils and name=='中国豆油产量' and oil_stage!='生产':continue
            out.append({'id':'CASDE:'+name,'provider':'农业农村部官方','label':name,'unit':'万吨','frequency':'report','kind':'年度预测','scope':vintage,
                        'appliesTo':applies,'sourceUrl':url,'note':'农业市场年度预测，不是当月实绩；前值为上一报告对同一市场年度的预测，不是上年实际值。',
                        'history':[{'date':published,'publishedAt':published,'period':vintage,'value':value,'previous':prior,'previousPeriod':previous_vintage,'revision':value-prior,'sourceUrl':url}]})
    if len(out)!=9:raise ValueError('CASDE expected 9 explicitly selected balance-sheet rows')
    return out


def fetch_casde(root,as_of):
    base='https://scs.moa.gov.cn/jcyj/'
    soup=BeautifulSoup(http_raw(base).decode('utf-8'),'html.parser')
    links=[]
    for a in soup.find_all('a',href=True):
        if '中国农产品供需形势分析' not in a.get_text():continue
        u=urllib.parse.urljoin(base,a['href']);m=re.search(r'/t(20\d{6})_',u)
        if m:
            d=m[1];day=f'{d[:4]}-{d[4:6]}-{d[6:]}'
            if day<=as_of:links.append((day,u))
    if not links:raise ValueError('no published CASDE article in directory')
    _,url=max(links)
    raw=http_raw(url);out=parse_casde(raw,url,as_of)
    cache=root/'data/raw/fundamentals';cache.mkdir(parents=True,exist_ok=True)
    (cache/('casde-'+out[0]['history'][0]['date']+'.html')).write_bytes(raw)
    return out,{'source':'casde','status':'ok','latest':out[0]['history'][0]['date'],'url':url}


def refresh_supplies(root,as_of,previous):
    merged={s['id']:s for s in previous};statuses=[]
    for fetcher,name in [(fetch_nbs,'nbs-production'),(fetch_casde,'casde')]:
        try:
            series,status=fetcher(root,as_of);statuses.append(status)
            for s in series:
                old=merged.get(s['id']);points={p['date']:p for p in old['history']} if old else {}
                if old and (old['unit']!=s['unit'] or old['scope']!=s['scope']) and name!='casde':raise ValueError('supply series unit/scope changed')
                # Different market-year forecasts are not a continuous quantity series.
                if name=='casde' and old and old['scope'][:7]!=s['scope'][:7]:points={}
                points.update({p['date']:p for p in s['history']});merged[s['id']]={**s,'history':[points[k] for k in sorted(points) if k<=as_of][-180:]}
        except Exception as e:statuses.append({'source':name,'status':'failed','error':f'{type(e).__name__}: {str(e)[:180]}'})
    return list(merged.values()),statuses
