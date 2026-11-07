# ETF-Backtesting

面向场内 ETF 长期积累策略的可复现研究与回测项目。

## 当前研究目标

验证多只 ETF 共用公共现金池、各自独立持仓账本的长期积累策略，重点比较：

- 固定周期定投；
- 布林下轨分批买入、不主动卖出；
- 布林下轨买入、上轨分批卖出；
- 布林信号驱动的公共资金池动态分配，并保留长期底仓。

本项目首先验证数据是否足以支持可信回测。数据不完整时，必须输出 `MISSING` 或 `UNKNOWN`，不得用模拟数据冒充真实历史结果。

## 初始 ETF 研究池

| 代码 | 产品 | 研究角色 | 状态 |
|---|---|---|---|
| 510300 | 沪深300ETF | A股宽基 | 候选 |
| 510880 | 上证红利ETF | 红利/价值 | 候选 |
| 513020 | 港股通科技ETF | 港股科技成长 | 候选 |
| 159928 | 中证主要消费ETF | 主要消费 | 候选 |
| 159611 | 中证全指电力公用事业ETF | 电力公用事业 | 候选 |

上述是研究候选池，不代表最终必须全部纳入。159611 与 561560 属于同指数产品备选，首轮只选其一；煤炭ETF暂不纳入核心池。产品代码、跟踪指数、上市日期、规模、流动性和费率均须在数据审计阶段重新核验。

## 配置模板

- [ETF候选池](config/etf_universe.yaml)
- [数据源配置](config/data_sources.yaml)
- [回测参数](config/backtest.yaml)
- [交易费用模板](config/trading_costs.yaml)（待券商规则核实）

## 设计文档

- [总体架构](docs/ARCHITECTURE.md)
- [数据契约](docs/DATA_CONTRACT.md)
- [数据审计计划](docs/DATA_AUDIT_PLAN.md)
- [外部历史数据源候选](docs/DATA_SOURCE_OPTIONS.md)
- [指数重叠方法](docs/OVERLAP_METHODOLOGY.md)
- [回测方法](docs/BACKTEST_METHODOLOGY.md)
- [验收标准](docs/ACCEPTANCE_CRITERIA.md)
- [实施与并行开发计划](docs/WORK_PLAN.md)

## 数据源边界

支持两种 free-stockdb 接入形态：本机 LevelDB 服务（本地适配器）与用户提供的远程 `stock_sdk` 双端服务（远程适配器）。远程日线优先通过模块级 `get_price(..., fq=None)` 读取不复权 OHLCV；若实际SDK没有导出该函数，则支持 `rd.get_data(code=..., frequency="1d", fq=None, as_df=True)`。原生 `rd.get()` 是独立高速范围查询。若 `rd.get_data` 是唯一历史入口且原生初始化失败，适配器会明确报错，不会伪称在线API成功，也不会读取本地LevelDB。在线财务与 Tick 仅作为补充数据。服务地址通过环境变量配置，不写入仓库。项目不假定任一服务已具备完整历史数据、有效复权因子、分红事件或历史指数成分权重；必须先运行远程在线API覆盖探测并核验字段和数据语义。详见 [数据源审计](docs/FREE_STOCKDB_SOURCE_AUDIT.md)。

远程 SDK 覆盖探测（在安装了 `stock_sdk` 的本机执行）：

```powershell
$env:STOCKSDK_HOST = "<init() 使用的主机>"
$env:STOCKSDK_PORT = "7899"
$env:STOCKSDK_ONLINE_ENDPOINT = "<set_init() 使用的 host:port>"
# 只有当实际模块函数名不同时才覆盖以下默认值
$env:STOCKSDK_INDEX_API = ""
$env:STOCKSDK_INDEX_STOCKS_API = "get_index_stocks"
$env:STOCKSDK_INDEX_WEIGHTS_API = "get_index_weights"
$env:STOCKSDK_TRADE_DAYS_API = "get_trade_days"
python scripts/probe_remote_sdk_contract.py --index-id 000300.XSHG --date 2020-06-30
```

远程历史数据快照导出（仅访问在线 API，不读取本地 LevelDB）：

```powershell
$env:STOCKSDK_HOST = "106.75.217.246"
$env:STOCKSDK_PORT = "7899"
$env:STOCKSDK_ONLINE_ENDPOINT = "106.75.217.246:12328"
python scripts/export_remote_history.py --start 20000101
```

默认从 2000-01-01 拉取至指定结束日（默认运行日），逐只请求五只ETF的不复权全史日线；并核验已知上市首日。任何首日缺失、日历缺口或未知证券上市日期都会让覆盖门禁保持 UNKNOWN。数据写入 `data/snapshots/remote-stock-sdk/`，并生成包含每只证券记录数、首末日期、SHA-256 和交易日历缺口的 `manifest.json`。某只 ETF 拉取失败不会丢弃其他成功结果；空交易日历或日历接口异常必须标记 UNKNOWN。数据快照目录已被 Git 忽略。日历缺口暂标记为 UNKNOWN，因为缺少逐证券停牌状态时不能把缺K线直接判定为数据错误或停牌。

远程 SDK 原始接口/历史指数返回结构探测（只访问在线接口，不读取本地 LevelDB）：

```powershell
python scripts/probe_remote_sdk_contract.py --index-id 000300.XSHG --date 2020-06-30
```

输出包含实际加载的 `stock_sdk` 模块路径、各接口函数签名、交易日历样本、历史指数返回列名/数据类型/前五行及数值列统计。证券代码字段和权重单位只提供证据，不自动猜测。确认字段后再运行以下历史快照导出：

```powershell
python scripts/export_index_history.py --index-id 000300.XSHG --dates 2020-06-30 2021-06-30 --symbol-field <实际证券代码字段> --weight-field <实际权重字段> --weight-scale percent
```

若 API 返回的权重是 0.0–1.0 的小数比例，将 `--weight-scale` 改为 `fraction`。导入器会拒绝字段缺失、成分重复、非正权重和权重合计不在 100% 容差内的数据；不会把不完整成分列表自动归一化。每个历史日期独立写 CSV 与 SHA-256，失败日期保留在 manifest 中。

## 关键原则

1. 信号计算与成交执行分离：收盘后生成信号，下一交易日按可成交价格执行。
2. 真实成交使用 ETF 未复权市场价格；分红、拆分等公司行为通过独立账本处理。
3. 不得将当前指数成分股回填到历史日期。
4. 所有策略共用同一成交引擎、费用模型、现金池和持仓账本。
5. 原始行情与本地数据快照不提交 GitHub；仓库只保存代码、配置模板、文档和小型测试 fixture。
6. 不对历史回测结果作收益承诺，不以单一历史区间或单一参数作为结论。

## 项目状态

设计基线与四条首轮工作线已合并到 `main`。当前已实现远程在线行情接入、历史数据快照导出、严格历史指数权重导入器、A/B/C/D策略信号编排和共享执行/账本引擎。真实五只ETF快照、指数权重字段/单位、分红事件及完整成交规则仍未验收；正式策略比较仍被这些门禁阻断。详见 [实施状态](docs/IMPLEMENTATION_STATUS.md) 和 [free-stockdb静态审计](docs/FREE_STOCKDB_SOURCE_AUDIT.md)。


### 执行约束配置

正式成交需要逐证券逐交易日的 `ExecutionMarketContext`（bid/ask、涨跌停价、停牌及封板状态）和显式 `ExecutionModel`（滑点、价格冲击、价差上限）。配置模板位于 `config/execution_model.yaml`，未取得历史报价和规则数据前保持 null，不允许用零滑点或 OHLC 开盘价冒充真实成交约束。次日跳空超过分配预算时会按整手部分成交，现金储备在实际成交价再次检查。


### 官方ETF现金分红事件导入

现金分红事件必须来自基金管理人/交易所官方公告，且每只ETF都要有覆盖证明。事件表字段：`symbol,ex_date,record_date,pay_date,cash_per_share,announcement_date,source_name,source_url`；覆盖表字段：`symbol,coverage_start,coverage_end,source_name,source_url`。

```powershell
python scripts/import_dividends.py --events data/raw/official_dividends.csv --coverage data/raw/dividend_coverage.csv --symbols 510300 510880 513020 159928 159611 --coverage-start 2012-01-01 --coverage-end 2026-11-07 --approved-domain <官方公告域名>
```

导入器要求每只ETF的覆盖区间完整、来源域名在显式白名单中、公告日期不晚于除息日、现金分红金额有效。某只ETF没有事件时，只有完整覆盖证明才能表示“该区间未发现分红”；缺少覆盖声明不会默认为零。导出 manifest 的 SHA-256 必须传入正式回测的 `dividend_snapshot_sha256`。
