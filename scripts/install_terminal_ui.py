from pathlib import Path
import re
import json
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'dist/app.js';s=p.read_text(encoding='utf-8')
ui=(ROOT/'scripts/terminal_ui.js').read_text(encoding='utf-8')
packet=json.loads((ROOT/'scripts/domestic_research.json').read_text(encoding='utf-8'))
assert packet['schema']=='domestic-research-v1'
payload=json.dumps(packet,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('&','\\u0026')
domestic='const DOMESTIC_RESEARCH='+payload+';\n'+(ROOT/'scripts/domestic_research_ui.js').read_text(encoding='utf-8')
live_path=ROOT/'dist/fundamentals.json'
live=json.loads(live_path.read_text(encoding='utf-8')) if live_path.exists() else {'inventories':[],'supplies':[],'statuses':[],'asOf':'未取得','checkedAt':'未采集'}
live_payload=json.dumps(live,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('<','\\u003c').replace('&','\\u0026')
domestic+='\nconst LIVE_FUNDAMENTALS='+live_payload+';\n'+(ROOT/'scripts/live_fundamentals_ui.js').read_text(encoding='utf-8')
domestic+='\n'+(ROOT/'scripts/trend_context_ui.js').read_text(encoding='utf-8')
domestic+='\n'+(ROOT/'scripts/research_quality_ui.js').read_text(encoding='utf-8')
ui=ui.replace('// END TERMINAL UI',domestic+'\n// END TERMINAL UI')
if '// BEGIN TERMINAL UI' in s:
 a=s.index('// BEGIN TERMINAL UI');b=s.index('// END TERMINAL UI',a)+len('// END TERMINAL UI');s=s[:a]+ui+s[b:]
else:s=s.replace('function render(){',ui+'\nfunction render(){')
s=re.sub(r'// END TERMINAL UI\s*(?=function render\()', '// END TERMINAL UI\n', s)
# Previous repeated upgrades had duplicated this label; retain one.
label='''<span class="chart-unit">${m.aggregateScope==='representative-contract'?(m.mainMatchedContinuous?'已匹配主力合约':'盘后代表合约'):'持仓量最大合约'}</span>'''
while label+label in s:s=s.replace(label+label,label)
p.write_text(s,encoding='utf-8')
css='\n'.join((ROOT/'scripts'/name).read_text(encoding='utf-8') for name in ['terminal.css','terminal_readability.css'])
(ROOT/'dist/style.css').write_text(css,encoding='utf-8')
print('Terminal interface installed.')

# Give every published script a content-specific URL so a page refresh picks up UI fixes.
import hashlib
index=ROOT/'dist/index.html'
version=hashlib.sha256(p.read_bytes()).hexdigest()[:12]
html=index.read_text(encoding='utf-8')
html,count=re.subn(r'src="app\.js(?:\?[^"<>]*)?"', 'src="app.js?v='+version+'"',html)
assert count==1, 'Expected one application script tag.'
index.write_text(html,encoding='utf-8')
