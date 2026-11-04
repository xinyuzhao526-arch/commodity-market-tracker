# 商品研究终端 · 境内商品研究

[在线研究终端](https://xinyuzhao526-arch.github.io/guanlan-commodities/) · [下载离线 HTML](https://xinyuzhao526-arch.github.io/guanlan-commodities/guanlan.html) · [每日更新记录](https://github.com/xinyuzhao526-arch/guanlan-commodities/actions)。离线文件内嵌数据、样式和脚本，双击即可打开；在线版由下述工作流更新。实际行情日期以页面显示为准。

专业版采用石墨色研究工作台，支持浅色主题、紧凑/舒展密度、导航折叠、Ctrl+K 全局品种搜索和证据侧栏。研究矩阵置于概览指标之后，方法说明默认折叠。终端界面源文件为 `scripts/terminal_ui.js`、`scripts/terminal.css` 和 `scripts/terminal_readability.css`，更新后运行 `python scripts/install_terminal_ui.py`，再导出 HTML。若同时改动研究界面，先运行研究界面安装脚本，再运行终端安装脚本。

2026-10-23 盘后快照共 72 个有成交品种：SHFE 20、INE 5、CZCE 21、DCE 21、GFEX 5。SHFE/INE/CZCE/GFEX 来源为官方公开文件或接口；DCE 历史来自新浪财经具体交割合约日线，10 月 23 日来自日期匹配且 15:00 后的盘后合约快照。所有品种均固定跟踪同一个交割月，未用连续行情冒充固定合约历史。

DCE 的当日日线尚未发布时，仅在盘后快照的交易日期匹配、时间在 15:00 至 21:00 之间、昨收和昨结算分别与前一日日线完全一致、OHLC/成交量/持仓通过校验后追加当日快照，并明确标注来源。其成交量/持仓仅为代表合约，不混入全合约汇总。

会员排名采用**官方优先、东方财富备用**。官方排名已存在时保持原样；仅为缺少排名的代表合约查询东方财富 `RPT_FUTU_DAILYPOSITION`。严格核对交易日期、具体合约、交易所和分页总数，再分别按多头、空头独立名次取最多前20名；不能直接对接口返回的会员并集求和。增减字段缺失保留为空。来源在持仓页、研究侧栏和数据与方法中明确标为东方财富备用，不冒称官方。

空结果、日期或合约不匹配、名次缺口、缺页、重复会员及异常数量均不填入。备用源暂不可用不会抹去官方数据，也不以零补齐。晚间第二次任务会对仍缺失的排名再次查询，即使当天行情已经发布。当前快照的实际覆盖以网页为准；这项接入没有替换行情和历史价格来源。

## 更新真实数据

```powershell
python scripts/update_domestic.py --as-of 2026-10-23 --start 2026-07-14
python scripts/source_czce.py --as-of 2026-10-23 --start 2026-07-14
python scripts/source_dce.py --as-of 2026-10-23 --start 2026-07-14 --refresh
python scripts/source_gfex.py --as-of 2026-10-23 --start 2026-07-14
python scripts/merge_exchanges.py
python scripts/source_rank_fallback.py
python scripts/analyze_markets.py
python scripts/export_html.py
python scripts/export_html.py --output ../商品研究终端_研究雷达_20261023盘后.html
```

以上命令可复现原始快照；切换日期时所有来源的 `--as-of` 必须一致，并使用对应历史窗口。原始数据缓存于 `data/raw/`，独立来源包位于 `data/*-markets.json`。合并校验报告日期、同合约历史、涨跌基准、来源和重复品种。

## GitHub 每日更新与在线访问

工作流：[daily-update.yml](.github/workflows/daily-update.yml)。北京时间周一至周五 18:17 和 20:17 检查最新盘后数据；也可从 Actions → Daily commodity research → Run workflow 手动运行。GitHub 的定时任务可能延迟，页面日期始终表示实际数据日期。

`python scripts/refresh_daily.py` 会在临时目录更新四个来源、合并五个市场、重新计算因子并校验，再替换正式快照。默认使用最近收盘工作日及前 120 个自然日的历史窗口。已发布的相同或更早日期不会重复抓取。上期所目标日文件返回 404 时记录 `no-published-report`，保留旧快照；不将这一状态直接解释为休市。其他下载失败、错日、混合合约、DCE 部分品种失败或交易所覆盖下降超过 20% 均阻止发布。席位缺失仍明确留空，不能保证数据源每天可用。

每次成功更新提交 `dist/data.json`，Git 历史保存旧快照。同一合约在窗口内已验证的历史记录若因下载失败而丢失，会阻止发布。首次运行从 `source-cache` Release 载入已验证的上期所官方历史文件，再读取当天报告；后续使用 Actions 缓存，历史不填充、不插值。Actions 的构建产物提供可下载的 `guanlan.html`（保留 30 天），在线版本也可从 `guanlan.html` 下载。下载到电脑的 HTML 是固定快照，不会自行更新；在线网址显示最新发布版本。

新仓库默认分支使用 `main`。在 Settings → Pages 选择 **GitHub Actions**，并设置仓库变量 `ENABLE_GITHUB_PAGES=true` 后，同一工作流会将 `dist/` 发布到 Pages。未启用该变量时只更新仓库与离线构建，不公开网页。公开仓库不包含 `.openai/`、原始缓存、账号凭据或本地截图；公开内容为本站代码、公开来源加工数据及说明。

本地检查：`python scripts/check_analysis.py` 和 `python -m unittest discover -s tests -v`。本地手动更新示例：

```powershell
python -m pip install -r requirements.txt
python scripts/refresh_daily.py --as-of 2026-10-28
python scripts/export_html.py --output dist/guanlan.html
```

官方全合约数据的代表合约：在当日有成交、收盘价有效的标准期货合约中，取持仓量最大者。走势图始终读取该固定合约。DCE 代表合约另按以上新浪匹配方法核实。缺失收盘不填零。

趋势规则、涨跌幅口径、交易所覆盖与持仓排名边界均在“数据与方法”展示。不能将品种持仓增减称作资金净流入。未连接 Bloomberg / Wind。

## 研究加工层

“研究雷达”提供固定合约 5/20 交易日收盘收益、横截面收益分位、MA20 五日斜率、均线乖离、20日年化历史波动、简单ATR14、前20日量比、收盘突破、价仓象限、席位样本差与增减项差、样本前5集中占比、会员变动贡献、板块收益中位数与广度。每个品种列出支持观察、反向观察和无法验证的解释。

均线与风险指标要求完整的相应交易窗口，不插值缺失价格。计算不使用未来记录；量比和突破的参考区间排除当日。价仓维度只读同一个合约，不混入品种总持仓。只有一天席位排名，不生成连续席位迁移或历史净多分位。当前没有策略回测、收益预测、真实资金流或供需因果推断。

页面筛选、散点选择、证据拆解和研究CSV导出均可离线使用。更新研究界面源文件后运行 `python scripts/install_research_ui.py`；数学边界检查为 `python scripts/check_analysis.py`。

研究页顶部的“均值偏离观察”独立于三维同向状态：以 `(同合约收盘 − MA20) / 简单ATR14` 的绝对值 ≥ 2 筛选，正值关注回调，负值关注反弹，按绝对距离排序。默认显示6个，可展开全部，并筛选上下方或已有反向收盘的品种。矩阵、详情和CSV同时提供该观察。2 ATR是初始观察门槛，未验证反转概率；没有历史极端分位或事件豁免。样本不足或ATR为零时不可计算，不依赖席位覆盖。

“当日回落/反弹”仅比较标注日收盘与昨收；“盘中越界后收回”仅比较当日高低收与此前20日区间，均不等于趋势反转确认。观察区明确显示快照日期，不混入盘中行情；地缘、天气、政策、库存及现货数据尚未作为事件过滤器接入。每日分析脚本自动重新计算该名单。

五日价仓地图的横轴为同合约收盘价格涨跌幅，纵轴为同合约持仓变化率，均使用线性坐标。默认“主体区间”显示持仓变化在−100%至+100%的品种，超出范围的品种不会被压到边界或悄悄丢弃，而会单列五日价格和持仓的真实变化率、合约与起止值；“全部范围”绘入全部有效品种并自适应纵轴。低基数或移仓换月可能放大固定合约持仓变化率，不能解读为价格涨幅或品种整体资金流。运行 `node scripts/check_scatter.cjs` 验证范围、边界和端点隔离。

## 本地预览

```powershell
python -m http.server 8080 --directory dist
```

以上服务器仅用于开发 `dist/` 多文件版本。交付的独立 HTML 可直接双击打开。

`dist/data.json` 必须具有 `schema: domestic-v1`。本仓库仅包含境内商品研究终端，不包含此前的海外研究文件及其他托管平台的配置。


## 三板块与产品研究维度

研究入口聚焦油脂油料、有色金属（含贵金属）和黑色，共34个现有品种；数据采集仍保留全市场快照。板块广度按展示范围重新统计，相对强度分位沿用原始全市场样本。点击品种可切换宏观驱动、供需逻辑、库存变化、合约结构。铜资料来自用户提供的2026年11月2日至3日截图，明确标注未独立核验，并区分LME资料与境内行情；月差符号和单位疑点保留说明。其他品种展示跟踪清单和待补资料状态。研究资料暂不自动更新。
