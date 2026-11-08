# 实施状态（2026-11-07）

## 已合并到 main

| 工作线 | PR | 已落地内容 | CI |
|---|---:|---|---|
| 数据接入 | [#1](https://github.com/just2512/ETF-Backtesting/pull/1)、[#8](https://github.com/just2512/ETF-Backtesting/pull/8)、[#10](https://github.com/just2512/ETF-Backtesting/pull/10)、[#12](https://github.com/just2512/ETF-Backtesting/pull/12)、[#14](https://github.com/just2512/ETF-Backtesting/pull/14)、[#17](https://github.com/just2512/ETF-Backtesting/pull/17) | free-stockdb适配、原始行情探测、质量汇总、复权因子语义门禁、JSON本地报告 | PASS |
| 数据审计 | [#2](https://github.com/just2512/ETF-Backtesting/pull/2)、[#5](https://github.com/just2512/ETF-Backtesting/pull/5)、[#13](https://github.com/just2512/ETF-Backtesting/pull/13) | OHLCV、重复/异常、交易日历缺口、硬门禁状态汇总 | PASS |
| 指数重叠 | [#3](https://github.com/just2512/ETF-Backtesting/pull/3)、[#6](https://github.com/just2512/ETF-Backtesting/pull/6)、[#15](https://github.com/just2512/ETF-Backtesting/pull/15) | 历史生效区间快照、成分/权重重叠、组合穿透、CSV报告 | PASS |
| 回测引擎 | [#4](https://github.com/just2512/ETF-Backtesting/pull/4)、[#7](https://github.com/just2512/ETF-Backtesting/pull/7)、[#9](https://github.com/just2512/ETF-Backtesting/pull/9)、[#11](https://github.com/just2512/ETF-Backtesting/pull/11)、[#18](https://github.com/just2512/ETF-Backtesting/pull/18) | 布林/定投信号、S0/S1/S2卖出、订单编译、下一交易日成交、公共资金池与行业门禁、分红账本、单位净值和组合运行器 | PASS |

四个工作线均已合并，main 最新集成 CI：62 passed，Lint PASS。

## 当前代码范围

已建立可运行的 Python 包、共享数据类型、四个模块包和基础单元测试。当前属于第一轮基础设施，不等于完整回测系统。

### 已实现

- free-stockdb 本地 SDK 适配器：请求不复权行情用于成交模拟；独立读取SDK累计复权因子；复权指标序列只有在语义独立核验后才允许读取。
- 本地探测脚本：对五只候选ETF统计行情数量、首末日期、因子记录数量，按时间升序规范化，并输出OHLC质量和硬门禁汇总；支持本地JSON文件输出。
- 数据质量检查：空数据、重复日期、OHLC、缺失字段、异常数值；提供权威交易日历时可识别缺失交易日，无日历时标记UNKNOWN。
- 指数重叠：集合重叠、权重重叠、组合穿透暴露；可按成分生效区间重建历史快照，并拒绝权重缺失或不归一。
- 布林带：20期默认窗口、2倍总体标准差；窗口不足时不生成指标。
- 账本：买入、卖出、现金分红和外部投入独立记账；按平均成本法维护剩余成本和已实现盈亏。
- 成交模拟与组合运行器：收盘信号日期与下一交易日执行日期严格分离；按下一交易日开盘价、交易单位和停牌状态执行；无当日行情的持仓用最近收盘价估值并标记stale。
- ETF分红：按登记日持仓份额确定权益，在派息日计入现金账本，分红不计为外部投入。
- 信号到订单：按信号日收盘价估算整手数量，下一交易日按真实开盘价执行；跳空造成资金不足时拒绝成交。
- 费用模型：佣金、其他费用、最低佣金和货币精度显式配置，不把未核验费率写成默认事实。
- 公共资金池：按%B偏离程度排序，执行最低现金储备和单只ETF市值上限；可根据指数成分与行业映射限制新增资金分配。
- 行业暴露硬门禁：缺少成分穿透或行业分类时拒绝计算，不静默忽略。
- 策略信号：固定定投、布林下轨四档单周期触发、S0持有/S1上轨卖出/S2回归通道后分两次卖出。
- 绩效基础：账户市值、剔除期末外部投入影响的单位净值、最大回撤。

### 尚未完成

- 用户本机 free-stockdb 服务与真实数据覆盖探测：本机探测已 2026-11-07 完成，见 [FREE_STOCKDB_SOURCE_AUDIT.md](FREE_STOCKDB_SOURCE_AUDIT.md)；但 510300/159928 全史仍待补齐。
- 分红事件数据源及逐笔核验；
- 历史指数成分和历史权重数据源；
- 接入真实交易日历数据并对五只ETF逐只完成缺口审计；
- 涨跌停、买卖价差、滑点、价格冲击及券商最低收费的真实执行规则；
- 公共现金池与行业穿透暴露上限的组合约束；
- 完整A/B/C/D策略编排、卖出S0/S1/S2对照和分配周期状态管理；
- 完整账户估值、收益、回撤、滚动区间与参数稳健性报告。

## free-stockdb 当前结论

静态源码审计已完成，详见 [FREE_STOCKDB_SOURCE_AUDIT.md](FREE_STOCKDB_SOURCE_AUDIT.md)；本机真实数据探测已于 2026-11-07 完成（`python scripts/probe_free_stockdb.py`，退出码 0），结果见同一文档「本机探测结果」。

- 日K/分钟K查询：接口能力 PASS，本机 127.0.0.1:7899 实测可读五只ETF日线。
- 五只ETF实际本地行情覆盖：已探测；510880/513020/159611 覆盖完整，510300/159928 仅 2024-01-02 起、历史不全。
- 复权因子实际覆盖：已探测（510300=14 / 510880=19 / 513020=0 / 159928=1 / 159611=0）；语义仍 UNVERIFIED。
- 现金分红事件接口：当前已检查SDK中 MISSING。
- 带生效日期的历史指数成分/权重接口：当前已检查SDK中 MISSING。
- GitHub仓库不包含本地 `data/` 和 LevelDB 文件；`sync_url.txt` 当前无有效源配置；探测JSON保存在本地 `reports/audit/`（被 .gitignore 排除，不入库）。

## 下一阶段

1. ~~在用户本机运行free-stockdb探测脚本~~ 已完成；下一步针对 510300/159928 补齐 2012/2013 起的历史日线（重跑 `数据更新.exe` 完整同步并核验，或确认数据源历史窗口），并核验 513020/159611 复权因子=0 是否确为无分红所致。
2. 核验交易日历、ETF分红公告、历史指数成分/权重来源及其授权。
3. 完成涨跌停、滑点、价差和券商费用规则的成交模拟。
4. 补齐A/B/C/D完整策略编排、资金流收益计算和滚动/敏感性报告。
5. 以审计通过的真实数据运行历史回测；在此之前不输出真实策略收益结论。


## 远程 stock_sdk 接入（2026-11-07）

- 已合并独立适配器：src/etf_backtesting/adapters/stock_sdk.py。
- 支持双端初始化：init(host, port) 与 set_init(online_endpoint)；服务地址通过 STOCKSDK_HOST、STOCKSDK_PORT、STOCKSDK_ONLINE_ENDPOINT 配置，不写入仓库。
- 历史日线优先走 rd.get_data(..., frequency="1d", fq=None)，只把不复权 OHLCV 转为成交价格；原生 rd.get("日k", ...) 保留原始响应，不在字段结构未验证前强行解析。
- 在线财务查询和实时 Tick 作为补充数据读取接口，不得替代历史日线。
- 适配器提供 probe_symbol() / probe_universe()，输出观察到的日线覆盖与质量检查；无权威交易日历时保持 UNKNOWN。
- CI：stock_sdk adapter PR #20 已合并，精确分支 HEAD 8425d10de8cfb32a3e949c9ef590cec3a4c44629 的 lint / pytest 均 PASS；main 合并提交 3356da86f8561b5ce0556e0f550406d56405aa73 的 CI PASS。
- 尚未完成真实远程联通验收：GitHub Actions 无法访问用户指定的远程服务，实际字段结构、五只 ETF 历史覆盖、复权因子、分红事件及历史指数成分/权重仍须在用户运行环境探测。远程服务页面的功能描述不等同于已验证的历史时点数据契约。

- 已增加本地命令 scripts/probe_stock_sdk.py，默认探测五只 ETF 并输出 reports/audit/stock_sdk_probe.json；当前尚未收到该脚本在用户机器上的真实运行结果。
- 覆盖探测扩展已通过 PR #21 合并；精确分支 HEAD 8377d835bbe0ebf38e7b1f8e3b99b0419fcd97be 的 lint / pytest PASS（Actions run 42377205732）。本机 CLI 随后在 main 增加，尚未取得用户运行后的 JSON。


## 远程在线 API 主链路改造（work/online-api-backtest）

- 历史日线入口已改为在线 `get_price(..., frequency="daily", fq=None, panel=False)`；成交价格只接受不复权 OHLCV。
- 在线端点 `set_init()` 独立初始化。原生 `init(host, port)` 失败会被记录，不再阻断在线历史行情查询；调用原生 `rd.get()` 时才明确报出原生连接失败。
- 已增加 `get_trade_days(start_date, end_date)` 和 `get_history_constituents(index_id, date=...)` 的显式日期读取封装；指数代码由调用方传入含交易所后缀的标识（例如 `000300.XSHG`），不静默改写。
- 新增测试覆盖：7899拒连但12328在线行情仍可读取、强制 `fq=None`、交易日历日期边界、历史指数快照日期参数、原生通道失败隔离。
- 新增 `scripts/export_remote_history.py`：从在线API拉取五只ETF日线，写入Git忽略的快照目录，生成逐证券SHA-256、覆盖区间及交易日历缺口清单；未知停牌状态不会被误判为数据错误。
- 以上是代码与模拟契约测试，不代表本次执行环境已真实连接远程服务。真实数据回测必须在能访问远程在线 API 的运行环境执行，并保存原始请求参数、响应摘要和数据快照哈希。
- 分红事件、历史指数权重字段语义、ETF停牌/涨跌停、价差与滑点仍需独立验收；缺失项不得由行情价格推断。


## 远程在线数据链路修复与历史指数快照导入（2026-11-07）

- PR #23 已合并到 main。初次 CI 失败根因：pytest 从已安装包环境导入仓库根目录 `scripts/`，但 setuptools 只安装 `src/` 包。修复为将导出逻辑放入 `etf_backtesting.data.remote_export`，CLI 脚本只调用包入口。
- PR #23 最新 Actions run #251：Lint PASS，pytest 76 passed。
- 远程历史行情导出脚本已隔离单只证券失败；一个证券超时不会阻断其余证券导出；空交易日历和日历接口异常不会被误判为完整覆盖。
- 新增历史指数成分/权重导入器 `etf_backtesting.data.index_history` 与 CLI `scripts/export_index_history.py`。证券字段名、权重字段名和单位由运行者根据真实 API 响应显式指定；权重总和不归一时拒绝通过。
- 新增单元测试覆盖指数快照日期、fraction/percent单位、重复成分、字段缺失、权重总和异常、逐日期失败隔离及 SHA-256。
- 当前分支新增功能尚待 CI；远程五只ETF全史快照仍须在可访问在线 API 且安装 `pybao` 的运行环境实际执行。GitHub Actions 的模拟测试不等同真实服务导入。
- A/B/C/D 尚未形成同一数据快照、同一现金流、同一成交与成本配置下的可比较完整回测；分红事件、真实权重单位/字段、涨跌停、价差、滑点和价格冲击仍为后续硬门禁。


## A/B/C/D统一策略编排（2026-11-07，待CI与真实数据验收）

新增 `src/etf_backtesting/strategies/orchestrator.py`：

- A：固定周期/日期定投，固定金额按单ETF单次信号生成下一交易日订单。
- B：布林下轨分批买入、不主动卖出。
- C：布林分批买入 + S0/S1/S2卖出状态机；卖出数量在信号收盘时按当前实际持仓计算。
- D：多ETF同时产生布林买入信号，经公共现金池排序分配，执行单只ETF市值上限和最低现金储备；启用行业约束时必须提供当日有效的穿透上下文。
- A/B/C/D均调用同一 `PortfolioBacktestRunner`、`ExecutionEngine`、`PortfolioLedger` 和 `TradingCostModel`，不复制成交/账本逻辑。
- `PortfolioBacktestRunner` 新增收盘后信号回调：生成订单必须在下一交易日执行；允许传入权威交易日历，使缺失行情不会被误当作下一交易日成交。
- A/B/C单ETF独立比较；D用于多ETF公共现金池，避免A/B/C多证券订单按代码顺序隐式抢占现金。
- 未通过分红或执行规则门禁时，正式模式拒绝运行；`research_only=True` 可执行研究性机制测试，结果显式携带未通过门禁状态，不得作为正式收益结论。
- A/B/C的 `per_etf_cycle_budget` 是单个布林买入周期的额度基数；四档比例作用于该额度。该预算、D的单只市值上限、现金储备、初始资金和定投日程必须由配置/调用方明确传入，不写入虚构默认值。

新增测试覆盖A定投下一日成交、B布林买入下一日开盘成交、C的S1卖出持仓数量、D公共资金池与现金储备、正式门禁失败关闭，以及A/B/C多ETF调用边界。

本模块目前属于策略机制与接口实现；当前CI通过后仍需以真实远程快照完成A/B/C/D同口径历史比较。分红、涨跌停、滑点、价差和价格冲击未通过时只能运行 `research_only`。


### 统一执行层补充门禁

- `OrderIntent.cash_limit` 将买入订单绑定到信号日分配额度，下一交易日开盘跳空导致成交额+费用超过该额度时拒绝成交。
- `ExecutionEngine.minimum_cash_reserve` 在实际开盘价成交时再次检查最低现金储备，避免收盘时分配通过、次日跳空后突破储备线。
- D策略执行顺序保留 `CashPoolAllocator` 的显式信号优先级，不再按证券代码重新排序。
- 已新增测试覆盖预算超限拒单、最低现金储备保护、D策略开盘跳空后分配优先级与储备守恒。


### 可复现报告与历史指数正式门禁

- 新增 `etf_backtesting.reports.strategy_report`，输出 `report.json`、`equity_curve.csv`、`executions.csv`、`ledger_events.csv`。
- 报告以数据快照 SHA-256、完整运行配置 SHA-256、策略标识生成确定性 run_id；记录信号/成交时序、现金流时点、价格口径、策略门禁、逐笔成交、账本事件、NAV和最大回撤。
- 外部追加资金按 BEGINNING 时点剥离后计算单位净值；现金分红保留为投资现金流，不计作外部投入。
- 报告拒绝缺少数据快照哈希或完整运行配置的调用，研究性结果明确标记 research_only。
- D策略若启用行业/指数穿透约束，正式运行还必须显式提供历史指数暴露 PASS；不启用时将该项标为 NOT_APPLICABLE。不能将当前成分权重视作历史权重。
- A/B/C/D均要求初始资金为正；资金、周期预算、单只上限、现金储备必须由调用方明确传入。


## 远程 SDK 原始契约核验

- 已确认公开 `just2512/free-stockdb/pybao/stock_sdk.py` 与用户给出的 `sdk_test.py` 模块级 API 不是同一接口：公开文件没有 `set_init/get_price/get_fundamentals/get_last_tick`。
- 不使用不匹配的公开模块伪造远程接入。新增 `scripts/probe_remote_sdk_contract.py`，运行时记录用户实际导入的模块路径、函数签名、历史指数原始返回字段和数值列统计。
- 当前仍未取得用户实际 `./pybao/` 的文件或运行时模块路径，真实远程全史 CSV 导入、历史指数字段/单位确认尚未执行；这不是行情数据可用性否定，而是当前执行环境没有该确切 SDK 模块。


## 行情成交约束模型（2026-11-07，代码已实现，真实数据仍缺）

- `ExecutionMarketContext` 按证券/交易日显式提供买一价、卖一价、涨跌停价、停牌状态和涨跌停封板状态。
- `ExecutionModel` 显式提供滑点 bps、价格冲击 bps、最大允许价差，并可要求报价、涨跌停和停牌状态完整。
- 买入按卖一价、卖出按买一价成交，再施加不利滑点和冲击；成交价越过涨跌停价则拒绝。
- 缺少报价、涨跌停状态或停牌状态时，正式运行不允许默认使用 OHLC 开盘价替代；缺失上下文产生 NO_FILL，正式模式随后 fail-closed。
- 若次日开盘跳空导致原订单超出分配预算或现金储备，执行引擎按整手二分搜索最大可负担数量，生成 PARTIAL；若连一手也不可负担则 REJECTED。
- D策略的分配优先级按信号优先级执行；部分成交仍受每笔分配额度和最低现金储备约束。
- 新增 `config/execution_model.yaml`，所有需要外部证据的参数保持 null；未接入真实历史报价、涨跌停/停牌状态和滑点/冲击校准前，正式回测门禁仍为 UNKNOWN。


## A/B/C/D同口径矩阵入口

新增 `StrategyComparisonRunner`（`etf_backtesting.strategies.comparison`），一次运行生成：

- 每只 ETF 独立的 A 固定定投、B 布林分批买入、C 布林买卖三组结果；
- 一组 D 多 ETF 公共现金池结果；
- 所有结果共用相同交易日历、初始资金、追加资金、费用模型、分红输入和执行市场上下文；
- A/B/C逐只独立运行，避免单ETF策略之间共享现金产生代码顺序抢占；D统一多ETF资金池。
- 缺少任一ETF的定投预算、周期预算或D市值上限时直接拒绝矩阵运行。
- 每个结果可分别传给 `build_strategy_report`，并绑定同一行情/报价快照哈希与各自完整参数配置哈希。

该矩阵入口解决策略运行编排，不代表真实数据已导入或正式回测门禁已通过。


## 官方分红事件与覆盖门禁（2026-11-07）

- 扩展 `ETFDividend`，保留公告日期、来源名称和官方公告URL。
- 新增 `etf_backtesting.data.dividend_import` 与 `scripts/import_dividends.py`：分开读取事件CSV与逐ETF覆盖证明CSV。
- 五只ETF必须各自有覆盖起止日期完整的官方来源声明；事件来源域名必须命中显式HTTPS白名单；公告日期不得晚于除息日；分红金额必须为正；事件不得重复。
- 某ETF没有分红事件，不再自动等于零分红；只有该ETF完整覆盖证明存在且通过校验，才允许在该区间认定未发现事件。
- 导入器生成事件+覆盖双文件组合SHA-256；正式回测 `dividend_status=PASS` 必须传入该哈希，且每条事件都带公告来源元数据。
- 报告将记录分红快照哈希。当前没有真实官方公告事件/覆盖文件，分红门禁仍 MISSING；导入器和门禁已实现，未伪造任何事件。


### 对照公开 sdk_test.py 的历史行情接口

- 已读取 `just2512/free-stockdb/调用方式/python/sdk_test.py`：其批量历史行情示例实际调用 `rd.get_data(code, start, end, frequency="1d", fq=...)`，而不是模块级 `get_price`；原生范围查询使用 `rd.get()`。
- 适配器现优先使用用户此前实测的在线 `get_price(..., fq=None)`；当该函数不存在时，支持 `rd.get_data(..., fq=None, as_df=True)`。若仅有 `rd.get_data` 且 7899 原生初始化失败，会明确报错，不假装在线API可用。
- SDK探测脚本同时记录模块级接口与 `rd.get/rd.get_data` 的真实签名。
- 不复权参数在两条路径都显式设置为 `fq=None`，不沿用 sdk_test.py 示例中的 `qfq`。


### 历史指数API名称按用户实测修正

- 用户PR #22 的本机实测文档明确列出 `get_index_stocks` 与 `get_index_weights`，此前单一 `get_history_constituents` 假设不应作为默认。
- 适配器现默认分别调用两个接口，并按证券代码合并；字段、单位仍显式输入。
- 探测脚本输出两份接口各自的字段、样例和数值统计；`STOCKSDK_INDEX_API` 仅用于运行时确实存在的单一组合接口。


### 全史导入窗口修正

- `export_remote_history.py` 不再依赖 SDK 的默认返回窗口；显式传入 `start=20000101` 与 `end=运行日`，并对五只ETF逐只发起请求，符合在线API单标的限制。
- 使用用户远程实测的五只ETF首个交易日作为硬核验：510300=2012-05-28、510880=2007-01-18、513020=2022-02-08、159928=2013-09-16、159611=2022-01-07。首日晚于预期标 UNKNOWN，早于预期标 REJECT。
- 交易日历检查扩展到请求结束日，而不是只检查到最后一根已返回K线，能够发现数据尾部停更。
- 自定义证券若未提供预期上市首日，覆盖状态保持 UNKNOWN，不会误报全史 PASS。


## 远程全史与历史指数审计补强（2026-11-08）

- 全史导出器修正：未配置上市日期或请求起点晚于已知上市日期时，`history_coverage_status` 必须为 UNKNOWN，不再错误默认为 PASS。
- 新增 `calendar_gaps.csv`：逐只ETF列出交易日历中缺失的日期，标记 `UNCLASSIFIED` 并说明缺少逐证券停牌状态；manifest 同时记录该文件 SHA-256 和行数。
- 历史指数导出新增 `temporal_diff.csv`：对相邻成功快照逐项列出成分新增、剔除及权重变化；多日期快照没有差异时，历史日期语义保持 UNKNOWN。
- 这些改动只完善数据导入和审计代码；没有将 CI 模拟 SDK 测试描述为真实远程导出，也没有生成虚假的行情/指数快照。


## 2026-11-08 远程数据与回测状态复核

### CI 与代码合并
- PR #23 已合并；PR 检查 run #251（commit `c31e9ed`）：Lint PASS，pytest 76 passed。
- PR #34 已合并；修复全史覆盖 UNKNOWN 门禁、生成逐日 `calendar_gaps.csv`、生成历史指数快照 `temporal_diff.csv`。
- PR #34 检查 run #449：Lint PASS，pytest 123 passed；合并后 main run #450：Lint PASS，pytest 123 passed。

### 真实远程数据状态
- 远程五只 ETF 的历史根数和首日，仍以用户 2026-11-07 提供的远程实测记录为证据；GitHub Actions 的测试使用模拟 SDK，不是在线数据下载。
- 当前仓库没有真实 `data/snapshots/remote-stock-sdk/manifest.json`、五只 ETF CSV 或真实 `calendar_gaps.csv`；因此本轮不能把“导入完成”记为 PASS。
- 历史指数成分/权重的字段名与单位仍须来自实际 SDK 响应样本。导入器只接受显式 `symbol_field`、`weight_field` 和 `fraction/percent`，不自动猜测或归一化不完整权重。
- 历史日期语义现可由 `temporal_diff.csv` 检查，但尚无本轮真实多日期导出文件，仍不能将本轮真实指数导入记为 PASS。

### SDK 运行时契约待核对
- 用户提供的在线运行方式包含 `set_init`、在线财务/Tick 函数；但公开仓库 `just2512/free-stockdb/pybao/stock_sdk.py` 当前只显示 `StockDBClient` 包装类，并导入原生 `stockdb.init/rd`，未导出远程适配器当前要求的模块级 `set_init`、`get_price`、`get_trade_days`、`get_index_stocks`、`get_index_weights`。
- 官方说明页宣称 SDK 另有在线 API，但 API 详细文档重定向后当前无法由本次检索环境读取。不能据此臆造具体函数签名。
- 这不否定用户在其机器上实测的 12328 在线服务；它说明仓库可见的 SDK 源码与用户实际运行时模块不是同一份可确认契约。正式导出必须记录实际 `stock_sdk.__file__`、函数签名和原始返回样本，再确认适配器契约一致。

### 策略与正式回测门禁
- A/B/C/D 策略比较编排、D 公共资金池、统一账本、下一交易日执行、报价/涨跌停/停牌/滑点/冲击约束和可复现报告写入器均已有代码及模拟契约测试。
- A/B/C 按单只 ETF 分别运行，D 为多 ETF 公共资金池组合；正式回测仍要求分红事件快照、历史执行市场上下文和费用参数门禁 PASS。
- `config/trading_costs.yaml` 与 `config/execution_model.yaml` 仍有未确认参数为 null；不得用零费用、零滑点或 OHLC 开盘价替代真实成交规则。
- 分红事件仍 MISSING。现有官方公告 CSV 导入器可校验事件及逐 ETF 覆盖证明，但尚未有完整的五只 ETF 官方事件/零事件覆盖数据文件。
- 因此当前允许做的是研究性机制回测（明确 `research_only=True`）；正式策略收益结论仍 BLOCKED。


## 2026-11-08 后续数据门禁与报告交付

- PR #35：`PriceBar` 在共享数据契约入口拒绝 OHLCV 中的 NaN/Infinity；PR CI run #455：Lint PASS，pytest 129 passed。
- PR #36：分红覆盖按每只ETF自身上市日期核验，避免用单一全局起点错误覆盖不同上市历史；PR CI run #460：Lint PASS，pytest 125 passed。
- PR #37：新增 A/B/C（逐ETF）与 D（公共资金池）比较报告编排，生成每次运行的 report/equity/executions/ledger 文件及总览 `comparison.json`、`comparison.csv`；初次CI发现并修复子报告相对路径问题，最终 PR CI run #469：Lint PASS，pytest 132 passed。
- 以上均为代码和模拟契约验收；不代表产生了真实行情快照或正式回测收益。

### 当前阻断项保持原样
- 远程五只ETF真实快照、逐日缺口CSV：尚未在本轮执行环境中生成。
- 历史指数真实多日期权重快照及权重字段/单位确认：尚未生成。
- 官方分红公告事件与逐标的完整覆盖文件：尚未生成，分红门禁仍 MISSING。
- 历史逐日 bid/ask、涨跌停/封板、停牌状态和经确认费用参数：尚未齐备，正式执行门禁仍 UNKNOWN。


## 2026-11-08 真实运行环境交付（Jerry 本机）

云端要求的 SDK 契约与真实快照在本机完成取证，详见 [STOCK_SDK_RUNTIME_CONTRACT.md](STOCK_SDK_RUNTIME_CONTRACT.md)；机器可读契约 `reports/audit/remote_sdk_contract.json` 已生成（本地保留，不入库）。

### 取得的 SDK 契约（云端清单逐项回应）

- `stock_sdk.__file__` = `D:\stockdb\pybao\stock_sdk.py`；底层 `stockdb.pyd` 注入 RemoteProxy。模块级可调用 72 个。
- 实测签名：`init(host='127.0.0.1', port=7899, socket_timeout=None, password=None, warm=True)`；`set_init(ip='', df=None, cpu=None)`；`get_price/get_bars/get_trade_days/get_index_stocks/get_index_weights/get_history_constituents/get_last_tick/get_security_info` 为 RemoteProxy（无 Python 签名）；`get_fundamentals(query_object, date=None, statDate=None)`。
- 原始返回样本记录于契约 JSON（日历 43 交易日 PASS；price/bars/index 在探测时点返回服务端错误字符串）。

### 依契约发现并修复的三个适配器缺陷（本轮提交）

1. **日历日期格式**：`get_trade_days` 传 `YYYYMMDD` 静默返回 `[]`（实测），仅短横线格式有效。`read_trade_days` 现在内部转换 8 位日期；`scripts/probe_remote_sdk_contract.py` 同步修复。
2. **`get_price` 列表模式丢日期列**（2026-11-07 实测 `[{'open':..,'close':..}]` 无 date；文档 §12.2 证实 df 模式日期在索引）：`read_daily_bars` 现在先 `set_init(endpoint, df=True)` 再查询。
3. **服务端故障返回裸错误字符串而非异常**（2026-11-08 实测 `"\n执行查询时发生错误"`）：适配器现将其识别为 ConnectionError 并携带原文，不再伪装成 TypeError 数据结构问题。

测试：本机 pytest **134 passed**（新增错误字符串识别、df 模式、日历格式断言）；ruff 由 CI 执行。

### 真实服务状态（2026-11-08 探测时点）

- `get_trade_days` 正常（日历 PASS）；其余在线查询 API（price/bars/index/tick/security）返回服务端错误字符串——同一服务 2026-11-07 曾全部正常，属供应商端波动而非契约消失。
- K线库 7899 拒连、7898 协议不匹配（与 2026-11-07 结论一致）。
- 真实五只ETF快照导出已运行：manifest 诚实记录五只全部 UNKNOWN + ConnectionError（服务端原文），无伪造数据；`get_price` 恢复后重跑 `scripts/export_remote_history.py` 即可产出真实 CSV。
- 本地 `数据更新.exe` 同步链路健康（`ah/ad.123128.xyz` 可达），但源数据仅提供 510300/159928 自 2024-01-02 起的日线，与 2026-11-07 结论一致。

### 阻断项更新

- ~~SDK 运行时契约待核对~~ → 已取得（本节）。
- 远程五只ETF真实快照 → 适配器契约已对齐，等待供应商 `get_price` 服务恢复后重跑导出。
- 历史指数字段/单位确认 → `get_index_stocks/get_index_weights` 待服务恢复后按契约 JSON 取样。
- 分红事件、历史执行上下文、费用参数门禁 → 保持 MISSING/UNKNOWN，无变化。
