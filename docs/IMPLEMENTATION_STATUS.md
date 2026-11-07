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
- 以上是代码与模拟契约测试，不代表本次执行环境已真实连接远程服务。真实数据回测必须在能访问远程在线 API 的运行环境执行，并保存原始请求参数、响应摘要和数据快照哈希。
- 分红事件、历史指数权重字段语义、ETF停牌/涨跌停、价差与滑点仍需独立验收；缺失项不得由行情价格推断。
