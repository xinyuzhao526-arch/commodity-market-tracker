"""Boundary tests for financial data parsing and last-good preservation."""
import json
from pathlib import Path
import sys
import unittest
from io import BytesIO
import openpyxl

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from source_live_fundamentals import parse_shfe, parse_gfex, parse_czce, em_rows, merge_series, number
from source_supply import parse_nbs, parse_casde


class InventoryTests(unittest.TestCase):
    def shfe_html(self,day='2026-11-03'):
        # Synthetic test-only values. Leaf+subtotal+grand total must not be added.
        tables=[]
        for name in ['铜','铝','锌','铅','镍','锡','黄金','白银']:
            tables.append(f'<table><tr class="special_row_type"><td colspan="4">{name} 单位：吨</td></tr><tr><th>地区</th><th>仓库</th><th>期货</th><th>增减</th></tr><tr><td>A</td><td>仓库A</td><td>10</td><td>2</td></tr><tr><td colspan="2">合计</td><td>10</td><td>2</td></tr><tr><td colspan="2">非保税商品总计</td><td>10</td><td>2</td></tr><tr><td colspan="2">总计</td><td>10</td><td>2</td></tr></table>')
        return (day+''.join(tables)).encode()

    def test_official_totals_not_double_counted(self):
        rows=parse_shfe(self.shfe_html(),'2026-11-03','https://example.org/report')
        self.assertEqual(len(rows),8)
        self.assertTrue(all(s['history'][0]['value']==10 for s in rows))
        with self.assertRaises(ValueError):parse_shfe(self.shfe_html(),'2026-11-02','https://example.org/report')

    def test_gfex_excludes_subtotals_and_checks_arithmetic(self):
        d={'code':'0','param':{'gen_date':['20261103']},'data':[]}
        for c in ['si','lc','ps']:
            d['data'] += [{'varietyOrder':c,'whAbbr':'A','lastWbillQty':8,'wbillQty':10,'diff':2}, {'varietyOrder':c,'whAbbr':'','lastWbillQty':8,'wbillQty':10,'diff':2}]
        rows=parse_gfex(json.dumps(d).encode(),'2026-11-03','http://example.org')
        self.assertTrue(all(s['history'][0]['value']==10 for s in rows))
        d['data'][0]['diff']=3
        with self.assertRaises(ValueError):parse_gfex(json.dumps(d).encode(),'2026-11-03','http://example.org')

    def test_czce_forecast_is_not_receipt_and_zero_is_valid(self):
        w=openpyxl.Workbook();s=w.active;s.append(['仓单日报(2026-11-03)'])
        for c in ['RM','OI','RS','PK','SF','SM']:
            for forecast,value in [(True,999),(False,0)]:
                s.append([f'品种：测试{c} 单位：张 日期：2026-11-03 每张'+('预报' if forecast else '仓单')+'=5吨'])
                s.append(['仓库编号','仓库','仓单数量','当日增减']);s.append(['总计',None,value,0])
        raw=BytesIO();w.save(raw)
        rows=parse_czce(raw.getvalue(),'2026-11-03','https://example.org')
        self.assertEqual(len(rows),6);self.assertTrue(all(s['history'][0]['value']==0 for s in rows))

    def test_fallback_isolated_by_exchange_unit_and_date(self):
        r={'SECURITY_CODE':'M','TRADE_MARKET_CODE':'069001007','TRADE_DATE':'2026-11-03 00:00:00','UNIT':'手','ON_WARRANT_NUM':0,'ADDCHANGE':-5}
        doc={'success':True,'result':{'data':[r]}}
        series=em_rows(doc,'m','DCE','2026-11-03');self.assertEqual(series['history'][0]['value'],0)
        for field,value in [('SECURITY_CODE','Y'),('TRADE_MARKET_CODE','069001005'),('UNIT','未知'),('TRADE_DATE','2026-11-04')]:
            bad=json.loads(json.dumps(doc));bad['result']['data'][0][field]=value
            with self.assertRaises(ValueError):em_rows(bad,'m','DCE','2026-11-03')
        dup=json.loads(json.dumps(doc));dup['result']['data']*=2
        with self.assertRaises(ValueError):em_rows(dup,'m','DCE','2026-11-03')

    def test_failed_fetch_preserves_prior_and_rejects_mixed_units(self):
        s=em_rows({'success':True,'result':{'data':[{'SECURITY_CODE':'M','TRADE_MARKET_CODE':'069001007','TRADE_DATE':'2026-11-03','UNIT':'手','ON_WARRANT_NUM':10,'ADDCHANGE':2}]}},'m','DCE','2026-11-03')
        self.assertEqual(merge_series([s],[],'2026-11-03'),[s])
        bad={**s,'unit':'吨'}
        with self.assertRaises(ValueError):merge_series([s],[bad],'2026-11-03')
        for v in [None,True,'--',float('nan'),-1]:
            with self.assertRaises(ValueError):number(v)


class SupplyTests(unittest.TestCase):
    def test_nbs_current_and_yoy_only_no_cumulative_substitution(self):
        indicators=[{'_id':'current','dp':'1','du_name':'万吨','i_showname':'精炼铜（电解铜）产量当期值 (万吨)'},{'_id':'yoy','dp':'11','du_name':'%','i_showname':'精炼铜（电解铜）产量同比增长 (%)'}]
        values=[{'_id':'current','dp':'1','du_name':'万吨','da':'000000000000','value':'126.0'},{'_id':'yoy','dp':'11','du_name':'%','da':'000000000000','value':'1.1'}]
        doc={'success':True,'data':[{'code':'202609MM','name':'2026年9月','values':values}]}
        series=parse_nbs(doc,indicators,'精炼铜（电解铜）',{'cu':'品种产量'},'2026-11-03')
        self.assertEqual(series['history'][0]['value'],126)
        self.assertEqual(series['history'][0]['yoy'],1.1)
        self.assertIsNone(series['history'][0]['publishedAt'])
        with self.assertRaises(ValueError):parse_nbs(doc,indicators,'精炼铜（电解铜）',{'cu':'品种产量'},'2026-08-31')
        values[0]['value']=''
        with self.assertRaises(ValueError):parse_nbs(doc,indicators,'精炼铜（电解铜）',{'cu':'品种产量'},'2026-11-03')
        values[0].update(value='126',dp='21')
        with self.assertRaises(ValueError):parse_nbs(doc,indicators,'精炼铜（电解铜）',{'cu':'品种产量'},'2026-11-03')

    def test_casde_date_and_table_schema_guard(self):
        with self.assertRaises(ValueError):parse_casde(b'<h1>report</h1>','https://example.org','2026-11-03')
        html='<h1>中国农产品供需形势分析</h1>日期：2026-11-10'
        with self.assertRaises(ValueError):parse_casde(html.encode(),'https://example.org','2026-11-03')


if __name__=='__main__':unittest.main()
